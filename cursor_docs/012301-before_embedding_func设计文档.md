# before_embedding_func 节点设计文档

## 文档信息

- **文档版本**：V1.0
- **创建日期**：2026-01-23
- **作者**：开发团队
- **状态**：设计阶段

---

## 目录

1. [概述](#一概述)
2. [需求分析](#二需求分析)
3. [数据库设计](#三数据库设计)
4. [数据流程设计](#四数据流程设计)
5. [实现方案](#五实现方案)
6. [代码结构](#六代码结构)
7. [测试方案](#七测试方案)

---

## 一、概述

### 1.1 功能描述

`before_embedding_func` 是一个 Function 节点，位于 `embedding_agent` 流程中的 `format_data_node` 位置。该节点的主要职责是：

1. **接收前置 Agent 节点的输出**：从 `state.edges_var` 中获取 Agent 节点输出的结构化数据
2. **数据持久化**：将提取的数据插入到 embedding 表中
3. **生成 embedding 字符串**：根据业务规则拼接生成 `embedding_str`，供后续 embedding 节点使用
4. **状态更新**：将 `embedding_str` 存储到 `state.edges_var` 中

### 1.2 在流程中的位置

```
stem_extraction_node (Agent)
    ↓
format_data_node (Function: before_embedding_func) ← 本文档设计
    ↓
embedding_node (Embedding Agent)
    ↓
insert_data_to_vector_db_node (Function)
```

### 1.3 输入输出

**输入**：
- `state.edges_var`：包含前置 Agent 节点输出的 JSON 数据
  - `scene_summary`：场景摘要（字符串）
  - `optimization_question`：优化后的问题（字符串）
  - `input_tags`：输入标签数组
  - `response_tags`：响应标签数组
- `state.prompt_vars.source_id`：数据源 ID（BloodPressureSessionRecord 的 id）
- `state.prompt_vars.source_table_name`：数据来源表名（如 "blood_pressure_session_records"）

**输出**：
- `state.edges_var.embedding_str`：用于 embedding 的字符串
- `state.prompt_vars.embedding_records_id`：embedding 表记录的 ID（用于后续节点更新数据）
- 数据库：embedding 表中新增一条记录

---

## 二、需求分析

### 2.1 功能需求

#### 2.1.1 数据接收
- 从 `state.edges_var` 中读取前置 Agent 节点的输出数据
- 验证必要字段是否存在（`scene_summary`、`optimization_question`、`input_tags`、`response_tags`）

#### 2.1.2 数据源关联
- 从 `state.prompt_vars.source_id` 获取数据源 ID
- 从 `state.prompt_vars.source_table_name` 获取数据来源表名
- 根据 `source_id` 查询 `BloodPressureSessionRecord` 表，获取 `message_id`
- 如果 `source_id` 不存在，抛出异常中断流程

#### 2.1.3 版本管理
- 根据 `message_id` 查询 embedding 表中已存在的记录
- 计算下一个版本号（从 0 开始递增）
- 如果 `message_id` 不存在，版本号为 0；如果存在，版本号为 `max(version) + 1`

#### 2.1.4 数据插入
- 将以下字段插入到 embedding 表：
  - `scene_summary`：场景摘要
  - `optimization_question`：优化后的问题
  - `input_tags`：输入标签（JSON 数组格式存储）
  - `response_tags`：响应标签（JSON 数组格式存储）
  - `ai_response`：AI 回复内容（来自 `BloodPressureSessionRecord.new_session_response`）
  - `embedding_value`：Embedding 向量值（2048维，由 embedding_node 生成，在 insert_data_to_vector_db_node 中更新）
  - `message_id`：消息 ID（关联数据源）
  - `version`：版本号
  - `is_published`：是否发布（默认 false）
  - `source_table_name`：数据来源表名
  - `source_record_id`：数据来源记录ID
  - `generation_status`：生成状态（默认 0，表示进行中）
  - `failure_reason`：失败原因（初始为 NULL）

#### 2.1.5 embedding_str 生成
- 从 `state.edges_var` 获取 `scene_summary` 和 `optimization_question`
- 从 `BloodPressureSessionRecord.new_session_response` 获取 AI 回复
- 按照以下格式拼接：
  ```
  {scene_summary}
  问题：{optimization_question}
  回复：{ai_response}
  ```
- 将生成的 `embedding_str` 存储到 `state.edges_var.embedding_str`

#### 2.1.6 状态更新
- 将插入的 embedding 记录 ID 存储到 `state.prompt_vars.embedding_records_id`
- 供后续 `insert_data_to_vector_db_node` 节点使用，用于更新记录状态

### 2.2 非功能需求

#### 2.2.1 错误处理
- 如果必要字段缺失，抛出异常中断流程
- 如果数据库操作失败，抛出异常中断流程
- 异常信息应包含详细的错误堆栈，便于问题排查
- 不采用降级策略，确保数据一致性

#### 2.2.2 性能要求
- 数据库查询操作应使用异步方式
- 尽量减少数据库查询次数（合并查询或使用批量操作）

#### 2.2.3 可维护性
- 代码结构清晰，职责单一
- 完善的日志记录
- 详细的类型提示和文档字符串

---

## 三、数据库设计

### 3.1 表结构设计

#### 3.1.1 表名
```
gd2502_embedding_records
```

#### 3.1.2 字段定义

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | String(50) | PRIMARY KEY | 记录ID（ULID） |
| scene_summary | Text | NOT NULL | 场景摘要 |
| optimization_question | Text | NOT NULL | 优化后的问题 |
| input_tags | Text | NULL | 输入标签（JSON数组字符串） |
| response_tags | Text | NULL | 响应标签（JSON数组字符串） |
| ai_response | Text | NULL | AI回复内容（来自原始表的new_session_response） |
| embedding_value | Vector(2048) | NULL | Embedding向量值（2048维，由embedding_node生成） |
| message_id | String(100) | NULL, INDEX | 消息ID（关联数据源） |
| version | Integer | NOT NULL, DEFAULT 0 | 版本号（从0开始递增） |
| is_published | Boolean | NOT NULL, DEFAULT False | 是否发布 |
| source_table_name | String(200) | NULL | 数据来源表名 |
| source_record_id | String(50) | NULL | 数据来源记录ID |
| generation_status | Integer | NOT NULL, DEFAULT 0 | 生成状态（0=进行中，1=成功，-1=失败） |
| failure_reason | Text | NULL | 失败原因（包含异常堆栈信息） |
| created_at | DateTime(timezone=True) | NOT NULL | 创建时间 |
| updated_at | DateTime(timezone=True) | NULL | 更新时间 |

#### 3.1.3 字段说明

**id**
- 类型：`String(50)`
- 主键，使用 ULID 生成
- 自动生成，无需手动设置

**scene_summary**
- 类型：`Text`
- 必填字段
- 存储前置 Agent 节点输出的场景摘要

**optimization_question**
- 类型：`Text`
- 必填字段
- 存储前置 Agent 节点输出的优化后的问题

**input_tags**
- 类型：`Text`
- 可选字段
- 存储 JSON 数组格式的输入标签，例如：`["高血压", "重度偏高", "头晕"]`
- 使用 `json.dumps()` 序列化，`json.loads()` 反序列化

**response_tags**
- 类型：`Text`
- 可选字段
- 存储 JSON 数组格式的响应标签，例如：`["警示型", "预警提醒", "就医建议"]`
- 使用 `json.dumps()` 序列化，`json.loads()` 反序列化

**ai_response**
- 类型：`Text`
- 可选字段
- 存储 AI 回复内容，来自 `BloodPressureSessionRecord.new_session_response`
- 用于保存原始回复内容，便于后续查询和追溯

**embedding_value**
- 类型：`Vector(2048)`
- 可选字段
- 存储 embedding 后的向量值，维度为 2048
- 由 `embedding_node` 节点生成，在 `insert_data_to_vector_db_node` 节点中更新
- 使用 pgvector 扩展的 Vector 类型

**message_id**
- 类型：`String(100)`
- 可选字段，但建议必填（业务逻辑需要）
- 关联 `BloodPressureSessionRecord.message_id`
- 用于版本管理和数据溯源

**version**
- 类型：`Integer`
- 必填字段，默认值为 0
- 按照 `message_id` 分组，从 0 开始递增
- 同一 `message_id` 的多条记录，版本号递增

**is_published**
- 类型：`Boolean`
- 必填字段，默认值为 `False`
- 标识该记录是否已发布（用于后续的发布管理功能）

**created_at**
- 类型：`DateTime(timezone=True)`
- 必填字段
- 记录创建时间，自动设置为当前时间

**source_table_name**
- 类型：`String(200)`
- 可选字段
- 存储数据来源表名，例如：`"blood_pressure_session_records"`
- 用于数据溯源和关联查询

**source_record_id**
- 类型：`String(50)`
- 可选字段
- 存储数据来源记录的ID，例如：`BloodPressureSessionRecord.id`
- 用于数据溯源和关联查询

**generation_status**
- 类型：`Integer`
- 必填字段，默认值为 0
- 生成状态标识：
  - `0`：进行中（初始状态，before_embedding_func 插入时设置）
  - `1`：成功（insert_data_to_vector_db_node 成功时设置）
  - `-1`：失败（出现异常时设置）
- 用于跟踪数据处理流程的状态

**failure_reason**
- 类型：`Text`
- 可选字段
- 存储失败原因，包含完整的异常堆栈信息
- 当 `generation_status` 为 `-1` 时，此字段应包含详细的错误信息
- 使用 Python 的 `traceback.format_exc()` 获取完整堆栈信息

**updated_at**
- 类型：`DateTime(timezone=True)`
- 可选字段
- 记录更新时间，更新时自动设置为当前时间

### 3.2 索引设计

**当前阶段**：暂不建立索引，后续根据查询需求补充。

**建议索引**（后续补充）：
- `message_id`：用于版本查询
- `(message_id, version)`：复合索引，用于版本管理查询
- `is_published`：用于发布状态查询
- `generation_status`：用于状态查询
- `source_record_id`：用于数据溯源查询
- `created_at`：用于时间范围查询

### 3.3 数据示例

```json
{
  "id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "scene_summary": "高血压患者报告当前血压180/110mmHg，伴有头晕症状，属于重度偏高，需紧急预警。",
  "optimization_question": "我刚测血压180/110，还有点头晕，这种情况危险吗？",
  "input_tags": "[\"高血压\", \"重度偏高\", \"头晕\", \"需预警\", \"record\"]",
  "response_tags": "[\"警示型\", \"预警提醒\", \"就医建议\"]",
  "ai_response": "您本次测量的血压过高，且伴有不适症状，建议您尽快到医院就诊...",
  "embedding_value": null,
  "message_id": "msg_123456",
  "version": 0,
  "is_published": false,
  "source_table_name": "blood_pressure_session_records",
  "source_record_id": "01ARZ3NDEKTSV4RRFFQ69G5FAW",
  "generation_status": 0,
  "failure_reason": null,
  "created_at": "2026-01-23T10:30:00+08:00",
  "updated_at": null
}
```

---

## 四、数据流程设计

### 4.1 整体流程

```
┌─────────────────────────────────────────────────────────────┐
│ 前置节点：stem_extraction_node (Agent)                      │
│ 输出到 state.edges_var:                                     │
│   - scene_summary                                           │
│   - optimization_question                                   │
│   - input_tags                                              │
│   - response_tags                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ before_embedding_func 节点执行流程                            │
│                                                              │
│ 1. 读取 state.edges_var 中的数据                            │
│ 2. 读取 state.prompt_vars.source_id 和 source_table_name    │
│ 3. 根据 source_id 查询 BloodPressureSessionRecord           │
│    └─> 获取 message_id 和 new_session_response              │
│ 4. 根据 message_id 查询 embedding 表                        │
│    └─> 计算下一个 version（max(version) + 1 或 0）          │
│ 5. 插入新记录到 embedding 表                                │
│    └─> generation_status = 0（进行中）                      │
│ 6. 生成 embedding_str                                        │
│    └─> 格式：{scene_summary}\n问题：{optimization_question}  │
│        \n回复：{ai_response}                                 │
│ 7. 更新 state：                                              │
│    - state.edges_var.embedding_str                           │
│    - state.prompt_vars.embedding_records_id                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 输出：                                                        │
│ - state.edges_var.embedding_str                              │
│ - state.prompt_vars.embedding_records_id                     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 数据来源改造

#### 4.2.1 state_builder.py 改造

**文件位置**：`scripts/embedding_import/core/state_builder.py`

**改造内容**：
- 修改 `build_initial_state_from_record()` 方法
- 在返回的 `FlowState` 的 `prompt_vars` 中增加以下属性：
  - `source_id`：数据源记录ID，值为 `record.id`
  - `source_table_name`：数据来源表名，值为 `"blood_pressure_session_records"`

**改造前**：
```python
def build_initial_state_from_record(
    record: "BloodPressureSessionRecord",
    session_id: str,
    trace_id: str,
) -> FlowState:
    # ... 现有代码 ...
    return {
        "current_message": current_message,
        "history_messages": history_messages,
        "flow_msgs": [],
        "session_id": session_id,
        "token_id": TOKEN_ID_PLACEHOLDER,
        "trace_id": trace_id,
        "prompt_vars": prompt_vars,
    }
```

**改造后**：
```python
def build_initial_state_from_record(
    record: "BloodPressureSessionRecord",
    session_id: str,
    trace_id: str,
) -> FlowState:
    # ... 现有代码 ...
    # 在 prompt_vars 中增加数据源信息
    prompt_vars["source_id"] = record.id  # 数据源记录ID
    prompt_vars["source_table_name"] = "blood_pressure_session_records"  # 数据来源表名
    
    return {
        "current_message": current_message,
        "history_messages": history_messages,
        "flow_msgs": [],
        "session_id": session_id,
        "token_id": TOKEN_ID_PLACEHOLDER,
        "trace_id": trace_id,
        "prompt_vars": prompt_vars,
    }
```

#### 4.2.2 数据流转说明

1. **脚本执行阶段**（`run_embedding_import.py`）：
   - 从 `blood_pressure_session_records` 表读取记录
   - 调用 `build_initial_state_from_record()` 组装初始状态
   - `state.prompt_vars.source_id` 被设置为 `record.id`
   - `state.prompt_vars.source_table_name` 被设置为 `"blood_pressure_session_records"`

2. **Agent 节点执行阶段**（`stem_extraction_node`）：
   - Agent 节点读取 `state.prompt_vars` 中的数据
   - Agent 节点输出 JSON 格式数据到 `state.edges_var`
   - `state.edges_var` 现在包含：
     - `scene_summary`：场景摘要（Agent 输出）
     - `optimization_question`：优化后的问题（Agent 输出）
     - `input_tags`：输入标签（Agent 输出）
     - `response_tags`：响应标签（Agent 输出）
   - 注意：`state.prompt_vars` 保持不变，包含 `source_id` 和 `source_table_name`

3. **Function 节点执行阶段**（`before_embedding_func`）：
   - 读取 `state.prompt_vars.source_id` 和 `state.prompt_vars.source_table_name`
   - 读取 `state.edges_var` 中的 Agent 输出数据
   - 根据 `source_id` 查询 `BloodPressureSessionRecord` 表
   - 获取 `message_id` 和 `new_session_response`
   - 执行数据插入和 `embedding_str` 生成逻辑
   - 将 embedding 记录 ID 存储到 `state.prompt_vars.embedding_records_id`

### 4.3 embedding_str 生成规则

#### 4.3.1 数据来源

- `scene_summary`：来自 `state.edges_var.scene_summary`
- `optimization_question`：来自 `state.edges_var.optimization_question`
- `ai_response`：来自 `BloodPressureSessionRecord.new_session_response`

#### 4.3.2 拼接格式

```
{scene_summary}
问题：{optimization_question}
回复：{ai_response}
```

#### 4.3.3 示例

**输入数据**：
- `scene_summary`: "高血压患者报告当前血压180/110mmHg，伴有头晕症状，属于重度偏高，需紧急预警。"
- `optimization_question`: "我刚测血压180/110，还有点头晕，这种情况危险吗？"
- `ai_response`: "您本次测量的血压过高，且伴有不适症状，建议您尽快到医院就诊..."

**生成的 embedding_str**：
```
高血压患者报告当前血压180/110mmHg，伴有头晕症状，属于重度偏高，需紧急预警。
问题：我刚测血压180/110，还有点头晕，这种情况危险吗？
回复：您本次测量的血压过高，且伴有不适症状，建议您尽快到医院就诊...
```

#### 4.3.4 边界处理

- 如果 `scene_summary` 为空，使用空字符串
- 如果 `optimization_question` 为空，使用空字符串
- 如果 `ai_response` 为空或 None，使用空字符串
- 所有字段都进行 `strip()` 处理，去除首尾空白

### 4.4 generation_status 状态流转

#### 4.4.1 状态说明

`generation_status` 字段用于跟踪 embedding 数据处理流程的状态：

- **0（进行中）**：`before_embedding_func` 节点插入记录时设置，表示数据处理流程已开始
- **1（成功）**：`insert_data_to_vector_db_node` 节点成功完成后设置，表示整个流程成功完成
- **-1（失败）**：任何节点出现异常时设置，表示流程失败

#### 4.4.2 状态流转图

```
before_embedding_func 插入记录
    ↓
generation_status = 0（进行中）
    ↓
embedding_node 执行
    ↓
insert_data_to_vector_db_node 执行
    ├─> 成功 → generation_status = 1（成功）
    └─> 失败 → generation_status = -1（失败）+ failure_reason
```

#### 4.4.3 状态更新机制

1. **before_embedding_func 节点**：
   - 插入记录时，`generation_status` 设置为 `0`
   - `failure_reason` 为 `NULL`

2. **insert_data_to_vector_db_node 节点**：
   - 根据 `state.prompt_vars.embedding_records_id` 查询记录
   - 成功时：更新 `generation_status = 1`
   - 失败时：更新 `generation_status = -1`，并记录 `failure_reason`（包含异常堆栈信息）

3. **异常处理**：
   - 如果 `before_embedding_func` 节点执行失败，记录不会插入，流程直接中断
   - 如果后续节点执行失败，已插入的记录会被更新为失败状态

---

## 五、实现方案

### 5.1 数据库模型实现

#### 5.1.1 文件位置
```
backend/infrastructure/database/models/embedding_record.py
```

#### 5.1.2 模型定义

```python
"""
Embedding 记录模型
用于存储词干提取后的结构化数据
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func as sql_func

from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid


class EmbeddingRecord(Base):
    """Embedding 记录模型"""
    
    __tablename__ = f"{TABLE_PREFIX}embedding_records"
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="记录ID（ULID）"
    )
    scene_summary = Column(
        Text,
        nullable=False,
        comment="场景摘要"
    )
    optimization_question = Column(
        Text,
        nullable=False,
        comment="优化后的问题"
    )
    input_tags = Column(
        Text,
        nullable=True,
        comment="输入标签（JSON数组字符串）"
    )
    response_tags = Column(
        Text,
        nullable=True,
        comment="响应标签（JSON数组字符串）"
    )
    ai_response = Column(
        Text,
        nullable=True,
        comment="AI回复内容（来自原始表的new_session_response）"
    )
    embedding_value = Column(
        Vector(2048) if HAS_PGVECTOR else Text,
        nullable=True,
        comment="Embedding向量值（2048维，由embedding_node生成）"
    )
    message_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="消息ID（关联数据源）"
    )
    version = Column(
        Integer,
        nullable=False,
        default=0,
        comment="版本号（从0开始递增）"
    )
    is_published = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="是否发布"
    )
    source_table_name = Column(
        String(200),
        nullable=True,
        comment="数据来源表名"
    )
    source_record_id = Column(
        String(50),
        nullable=True,
        comment="数据来源记录ID"
    )
    generation_status = Column(
        Integer,
        nullable=False,
        default=0,
        comment="生成状态（0=进行中，1=成功，-1=失败）"
    )
    failure_reason = Column(
        Text,
        nullable=True,
        comment="失败原因（包含异常堆栈信息）"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sql_func.now(),
        default=sql_func.now(),
        comment="创建时间（自动生成）"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=sql_func.now(),
        comment="更新时间（自动更新）"
    )
    
    def __repr__(self):
        return (
            f"<EmbeddingRecord(id={self.id}, "
            f"message_id={self.message_id}, "
            f"version={self.version}, "
            f"generation_status={self.generation_status})>"
        )
```

### 5.2 Function 节点实现

#### 5.2.1 文件位置
```
backend/domain/flows/implementations/before_embedding_func.py
```

#### 5.2.2 实现要点

1. **继承 BaseFunctionNode**
   - 实现 `get_key()` 方法，返回 `"before_embedding_func"`
   - 实现 `execute()` 方法，执行节点逻辑

2. **数据读取**
   - 从 `state.edges_var` 读取 Agent 输出数据
   - 从 `state.prompt_vars.source_id` 读取数据源ID
   - 从 `state.prompt_vars.source_table_name` 读取数据来源表名

3. **数据库操作**
   - 使用异步数据库会话（通过依赖注入或全局获取）
   - 查询 `BloodPressureSessionRecord` 表
   - 查询 `EmbeddingRecord` 表（计算版本号）
   - 插入新记录到 `EmbeddingRecord` 表

4. **embedding_str 生成**
   - 从多个数据源获取字段
   - 按照格式拼接字符串
   - 存储到 `state.edges_var.embedding_str`

5. **状态更新**
   - 将插入的 embedding 记录 ID 存储到 `state.prompt_vars.embedding_records_id`
   - 供后续节点使用

6. **错误处理**
   - 使用 try-except 捕获异常
   - 记录详细的错误日志（包含完整堆栈信息）
   - 如果数据插入失败，抛出异常中断流程
   - 确保数据一致性，不采用降级策略

#### 5.2.3 伪代码

```python
async def execute(self, state: FlowState) -> FlowState:
    """
    执行 before_embedding_func 节点逻辑
    """
    import traceback
    
    try:
        # 1. 读取 edges_var 中的数据
        edges_var = state.get("edges_var", {})
        scene_summary = edges_var.get("scene_summary", "")
        optimization_question = edges_var.get("optimization_question", "")
        input_tags = edges_var.get("input_tags", [])
        response_tags = edges_var.get("response_tags", [])
        
        # 2. 读取 prompt_vars 中的数据源信息
        prompt_vars = state.get("prompt_vars", {})
        source_id = prompt_vars.get("source_id")
        source_table_name = prompt_vars.get("source_table_name")
        
        # 3. 验证必要字段
        if not source_id:
            raise ValueError("prompt_vars.source_id 缺失，无法继续执行")
        if not source_table_name:
            raise ValueError("prompt_vars.source_table_name 缺失，无法继续执行")
        
        # 4. 查询 BloodPressureSessionRecord
        record = await get_blood_pressure_session_record(source_id)
        if not record:
            raise ValueError(f"未找到 source_id={source_id} 的记录")
        
        message_id = record.message_id
        
        # 5. 计算版本号
        version = await calculate_next_version(message_id)
        
        # 6. 插入 embedding 记录
        embedding_record = await insert_embedding_record(
            scene_summary=scene_summary,
            optimization_question=optimization_question,
            input_tags=input_tags,
            response_tags=response_tags,
            message_id=message_id,
            version=version,
            source_table_name=source_table_name,
            source_record_id=source_id,
            generation_status=0,  # 进行中
        )
        
        # 7. 生成 embedding_str
        ai_response = record.new_session_response or ""
        embedding_str = format_embedding_str(
            scene_summary=scene_summary,
            optimization_question=optimization_question,
            ai_response=ai_response,
        )
        
        # 8. 更新 state
        new_state = state.copy()
        if "edges_var" not in new_state:
            new_state["edges_var"] = {}
        new_state["edges_var"]["embedding_str"] = embedding_str
        
        if "prompt_vars" not in new_state:
            new_state["prompt_vars"] = {}
        new_state["prompt_vars"]["embedding_records_id"] = embedding_record.id
        
        return new_state
        
    except Exception as e:
        # 记录完整的异常堆栈信息
        error_traceback = traceback.format_exc()
        logger.error(f"before_embedding_func 执行失败: {e}\n{error_traceback}")
        
        # 如果已经创建了 embedding 记录，更新其状态为失败
        # （这种情况理论上不应该发生，因为插入失败会抛出异常）
        
        # 抛出异常，中断流程
        raise
```

### 5.3 Repository 实现（可选）

如果需要封装数据库操作，可以创建 Repository 类：

#### 5.3.1 文件位置
```
backend/infrastructure/database/repositories/embedding_repository.py
```

#### 5.3.2 主要方法

- `get_max_version_by_message_id(message_id: str) -> int`：获取指定 message_id 的最大版本号
- `create_embedding_record(...)`：创建新的 embedding 记录
- `get_embedding_record_by_id(id: str)`：根据 ID 查询记录

### 5.4 数据库迁移

需要创建 Alembic 迁移文件，创建 `gd2502_embedding_records` 表。

---

## 六、代码结构

### 6.1 文件清单

```
backend/
├── domain/
│   └── flows/
│       └── implementations/
│           └── before_embedding_func.py          # Function 节点实现
├── infrastructure/
│   └── database/
│       ├── models/
│       │   └── embedding_record.py               # 数据库模型
│       └── repositories/
│           └── embedding_repository.py            # Repository
scripts/
└── embedding_import/
    └── core/
        └── state_builder.py                      # 改造：增加 source_id
```

### 6.2 依赖关系

```
before_embedding_func.py
    ├── 依赖 BaseFunctionNode（基类）
    ├── 依赖 FlowState（状态类型）
    ├── 依赖 EmbeddingRecord（数据库模型）
    ├── 依赖 BloodPressureSessionRecord（数据库模型）
    └── 依赖数据库会话（异步）
```

### 6.3 导入关系

```python
# before_embedding_func.py
from backend.domain.state import FlowState
from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.infrastructure.database.models.embedding_record import EmbeddingRecord
from backend.infrastructure.database.models.blood_pressure_session import (
    BloodPressureSessionRecord,
)
```

---

## 七、测试方案

### 7.1 单元测试

#### 7.1.1 测试文件位置
```
cursor_test/test_before_embedding_func.py
```

#### 7.1.2 测试用例

1. **正常流程测试**
   - 测试完整的数据插入和 embedding_str 生成流程
   - 验证数据库记录是否正确插入
   - 验证 embedding_str 格式是否正确

2. **版本号计算测试**
   - 测试 message_id 不存在时，版本号为 0
   - 测试 message_id 存在时，版本号递增
   - 测试多个 message_id 的版本号独立计算

3. **边界情况测试**
   - 测试 source_id 缺失的情况（应抛出异常）
   - 测试 source_table_name 缺失的情况（应抛出异常）
   - 测试必要字段缺失的情况（应抛出异常）
   - 测试 ai_response 为空的情况
   - 测试字段值为空字符串的情况

4. **错误处理测试**
   - 测试数据库操作失败时是否抛出异常
   - 测试异常情况下的日志记录（包含堆栈信息）
   - 测试异常时 failure_reason 是否正确记录

### 7.2 集成测试

#### 7.2.1 测试场景

1. **完整流程测试**
   - 从 `run_embedding_import.py` 开始执行
   - 验证整个 embedding_agent 流程是否正常
   - 验证数据是否正确流转

2. **数据一致性测试**
   - 验证插入的 embedding 记录与原始数据的一致性
   - 验证 embedding_str 的内容是否正确
   - 验证 embedding_records_id 是否正确传递到后续节点

3. **状态流转测试**
   - 验证 generation_status 的初始值为 0
   - 验证后续节点能够根据 embedding_records_id 更新状态

### 7.3 测试数据准备

- 准备测试用的 `BloodPressureSessionRecord` 数据
- 准备不同版本的 embedding 记录数据
- 准备边界情况的测试数据

---

## 八、后续优化

### 8.1 性能优化

- 考虑批量插入操作（如果有多条记录需要插入）
- 优化版本号查询（使用数据库聚合函数）
- 添加数据库索引（根据实际查询需求）

### 8.2 功能扩展

- 支持更新已存在的 embedding 记录
- 支持删除 embedding 记录
- 支持发布管理功能（基于 `is_published` 字段）

### 8.3 监控和日志

- 添加详细的执行日志
- 添加性能监控指标（执行时间、数据库操作耗时等）
- 添加错误告警机制

---

## 九、附录

### 9.1 相关文件

- `config/flows/embedding_agent/flow.yaml`：流程定义文件
- `config/flows/embedding_agent/prompts/20-ext_agent.md`：Agent 提示词文件
- `backend/domain/state.py`：状态定义
- `backend/infrastructure/database/models/blood_pressure_session.py`：数据源模型
- `scripts/embedding_import/core/state_builder.py`：状态构建器

### 9.2 参考文档

- Function 节点实现规范：参考 `query_user_info_node.py`
- 数据库模型规范：参考 `blood_pressure_session.py`
- 状态管理规范：参考 `state.py`

---

## 十一、开发进度

### 11.1 完成情况

| 任务项 | 状态 | 完成时间 | 说明 |
|--------|------|----------|------|
| 数据库模型 EmbeddingRecord | ✅ 已完成 | 2026-01-23 | 已创建模型文件，包含所有必需字段 |
| 模型导入 | ✅ 已完成 | 2026-01-23 | 已在 models/__init__.py 中导入 |
| Alembic 迁移文件 | ✅ 已完成 | 2026-01-23 | 已生成并执行迁移，表已创建 |
| before_embedding_func 节点实现 | ✅ 已完成 | 2026-01-23 | 已实现完整的节点逻辑 |
| state_builder.py 改造 | ✅ 已完成 | 2026-01-23 | 已增加 source_id 和 source_table_name |
| 数据库表创建 | ✅ 已完成 | 2026-01-23 | 已执行 alembic upgrade head，表已创建 |
| ai_response 字段补充 | ✅ 已完成 | 2026-01-23 | 已添加 ai_response 字段并执行迁移 |
| embedding_value 字段补充 | ✅ 已完成 | 2026-01-23 | 已添加 embedding_value 字段（Vector(2048)）并执行迁移 |

### 11.2 已实现功能

1. **数据库模型** (`backend/infrastructure/database/models/embedding_record.py`)
   - ✅ 完整的字段定义（包括新增的 source_table_name、source_record_id、generation_status、failure_reason、ai_response、embedding_value）
   - ✅ JSON 标签的序列化/反序列化辅助方法
   - ✅ 完整的类型提示和文档字符串

2. **Function 节点** (`backend/domain/flows/implementations/before_embedding_func.py`)
   - ✅ 从 `state.edges_var` 读取 Agent 输出数据
   - ✅ 从 `state.prompt_vars` 读取数据源信息
   - ✅ 查询 `BloodPressureSessionRecord` 表
   - ✅ 计算版本号（按 message_id 分组递增）
   - ✅ 插入 embedding 记录（generation_status=0），包含 ai_response 字段
   - ✅ 生成 `embedding_str` 并存储到 `state.edges_var.embedding_str`
   - ✅ 将记录 ID 存储到 `state.prompt_vars.embedding_records_id`
   - ✅ 完整的错误处理和异常堆栈记录

3. **状态构建器改造** (`scripts/embedding_import/core/state_builder.py`)
   - ✅ 在 `prompt_vars` 中增加 `source_id`
   - ✅ 在 `prompt_vars` 中增加 `source_table_name`

4. **数据库迁移**
   - ✅ 迁移文件已生成：`alembic/versions/9a6d8edb7942_add_embedding_records_table.py`
   - ✅ 迁移已执行，表已创建：`gd2502_embedding_records`
   - ✅ 迁移文件已生成：`alembic/versions/4d076248e1b9_add_ai_response_field_to_embedding_.py`
   - ✅ 迁移已执行，ai_response 字段已添加
   - ✅ 迁移文件已生成：`alembic/versions/52d7e028101e_add_embedding_value_field_to_embedding_.py`
   - ✅ 迁移已执行，embedding_value 字段已添加（Vector(2048)）

### 11.3 待测试功能

1. **单元测试**
   - ⏳ 正常流程测试
   - ⏳ 版本号计算测试
   - ⏳ 边界情况测试
   - ⏳ 错误处理测试

2. **集成测试**
   - ⏳ 完整流程测试（从 run_embedding_import.py 开始）
   - ⏳ 数据一致性测试

### 11.4 注意事项

1. **迁移文件说明**：生成的迁移文件包含了其他表的变更（greeting_examples、qa_examples 等），这些是 Alembic 自动检测到的未提交变更。迁移已成功执行。

2. **错误处理策略**：按照设计要求，如果数据插入失败，节点会抛出异常中断流程，不采用降级策略。

3. **数据源位置**：数据源信息（source_id、source_table_name）存储在 `prompt_vars` 中，而不是 `edges_var`，因为 `edges_var` 在节点之间会被重新创建。

---

## 十、变更记录

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| V1.3 | 2026-01-23 | 开发团队 | 增加 embedding_value 字段（Vector(2048)），用于存储 embedding 后的向量值 |
| V1.2 | 2026-01-23 | 开发团队 | 增加 ai_response 字段，用于存储原始表的 new_session_response 内容 |
| V1.1 | 2026-01-23 | 开发团队 | 修正数据源位置（prompt_vars）、增加输出字段、修正错误处理策略、增加数据库字段 |
| V1.0 | 2026-01-23 | 开发团队 | 初始版本 |
