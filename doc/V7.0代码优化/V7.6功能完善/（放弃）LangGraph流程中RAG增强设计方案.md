# LangGraph流程中RAG增强设计方案（V7.6）

## 一、背景与需求

### 1.1 需求描述

在LangGraph流程中集成RAG（检索增强生成）功能，实现以下流程：

1. **RAG数据查询阶段**：在流程中插入RAG检索节点，查询各种数据源（向量数据库、知识库等）
2. **数据组装阶段**：将查询到的数据组装到流程状态中，供后续节点使用
3. **模型处理阶段**：将查询到的数据交给模型进行处理和分析
4. **结果路由阶段**：根据模型返回的结果，通过条件边路由到不同的下级节点
5. **分支处理阶段**：下级节点根据模型返回的情况，进行条件选择，执行不同的后续操作

### 1.2 核心目标

- ✅ 将RAG检索作为流程中的独立节点，支持在流程配置中灵活插入
- ✅ 支持多种数据源查询（向量数据库、关系数据库、外部API等）
- ✅ 查询结果自动组装到流程状态中，供后续节点使用
- ✅ 模型节点可以基于RAG查询结果进行推理和决策
- ✅ 支持基于模型返回结果的条件路由，实现动态分支选择
- ✅ 保持与现有流程系统的兼容性，不破坏现有功能

### 1.3 使用场景

**场景1：医疗知识问答流程**
```
用户问题 → RAG检索（医学知识库） → 模型分析（结合检索结果） → 根据分析结果路由
  ├─ 需要进一步检查 → 检查建议节点
  ├─ 需要用药建议 → 用药建议节点
  └─ 可以直接回答 → 直接回答节点
```

**场景2：多数据源综合查询流程**
```
用户查询 → RAG检索（向量库） → 数据库查询（关系库） → 模型综合分析 → 路由决策
  ├─ 数据充足 → 生成完整报告
  ├─ 数据不足 → 请求补充信息
  └─ 数据异常 → 人工审核节点
```

**场景3：动态知识更新流程**
```
用户问题 → RAG检索（最新知识） → 模型对比分析 → 路由判断
  ├─ 知识已更新 → 更新建议节点
  ├─ 知识未变化 → 标准回答节点
  └─ 需要验证 → 验证节点
```

## 二、技术分析

### 2.1 当前架构分析

#### 2.1.1 流程构建机制

当前系统通过 `GraphBuilder` 构建LangGraph流程：

```python
# backend/domain/flows/builder.py
class GraphBuilder:
    @staticmethod
    def build_graph(flow_def: FlowDefinition) -> StateGraph:
        graph = StateGraph(FlowState)
        
        # 为每个节点创建节点函数
        for node_def in flow_def.nodes:
            node_func = GraphBuilder._create_node_function(node_def, flow_def)
            graph.add_node(node_def.name, node_func)
        
        # 添加边（条件边和普通边）
        # ...
```

**当前支持的节点类型**：
- ✅ `agent`：Agent节点，执行LLM推理和工具调用

**需要扩展的节点类型**：
- ⏳ `rag`：RAG检索节点，执行数据查询
- ⏳ `data_query`：通用数据查询节点（可选，用于非向量数据查询）

#### 2.1.2 流程状态结构

```python
# backend/domain/state.py
class FlowState(TypedDict, total=False):
    current_message: HumanMessage
    history_messages: List[BaseMessage]
    flow_msgs: List[BaseMessage]
    session_id: str
    intent: Optional[str]
    confidence: Optional[float]
    need_clarification: Optional[bool]
    token_id: Optional[str]
    trace_id: Optional[str]
    prompt_vars: Optional[Dict[str, Any]]  # 提示词变量
    edges_var: Optional[Dict[str, Any]]  # 边条件判断变量
```

**需要扩展的状态字段**：
- ⏳ `rag_results: Optional[Dict[str, Any]]`：RAG查询结果
- ⏳ `query_context: Optional[Dict[str, Any]]`：查询上下文信息

#### 2.1.3 条件路由机制

当前系统支持基于 `edges_var` 的条件路由：

```python
# 条件边示例
edges:
  - from: model_agent
    to: branch_a
    condition: analysis_result == "sufficient" && confidence >= 0.8
  - from: model_agent
    to: branch_b
    condition: analysis_result == "insufficient"
```

**优势**：
- ✅ 支持复杂的条件表达式（&&, ||, ==, !=, <, >, >=, <=）
- ✅ 条件变量自动从Agent节点的输出中提取
- ✅ 支持JSON格式的输出解析

### 2.2 RAG集成方案对比

#### 方案一：RAG作为工具（已规划，不满足当前需求）

**实现方式**：
- RAG作为Agent的工具，由Agent主动调用
- 在 `flow.yaml` 中为Agent配置RAG工具

**优点**：
- ✅ 实现简单，复用现有工具机制
- ✅ Agent可以灵活决定何时使用RAG

**缺点**：
- ❌ 无法在流程层面控制RAG的执行时机
- ❌ 无法在RAG查询后、模型处理前进行数据预处理
- ❌ 不满足"查询数据 → 交给模型 → 路由决策"的流程需求

#### 方案二：RAG作为独立节点（推荐方案）⭐

**实现方式**：
- RAG作为流程中的独立节点类型
- 在 `flow.yaml` 中定义RAG节点，通过边连接到模型节点
- RAG节点查询数据，将结果存储到 `state.rag_results`
- 模型节点从 `state.rag_results` 读取数据，进行处理
- 模型节点输出结果，通过条件边路由到下级节点

**优点**：
- ✅ 完全满足需求：查询 → 模型 → 路由的流程
- ✅ 流程层面可控，可以在配置中灵活插入RAG节点
- ✅ 支持多阶段RAG查询（多个RAG节点串联）
- ✅ 支持RAG结果的数据预处理和转换
- ✅ 与现有流程系统完美集成

**缺点**：
- ⚠️ 需要扩展 `GraphBuilder` 支持新节点类型
- ⚠️ 需要实现RAG节点的基础设施（向量数据库、检索器等）

**推荐**：采用方案二（RAG作为独立节点）

## 三、设计方案

### 3.1 整体架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph流程层                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  [入口节点] → [RAG检索节点] → [模型分析节点] → [条件路由]    │
│      │              │                │              │         │
│      │              │                │              ├─→ [分支A]│
│      │              │                │              ├─→ [分支B]│
│      │              │                │              └─→ [分支C]│
│      │              │                │                         │
│      │              ▼                │                         │
│      │      [查询向量库]             │                         │
│      │      [查询关系库]             │                         │
│      │      [查询外部API]            │                         │
│      │              │                │                         │
│      │              ▼                │                         │
│      │      state.rag_results        │                         │
│      │              │                │                         │
│      │              └───────────────►│                         │
│      │                   读取数据    │                         │
│      │                              │                         │
│      │                              ▼                         │
│      │                    state.edges_var                    │
│      │                    (模型输出结果)                      │
│      │                              │                         │
│      └──────────────────────────────┴─────────────────────────┘
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    RAG基础设施层                              │
├─────────────────────────────────────────────────────────────┤
│  - 向量数据库（PgVector/FAISS/Chroma）                       │
│  - Embedding模型（BGE/Qwen Embedding）                       │
│  - 检索器（Retriever）                                       │
│  - 数据源适配器（向量库/关系库/API）                         │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 RAG节点设计

#### 3.2.1 节点配置结构

在 `flow.yaml` 中定义RAG节点：

```yaml
nodes:
  # RAG检索节点
  - name: rag_retrieval
    type: rag  # 新节点类型
    config:
      # 数据源配置
      data_sources:
        - type: vector_store  # 向量数据库
          name: medical_knowledge_base
          collection: medical_docs
          top_k: 5
          similarity_threshold: 0.7
        - type: database  # 关系数据库
          name: patient_records
          query_template: |
            SELECT * FROM patients 
            WHERE user_id = {user_id} 
            AND created_at > {date_range}
        - type: api  # 外部API
          name: external_service
          endpoint: https://api.example.com/search
          params:
            query: "{user_query}"
      
      # 查询策略
      query_strategy: parallel  # parallel（并行）或 sequential（串行）
      
      # 结果处理
      result_format: structured  # structured（结构化）或 raw（原始）
      merge_strategy: append  # append（追加）或 replace（替换）
      
      # 结果存储字段
      result_key: rag_results  # 存储到 state.rag_results
```

#### 3.2.2 节点实现逻辑

```python
# backend/domain/flows/builder.py (扩展)

@staticmethod
def _create_node_function(node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
    """创建节点函数"""
    
    if node_def.type == "rag":
        # RAG节点
        from backend.domain.flows.definition import RAGNodeConfig
        from backend.domain.flows.rag_node import create_rag_node
        
        config_dict = node_def.config
        rag_config = RAGNodeConfig(**config_dict)
        
        # 创建RAG节点函数
        return create_rag_node(rag_config, node_def.name)
    
    elif node_def.type == "agent":
        # Agent节点（现有逻辑）
        # ...
```

#### 3.2.3 RAG节点执行流程

```python
# backend/domain/flows/rag_node.py (新建)

async def create_rag_node(config: RAGNodeConfig, node_name: str) -> Callable:
    """创建RAG检索节点"""
    
    async def rag_node_action(state: FlowState) -> FlowState:
        """RAG节点执行函数"""
        logger.info(f"[RAG节点 {node_name}] 开始执行RAG检索")
        
        # 1. 提取查询内容
        query_text = _extract_query_text(state)
        
        # 2. 执行多数据源查询
        rag_results = {}
        
        if config.query_strategy == "parallel":
            # 并行查询
            tasks = []
            for data_source in config.data_sources:
                task = _query_data_source(data_source, query_text, state)
                tasks.append(task)
            results = await asyncio.gather(*tasks)
            
            for i, result in enumerate(results):
                source_name = config.data_sources[i].name
                rag_results[source_name] = result
        else:
            # 串行查询
            for data_source in config.data_sources:
                result = await _query_data_source(data_source, query_text, state)
                rag_results[data_source.name] = result
        
        # 3. 结果处理和格式化
        formatted_results = _format_results(rag_results, config.result_format)
        
        # 4. 更新状态
        new_state = state.copy()
        
        # 存储到指定字段
        result_key = config.result_key or "rag_results"
        if config.merge_strategy == "append":
            existing_results = new_state.get(result_key, {})
            existing_results.update(formatted_results)
            new_state[result_key] = existing_results
        else:
            new_state[result_key] = formatted_results
        
        # 5. 记录查询上下文（供后续节点使用）
        new_state["query_context"] = {
            "query_text": query_text,
            "query_time": datetime.now().isoformat(),
            "data_sources": [ds.name for ds in config.data_sources],
            "result_count": sum(len(r) if isinstance(r, list) else 1 for r in formatted_results.values())
        }
        
        logger.info(f"[RAG节点 {node_name}] RAG检索完成，结果数量: {new_state['query_context']['result_count']}")
        
        return new_state
    
    return rag_node_action
```

### 3.3 模型节点增强

#### 3.3.1 读取RAG结果

模型节点需要能够读取RAG查询结果，并在提示词中使用：

```python
# backend/domain/flows/builder.py (修改agent节点)

async def agent_node_action(state: FlowState) -> FlowState:
    """Agent节点函数"""
    
    # 构建系统消息（自动替换占位符）
    sys_msg = build_system_message(
        prompt_cache_key=agent_executor.prompt_cache_key,
        state=state
    )
    
    # 如果state中包含RAG结果，自动注入到提示词变量中
    if "rag_results" in state:
        # 将RAG结果格式化为文本，供提示词使用
        rag_context = _format_rag_results_for_prompt(state["rag_results"])
        state["prompt_vars"] = state.get("prompt_vars", {})
        state["prompt_vars"]["rag_context"] = rag_context
    
    # 执行Agent...
```

#### 3.3.2 提示词模板支持

在Agent的提示词模板中，可以使用RAG上下文：

```markdown
# prompts/50-QA_agent.md

你是一个医疗问答助手。请基于以下知识库内容回答用户问题。

## 知识库内容

{rag_context}

## 用户问题

{user_query}

请基于知识库内容，给出准确、专业的回答。
```

### 3.4 条件路由设计

#### 3.4.1 模型输出结果提取

模型节点执行后，将结果存储到 `state.edges_var`，供条件路由使用：

```python
# backend/domain/flows/builder.py (现有逻辑)

# Agent执行后，从输出中提取数据到 edges_var
if isinstance(output, str):
    # 解析JSON输出
    output_data = json.loads(output)
    
    # 存储到 edges_var（用于条件路由）
    for key, value in output_data.items():
        if key not in ["response_content", "reasoning_summary"]:
            new_state["edges_var"][key] = value
```

#### 3.4.2 条件路由配置

在 `flow.yaml` 中配置基于模型结果的条件路由：

```yaml
edges:
  # RAG检索 → 模型分析
  - from: rag_retrieval
    to: model_analysis
    condition: always
  
  # 模型分析 → 条件路由
  - from: model_analysis
    to: branch_sufficient
    condition: analysis_result == "sufficient" && confidence >= 0.8
  
  - from: model_analysis
    to: branch_insufficient
    condition: analysis_result == "insufficient" || confidence < 0.6
  
  - from: model_analysis
    to: branch_need_verification
    condition: analysis_result == "need_verification" && data_quality == "low"
  
  # 分支节点 → 后续处理
  - from: branch_sufficient
    to: generate_report
    condition: always
  
  - from: branch_insufficient
    to: request_additional_info
    condition: always
  
  - from: branch_need_verification
    to: human_review
    condition: always
```

#### 3.4.3 模型输出格式规范

为了支持条件路由，模型节点的输出需要遵循特定格式：

```json
{
  "response_content": "用户的回答内容...",
  "analysis_result": "sufficient|insufficient|need_verification",
  "confidence": 0.85,
  "data_quality": "high|medium|low",
  "reasoning_summary": "分析过程摘要...",
  "additional_fields": {
    "suggested_actions": ["action1", "action2"],
    "risk_level": "low"
  }
}
```

**字段说明**：
- `response_content`：给用户的回答内容（不用于路由）
- `analysis_result`：分析结果（用于路由判断）
- `confidence`：置信度（用于路由判断）
- `data_quality`：数据质量评估（用于路由判断）
- `reasoning_summary`：推理过程摘要（不用于路由）
- `additional_fields`：其他自定义字段（自动提取到 `edges_var`）

### 3.5 状态结构扩展

#### 3.5.1 FlowState扩展

```python
# backend/domain/state.py (扩展)

class FlowState(TypedDict, total=False):
    # 现有字段...
    current_message: HumanMessage
    history_messages: List[BaseMessage]
    flow_msgs: List[BaseMessage]
    session_id: str
    intent: Optional[str]
    confidence: Optional[float]
    need_clarification: Optional[bool]
    token_id: Optional[str]
    trace_id: Optional[str]
    prompt_vars: Optional[Dict[str, Any]]
    edges_var: Optional[Dict[str, Any]]
    
    # 新增字段
    rag_results: Optional[Dict[str, Any]]  # RAG查询结果
    query_context: Optional[Dict[str, Any]]  # 查询上下文信息
```

#### 3.5.2 RAG结果数据结构

```python
# RAG结果结构示例
rag_results = {
    "medical_knowledge_base": [
        {
            "content": "文档内容...",
            "score": 0.85,
            "metadata": {
                "source": "medical_guide_2024.pdf",
                "page": 42,
                "section": "高血压治疗"
            }
        },
        # ...
    ],
    "patient_records": [
        {
            "patient_id": "12345",
            "diagnosis": "高血压",
            "medications": ["药物A", "药物B"],
            "last_visit": "2024-01-15"
        }
    ],
    "external_service": {
        "status": "success",
        "data": {
            "latest_guidelines": "...",
            "update_date": "2024-01-20"
        }
    }
}
```

## 四、实现方案

### 4.1 实现步骤

#### 阶段一：基础设施准备（1-2周）

1. **RAG基础设施模块**
   - 创建 `backend/infrastructure/rag/` 目录
   - 实现向量数据库连接（PgVector）
   - 实现Embedding模型客户端
   - 实现检索器（Retriever）

2. **数据源适配器**
   - 向量数据库适配器
   - 关系数据库适配器
   - 外部API适配器

#### 阶段二：RAG节点实现（1-2周）

1. **节点类型扩展**
   - 扩展 `NodeDefinition` 支持 `rag` 类型
   - 扩展 `GraphBuilder._create_node_function` 支持RAG节点
   - 实现 `create_rag_node` 函数

2. **状态结构扩展**
   - 扩展 `FlowState` 添加 `rag_results` 和 `query_context`
   - 更新类型定义

3. **配置结构定义**
   - 定义 `RAGNodeConfig` 类
   - 支持多数据源配置
   - 支持查询策略配置

#### 阶段三：模型节点增强（1周）

1. **RAG结果注入**
   - 修改Agent节点，自动读取 `rag_results`
   - 将RAG结果格式化为提示词变量
   - 更新提示词构建逻辑

2. **提示词模板支持**
   - 在提示词模板中添加 `{rag_context}` 占位符
   - 实现RAG结果格式化函数

#### 阶段四：条件路由增强（1周）

1. **路由逻辑验证**
   - 验证现有条件路由机制是否满足需求
   - 测试基于模型输出的条件路由

2. **输出格式规范**
   - 定义模型输出格式规范
   - 更新Agent提示词，引导模型输出规范格式

#### 阶段五：测试与优化（1-2周）

1. **单元测试**
   - RAG节点单元测试
   - 数据源适配器测试
   - 条件路由测试

2. **集成测试**
   - 完整流程测试（RAG → 模型 → 路由）
   - 多数据源查询测试
   - 条件分支测试

3. **性能优化**
   - 并行查询优化
   - 结果缓存机制
   - 查询超时处理

### 4.2 代码结构

```
backend/
├── domain/
│   ├── flows/
│   │   ├── builder.py          # 扩展：支持rag节点类型
│   │   ├── definition.py        # 扩展：RAGNodeConfig定义
│   │   ├── rag_node.py          # 新建：RAG节点实现
│   │   └── rag_formatter.py     # 新建：RAG结果格式化
│   └── state.py                 # 扩展：FlowState添加rag相关字段
│
├── infrastructure/
│   └── rag/                     # 新建：RAG基础设施
│       ├── __init__.py
│       ├── embeddings.py        # Embedding模型客户端
│       ├── vector_store.py       # 向量数据库接口
│       ├── retriever.py         # 检索器实现
│       └── adapters/            # 数据源适配器
│           ├── vector_adapter.py
│           ├── database_adapter.py
│           └── api_adapter.py
│
config/
└── flows/
    └── medical_agent_v4/        # 示例流程
        ├── flow.yaml            # 包含RAG节点配置
        └── prompts/
            └── 50-QA_agent.md   # 包含{rag_context}占位符
```

### 4.3 配置示例

#### 4.3.1 完整流程配置示例

```yaml
# config/flows/medical_agent_v4/flow.yaml

name: medical_agent_v4
version: "4.0"
description: "医疗Agent流程V4 - 支持RAG增强"

nodes:
  # 意图识别
  - name: intent_recognition
    type: agent
    config:
      prompt: prompts/00-intent_recognition_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
        thinking:
          type: disabled

  # RAG检索节点
  - name: rag_retrieval
    type: rag
    config:
      data_sources:
        - type: vector_store
          name: medical_knowledge_base
          collection: medical_docs
          top_k: 5
          similarity_threshold: 0.7
        - type: database
          name: patient_records
          query_template: |
            SELECT diagnosis, medications, last_visit 
            FROM patients 
            WHERE user_id = {token_id}
            ORDER BY last_visit DESC 
            LIMIT 10
      query_strategy: parallel
      result_format: structured
      merge_strategy: append
      result_key: rag_results

  # 模型分析节点
  - name: model_analysis
    type: agent
    config:
      prompt: prompts/50-QA_agent.md  # 包含{rag_context}占位符
      model:
        provider: doubao
        name: doubao-seed-1-8-251228
        temperature: 0.7
        thinking:
          type: enabled
        reasoning_effort: high
        timeout: 1800
      tools:
        - query_blood_pressure

  # 分支节点：数据充足
  - name: branch_sufficient
    type: agent
    config:
      prompt: prompts/60-generate_report_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-8-251228
        temperature: 0.7
        thinking:
          type: enabled
        reasoning_effort: medium

  # 分支节点：数据不足
  - name: branch_insufficient
    type: agent
    config:
      prompt: prompts/70-request_info_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
        thinking:
          type: disabled

  # 分支节点：需要验证
  - name: branch_need_verification
    type: agent
    config:
      prompt: prompts/80-verification_agent.md
      model:
        provider: doubao
        name: doubao-seed-1-6-251015
        temperature: 0.7
        thinking:
          type: disabled

edges:
  # 意图识别 → RAG检索
  - from: intent_recognition
    to: rag_retrieval
    condition: intent == "qa" && confidence >= 0.8

  # RAG检索 → 模型分析
  - from: rag_retrieval
    to: model_analysis
    condition: always

  # 模型分析 → 条件路由
  - from: model_analysis
    to: branch_sufficient
    condition: analysis_result == "sufficient" && confidence >= 0.8

  - from: model_analysis
    to: branch_insufficient
    condition: analysis_result == "insufficient" || confidence < 0.6

  - from: model_analysis
    to: branch_need_verification
    condition: analysis_result == "need_verification" && data_quality == "low"

  # 分支节点 → 结束
  - from: branch_sufficient
    to: END
    condition: always

  - from: branch_insufficient
    to: END
    condition: always

  - from: branch_need_verification
    to: END
    condition: always

entry_node: intent_recognition
```

#### 4.3.2 提示词模板示例

```markdown
# prompts/50-QA_agent.md

你是一个专业的医疗问答助手。请基于以下知识库内容和患者历史记录，分析用户问题并给出专业建议。

## 知识库内容

{rag_context}

## 分析任务

请分析用户问题，并输出以下格式的JSON结果：

```json
{
  "response_content": "给用户的回答内容",
  "analysis_result": "sufficient|insufficient|need_verification",
  "confidence": 0.0-1.0,
  "data_quality": "high|medium|low",
  "reasoning_summary": "分析过程摘要",
  "additional_fields": {
    "suggested_actions": ["建议的操作"],
    "risk_level": "low|medium|high"
  }
}
```

**字段说明**：
- `analysis_result`: 
  - `sufficient`: 数据充足，可以给出完整回答
  - `insufficient`: 数据不足，需要补充信息
  - `need_verification`: 需要进一步验证
- `confidence`: 回答的置信度（0.0-1.0）
- `data_quality`: 数据质量评估

## 用户问题

{user_query}
```

## 五、关键技术点

### 5.1 多数据源查询策略

#### 5.1.1 并行查询

```python
# 并行查询实现
async def _query_parallel(data_sources, query_text, state):
    tasks = []
    for data_source in data_sources:
        task = _query_data_source(data_source, query_text, state)
        tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理异常
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"数据源 {data_sources[i].name} 查询失败: {result}")
            results[i] = None
    
    return results
```

#### 5.1.2 串行查询

```python
# 串行查询实现（支持依赖关系）
async def _query_sequential(data_sources, query_text, state):
    results = {}
    for data_source in data_sources:
        # 检查依赖
        if data_source.depends_on:
            if data_source.depends_on not in results:
                raise ValueError(f"数据源 {data_source.name} 依赖 {data_source.depends_on} 未查询")
            # 将依赖结果作为参数
            result = await _query_data_source(
                data_source, 
                query_text, 
                state,
                context=results[data_source.depends_on]
            )
        else:
            result = await _query_data_source(data_source, query_text, state)
        results[data_source.name] = result
    return results
```

### 5.2 RAG结果格式化

#### 5.2.1 结构化格式化

```python
def _format_rag_results_for_prompt(rag_results: Dict[str, Any]) -> str:
    """将RAG结果格式化为提示词可用的文本"""
    formatted_parts = []
    
    for source_name, results in rag_results.items():
        formatted_parts.append(f"## {source_name}\n")
        
        if isinstance(results, list):
            for i, item in enumerate(results, 1):
                if isinstance(item, dict):
                    content = item.get("content", str(item))
                    score = item.get("score", "")
                    metadata = item.get("metadata", {})
                    
                    formatted_parts.append(f"### 结果 {i}\n")
                    formatted_parts.append(f"内容: {content}\n")
                    if score:
                        formatted_parts.append(f"相似度: {score}\n")
                    if metadata:
                        formatted_parts.append(f"来源: {metadata}\n")
                    formatted_parts.append("\n")
        else:
            formatted_parts.append(f"{results}\n\n")
    
    return "\n".join(formatted_parts)
```

### 5.3 条件路由增强

#### 5.3.1 复杂条件支持

当前 `ConditionEvaluator` 已支持复杂条件表达式：

```python
# 支持的条件表达式示例
condition: analysis_result == "sufficient" && confidence >= 0.8
condition: analysis_result == "insufficient" || confidence < 0.6
condition: (analysis_result == "need_verification" && data_quality == "low") || risk_level == "high"
```

#### 5.3.2 条件变量提取

模型输出自动提取到 `edges_var`：

```python
# 模型输出JSON
{
  "analysis_result": "sufficient",
  "confidence": 0.85,
  "data_quality": "high",
  "additional_fields": {
    "risk_level": "low"
  }
}

# 自动提取到 edges_var
edges_var = {
  "analysis_result": "sufficient",
  "confidence": 0.85,
  "data_quality": "high",
  "risk_level": "low"  # 从 additional_fields 中提取
}
```

## 六、实施计划

### 6.1 开发优先级

**P0（必须实现）**：
1. RAG节点基础实现（支持向量数据库查询）
2. 状态结构扩展（rag_results字段）
3. 模型节点RAG结果读取和注入
4. 条件路由验证（基于模型输出）

**P1（重要功能）**：
1. 多数据源支持（关系数据库、外部API）
2. 并行查询策略
3. RAG结果格式化
4. 提示词模板占位符支持

**P2（优化功能）**：
1. 查询结果缓存
2. 查询超时处理
3. 错误处理和重试机制
4. 性能监控和日志

### 6.2 里程碑

**Milestone 1：基础RAG节点（2周）**
- ✅ RAG基础设施模块
- ✅ RAG节点类型实现
- ✅ 向量数据库查询
- ✅ 状态结构扩展

**Milestone 2：模型集成（1周）**
- ✅ 模型节点RAG结果读取
- ✅ 提示词变量注入
- ✅ 提示词模板支持

**Milestone 3：条件路由（1周）**
- ✅ 模型输出格式规范
- ✅ 条件路由测试
- ✅ 多分支流程测试

**Milestone 4：多数据源支持（1-2周）**
- ✅ 关系数据库适配器
- ✅ 外部API适配器
- ✅ 并行查询策略

**Milestone 5：优化与测试（1-2周）**
- ✅ 性能优化
- ✅ 错误处理
- ✅ 完整集成测试

## 七、风险评估与应对

### 7.1 技术风险

**风险1：RAG查询性能问题**
- **影响**：查询延迟高，影响用户体验
- **应对**：
  - 实现查询结果缓存
  - 支持并行查询
  - 设置查询超时
  - 优化向量数据库索引

**风险2：多数据源查询失败**
- **影响**：部分数据源失败导致整个流程失败
- **应对**：
  - 实现异常处理和降级策略
  - 支持部分失败（部分数据源失败不影响其他）
  - 记录详细错误日志

**风险3：RAG结果过大**
- **影响**：提示词过长，超出模型上下文限制
- **应对**：
  - 实现结果截断和摘要
  - 支持top_k限制
  - 实现结果压缩算法

### 7.2 兼容性风险

**风险1：现有流程兼容性**
- **影响**：新功能影响现有流程
- **应对**：
  - RAG节点为可选功能，不影响现有流程
  - 保持向后兼容
  - 充分测试现有流程

**风险2：状态结构变更**
- **影响**：状态结构变更可能导致现有流程失败
- **应对**：
  - 使用 `total=False` 的TypedDict，新字段为可选
  - 保持现有字段不变
  - 提供迁移指南

## 八、总结

### 8.1 方案优势

1. **流程层面可控**：RAG作为独立节点，可以在流程配置中灵活插入
2. **多数据源支持**：支持向量数据库、关系数据库、外部API等多种数据源
3. **灵活的路由机制**：基于模型输出的条件路由，支持复杂的业务逻辑
4. **向后兼容**：不影响现有流程，新功能为可选
5. **可扩展性强**：易于添加新的数据源类型和查询策略

### 8.2 关键技术点

1. **RAG节点设计**：独立节点类型，支持多数据源查询
2. **状态管理**：扩展FlowState，支持RAG结果存储
3. **模型集成**：自动读取RAG结果，注入到提示词
4. **条件路由**：基于模型输出的动态路由决策
5. **多分支处理**：支持根据模型结果选择不同的处理分支

### 8.3 下一步行动

1. **评审方案**：与团队评审设计方案，确认技术路线
2. **基础设施准备**：开始RAG基础设施模块开发
3. **节点实现**：实现RAG节点核心功能
4. **集成测试**：完成端到端测试，验证方案可行性

---

**文档版本**：V1.0  
**创建时间**：2025-01-XX  
**作者**：AI Assistant  
**审核状态**：待审核
