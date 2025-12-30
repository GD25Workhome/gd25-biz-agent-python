# LangGraphFlow 多智能体路由系统核心功能设计文档

## 文档说明

本文档基于对 `/Users/m684620/work/github/agent_2025_02/langGraphFlow` 代码库的深入分析，整理出系统的所有核心功能、架构设计和关键技术实现细节。文档包含总体设计和详细设计两部分，并摘抄了源代码中的关键设计代码，确保后续实现时不会丢失核心细节。

**文档版本**：V1.0  
**创建时间**：2025-01-XX  
**基于代码库**：langGraphFlow V2.0

---

## 目录

1. [总体设计](#一总体设计)
   - [1.1 系统概述](#11-系统概述)
   - [1.2 架构设计](#12-架构设计)
   - [1.3 核心技术栈](#13-核心技术栈)
   - [1.4 核心设计思想](#14-核心设计思想)

2. [详细设计](#二详细设计)
   - [2.1 路由智能体详细设计](#21-路由智能体详细设计)
   - [2.2 专门智能体详细设计](#22-专门智能体详细设计)
   - [2.3 RAG检索系统详细设计](#23-rag检索系统详细设计)
   - [2.4 状态管理详细设计](#24-状态管理详细设计)
   - [2.5 工具系统详细设计](#25-工具系统详细设计)

3. [关键源代码摘抄](#三关键源代码摘抄)
   - [3.1 路由状态定义](#31-路由状态定义)
   - [3.2 路由图构建](#32-路由图构建)
   - [3.3 路由节点实现](#33-路由节点实现)
   - [3.4 意图识别工具](#34-意图识别工具)
   - [3.5 智能体节点工厂函数](#35-智能体节点工厂函数)
   - [3.6 RAG检索实现](#36-rag检索实现)

---

## 一、总体设计

### 1.1 系统概述

LangGraphFlow 多智能体路由系统是一个基于 LangGraph StateGraph 构建的智能对话系统，旨在为用户提供统一的对话入口，自动识别用户意图并路由到对应的专门智能体处理业务需求。

#### 1.1.1 核心功能

系统核心功能包括：

1. **意图识别与路由**
   - 自动识别用户意图（血压记录、复诊管理、诊断支持等）
   - 将任务路由到对应的专门智能体
   - 支持意图澄清和自动重新路由

2. **血压记录管理**
   - 支持血压数据的记录、查询、更新和统计
   - 支持相对时间解析（如"今天早上8点"）

3. **复诊管理**
   - 支持复诊预约、查询、更新和提醒功能
   - 通过 HTTP API 调用 Java 微服务

4. **诊断智能体系统**
   - 支持多科室诊断（内科、外科、儿科、妇科、心血管科等）
   - 基于 RAG（检索增强生成）架构
   - 每个诊断智能体拥有独立的知识库和提示词

#### 1.1.2 系统特点

- **统一入口**：用户只需要与一个入口对话，系统自动处理路由和切换
- **自动重新路由**：每次调用都经过路由节点，自动检测用户意图变化并重新路由
- **状态持久化**：使用 PostgreSQL Checkpointer 持久化保存对话历史和状态
- **可扩展架构**：易于添加新的专门智能体

### 1.2 架构设计

#### 1.2.1 整体架构
```
┌─────────────────────────────────────────────────────────┐
│                   用户请求入口                            │
│              (FastAPI Backend Server)                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           输入安全检查节点 (Input Security Check)        │
│  - 敏感信息过滤                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           输入审核节点 (Input Review)                    │
│  - 内容合规性检查                                        │
│  - 恶意内容检测                                          │
│  - 用户行为分析                                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              路由智能体 (Router Agent)                   │
│  基于StateGraph实现，每次调用都经过路由节点               │
│  - 意图识别                                             │
│  - 意图澄清                                             │
│  - 路由决策                                             │
│  - 自动重新路由                                         │
└─────┬───────────┬───────────┬───────────┬──────────────┘
      │           │           │           │
      ▼           ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────────────┐ ┌──────────┐
│ 血压记录 │ │ 复诊管理 │ │  诊断智能体系统   │ │ 其他智能体│
│ 智能体   │ │ 智能体   │ │  ├─ 内科诊断      │ │ (可扩展) │
│          │ │          │ │  ├─ 外科诊断      │ │          │
│          │ │          │ │  ├─ 儿科诊断      │ │          │
│          │ │          │ │  ├─ 妇科诊断      │ │          │
│          │ │          │ │  ├─ 心血管科诊断  │ │          │
│          │ │          │ │  └─ 通用诊断      │ │          │
└─────┬────┘ └─────┬────┘ └─────┬──────────────┘ └─────┬────┘
      │           │           │           │
      └───────────┴───────────┴───────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│         回复内容评估节点 (Response Evaluation)           │
│  - 回复内容质量评估                                      │
│  - 安全性检查                                            │
│  - 准确性验证                                            │
│  - 合规性检查                                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           回复审核节点 (Response Review)                 │
│  - 内容审核                                              │
│  - 敏感信息检测                                          │
│  - 医疗建议风险评估                                      │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │   返回到路由节点      │
          │  (通过StateGraph边)  │
          └──────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              基础设施层                                   │
│  - PostgreSQL (短期记忆 + 长期记忆 + 业务数据)           │
│  - Redis (会话管理 + 安全策略缓存)                       │
│  - 向量数据库 (RAG知识库: PgVector 或 ADB PG)          │
│  - LangGraph (Agent框架)                                │
│  - Java微服务 (业务功能)                                │
│  - 审核服务 (可选，外部审核API)                         │
└─────────────────────────────────────────────────────────┘
```

**说明**：
- 系统默认包含安全审核功能，可通过配置开关控制是否启用
- 输入安全检查节点专注于敏感信息过滤
- 详细集成方案请参考：`审核安全内容评估集成方案.md`

#### 1.2.2 路由图结构

系统采用 LangGraph StateGraph 构建路由图，核心特点：

1. **每次调用都经过路由节点**：确保能够检测到用户意图变化
2. **条件路由**：根据意图识别结果，动态路由到对应的专门智能体
3. **回边机制**：专门智能体执行完后，返回到路由节点，等待下次调用

**路由图节点结构**：
- `router`：路由节点（入口点）
- `clarify_intent`：意图澄清节点
- `blood_pressure_agent`：血压记录智能体节点
- `appointment_agent`：复诊管理智能体节点
- `internal_medicine_diagnosis_agent`：内科诊断智能体节点
- `surgery_diagnosis_agent`：外科诊断智能体节点
- `pediatrics_diagnosis_agent`：儿科诊断智能体节点
- `gynecology_diagnosis_agent`：妇科诊断智能体节点
- `cardiology_diagnosis_agent`：心血管科诊断智能体节点
- `general_diagnosis_agent`：通用诊断智能体节点
- `doctor_assistant_agent`：医生助手智能体节点（占位）

### 1.3 核心技术栈

#### 1.3.1 框架和库

- **LangGraph**：用于构建路由智能体和专门智能体（StateGraph）
- **LangChain**：提供 LLM 调用和工具支持
- **FastAPI**：后端 API 服务框架
- **PostgreSQL**：
  - 短期记忆（Checkpointer）：存储对话状态快照
  - 长期记忆（Store）：存储用户设置信息
  - 业务数据：存储血压记录、复诊预约等业务数据
- **Redis**：会话状态管理（可选）
- **向量数据库**：
  - PgVector：PostgreSQL 的向量扩展（本地开发）
  - ADB PG：阿里云 AnalyticDB PostgreSQL（生产环境）

#### 1.3.2 技术版本要求

- Python 3.10+
- LangGraph 0.2+
- LangChain 0.3+
- FastAPI 0.100+
- PostgreSQL 14+
- Redis 7+

### 1.4 核心设计思想

#### 1.4.1 路由机制

**采用方案：LangGraph StateGraph + 条件路由**

核心特点：
- **每次调用都经过路由节点**：确保能够检测到用户意图变化
- **状态管理**：使用 RouterState 统一管理所有状态信息
- **条件路由**：根据意图识别结果，动态路由到对应的专门智能体
- **自动重新路由**：当检测到意图变化时，自动重新路由到新智能体

**路由流程**：
```
用户请求
    ↓
FastAPI接口接收
    ↓
StateGraph Agent.ainvoke()
    ↓
读取历史对话和状态（从checkpointer）
    ↓
进入router节点（入口点）
    ↓
router节点：识别意图，判断是否需要重新路由
    ↓
路由决策：根据意图路由到对应智能体节点
    ├─ blood_pressure → 血压记录智能体
    ├─ appointment → 复诊管理智能体
    ├─ diagnosis → 诊断智能体系统
    │   ├─ internal_medicine_diagnosis → 内科诊断智能体
    │   ├─ surgery_diagnosis → 外科诊断智能体
    │   ├─ pediatrics_diagnosis → 儿科诊断智能体
    │   ├─ gynecology_diagnosis → 妇科诊断智能体
    │   ├─ cardiology_diagnosis → 心血管科诊断智能体
    │   └─ general_diagnosis → 通用诊断智能体
    └─ unclear → 意图澄清节点
    ↓
执行专门智能体节点
    ↓
返回到router节点（通过边配置）
    ↓
保存新的对话状态（到checkpointer）
    ↓
返回结果给用户
```

#### 1.4.2 RAG架构

诊断智能体采用 RAG（检索增强生成）架构：

- **知识库管理**：每个诊断智能体拥有独立的知识库，存储在向量数据库中
- **检索增强**：通过向量检索获取相关医学知识、病例和指南
- **提示词定制**：每个诊断智能体有专门的系统提示词，定义角色和回答风格
- **模型演进**：前期使用通用模型+RAG，后期可升级为专业医疗模型

#### 1.4.3 状态管理机制

**Checkpointer（短期记忆）**：
- 使用 PostgreSQL 存储对话状态快照
- 每个 `session_id` 对应一个 `thread_id`
- 自动保存每次节点执行后的状态
- 支持状态恢复和历史消息读取

**Store（长期记忆）**：
- 使用 PostgreSQL Store 存储用户设置信息
- 支持命名空间隔离（memories、blood_pressure等）
- 结构化数据存储

#### 1.4.4 智能体创建模式

所有专门智能体都使用 **ReAct Agent** 模式：

- 使用 LangGraph 的 `create_react_agent` 创建智能体
- 每个智能体有独立的工具集和系统提示词
- 使用工厂函数模式创建节点函数，捕获外部依赖（pool、checkpointer、store）

---

## 二、详细设计

### 2.1 路由智能体详细设计

#### 2.1.1 功能描述

路由智能体是多智能体路由系统的核心组件，负责识别用户意图并将任务路由到对应的专门智能体。路由智能体每次调用都会经过，自动检测用户意图变化并实现重新路由，确保用户能够无缝切换不同的业务场景。

#### 2.1.2 核心功能

1. **意图识别**
   - 识别用户真实意图，返回意图类型和置信度
   - 支持多轮对话澄清意图
   - 处理复合意图（用户同时提及多个需求）

2. **意图澄清**
   - 当意图不明确时，生成澄清问题引导用户

3. **路由决策**
   - 根据意图识别结果，路由到对应的专门智能体
   - 支持诊断意图的细化（识别具体科室）

4. **重新路由**
   - 检测用户意图变化，自动重新路由到新智能体

#### 2.1.3 意图类型

系统支持的意图类型：

1. **blood_pressure**：用户想要记录、查询或管理血压数据
2. **appointment**：用户想要预约、查询或管理复诊
3. **diagnosis**：医生需要进行患者病情诊断
   - 子类型：
     - `internal_medicine_diagnosis`：内科诊断
     - `surgery_diagnosis`：外科诊断
     - `pediatrics_diagnosis`：儿科诊断
     - `gynecology_diagnosis`：妇科诊断
     - `cardiology_diagnosis`：心血管科诊断
     - `general_diagnosis`：通用诊断（无法确定具体科室）
4. **unclear**：意图不明确，需要进一步澄清

#### 2.1.4 路由决策逻辑

路由决策函数根据当前意图返回路由目标节点名称：

```python
def route_decision(state: RouterState) -> Literal[
    "blood_pressure", "appointment", 
    "internal_medicine_diagnosis", "surgery_diagnosis", "pediatrics_diagnosis",
    "gynecology_diagnosis", "cardiology_diagnosis", "general_diagnosis",
    "doctor_assistant", "unclear", "__end__"
]:
    """
    路由决策函数
    根据当前意图返回路由目标节点名称
    """
    # 检查是否有新的用户消息
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        # 如果最后一条消息是AI消息，停止执行
        if isinstance(last_message, AIMessage):
            return "__end__"
    
    current_intent = state.get("current_intent", "unclear")
    
    # 如果意图是unclear，路由到clarify_intent节点
    if current_intent == "unclear":
        return "unclear"
    
    # 其他情况直接返回意图类型（对应智能体节点名称）
    return current_intent
```

### 2.2 专门智能体详细设计

#### 2.2.1 血压记录智能体

**功能描述**：
血压记录智能体是专门处理血压数据收集和管理的智能体，支持血压数据的记录、查询、更新和统计功能。

**核心功能**：
1. **记录血压**：引导用户完成血压数据收集，包括收缩压、舒张压、测量时间等信息
2. **查询历史**：查询用户的历史血压记录，支持按时间范围查询
3. **更新记录**：更新已有的血压记录信息
4. **统计信息**：提供血压统计信息，如平均值、最高值、最低值等

**数据验证规则**：
- 收缩压范围：50-300 mmHg
- 舒张压范围：30-200 mmHg
- 收缩压必须大于舒张压

**时间解析**：
支持相对时间解析（如"今天早上8点"、"昨天下午"、"本周一上午"等），使用两阶段解析策略：
1. 标准格式解析（快速路径）
2. LLM解析（相对时间）

#### 2.2.2 复诊管理智能体

**功能描述**：
复诊管理智能体是专门处理复诊预约、查询和更新的智能体，通过调用 Java 微服务提供的 HTTP API 接口实现业务功能。

**核心功能**：
1. **复诊预约**：引导用户完成复诊预约，包括科室选择、医生选择、时间选择等
2. **查询预约**：查询用户的复诊预约记录，支持按状态、时间范围查询
3. **更新预约**：更新已有的复诊预约信息

**Java微服务集成**：
- 通过 HTTP API 调用 Java 微服务
- 支持认证和超时设置
- 错误处理：Java微服务调用失败时优雅降级

#### 2.2.3 诊断智能体系统

**功能描述**：
诊断智能体系统是专门协助医生进行患者病情诊断的智能体集群，通过细化的专业智能体提供不同科室或疾病类型的诊断支持。每个诊断智能体拥有自己的知识库和提示词，定义其专业角色和回答风格。

**支持的科室**：
- 内科诊断智能体（internal_medicine_diagnosis）
- 外科诊断智能体（surgery_diagnosis）
- 儿科诊断智能体（pediatrics_diagnosis）
- 妇科诊断智能体（gynecology_diagnosis）
- 心血管科诊断智能体（cardiology_diagnosis）
- 通用诊断智能体（general_diagnosis）

**RAG架构**：
- 每个诊断智能体拥有独立的知识库
- 通过向量检索获取相关医学知识、病例和指南
- 每个诊断智能体有专门的系统提示词，定义角色、回答风格和专业领域

**工作流程**：
1. 仔细分析患者的主诉、症状和检查结果
2. 使用 `retrieve_diagnosis_knowledge` 工具检索相关知识
3. 结合检索到的知识和临床经验，提供诊断建议
4. 明确列出诊断依据、鉴别诊断和下一步检查建议

### 2.3 RAG检索系统详细设计

#### 2.3.1 架构设计

RAG检索系统提供完整的检索增强生成流程：

```
医学文档收集
    ↓
文档预处理
    ├─→ 文本清洗
    ├─→ 分块（chunking）
    └─→ 元数据提取
    ↓
向量化
    ├─→ 文本嵌入（embedding）
    └─→ 存储到向量数据库
    ↓
知识库索引
    ├─→ 建立索引
    └─→ 质量检查
    ↓
检索查询
    ├─→ 查询向量化
    ├─→ 相似度搜索
    └─→ 返回Top-K相关文档
```

#### 2.3.2 向量数据库支持

系统支持两种向量数据库：

1. **PgVector**（本地开发）
   - 使用 PostgreSQL 的 pgvector 扩展
   - 支持 HNSW 索引和 IVFFlat 索引
   - 适用于本地开发、Docker 环境

2. **ADB PG**（生产环境）
   - 使用阿里云 AnalyticDB PostgreSQL
   - 通过 API 调用向量检索服务
   - 适用于生产环境、云原生部署

#### 2.3.3 RAG检索工具

**工具名称**：`retrieve_diagnosis_knowledge`

**功能**：检索诊断相关知识库，获取相关医学知识、病例和指南

**参数**：
- `query`：检索查询（患者症状、检查结果等）
- `department`：科室类型（internal_medicine/surgery/pediatrics等）
- `top_k`：返回Top-K相关文档（默认5）
- `filter_metadata`：元数据过滤条件（可选）

**返回**：
- 格式化的相关知识文档字符串，包含内容、来源和相关性得分

### 2.4 状态管理详细设计

#### 2.4.1 RouterState 定义

路由状态数据结构，统一管理所有状态信息：

```python
class RouterState(TypedDict):
    """路由状态数据结构"""
    messages: List[BaseMessage]  # 消息列表
    current_intent: Optional[str]  # 当前意图
    sub_intent: Optional[str]  # 子意图（用于诊断意图的细化）
    current_agent: Optional[str]  # 当前活跃的智能体名称
    need_reroute: bool  # 是否需要重新路由
    session_id: str  # 会话ID
    user_id: str  # 用户ID
```

#### 2.4.2 IntentResult 定义

意图识别结果数据结构：

```python
class IntentResult(BaseModel):
    """意图识别结果"""
    intent_type: str  # "blood_pressure", "appointment", "diagnosis", "unclear"
    sub_intent: Optional[str] = None  # 子意图（用于诊断意图的细化）
    confidence: float  # 0.0-1.0
    entities: Dict[str, Any]  # 提取的实体信息
    need_clarification: bool  # 是否需要澄清
    reasoning: Optional[str] = None  # 识别理由（可选）
```

#### 2.4.3 Checkpointer 机制

**功能**：持久化保存对话状态快照

**实现**：
- 使用 PostgreSQL 存储
- 每个 `session_id` 对应一个 `thread_id`
- 自动保存每次节点执行后的状态
- 支持状态恢复和历史消息读取

**使用方式**：
```python
# 初始化checkpointer
checkpointer = AsyncPostgresSaver(pool)
await checkpointer.setup()

# 编译图时绑定checkpointer
graph = router_graph.compile(checkpointer=checkpointer)

# 调用时指定thread_id（对应session_id）
config = {"configurable": {"thread_id": session_id}}
result = await graph.ainvoke(state_input, config=config)
```

#### 2.4.4 Store 机制

**功能**：存储用户设置信息（长期记忆）

**实现**：
- 使用 PostgreSQL Store 存储
- 支持命名空间隔离（memories、blood_pressure等）
- 结构化数据存储

**使用方式**：
```python
# 初始化store
store = AsyncPostgresStore(pool)
await store.setup()

# 存储用户设置
namespace = ("memories", user_id)
await store.aput(namespace, key, value)

# 查询用户设置
memories = await store.asearch(namespace, query="")
```

### 2.5 工具系统详细设计

#### 2.5.1 路由工具

**identify_intent 工具**：
- 功能：识别用户意图，返回意图类型和置信度
- 输入：用户查询、对话历史（可选）、当前意图（可选）
- 输出：IntentResult 对象（字典格式）

**clarify_intent 工具**：
- 功能：当意图不明确时，生成澄清问题
- 输入：用户查询、可能的意图列表
- 输出：澄清问题字符串

#### 2.5.2 血压记录工具

**record_blood_pressure 工具**：
- 功能：记录用户的血压数据
- 参数：
  - `systolic`：收缩压（50-300）
  - `diastolic`：舒张压（30-200）
  - `date_time`：测量时间（可选，支持相对时间）
  - `original_time_description`：原始时间描述（可选）
  - `notes`：备注（可选）
- 返回：保存结果消息

**query_blood_pressure 工具**：
- 功能：查询用户的历史血压记录
- 参数：
  - `user_id`：用户ID
  - `start_date`：开始日期（可选）
  - `end_date`：结束日期（可选）
  - `limit`：返回记录数限制（默认10）
- 返回：血压记录列表

**update_blood_pressure 工具**：
- 功能：更新已有的血压记录
- 参数：
  - `record_id`：记录ID
  - `systolic`：收缩压（可选）
  - `diastolic`：舒张压（可选）
  - `measurement_time`：测量时间（可选）
- 返回：更新结果消息

**info 工具**：
- 功能：查询用户的基础信息（设置信息和血压统计信息）
- 参数：
  - `user_id`：用户ID
  - `start_date`：开始日期（可选）
  - `end_date`：结束日期（可选）
- 返回：统计信息（平均值、最高值、最低值等）

#### 2.5.3 诊断工具

**retrieve_diagnosis_knowledge 工具**：
- 功能：检索诊断相关知识库
- 参数：
  - `query`：检索查询（患者症状、检查结果等）
  - `department`：科室类型
  - `top_k`：返回Top-K相关文档（默认5）
  - `filter_metadata`：元数据过滤条件（可选）
- 返回：格式化的相关知识文档字符串

---

## 三、关键源代码摘抄

### 3.1 路由状态定义

**文件位置**：`domain/router/state.py`

```python
"""
路由智能体状态定义
定义RouterState和IntentResult数据结构
"""
from typing import TypedDict, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from pydantic import BaseModel


class RouterState(TypedDict):
    """路由状态数据结构"""
    messages: List[BaseMessage]  # 消息列表
    current_intent: Optional[str]  # 当前意图：blood_pressure, appointment, diagnosis, internal_medicine_diagnosis, unclear
    sub_intent: Optional[str]  # 子意图（用于诊断意图的细化，如internal_medicine_diagnosis）
    current_agent: Optional[str]  # 当前活跃的智能体名称
    need_reroute: bool  # 是否需要重新路由
    session_id: str  # 会话ID
    user_id: str  # 用户ID


class IntentResult(BaseModel):
    """意图识别结果"""
    intent_type: str  # "blood_pressure", "appointment", "diagnosis", "unclear"
    sub_intent: Optional[str] = None  # 子意图（用于诊断意图的细化，如internal_medicine_diagnosis）
    confidence: float  # 0.0-1.0
    entities: Dict[str, Any]  # 提取的实体信息
    need_clarification: bool  # 是否需要澄清
    reasoning: Optional[str] = None  # 识别理由（可选）
```

### 3.2 路由图构建

**文件位置**：`domain/router/graph.py`

```python
"""
路由图创建
创建并配置StateGraph路由图
"""
import logging
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool
from .state import RouterState
from .node import router_node, clarify_intent_node, route_decision

logger = logging.getLogger(__name__)


def create_router_graph(checkpointer: AsyncPostgresSaver, pool: AsyncConnectionPool, store: AsyncPostgresStore = None):
    """
    创建路由图
    
    Args:
        checkpointer: PostgreSQL checkpointer实例，用于保存对话状态
        pool: PostgreSQL数据库连接池实例，用于访问业务表
        store: PostgreSQL Store实例，用于长期记忆存储（可选）
        
    Returns:
        CompiledGraph: 编译后的路由图
    """
    # 创建StateGraph
    router_graph = StateGraph(RouterState)
    
    # 添加节点
    router_graph.add_node("router", router_node)  # 路由节点（每次调用都经过）
    router_graph.add_node("clarify_intent", clarify_intent_node)  # 意图澄清节点
    
    # 添加专门智能体节点
    if pool:
        # 延迟导入智能体，避免循环导入
        from domain.agents import (
            create_blood_pressure_agent_node,
            create_appointment_agent_node,
            create_internal_medicine_diagnosis_agent_node,
            create_surgery_diagnosis_agent_node,
            create_pediatrics_diagnosis_agent_node,
            create_gynecology_diagnosis_agent_node,
            create_cardiology_diagnosis_agent_node,
            create_general_diagnosis_agent_node
        )
        # 使用工厂函数创建节点，传递pool、checkpointer和store
        blood_pressure_node = create_blood_pressure_agent_node(pool, checkpointer, store)
        router_graph.add_node("blood_pressure_agent", blood_pressure_node)
        
        appointment_node = create_appointment_agent_node(pool, checkpointer, store)
        router_graph.add_node("appointment_agent", appointment_node)
        
        # 添加各科室诊断智能体节点
        internal_medicine_diagnosis_node = create_internal_medicine_diagnosis_agent_node(
            pool, checkpointer, store
        )
        router_graph.add_node("internal_medicine_diagnosis_agent", internal_medicine_diagnosis_node)
        
        surgery_diagnosis_node = create_surgery_diagnosis_agent_node(
            pool, checkpointer, store
        )
        router_graph.add_node("surgery_diagnosis_agent", surgery_diagnosis_node)
        
        pediatrics_diagnosis_node = create_pediatrics_diagnosis_agent_node(
            pool, checkpointer, store
        )
        router_graph.add_node("pediatrics_diagnosis_agent", pediatrics_diagnosis_node)
        
        gynecology_diagnosis_node = create_gynecology_diagnosis_agent_node(
            pool, checkpointer, store
        )
        router_graph.add_node("gynecology_diagnosis_agent", gynecology_diagnosis_node)
        
        cardiology_diagnosis_node = create_cardiology_diagnosis_agent_node(
            pool, checkpointer, store
        )
        router_graph.add_node("cardiology_diagnosis_agent", cardiology_diagnosis_node)
        
        general_diagnosis_node = create_general_diagnosis_agent_node(
            pool, checkpointer, store
        )
        router_graph.add_node("general_diagnosis_agent", general_diagnosis_node)
    
    # 设置入口点：每次调用都从router节点开始
    router_graph.set_entry_point("router")
    
    # 添加条件边：根据意图路由到对应智能体
    router_graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "blood_pressure": "blood_pressure_agent",
            "appointment": "appointment_agent",
            "internal_medicine_diagnosis": "internal_medicine_diagnosis_agent",
            "surgery_diagnosis": "surgery_diagnosis_agent",
            "pediatrics_diagnosis": "pediatrics_diagnosis_agent",
            "gynecology_diagnosis": "gynecology_diagnosis_agent",
            "cardiology_diagnosis": "cardiology_diagnosis_agent",
            "general_diagnosis": "general_diagnosis_agent",
            "doctor_assistant": "doctor_assistant_agent",
            "unclear": "clarify_intent",
            "__end__": "__end__"  # 停止执行
        }
    )
    
    # 添加回边：专门智能体执行完后，返回到router节点
    router_graph.add_edge("blood_pressure_agent", "router")
    router_graph.add_edge("appointment_agent", "router")
    router_graph.add_edge("internal_medicine_diagnosis_agent", "router")
    router_graph.add_edge("surgery_diagnosis_agent", "router")
    router_graph.add_edge("pediatrics_diagnosis_agent", "router")
    router_graph.add_edge("gynecology_diagnosis_agent", "router")
    router_graph.add_edge("cardiology_diagnosis_agent", "router")
    router_graph.add_edge("general_diagnosis_agent", "router")
    router_graph.add_edge("doctor_assistant_agent", "router")
    router_graph.add_edge("clarify_intent", "router")
    
    # 编译图
    compiled_graph = router_graph.compile(checkpointer=checkpointer)
    
    logger.info("路由图创建成功")
    
    return compiled_graph
```

### 3.3 路由节点实现

**文件位置**：`domain/router/node.py`

```python
"""
路由节点实现
包含router_node和route_decision函数
"""
import logging
from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from .state import RouterState, IntentResult
from .tools.router_tools import identify_intent, clarify_intent
from core.config import get_settings

logger = logging.getLogger(__name__)


def router_node(state: RouterState) -> RouterState:
    """
    路由节点函数
    每次调用都会经过此节点，识别意图并更新状态
    
    Args:
        state: 路由状态
        
    Returns:
        RouterState: 更新后的路由状态
    """
    # 获取配置
    settings = get_settings()
    
    # 获取最后一条消息
    messages = state.get("messages", [])
    if not messages:
        logger.warning("没有消息，返回未更新状态")
        return state
    
    last_message = messages[-1]
    
    # 关键修复：如果最后一条消息是AI消息，说明没有新的用户消息，应该停止执行
    # 这可以防止无限循环：router -> agent -> router -> ...
    if isinstance(last_message, AIMessage):
        logger.debug("最后一条消息是AI消息，没有新的用户消息，停止路由执行")
        # 直接返回当前状态，不进行路由决策
        return state
    
    # 获取用户查询
    user_query = ""
    if isinstance(last_message, HumanMessage):
        user_query = last_message.content
    else:
        user_query = str(last_message.content) if hasattr(last_message, 'content') else str(last_message)
    
    # 获取当前意图和智能体
    current_intent = state.get("current_intent")
    current_agent = state.get("current_agent")
    
    logger.info(f"路由节点: 用户查询='{user_query}', 当前意图={current_intent}, 当前智能体={current_agent}")
    
    # 准备对话历史（用于上下文）
    conversation_history = []
    for msg in messages[-5:]:  # 只取最近5条消息
        if isinstance(msg, HumanMessage):
            conversation_history.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage):
            conversation_history.append(f"助手: {msg.content}")
    
    conversation_history_str = "\n".join(conversation_history) if conversation_history else None
    
    # 调用意图识别工具
    try:
        intent_result_dict = identify_intent.invoke({
            "query": user_query,
            "conversation_history": conversation_history_str,
            "current_intent": current_intent
        })
        
        intent_result = IntentResult(**intent_result_dict)
        
        logger.info(f"意图识别结果: type={intent_result.intent_type}, confidence={intent_result.confidence}, "
                   f"need_clarification={intent_result.need_clarification}")
        
        # 检查是否需要重新路由
        need_reroute = False
        new_intent = intent_result.intent_type
        new_agent = None
        
        # 如果置信度低，需要澄清
        if intent_result.confidence < settings.intent_confidence_threshold:
            logger.info(f"置信度低（{intent_result.confidence} < {settings.intent_confidence_threshold}），需要澄清")
            new_intent = "unclear"
            new_agent = None
        else:
            # 置信度高，检查意图是否变化
            if current_intent != new_intent:
                logger.info(f"检测到意图变化: {current_intent} -> {new_intent}")
                need_reroute = True
            
            # 确定对应的智能体
            intent_to_agent = {
                "blood_pressure": "blood_pressure_agent",
                "appointment": "appointment_agent",
                "internal_medicine_diagnosis": "internal_medicine_diagnosis_agent",
                "diagnosis": "internal_medicine_diagnosis_agent",  # 通用诊断意图也路由到内科诊断智能体（默认）
                "doctor_assistant": "doctor_assistant_agent",
                "unclear": None
            }
            
            # 处理诊断意图的子类型
            sub_intent = intent_result.sub_intent
            if new_intent == "diagnosis" and sub_intent:
                # 如果有子意图，使用子意图对应的智能体
                # 科室诊断智能体映射
                diagnosis_agent_map = {
                    "internal_medicine_diagnosis": "internal_medicine_diagnosis_agent",
                    "surgery_diagnosis": "surgery_diagnosis_agent",
                    "pediatrics_diagnosis": "pediatrics_diagnosis_agent",
                    "gynecology_diagnosis": "gynecology_diagnosis_agent",
                    "cardiology_diagnosis": "cardiology_diagnosis_agent",
                    "general_diagnosis": "general_diagnosis_agent"
                }
                
                if sub_intent in diagnosis_agent_map:
                    new_agent = diagnosis_agent_map[sub_intent]
                    new_intent = sub_intent  # 更新意图为子意图
                else:
                    # 未知的子类型，使用通用诊断智能体
                    logger.warning(f"诊断子类型 {sub_intent} 未映射到具体智能体，使用通用诊断智能体")
                    new_agent = "general_diagnosis_agent"
                    new_intent = "general_diagnosis"
            else:
                new_agent = intent_to_agent.get(new_intent)
        
        # 更新状态
        updated_state = state.copy()
        updated_state["current_intent"] = new_intent
        updated_state["current_agent"] = new_agent
        updated_state["need_reroute"] = need_reroute
        # 保存子意图
        if intent_result.sub_intent:
            updated_state["sub_intent"] = intent_result.sub_intent
        
        logger.info(f"状态更新: current_intent={new_intent}, sub_intent={intent_result.sub_intent}, current_agent={new_agent}, need_reroute={need_reroute}")
        
        return updated_state
        
    except Exception as e:
        logger.error(f"路由节点执行失败: {str(e)}")
        # 返回默认状态，设置为unclear
        updated_state = state.copy()
        updated_state["current_intent"] = "unclear"
        updated_state["need_reroute"] = False
        return updated_state


def route_decision(state: RouterState) -> Literal[
    "blood_pressure", "appointment", 
    "internal_medicine_diagnosis", "surgery_diagnosis", "pediatrics_diagnosis",
    "gynecology_diagnosis", "cardiology_diagnosis", "general_diagnosis",
    "doctor_assistant", "unclear", "__end__"
]:
    """
    路由决策函数
    根据当前意图返回路由目标节点名称
    
    Args:
        state: 路由状态
        
    Returns:
        Literal: 路由目标节点名称，如果是"__end__"则停止执行
    """
    # 检查是否有新的用户消息
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        # 如果最后一条消息是AI消息，停止执行
        if isinstance(last_message, AIMessage):
            logger.info("路由决策: 最后一条消息是AI消息，停止执行")
            return "__end__"  # type: ignore
    
    current_intent = state.get("current_intent", "unclear")
    
    logger.info(f"路由决策: current_intent={current_intent}")
    
    # 如果意图是unclear，路由到clarify_intent节点
    if current_intent == "unclear":
        return "unclear"
    
    # 其他情况直接返回意图类型（对应智能体节点名称）
    return current_intent  # type: ignore
```

### 3.4 意图识别工具

**文件位置**：`domain/router/tools/router_tools.py`

```python
"""
路由工具实现
包含意图识别工具和意图澄清工具
"""
import json
import logging
from typing import Optional, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from ..state import IntentResult
from core.llm import get_llm_by_config, LLMFactory
from core.config import get_settings

logger = logging.getLogger(__name__)

# 意图识别系统提示词
INTENT_IDENTIFICATION_PROMPT = """你是一个智能路由助手，负责识别用户的真实意图。

支持的意图类型：
1. blood_pressure: 用户想要记录、查询或管理血压数据
   - 关键词：血压、收缩压、舒张压、记录血压、查询血压、血压记录、血压数据
   - 示例："我想记录血压"、"查询我的血压记录"、"更新血压数据"

2. appointment: 用户想要预约、查询或管理复诊
   - 关键词：预约、复诊、挂号、就诊、门诊、预约医生、预约时间
   - 示例："我想预约复诊"、"查询我的预约"、"取消预约"

3. diagnosis: 医生需要进行患者病情诊断
   - 子类型：
     - internal_medicine_diagnosis: 内科诊断（关键词：内科、消化、呼吸、内分泌等）
     - surgery_diagnosis: 外科诊断（关键词：外科、手术、外伤、肿瘤等）
     - pediatrics_diagnosis: 儿科诊断（关键词：儿科、儿童、小儿、婴幼儿等）
     - gynecology_diagnosis: 妇科诊断（关键词：妇科、女性、月经、妊娠等）
     - cardiology_diagnosis: 心血管科诊断（关键词：心血管、心脏、血压、冠心病等）
     - neurology_diagnosis: 神经科诊断（关键词：神经、头痛、癫痫、脑部等）
     - dermatology_diagnosis: 皮肤科诊断（关键词：皮肤、皮疹、过敏、皮炎等）
     - general_diagnosis: 通用诊断（无法确定具体科室）
   - 关键词：诊断、病情、症状、检查结果、患者、病例、分析
   - 示例："帮我诊断这个患者"、"这个症状是什么病"、"分析一下检查结果"

4. unclear: 意图不明确，需要进一步澄清
   - 当用户的消息无法明确归类到上述三种意图时
   - 示例："你好"、"在吗"、"有什么功能"

请分析用户消息，返回JSON格式的意图识别结果：
{{
    "intent_type": "意图类型（blood_pressure/appointment/diagnosis/unclear）",
    "sub_intent": "子意图类型（如果是diagnosis，返回具体科室如internal_medicine_diagnosis；否则为null）",
    "confidence": 置信度（0.0-1.0之间的浮点数）,
    "entities": {{}},
    "need_clarification": 是否需要澄清（true/false）,
    "reasoning": "识别理由"
}}

规则：
- 如果意图明确且置信度>0.8，设置need_clarification=false
- 如果意图不明确（置信度<0.8），设置need_clarification=true
- 如果识别为diagnosis但无法确定具体科室，sub_intent设置为"general_diagnosis"
- 如果用户同时提及多个意图，按优先级选择（优先级：diagnosis > appointment > blood_pressure）
- 如果用户的消息很短，且当前有活跃的智能体，可能继续当前意图
"""


@tool
def identify_intent(
    query: str,
    conversation_history: Optional[str] = None,
    current_intent: Optional[str] = None
) -> Dict[str, Any]:
    """
    识别用户意图
    
    Args:
        query: 用户查询内容
        conversation_history: 对话历史（可选，JSON字符串格式）
        current_intent: 当前意图（可选）
        
    Returns:
        Dict: 意图识别结果，包含intent_type、confidence、entities、need_clarification等字段
    """
    try:
        # 构建提示词
        prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_IDENTIFICATION_PROMPT),
            ("human", """用户消息: {query}

对话历史: {history}

当前意图: {current_intent}

请识别用户的真实意图，返回JSON格式的结果。""")
        ])
        
        # 准备输入
        history_text = conversation_history if conversation_history else "无"
        current_intent_text = current_intent if current_intent else "无"
        
        # 调用LLM
        settings = get_settings()
        llm_factory = LLMFactory(settings)
        llm = llm_factory.create_by_config()
        chain = prompt | llm
        response = chain.invoke({
            "query": query,
            "history": history_text,
            "current_intent": current_intent_text
        })
        
        # 解析响应
        llm_text = response.content if hasattr(response, 'content') else str(response)
        intent_result = _parse_intent_result(llm_text)
        
        logger.info(f"意图识别结果: {intent_result.intent_type}, 置信度: {intent_result.confidence}")
        
        # 返回字典格式（工具需要返回可序列化的字典）
        return intent_result.model_dump()
        
    except Exception as e:
        logger.error(f"意图识别失败: {str(e)}")
        # 返回默认结果
        default_result = IntentResult(
            intent_type="unclear",
            sub_intent=None,
            confidence=0.0,
            entities={},
            need_clarification=True,
            reasoning=f"意图识别异常: {str(e)}"
        )
        return default_result.model_dump()
```

### 3.5 智能体节点工厂函数

**文件位置**：`domain/agents/blood_pressure/agent.py`

```python
"""
血压记录智能体实现
创建血压记录智能体节点和智能体
"""
import logging
from langgraph.prebuilt import create_react_agent
from langgraph.store.postgres import AsyncPostgresStore
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from psycopg_pool import AsyncConnectionPool
from domain.router import RouterState
from .tools import create_blood_pressure_tools
from core.llm import get_llm_by_config

logger = logging.getLogger(__name__)


def create_blood_pressure_agent_node(pool: AsyncConnectionPool, checkpointer: AsyncPostgresSaver, store: AsyncPostgresStore = None):
    """
    创建血压记录智能体节点函数（工厂函数）
    
    使用闭包捕获pool、checkpointer和store，返回符合LangGraph节点签名的函数
    
    Args:
        pool: PostgreSQL数据库连接池实例
        checkpointer: PostgreSQL Checkpointer实例
        store: PostgreSQL Store实例（可选，用于长期记忆）
        
    Returns:
        Callable: 符合(state: RouterState) -> RouterState签名的节点函数
    """
    async def blood_pressure_agent_node(state: RouterState) -> RouterState:
        """
        血压记录智能体节点函数
        
        注意：这个节点执行完后，会返回到router节点
        下次调用时，router节点会重新判断意图
        """
        try:
            messages = state.get("messages", [])
            session_id = state.get("session_id")
            user_id = state.get("user_id")
            
            if not user_id:
                logger.error("blood_pressure_agent_node: user_id为空")
                return state
            
            # 获取LLM
            llm = get_llm_by_config()
            
            # 创建血压记录智能体
            agent = await create_blood_pressure_agent(
                llm=llm,
                pool=pool,
                user_id=user_id,
                checkpointer=checkpointer,
                store=store
            )
            
            # 调用智能体（使用相同的thread_id）
            config = {"configurable": {"thread_id": session_id}} if session_id else {}
            
            # 获取当前日期时间，用于构建系统提示词
            from datetime import datetime
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_prompt = get_blood_pressure_system_prompt(current_datetime)
            
            # 构造消息列表，包含系统提示词
            # 注意：LangGraph会自动从checkpointer读取历史消息，我们只需要添加系统提示词
            # 如果messages中已经有SystemMessage，则替换；否则添加
            messages_with_system = []
            has_system_message = False
            for msg in messages:
                if isinstance(msg, SystemMessage):
                    # 替换现有的系统消息
                    messages_with_system.append(SystemMessage(content=system_prompt))
                    has_system_message = True
                else:
                    messages_with_system.append(msg)
            
            # 如果没有系统消息，在开头添加
            if not has_system_message:
                messages_with_system.insert(0, SystemMessage(content=system_prompt))
            
            result = await agent.ainvoke(
                {"messages": messages_with_system},
                config=config
            )
            
            # 更新状态
            updated_state = state.copy()
            updated_state["messages"] = result.get("messages", messages)
            
            logger.info(f"血压记录智能体节点执行完成，用户ID: {user_id}")
            
            return updated_state
            
        except Exception as e:
            logger.error(f"血压记录智能体节点执行失败: {str(e)}")
            import traceback
            traceback.print_exc()
            # 返回未更新的状态
            return state
    
    return blood_pressure_agent_node
```

### 3.6 RAG检索实现

**文件位置**：`domain/rag/rag_retriever.py`

```python
"""
RAG检索工具
完整的RAG检索流程：文档入库 -> 向量化 -> 检索
"""
from typing import List, Dict, Any, Optional
import logging

from .document_loader import DocumentLoader
from .text_splitter import TextSplitter
from .embedding_service import EmbeddingService
from .vector_store_factory import create_vector_store

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    RAG检索工具类
    提供完整的RAG检索流程
    """
    
    def __init__(
        self,
        table_name: str = "rag_documents",
        chunk_size: int = 200,
        chunk_overlap: int = 50,
        embedding_model_name: str = "moka-ai/m3e-base",
        db_uri: Optional[str] = None
    ):
        """
        初始化RAG检索工具
        
        Args:
            table_name: 向量数据库表名
            chunk_size: 文档分块大小
            chunk_overlap: 文档分块重叠大小
            embedding_model_name: Embedding模型名称
            db_uri: 数据库连接URI，默认使用Config.DB_URI
        """
        self.table_name = table_name
        self.document_loader = DocumentLoader()
        self.text_splitter = TextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        self.embedding_service = EmbeddingService(model_name=embedding_model_name)
        # 使用工厂函数创建向量存储实例
        self.vector_store = create_vector_store(
            table_name=table_name,
            db_uri=db_uri
        )
        
        # 确保模型已加载
        self.embedding_service.load_model()
        self.dimension = self.embedding_service.get_dimension()
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        threshold: Optional[float] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        检索相关知识
        
        Args:
            query: 查询文本
            top_k: 返回Top-K相关文档
            threshold: 相似度阈值（0-1之间），只返回相似度大于阈值的记录
            filter_metadata: 元数据过滤条件（可选）
        
        Returns:
            List[Dict]: 检索结果列表，每个结果包含：
                - content: 文档内容
                - similarity: 相似度得分
                - metadata: 元数据
                - id: 记录ID
        """
        try:
            # 1. 查询向量化
            query_vector = self.embedding_service.encode(query)
            
            # 2. 构建WHERE条件
            where_clause = None
            if filter_metadata:
                conditions = []
                for key, value in filter_metadata.items():
                    conditions.append(f"metadata->>'{key}' = '{value}'")
                if conditions:
                    where_clause = " AND ".join(conditions)
            
            # 3. 执行相似度搜索
            # 对于 ADB PG，需要传递 query_text（原始查询文本）
            results = self.vector_store.cosine_search(
                self.table_name,
                query_vector,
                limit=top_k,
                threshold=threshold,
                where_clause=where_clause,
                filter_metadata=filter_metadata,
                query_text=query  # ADB PG 需要原始查询文本
            )
            
            # 4. 格式化结果
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'id': result['id'],
                    'content': result['content'],
                    'similarity': float(result['similarity']),
                    'metadata': result.get('metadata', {}),
                    'source': result.get('metadata', {}).get('source_file_name', '未知')
                })
            
            logger.debug(f"检索完成: 查询='{query}', 返回 {len(formatted_results)} 条结果")
            return formatted_results
        except Exception as e:
            logger.error(f"检索失败: {str(e)}")
            raise
```

---

## 四、总结

### 4.1 核心要点

1. **LangGraph StateGraph 架构**
   - 使用 StateGraph 构建路由图，每次调用都经过路由节点
   - 支持自动重新路由，检测用户意图变化并重新路由
   - 状态持久化，使用 PostgreSQL Checkpointer 保存对话状态

2. **多智能体路由机制**
   - 路由智能体负责意图识别和路由决策
   - 专门智能体处理具体业务逻辑
   - 支持诊断智能体的细化（按科室分类）

3. **RAG 检索增强生成**
   - 每个诊断智能体拥有独立的知识库
   - 支持 PgVector 和 ADB PG 两种向量数据库
   - 通过向量检索获取相关医学知识

4. **状态管理**
   - RouterState 统一管理所有状态信息
   - Checkpointer 持久化保存对话状态
   - Store 存储用户设置信息（长期记忆）

5. **工具系统**
   - 路由工具：意图识别、意图澄清
   - 业务工具：血压记录、复诊管理、诊断检索等
   - 使用 LangChain 的 `@tool` 装饰器定义工具

### 4.2 关键技术决策

1. **状态持久化**：选择 PostgreSQL 而非内存，支持会话恢复
2. **时间解析**：两阶段解析（标准格式 + LLM解析），支持相对时间
3. **路由机制**：每次用户输入都经过 router 节点，支持动态路由
4. **错误处理**：分层错误处理，保证系统稳定性
5. **向量数据库**：支持 PgVector 和 ADB PG，便于本地开发和生产部署

### 4.3 扩展性设计

1. **添加新智能体**：
   - 创建智能体节点工厂函数
   - 创建对应的工具集
   - 在路由图中注册新节点和边

2. **添加新科室诊断智能体**：
   - 创建新的知识库集合
   - 配置系统提示词
   - 在路由层添加新的意图识别规则

3. **知识库更新**：
   - 支持增量更新知识库
   - 支持版本管理
   - 支持 A/B 测试不同版本的知识库

---

**文档版本**：V1.0  
**创建时间**：2025-01-XX  
**维护者**：开发团队

