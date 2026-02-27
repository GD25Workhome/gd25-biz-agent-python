# Langfuse Datasets 接入指南

> 本文档介绍 Langfuse Datasets 的功能、API 使用方法及官方核心文档索引。

## 一、功能概述

### 1.1 什么是 Datasets

**Dataset** 是 Langfuse 中用于测试和评估 LLM 应用的数据集，包含 **输入** 以及可选的 **预期输出**。它支持通过 [UI](https://langfuse.com/docs/evaluation/experiments/experiments-via-ui) 和 [SDK](https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk) 两种方式运行实验（Experiments）。

### 1.2 核心价值

- **从生产 Trace 创建测试用例**：从线上 Trace 挑选问题案例，补充专家标注的预期输出，形成可回归的测试集
- **团队协作管理**：通过 UI、API 或 SDK 共同维护数据集
- **单一数据源**：测试数据集中托管在 Langfuse，便于与评估、实验打通

### 1.3 主要能力

| 能力 | 说明 |
|------|------|
| **Dataset 管理** | 创建、命名、描述、元数据、JSON Schema 校验 |
| **Dataset Items** | 添加 input / expected_output，支持从 Trace/Observation 导入 |
| **版本管理** | 每次 add/update/delete/archive 产生新版本，便于回溯 |
| **批量导入** | 从 Observations 表批量选中的条目添加到 Dataset |
| **Schema 校验** | 为 input / expected_output 定义 JSON Schema，自动校验新增数据 |
| **实验运行** | 基于 Dataset 运行 Experiment，对比不同配置/模型的表现 |

---

## 二、API 与 SDK 接入

### 2.1 Python SDK 接入

#### 2.1.1 初始化客户端

```python
from langfuse import Langfuse

# 通过环境变量 LANGFUSE_PUBLIC_KEY、LANGFUSE_SECRET_KEY、LANGFUSE_HOST 初始化
langfuse = Langfuse()
```

#### 2.1.2 创建 Dataset

```python
langfuse.create_dataset(
    name="qa-evaluation-dataset",
    description="QA 评估数据集",
    metadata={
        "author": "Alice",
        "date": "2025-02-02",
        "type": "benchmark"
    }
)
```

#### 2.1.3 添加 Dataset Item

```python
langfuse.create_dataset_item(
    dataset_name="qa-evaluation-dataset",
    input={"text": "hello world"},           # 任意 Python 对象
    expected_output={"text": "hello world"}, # 可选
    metadata={"model": "llama3"},            # 可选
)
```

#### 2.1.4 从生产 Trace 创建 Item

```python
langfuse.create_dataset_item(
    dataset_name="qa-evaluation-dataset",
    input={"text": "hello world"},
    expected_output={"text": "hello world"},
    source_trace_id="<trace_id>",            # 关联 Trace
    source_observation_id="<observation_id>", # 可选：关联具体 span/event/generation
)
```

#### 2.1.5 获取 Dataset

```python
dataset = langfuse.get_dataset("qa-evaluation-dataset")
# 遍历 items
for item in dataset.items:
    print(item.input, item.expected_output)
```

#### 2.1.6 更新/归档 Item

```python
langfuse.create_dataset_item(
    id="<item_id>",           # 指定 id 实现 upsert
    status="ARCHIVED"         # 归档后不再参与实验
)
```

#### 2.1.7 带 Schema 的 Dataset

```python
langfuse.create_dataset(
    name="qa-conversations",
    input_schema={
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["user", "assistant", "system"]},
                        "content": {"type": "string"}
                    },
                    "required": ["role", "content"]
                }
            }
        },
        "required": ["messages"]
    },
    expected_output_schema={
        "type": "object",
        "properties": {"response": {"type": "string"}},
        "required": ["response"]
    }
)
```

### 2.2 基于 Dataset 运行实验（Experiment Runner）

```python
from langfuse import get_client
from langfuse.openai import OpenAI

langfuse = get_client()

def my_task(*, item, **kwargs):
    question = item.input
    response = OpenAI().chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content

# 从 Langfuse 获取 dataset
dataset = langfuse.get_dataset("my-evaluation-dataset")

# 直接对 dataset 运行实验
result = dataset.run_experiment(
    name="Production Model Test",
    description="月度评估",
    task=my_task
)

print(result.format())
```

### 2.3 低层级 API：手动遍历 Dataset

```python
from langfuse import get_client

dataset = get_client().get_dataset("<dataset_name>")

for item in dataset.items:
    with item.run(
        run_name="<run_name>",
        run_description="My first run",
        run_metadata={"model": "llama3"}
    ) as root_span:
        output = my_llm_application.run(item.input)
        root_span.score_trace(
            name="accuracy",
            value=my_eval_fn(item.input, output, item.expected_output)
        )

get_client().flush()
```

---

## 三、官方核心文档索引

### 3.1 Datasets 文档

| 文档 | 链接 | 说明 |
|------|------|------|
| Datasets 主文档 | https://langfuse.com/docs/datasets | 创建、管理、版本、Schema、生产数据导入等 |
| Datasets 快速开始 | https://langfuse.com/docs/datasets/get-started | 与主文档同源，侧重入门 |

### 3.2 Experiments 文档

| 文档 | 链接 | 说明 |
|------|------|------|
| 评估概览 | https://langfuse.com/docs/evaluation/overview | 评估体系总览 |
| 核心概念 | https://langfuse.com/docs/evaluation/core-concepts | 评估相关概念 |
| Experiments 数据模型 | https://langfuse.com/docs/evaluation/experiments/data-model | Dataset、Run、Item 等模型 |
| Experiments 中的 Datasets | https://langfuse.com/docs/evaluation/experiments/datasets | 在实验中使用 Datasets |
| **Experiments via SDK** | https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk | **SDK 运行实验（推荐）** |
| Experiments via UI | https://langfuse.com/docs/evaluation/experiments/experiments-via-ui | UI 运行实验 |

### 3.3 API / SDK 参考

| 资源 | 链接 | 说明 |
|------|------|------|
| API Reference | https://api.reference.langfuse.com | REST API |
| Python SDK Reference | https://python.reference.langfuse.com | Python 客户端 |
| JS/TS SDK Reference | https://js.reference.langfuse.com | JS/TS 客户端 |

### 3.4 相关能力文档

| 文档 | 链接 | 说明 |
|------|------|------|
| Synthetic Datasets | https://langfuse.com/docs/evaluation/features/synthetic-datasets | 使用 LLM 生成合成数据集 |
| LLM-as-a-Judge | https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge | 基于 LLM 的自动评估 |
| Scores via SDK | https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk | 代码中打分数 |

---

## 四、接入流程小结

1. **初始化 Langfuse 客户端**（环境变量或代码传入 public_key、secret_key、host）
2. **创建 Dataset**：`create_dataset(name=..., description=..., metadata=...)`
3. **添加 Item**：`create_dataset_item(dataset_name=..., input=..., expected_output=...)`  
   - 可从 Trace/Observation 引用：`source_trace_id`、`source_observation_id`
4. **运行实验**：  
   - 推荐：`dataset.run_experiment(name=..., task=my_task)`  
   - 或低层级：遍历 `dataset.items`，用 `item.run()` 关联 Trace 并打分

---

## 五、注意事项

- **Dataset 名称**：项目内唯一；使用 `/` 可形成虚拟文件夹（如 `evaluation/qa-dataset`）
- **URL 编码**：名称中含 `/` 时，在 API 或 JS SDK 中需使用 `encodeURIComponent(name)`
- **版本**：每次对 Items 的增删改 archive 都会产生新版本；默认 API 返回最新版本
- **Schema 校验**：配置 `input_schema` / `expected_output_schema` 后，所有新增 Item 会被校验
