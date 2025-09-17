# -*- coding: utf-8 -*-
"""
Agentic RAG 系统配置文件
统一管理所有API密钥和模型配置
"""

# OpenAI API 配置 (使用OpenRouter)
OPENAI_CONFIG = {
    "api_key": "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",
    "base_url": "https://openrouter.ai/api/v1",  # OpenRouter API端点
    "model": "deepseek/deepseek-chat",  # OpenRouter上的DeepSeek模型
    "timeout": 60,
    "temperature": 0.1
}

# 备用API配置（如果主API失败时使用）
BACKUP_OPENAI_CONFIG = {
    "api_key": "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",
    "base_url": "https://api.chatanywhere.tech/v1",
    "model": "gpt-4o-mini-2024-07-18",
    "timeout": 60,
    "temperature": 0.1
}

# Pinecone 向量数据库配置
PINECONE_CONFIG = {
    "api_key": "e5b7d591-d2c7-411a-9b9b-c52d17934415",
    "environment": "gcp-starter",
    "index_name": "medical-records",
    "dimension": 384,  # all-MiniLM-L6-v2 的维度
    "metric": "cosine"
}

# MongoDB 配置
MONGODB_CONFIG = {
    "connection_string": "mongodb+srv://alantany:Mikeno01@airss.ykc1h.mongodb.net/ai-news?retryWrites=true&w=majority&appName=MedicalRAG",
    "database_name": "medical_records",
    "collection_name": "patients",
    "tls_allow_invalid_certificates": True
}

# Sentence Transformers 模型配置
SENTENCE_TRANSFORMER_CONFIG = {
    "model_name": "sentence-transformers/all-MiniLM-L6-v2",
    "cache_folder": "./models",
    "device": "cpu"  # 可以改为 "cuda" 如果有GPU
}

# 系统配置
SYSTEM_CONFIG = {
    "max_retries": 3,
    "chunk_size": 100000,
    "similarity_threshold": 0.3,
    "max_results": 5,
    "vector_top_k": 50
}

# 环境变量配置
ENV_CONFIG = {
    "HF_HUB_OFFLINE": "0",
    "TRANSFORMERS_OFFLINE": "0",
    "TOKENIZERS_PARALLELISM": "false"
}

# 获取OpenAI客户端的便捷函数
def get_openai_client(use_backup=False):
    """获取配置好的OpenAI客户端"""
    from openai import OpenAI
    import os
    
    # 设置环境变量
    for key, value in ENV_CONFIG.items():
        os.environ[key] = value
    
    config = BACKUP_OPENAI_CONFIG if use_backup else OPENAI_CONFIG
    
    return OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=config["timeout"]
    ), config["model"], config["temperature"]

# 获取Pinecone配置的便捷函数
def get_pinecone_config():
    """获取Pinecone配置"""
    return PINECONE_CONFIG

# 获取MongoDB配置的便捷函数
def get_mongodb_config():
    """获取MongoDB配置"""
    return MONGODB_CONFIG

# 获取Sentence Transformer配置的便捷函数
def get_sentence_transformer_config():
    """获取Sentence Transformer配置"""
    return SENTENCE_TRANSFORMER_CONFIG

# 获取系统配置的便捷函数
def get_system_config():
    """获取系统配置"""
    return SYSTEM_CONFIG
