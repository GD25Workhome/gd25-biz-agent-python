# 豆包 Embedding API 测试

本目录包含豆包 Embedding API 的测试代码。

## 文件说明

### 1. `test_doubao_embedding_01.pyt`
最简单的测试示例，直接调用豆包 Embedding API。

**运行方式：**
```bash
cd cursor_test/rag/03_doubao_rag
python test_doubao_embedding_01.pyt
```

**功能：**
- 测试多模态 Embedding API（支持文本和图片）
- 使用硬编码的 API Key（仅用于测试）

### 2. `test_doubao_embedding_api.py`
完整的测试套件，包含多个测试用例。

**运行方式：**
```bash
cd cursor_test/rag/03_doubao_rag
python test_doubao_embedding_api.py
```

**功能：**
- 单个文本向量化测试
- 多个文本批量向量化测试
- 医疗场景文本向量化测试
- 向量一致性测试
- 从环境变量读取配置（`OPENAI_API_KEY`）

### 3. `test_langChain_embedding_02.py`
LangChain Embeddings 接口集成测试。

**运行方式：**
```bash
cd cursor_test/rag/03_doubao_rag
python test_langChain_embedding_02.py
```

**功能：**
- 实现 `DoubaoEmbeddings` 类，继承 LangChain `Embeddings` 基类
- 测试 `embed_query` 方法
- 测试 `embed_documents` 方法
- 验证 LangChain 兼容性

## 环境变量配置

在 `.env` 文件中设置以下环境变量：

```env
# 豆包 Embedding API Key
OPENAI_API_KEY=your_api_key_here

# 可选：自定义模型ID
DOUBAO_EMBEDDING_MODEL_ID=doubao-embedding-vision-250615
```

## 依赖安装

```bash
pip install volcengine-python-sdk[ark]
pip install langchain
pip install python-dotenv
```

## 使用示例

### 在代码中使用 DoubaoEmbeddings

```python
from test_langChain_embedding_02 import DoubaoEmbeddings

# 创建 Embeddings 实例
embeddings = DoubaoEmbeddings()

# 单个文本嵌入
vector = embeddings.embed_query("天很蓝")

# 批量嵌入
vectors = embeddings.embed_documents(["文本1", "文本2"])
```

## 注意事项

1. 所有文件已配置正确的路径引用，可以从新目录正常运行
2. 确保已安装 `volcengine-python-sdk[ark]` SDK
3. API Key 需要从豆包平台获取并配置
