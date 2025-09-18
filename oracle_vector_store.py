"""
Oracle 23ai 向量存储实现
替代 Pinecone，使用 Oracle AI Vector Search
"""

import numpy as np
import json
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer
import streamlit as st
from oracle_23ai_config import oracle_manager, get_vector_config, get_oracle_config
import oracledb

class OracleVectorStore:
    """Oracle 23ai向量存储"""
    
    def __init__(self):
        self.config = get_vector_config()
        self.model = None
        self.connection = None
    
    def initialize_model(self):
        """初始化embedding模型"""
        try:
            st.write("初始化embedding模型...")
            from config import get_sentence_transformer_config
            st_config = get_sentence_transformer_config()
            
            self.model = SentenceTransformer(
                st_config["model_name"],
                cache_folder=st_config["cache_folder"],
                device=st_config["device"]
            )
            
            st.write("✅ Embedding模型初始化成功")
            return True
            
        except Exception as e:
            st.error(f"Embedding模型初始化失败: {str(e)}")
            return False
    
    def get_connection(self):
        """获取数据库连接"""
        if not self.connection:
            self.connection = oracle_manager.get_connection()
        return self.connection
    
    def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """创建文本向量"""
        if not self.model:
            if not self.initialize_model():
                raise Exception("无法初始化embedding模型")
        
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings
        except Exception as e:
            st.error(f"创建向量失败: {str(e)}")
            raise
    
    def insert_vectors(self, texts: List[str], metadatas: List[Dict[str, Any]], 
                      patient_names: List[str] = None) -> bool:
        """插入向量数据"""
        try:
            # 创建向量
            embeddings = self.create_embeddings(texts)
            
            connection = self.get_connection()
            if not connection:
                raise Exception("无法获取数据库连接")
            
            cursor = connection.cursor()
            
            # 逐条插入向量数据（使用Oracle 23ai原生VECTOR类型）
            insert_sql = f"""
            INSERT INTO {self.config["table_name"]} 
            (patient_name, content, {self.config["embedding_column"]}, {self.config["metadata_column"]})
            VALUES (:patient_name, :content, :vector_data, :metadata)
            """
            
            # 逐条插入
            for i, (text, metadata, embedding) in enumerate(zip(texts, metadatas, embeddings)):
                patient_name = patient_names[i] if patient_names else metadata.get('patient_name', 'Unknown')
                
                # 使用TO_VECTOR函数和参数绑定
                vector_str = '[' + ','.join(map(str, embedding.tolist())) + ']'
                
                # 使用TO_VECTOR函数避免字符串长度限制
                insert_sql_with_to_vector = f"""
                INSERT INTO {self.config["table_name"]} 
                (patient_name, content, {self.config["embedding_column"]}, {self.config["metadata_column"]})
                VALUES (:patient_name, :content, TO_VECTOR(:vector_data), :metadata)
                """
                
                cursor.execute(insert_sql_with_to_vector, {
                    'patient_name': patient_name,
                    'content': text,
                    'vector_data': vector_str,
                    'metadata': json.dumps(metadata, ensure_ascii=False)
                })
            connection.commit()
            
            st.write(f"✅ 成功插入 {len(texts)} 条向量记录")
            return True
            
        except Exception as e:
            st.error(f"插入向量数据失败: {str(e)}")
            if connection:
                connection.rollback()
            return False
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def search_similar_vectors(self, query_text: str, top_k: int = 5, 
                              patient_filter: str = None) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        try:
            # 创建查询向量
            query_embedding = self.create_embeddings([query_text])[0]
            
            connection = self.get_connection()
            if not connection:
                raise Exception("无法获取数据库连接")
            
            cursor = connection.cursor()
            
            # 使用Oracle 23ai原生向量搜索 - 使用TO_VECTOR函数
            # 将查询向量转换为字符串，然后用TO_VECTOR函数转换
            vector_str = '[' + ','.join(map(str, query_embedding.tolist())) + ']'
            
            base_sql = f"""
            SELECT id, patient_name, content, {self.config["embedding_column"]}, {self.config["metadata_column"]},
                   COSINE_DISTANCE({self.config["embedding_column"]}, TO_VECTOR(:query_vector)) as distance
            FROM {self.config["table_name"]}
            """
            
            # 添加患者过滤条件
            where_clause = ""
            params = {'query_vector': vector_str}
            
            if patient_filter:
                where_clause = " WHERE patient_name = :patient_name"
                params['patient_name'] = patient_filter
            
            # 添加排序和限制
            order_clause = f" ORDER BY COSINE_DISTANCE({self.config['embedding_column']}, TO_VECTOR(:query_vector)) FETCH FIRST {top_k} ROWS ONLY"
            
            # 完整SQL
            search_sql = f"{base_sql} {where_clause} {order_clause}"
            
            st.write(f"🔍 生成的SQL: {search_sql[:200]}...")  # 显示SQL调试信息
            st.write(f"🔍 向量字符串长度: {len(vector_str)}")  # 显示向量字符串长度
            
            cursor.execute(search_sql, params)
            results = cursor.fetchall()
            
            st.write(f"🔍 数据库查询返回了 {len(results)} 行数据")
            
            # Oracle 23ai已经计算了距离，直接使用结果
            formatted_results = []
            for i, row in enumerate(results):
                try:
                    # Oracle 23ai原生向量搜索结果
                    distance = float(row[5])  # Oracle计算的距离
                    similarity = 1 - distance  # 将距离转换为相似度
                    
                    # 处理元数据 - Oracle可能返回已解析的字典或JSON字符串
                    metadata_raw = row[4]
                    if isinstance(metadata_raw, dict):
                        # 如果已经是字典，直接使用
                        metadata = metadata_raw
                    elif isinstance(metadata_raw, str):
                        # 如果是字符串，尝试解析
                        metadata = json.loads(metadata_raw)
                    else:
                        # 其他情况，使用空字典
                        metadata = {}
                    
                    # 处理CLOB字段
                    content = row[2]
                    if hasattr(content, 'read'):
                        # 如果是CLOB对象，读取内容
                        content = content.read()
                    
                    result = {
                        'id': row[0],
                        'patient_name': row[1],
                        'content': content,
                        'metadata': metadata,
                        'similarity': float(similarity),
                        'distance': float(distance)
                    }
                    formatted_results.append(result)
                    
                    # 调试：显示前几个结果的相似度
                    if i < 3:
                        content_preview = content[:50] + "..." if len(content) > 50 else content
                        st.write(f"🔍 第{i+1}条: 患者={row[1]}, 距离={distance:.4f}, 相似度={similarity:.4f}, 内容={content_preview}")
                        st.write(f"🔍 元数据类型: {type(metadata_raw)}, 内容类型: {type(row[2])}")
                        
                except Exception as e:
                    st.write(f"⚠️ 第{i+1}条结果处理失败: {str(e)}")
                    continue
            
            return formatted_results
            
        except Exception as e:
            st.error(f"向量搜索失败: {str(e)}")
            return []
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取向量库统计信息"""
        try:
            connection = self.get_connection()
            if not connection:
                return {}
            
            cursor = connection.cursor()
            
            # 统计总数
            cursor.execute(f"SELECT COUNT(*) FROM {self.config['table_name']}")
            total_count = cursor.fetchone()[0]
            
            # 统计患者数
            cursor.execute(f"SELECT COUNT(DISTINCT patient_name) FROM {self.config['table_name']}")
            patient_count = cursor.fetchone()[0]
            
            # 最近更新时间
            cursor.execute(f"SELECT MAX(updated_date) FROM {self.config['table_name']}")
            last_updated = cursor.fetchone()[0]
            
            return {
                'total_vectors': total_count,
                'unique_patients': patient_count,
                'last_updated': last_updated,
                'dimension': self.config['dimension'],
                'distance_metric': self.config['distance_metric']
            }
            
        except Exception as e:
            st.error(f"获取统计信息失败: {str(e)}")
            return {}
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def clear_all_vectors(self) -> bool:
        """清空所有向量数据"""
        try:
            connection = self.get_connection()
            if not connection:
                return False
            
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM {self.config['table_name']}")
            connection.commit()
            
            st.write("✅ 向量数据清空成功")
            return True
            
        except Exception as e:
            st.error(f"清空向量数据失败: {str(e)}")
            if connection:
                connection.rollback()
            return False
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()

# 全局向量存储实例
oracle_vector_store = OracleVectorStore()

def init_oracle_vector_store():
    """初始化Oracle向量存储"""
    return oracle_vector_store

def get_oracle_vector_search_results(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Oracle向量搜索结果"""
    import re
    import streamlit as st
    
    # 提取患者姓名（更灵活的匹配）
    common_surnames = "李王张刘陈杨黄周吴马蒲赵钱孙朱胡郭何高林罗郑梁谢宋唐许邓冯韩曹曾彭萧蔡潘田董袁于余叶蒋杜苏魏程吕丁沈任姚卢傅钟姜崔谭廖范汪陆金石戴贾韦夏邱方侯邹熊孟秦白江阎薛尹段雷黎史龙陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
    pattern = f'([{common_surnames}])某某'
    patient_match = re.search(pattern, query)
    patient_filter = patient_match.group(0) if patient_match else None
    
    # 调试信息
    st.write(f"🔍 向量搜索调试: 查询='{query}', 患者过滤='{patient_filter}'")
    
    # 首先尝试带患者过滤的搜索
    results = oracle_vector_store.search_similar_vectors(
        query_text=query,
        top_k=top_k,
        patient_filter=patient_filter
    )
    
    # 如果没有结果且有患者过滤，尝试不过滤的搜索
    if not results and patient_filter:
        st.write("🔍 患者过滤搜索无结果，尝试通用搜索...")
        results = oracle_vector_store.search_similar_vectors(
            query_text=query,
            top_k=top_k,
            patient_filter=None
        )
    
    st.write(f"🔍 向量搜索最终返回: {len(results)} 个结果")
    return results

def import_to_oracle_vectors(texts: List[str], metadatas: List[Dict[str, Any]], 
                           patient_names: List[str] = None) -> bool:
    """导入数据到Oracle向量存储"""
    return oracle_vector_store.insert_vectors(texts, metadatas, patient_names)

def get_oracle_vector_stats() -> Dict[str, Any]:
    """获取Oracle向量库统计"""
    return oracle_vector_store.get_stats()

def clear_oracle_vectors() -> bool:
    """清空Oracle向量数据"""
    return oracle_vector_store.clear_all_vectors()

if __name__ == "__main__":
    # 测试向量存储
    print("Oracle 23ai向量存储测试")
    print("=" * 50)
    
    # 初始化
    store = OracleVectorStore()
    
    if store.initialize_model():
        print("✅ 模型初始化成功")
        
        # 测试创建向量
        test_texts = ["患者主诉头痛", "血压偏高需要治疗"]
        embeddings = store.create_embeddings(test_texts)
        print(f"✅ 成功创建 {len(embeddings)} 个向量，维度: {embeddings[0].shape}")
    else:
        print("❌ 模型初始化失败")
