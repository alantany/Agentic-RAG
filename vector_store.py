import pinecone
from sentence_transformers import SentenceTransformer
import streamlit as st
import tiktoken
import traceback
import time
import jieba  # 添加中文分词库
import networkx as nx

# 初始化 Pinecone
def init_pinecone():
    """初始化 Pinecone 客户端"""
    try:
        pinecone.init(
            api_key="e5b7d591-d2c7-411a-9b9b-c52d17934415",
            environment="gcp-starter"
        )
        
        index_name = "medical-records"
        
        # 只在索引不存在时创建新索引
        if index_name not in pinecone.list_indexes():
            st.write("创建新的 Pinecone 索引...")
            dimension = 384  # all-MiniLM-L6-v2 的维度
            pinecone.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine"
            )
            st.write("✅ 新索引创建成功")
        else:
            st.write("✅ 使用现有的 Pinecone 索引")
        
        return pinecone.Index(index_name)
    except Exception as e:
        st.error(f"Pinecone 初始化失败: {str(e)}")
        return None

def get_embeddings(texts):
    """获取文本的向量表示"""
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
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
        patient_name_match = re.search(r'([李|王|张|刘|陈|杨|黄|周|吴|马|蒲]某某)', query)
        if not patient_name_match:
            st.warning("未能从问题中识别出患者姓名")
            return []
        
        patient_name = patient_name_match.group(1)
        st.write(f"查询患者：{patient_name}")
        
        # 获取查询的 embedding
        query_embedding = get_embeddings([query])[0]
        
        # 在 Pinecone 中搜索，不使用过滤器
        results = index.query(
            vector=query_embedding.tolist(),
            top_k=50,  # 增加返回结果数量
            include_metadata=True
        )
        
        # 在结果中手动过滤患者
        matched_texts = []
        if results['matches']:
            for match in results['matches']:
                # 检查文件名是否包含患者姓名
                file_name = match['metadata'].get('original_file_name', '')
                if patient_name in file_name:
                    score = match['score']
                    text = match['metadata']['text']
                    
                    # 显示匹配信息
                    st.write(f"找到匹配：")
                    st.write(f"- 文件名: {file_name}")
                    st.write(f"- 相似度: {score:.2f}")
                    
                    # 只返回相关的文档
                    if score >= 0.01:  # 保持一个最低相似度阈值
                        matched_texts.append(f"[{file_name}] (相似度: {score:.2f}): {text}")
                        break  # 找到第一个匹配就退出
        
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
            # 删除所有向量
            index.delete(delete_all=True)
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
