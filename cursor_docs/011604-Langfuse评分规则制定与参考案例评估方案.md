# Langfuse 评分规则制定与参考案例评估方案

## 文档说明

本文档详细说明如何制定 Langfuse 评分规则，以及如何使用参考案例（如线上版本）进行评分，帮助团队在制作 AI 复制品时评估与线上版本的相似度。

**文档版本**：V1.0  
**创建时间**：2026-01-16

---

## 目录

1. [评分规则制定方法](#一评分规则制定方法)
2. [参考案例评估方案](#二参考案例评估方案)
3. [相似度评估方法](#三相似度评估方法)
4. [实现方案](#四实现方案)
5. [最佳实践](#五最佳实践)

---

## 一、评分规则制定方法

### 1.1 评分规则制定的核心原则

制定评分规则时，需要遵循以下原则：

1. **明确性**：评分标准必须清晰明确，避免主观歧义
2. **可操作性**：评分标准必须可执行，能够通过自动化或人工方式评估
3. **相关性**：评分维度必须与业务目标相关
4. **可量化**：尽量使用数值型评分，便于分析和对比
5. **一致性**：评分标准应该在不同评估者之间保持一致

### 1.2 评分规则制定的步骤

#### 步骤1：明确评估目标

首先需要明确评估的目标：

- **业务目标**：提升用户满意度、减少错误率、提高响应速度等
- **技术目标**：与线上版本保持一致、提升模型性能、优化成本等
- **质量目标**：提高准确性、完整性、相关性等

**示例**：
```
评估目标：制作一个与线上 AI 复制品，希望：
1. 回复内容与线上版本尽可能相似
2. 保持相同的回复风格和语气
3. 确保关键信息不遗漏
4. 维持相同的安全性和合规性标准
```

#### 步骤2：定义评分维度

根据评估目标，定义具体的评分维度：

**通用评分维度**：
- **相关性（Relevance）**：回复是否与问题相关
- **完整性（Completeness）**：回复是否完整回答了问题
- **准确性（Accuracy）**：回复内容是否准确
- **相似度（Similarity）**：与参考案例（线上版本）的相似程度
- **风格一致性（Style Consistency）**：与参考案例的风格是否一致
- **安全性（Safety）**：回复是否安全、合规

**针对复制品的特殊维度**：
- **语义相似度（Semantic Similarity）**：与参考案例的语义相似程度
- **关键信息覆盖度（Key Information Coverage）**：是否覆盖了参考案例中的关键信息
- **结构相似度（Structure Similarity）**：回复结构是否与参考案例相似
- **语气一致性（Tone Consistency）**：语气是否与参考案例一致

#### 步骤3：制定评分标准

为每个评分维度制定具体的评分标准：

**示例：相似度评分标准**

| 分数范围 | 标准描述 | 示例 |
|---------|---------|------|
| 0.9-1.0 | 几乎完全相同，语义和结构高度一致 | 回复内容与参考案例在语义上几乎一致，仅有个别词汇差异 |
| 0.7-0.9 | 高度相似，核心内容一致 | 回复的核心信息和结构一致，但表达方式略有不同 |
| 0.5-0.7 | 中等相似，部分内容一致 | 回复包含参考案例的部分关键信息，但结构或表达有较大差异 |
| 0.3-0.5 | 低相似度，少量内容一致 | 回复仅包含参考案例的少量信息，大部分内容不同 |
| 0.0-0.3 | 几乎不相似 | 回复与参考案例在语义和结构上差异很大 |

**示例：关键信息覆盖度评分标准**

| 分数范围 | 标准描述 |
|---------|---------|
| 0.9-1.0 | 覆盖了参考案例中所有关键信息 |
| 0.7-0.9 | 覆盖了参考案例中大部分关键信息（>80%） |
| 0.5-0.7 | 覆盖了参考案例中部分关键信息（50%-80%） |
| 0.3-0.5 | 覆盖了参考案例中少量关键信息（20%-50%） |
| 0.0-0.3 | 几乎没有覆盖参考案例中的关键信息（<20%） |

#### 步骤4：创建 ScoreConfig

在 Langfuse 中为每个评分维度创建 ScoreConfig：

```python
# 通过 Langfuse UI 或 API 创建 ScoreConfig
score_configs = [
    {
        "name": "similarity_score",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
        "description": "与参考案例的相似度评分（0-1）"
    },
    {
        "name": "semantic_similarity_score",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
        "description": "与参考案例的语义相似度评分（0-1）"
    },
    {
        "name": "key_info_coverage_score",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
        "description": "关键信息覆盖度评分（0-1）"
    },
    {
        "name": "style_consistency_score",
        "data_type": "NUMERIC",
        "min_value": 0.0,
        "max_value": 1.0,
        "description": "风格一致性评分（0-1）"
    }
]
```

### 1.3 评分规则文档化

将评分规则文档化，便于团队共享和维护：

```markdown
# 评分规则文档

## 1. 相似度评分（similarity_score）

### 评分标准
- 0.9-1.0：几乎完全相同
- 0.7-0.9：高度相似
- 0.5-0.7：中等相似
- 0.3-0.5：低相似度
- 0.0-0.3：几乎不相似

### 评估方法
使用 Embedding 相似度 + LLM 评估相结合的方式

### 评估示例
- 参考案例："您的血压是 120/80 mmHg，属于正常范围。"
- 测试回复："您的血压值为 120/80 mmHg，在正常范围内。"
- 预期评分：0.95（高度相似，语义一致）
```

---

## 二、参考案例评估方案

### 2.1 为什么需要参考案例

在制作 AI 复制品时，引入参考案例（线上版本）有以下优势：

1. **目标明确**：参考案例提供了明确的目标，知道"好"的标准是什么
2. **一致性保证**：确保新版本与线上版本在关键方面保持一致
3. **快速迭代**：通过对比参考案例，快速识别需要改进的地方
4. **质量基准**：参考案例可以作为质量基准，评估新版本的质量

### 2.2 参考案例的来源

参考案例可以从以下渠道获取：

1. **线上生产环境**：
   - 从生产环境的日志中提取用户问题和对应的回复
   - 选择高质量、有代表性的案例

2. **历史数据**：
   - 从历史对话记录中提取
   - 选择不同场景、不同类型的案例

3. **人工标注**：
   - 人工筛选和标注高质量的案例
   - 确保案例的代表性和多样性

4. **测试数据集**：
   - 使用已有的测试数据集
   - 或创建专门的测试数据集

### 2.3 参考案例的管理

#### 2.3.1 参考案例数据结构

```python
class ReferenceCase:
    """参考案例数据结构"""
    def __init__(
        self,
        case_id: str,
        user_query: str,
        reference_response: str,  # 线上版本的回复
        metadata: Dict[str, Any] = None
    ):
        self.case_id = case_id
        self.user_query = user_query
        self.reference_response = reference_response
        self.metadata = metadata or {}
        # metadata 可以包含：
        # - agent_name: 使用的智能体
        # - intent: 用户意图
        # - key_points: 关键信息点列表
        # - style_notes: 风格说明
```

#### 2.3.2 参考案例存储

可以使用以下方式存储参考案例：

1. **数据库存储**：
   ```python
   # 在数据库中创建参考案例表
   CREATE TABLE reference_cases (
       case_id VARCHAR(64) PRIMARY KEY,
       user_query TEXT NOT NULL,
       reference_response TEXT NOT NULL,
       agent_name VARCHAR(64),
       intent VARCHAR(64),
       key_points JSONB,
       created_at TIMESTAMP DEFAULT NOW()
   );
   ```

2. **文件存储**：
   ```python
   # 使用 JSON 文件存储参考案例
   reference_cases = [
       {
           "case_id": "case_001",
           "user_query": "我想记录血压，收缩压120，舒张压80",
           "reference_response": "好的，我已经为您记录了血压：收缩压 120 mmHg，舒张压 80 mmHg。您的血压值在正常范围内。",
           "metadata": {
               "agent_name": "blood_pressure_agent",
               "intent": "record_blood_pressure",
               "key_points": ["血压值", "正常范围"]
           }
       }
   ]
   ```

3. **Langfuse Dataset**：
   ```python
   # 使用 Langfuse Dataset 存储参考案例
   from langfuse import Langfuse
   
   langfuse = Langfuse()
   
   # 创建 Dataset
   dataset = langfuse.create_dataset(name="reference_cases")
   
   # 添加参考案例
   dataset.create_item(
       input={"user_query": "我想记录血压，收缩压120，舒张压80"},
       expected_output="好的，我已经为您记录了血压：收缩压 120 mmHg，舒张压 80 mmHg。您的血压值在正常范围内。",
       metadata={
           "agent_name": "blood_pressure_agent",
           "intent": "record_blood_pressure"
       }
   )
   ```

### 2.4 参考案例的使用方式

#### 方式1：直接对比评估

在评估时，将参考案例作为输入，直接对比测试回复与参考回复：

```python
async def evaluate_with_reference(
    user_query: str,
    test_response: str,
    reference_response: str,
    trace_id: str
) -> Dict[str, float]:
    """
    使用参考案例进行评估
    
    Args:
        user_query: 用户问题
        test_response: 测试回复（新版本）
        reference_response: 参考回复（线上版本）
        trace_id: Trace ID
        
    Returns:
        评分字典
    """
    # 1. 计算相似度评分
    similarity_score = calculate_similarity(test_response, reference_response)
    
    # 2. 使用 LLM 进行多维度评估
    llm_scores = await evaluate_with_llm_judge(
        user_query=user_query,
        test_response=test_response,
        reference_response=reference_response
    )
    
    # 3. 记录评分到 Langfuse
    from backend.infrastructure.observability.langfuse_handler import record_langfuse_score
    
    record_langfuse_score(
        trace_id=trace_id,
        name="similarity_score",
        value=similarity_score,
        comment=f"与参考案例的相似度: {similarity_score:.2f}"
    )
    
    for score_name, score_value in llm_scores.items():
        record_langfuse_score(
            trace_id=trace_id,
            name=score_name,
            value=score_value,
            comment=f"LLM评估: {score_name}"
        )
    
    return {
        "similarity_score": similarity_score,
        **llm_scores
    }
```

#### 方式2：作为评估标准

将参考案例作为评估标准，评估测试回复是否符合标准：

```python
async def evaluate_against_reference(
    user_query: str,
    test_response: str,
    reference_case: ReferenceCase,
    trace_id: str
) -> Dict[str, float]:
    """
    以参考案例为标准进行评估
    
    Args:
        user_query: 用户问题
        test_response: 测试回复
        reference_case: 参考案例
        trace_id: Trace ID
        
    Returns:
        评分字典
    """
    reference_response = reference_case.reference_response
    
    # 评估维度
    scores = {}
    
    # 1. 相似度评分
    scores["similarity_score"] = calculate_similarity(
        test_response, 
        reference_response
    )
    
    # 2. 关键信息覆盖度
    scores["key_info_coverage_score"] = calculate_key_info_coverage(
        test_response,
        reference_case.metadata.get("key_points", [])
    )
    
    # 3. 风格一致性
    scores["style_consistency_score"] = await evaluate_style_consistency(
        test_response,
        reference_response
    )
    
    # 4. 语义相似度
    scores["semantic_similarity_score"] = calculate_semantic_similarity(
        test_response,
        reference_response
    )
    
    # 记录评分
    for score_name, score_value in scores.items():
        record_langfuse_score(
            trace_id=trace_id,
            name=score_name,
            value=score_value,
            comment=f"参考案例: {reference_case.case_id}"
        )
    
    return scores
```

---

## 三、相似度评估方法

### 3.1 文本相似度计算方法

#### 3.1.1 基于 Embedding 的语义相似度

使用 Embedding 模型计算两个文本的语义相似度：

```python
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class SemanticSimilarityCalculator:
    """语义相似度计算器"""
    
    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        self.model = SentenceTransformer(model_name)
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的语义相似度（0-1）
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度分数（0-1）
        """
        # 生成 Embedding
        embeddings = self.model.encode([text1, text2])
        
        # 计算余弦相似度
        similarity = cosine_similarity(
            embeddings[0:1],
            embeddings[1:2]
        )[0][0]
        
        return float(similarity)
    
    def calculate_batch_similarity(
        self, 
        texts1: List[str], 
        texts2: List[str]
    ) -> List[float]:
        """批量计算相似度"""
        embeddings1 = self.model.encode(texts1)
        embeddings2 = self.model.encode(texts2)
        
        similarities = cosine_similarity(embeddings1, embeddings2)
        
        # 返回对角线元素（对应位置的相似度）
        return [float(similarities[i][i]) for i in range(len(texts1))]
```

#### 3.1.2 基于字符串的相似度

使用字符串相似度算法（如 Levenshtein 距离、Jaccard 相似度）：

```python
from difflib import SequenceMatcher
import jieba

class StringSimilarityCalculator:
    """字符串相似度计算器"""
    
    @staticmethod
    def calculate_sequence_similarity(text1: str, text2: str) -> float:
        """
        使用 SequenceMatcher 计算相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度分数（0-1）
        """
        return SequenceMatcher(None, text1, text2).ratio()
    
    @staticmethod
    def calculate_jaccard_similarity(text1: str, text2: str) -> float:
        """
        使用 Jaccard 相似度计算
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度分数（0-1）
        """
        # 分词
        words1 = set(jieba.cut(text1))
        words2 = set(jieba.cut(text2))
        
        # 计算交集和并集
        intersection = words1 & words2
        union = words1 | words2
        
        if len(union) == 0:
            return 0.0
        
        return len(intersection) / len(union)
```

#### 3.1.3 混合相似度计算

结合多种方法计算综合相似度：

```python
class HybridSimilarityCalculator:
    """混合相似度计算器"""
    
    def __init__(self):
        self.semantic_calc = SemanticSimilarityCalculator()
        self.string_calc = StringSimilarityCalculator()
    
    def calculate_similarity(
        self, 
        text1: str, 
        text2: str,
        weights: Dict[str, float] = None
    ) -> Dict[str, float]:
        """
        计算混合相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            weights: 权重配置
                - semantic: 语义相似度权重（默认0.7）
                - string: 字符串相似度权重（默认0.3）
                
        Returns:
            相似度分数字典
        """
        if weights is None:
            weights = {"semantic": 0.7, "string": 0.3}
        
        # 计算各种相似度
        semantic_sim = self.semantic_calc.calculate_similarity(text1, text2)
        string_sim = self.string_calc.calculate_sequence_similarity(text1, text2)
        
        # 加权平均
        combined_sim = (
            semantic_sim * weights["semantic"] +
            string_sim * weights["string"]
        )
        
        return {
            "semantic_similarity": semantic_sim,
            "string_similarity": string_sim,
            "combined_similarity": combined_sim
        }
```

### 3.2 使用 LLM 进行相似度评估

使用 LLM 作为评判者，评估两个回复的相似度：

```python
from langchain_core.prompts import ChatPromptTemplate
from backend.infrastructure.llm.client import get_llm_by_config
import json

async def evaluate_similarity_with_llm(
    user_query: str,
    test_response: str,
    reference_response: str
) -> Dict[str, float]:
    """
    使用 LLM 评估相似度
    
    Args:
        user_query: 用户问题
        test_response: 测试回复
        reference_response: 参考回复
        
    Returns:
        评分字典
    """
    evaluation_prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个专业的评估专家，负责评估两个回复的相似度。

评估维度：
1. **语义相似度**：两个回复在语义上是否相似（0-1分）
2. **内容完整性**：测试回复是否包含了参考回复中的关键信息（0-1分）
3. **风格一致性**：测试回复的风格是否与参考回复一致（0-1分）
4. **结构相似度**：测试回复的结构是否与参考回复相似（0-1分）

请返回JSON格式的评估结果：
{
    "semantic_similarity": 0.0-1.0,
    "content_completeness": 0.0-1.0,
    "style_consistency": 0.0-1.0,
    "structure_similarity": 0.0-1.0,
    "overall_similarity": 0.0-1.0,
    "reasoning": "评估理由"
}"""),
        ("human", """用户问题：{user_query}

参考回复（线上版本）：
{reference_response}

测试回复（新版本）：
{test_response}

请评估两个回复的相似度。""")
    ])
    
    llm = get_llm_by_config()
    chain = evaluation_prompt | llm
    
    response = chain.invoke({
        "user_query": user_query,
        "reference_response": reference_response,
        "test_response": test_response
    })
    
    # 解析结果
    eval_text = response.content if hasattr(response, 'content') else str(response)
    eval_result = json.loads(eval_text)
    
    return {
        "semantic_similarity": eval_result.get("semantic_similarity", 0.0),
        "content_completeness": eval_result.get("content_completeness", 0.0),
        "style_consistency": eval_result.get("style_consistency", 0.0),
        "structure_similarity": eval_result.get("structure_similarity", 0.0),
        "overall_similarity": eval_result.get("overall_similarity", 0.0)
    }
```

### 3.3 关键信息提取与覆盖度计算

提取参考回复中的关键信息，评估测试回复的覆盖度：

```python
async def extract_key_information(response: str) -> List[str]:
    """
    从回复中提取关键信息
    
    Args:
        response: 回复内容
        
    Returns:
        关键信息列表
    """
    extraction_prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个信息提取专家，负责从回复中提取关键信息。

关键信息包括：
- 数值数据（如血压值、日期等）
- 关键结论（如"正常"、"异常"等）
- 重要建议（如"建议复查"等）
- 关键实体（如疾病名称、药物名称等）

请返回JSON格式的关键信息列表：
{
    "key_points": ["关键信息1", "关键信息2", ...]
}"""),
        ("human", "回复内容：{response}\n\n请提取关键信息。")
    ])
    
    llm = get_llm_by_config()
    chain = extraction_prompt | llm
    
    response_obj = chain.invoke({"response": response})
    result = json.loads(response_obj.content)
    
    return result.get("key_points", [])

def calculate_key_info_coverage(
    test_response: str,
    reference_key_points: List[str]
) -> float:
    """
    计算关键信息覆盖度
    
    Args:
        test_response: 测试回复
        reference_key_points: 参考回复的关键信息列表
        
    Returns:
        覆盖度分数（0-1）
    """
    if not reference_key_points:
        return 1.0  # 如果没有关键信息，认为完全覆盖
    
    # 检查每个关键信息是否在测试回复中
    covered_count = 0
    for key_point in reference_key_points:
        if key_point in test_response:
            covered_count += 1
    
    coverage = covered_count / len(reference_key_points)
    return coverage
```

---

## 四、实现方案

### 4.1 完整的评估流程

```python
"""
完整的参考案例评估流程
"""
import logging
from typing import Dict, Any, Optional, List
from backend.infrastructure.observability.langfuse_handler import (
    record_langfuse_score,
    get_langfuse_client
)
from backend.infrastructure.llm.client import get_llm_by_config

logger = logging.getLogger(__name__)

class ReferenceCaseEvaluator:
    """参考案例评估器"""
    
    def __init__(self):
        self.similarity_calc = HybridSimilarityCalculator()
    
    async def evaluate(
        self,
        user_query: str,
        test_response: str,
        reference_case: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, float]:
        """
        完整的评估流程
        
        Args:
            user_query: 用户问题
            test_response: 测试回复
            reference_case: 参考案例
                {
                    "case_id": "case_001",
                    "reference_response": "参考回复内容",
                    "metadata": {
                        "key_points": ["关键信息1", "关键信息2"],
                        "agent_name": "blood_pressure_agent"
                    }
                }
            trace_id: Trace ID
            
        Returns:
            评分字典
        """
        reference_response = reference_case["reference_response"]
        metadata = reference_case.get("metadata", {})
        
        scores = {}
        
        # 1. 计算相似度（基于 Embedding 和字符串）
        similarity_results = self.similarity_calc.calculate_similarity(
            test_response,
            reference_response
        )
        scores.update(similarity_results)
        
        # 2. 计算关键信息覆盖度
        key_points = metadata.get("key_points", [])
        if not key_points:
            # 如果没有提供关键信息，尝试提取
            key_points = await extract_key_information(reference_response)
        
        coverage_score = calculate_key_info_coverage(test_response, key_points)
        scores["key_info_coverage_score"] = coverage_score
        
        # 3. 使用 LLM 进行多维度评估
        llm_scores = await evaluate_similarity_with_llm(
            user_query=user_query,
            test_response=test_response,
            reference_response=reference_response
        )
        scores.update(llm_scores)
        
        # 4. 记录所有评分到 Langfuse
        for score_name, score_value in scores.items():
            record_langfuse_score(
                trace_id=trace_id,
                name=score_name,
                value=score_value,
                comment=f"参考案例: {reference_case.get('case_id', 'unknown')}",
                metadata={
                    "reference_case_id": reference_case.get("case_id"),
                    "evaluation_method": "reference_based"
                }
            )
        
        logger.info(
            f"参考案例评估完成: case_id={reference_case.get('case_id')}, "
            f"overall_similarity={scores.get('overall_similarity', 0.0):.2f}"
        )
        
        return scores
```

### 4.2 在 API 路由中集成

```python
from backend.infrastructure.observability.reference_evaluator import ReferenceCaseEvaluator

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, app_request: Request) -> ChatResponse:
    """聊天接口，支持参考案例评估"""
    try:
        # ... 现有的聊天逻辑 ...
        
        # 执行流程图
        result = await graph.ainvoke(initial_state, config)
        
        # 提取回复内容
        response_text = extract_response(result)
        
        # 如果提供了参考案例，进行评估
        if request.reference_case_id:
            # 获取参考案例
            reference_case = get_reference_case(request.reference_case_id)
            
            if reference_case:
                # 进行评估
                evaluator = ReferenceCaseEvaluator()
                scores = await evaluator.evaluate(
                    user_query=request.message,
                    test_response=response_text,
                    reference_case=reference_case,
                    trace_id=request.trace_id
                )
                
                logger.info(f"参考案例评估完成: scores={scores}")
        
        return ChatResponse(
            response=response_text,
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"处理聊天请求失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理请求失败: {str(e)}")
```

### 4.3 批量评估脚本

```python
"""
批量评估脚本：使用参考案例数据集评估新版本
"""
import asyncio
from typing import List, Dict, Any

async def batch_evaluate_with_references(
    test_cases: List[Dict[str, Any]],
    reference_cases: Dict[str, Dict[str, Any]],
    graph
) -> Dict[str, Any]:
    """
    批量评估
    
    Args:
        test_cases: 测试用例列表
            [
                {
                    "case_id": "test_001",
                    "user_query": "用户问题",
                    "reference_case_id": "ref_001"  # 关联的参考案例ID
                }
            ]
        reference_cases: 参考案例字典
            {
                "ref_001": {
                    "reference_response": "参考回复",
                    "metadata": {...}
                }
            }
        graph: 流程图实例
        
    Returns:
        评估结果
    """
    evaluator = ReferenceCaseEvaluator()
    results = []
    
    for test_case in test_cases:
        case_id = test_case["case_id"]
        user_query = test_case["user_query"]
        ref_case_id = test_case.get("reference_case_id")
        
        # 执行流程图，获取测试回复
        initial_state = build_initial_state_from_query(user_query)
        result = await graph.ainvoke(initial_state, config)
        test_response = extract_response(result)
        
        # 获取参考案例
        if ref_case_id and ref_case_id in reference_cases:
            reference_case = reference_cases[ref_case_id]
            reference_case["case_id"] = ref_case_id
            
            # 进行评估
            scores = await evaluator.evaluate(
                user_query=user_query,
                test_response=test_response,
                reference_case=reference_case,
                trace_id=f"batch_eval_{case_id}"
            )
            
            results.append({
                "case_id": case_id,
                "test_response": test_response,
                "reference_response": reference_case["reference_response"],
                "scores": scores
            })
    
    # 计算平均分
    avg_scores = {}
    if results:
        score_names = results[0]["scores"].keys()
        for score_name in score_names:
            avg_scores[score_name] = sum(
                r["scores"].get(score_name, 0.0) 
                for r in results
            ) / len(results)
    
    return {
        "results": results,
        "average_scores": avg_scores,
        "total_cases": len(results)
    }
```

---

## 五、最佳实践

### 5.1 参考案例的选择

1. **多样性**：选择不同场景、不同类型的案例
2. **代表性**：选择能够代表典型使用场景的案例
3. **质量**：选择高质量的案例，避免有问题的案例
4. **数量**：建议至少 50-100 个参考案例，确保评估的可靠性

### 5.2 评分权重的设置

根据业务目标调整不同评分维度的权重：

```python
# 如果目标是保持与线上版本一致，可以增加相似度权重
similarity_weights = {
    "semantic_similarity": 0.4,
    "key_info_coverage": 0.3,
    "style_consistency": 0.2,
    "structure_similarity": 0.1
}

# 如果目标是提升质量，可以增加质量维度权重
quality_weights = {
    "relevance": 0.3,
    "completeness": 0.3,
    "accuracy": 0.2,
    "similarity": 0.2
}
```

### 5.3 评估频率

1. **开发阶段**：每次代码变更后进行评估
2. **测试阶段**：使用完整的测试数据集进行评估
3. **生产阶段**：定期抽样评估，监控质量

### 5.4 结果分析

1. **趋势分析**：跟踪评分随时间的变化趋势
2. **对比分析**：对比不同版本的评分
3. **问题定位**：分析低分案例，找出共性问题
4. **优化方向**：基于评分数据确定优化方向

---

## 六、总结

### 6.1 核心要点

1. **评分规则制定**：
   - 明确评估目标
   - 定义评分维度
   - 制定评分标准
   - 创建 ScoreConfig

2. **参考案例评估**：
   - 引入参考案例（线上版本）作为评估标准
   - 使用多种方法计算相似度
   - 评估关键信息覆盖度
   - 评估风格一致性

3. **相似度计算方法**：
   - 基于 Embedding 的语义相似度
   - 基于字符串的相似度
   - 使用 LLM 进行多维度评估
   - 混合相似度计算

### 6.2 实施建议

1. **建立参考案例库**：从线上环境收集高质量的参考案例
2. **定义评分规则**：为每个评分维度制定明确的评分标准
3. **实现评估工具**：开发自动化的评估工具
4. **持续监控**：定期评估，跟踪评分趋势
5. **迭代优化**：基于评分数据持续优化

### 6.3 注意事项

1. **参考案例质量**：确保参考案例的质量和代表性
2. **评估成本**：LLM 评估需要额外成本，考虑采样率
3. **评估一致性**：确保评估结果在不同时间、不同评估者之间保持一致
4. **数据隐私**：注意参考案例中的数据隐私保护

---

## 参考资料

- **Langfuse Scores 文档**：https://langfuse.com/docs/scores
- **Langfuse Evaluation 文档**：https://langfuse.com/docs/evaluation
- **Sentence Transformers**：https://www.sbert.net/
- **项目中的评分功能**：`cursor_docs/011603-Langfuse评分功能使用指南.md`

---

*最后更新：2026-01-16*
