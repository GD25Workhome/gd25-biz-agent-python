# RAG集成方案分析报告

## 文档目的

本文档分析如何将提示词中的示例和场景定义提取为知识库，并通过RAG（检索增强生成）技术减少提示词长度，提升系统可维护性和扩展性。

## 一、可提取为知识库的内容分析

### 1.1 当前提示词结构分析

以 `medical_agent_v3` 流程为例，提示词文件主要包含以下部分：

#### 1.1.1 核心结构部分（应保留在提示词中）
- **角色定义**：Agent的身份和职责
- **核心原则**：安全边界、行为规范（通过 `{llm_rule_part}` 占位符注入）
- **上下文信息**：用户信息、历史数据（通过 `{llm_context_part}` 占位符注入）
- **工作流程**：Agent的执行步骤和逻辑
- **行为规则**：通用的行为指导原则

#### 1.1.2 可提取为知识库的内容（建议提取）

**1. 场景定义和回复话术（QA Agent）**
- **位置**：`50-QA_agent.md` 中的大量场景定义
- **内容类型**：
  - 场景匹配规则（如"诊疗相关"、"药物相关"、"危重症等紧急情况"）
  - 患者问题示例
  - 标准回复话术
  - 场景判断条件（如"胸痛"、"头痛"、"恶心呕吐"等详细判断规则）
- **提取理由**：
  - 内容量大（约400行）
  - 结构化程度高，易于向量化
  - 更新频率相对较低
  - 适合通过语义检索匹配

**2. Few-shot示例（After Record Agent）**
- **位置**：`12-after_record_agent.md` 第177行开始的示例部分
- **内容类型**：
  - 血压场景示例（单次数据点评、趋势点评、症状预警等）
  - 场景特征描述
  - 回复案例（期望的输出格式和风格）
- **提取理由**：
  - 示例数量多（20+个场景）
  - 每个示例包含场景特征和回复案例的对应关系
  - 可以通过场景特征检索匹配的示例
  - 减少提示词长度，提升可维护性

**3. 其他Agent的示例内容**
- **位置**：其他提示词文件中的示例部分
- **内容类型**：类似的结构化示例和场景定义

### 1.2 知识库内容分类建议

#### 分类1：场景匹配知识库（QA Agent）
```
知识条目结构：
{
  "category": "诊疗相关|药物相关|危重症等",
  "scene_name": "场景名称",
  "scene_conditions": "场景判断条件（结构化描述）",
  "patient_examples": ["患者问题示例1", "患者问题示例2"],
  "reply_template": "标准回复话术",
  "keywords": ["关键词1", "关键词2"],
  "priority": "high|medium|low"  // 紧急情况优先级高
}
```

#### 分类2：Few-shot示例知识库（After Record Agent）
```
知识条目结构：
{
  "agent_type": "after_record_agent",
  "scene_type": "单次血压数据点评|血压趋势点评|症状预警",
  "scene_features": "场景特征描述（如：90<=收缩压<=目标值）",
  "reply_example": "回复案例（期望的输出）",
  "scene_tags": ["达标", "轻度偏高", "重度偏高"],
  "data_conditions": "数据条件（如：BPM范围、血压范围）"
}
```

#### 分类3：通用回复风格示例
```
知识条目结构：
{
  "style_type": "鼓励性回复|预警性回复|澄清性回复",
  "context": "适用场景描述",
  "example": "示例回复",
  "style_notes": "风格要点说明"
}
```

### 1.3 提取优先级

| 优先级 | Agent | 内容类型 | 提取收益 | 实施难度 |
|--------|-------|----------|----------|----------|
| **P0** | QA Agent | 场景定义和回复话术 | ⭐⭐⭐⭐⭐ | 中 |
| **P0** | After Record Agent | Few-shot示例 | ⭐⭐⭐⭐⭐ | 中 |
| **P1** | 其他Agent | 示例内容 | ⭐⭐⭐ | 低 |
| **P2** | 所有Agent | 通用风格示例 | ⭐⭐ | 低 |

---

## 二、检索方案分析与LangGraph亲和度评估

### 2.1 方案一：前置RAG节点（推荐⭐⭐⭐⭐⭐）

#### 2.1.1 方案描述
在Agent节点执行前，添加一个RAG检索节点，从知识库中检索相关示例和场景，动态注入到提示词中。

#### 2.1.2 架构设计
```
流程结构：
intent_recognition → [RAG检索节点] → qa_agent
                              ↓
                        知识库检索
                              ↓
                        动态构建提示词
```

#### 2.1.3 实现方式
```python
# 在 flow.yaml 中添加RAG节点
nodes:
  - name: rag_retrieval
    type: rag_retrieval
    config:
      knowledge_base: "qa_scenarios"  # 知识库名称
      top_k: 3  # 检索Top-K条
      similarity_threshold: 0.7  # 相似度阈值

edges:
  - from: intent_recognition
    to: rag_retrieval
    condition: intent == "qa"
  
  - from: rag_retrieval
    to: qa_agent
    condition: always
```

#### 2.1.4 LangGraph亲和度评估
- **亲和度**: ⭐⭐⭐⭐⭐ (5/5)
- **优势**:
  - ✅ 完全符合LangGraph的节点-边架构
  - ✅ 可以无缝集成到现有流程中
  - ✅ 状态传递自然（通过FlowState）
  - ✅ 支持条件路由（根据检索结果决定是否使用）
  - ✅ 易于调试和监控（独立的节点）
- **实现要点**:
  - 在 `FlowState` 中添加 `retrieved_knowledge` 字段
  - RAG节点将检索结果写入状态
  - 提示词构建器从状态中读取并注入到提示词

#### 2.1.5 代码改造点
1. **新增RAG节点类型**（`backend/domain/flows/builder.py`）
2. **扩展FlowState**（添加 `retrieved_knowledge` 字段）
3. **修改提示词构建器**（支持动态注入检索结果）
4. **实现向量检索服务**（封装pgvector查询）

---

### 2.2 方案二：工具化RAG（推荐⭐⭐⭐⭐）

#### 2.2.1 方案描述
将RAG检索封装为LangChain工具，Agent在需要时主动调用检索工具。

#### 2.2.2 架构设计
```
Agent执行流程：
1. Agent接收用户问题
2. Agent调用 retrieve_knowledge 工具
3. 工具返回相关示例
4. Agent基于检索结果生成回复
```

#### 2.2.3 实现方式
```python
# 在Agent的tools中添加RAG工具
tools:
  - retrieve_knowledge  # RAG检索工具
  - record_blood_pressure
  - query_blood_pressure
```

#### 2.2.4 LangGraph亲和度评估
- **亲和度**: ⭐⭐⭐⭐ (4/5)
- **优势**:
  - ✅ 符合LangChain工具系统设计
  - ✅ Agent可以按需检索，更灵活
  - ✅ 工具调用结果会出现在消息历史中，可追溯
  - ✅ 无需修改流程结构
- **劣势**:
  - ⚠️ Agent可能忘记调用工具（需要提示词引导）
  - ⚠️ 每次调用都有工具调用开销
  - ⚠️ 检索结果可能不够及时（在Agent推理过程中）

#### 2.2.5 代码改造点
1. **实现RAG工具**（`backend/domain/tools/rag_retrieval.py`）
2. **注册到TOOL_REGISTRY**
3. **在Agent配置中添加工具**
4. **更新提示词**（引导Agent使用检索工具）

---

### 2.3 方案三：提示词动态构建时检索（推荐⭐⭐⭐⭐⭐）

#### 2.3.1 方案描述
在 `build_system_message` 函数中，根据当前上下文动态检索知识库，将检索结果作为占位符注入。

#### 2.3.2 架构设计
```
提示词构建流程：
1. build_system_message 被调用
2. 从 FlowState 提取用户问题和上下文
3. 调用向量检索服务
4. 将检索结果格式化为 {rag_examples} 占位符
5. 替换提示词模板中的占位符
```

#### 2.3.3 实现方式
```python
# 在 sys_prompt_builder.py 中
def build_system_message(...):
    # 1. 获取基础提示词模板
    template = prompt_manager.get_prompt_by_key(prompt_cache_key)
    
    # 2. 动态检索知识库
    user_query = state.get("current_message", "").content
    retrieved_knowledge = rag_service.retrieve(
        query=user_query,
        top_k=3,
        knowledge_base="qa_scenarios"
    )
    
    # 3. 格式化检索结果
    rag_content = format_retrieved_knowledge(retrieved_knowledge)
    
    # 4. 替换占位符
    system_prompt = template.replace("{rag_examples}", rag_content)
    
    return SystemMessage(content=system_prompt)
```

#### 2.3.4 LangGraph亲和度评估
- **亲和度**: ⭐⭐⭐⭐⭐ (5/5)
- **优势**:
  - ✅ **零流程改造**：无需修改flow.yaml
  - ✅ **透明集成**：对Agent完全透明
  - ✅ **按需检索**：每次Agent执行时自动检索
  - ✅ **易于缓存**：可以缓存检索结果
  - ✅ **灵活性高**：可以根据不同Agent使用不同知识库
- **劣势**:
  - ⚠️ 检索延迟会影响Agent响应时间（可通过异步优化）
  - ⚠️ 需要确保检索服务的高可用性

#### 2.3.5 代码改造点
1. **实现向量检索服务**（`backend/infrastructure/rag/vector_store.py`）
2. **修改 `build_system_message`**（添加检索逻辑）
3. **在提示词模板中添加 `{rag_examples}` 占位符**
4. **实现检索结果格式化函数**

---

### 2.4 方案四：混合方案（推荐⭐⭐⭐⭐⭐）

#### 2.4.1 方案描述
结合方案一和方案三：
- **方案一**用于需要大量检索的场景（如QA Agent）
- **方案三**用于轻量级检索的场景（如After Record Agent）

#### 2.4.2 架构设计
```
流程1（QA Agent - 使用前置RAG节点）：
intent_recognition → rag_retrieval → qa_agent

流程2（After Record Agent - 使用动态构建时检索）：
record_agent → after_record_agent (内部动态检索)
```

#### 2.4.3 LangGraph亲和度评估
- **亲和度**: ⭐⭐⭐⭐⭐ (5/5)
- **优势**:
  - ✅ 结合两种方案的优点
  - ✅ 根据场景选择最优方案
  - ✅ 灵活性和性能兼顾

---

## 三、RAG其他设计方式探讨

### 3.1 分层检索策略

#### 3.1.1 设计思路
根据用户问题的类型，使用不同的检索策略：
- **精确匹配**：关键词匹配（用于场景名称、标签）
- **语义检索**：向量相似度检索（用于问题理解）
- **混合检索**：结合关键词和语义检索

#### 3.1.2 实现示例
```python
def hybrid_retrieve(query: str, knowledge_base: str, top_k: int = 3):
    # 1. 关键词检索（快速过滤）
    keyword_results = keyword_search(query, knowledge_base, limit=top_k*2)
    
    # 2. 向量检索（语义匹配）
    vector_results = vector_search(query, knowledge_base, limit=top_k*2)
    
    # 3. 结果融合和去重
    merged_results = merge_and_deduplicate(keyword_results, vector_results)
    
    # 4. 重排序（结合相似度和关键词匹配度）
    reranked_results = rerank(merged_results, query)
    
    return reranked_results[:top_k]
```

### 3.2 上下文感知检索

#### 3.2.1 设计思路
不仅基于当前用户问题，还考虑：
- 用户历史对话上下文
- 用户的基础信息（疾病类型、用药情况等）
- 当前流程状态（如刚记录完血压，检索血压相关示例）

#### 3.2.2 实现示例
```python
def context_aware_retrieve(
    query: str,
    user_context: Dict,
    flow_state: FlowState,
    knowledge_base: str
):
    # 1. 构建增强查询（包含上下文信息）
    enhanced_query = f"""
    用户问题：{query}
    用户疾病类型：{user_context.get('disease_type')}
    当前流程：{flow_state.get('current_agent')}
    最近操作：{flow_state.get('last_action')}
    """
    
    # 2. 使用增强查询检索
    results = vector_search(enhanced_query, knowledge_base)
    
    # 3. 根据上下文过滤结果（如只返回相关疾病类型的示例）
    filtered_results = filter_by_context(results, user_context)
    
    return filtered_results
```

### 3.3 多知识库路由

#### 3.3.1 设计思路
根据Agent类型和用户意图，路由到不同的知识库：
- `qa_scenarios`：QA场景知识库
- `blood_pressure_examples`：血压点评示例知识库
- `reply_style_examples`：回复风格示例知识库

#### 3.3.2 实现示例
```python
def route_to_knowledge_base(agent_type: str, intent: str) -> str:
    """根据Agent类型和意图路由到对应知识库"""
    routing_map = {
        "qa_agent": "qa_scenarios",
        "after_record_agent": "blood_pressure_examples",
        "record_agent": "reply_style_examples",
    }
    
    # 可以根据intent进一步细分
    if agent_type == "qa_agent":
        if "紧急" in intent or "危重症" in intent:
            return "qa_emergency_scenarios"
        return "qa_scenarios"
    
    return routing_map.get(agent_type, "default_knowledge_base")
```

### 3.4 检索结果缓存策略

#### 3.4.1 设计思路
- **查询缓存**：相同查询直接返回缓存结果
- **用户会话缓存**：同一会话中的相似查询复用结果
- **时间窗口缓存**：短时间内相同查询使用缓存

#### 3.4.2 实现示例
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def cached_retrieve(query_hash: str, knowledge_base: str, top_k: int):
    """缓存检索结果"""
    # 实际检索逻辑
    pass

def retrieve_with_cache(query: str, knowledge_base: str, top_k: int):
    # 生成查询哈希
    query_hash = hashlib.md5(f"{query}_{knowledge_base}_{top_k}".encode()).hexdigest()
    
    # 检查缓存
    return cached_retrieve(query_hash, knowledge_base, top_k)
```

### 3.5 检索结果质量评估

#### 3.5.1 设计思路
对检索结果进行质量评估，如果质量不足，可以：
- 降低相似度阈值，扩大检索范围
- 使用备用检索策略
- 回退到不使用RAG的原始提示词

#### 3.5.2 实现示例
```python
def retrieve_with_quality_check(query: str, knowledge_base: str, top_k: int):
    results = vector_search(query, knowledge_base, top_k)
    
    # 质量评估
    max_similarity = max(r['similarity'] for r in results) if results else 0
    
    if max_similarity < 0.6:  # 质量阈值
        # 质量不足，尝试扩大检索范围
        expanded_results = vector_search(query, knowledge_base, top_k * 2)
        # 或者使用关键词检索作为补充
        keyword_results = keyword_search(query, knowledge_base, top_k)
        results = merge_results(expanded_results, keyword_results)
    
    return results[:top_k]
```

---

## 四、推荐实施方案

### 4.1 阶段一：MVP实现（推荐方案三）

**目标**：快速验证RAG效果，最小化代码改造

**实施步骤**：
1. ✅ 实现向量检索服务（基于pgvector）
2. ✅ 实现知识库数据模型和导入脚本
3. ✅ 修改 `build_system_message` 支持动态检索
4. ✅ 在 `12-after_record_agent.md` 和 `50-QA_agent.md` 中添加 `{rag_examples}` 占位符
5. ✅ 提取Few-shot示例到知识库
6. ✅ 测试和优化

**优势**：
- 零流程改造
- 快速上线
- 易于回滚

### 4.2 阶段二：优化和扩展（推荐混合方案）

**目标**：根据阶段一的效果，优化检索策略，扩展到更多Agent

**实施步骤**：
1. 分析阶段一的检索效果和性能
2. 实现分层检索策略（关键词+向量）
3. 实现上下文感知检索
4. 对于QA Agent，考虑使用前置RAG节点（方案一）
5. 实现检索结果缓存
6. 扩展到其他Agent

### 4.3 阶段三：高级特性

**目标**：实现高级RAG特性，提升系统智能化

**实施步骤**：
1. 实现多知识库路由
2. 实现检索结果质量评估和自适应调整
3. 实现用户反馈学习（根据用户满意度调整检索策略）
4. 实现知识库自动更新机制

---

## 五、技术实现要点

### 5.1 向量存储设计

#### 5.1.1 数据库表结构
```sql
CREATE TABLE knowledge_base (
    id SERIAL PRIMARY KEY,
    agent_type VARCHAR(50) NOT NULL,  -- qa_agent, after_record_agent等
    category VARCHAR(100),  -- 场景分类
    scene_name VARCHAR(200),  -- 场景名称
    scene_conditions TEXT,  -- 场景条件描述
    patient_examples TEXT[],  -- 患者问题示例数组
    reply_template TEXT,  -- 回复话术模板
    keywords TEXT[],  -- 关键词数组
    embedding vector(768),  -- 向量（moka-ai/m3e-base输出768维）
    metadata JSONB,  -- 其他元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建向量索引（HNSW）
CREATE INDEX ON knowledge_base USING hnsw (embedding vector_cosine_ops);
```

#### 5.1.2 向量化策略
- **查询向量化**：用户问题 → embedding模型 → 768维向量
- **知识条目向量化**：场景描述 + 患者示例 + 回复模板 → embedding模型 → 768维向量
- **混合向量化**：可以分别为场景描述、示例、回复模板生成向量，检索时融合

### 5.2 检索服务实现

#### 5.2.1 核心接口
```python
class VectorRetrievalService:
    async def retrieve(
        self,
        query: str,
        knowledge_base: str,
        top_k: int = 3,
        similarity_threshold: float = 0.7,
        agent_type: Optional[str] = None
    ) -> List[Dict]:
        """
        检索相关知识条目
        
        Returns:
            List[Dict]: 检索结果，包含：
                - scene_name: 场景名称
                - scene_conditions: 场景条件
                - reply_template: 回复模板
                - similarity: 相似度分数
        """
        pass
```

### 5.3 提示词改造

#### 5.3.1 占位符设计
```markdown
# 在提示词模板中添加：

# 检索增强示例（动态注入）
{rag_examples}

# 如果检索结果为空，显示：
# 注：未找到相关示例，请根据上述规则生成回复。
```

#### 5.3.2 格式化函数
```python
def format_retrieved_knowledge(results: List[Dict]) -> str:
    """将检索结果格式化为提示词内容"""
    if not results:
        return "# 检索增强示例\n\n注：未找到相关示例，请根据上述规则生成回复。\n"
    
    formatted = "# 检索增强示例（Few-shot Learning）\n\n"
    
    for i, result in enumerate(results, 1):
        formatted += f"## 示例 {i}（相似度：{result['similarity']:.2f}）\n\n"
        formatted += f"**场景**：{result['scene_name']}\n\n"
        formatted += f"**场景条件**：{result['scene_conditions']}\n\n"
        formatted += f"**患者问题示例**：\n"
        for example in result['patient_examples']:
            formatted += f"- {example}\n"
        formatted += f"\n**回复话术**：{result['reply_template']}\n\n"
        formatted += "---\n\n"
    
    return formatted
```

---

## 六、预期效果

### 6.1 提示词长度减少

| Agent | 当前长度 | 预期减少 | 减少比例 |
|-------|----------|----------|----------|
| QA Agent | ~400行 | ~200行 | 50% |
| After Record Agent | ~400行 | ~150行 | 37.5% |
| 其他Agent | 变化 | ~30% | 30% |

### 6.2 可维护性提升

- ✅ **知识库独立管理**：场景和示例可以独立更新，无需修改提示词文件
- ✅ **版本控制友好**：知识库变更可以单独版本管理
- ✅ **A/B测试支持**：可以轻松测试不同示例的效果

### 6.3 扩展性提升

- ✅ **新场景快速添加**：只需向知识库添加条目，无需修改提示词
- ✅ **多语言支持**：可以为不同语言维护独立知识库
- ✅ **个性化支持**：可以根据用户特征检索个性化示例

---

## 七、风险评估与应对

### 7.1 技术风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 检索延迟影响响应时间 | 中 | 1. 使用异步检索 2. 实现缓存 3. 设置超时机制 |
| 检索结果质量不稳定 | 高 | 1. 设置相似度阈值 2. 实现质量评估 3. 提供回退机制 |
| 向量数据库性能问题 | 中 | 1. 创建合适的索引 2. 优化查询语句 3. 考虑分库分表 |

### 7.2 业务风险

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 检索到错误示例 | 高 | 1. 严格的质量审核 2. 人工审核机制 3. 监控和告警 |
| 知识库更新不及时 | 中 | 1. 建立更新流程 2. 版本管理 3. 快速回滚机制 |

---

## 八、总结

### 8.1 核心建议

1. **优先提取内容**：
   - QA Agent的场景定义和回复话术（P0）
   - After Record Agent的Few-shot示例（P0）

2. **推荐实施方案**：
   - **阶段一**：使用方案三（动态构建时检索），快速验证
   - **阶段二**：根据效果优化，考虑混合方案

3. **技术选型**：
   - 向量数据库：PostgreSQL + pgvector（已具备）
   - Embedding模型：moka-ai/m3e-base（已具备）
   - 检索策略：语义检索 + 关键词检索（混合）

### 8.2 下一步行动

1. ✅ 完成环境检查（已完成）
2. ⏳ 设计知识库数据模型
3. ⏳ 实现向量检索服务
4. ⏳ 实现知识库导入脚本
5. ⏳ 修改提示词构建器支持RAG
6. ⏳ 提取示例到知识库
7. ⏳ 测试和优化

---

**文档生成时间**: 2025-01-XX  
**分析人员**: AI Assistant  
**文档版本**: v1.0
