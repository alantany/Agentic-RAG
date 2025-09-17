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
            if cursor:
                cursor.close()
    
    def find_documents(self, query_conditions: Dict[str, Any] = None, 
                      patient_id: str = None) -> List[Dict[str, Any]]:
        """查找JSON文档"""
        try:
            connection = self.get_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()
            
            # 构建查询SQL
            base_sql = f"""
            SELECT id, patient_id, {self.config["json_column"]}, 
                   {self.config["metadata_column"]}, created_date, updated_date
            FROM {self.config["table_name"]}
            """
            
            where_conditions = []
            params = {}
            
            # 添加患者ID过滤
            if patient_id:
                where_conditions.append("patient_id = :patient_id")
                params['patient_id'] = patient_id
            
            # 添加JSON查询条件
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
            
            cursor.execute(query_sql, params)
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
            st.error(f"查找JSON文档失败: {str(e)}")
            return []
        
        finally:
            if cursor:
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
                   SCORE(1) as relevance_score
            FROM {self.config["table_name"]}
            WHERE CONTAINS({self.config["json_column"]}, :search_text, 1) > 0
            """
            
            params = {'search_text': search_text}
            
            # 添加患者过滤
            if patient_id:
                search_sql = f"{base_sql} AND patient_id = :patient_id"
                params['patient_id'] = patient_id
            else:
                search_sql = base_sql
            
            search_sql += " ORDER BY SCORE(1) DESC"
            
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
            if cursor:
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
            if cursor:
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
            if cursor:
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
            if cursor:
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
        # 提取患者姓名
        import re
        common_surnames = "李王张刘陈杨黄周吴马蒲赵钱孙朱胡郭何高林罗郑梁谢宋唐许邓冯韩曹曾彭萧蔡潘田董袁于余叶蒋杜苏魏程吕丁沈任姚卢傅钟姜崔谭廖范汪陆金石戴贾韦夏邱方侯邹熊孟秦白江阎薛尹段雷黎史龙陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
        pattern = f'([{common_surnames}])某某'
        patient_match = re.search(pattern, query)
        patient_filter = patient_match.group(0) if patient_match else None
        
        # 搜索文档
        docs = oracle_json_store.search_documents(query, patient_filter)
        
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
