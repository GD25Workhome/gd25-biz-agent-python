# Langfuse 评估功能详解：Scores、LLM-as-a-Judge、Human Annotation、Datasets

## 文档说明

本文档详细解释 Langfuse Evaluation 菜单下的四个核心功能：Scores、LLM-as-a-Judge、Human Annotation、Datasets，以及它们在评分功能中的作用和协作方式。

**文档版本**：V1.0  
**创建时间**：2026-01-16

---

## 目录

1. [四个功能概览](#一四个功能概览)
2. [Scores（评分）详解](#二scores评分详解)
3. [LLM-as-a-Judge（LLM 作为评判者）详解](#三llm-as-a-judge-llm-作为评判者详解)
4. [Human Annotation（人工标注）详解](#四human-annotation人工标注详解)
5. [Datasets（数据集）详解](#五datasets数据集详解)
6. [四个功能的协作流程](#六四个功能的协作流程)
7. [实际应用场景](#七实际应用场景)

---

## 一、四个功能概览

### 1.1 功能对比表

| 功能 | 主要作用 | 数据来源 | 在评分中的角色 | 适用场景 |
|------|---------|---------|---------------|---------|
| **Scores** | 定义评分维度，查看评估分布、趋势，统计评分结果 | 自动评分（LLM judge）、人工标注、自定义评分 | **评分结果汇总中心**，所有评估结果的展示和分析 | 查看评分趋势、对比不同版本、分析评分分布 |
| **LLM-as-a-Judge** | 使用另一个 LLM 自动为模型输出打分 | Judge LLM 根据标准自动评分 | **自动化评估工具**，提供大规模、快速的评分 | 批量评估、持续监控、快速迭代 |
| **Human Annotation** | 人工对 Trace 或输出进行打分或分类 | 专家或标注人员通过 UI 标注 | **高质量基准标签**，作为自动评估的校准标准 | 建立 ground truth、校准自动评估、关键案例标注 |
| **Datasets** | 定义标准测试用例（input + expected_output） | 生产数据、合成数据、基准数据 | **对比基准库**，提供标准测试用例 | 离线评估、A/B 测试、版本对比 |

### 1.2 核心关系

```
┌─────────────────────────────────────────────────────────┐
│                    Datasets（数据集）                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │  • 定义标准测试用例                                │  │
│  │  • 包含 input + expected_output                   │  │
│  │  • 作为评估基准                                    │  │
│  └───────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│             评估执行（两种方式）                          │
│  ┌──────────────────────┐  ┌──────────────────────┐   │
│  │ LLM-as-a-Judge       │  │ Human Annotation     │   │
│  │ （自动评估）          │  │ （人工标注）          │   │
│  │                      │  │                      │   │
│  │ • 使用 Judge LLM     │  │ • 专家标注           │   │
│  │ • 批量评估           │  │ • 高质量基准         │   │
│  │ • 快速迭代           │  │ • 校准自动评估        │   │
│  └──────────────────────┘  └──────────────────────┘   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    Scores（评分汇总）                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │  • 评分结果展示                                     │  │
│  │  • 趋势分析                                         │  │
│  │  • 分布统计                                         │  │
│  │  • 版本对比                                         │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 二、Scores（评分）详解

### 2.1 功能定位

**Scores** 是 Langfuse 评估体系中的**评分结果汇总中心**，用于：

1. **定义评分维度**：通过 ScoreConfig 定义评分指标（如相关性、准确性等）
2. **查看评分结果**：展示所有评估结果（来自 LLM-as-a-Judge、Human Annotation、自定义评分）
3. **分析评分数据**：提供趋势分析、分布统计、版本对比等功能

### 2.2 核心功能

#### 2.2.1 ScoreConfig（评分配置）

定义评分维度的标准：

```python
# 创建 ScoreConfig
score_config = {
    "name": "similarity_score",          # 评分名称
    "data_type": "NUMERIC",              # 数据类型：NUMERIC/CATEGORICAL/BOOLEAN
    "min_value": 0.0,                    # 最小值（NUMERIC 类型）
    "max_value": 1.0,                    # 最大值（NUMERIC 类型）
    "description": "与参考案例的相似度评分"
}
```

#### 2.2.2 评分来源

Scores 可以接收来自多个来源的评分：

1. **LLM-as-a-Judge**：自动评估的评分
2. **Human Annotation**：人工标注的评分
3. **Custom Scores**：通过 SDK/API 自定义的评分

#### 2.2.3 评分分析功能

- **趋势分析**：查看评分随时间的变化趋势
- **分布统计**：查看评分的分布情况（直方图）
- **版本对比**：对比不同版本的评分
- **相关性分析**：分析不同评分维度之间的相关性

### 2.3 在评分中的作用

1. **统一评分标准**：通过 ScoreConfig 确保所有评分遵循统一标准
2. **汇总评估结果**：收集来自不同来源的评分，统一展示
3. **数据分析**：提供强大的分析工具，帮助识别问题和优化方向

### 2.4 使用示例

```python
from langfuse import Langfuse

langfuse = Langfuse()

# 记录评分（可以来自任何来源）
langfuse.score(
    name="similarity_score",
    value=0.85,
    trace_id="trace_xxx",
    comment="与参考案例的相似度评分"
)

# 在 Scores 菜单中查看：
# - 所有 similarity_score 的分布
# - 不同版本的 similarity_score 对比
# - similarity_score 随时间的变化趋势
```

---

## 三、LLM-as-a-Judge（LLM 作为评判者）详解

### 3.1 功能定位

**LLM-as-a-Judge** 是 Langfuse 提供的**自动化评估工具**，使用另一个 LLM（Judge LLM）来自动为模型输出打分。

### 3.2 核心功能

#### 3.2.1 Managed Evaluator（托管评估器）

Langfuse 提供预定义的评估器，可以直接使用：

- **相关性评估**：评估回复是否与问题相关
- **准确性评估**：评估回复内容是否准确
- **完整性评估**：评估回复是否完整
- **风格一致性评估**：评估回复风格是否一致

#### 3.2.2 自定义 Evaluator

可以创建自定义的评估器，定义自己的评估标准：

```python
# 创建自定义评估器
evaluator = {
    "name": "similarity_evaluator",
    "prompt_template": """
    你是一个评估专家，负责评估两个回复的相似度。
    
    评估标准：
    1. 语义相似度：两个回复在语义上是否相似（0-1分）
    2. 内容完整性：测试回复是否包含了参考回复中的关键信息（0-1分）
    3. 风格一致性：测试回复的风格是否与参考回复一致（0-1分）
    
    参考回复：{reference_response}
    测试回复：{test_response}
    
    请返回JSON格式的评估结果。
    """,
    "model": "gpt-4",  # 使用的 Judge LLM
    "output_schema": {
        "semantic_similarity": "float",
        "content_completeness": "float",
        "style_consistency": "float"
    }
}
```

#### 3.2.3 评估执行

可以针对以下目标执行评估：

- **Production Traces**：对生产环境的 Trace 进行评估
- **Dataset Runs**：对数据集运行结果进行评估
- **Experiment Runs**：对实验版本进行评估

### 3.3 工作原理

1. **输入准备**：收集需要评估的 Trace 或 Dataset Run
2. **评估执行**：使用 Judge LLM 根据评估标准打分
3. **结果记录**：将评分结果记录到 Scores 中
4. **结果分析**：在 Scores 菜单中查看和分析结果

### 3.4 在评分中的作用

1. **自动化评估**：提供大规模、快速的自动化评估能力
2. **持续监控**：可以对生产环境的 Trace 进行持续评估
3. **快速迭代**：支持快速评估多个版本，加速迭代

### 3.5 使用示例

```python
# 在 Langfuse UI 中配置 LLM-as-a-Judge
# 1. 创建 Evaluator
# 2. 选择评估目标（Dataset、Trace 等）
# 3. 执行评估
# 4. 在 Scores 菜单中查看结果

# 或者通过 API 执行评估
from langfuse import Langfuse

langfuse = Langfuse()

# 创建评估任务
evaluation_task = langfuse.create_evaluation(
    name="similarity_evaluation",
    dataset_id="dataset_xxx",
    evaluator_config={
        "type": "llm_judge",
        "model": "gpt-4",
        "prompt_template": "..."
    }
)

# 执行评估
evaluation_task.run()
```

### 3.6 优缺点

**优点**：
- 自动化，无需人工干预
- 可以批量评估大量样本
- 成本相对较低
- 评估速度快

**缺点**：
- 评估结果可能不够准确
- 需要设计好的 Prompt
- 需要额外的 LLM 调用成本
- 可能存在评估偏差

---

## 四、Human Annotation（人工标注）详解

### 4.1 功能定位

**Human Annotation** 是 Langfuse 提供的**人工标注模块**，由专家或标注人员通过 UI 对 Trace 或输出进行打分或分类。

### 4.2 核心功能

#### 4.2.1 标注界面

提供直观的标注界面，支持：

- **评分标注**：按照 ScoreConfig 对 Trace 或输出进行评分
- **分类标注**：对输出进行分类（如 "good"、"neutral"、"bad"）
- **一致性检查**：检查输出是否与 expected_output 一致
- **评论添加**：添加标注说明和评论

#### 4.2.2 Annotation Queue（标注队列）

创建标注队列来组织和管理标注任务：

```python
# 创建标注队列
annotation_queue = {
    "name": "similarity_annotation_queue",
    "description": "相似度标注队列",
    "score_configs": [
        "similarity_score",
        "style_consistency_score"
    ],
    "filters": {
        "trace_ids": ["trace_001", "trace_002"],
        "tags": ["test_case"]
    }
}
```

#### 4.2.3 标注工作流

1. **任务分配**：将标注任务分配给标注人员
2. **标注执行**：标注人员在 UI 中进行标注
3. **质量检查**：对标注结果进行质量检查
4. **结果汇总**：标注结果自动记录到 Scores 中

### 4.3 在评分中的作用

1. **建立 Ground Truth**：提供高质量的基准标签
2. **校准自动评估**：用于校准 LLM-as-a-Judge 的评估结果
3. **关键案例标注**：对重要的案例进行人工标注

### 4.4 使用场景

1. **建立评估基线**：对初始数据集进行人工标注，建立评估基线
2. **校准自动评估**：定期进行人工标注，校准自动评估的准确性
3. **关键案例评估**：对重要的生产案例进行人工评估
4. **质量检查**：对自动评估结果进行质量检查

### 4.5 使用示例

```python
# 在 Langfuse UI 中：
# 1. 创建 Annotation Queue
# 2. 添加需要标注的 Trace
# 3. 分配标注任务
# 4. 标注人员在 UI 中进行标注
# 5. 标注结果自动记录到 Scores

# 或者通过 API 创建标注任务
from langfuse import Langfuse

langfuse = Langfuse()

# 创建标注队列
queue = langfuse.create_annotation_queue(
    name="similarity_queue",
    score_configs=["similarity_score"]
)

# 添加标注任务
queue.add_items(
    trace_ids=["trace_001", "trace_002"]
)
```

### 4.6 优缺点

**优点**：
- 评估结果准确
- 可以处理复杂场景
- 提供高质量的基准标签

**缺点**：
- 成本高、耗时长
- 难以大规模应用
- 可能存在标注者之间的差异

---

## 五、Datasets（数据集）详解

### 5.1 功能定位

**Datasets** 是 Langfuse 提供的**标准测试用例库**，用于定义和管理评估数据集。

### 5.2 核心功能

#### 5.2.1 数据集结构

数据集包含：

- **Input**：模型要处理的内容（用户问题）
- **Expected Output**：期望的回复（可选，用于对比评估）
- **Metadata**：元数据（如标签、分类等）

```python
# 数据集项结构
dataset_item = {
    "input": {
        "user_query": "我想记录血压，收缩压120，舒张压80"
    },
    "expected_output": {
        "response": "好的，我已经为您记录了血压：收缩压 120 mmHg，舒张压 80 mmHg。您的血压值在正常范围内。"
    },
    "metadata": {
        "agent_name": "blood_pressure_agent",
        "intent": "record_blood_pressure",
        "key_points": ["血压值", "正常范围"]
    }
}
```

#### 5.2.2 数据集管理

- **版本控制**：支持数据集的版本管理
- **Schema 验证**：验证数据集的结构和格式
- **批量导入**：支持批量导入数据集
- **数据质量保障**：提供数据质量检查机制

#### 5.2.3 Dataset Run（数据集运行）

执行数据集评估：

```python
# 创建 Dataset Run
dataset_run = {
    "dataset_id": "dataset_xxx",
    "model_version": "v1.0",
    "config": {
        "temperature": 0.7,
        "max_tokens": 500
    }
}

# 执行评估
results = dataset_run.execute()

# 查看结果
# - 每个测试用例的评分
# - 平均评分
# - 评分分布
```

### 5.3 在评分中的作用

1. **提供评估基准**：定义标准测试用例，作为评估基准
2. **版本对比**：使用相同的数据集对比不同版本
3. **离线评估**：在发布前进行离线评估

### 5.4 使用场景

1. **建立测试集**：从生产环境收集高质量案例，建立测试集
2. **版本对比**：使用相同的数据集对比不同版本的表现
3. **A/B 测试**：使用数据集进行 A/B 测试
4. **持续评估**：定期使用数据集评估模型性能

### 5.5 使用示例

```python
from langfuse import Langfuse

langfuse = Langfuse()

# 创建数据集
dataset = langfuse.create_dataset(name="reference_cases")

# 添加数据集项
dataset.create_item(
    input={"user_query": "我想记录血压，收缩压120，舒张压80"},
    expected_output={
        "response": "好的，我已经为您记录了血压：收缩压 120 mmHg，舒张压 80 mmHg。您的血压值在正常范围内。"
    },
    metadata={
        "agent_name": "blood_pressure_agent",
        "intent": "record_blood_pressure"
    }
)

# 执行数据集运行
dataset_run = dataset.create_run(
    name="v1.0_evaluation",
    metadata={"model_version": "v1.0"}
)

# 在 Langfuse UI 中查看结果
# - 每个测试用例的评分
# - 平均评分
# - 评分分布
```

---

## 六、四个功能的协作流程

### 6.1 完整评估流程

以下是一个完整的评估流程，展示四个功能如何协作：

```
步骤1：建立数据集（Datasets）
    ↓
    从生产环境收集高质量案例
    创建 Dataset，包含 input + expected_output
    ↓
步骤2：定义评分标准（Scores）
    ↓
    创建 ScoreConfig，定义评分维度
    如：similarity_score, style_consistency_score
    ↓
步骤3：建立评估基线（Human Annotation）
    ↓
    对数据集进行人工标注
    建立 ground truth 基准
    ↓
步骤4：配置自动评估（LLM-as-a-Judge）
    ↓
    创建 Evaluator
    使用人工标注的结果校准评估器
    ↓
步骤5：执行评估
    ↓
    使用 LLM-as-a-Judge 对数据集进行评估
    或对生产环境的 Trace 进行评估
    ↓
步骤6：分析结果（Scores）
    ↓
    在 Scores 菜单中查看：
    - 评分分布
    - 趋势分析
    - 版本对比
    - 人工标注 vs 自动评估的一致性
    ↓
步骤7：迭代优化
    ↓
    根据分析结果优化模型或 Prompt
    重新执行评估
```

### 6.2 针对"与线上版本相近"的场景

如果要制作一个与线上版本尽可能相近的 AI 复制品，推荐以下流程：

#### 步骤1：收集线上案例到 Datasets

```python
# 从生产环境收集高质量案例
reference_cases = [
    {
        "input": {"user_query": "我想记录血压，收缩压120，舒张压80"},
        "expected_output": {
            "response": "好的，我已经为您记录了血压：收缩压 120 mmHg，舒张压 80 mmHg。您的血压值在正常范围内。"
        },
        "metadata": {
            "agent_name": "blood_pressure_agent",
            "source": "production"
        }
    }
    # ... 更多案例
]

# 创建 Dataset
dataset = langfuse.create_dataset(name="production_reference_cases")
for case in reference_cases:
    dataset.create_item(**case)
```

#### 步骤2：定义评分维度（Scores）

```python
# 创建 ScoreConfig
score_configs = [
    {
        "name": "similarity_score",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
        "description": "与参考案例的相似度评分"
    },
    {
        "name": "style_consistency_score",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
        "description": "风格一致性评分"
    }
]
```

#### 步骤3：人工标注关键案例（Human Annotation）

```python
# 对部分关键案例进行人工标注，建立 ground truth
# 在 Langfuse UI 中创建 Annotation Queue
# 标注人员对案例进行评分
```

#### 步骤4：配置 LLM-as-a-Judge

```python
# 创建 Evaluator，使用参考案例作为标准
evaluator = {
    "name": "similarity_evaluator",
    "prompt_template": """
    评估测试回复与参考回复的相似度。
    
    参考回复（线上版本）：{reference_response}
    测试回复（新版本）：{test_response}
    
    评估维度：
    1. 语义相似度（0-1分）
    2. 风格一致性（0-1分）
    3. 关键信息覆盖度（0-1分）
    
    请返回JSON格式的评估结果。
    """,
    "model": "gpt-4"
}
```

#### 步骤5：执行评估

```python
# 使用新版本模型在数据集上运行
dataset_run = dataset.create_run(
    name="new_version_evaluation",
    metadata={"model_version": "v2.0"}
)

# 使用 LLM-as-a-Judge 进行评估
evaluation_task = langfuse.create_evaluation(
    name="similarity_evaluation",
    dataset_run_id=dataset_run.id,
    evaluator_config=evaluator
)

evaluation_task.run()
```

#### 步骤6：分析结果（Scores）

```python
# 在 Scores 菜单中查看：
# - 新版本与线上版本的相似度评分
# - 不同维度的评分分布
# - 人工标注 vs 自动评估的一致性
# - 评分趋势和变化
```

---

## 七、实际应用场景

### 7.1 场景1：制作 AI 复制品

**目标**：制作一个与线上版本尽可能相近的 AI 复制品

**流程**：
1. **Datasets**：收集线上高质量案例，建立参考数据集
2. **Scores**：定义相似度、风格一致性等评分维度
3. **Human Annotation**：对关键案例进行人工标注，建立基准
4. **LLM-as-a-Judge**：配置评估器，使用参考案例作为标准
5. **执行评估**：使用新版本在数据集上运行，自动评估
6. **Scores 分析**：查看评分结果，识别需要改进的地方
7. **迭代优化**：根据评分结果优化，重新评估

### 7.2 场景2：版本对比评估

**目标**：对比不同版本的表现

**流程**：
1. **Datasets**：使用标准测试数据集
2. **Scores**：定义评估维度
3. **执行评估**：对不同版本执行评估
4. **Scores 分析**：对比不同版本的评分

### 7.3 场景3：持续监控

**目标**：持续监控生产环境的模型表现

**流程**：
1. **LLM-as-a-Judge**：配置自动评估器
2. **执行评估**：对生产环境的 Trace 进行评估
3. **Scores 分析**：查看评分趋势，识别问题
4. **Human Annotation**：对异常案例进行人工标注

---

## 八、总结

### 8.1 四个功能的核心作用

| 功能 | 核心作用 | 关键价值 |
|------|---------|---------|
| **Scores** | 评分结果汇总中心 | 统一评分标准，提供强大的分析工具 |
| **LLM-as-a-Judge** | 自动化评估工具 | 大规模、快速的自动化评估 |
| **Human Annotation** | 高质量基准标签 | 建立 ground truth，校准自动评估 |
| **Datasets** | 标准测试用例库 | 提供评估基准，支持版本对比 |

### 8.2 协作关系

- **Datasets** 提供评估基准
- **Scores** 定义评分标准
- **Human Annotation** 建立高质量基准
- **LLM-as-a-Judge** 提供自动化评估
- **Scores** 汇总所有结果，提供分析

### 8.3 最佳实践

1. **建立数据集**：从生产环境收集高质量案例，建立标准测试集
2. **定义评分标准**：使用 ScoreConfig 定义清晰的评分标准
3. **人工标注基准**：对关键案例进行人工标注，建立 ground truth
4. **配置自动评估**：使用 LLM-as-a-Judge 进行大规模评估
5. **持续分析**：在 Scores 菜单中持续分析评分结果
6. **迭代优化**：基于评分结果持续优化

---

## 参考资料

- **Langfuse Evaluation 文档**：https://langfuse.com/docs/evaluation
- **Langfuse Scores 文档**：https://langfuse.com/docs/scores
- **Langfuse Datasets 文档**：https://langfuse.com/docs/datasets
- **Langfuse LLM-as-a-Judge 文档**：https://langfuse.com/docs/scores/model-based-evals
- **项目中的评分功能**：`cursor_docs/011603-Langfuse评分功能使用指南.md`
- **评分规则制定**：`cursor_docs/011604-Langfuse评分规则制定与参考案例评估方案.md`

---

*最后更新：2026-01-16*
