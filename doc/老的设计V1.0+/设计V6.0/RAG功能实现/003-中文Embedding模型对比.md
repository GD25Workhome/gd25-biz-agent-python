# 中文 Embedding 模型对比

本文档汇总了 Hugging Face 上支持中文的主要 embedding 模型及其关键参数。

## 一、主流中文 Embedding 模型列表

### 1.1 轻量级模型（< 500MB）

| 模型名称 | HuggingFace 路径 | 向量维度 | 模型大小 | 特点 | 推荐场景 |
|---------|-----------------|---------|---------|------|---------|
| **Dmeta-embedding-zh-small** | DMetaSoul/Dmeta-embedding-zh-small | 768 | ~297MB | 蒸馏版本，推理速度快 | 资源受限、需要快速响应的场景 |
| **m3e-base** | moka-ai/m3e-base | 768 | ~390-391MB | 支持中英双语，性能平衡 | 通用场景，目前已下载 |
| **text2vec-base-chinese** | shibing624/text2vec-base-chinese | 768 | ~400-440MB | 基于 CoSENT 方法 | 文本匹配、语义搜索 |

### 1.2 中等规模模型（500MB - 1.5GB）

| 模型名称 | HuggingFace 路径 | 向量维度 | 模型大小 | 特点 | 推荐场景 |
|---------|-----------------|---------|---------|------|---------|
| **m3e-large** | moka-ai/m3e-large | 768 | ~1.3GB | m3e-base 的增强版，精度更高 | 需要更高精度的检索任务 |
| **BAAI/bge-base-zh-v1.5** | BAAI/bge-base-zh-v1.5 | 768 | ~400-500MB | BGE 系列基础版，性能优秀 | 通用检索和 RAG 应用 |
| **text2vec-large-chinese** | shibing624/text2vec-large-chinese | 768 | ~330MB | text2vec 系列大型版本 | 文本分类和检索任务 |
| **longbert-embedding-8k-zh** | OctopusMind/longbert-embedding-8k-zh | 未明确 | ~1.2-1.3GB | 支持最长 8192 token | 长文本处理场景 |

### 1.3 大型模型（> 1.5GB）

| 模型名称 | HuggingFace 路径 | 向量维度 | 模型大小 | 特点 | 推荐场景 |
|---------|-----------------|---------|---------|------|---------|
| **BAAI/bge-large-zh-v1.5** | BAAI/bge-large-zh-v1.5 | 1024 | ~1.2-1.3GB | BGE 系列大型版本，1024 维 | 高精度检索、大模型 RAG |
| **text2vec-bge-large-chinese** | shibing624/text2vec-bge-large-chinese | 1024 | ~1.2GB | 基于 BGE-large，1024 维 | 需要高维度嵌入的场景 |
| **MiniCPM-Embedding-Light** | openbmb/MiniCPM-Embedding-Light | 可变 | ~1.2GB | 支持最长 8192 token，可变维度 | 长文本 + 灵活维度需求 |

### 1.4 超大模型（参数量 > 1B）

| 模型名称 | HuggingFace 路径 | 向量维度 | 模型大小 | 特点 | 推荐场景 |
|---------|-----------------|---------|---------|------|---------|
| **gte-Qwen2-1.5B-instruct** | Alibaba-NLP/gte-Qwen2-1.5B-instruct | 未明确 | ~3-4GB | Qwen2 系列，1.5B 参数 | 高性能嵌入需求 |
| **gte-Qwen2-7B-instruct** | Alibaba-NLP/gte-Qwen2-7B-instruct | 未明确 | ~14-15GB | Qwen2 系列，7B 参数，MTEB 排名第6 | 极高精度需求 |
| **Qwen3-Embedding-0.6B** | Qwen/Qwen3-Embedding-0.6B | 未明确 | ~1.2-1.5GB | Qwen3 系列，MTEB 排名第4 | 平衡性能和资源 |
| **Qwen3-Embedding-8B** | Qwen/Qwen3-Embedding-8B | 未明确 | ~16-18GB | Qwen3 系列，MTEB 排名第2 | 最高精度需求 |

## 二、模型系列详细说明

### 2.1 M3E 系列（MokaAI）

- **m3e-base**: 当前已下载，适合大多数场景
- **m3e-large**: 更大的参数量，更高的精度

**特点**：
- 支持中英双语
- 针对中文场景优化
- 性能与速度平衡

### 2.2 BGE 系列（BAAI - 智源）

BGE（BAAI General Embedding）是智源研究院开发的通用 embedding 模型系列。

- **bge-small-zh-v1.5**: 小型版本，速度快
- **bge-base-zh-v1.5**: 基础版本，768 维，平衡性能
- **bge-large-zh-v1.5**: 大型版本，1024 维，高精度

**特点**：
- 在 C-MTEB 中文评测中表现优秀
- 支持检索、重排序等多种任务
- 开源且维护活跃

### 2.3 Text2Vec 系列

- **text2vec-base-chinese**: 基础版本
- **text2vec-large-chinese**: 大型版本
- **text2vec-bge-large-chinese**: 基于 BGE-large 的包装

**特点**：
- 基于 CoSENT（Cosine Sentence）方法
- 社区支持活跃，有丰富的使用示例
- 适合文本匹配和语义搜索

### 2.4 Qwen 系列（阿里巴巴）

Qwen Embedding 系列是阿里巴巴开发的多语言 embedding 模型。

**特点**：
- 在 MTEB 排行榜上排名靠前
- 支持多语言（包括中文）
- 参数量较大，需要更多资源

### 2.5 其他特色模型

- **Dmeta-embedding-zh-small**: 最小体积，适合边缘设备
- **longbert-embedding-8k-zh**: 专门处理长文本
- **MiniCPM-Embedding-Light**: 支持可变维度和长文本

## 三、选择建议

### 3.1 按场景选择

**通用场景（推荐）**：
- **m3e-base**（已下载）：平衡性能和速度
- **BAAI/bge-base-zh-v1.5**：精度稍高，768 维

**需要高精度**：
- **m3e-large**：768 维，精度提升
- **BAAI/bge-large-zh-v1.5**：1024 维，更高精度

**资源受限**：
- **Dmeta-embedding-zh-small**：最小体积
- **m3e-base**：平衡选择

**长文本处理**：
- **longbert-embedding-8k-zh**：支持 8K token
- **MiniCPM-Embedding-Light**：支持 8K token，可变维度

**极高精度需求**：
- **Qwen3-Embedding 系列**：MTEB 排行榜前列
- **gte-Qwen2-7B-instruct**：7B 参数，性能优异

### 3.2 按向量维度选择

**768 维（常见）**：
- m3e-base / m3e-large
- text2vec-base-chinese / text2vec-large-chinese
- BAAI/bge-base-zh-v1.5
- Dmeta-embedding-zh-small

**1024 维（高精度）**：
- BAAI/bge-large-zh-v1.5
- text2vec-bge-large-chinese

**可变维度**：
- MiniCPM-Embedding-Light

### 3.3 性能对比参考

根据 C-MTEB（中文文本嵌入评测基准）和 MTEB（多语言文本嵌入评测基准）：

**C-MTEB 排行榜（中文）**：
- BGE 系列表现优秀
- m3e 系列在中英双语场景表现良好
- acge_text_embedding 在 C-MTEB 中排名第一（但不在 Hugging Face 上）

**MTEB 排行榜（多语言）**：
- Qwen3-Embedding-8B：排名第 2
- Qwen3-Embedding-0.6B：排名第 4
- gte-Qwen2-7B-instruct：排名第 6

## 四、使用建议

### 4.1 当前环境

当前已下载的模型：
- **m3e-base**（~390MB，768 维）

### 4.2 推荐备选方案

如果需要更高精度，可以考虑：

1. **BAAI/bge-base-zh-v1.5**（~500MB，768 维）
   - 在 C-MTEB 上表现优秀
   - 维度与 m3e-base 相同，易于迁移
   - 性能和精度平衡

2. **m3e-large**（~1.3GB，768 维）
   - 与 m3e-base 同系列，迁移成本低
   - 精度提升明显

3. **BAAI/bge-large-zh-v1.5**（~1.2GB，1024 维）
   - 如果需要更高维度向量
   - 精度最高

### 4.3 下载和测试

如果需要下载其他模型进行测试，可以使用：

```python
from sentence_transformers import SentenceTransformer

# 下载并测试模型
model = SentenceTransformer('BAAI/bge-base-zh-v1.5')
# 或
model = SentenceTransformer('moka-ai/m3e-large')

# 测试向量维度
test_embedding = model.encode('测试文本')
print(f'向量维度: {len(test_embedding)}')
```

## 五、参考资料

- [Hugging Face Models](https://huggingface.co/models)
- [C-MTEB 中文文本嵌入评测基准](https://github.com/FlagOpen/C-MTEB)
- [MTEB 多语言文本嵌入评测基准](https://github.com/embeddings-benchmark/mteb)
- [FlagEmbedding GitHub](https://github.com/FlagOpen/FlagEmbedding)
- [Text2Vec GitHub](https://github.com/shibing624/text2vec)

## 六、注意事项

1. **模型大小**：下载后的模型文件大小可能因格式（.safetensors vs .bin）和压缩而有所不同
2. **向量维度**：选择模型时需考虑向量数据库的维度支持
3. **性能测试**：建议在真实数据上测试模型性能，选择最适合的模型
4. **资源消耗**：大型模型需要更多内存和计算资源
5. **版本更新**：模型版本可能会更新，建议查看 Hugging Face 页面获取最新信息

