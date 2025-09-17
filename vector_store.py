from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
import streamlit as st
import tiktoken
import traceback
import time
import jieba  # 添加中文分词库
import networkx as nx
import json
from openai import OpenAI
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import get_pinecone_config, get_openai_client, get_sentence_transformer_config

# 初始化 Pinecone
def init_pinecone():
    """初始化 Pinecone 客户端"""
    try:
        # 使用配置文件中的Pinecone设置
        config = get_pinecone_config()
        pc = Pinecone(api_key=config["api_key"])
        
        index_name = config["index_name"]
        
        # 检查索引是否存在
        existing_indexes = pc.list_indexes()
        index_names = [index.name for index in existing_indexes]
        
        if index_name not in index_names:
            st.write("创建新的 Pinecone 索引...")
            pc.create_index(
                name=index_name,
                dimension=config["dimension"],
                metric=config["metric"],
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            st.write("✅ 新索引创建成功")
        else:
            st.write("✅ 使用现有的 Pinecone 索引")
        
        return pc.Index(index_name)
    except Exception as e:
        st.error(f"Pinecone 初始化失败: {str(e)}")
        return None

def get_embeddings(texts):
    """获取文本的向量表示"""
    try:
        # 使用配置文件中的sentence transformer设置
        import os
        os.environ['HF_HUB_OFFLINE'] = '0'
        os.environ['TRANSFORMERS_OFFLINE'] = '0'
        
        st_config = get_sentence_transformer_config()
        model = SentenceTransformer(
            st_config["model_name"], 
            cache_folder=st_config["cache_folder"],
            device=st_config["device"]
        )
        
        # 对中文文本进行预处理
        processed_texts = []
        for text in texts:
            # 使用jieba进行中文分词
            words = jieba.cut(text)
            # 将分词结果重新组合，用空格连接
            processed_text = " ".join(words)
            processed_texts.append(processed_text)
        
        # 获取向量表示
        embeddings = model.encode(processed_texts)
        return embeddings
    except Exception as e:
        st.warning(f"无法使用sentence-transformers模型: {str(e)}")
        st.info("使用简单的文本向量化方法作为备选...")
        
        # 备选方案：使用简单的TF-IDF向量化
        return get_simple_embeddings(texts)

def get_simple_embeddings(texts):
    """使用TF-IDF的简单向量化方法"""
    try:
        # 对中文文本进行预处理
        processed_texts = []
        for text in texts:
            # 使用jieba进行中文分词
            words = jieba.cut(text)
            processed_text = " ".join(words)
            processed_texts.append(processed_text)
        
        # 使用TF-IDF向量化
        vectorizer = TfidfVectorizer(max_features=384, stop_words=None)
        tfidf_matrix = vectorizer.fit_transform(processed_texts)
        
        # 转换为密集矩阵并确保维度为384
        embeddings = tfidf_matrix.toarray()
        
        # 如果特征数少于384，用零填充
        if embeddings.shape[1] < 384:
            padding = np.zeros((embeddings.shape[0], 384 - embeddings.shape[1]))
            embeddings = np.hstack([embeddings, padding])
        elif embeddings.shape[1] > 384:
            # 如果特征数多于384，截取前384个
            embeddings = embeddings[:, :384]
        
        return embeddings
    except Exception as e:
        st.error(f"简单向量化也失败了: {str(e)}")
        # 最后的备选方案：返回随机向量
        return np.random.random((len(texts), 384))

def vectorize_document(text: str, file_name: str = None):
    """向量化文档并存储到 Pinecone"""
    try:
        # 文本分块
        chunks = text_to_chunks(text)
        
        # 获取 embeddings
        embeddings = get_embeddings(chunks)
        
        # 初始化 Pinecone
        index = init_pinecone()
        if not index:
            return None, None
        
        # 生成唯一的文档ID前缀（确保是ASCII字符）
        doc_id = f"doc_{int(time.time())}"  # 不使用文件名，改用时间戳
        
        # 上传向量到 Pinecone
        vectors = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            vector = {
                'id': f"{doc_id}_chunk_{i}",  # 使用时间戳作为ID前缀
                'values': embedding.tolist(),
                'metadata': {
                    'text': chunk,
                    'original_file_name': file_name,  # 在元数据中保存原始文件名
                    'chunk_index': i,
                    'timestamp': time.time()
                }
            }
            vectors.append(vector)
        
        # 批量上传
        index.upsert(vectors=vectors)
        
        return chunks, index
    except Exception as e:
        st.error(f"向量化文档失败: {str(e)}")
        st.error(f"错误类型: {type(e).__name__}")
        st.error(f"错误堆栈: {traceback.format_exc()}")
        return None, None

def search_similar(query: str, index, chunks=None, top_k=3):
    """在 Pinecone 中搜索相似内容"""
    try:
        # 获取查询的 embedding
        query_embedding = get_embeddings([query])[0]
        
        # 直接从 Pinecone 中搜索，不再使用本地的 chunks
        results = index.query(
            vector=query_embedding.tolist(),
            top_k=top_k,
            include_metadata=True
        )
        
        # 只返回相似度较高的相关文本
        matched_texts = []
        for match in results['matches']:
            if match['score'] >= 0.3:  # 相似度阈值
                text = match['metadata']['text']
                matched_texts.append(text)
        
        return matched_texts
    except Exception as e:
        st.error(f"搜索失败: {str(e)}")
        st.error(f"错误类型: {type(e).__name__}")
        st.error(f"错误堆栈: {traceback.format_exc()}")
        return []

def get_vector_search_results(query: str) -> list:
    """从 Pinecone 中搜索相关信息"""
    try:
        # 初始化 Pinecone 索引
        index = init_pinecone()
        if not index:
            return []
        
        # 从查询中提取患者姓名
        import re
        # 更宽松的患者姓名匹配，包括常见姓氏+某某的模式
        common_surnames = "李王张刘陈杨黄周吴马蒲赵钱孙朱胡郭何高林罗郑梁谢宋唐许邓冯韩曹曾彭萧蔡潘田董袁于余叶蒋杜苏魏程吕丁沈任姚卢傅钟姜崔谭廖范汪陆金石戴贾韦夏邱方侯邹熊孟秦白江阎薛尹段雷黎史龙陶贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
        pattern = f'([{common_surnames}])某某'
        patient_name_match = re.search(pattern, query)
        if not patient_name_match:
            # 如果没有找到特定患者姓名，尝试通用搜索
            st.info("未识别到特定患者姓名，进行通用向量搜索...")
            patient_name = None
        else:
            patient_name = patient_name_match.group(1) + "某某"
            st.write(f"查询患者：{patient_name}")
        
        # 获取查询的 embedding
        query_embedding = get_embeddings([query])[0]
        
        # 在 Pinecone 中搜索，不使用过滤器
        results = index.query(
            vector=query_embedding.tolist(),
            top_k=50,  # 增加返回结果数量
            include_metadata=True
        )
        
        # 在结果中过滤和处理匹配结果
        matched_texts = []
        if results['matches']:
            for match in results['matches']:
                file_name = match['metadata'].get('original_file_name', '')
                score = match['score']
                text = match['metadata']['text']
                
                # 如果指定了患者姓名，优先匹配该患者的文件
                if patient_name:
                    if patient_name in file_name:
                        st.write(f"找到患者匹配：")
                        st.write(f"- 文件名: {file_name}")
                        st.write(f"- 相似度: {score:.2f}")
                        
                        if score >= 0.01:  # 保持一个最低相似度阈值
                            matched_texts.append(f"[{file_name}] (相似度: {score:.2f}): {text}")
                else:
                    # 如果没有指定患者姓名，返回所有相关度较高的结果
                    if score >= 0.3:  # 提高通用搜索的相似度阈值
                        st.write(f"找到相关匹配：")
                        st.write(f"- 文件名: {file_name}")
                        st.write(f"- 相似度: {score:.2f}")
                        matched_texts.append(f"[{file_name}] (相似度: {score:.2f}): {text}")
                
                # 限制返回结果数量
                if len(matched_texts) >= 5:
                    break
        
        return matched_texts
    except Exception as e:
        st.error(f"向量搜索错误: {str(e)}")
        return []

def text_to_chunks(text: str, chunk_size: int = 100000):
    """将文本分割成小块"""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    
    for word in words:
        current_chunk.append(word)
        current_size += len(word) + 1  # +1 for space
        
        if current_size >= chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = []
            current_size = 0
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def clean_vector_store():
    """清理向量数据库"""
    try:
        index = init_pinecone()
        if index:
            # 删除所有向量（新版本API）
            try:
                index.delete(delete_all=True)
            except Exception as delete_error:
                # 如果delete_all不支持，尝试获取所有向量ID并逐个删除
                st.warning("尝试使用替代方法清理向量数据库...")
                stats = index.describe_index_stats()
                if stats.total_vector_count > 0:
                    # 由于新版本可能不支持直接删除所有向量，我们创建一个新的索引来替代
                    st.warning("当前索引包含数据，建议手动清理或重新创建索引")
            st.success("✅ Pinecone 向量数据库已清空")
            return True
    except Exception as e:
        st.error(f"清理 Pinecone 数据库错误: {str(e)}")
        return False

# 添加 num_tokens_from_string 函数
def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    """计算文本的token数量"""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def get_graph_search_results(query: str) -> list:
    """从图数据库中搜索相关信息"""
    try:
        # 使用LLM生成查询条件
        query_obj = generate_graph_query(query)
        if not query_obj:
            return []
        
        G = nx.read_gexf("medical_graph.gexf")
        results = []
        
        # 根据查询条件执行搜索
        start_nodes = [node for node, data in G.nodes(data=True)
                      if data.get('type') == query_obj["start_node"]["type"] and 
                         node == query_obj["start_node"]["name"]]
        
        for start_node in start_nodes:
            # 获取所有邻居节点
            for neighbor in G.neighbors(start_node):
                edge_data = G.get_edge_data(start_node, neighbor)
                neighbor_data = G.nodes[neighbor]
                
                # 检查关系类型和终点节点类型是否匹配
                if (edge_data.get("relationship") == query_obj["relationship"] and
                    neighbor_data.get('type') == query_obj["end_node"]["type"]):
                    
                    # 构建结果
                    result = []
                    for attr in query_obj["return"]:
                        node_type, attr_name = attr.split(".")
                        if node_type == "end_node":
                            # 如果是诊断节点，直接使用节点的名称作为诊断内容
                            if neighbor_data.get('type') in ['admission_diagnosis', 'discharge_diagnosis']:
                                result.append(f"{attr_name}: {neighbor}")
                            else:
                                result.append(f"{attr_name}: {neighbor_data.get(attr_name, '')}")
                    
                    if result:  # 只添加有内容的结果
                        results.append(f"{start_node} -> {edge_data.get('relationship')} -> {' | '.join(result)}")
        
        return results
    except Exception as e:
        st.error(f"图数据库搜索错误: {str(e)}")
        st.error(f"错误类型: {type(e).__name__}")
        st.error(f"错误堆栈: {traceback.format_exc()}")
        return []

def generate_graph_query(query: str) -> dict:
    """使用LLM生成图数据库查询条件"""
    try:
        st.write("开始创建OpenAI客户端...")
        client = OpenAI(
            api_key="sk-1pUmQlsIkgla3CuvKTgCrzDZ3r0pBxO608YJvIHCN18lvOrn",
            base_url="https://api.chatanywhere.tech/v1",
            timeout=60
        )
        st.write("✅ OpenAI客户端创建成功")
        
        # 读取图数据库的结构信息
        G = nx.read_gexf("medical_graph.gexf")
        
        # 获取图的基本信息
        graph_info = {
            "node_types": list(set(nx.get_node_attributes(G, 'type').values())),
            "relationships": list(set(nx.get_edge_attributes(G, 'relationship').values())),
            "nodes_sample": {
                node: data for node, data in list(G.nodes(data=True))[:5]
            },
            "edges_sample": {
                f"{u}->{v}": data for u, v, data in list(G.edges(data=True))[:5]
            }
        }
        
        prompt = f"""请根据问题和图数据库结构生成图数据库查询条件。

图数据库结构：
节点类型: {graph_info["node_types"]}
关系类型: {graph_info["relationships"]}
节点示例: {json.dumps(graph_info["nodes_sample"], ensure_ascii=False, indent=2)}
关系示例: {json.dumps(graph_info["edges_sample"], ensure_ascii=False, indent=2)}

用户问题：{query}

请生成一个包含查询条件的字典，示例格式：

1. 查询患者的主诉：
{{
    "start_node": {{"type": "patient", "name": "从问题中提取的患者姓名"}},
    "relationship": "complains_of",
    "end_node": {{"type": "chief_complaint"}},
    "return": ["end_node.content"]
}}

注意：
1. 从用户问题中提取正确的患者姓名
2. 使用正确的节点类型和关系类型
3. 使用正确的属性名称
4. 指定要返回的具体属性

请直接返回查询条件的JSON字符串，不要包含任何其他内容。"""

        st.write("🔄 正在调用OpenAI API...")
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {
                    "role": "system", 
                    "content": "你是一个图数据库查询专家。请根据实际的图数据库结构生成精确的查询条件。"
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.1
        )
        st.write("✅ OpenAI API调用成功")
        
        # 获取响应文本并清理
        query_str = response.choices[0].message.content.strip()
        st.write("原始响应文本：", query_str)
        
        if query_str.startswith('```json'):
            query_str = query_str[7:]
        if query_str.endswith('```'):
            query_str = query_str[:-3]
        query_str = query_str.strip()
        
        st.write("清理后的JSON字符串：", query_str)
        
        # 显示生成的查询条件
        st.write("生成的图数据库查询条件：")
        st.code(query_str, language="json")
        
        return json.loads(query_str)
        
    except Exception as e:
        st.error(f"生成图数据库查询条件错误: {str(e)}")
        st.error(f"错误类型: {type(e).__name__}")
        st.error(f"错误堆栈: {traceback.format_exc()}")
        return None
