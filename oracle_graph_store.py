"""
Oracle 23ai 图数据库存储实现
替代 NetworkX/Neo4j，使用 Oracle Graph
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import streamlit as st
from oracle_23ai_config import oracle_manager, get_graph_config
import oracledb

class OracleGraphStore:
    """Oracle 23ai图数据库存储"""
    
    def __init__(self):
        self.config = get_graph_config()
        self.connection = None
    
    def _safe_json_parse(self, data):
        """安全解析JSON数据"""
        if not data:
            return {}
        if isinstance(data, str):
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return {}
        elif isinstance(data, dict):
            return data
        else:
            return {}
    
    def get_connection(self):
        """获取数据库连接"""
        if not self.connection:
            self.connection = oracle_manager.get_connection()
        return self.connection
    
    def create_vertex(self, vertex_type: str, vertex_label: str, 
                     properties: Dict[str, Any]) -> Optional[int]:
        """创建图顶点"""
        try:
            connection = self.get_connection()
            if not connection:
                return None
            
            cursor = connection.cursor()
            
            # 插入顶点
            insert_sql = f"""
            INSERT INTO {self.config["vertex_table"]} 
            (vertex_type, vertex_label, properties)
            VALUES (:vertex_type, :vertex_label, :properties)
            RETURNING vertex_id INTO :vertex_id
            """
            
            vertex_id_var = cursor.var(int)
            cursor.execute(insert_sql, {
                'vertex_type': vertex_type,
                'vertex_label': vertex_label,
                'properties': json.dumps(properties, ensure_ascii=False),
                'vertex_id': vertex_id_var
            })
            
            connection.commit()
            vertex_id = vertex_id_var.getvalue()[0]
            
            return vertex_id
            
        except Exception as e:
            st.error(f"创建顶点失败: {str(e)}")
            if connection:
                connection.rollback()
            return None
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def create_edge(self, source_vertex_id: int, target_vertex_id: int,
                   edge_type: str, edge_label: str = None, 
                   properties: Dict[str, Any] = None) -> Optional[int]:
        """创建图边"""
        try:
            connection = self.get_connection()
            if not connection:
                return None
            
            cursor = connection.cursor()
            
            if edge_label is None:
                edge_label = edge_type
            if properties is None:
                properties = {}
            
            # 插入边
            insert_sql = f"""
            INSERT INTO {self.config["edge_table"]} 
            (source_vertex_id, target_vertex_id, edge_type, edge_label, properties)
            VALUES (:source_vertex_id, :target_vertex_id, :edge_type, :edge_label, :properties)
            RETURNING edge_id INTO :edge_id
            """
            
            edge_id_var = cursor.var(int)
            cursor.execute(insert_sql, {
                'source_vertex_id': source_vertex_id,
                'target_vertex_id': target_vertex_id,
                'edge_type': edge_type,
                'edge_label': edge_label,
                'properties': json.dumps(properties, ensure_ascii=False),
                'edge_id': edge_id_var
            })
            
            connection.commit()
            edge_id = edge_id_var.getvalue()[0]
            
            return edge_id
            
        except Exception as e:
            st.error(f"创建边失败: {str(e)}")
            if connection:
                connection.rollback()
            return None
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def find_vertices(self, vertex_type: str = None, vertex_label: str = None,
                     property_filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """查找顶点"""
        try:
            connection = self.get_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()
            
            # 构建查询SQL
            base_sql = f"""
            SELECT vertex_id, vertex_type, vertex_label, properties, created_date
            FROM {self.config["vertex_table"]}
            """
            
            where_conditions = []
            params = {}
            
            if vertex_type:
                where_conditions.append("vertex_type = :vertex_type")
                params['vertex_type'] = vertex_type
            
            if vertex_label:
                where_conditions.append("vertex_label = :vertex_label")
                params['vertex_label'] = vertex_label
            
            # 添加属性过滤（使用JSON查询）
            if property_filters:
                for key, value in property_filters.items():
                    condition_name = f"prop_{len(params)}"
                    where_conditions.append(f"JSON_VALUE(properties, '$.{key}') = :{condition_name}")
                    params[condition_name] = str(value)
            
            # 完整SQL
            if where_conditions:
                query_sql = f"{base_sql} WHERE {' AND '.join(where_conditions)}"
            else:
                query_sql = base_sql
            
            cursor.execute(query_sql, params)
            results = cursor.fetchall()
            
            # 格式化结果
            vertices = []
            for row in results:
                vertex = {
                    'vertex_id': row[0],
                    'vertex_type': row[1],
                    'vertex_label': row[2],
                    'properties': self._safe_json_parse(row[3]),
                    'created_date': row[4]
                }
                vertices.append(vertex)
            
            return vertices
            
        except Exception as e:
            st.error(f"查找顶点失败: {str(e)}")
            return []
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def find_edges(self, source_vertex_id: int = None, target_vertex_id: int = None,
                  edge_type: str = None) -> List[Dict[str, Any]]:
        """查找边"""
        try:
            connection = self.get_connection()
            if not connection:
                return []
            
            cursor = connection.cursor()
            
            # 构建查询SQL
            base_sql = f"""
            SELECT e.edge_id, e.source_vertex_id, e.target_vertex_id, 
                   e.edge_type, e.edge_label, e.properties, e.created_date,
                   sv.vertex_label as source_label, tv.vertex_label as target_label
            FROM {self.config["edge_table"]} e
            LEFT JOIN {self.config["vertex_table"]} sv ON e.source_vertex_id = sv.vertex_id
            LEFT JOIN {self.config["vertex_table"]} tv ON e.target_vertex_id = tv.vertex_id
            """
            
            where_conditions = []
            params = {}
            
            if source_vertex_id:
                where_conditions.append("e.source_vertex_id = :source_vertex_id")
                params['source_vertex_id'] = source_vertex_id
            
            if target_vertex_id:
                where_conditions.append("e.target_vertex_id = :target_vertex_id")
                params['target_vertex_id'] = target_vertex_id
            
            if edge_type:
                where_conditions.append("e.edge_type = :edge_type")
                params['edge_type'] = edge_type
            
            # 完整SQL
            if where_conditions:
                query_sql = f"{base_sql} WHERE {' AND '.join(where_conditions)}"
            else:
                query_sql = base_sql
            
            cursor.execute(query_sql, params)
            results = cursor.fetchall()
            
            # 格式化结果
            edges = []
            for row in results:
                edge = {
                    'edge_id': row[0],
                    'source_vertex_id': row[1],
                    'target_vertex_id': row[2],
                    'edge_type': row[3],
                    'edge_label': row[4],
                    'properties': self._safe_json_parse(row[5]),
                    'created_date': row[6],
                    'source_label': row[7],
                    'target_label': row[8]
                }
                edges.append(edge)
            
            return edges
            
        except Exception as e:
            st.error(f"查找边失败: {str(e)}")
            return []
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def graph_traversal(self, start_vertex_id: int, edge_types: List[str] = None,
                       max_depth: int = 2) -> Dict[str, Any]:
        """图遍历查询"""
        try:
            connection = self.get_connection()
            if not connection:
                return {}
            
            cursor = connection.cursor()
            
            # 使用递归CTE进行图遍历
            edge_filter = ""
            params = {'start_vertex': start_vertex_id, 'max_depth': max_depth}
            
            if edge_types:
                placeholders = ', '.join([f':edge_type_{i}' for i in range(len(edge_types))])
                edge_filter = f"AND e.edge_type IN ({placeholders})"
                for i, edge_type in enumerate(edge_types):
                    params[f'edge_type_{i}'] = edge_type
            
            traversal_sql = f"""
            WITH graph_traversal (vertex_id, vertex_label, vertex_type, properties, 
                                 path, depth) AS (
                -- 起始顶点
                SELECT vertex_id, vertex_label, vertex_type, properties, 
                       vertex_label as path, 0 as depth
                FROM {self.config["vertex_table"]}
                WHERE vertex_id = :start_vertex
                
                UNION ALL
                
                -- 递归遍历
                SELECT tv.vertex_id, tv.vertex_label, tv.vertex_type, tv.properties,
                       gt.path || ' -> ' || tv.vertex_label as path, gt.depth + 1
                FROM graph_traversal gt
                JOIN {self.config["edge_table"]} e ON gt.vertex_id = e.source_vertex_id
                JOIN {self.config["vertex_table"]} tv ON e.target_vertex_id = tv.vertex_id
                WHERE gt.depth < :max_depth {edge_filter}
            )
            SELECT * FROM graph_traversal ORDER BY depth, vertex_id
            """
            
            cursor.execute(traversal_sql, params)
            results = cursor.fetchall()
            
            # 格式化结果
            traversal_result = {
                'start_vertex_id': start_vertex_id,
                'max_depth': max_depth,
                'vertices': [],
                'paths': []
            }
            
            for row in results:
                vertex_info = {
                    'vertex_id': row[0],
                    'vertex_label': row[1],
                    'vertex_type': row[2],
                    'properties': self._safe_json_parse(row[3]),
                    'path': row[4],
                    'depth': row[5]
                }
                traversal_result['vertices'].append(vertex_info)
                
                if row[5] > 0:  # 不包括起始顶点的路径
                    traversal_result['paths'].append(row[4])
            
            return traversal_result
            
        except Exception as e:
            st.error(f"图遍历失败: {str(e)}")
            return {}
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def build_graph_from_json_data(self, json_documents: List[Dict[str, Any]]) -> bool:
        """从JSON文档构建图数据库"""
        try:
            st.write("开始从JSON数据构建图数据库...")
            
            vertex_cache = {}  # 缓存已创建的顶点
            
            for doc_data in json_documents:
                document = doc_data.get('document', {})
                patient_id = doc_data.get('patient_id', 'Unknown')
                
                st.write(f"处理患者: {patient_id}")
                
                # 1. 创建患者顶点
                patient_vertex_id = self.create_vertex(
                    vertex_type="patient",
                    vertex_label=patient_id,
                    properties={"name": patient_id}
                )
                
                if not patient_vertex_id:
                    continue
                
                vertex_cache[f"patient_{patient_id}"] = patient_vertex_id
                
                # 2. 处理基本信息
                basic_info_fields = ['性别', '年龄', '民族', '职业', '婚姻状况']
                for field in basic_info_fields:
                    if field in document and document[field]:
                        vertex_id = self.create_vertex(
                            vertex_type="basic_info",
                            vertex_label=f"{field}_{document[field]}",
                            properties={
                                "field_name": field,
                                "field_value": str(document[field])
                            }
                        )
                        
                        if vertex_id:
                            self.create_edge(
                                source_vertex_id=patient_vertex_id,
                                target_vertex_id=vertex_id,
                                edge_type="has_basic_info"
                            )
                
                # 3. 处理主诉
                if '主诉' in document and document['主诉']:
                    vertex_id = self.create_vertex(
                        vertex_type="chief_complaint",
                        vertex_label=f"主诉_{patient_id}",
                        properties={"content": str(document['主诉'])}
                    )
                    
                    if vertex_id:
                        self.create_edge(
                            source_vertex_id=patient_vertex_id,
                            target_vertex_id=vertex_id,
                            edge_type="has_complaint"
                        )
                
                # 4. 处理现病史
                if '现病史' in document and document['现病史']:
                    vertex_id = self.create_vertex(
                        vertex_type="present_illness",
                        vertex_label=f"现病史_{patient_id}",
                        properties={"content": str(document['现病史'])}
                    )
                    
                    if vertex_id:
                        self.create_edge(
                            source_vertex_id=patient_vertex_id,
                            target_vertex_id=vertex_id,
                            edge_type="has_present_illness"
                        )
                
                # 5. 处理生化指标
                if '生化指标' in document and document['生化指标']:
                    lab_data = document['生化指标']
                    if isinstance(lab_data, dict):
                        for indicator, value in lab_data.items():
                            if value:
                                vertex_id = self.create_vertex(
                                    vertex_type="lab_result",
                                    vertex_label=f"生化指标_{indicator}_{value}",
                                    properties={
                                        "indicator_name": str(indicator),
                                        "indicator_value": str(value)
                                    }
                                )
                                
                                if vertex_id:
                                    self.create_edge(
                                        source_vertex_id=patient_vertex_id,
                                        target_vertex_id=vertex_id,
                                        edge_type="has_lab_result"
                                    )
                
                # 6. 处理诊断
                if '诊断' in document and document['诊断']:
                    vertex_id = self.create_vertex(
                        vertex_type="diagnosis",
                        vertex_label=f"诊断_{patient_id}",
                        properties={"content": str(document['诊断'])}
                    )
                    
                    if vertex_id:
                        self.create_edge(
                            source_vertex_id=patient_vertex_id,
                            target_vertex_id=vertex_id,
                            edge_type="has_diagnosis"
                        )
                
                # 7. 处理治疗方案
                if '治疗方案' in document and document['治疗方案']:
                    vertex_id = self.create_vertex(
                        vertex_type="treatment",
                        vertex_label=f"治疗方案_{patient_id}",
                        properties={"content": str(document['治疗方案'])}
                    )
                    
                    if vertex_id:
                        self.create_edge(
                            source_vertex_id=patient_vertex_id,
                            target_vertex_id=vertex_id,
                            edge_type="has_treatment"
                        )
            
            st.write("✅ 图数据库构建完成")
            return True
            
        except Exception as e:
            st.error(f"构建图数据库失败: {str(e)}")
            return False
    
    def search_graph(self, query_conditions: Dict[str, Any]) -> List[str]:
        """搜索图数据库"""
        try:
            start_node = query_conditions.get("start_node", {})
            relationship = query_conditions.get("relationship", "")
            end_node = query_conditions.get("end_node", {})
            
            # 查找起始顶点
            start_vertices = self.find_vertices(
                vertex_type=start_node.get("type"),
                vertex_label=start_node.get("name")
            )
            
            if not start_vertices:
                return []
            
            results = []
            
            for start_vertex in start_vertices:
                # 查找相关的边
                edges = self.find_edges(
                    source_vertex_id=start_vertex['vertex_id'],
                    edge_type=relationship
                )
                
                for edge in edges:
                    # 获取目标顶点信息
                    target_vertices = self.find_vertices()  # 获取所有顶点以便匹配
                    
                    for target_vertex in target_vertices:
                        if (target_vertex['vertex_id'] == edge['target_vertex_id'] and
                            target_vertex['vertex_type'] == end_node.get("type")):
                            
                            # 格式化结果
                            properties = target_vertex['properties']
                            
                            # 根据节点类型提取相应的属性
                            if target_vertex['vertex_type'] == 'lab_result':
                                field_name = properties.get('indicator_name', '')
                                field_value = properties.get('indicator_value', '')
                            elif target_vertex['vertex_type'] == 'basic_info':
                                field_name = properties.get('field_name', '')
                                field_value = properties.get('field_value', '')
                            else:
                                field_name = 'content'
                                field_value = properties.get('content', '')
                            
                            result_str = f"{start_vertex['vertex_label']} -> {edge['edge_type']} -> {field_name}: {field_value}"
                            results.append(result_str)
            
            return results
            
        except Exception as e:
            st.error(f"图搜索失败: {str(e)}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """获取图数据库统计信息"""
        try:
            connection = self.get_connection()
            if not connection:
                return {}
            
            cursor = connection.cursor()
            
            # 统计顶点数
            cursor.execute(f"SELECT COUNT(*) FROM {self.config['vertex_table']}")
            vertex_count = cursor.fetchone()[0]
            
            # 统计边数
            cursor.execute(f"SELECT COUNT(*) FROM {self.config['edge_table']}")
            edge_count = cursor.fetchone()[0]
            
            # 统计不同类型的顶点
            cursor.execute(f"""
                SELECT vertex_type, COUNT(*) 
                FROM {self.config['vertex_table']} 
                GROUP BY vertex_type
            """)
            vertex_types = dict(cursor.fetchall())
            
            # 统计不同类型的边
            cursor.execute(f"""
                SELECT edge_type, COUNT(*) 
                FROM {self.config['edge_table']} 
                GROUP BY edge_type
            """)
            edge_types = dict(cursor.fetchall())
            
            return {
                'total_vertices': vertex_count,
                'total_edges': edge_count,
                'vertex_types': vertex_types,
                'edge_types': edge_types,
                'graph_name': self.config['graph_name']
            }
            
        except Exception as e:
            st.error(f"获取图统计信息失败: {str(e)}")
            return {}
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    def clear_all_graph_data(self) -> bool:
        """清空所有图数据"""
        try:
            connection = self.get_connection()
            if not connection:
                return False
            
            cursor = connection.cursor()
            
            # 先删除边（因为外键约束）
            cursor.execute(f"DELETE FROM {self.config['edge_table']}")
            # 再删除顶点
            cursor.execute(f"DELETE FROM {self.config['vertex_table']}")
            
            connection.commit()
            
            st.write("✅ 图数据库数据清空成功")
            return True
            
        except Exception as e:
            st.error(f"清空图数据库数据失败: {str(e)}")
            if connection:
                connection.rollback()
            return False
        
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()

# 全局图存储实例
oracle_graph_store = OracleGraphStore()

def build_oracle_graph_from_json(json_documents: List[Dict[str, Any]]) -> bool:
    """从JSON文档构建Oracle图数据库"""
    return oracle_graph_store.build_graph_from_json_data(json_documents)

def get_oracle_graph_search_results(query: str) -> List[str]:
    """Oracle图搜索结果"""
    # 这里需要实现查询解析逻辑，类似于原来的generate_graph_query
    # 暂时使用简化的关键词匹配
    
    import re
    
    # 提取患者姓名
    common_surnames = "李王张刘陈杨黄周吴马蒲赵钱孙朱胡郭何高林罗郑梁谢宋唐许邓冯韩曹曾彭萧蔡潘田董袁于余叶蒋杜苏魏程吕丁沈任姚卢傅钟姜崔谭廖范汪陆金石戴贾韦夏邱方侯邹熊孟秦白江阎薛尹段雷黎史龙陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
    pattern = f'([{common_surnames}])某某'
    patient_match = re.search(pattern, query)
    patient_name = patient_match.group(0) if patient_match else "周某某"
    
    # 根据关键词确定查询类型
    query_lower = query.lower()
    
    if any(word in query_lower for word in ['主诉', '症状', '不适']):
        query_obj = {
            "start_node": {"type": "patient", "name": patient_name},
            "relationship": "has_complaint",
            "end_node": {"type": "chief_complaint"}
        }
    elif any(word in query_lower for word in ['生化指标', '检验', '化验']):
        query_obj = {
            "start_node": {"type": "patient", "name": patient_name},
            "relationship": "has_lab_result",
            "end_node": {"type": "lab_result"}
        }
    elif any(word in query_lower for word in ['诊断', '病情', '疾病']):
        query_obj = {
            "start_node": {"type": "patient", "name": patient_name},
            "relationship": "has_diagnosis",
            "end_node": {"type": "diagnosis"}
        }
    else:
        # 默认查询基本信息
        query_obj = {
            "start_node": {"type": "patient", "name": patient_name},
            "relationship": "has_basic_info",
            "end_node": {"type": "basic_info"}
        }
    
    return oracle_graph_store.search_graph(query_obj)

def get_oracle_graph_stats() -> Dict[str, Any]:
    """获取Oracle图数据库统计"""
    return oracle_graph_store.get_stats()

def clear_oracle_graph() -> bool:
    """清空Oracle图数据库"""
    return oracle_graph_store.clear_all_graph_data()

if __name__ == "__main__":
    # 测试图存储
    print("Oracle 23ai图数据库测试")
    print("=" * 50)
    
    store = OracleGraphStore()
    
    # 测试创建顶点
    print("测试图数据库操作...")
    
    # 注意：实际运行需要先初始化数据库连接
    print("⚠️  请在实际使用前初始化Oracle 23ai连接")
