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
            
            # 准备插入语句
            insert_sql = f"""
            INSERT INTO {self.config["table_name"]} 
            (patient_name, content, {self.config["embedding_column"]}, {self.config["metadata_column"]})
            VALUES (:patient_name, :content, :vector_data, :metadata)
            """
            
            # 批量插入
            batch_data = []
            for i, (text, metadata, embedding) in enumerate(zip(texts, metadatas, embeddings)):
                patient_name = patient_names[i] if patient_names else metadata.get('patient_name', 'Unknown')
                
                # 将numpy数组转换为Oracle向量格式
                vector_array = embedding.tolist()
                
                batch_data.append({
                    'patient_name': patient_name,
                    'content': text,
                    'vector_data': vector_array,
                    'metadata': json.dumps(metadata, ensure_ascii=False)
                })
            
            cursor.executemany(insert_sql, batch_data)
            connection.commit()
            
            st.write(f"✅ 成功插入 {len(batch_data)} 条向量记录")
            return True
            
        except Exception as e:
            st.error(f"插入向量数据失败: {str(e)}")
            if connection:
                connection.rollback()
            return False
        
        finally:
            if cursor:
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
            
            # 构建搜索SQL
            base_sql = f"""
            SELECT id, patient_name, content, {self.config["metadata_column"]},
                   VECTOR_DISTANCE({self.config["embedding_column"]}, :query_vector, {self.config["distance_metric"]}) as distance
            FROM {self.config["table_name"]}
            """
            
            # 添加患者过滤条件
            where_clause = ""
            params = {'query_vector': query_embedding.tolist()}
            
            if patient_filter:
                where_clause = " WHERE patient_name = :patient_name"
                params['patient_name'] = patient_filter
            
            # 完整SQL
            search_sql = f"""
            {base_sql} {where_clause}
            ORDER BY VECTOR_DISTANCE({self.config["embedding_column"]}, :query_vector, {self.config["distance_metric"]})
            FETCH FIRST :top_k ROWS ONLY
            """
            
            params['top_k'] = top_k
            
            cursor.execute(search_sql, params)
            results = cursor.fetchall()
            
            # 格式化结果
            formatted_results = []
            for row in results:
                result = {
                    'id': row[0],
                    'patient_name': row[1],
                    'content': row[2],
                    'metadata': json.loads(row[3]) if row[3] else {},
                    'distance': float(row[4]),
                    'similarity': 1 - float(row[4])  # 转换为相似度分数
                }
                formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            st.error(f"向量搜索失败: {str(e)}")
            return []
        
        finally:
            if cursor:
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
            if cursor:
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
            if cursor:
                cursor.close()

# 全局向量存储实例
oracle_vector_store = OracleVectorStore()

def init_oracle_vector_store():
    """初始化Oracle向量存储"""
    return oracle_vector_store

def get_oracle_vector_search_results(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Oracle向量搜索结果"""
    import re
    
    # 提取患者姓名
    common_surnames = "李王张刘陈杨黄周吴马蒲赵钱孙朱胡郭何高林罗郑梁谢宋唐许邓冯韩曹曾彭萧蔡潘田董袁于余叶蒋杜苏魏程吕丁沈任姚卢傅钟姜崔谭廖范汪陆金石戴贾韦夏邱方侯邹熊孟秦白江阎薛尹段雷黎史龙陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
    pattern = f'([{common_surnames}])某某'
    patient_match = re.search(pattern, query)
    patient_filter = patient_match.group(0) if patient_match else None
    
    # 执行搜索
    results = oracle_vector_store.search_similar_vectors(
        query_text=query,
        top_k=top_k,
        patient_filter=patient_filter
    )
    
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
