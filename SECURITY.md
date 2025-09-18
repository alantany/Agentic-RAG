# 🔒 安全配置指南

## ⚠️ 重要安全提醒

**此项目已经修复了API密钥泄露问题！** 所有敏感信息现在都存储在 `.env` 文件中，该文件不会被提交到版本控制系统。

## 🚨 如果您发现API密钥泄露

如果您的API密钥已经被提交到GitHub，请立即：

1. **撤销现有密钥**：
   - OpenRouter: 登录 https://openrouter.ai 撤销旧密钥
   - Pinecone: 登录 https://pinecone.io 撤销旧密钥
   - MongoDB: 登录 MongoDB Atlas 更改密码
   - Neo4j: 登录 Neo4j Aura 更改密码

2. **生成新的API密钥**
3. **更新 `.env` 文件**
4. **确认 `.env` 在 `.gitignore` 中**

## 📋 环境配置步骤

### 1. 复制环境变量模板

```bash
cp .env.template .env
```

### 2. 编辑 `.env` 文件

```bash
# 使用您喜欢的编辑器
nano .env
# 或
vim .env
# 或
code .env
```

### 3. 填入实际的API密钥

```bash
# OpenAI/OpenRouter API配置
OPENAI_API_KEY=sk-or-v1-your_actual_key_here
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=deepseek/deepseek-chat-v3.1:free

# Pinecone配置 (主分支使用)
PINECONE_API_KEY=your_actual_pinecone_key
PINECONE_ENVIRONMENT=gcp-starter
PINECONE_INDEX_NAME=medical-records

# MongoDB配置 (主分支使用)  
MONGODB_CONNECTION_STRING=mongodb+srv://user:pass@cluster.mongodb.net/db

# Neo4j配置 (主分支使用)
NEO4J_URI=neo4j+s://your_instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_actual_password

# Oracle 23ai配置 (Oracle分支使用)
ORACLE_USERNAME=vector
ORACLE_PASSWORD=vector
ORACLE_DSN=localhost:1521/FREEpdb1
```

## 🛡️ 安全最佳实践

### ✅ 应该做的

- ✅ 使用 `.env` 文件存储敏感信息
- ✅ 确保 `.env` 在 `.gitignore` 中
- ✅ 定期轮换API密钥
- ✅ 使用最小权限原则
- ✅ 监控API使用情况
- ✅ 在生产环境中使用环境变量或密钥管理服务

### ❌ 不应该做的

- ❌ 将API密钥硬编码在源代码中
- ❌ 将 `.env` 文件提交到版本控制
- ❌ 在公共场所分享API密钥
- ❌ 使用弱密码或默认密码
- ❌ 忽略API使用限制和配额

## 🔍 验证安全配置

### 检查 `.env` 文件是否被忽略

```bash
git status
# .env 文件不应该出现在待提交列表中
```

### 检查是否有敏感信息泄露

```bash
# 检查Git历史中是否有API密钥
git log --all --full-history -- "*.py" | grep -i "api_key\|password\|secret"
```

### 验证环境变量加载

```python
from dotenv import load_dotenv
import os

load_dotenv()
print("OPENAI_API_KEY loaded:", bool(os.getenv("OPENAI_API_KEY")))
print("API key starts with:", os.getenv("OPENAI_API_KEY", "")[:10] + "...")
```

## 🚀 部署安全

### 本地开发

- 使用 `.env` 文件
- 确保 `.env` 在 `.gitignore` 中

### 生产部署

- 使用系统环境变量
- 使用密钥管理服务 (AWS Secrets Manager, Azure Key Vault, etc.)
- 使用容器secrets (Docker secrets, Kubernetes secrets)

### Docker部署示例

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# 不要COPY .env文件到容器中！
# 使用环境变量或secrets

CMD ["streamlit", "run", "agentic_rag_demo.py"]
```

```bash
# 使用环境变量运行容器
docker run -e OPENAI_API_KEY=your_key -e PINECONE_API_KEY=your_key your_app
```

## 📞 安全问题报告

如果您发现安全问题，请：

1. 不要在公共issue中报告
2. 直接联系项目维护者
3. 提供详细的问题描述
4. 等待确认后再公开

## 🔄 定期安全检查

- 每月检查API密钥使用情况
- 每季度轮换API密钥
- 定期审查访问权限
- 监控异常API调用

---

**记住：安全是一个持续的过程，不是一次性的任务！** 🛡️
