# Agentic RAG 医疗知识问答系统

## 项目简介
这是一个基于 RAG (Retrieval-Augmented Generation) 技术的医疗知识问答系统，集成了三种不同类型的数据库：
- 向量数据库：用于语义相似性搜索
- 关系数据库：用于结构化数据查询
- 图数据库：用于知识图谱关系查询

## 功能特点
1. 支持 PDF 格式的医疗病历导入
2. 多数据库协同检索
3. 交互式知识图谱可视化
4. 智能问答与上下文理解
5. 详细的检索过程展示

## 安装说明
1. 克隆项目：
```bash
git clone [项目地址]
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 运行应用：
```bash
streamlit run agentic_rag_demo.py
```

## 使用说明
1. 上传医疗病历 PDF 文件
2. 系统会自动解析并存储到三个数据库中
3. 在查询框输入问题
4. 系统会从三个数据库中检索相关信息并生成回答
5. 可以在侧边栏查看各个数据库的具体内容

## 部署说明
本项目已适配 Streamlit Cloud 部署：
1. Fork 本项目到您的 GitHub
2. 在 Streamlit Cloud 中连接您的 GitHub 仓库
3. 选择 agentic_rag_demo.py 作为主文件部署

## 技术架构
- 前端：Streamlit
- 向量化：Transformers (BERT)
- 数据库：SQLite, NetworkX
- 大语言模型：GPT-4
