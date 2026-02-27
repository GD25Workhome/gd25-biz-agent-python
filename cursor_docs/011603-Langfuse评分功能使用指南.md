# Langfuse 评分功能使用指南

## 文档说明

本文档详细介绍 Langfuse 评分（Scores）功能的原理、使用方法和在项目中的集成方案，帮助团队将评分作为后续调优的依据。

**文档版本**：V1.0  
**创建时间**：2025-01-16

---

## 目录

1. [Langfuse 评分核心概念](#一langfuse-评分核心概念)
2. [评分数据模型](#二评分数据模型)
3. [评分来源与评估方法](#三评分来源与评估方法)
4. [评分功能使用方法](#四评分功能使用方法)
5. [项目集成方案](#五项目集成方案)
6. [评分数据分析与调优](#六评分数据分析与调优)
7. [最佳实践](#七最佳实践)

---

## 一、Langfuse 评分核心概念

### 1.1 什么是 Score（评分）

**Score** 是 Langfuse 中用于评估 LLM 应用质量的通用数据对象，可以关联到以下实体：

- **Trace**：一次完整的用户交互或业务流程
- **Observation**：Trace 中的某个操作（Span 或 Generation）
- **Session**：多个互动组成的会话
- **DatasetRun**：一组测试数据整体运行的结果

### 1.2 评分的作用

评分功能主要用于：

1. **质量评估**：评估 LLM 输出质量（相关性、准确性、完整性等）
2. **用户反馈**：记录用户对回复的满意度
3. **效果监控**：监控不同智能体、不同版本的平均评分
4. **持续优化**：基于评分数据识别需要优化的环节

### 1.3 评分类型

Langfuse 支持三种评分类型：

| 类型 | 说明 | 示例 |
|------|------|------|
| **NUMERIC（数值型）** | 数值评分，通常为 0-1 或 1-5 | 0.85, 4.5 |
| **CATEGORICAL（分类型）** | 分类评分，从预定义类别中选择 | "good", "neutral", "bad" |
| **BOOLEAN（布尔型）** | 布尔评分，0/1 或 true/false | 1, 0 |

---

## 二、评分数据模型

### 2.1 Score 对象结构

```python
{
    "name": "relevance_score",           # 评分名称（必填）
    "value": 0.85,                       # 评分值（必填）
    "data_type": "NUMERIC",              # 数据类型：NUMERIC/CATEGORICAL/BOOLEAN
    "trace_id": "trace_xxx",             # 关联的 Trace ID（可选）
    "observation_id": "obs_xxx",         # 关联的 Observation ID（可选）
    "session_id": "session_xxx",         # 关联的 Session ID（可选）
    "config_id": "config_xxx",           # 关联的 ScoreConfig ID（可选）
    "comment": "回答与问题高度相关",      # 评分说明（可选）
    "metadata": {                        # 元数据（可选）
        "evaluation_type": "auto",
        "evaluator": "llm_judge"
    }
}
```

### 2.2 ScoreConfig（评分配置）

**ScoreConfig** 是对评分指标的定义，用于标准化评分 schema：

- **名称**：评分指标的名称（如 "relevance_score"）
- **类型**：NUMERIC、CATEGORICAL、BOOLEAN
- **数值范围**：对于 NUMERIC 类型，定义 min/max（如 0-1）
- **类别集合**：对于 CATEGORICAL 类型，定义可选类别（如 ["good", "neutral", "bad"]）

**作用**：
- 统一评分标准
- 在 ingestion（摄入评分）阶段强制校验
- 确保评分数据的一致性

**创建方式**：
- 通过 Langfuse UI 创建
- 通过 API/SDK 创建

---

## 三、评分来源与评估方法

Langfuse 支持多种方式获取评分，用于评估模型或应用质量：

### 3.1 LLM-as-a-Judge（LLM 作为评分者）

**原理**：使用一个大模型按照规则（Prompt + 标准）来自动打分。

**适用场景**：
- 主观度较高的维度（相关性、风格、语气）
- 需要理解语义的评估（是否有幻觉、是否准确）

**优点**：
- 自动化，无需人工干预
- 可以批量评估
- 成本相对较低

**缺点**：
- 评估结果可能不够准确
- 需要设计好的 Prompt
- 需要额外的 LLM 调用成本

**示例**：
```python
# 使用 LLM 评估回复质量
evaluation_prompt = """
请评估以下回复的质量，从以下维度打分（0-1分）：
1. 相关性：回复是否与问题相关
2. 完整性：回复是否完整回答了问题
3. 准确性：回复内容是否准确

请返回JSON格式：
{
    "relevance_score": 0.0-1.0,
    "completeness_score": 0.0-1.0,
    "accuracy_score": 0.0-1.0,
    "overall_score": 0.0-1.0
}
"""

# 调用 LLM 进行评估
llm_response = llm.invoke(evaluation_prompt)
scores = json.loads(llm_response.content)

# 记录评分到 Langfuse
for score_name, score_value in scores.items():
    langfuse.score(
        name=score_name,
        value=score_value,
        trace_id=trace_id
    )
```

### 3.2 人工标注（Human Annotations）

**原理**：人工给出评估，通常用于训练集、离线评估或质量检查。

**适用场景**：
- 需要高准确度的评估
- 建立评估基线
- 验证自动评估的准确性

**优点**：
- 评估结果准确
- 可以处理复杂场景

**缺点**：
- 成本高、耗时长
- 难以大规模应用

### 3.3 自定义评分（Custom Scores）

**原理**：使用脚本、业务逻辑来做评估，比如检查关键词、长度、结构等。

**适用场景**：
- 客观维度评估（长度、格式、关键词）
- 业务规则检查（是否包含特定字段）
- 性能指标（响应时间、token 使用量）

**优点**：
- 快速、准确
- 无需额外成本
- 可以实时评估

**缺点**：
- 只能评估客观指标
- 无法评估语义相关的内容

**示例**：
```python
# 自定义评分：检查回复长度
def evaluate_response_length(response: str) -> float:
    """评估回复长度是否合适"""
    length = len(response)
    if 50 <= length <= 500:
        return 1.0  # 长度合适
    elif length < 50:
        return 0.5  # 太短
    else:
        return 0.7  # 太长

# 记录评分
score = evaluate_response_length(response_text)
langfuse.score(
    name="length_score",
    value=score,
    trace_id=trace_id,
    comment=f"回复长度: {len(response_text)} 字符"
)
```

---

## 四、评分功能使用方法

### 4.1 Python SDK 使用方式

#### 4.1.1 基本用法

```python
from langfuse import Langfuse

# 初始化 Langfuse 客户端
langfuse = Langfuse(
    public_key="pk-lf-...",
    secret_key="sk-lf-...",
    host="https://cloud.langfuse.com"
)

# 方式1：为 Trace 评分
trace = langfuse.trace(id="trace_id")
trace.score(
    name="user_satisfaction",
    value=0.9,
    comment="用户对回复很满意"
)

# 方式2：直接使用 score() 方法
langfuse.score(
    name="relevance_score",
    value=0.85,
    trace_id="trace_id",
    comment="回答与问题高度相关"
)
```

#### 4.1.2 为不同实体评分

```python
# 为 Trace 评分
langfuse.score(
    name="overall_quality",
    value=0.9,
    trace_id="trace_xxx"
)

# 为 Generation（LLM 调用）评分
langfuse.score(
    name="accuracy_score",
    value=0.85,
    trace_id="trace_xxx",
    observation_id="generation_xxx"  # Generation 的 ID
)

# 为 Span（节点）评分
langfuse.score(
    name="node_performance",
    value=0.8,
    trace_id="trace_xxx",
    observation_id="span_xxx"  # Span 的 ID
)

# 为 Session 评分
langfuse.score(
    name="session_satisfaction",
    value=0.9,
    session_id="session_xxx"
)
```

#### 4.1.3 使用 ScoreConfig

```python
# 创建 ScoreConfig（通常在初始化时创建一次）
# 注意：ScoreConfig 需要通过 UI 或 API 创建，SDK 可能不支持直接创建

# 使用 ScoreConfig 记录评分
langfuse.score(
    name="relevance_score",
    value=0.85,
    trace_id="trace_xxx",
    config_id="relevance_config_id"  # 关联到 ScoreConfig
)
```

#### 4.1.4 记录多维度评分

```python
# 记录多个维度的评分
scores = {
    "relevance_score": 0.9,
    "completeness_score": 0.85,
    "accuracy_score": 0.8,
    "safety_score": 0.95,
    "overall_score": 0.875
}

for score_name, score_value in scores.items():
    langfuse.score(
        name=score_name,
        value=score_value,
        trace_id=trace_id,
        comment=f"{score_name} 评分"
    )
```

### 4.2 在 LangGraph 节点中使用

```python
from langfuse import Langfuse
from langchain_core.messages import AIMessage

def agent_node(state: RouterState) -> RouterState:
    """智能体节点，执行后记录评分"""
    langfuse = Langfuse()
    
    # 获取当前 trace_id（从上下文或 state 中获取）
    trace_id = get_current_trace_id()
    
    # 执行智能体逻辑
    response = agent.invoke(state)
    
    # 评估回复质量（使用 LLM-as-a-Judge）
    evaluation_result = evaluate_response_quality(
        user_query=state["user_query"],
        response=response.content
    )
    
    # 记录评分到 Langfuse
    for score_name, score_value in evaluation_result.items():
        langfuse.score(
            name=score_name,
            value=score_value,
            trace_id=trace_id,
            comment=f"自动评估: {score_name}"
        )
    
    return state
```

---

## 五、项目集成方案

### 5.1 在 langfuse_handler.py 中添加评分功能

在 `backend/infrastructure/observability/langfuse_handler.py` 中添加评分相关函数：

```python
def record_langfuse_score(
    name: str,
    value: float,
    trace_id: Optional[str] = None,
    observation_id: Optional[str] = None,
    session_id: Optional[str] = None,
    comment: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    config_id: Optional[str] = None
) -> bool:
    """
    记录 Langfuse Score
    
    Args:
        name: 评分名称（如 "relevance_score", "completeness_score"）
        value: 评分值（0.0-1.0 或自定义范围）
        trace_id: Trace ID（可选）
        observation_id: Observation ID（可选，用于关联 Generation 或 Span）
        session_id: Session ID（可选）
        comment: 评分说明（可选）
        metadata: 元数据（可选）
        config_id: ScoreConfig ID（可选）
        
    Returns:
        bool: 是否记录成功
    """
    if not is_langfuse_available():
        logger.debug("Langfuse不可用，跳过评分记录")
        return False
    
    langfuse_client = get_langfuse_client()
    if not langfuse_client:
        logger.warning("Langfuse客户端获取失败，跳过评分记录")
        return False
    
    try:
        # 构建评分参数
        score_params = {
            "name": name,
            "value": value,
        }
        
        if trace_id:
            score_params["trace_id"] = normalize_langfuse_trace_id(trace_id)
        if observation_id:
            score_params["observation_id"] = observation_id
        if session_id:
            score_params["session_id"] = session_id
        if comment:
            score_params["comment"] = comment
        if metadata:
            score_params["metadata"] = metadata
        if config_id:
            score_params["config_id"] = config_id
        
        # 记录评分
        langfuse_client.score(**score_params)
        
        logger.info(
            f"记录 Langfuse Score: name={name}, value={value}, "
            f"trace_id={trace_id}, comment={comment}"
        )
        return True
        
    except Exception as e:
        # 错误隔离：Score 记录失败不影响主流程
        logger.warning(f"记录 Langfuse Score 失败: {e}，继续执行主流程", exc_info=True)
        return False
```

### 5.2 实现自动评估函数

```python
async def evaluate_response_quality_with_llm(
    user_query: str,
    response_content: str,
    trace_id: Optional[str] = None,
    generation_id: Optional[str] = None
) -> Dict[str, float]:
    """
    使用 LLM 自动评估回复质量并记录 Scores
    
    Args:
        user_query: 用户问题
        response_content: AI 回复内容
        trace_id: Trace ID（用于记录评分）
        generation_id: Generation ID（用于记录评分）
        
    Returns:
        评分字典，包含各项评分
    """
    from langchain_core.prompts import ChatPromptTemplate
    from backend.infrastructure.llm.client import get_llm_by_config
    from backend.infrastructure.observability.langfuse_handler import record_langfuse_score
    from backend.app.config import settings
    import json
    
    if not settings.LANGFUSE_ENABLED:
        return {}
    
    # 构建评估 Prompt
    evaluation_prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的评估专家，负责评估 AI 助手的回复质量。

评估标准：
1. **相关性**：回复是否与用户问题相关（0-1分）
2. **完整性**：回复是否完整回答了用户问题（0-1分）
3. **准确性**：回复内容是否准确，特别是医疗建议（0-1分）
4. **安全性**：回复是否包含敏感信息或不当建议（0-1分，越高越安全）
5. **合规性**：回复是否符合医疗行业规范（0-1分）

请返回JSON格式的评估结果：
{
    "relevance_score": 0.0-1.0,
    "completeness_score": 0.0-1.0,
    "accuracy_score": 0.0-1.0,
    "safety_score": 0.0-1.0,
    "compliance_score": 0.0-1.0,
    "overall_score": 0.0-1.0
}"""),
        ("human", """用户问题：{user_query}

AI回复：{response_content}

请对回复质量进行全面评估。""")
    ])
    
    try:
        # 获取 LLM 客户端
        llm = get_llm_by_config()
        
        # 调用 LLM 进行评估
        chain = evaluation_prompt | llm
        response = chain.invoke({
            "user_query": user_query,
            "response_content": response_content
        })
        
        # 解析评估结果
        eval_text = response.content if hasattr(response, 'content') else str(response)
        eval_result = json.loads(eval_text)
        
        # 记录各项评分到 Langfuse
        scores = {}
        for score_name, score_value in eval_result.items():
            if score_name.endswith("_score") and isinstance(score_value, (int, float)):
                # 记录评分
                record_langfuse_score(
                    trace_id=trace_id,
                    observation_id=generation_id,
                    name=score_name,
                    value=float(score_value),
                    comment=f"自动评估: {score_name}",
                    metadata={
                        "evaluation_type": "auto",
                        "evaluator": "llm_judge"
                    }
                )
                scores[score_name] = float(score_value)
        
        logger.info(
            f"自动评估完成: trace_id={trace_id}, "
            f"overall_score={eval_result.get('overall_score', 0.0)}"
        )
        
        return scores
        
    except Exception as e:
        logger.error(f"自动评估失败: {e}", exc_info=True)
        return {}
```

### 5.3 在 API 路由中集成评分

在 `backend/app/api/routes/chat.py` 中添加评分记录：

```python
from backend.infrastructure.observability.langfuse_handler import (
    record_langfuse_score,
    evaluate_response_quality_with_llm
)

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, app_request: Request) -> ChatResponse:
    """聊天接口"""
    try:
        # ... 现有的聊天逻辑 ...
        
        # 执行流程图
        result = await graph.ainvoke(initial_state, config)
        
        # 提取回复内容
        response_text = extract_response(result)
        
        # 可选：自动评估回复质量（如果启用）
        if settings.LANGFUSE_ENABLED and settings.LANGFUSE_AUTO_EVALUATION:
            await evaluate_response_quality_with_llm(
                user_query=request.message,
                response_content=response_text,
                trace_id=request.trace_id,
                generation_id=None  # 可以从 result 中获取
            )
        
        return ChatResponse(
            response=response_text,
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"处理聊天请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")
```

### 5.4 添加用户反馈评分接口

```python
@router.post("/chat/{trace_id}/score")
async def record_chat_score(
    trace_id: str,
    score_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    记录聊天评分（用户反馈）
    
    Args:
        trace_id: Trace ID
        score_data: 评分数据
            - name: 评分名称（如 "user_satisfaction"）
            - value: 评分值（0.0-1.0 或自定义范围）
            - comment: 评分说明（可选）
            - metadata: 元数据（可选）
            
    Returns:
        操作结果
    """
    from backend.infrastructure.observability.langfuse_handler import record_langfuse_score
    
    try:
        success = record_langfuse_score(
            trace_id=trace_id,
            name=score_data.get("name", "user_satisfaction"),
            value=score_data.get("value", 0.0),
            comment=score_data.get("comment"),
            metadata={
                **(score_data.get("metadata", {})),
                "source": "user_feedback"  # 标记为用户反馈
            }
        )
        
        if success:
            return {"message": "评分记录成功", "trace_id": trace_id}
        else:
            raise HTTPException(status_code=500, detail="评分记录失败")
            
    except Exception as e:
        logger.error(f"记录评分失败: trace_id={trace_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"记录评分失败: {str(e)}")
```

### 5.5 配置项添加

在 `backend/app/config.py` 中添加评分相关配置：

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # Langfuse 评分配置
    LANGFUSE_ENABLE_SCORES: bool = True  # 是否启用 Scores 功能（默认启用）
    LANGFUSE_AUTO_EVALUATION: bool = False  # 是否启用自动评估（默认禁用，需要额外 LLM 调用）
    LANGFUSE_EVALUATION_MODEL: Optional[str] = None  # 自动评估使用的模型（可选）
```

---

## 六、评分数据分析与调优

### 6.1 Score Analytics（评分分析）

Langfuse 提供了 Score Analytics 功能来帮助你理解、对比、监测这些分数。

#### 6.1.1 核心能力

1. **分布与趋势**：
   - 查看某个分数随时间的变化（Trend Over Time）
   - 查看分数的分布情况（Histogram）

2. **比对分析**：
   - 比对两个分数（如 LLM 评分 vs 人工评分）
   - 计算 Pearson / Spearman 相关系数
   - 计算 MAE / RMSE 等误差指标
   - 对于分类/布尔型支持 Cohen's Kappa、F1、整体一致性等

3. **版本对比**：
   - 对比不同模型版本之间的分数
   - 跟踪某一指标随版本迭代的改善

#### 6.1.2 使用场景

- **验证 LLM 评分者 vs 人工标注的一致性**：如果两者 correlation 很高，可以信任自动评估
- **跟踪指标随版本迭代的改善**：例如正确率从 0.75 提升到 0.85，幻觉率下降等
- **识别低分案例**：查看哪些 Trace 评分较低，分析共性问题

### 6.2 调优流程

#### 6.2.1 建立基线（Baseline）

在引入评分之前，对现有模型或当前版本跑一次 test dataset，给每个评分维度打分：

```python
# 使用固定数据集进行评估
test_dataset = [
    {"query": "我想记录血压，收缩压120，舒张压80", "expected_intent": "blood_pressure"},
    {"query": "我想预约复诊", "expected_intent": "appointment"},
    # ... 更多测试用例
]

baseline_scores = {}
for test_case in test_dataset:
    # 执行流程并记录评分
    result = await graph.ainvoke(test_case)
    scores = await evaluate_response_quality_with_llm(
        user_query=test_case["query"],
        response_content=result["response"]
    )
    # 汇总评分
    for score_name, score_value in scores.items():
        if score_name not in baseline_scores:
            baseline_scores[score_name] = []
        baseline_scores[score_name].append(score_value)

# 计算基线平均值
baseline_avg = {
    score_name: sum(values) / len(values)
    for score_name, values in baseline_scores.items()
}
print(f"基线评分: {baseline_avg}")
```

#### 6.2.2 定期评估

- **Offline 评估**：用固定 dataset 进行评估，跑实验（DatasetRun），得到每个维度的分数
- **Online 评估**：在真实用户交互中收集评分，例如用户反馈、抽样 trace 用人工或 LLM 给分

#### 6.2.3 分析与定位改进点

1. **查看低分案例**：
   - 在 Langfuse Dashboard 中筛选低分 Trace
   - 分析共性问题（prompt、模型、上下文长度、输入格式等）

2. **多维度分析**：
   - 看多个维度是否冲突，如正确性高但是相关性低
   - 了解 trade-off，找到平衡点

3. **版本对比**：
   - 每次改 prompt / 调整模型 / 改策略后，跑新的 DatasetRun
   - 对比评分基线与新版本，确认改进
   - 看是否有副作用，例如改正确性提升但回应变长导致风格/简洁性变差等

#### 6.2.4 构建自动化监控与告警

```python
# 定期抽样打分（自动或人工/LLM裁判员）
async def monitor_scores():
    """监控评分趋势"""
    # 获取最近 N 条 Trace 的评分
    recent_scores = get_recent_scores(limit=100)
    
    # 计算平均分
    avg_scores = calculate_average_scores(recent_scores)
    
    # 检查是否有下降
    for score_name, avg_value in avg_scores.items():
        baseline = get_baseline_score(score_name)
        if avg_value < baseline * 0.9:  # 下降超过 10%
            # 触发告警
            send_alert(f"{score_name} 评分下降: {baseline} -> {avg_value}")
```

---

## 七、最佳实践

### 7.1 评分维度设计

**建议的评分维度**：

1. **相关性（Relevance）**：回复是否与问题相关
2. **完整性（Completeness）**：回复是否完整回答了问题
3. **准确性（Accuracy）**：回复内容是否准确
4. **安全性（Safety）**：回复是否安全、合规
5. **用户满意度（User Satisfaction）**：用户对回复的满意度

**评分标准**：
- 使用 0-1 的数值型评分，便于计算和分析
- 为每个维度创建 ScoreConfig，确保一致性
- 明确定义每个分数的含义（如 0.9 表示优秀，0.7 表示良好）

### 7.2 评分记录时机

1. **自动评估**：在流程执行完成后自动评估（可选，需要额外 LLM 调用）
2. **用户反馈**：用户主动给出反馈时记录
3. **抽样评估**：定期抽样评估，用于监控质量

### 7.3 错误处理

```python
# 评分记录失败不应该影响主流程
try:
    record_langfuse_score(...)
except Exception as e:
    logger.warning(f"评分记录失败: {e}，继续执行主流程")
    # 不抛出异常，确保主流程继续
```

### 7.4 性能考虑

1. **异步处理**：自动评估可以异步处理，不阻塞主流程
2. **采样率**：在生产环境中可以设置采样率，只评估部分请求
3. **缓存**：对于相同的输入，可以缓存评估结果

### 7.5 数据隐私

- 评分数据可能包含敏感信息，注意数据隐私保护
- 可以考虑对评分数据进行脱敏处理

---

## 八、总结

### 8.1 核心要点

1. **Score 是评估工具**：用于评估 LLM 应用质量，支持多维度评分
2. **多种评估方法**：LLM-as-a-Judge、人工标注、自定义评分
3. **数据分析**：通过 Score Analytics 分析评分趋势，识别改进点
4. **持续优化**：基于评分数据建立基线、对比版本、持续改进

### 8.2 实施步骤

1. **定义评分维度**：确定要评估的维度（相关性、完整性、准确性等）
2. **创建 ScoreConfig**：在 Langfuse UI 中创建评分配置
3. **集成评分功能**：在代码中添加评分记录逻辑
4. **建立基线**：对当前版本进行评估，建立基线
5. **持续监控**：定期评估，监控评分趋势
6. **优化迭代**：基于评分数据优化提示词、模型、流程

### 8.3 下一步

1. 在项目中集成评分功能
2. 定义适合项目的评分维度
3. 建立评估基线和监控机制
4. 基于评分数据持续优化

---

## 参考资料

- **Langfuse Scores 官方文档**：https://langfuse.com/docs/scores
- **Langfuse Evaluation 文档**：https://langfuse.com/docs/evaluation
- **Langfuse Python SDK**：https://langfuse.com/docs/sdk/python
- **项目中的 Langfuse 集成**：`backend/infrastructure/observability/langfuse_handler.py`

---

*最后更新：2026-01-16*
