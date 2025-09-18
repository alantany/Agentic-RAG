"""
Oracle 23ai JSON文档存储实现
替代 MongoDB，使用 Oracle JSON
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import streamlit as st
from oracle_23ai_config import oracle_manager, get_json_config
import oracledb

class OracleJSONStore:
    """Oracle 23ai JSON文档存储"""
    
    def __init__(self):
        self.config = get_json_config()
        self.connection = None
    
    def get_connection(self):
        """获取数据库连接"""
        if not self.connection:
            self.connection = oracle_manager.get_connection()
        return self.connection
    
    def insert_document(self, patient_id: str, document: Dict[str, Any], 
                       metadata: Dict[str, Any] = None) -> bool:
        """插入JSON文档"""
        try:
            connection = self.get_connection()
            if not connection:
                raise Exception("无法获取数据库连接")
            
            cursor = connection.cursor()
            
            # 添加时间戳
            document['import_time'] = datetime.now().isoformat()
            if metadata is None:
                metadata = {}
            metadata['import_time'] = datetime.now().isoformat()
            
            # 插入文档
            insert_sql = f"""
            INSERT INTO {self.config["table_name"]} 
            (patient_id, {self.config["json_column"]}, {self.config["metadata_column"]})
            VALUES (:patient_id, :doc_data, :metadata)
            """
            
            cursor.execute(insert_sql, {
                'patient_id': patient_id,
                'doc_data': json.dumps(document, ensure_ascii=False),
                'metadata': json.dumps(metadata, ensure_ascii=False)
            })
            
            connection.commit()
            st.write(f"✅ 成功插入患者 {patient_id} 的文档")
            return True
            
        except Exception as e:
            st.error(f"插入JSON文档失败: {str(e)}")
            if connection:
                connection.rollback()
            return False
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def find_documents(self, query_conditions: Dict[str, Any] = None, 
                      patient_id: str = None, query_text: str = None) -> List[Dict[str, Any]]:
        """查找JSON文档"""
        try:
            connection = self.get_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()
            
            # 首先检查表中是否有数据
            cursor.execute(f"SELECT COUNT(*) FROM {self.config['table_name']}")
            total_count = cursor.fetchone()[0]
            st.write(f"📄 JSON表中总记录数: {total_count}")
            
            # 构建查询SQL
            base_sql = f"""
            SELECT id, patient_id, {self.config["json_column"]}, 
                   {self.config["metadata_column"]}, created_date, updated_date
            FROM {self.config["table_name"]}
            """
            
            where_conditions = []
            params = {}
            
            # 添加患者ID过滤 - 使用LIKE进行模糊匹配
            if patient_id:
                where_conditions.append("patient_id LIKE :patient_id")
                params['patient_id'] = f"%{patient_id}%"
            
            # 简化关键词搜索 - 先测试基本搜索
            if query_text and query_text.strip():
                # 提取查询中的关键词
                keywords = []
                if '主诉' in query_text:
                    keywords.append('主诉')
                if '现病史' in query_text:
                    keywords.append('现病史')
                if '头晕' in query_text:
                    keywords.append('头晕')
                if '症状' in query_text:
                    keywords.append('症状')
                
                st.write(f"📄 提取的关键词: {keywords}")
                
                # 为每个关键词添加LIKE条件（使用OR连接，更宽松）
                if keywords:
                    keyword_conditions = []
                    for i, keyword in enumerate(keywords):
                        condition_name = f"keyword_{i}"
                        keyword_conditions.append(f"UPPER({self.config['json_column']}) LIKE UPPER(:{condition_name})")
                        params[condition_name] = f"%{keyword}%"
                    
                    # 使用OR连接关键词条件
                    if keyword_conditions:
                        where_conditions.append(f"({' OR '.join(keyword_conditions)})")
                else:
                    # 如果没有特定关键词，搜索所有记录
                    st.write(f"📄 没有找到特定关键词，将返回所有匹配患者的记录")
            
            # 添加JSON查询条件（保留原有逻辑）
            if query_conditions:
                for key, value in query_conditions.items():
                    condition_name = f"condition_{len(params)}"
                    if isinstance(value, str):
                        where_conditions.append(f"JSON_VALUE({self.config['json_column']}, '$.{key}') = :{condition_name}")
                    else:
                        where_conditions.append(f"JSON_VALUE({self.config['json_column']}, '$.{key}') = :{condition_name}")
                    params[condition_name] = str(value)
            
            # 完整SQL
            if where_conditions:
                query_sql = f"{base_sql} WHERE {' AND '.join(where_conditions)}"
            else:
                query_sql = base_sql
            
            st.write(f"📄 执行SQL: {query_sql}")
            st.write(f"📄 参数: {params}")
            
            # 先测试简单查询，看看能否获取数据
            cursor.execute(f"SELECT COUNT(*) FROM {self.config['table_name']} WHERE patient_id LIKE '%周某某%'")
            patient_count = cursor.fetchone()[0]
            st.write(f"📄 患者'周某某'相关记录数: {patient_count}")
            
            cursor.execute(query_sql, params)
            results = cursor.fetchall()
            
            st.write(f"📄 原始查询返回 {len(results)} 行")
            
            # 格式化结果 - 安全处理JSON数据
            documents = []
            for row in results:
                # 安全地处理DOC_DATA
                doc_data = row[2]
                if isinstance(doc_data, dict):
                    document = doc_data
                elif isinstance(doc_data, str):
                    try:
                        document = json.loads(doc_data)
                    except:
                        document = {'raw_content': doc_data}
                else:
                    document = {'raw_content': str(doc_data)}
                
                # 安全地处理DOC_METADATA
                metadata_data = row[3]
                if isinstance(metadata_data, dict):
                    metadata = metadata_data
                elif isinstance(metadata_data, str):
                    try:
                        metadata = json.loads(metadata_data)
                    except:
                        metadata = {}
                else:
                    metadata = {}
                
                doc = {
                    'id': row[0],
                    'patient_id': row[1],
                    'document': document,
                    'metadata': metadata,
                    'created_date': row[4],
                    'updated_date': row[5]
                }
                documents.append(doc)
                
                # 调试信息
                st.write(f"📄 成功解析文档: 患者={row[1]}, keys={list(document.keys())}")
            
            return documents
            
        except Exception as e:
            st.error(f"查找JSON文档失败: {str(e)}")
            return []
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def search_documents(self, search_text: str, patient_id: str = None) -> List[Dict[str, Any]]:
        """全文搜索JSON文档"""
        try:
            connection = self.get_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()
            
            # 使用Oracle Text搜索
            base_sql = f"""
            SELECT id, patient_id, {self.config["json_column"]}, 
                   {self.config["metadata_column"]}, created_date, updated_date,
                   1.0 as relevance_score
            FROM {self.config["table_name"]}
            WHERE {self.config["json_column"]} LIKE :search_text
            """
            
            params = {'search_text': f'%{search_text}%'}
            
            # 添加患者过滤
            if patient_id:
                search_sql = f"{base_sql} AND patient_id = :patient_id"
                params['patient_id'] = patient_id
            else:
                search_sql = base_sql
            
            search_sql += " ORDER BY created_date DESC"
            
            cursor.execute(search_sql, params)
            results = cursor.fetchall()
            
            # 格式化结果
            documents = []
            for row in results:
                doc = {
                    'id': row[0],
                    'patient_id': row[1],
                    'document': json.loads(row[2]) if row[2] else {},
                    'metadata': json.loads(row[3]) if row[3] else {},
                    'created_date': row[4],
                    'updated_date': row[5],
                    'relevance_score': float(row[6])
                }
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            # 如果全文搜索失败，使用简单的LIKE搜索
            st.warning(f"全文搜索失败，使用简单搜索: {str(e)}")
            return self._simple_search(search_text, patient_id)
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def _simple_search(self, search_text: str, patient_id: str = None) -> List[Dict[str, Any]]:
        """简单的LIKE搜索（备用方案）"""
        try:
            connection = self.get_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()
            
            base_sql = f"""
            SELECT id, patient_id, {self.config["json_column"]}, 
                   {self.config["metadata_column"]}, created_date, updated_date
            FROM {self.config["table_name"]}
            WHERE {self.config["json_column"]} LIKE :search_pattern
            """
            
            params = {'search_pattern': f'%{search_text}%'}
            
            if patient_id:
                search_sql = f"{base_sql} AND patient_id = :patient_id"
                params['patient_id'] = patient_id
            else:
                search_sql = base_sql
            
            cursor.execute(search_sql, params)
            results = cursor.fetchall()
            
            # 格式化结果
            documents = []
            for row in results:
                doc = {
                    'id': row[0],
                    'patient_id': row[1],
                    'document': json.loads(row[2]) if row[2] else {},
                    'metadata': json.loads(row[3]) if row[3] else {},
                    'created_date': row[4],
                    'updated_date': row[5]
                }
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            st.error(f"简单搜索失败: {str(e)}")
            return []
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def get_patient_info(self, patient_name: str) -> Dict[str, Any]:
        """获取患者基本信息"""
        try:
            # 查找患者文档
            docs = self.find_documents(patient_id=patient_name)
            
            if not docs:
                return {}
            
            # 合并所有文档信息
            patient_info = {}
            for doc in docs:
                document = doc['document']
                patient_info.update(document)
            
            return patient_info
            
        except Exception as e:
            st.error(f"获取患者信息失败: {str(e)}")
            return {}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取文档库统计信息"""
        try:
            connection = self.get_connection()
            if not connection:
                return {}
            
            cursor = connection.cursor()
            
            # 统计总文档数
            cursor.execute(f"SELECT COUNT(*) FROM {self.config['table_name']}")
            total_docs = cursor.fetchone()[0]
            
            # 统计患者数
            cursor.execute(f"SELECT COUNT(DISTINCT patient_id) FROM {self.config['table_name']}")
            patient_count = cursor.fetchone()[0]
            
            # 最近更新时间
            cursor.execute(f"SELECT MAX(updated_date) FROM {self.config['table_name']}")
            last_updated = cursor.fetchone()[0]
            
            return {
                'total_documents': total_docs,
                'unique_patients': patient_count,
                'last_updated': last_updated,
                'table_name': self.config['table_name']
            }
            
        except Exception as e:
            st.error(f"获取统计信息失败: {str(e)}")
            return {}
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def clear_all_documents(self) -> bool:
        """清空所有文档"""
        try:
            connection = self.get_connection()
            if not connection:
                return False
            
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM {self.config['table_name']}")
            connection.commit()
            
            st.write("✅ JSON文档数据清空成功")
            return True
            
        except Exception as e:
            st.error(f"清空JSON文档数据失败: {str(e)}")
            if connection:
                connection.rollback()
            return False
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()

# 全局JSON存储实例
oracle_json_store = OracleJSONStore()

def get_oracle_connection():
    """获取Oracle连接（兼容接口）"""
    return oracle_json_store.get_connection()

def import_to_oracle_json(document: Dict[str, Any], patient_name: str) -> bool:
    """导入文档到Oracle JSON存储"""
    metadata = {
        'source_type': 'pdf',
        'import_time': datetime.now().isoformat(),
        'last_updated': datetime.now().isoformat()
    }
    
    return oracle_json_store.insert_document(patient_name, document, metadata)

def get_oracle_json_search_results(query: str) -> List[str]:
    """Oracle JSON搜索结果"""
    try:
        import streamlit as st
        # 提取患者姓名
        import re
        common_surnames = "李王张刘陈杨黄周吴马蒲赵钱孙朱胡郭何高林罗郑梁谢宋唐许邓冯韩曹曾彭萧蔡潘田董袁于余叶蒋杜苏魏程吕丁沈任姚卢傅钟姜崔谭廖范汪陆金石戴贾韦夏邱方侯邹熊孟秦白江阎薛尹段雷黎史龙陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
        pattern = f'([{common_surnames}])某某'
        patient_match = re.search(pattern, query)
        patient_filter = patient_match.group(0) if patient_match else None
        
        # 调试信息
        st.write(f"📄 JSON搜索调试: 查询='{query}', 患者过滤='{patient_filter}'")
        
        # 搜索文档 - 直接使用最简单的搜索方法
        try:
            # 先尝试按患者搜索
            docs = oracle_json_store.find_documents(patient_id=patient_filter, query_text=query)
            st.write(f"📄 按患者搜索找到 {len(docs)} 个文档")
            
            # 如果没找到，尝试搜索所有文档
            if len(docs) == 0:
                st.write(f"📄 患者搜索无结果，尝试全表搜索...")
                docs = oracle_json_store.find_documents(query_text=query)
                st.write(f"📄 全表搜索找到 {len(docs)} 个文档")
        except Exception as e:
            st.write(f"📄 搜索出错: {str(e)}")
            docs = []
        
        # 显示文档样本（调试用）
        for i, doc in enumerate(docs[:2]):
            st.write(f"📄 文档{i+1}: 患者={doc['patient_id']}, 文档keys={list(doc['document'].keys())}")
        
        results = []
        for doc in docs:
            document = doc['document']
            patient_name = doc['patient_id']
            
            # 格式化结果
            if '患者姓名' in document:
                results.append(f"患者 {document['患者姓名']} 的患者姓名是：{document['患者姓名']}")
            
            if '生化指标' in document:
                results.append(f"患者 {patient_name} 的生化指标：")
                lab_data = document['生化指标']
                if isinstance(lab_data, dict):
                    for indicator, value in lab_data.items():
                        if value:
                            results.append(f"• {indicator}: {value}")
        
        return results
        
    except Exception as e:
        st.error(f"Oracle JSON搜索失败: {str(e)}")
        return []

def get_oracle_json_stats() -> Dict[str, Any]:
    """获取Oracle JSON库统计"""
    return oracle_json_store.get_stats()

def clear_oracle_json() -> bool:
    """清空Oracle JSON数据"""
    return oracle_json_store.clear_all_documents()

if __name__ == "__main__":
    # 测试JSON存储
    print("Oracle 23ai JSON存储测试")
    print("=" * 50)
    
    store = OracleJSONStore()
    
    # 测试文档
    test_doc = {
        "患者姓名": "测试患者",
        "性别": "男",
        "年龄": 45,
        "主诉": "头痛3天",
        "生化指标": {
            "血糖": "5.6mmol/L",
            "血压": "120/80mmHg"
        }
    }
    
    print("测试文档结构:")
    print(json.dumps(test_doc, ensure_ascii=False, indent=2))
