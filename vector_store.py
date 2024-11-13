import streamlit as st
from transformers import AutoTokenizer, AutoModel
import torch
import tiktoken

# 全局变量，确保只加载一次
if 'tokenizer' not in st.session_state:
    st.session_state.tokenizer = AutoTokenizer.from_pretrained('bert-base-chinese')
if 'model' not in st.session_state:
    st.session_state.model = AutoModel.from_pretrained('bert-base-chinese')

def num_tokens_from_string(string: str) -> int:
    """计算文本的token数量"""
    encoding = tiktoken.encoding_for_model("gpt-4o-mini")
    return len(encoding.encode(string))

def get_embeddings(text: str):
    """获取文本的向量表示"""
    inputs = st.session_state.tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    with torch.no_grad():
        outputs = st.session_state.model(**inputs)
    # 直接返回tensor而不是numpy数组
    return outputs.last_hidden_state.mean(dim=1).squeeze()

def vectorize_document(text: str, max_tokens: int = 4096):
    """处理并向量化文档"""
    # 分块
    chunks = []
    current_chunk = ""
    for sentence in text.split('.'):
        if num_tokens_from_string(current_chunk + sentence) > max_tokens:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
        else:
            current_chunk += sentence + '.'
    if current_chunk:
        chunks.append(current_chunk)
    
    # 向量化
    vectors = [get_embeddings(chunk) for chunk in chunks]
    vectors = torch.stack(vectors)
    
    return chunks, vectors

def search_similar(query: str, vectors, chunks: list, k: int = 3):
    """搜索相似文档片段"""
    try:
        query_vector = get_embeddings(query)
        
        # 计算余弦相似度
        similarities = torch.nn.functional.cosine_similarity(query_vector.unsqueeze(0), vectors)
        
        # 获取最相似的k个文档
        top_k = torch.topk(similarities, min(k, len(chunks)))
        
        results = []
        for idx in top_k.indices:
            results.append(chunks[int(idx)])
        return results
    except Exception as e:
        st.error(f"搜索错误: {str(e)}")
        return []
