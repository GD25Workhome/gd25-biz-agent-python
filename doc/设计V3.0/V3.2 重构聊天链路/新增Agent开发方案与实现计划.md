# 新增Agent开发方案与实现计划

## 1. 概述

### 1.1 需求背景

根据需求文档，需要在现有系统基础上新增三个Agent：
1. **健康事件记录Agent**：记录用户的健康事件（如体检、检查、手术等）
2. **用药记录Agent**：记录用户的用药信息（药物名称、剂量、频率等）
3. **症状记录Agent**：记录用户的症状信息（症状描述、严重程度、持续时间等）

### 1.2 参考实现

所有新增Agent的实现方式参考现有的**血压记录Agent**（`blood_pressure_agent`）的实现模式。

### 1.3 核心要求

- 所有数据必须能够入库（需要创建数据库模型和Repository）
- 实现方式与血压Agent保持一致
- 支持记录、查询、更新三种基本操作
- 支持多轮对话和槽位填充

## 2. 架构分析

### 2.1 现有架构组件

基于对现有代码的分析，每个Agent需要以下组件：

#### 2.1.1 数据库层
- **Model**：数据库模型（`infrastructure/database/models/`）
- **Repository**：数据访问层（`infrastructure/database/repository/`）

#### 2.1.2 工具层
- **Record Tool**：记录工具（`domain/tools/{agent_name}/record.py`）
- **Query Tool**：查询工具（`domain/tools/{agent_name}/query.py`）
- **Update Tool**：更新工具（`domain/tools/{agent_name}/update.py`）
- **工具注册**：在 `domain/tools/registry.py` 中注册

#### 2.1.3 Agent层
- **Agent配置**：在 `config/agents.yaml` 中配置
- **提示词模块**：在 `config/prompts/modules/{agent_name}/` 下创建提示词文件
- **Agent工厂**：通过 `domain/agents/factory.py` 创建

#### 2.1.4 路由层
- **意图识别**：在 `domain/router/tools/router_tools.py` 中添加新意图
- **路由节点**：在 `domain/router/node.py` 中添加路由逻辑
- **路由图**：在 `domain/router/graph.py` 中注册Agent节点

### 2.2 数据模型设计

#### 2.2.1 健康事件记录（HealthEventRecord）

```python
字段设计：
- id: 记录ID（主键，UUID）
- user_id: 用户ID（必填，索引）
- event_type: 事件类型（必填，如：体检、检查、手术、疫苗接种等）
- event_name: 事件名称（必填，如：年度体检、血常规检查等）
- event_date: 事件日期（可选，DateTime）
- location: 发生地点（可选，如：医院名称）
- description: 事件描述（可选，Text）
- notes: 备注（可选，Text）
- created_at: 创建时间（自动）
- updated_at: 更新时间（自动）
```

#### 2.2.2 用药记录（MedicationRecord）

```python
字段设计：
- id: 记录ID（主键，UUID）
- user_id: 用户ID（必填，索引）
- medication_name: 药物名称（必填）
- dosage: 剂量（必填，如：10mg、1片等）
- frequency: 用药频率（必填，如：每日一次、每日三次等）
- start_date: 开始日期（可选，DateTime）
- end_date: 结束日期（可选，DateTime）
- doctor_name: 开药医生（可选）
- purpose: 用药目的（可选，如：降血压、治疗感冒等）
- notes: 备注（可选，Text）
- created_at: 创建时间（自动）
- updated_at: 更新时间（自动）
```

#### 2.2.3 症状记录（SymptomRecord）

```python
字段设计：
- id: 记录ID（主键，UUID）
- user_id: 用户ID（必填，索引）
- symptom_name: 症状名称（必填，如：头痛、发热、咳嗽等）
- severity: 严重程度（可选，如：轻微、中等、严重）
- start_time: 开始时间（可选，DateTime）
- end_time: 结束时间（可选，DateTime）
- duration: 持续时间（可选，如：2小时、3天等）
- location: 症状部位（可选，如：头部、胸部等）
- description: 症状描述（可选，Text）
- notes: 备注（可选，Text）
- created_at: 创建时间（自动）
- updated_at: 更新时间（自动）
```

## 3. 开发方案

### 3.1 开发原则

1. **一致性**：所有新增Agent的实现方式与血压Agent保持一致
2. **模块化**：每个组件独立开发，便于测试和维护
3. **可扩展性**：预留扩展接口，便于后续功能增强
4. **数据完整性**：所有数据必须入库，支持查询和更新

### 3.2 开发步骤

#### 阶段一：数据库层开发

**任务1.1：创建数据库模型**

- 文件：`infrastructure/database/models/health_event.py`
- 文件：`infrastructure/database/models/medication.py`
- 文件：`infrastructure/database/models/symptom.py`
- 参考：`infrastructure/database/models/blood_pressure.py`

**任务1.2：创建Repository**

- 文件：`infrastructure/database/repository/health_event_repository.py`
- 文件：`infrastructure/database/repository/medication_repository.py`
- 文件：`infrastructure/database/repository/symptom_repository.py`
- 参考：`infrastructure/database/repository/blood_pressure_repository.py`

**任务1.3：数据库迁移**

- 创建数据库迁移脚本（如使用Alembic）
- 执行迁移，创建数据表

#### 阶段二：工具层开发

**任务2.1：创建工具目录结构**

```
domain/tools/
├── health_event/
│   ├── __init__.py
│   ├── record.py
│   ├── query.py
│   └── update.py
├── medication/
│   ├── __init__.py
│   ├── record.py
│   ├── query.py
│   └── update.py
└── symptom/
    ├── __init__.py
    ├── record.py
    ├── query.py
    └── update.py
```

**任务2.2：实现工具函数**

每个工具需要实现：
- `record_{agent_name}`：记录数据
- `query_{agent_name}`：查询数据
- `update_{agent_name}`：更新数据

参考实现：`domain/tools/blood_pressure/`

**任务2.3：注册工具**

在 `domain/tools/registry.py` 的 `init_tools()` 函数中注册所有新工具。

#### 阶段三：Agent配置与提示词

**任务3.1：创建提示词模块目录**

```
config/prompts/modules/
├── health_event/
│   ├── role.txt
│   ├── function_description.txt
│   ├── clarification.txt
│   ├── data_validation.txt
│   ├── response_format.txt
│   ├── few_shot_examples.txt
│   └── notes.txt
├── medication/
│   └── (同上)
└── symptom/
    └── (同上)
```

**任务3.2：编写提示词内容**

参考：`config/prompts/modules/blood_pressure/`

**任务3.3：配置Agent**

在 `config/agents.yaml` 中添加三个Agent配置：
- `health_event_agent`
- `medication_agent`
- `symptom_agent`

#### 阶段四：路由层集成

**任务4.1：更新意图识别**

在 `domain/router/tools/router_tools.py` 中：
- 更新 `INTENT_IDENTIFICATION_PROMPT_FALLBACK`，添加新意图类型
- 更新 `_parse_intent_result()` 函数，添加新意图验证
- 更新 `identify_intent()` 工具的描述

**任务4.2：更新路由节点**

在 `domain/router/node.py` 中：
- 在 `route_node()` 函数中添加新意图到Agent的映射

**任务4.3：更新路由图**

在 `domain/router/graph.py` 中：
- 创建新Agent节点
- 在 `route_to_agent()` 函数中添加路由逻辑

**任务4.4：更新澄清提示词**

在 `domain/router/tools/router_tools.py` 中：
- 更新 `CLARIFY_INTENT_PROMPT_FALLBACK`，添加新功能说明

## 4. 详细实现计划

### 4.1 阶段一：数据库层（预计2-3天）

#### 4.1.1 创建健康事件模型

**文件**：`infrastructure/database/models/health_event.py`

```python
"""
健康事件记录模型
"""
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Text, func
from infrastructure.database.base import Base

class HealthEventRecord(Base):
    """健康事件记录模型"""
    __tablename__ = "biz_agent_health_event_records"
    
    id = Column(String(50), primary_key=True, index=True, default=lambda: uuid4().hex)
    user_id = Column(String(50), nullable=False, index=True, comment="用户ID")
    event_type = Column(String(100), nullable=False, comment="事件类型")
    event_name = Column(String(200), nullable=False, comment="事件名称")
    event_date = Column(DateTime(timezone=True), nullable=True, index=True, comment="事件日期")
    location = Column(String(200), nullable=True, comment="发生地点")
    description = Column(Text, nullable=True, comment="事件描述")
    notes = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime(timezone=True), nullable=True, comment="创建时间")
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment="更新时间")
```

#### 4.1.2 创建用药记录模型

**文件**：`infrastructure/database/models/medication.py`

```python
"""
用药记录模型
"""
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Text, func
from infrastructure.database.base import Base

class MedicationRecord(Base):
    """用药记录模型"""
    __tablename__ = "biz_agent_medication_records"
    
    id = Column(String(50), primary_key=True, index=True, default=lambda: uuid4().hex)
    user_id = Column(String(50), nullable=False, index=True, comment="用户ID")
    medication_name = Column(String(200), nullable=False, comment="药物名称")
    dosage = Column(String(100), nullable=False, comment="剂量")
    frequency = Column(String(100), nullable=False, comment="用药频率")
    start_date = Column(DateTime(timezone=True), nullable=True, index=True, comment="开始日期")
    end_date = Column(DateTime(timezone=True), nullable=True, comment="结束日期")
    doctor_name = Column(String(100), nullable=True, comment="开药医生")
    purpose = Column(String(200), nullable=True, comment="用药目的")
    notes = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime(timezone=True), nullable=True, comment="创建时间")
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment="更新时间")
```

#### 4.1.3 创建症状记录模型

**文件**：`infrastructure/database/models/symptom.py`

```python
"""
症状记录模型
"""
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Text, func
from infrastructure.database.base import Base

class SymptomRecord(Base):
    """症状记录模型"""
    __tablename__ = "biz_agent_symptom_records"
    
    id = Column(String(50), primary_key=True, index=True, default=lambda: uuid4().hex)
    user_id = Column(String(50), nullable=False, index=True, comment="用户ID")
    symptom_name = Column(String(200), nullable=False, comment="症状名称")
    severity = Column(String(50), nullable=True, comment="严重程度")
    start_time = Column(DateTime(timezone=True), nullable=True, index=True, comment="开始时间")
    end_time = Column(DateTime(timezone=True), nullable=True, comment="结束时间")
    duration = Column(String(100), nullable=True, comment="持续时间")
    location = Column(String(200), nullable=True, comment="症状部位")
    description = Column(Text, nullable=True, comment="症状描述")
    notes = Column(Text, nullable=True, comment="备注")
    created_at = Column(DateTime(timezone=True), nullable=True, comment="创建时间")
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now(), comment="更新时间")
```

#### 4.1.4 创建Repository实现

参考 `infrastructure/database/repository/blood_pressure_repository.py` 的实现模式，为每个模型创建对应的Repository，实现：
- `get_by_user_id()`：根据用户ID查询
- `get_by_date_range()`：根据日期范围查询
- 继承 `BaseRepository` 的通用方法（create, update, delete等）

### 4.2 阶段二：工具层（预计3-4天）

#### 4.2.1 实现记录工具

每个Agent需要实现 `record_{agent_name}` 工具，参考 `domain/tools/blood_pressure/record.py`：

- 参数验证
- 数据解析（时间格式等）
- 调用Repository保存数据
- 返回友好的成功消息

#### 4.2.2 实现查询工具

每个Agent需要实现 `query_{agent_name}` 工具，参考 `domain/tools/blood_pressure/query.py`：

- 支持按用户ID查询
- 支持按日期范围查询
- 格式化返回结果

#### 4.2.3 实现更新工具

每个Agent需要实现 `update_{agent_name}` 工具，参考 `domain/tools/blood_pressure/update.py`：

- 根据ID查找记录
- 更新指定字段
- 返回更新结果

#### 4.2.4 注册工具

在 `domain/tools/registry.py` 中更新 `init_tools()` 函数：

```python
def init_tools():
    # ... 现有工具导入 ...
    
    # 导入健康事件工具
    from domain.tools.health_event.record import record_health_event
    from domain.tools.health_event.query import query_health_event
    from domain.tools.health_event.update import update_health_event
    
    # 导入用药记录工具
    from domain.tools.medication.record import record_medication
    from domain.tools.medication.query import query_medication
    from domain.tools.medication.update import update_medication
    
    # 导入症状记录工具
    from domain.tools.symptom.record import record_symptom
    from domain.tools.symptom.query import query_symptom
    from domain.tools.symptom.update import update_symptom
    
    # 注册工具
    register_tool("record_health_event", record_health_event)
    register_tool("query_health_event", query_health_event)
    register_tool("update_health_event", update_health_event)
    
    register_tool("record_medication", record_medication)
    register_tool("query_medication", query_medication)
    register_tool("update_medication", update_medication)
    
    register_tool("record_symptom", record_symptom)
    register_tool("query_symptom", query_symptom)
    register_tool("update_symptom", update_symptom)
```

### 4.3 阶段三：Agent配置与提示词（预计2-3天）

#### 4.3.1 创建提示词模块

为每个Agent创建提示词模块目录，包含以下文件：

- `role.txt`：Agent角色定义
- `function_description.txt`：功能说明
- `clarification.txt`：澄清机制说明
- `data_validation.txt`：数据验证规则
- `response_format.txt`：回复格式要求
- `few_shot_examples.txt`：示例对话
- `notes.txt`：注意事项

#### 4.3.2 配置Agent

在 `config/agents.yaml` 中添加配置：

```yaml
agents:
  # ... 现有Agent配置 ...
  
  # 健康事件记录智能体
  health_event_agent:
    name: "健康事件记录智能体"
    description: "负责处理用户健康事件相关的请求，包括记录、查询和更新健康事件数据"
    llm:
      temperature: 0.0
    tools:
      - record_health_event
      - query_health_event
      - update_health_event
    system_prompt_path: "config/prompts/modules/health_event/role.txt"
  
  # 用药记录智能体
  medication_agent:
    name: "用药记录智能体"
    description: "负责处理用户用药相关的请求，包括记录、查询和更新用药数据"
    llm:
      temperature: 0.0
    tools:
      - record_medication
      - query_medication
      - update_medication
    system_prompt_path: "config/prompts/modules/medication/role.txt"
  
  # 症状记录智能体
  symptom_agent:
    name: "症状记录智能体"
    description: "负责处理用户症状相关的请求，包括记录、查询和更新症状数据"
    llm:
      temperature: 0.0
    tools:
      - record_symptom
      - query_symptom
      - update_symptom
    system_prompt_path: "config/prompts/modules/symptom/role.txt"
```

### 4.4 阶段四：路由层集成（预计2-3天）

#### 4.4.1 更新意图识别

在 `domain/router/tools/router_tools.py` 中：

1. **更新意图类型列表**：
```python
valid_intents = ["blood_pressure", "appointment", "health_event", "medication", "symptom", "unclear"]
```

2. **更新意图识别提示词**：
```python
INTENT_IDENTIFICATION_PROMPT_FALLBACK = """你是一个智能路由助手，负责识别用户的真实意图。

支持的意图类型：
1. blood_pressure: 用户想要记录、查询或管理血压数据
2. appointment: 用户想要预约、查询或管理复诊
3. health_event: 用户想要记录、查询或管理健康事件（体检、检查、手术等）
4. medication: 用户想要记录、查询或管理用药信息
5. symptom: 用户想要记录、查询或管理症状信息
6. unclear: 意图不明确，需要进一步澄清
...
"""
```

#### 4.4.2 更新路由节点

在 `domain/router/node.py` 的 `route_node()` 函数中：

```python
# 根据意图确定智能体
if new_intent == "blood_pressure":
    new_agent = "blood_pressure_agent"
elif new_intent == "appointment":
    new_agent = "appointment_agent"
elif new_intent == "health_event":
    new_agent = "health_event_agent"
elif new_intent == "medication":
    new_agent = "medication_agent"
elif new_intent == "symptom":
    new_agent = "symptom_agent"
else:
    new_agent = None  # unclear 意图，需要澄清
```

#### 4.4.3 更新路由图

在 `domain/router/graph.py` 中：

1. **创建Agent节点**：
```python
# 添加健康事件Agent节点
health_event_agent = AgentFactory.create_agent("health_event_agent")
workflow.add_node("health_event_agent", with_user_context(health_event_agent, "health_event_agent"))

# 添加用药记录Agent节点
medication_agent = AgentFactory.create_agent("medication_agent")
workflow.add_node("medication_agent", with_user_context(medication_agent, "medication_agent"))

# 添加症状记录Agent节点
symptom_agent = AgentFactory.create_agent("symptom_agent")
workflow.add_node("symptom_agent", with_user_context(symptom_agent, "symptom_agent"))
```

2. **更新路由逻辑**：
```python
def route_to_agent(state: RouterState) -> str:
    # ... 现有逻辑 ...
    
    # 根据智能体路由
    if current_agent == "blood_pressure_agent":
        return "blood_pressure_agent"
    elif current_agent == "appointment_agent":
        return "appointment_agent"
    elif current_agent == "health_event_agent":
        return "health_event_agent"
    elif current_agent == "medication_agent":
        return "medication_agent"
    elif current_agent == "symptom_agent":
        return "symptom_agent"
    else:
        return END
```

#### 4.4.4 更新澄清提示词

在 `domain/router/tools/router_tools.py` 中更新 `CLARIFY_INTENT_PROMPT_FALLBACK`：

```python
CLARIFY_INTENT_PROMPT_FALLBACK = """你是一个友好的助手，当用户的意图不明确时，你需要友好地引导用户说明他们的需求。

系统支持的功能：
1. 记录血压：帮助用户记录、查询和管理血压数据（收缩压、舒张压、心率等）
2. 预约复诊：帮助用户创建、查询和管理预约（科室、时间、医生等）
3. 记录健康事件：帮助用户记录、查询和管理健康事件（体检、检查、手术等）
4. 记录用药：帮助用户记录、查询和管理用药信息（药物名称、剂量、频率等）
5. 记录症状：帮助用户记录、查询和管理症状信息（症状描述、严重程度、持续时间等）

用户消息: {query}

请生成一个友好的澄清问题，引导用户说明他们的具体需求。
**重要要求**：
- 澄清问题必须明确提到所有功能
- 问题应该简洁明了，不超过100字
- 使用友好、专业的语言
- 不要使用技术术语，使用用户容易理解的语言
"""
```

## 5. 测试计划

### 5.1 单元测试

为每个组件编写单元测试：

- **数据库模型测试**：验证模型定义正确
- **Repository测试**：验证CRUD操作
- **工具测试**：验证工具函数逻辑
- **Agent测试**：验证Agent创建和配置

### 5.2 集成测试

- **端到端测试**：测试完整的对话流程
- **多轮对话测试**：测试槽位填充和上下文理解
- **意图识别测试**：测试路由是否正确

### 5.3 测试文件位置

按照项目规范，测试文件放在 `cursor_test/` 目录下：
- `cursor_test/infrastructure/database/test_health_event_repository.py`
- `cursor_test/domain/tools/test_health_event_tools.py`
- `cursor_test/integration/test_health_event_agent.py`
- （其他Agent类似）

## 6. 实施时间表

| 阶段 | 任务 | 预计时间 | 负责人 |
|------|------|----------|--------|
| 阶段一 | 数据库层开发 | 2-3天 | 开发人员 |
| 阶段二 | 工具层开发 | 3-4天 | 开发人员 |
| 阶段三 | Agent配置与提示词 | 2-3天 | 开发人员 |
| 阶段四 | 路由层集成 | 2-3天 | 开发人员 |
| 测试 | 单元测试和集成测试 | 2-3天 | 开发人员 |
| **总计** | | **11-16天** | |

## 7. 风险与注意事项

### 7.1 技术风险

1. **数据库迁移风险**：需要确保数据库迁移脚本正确，避免数据丢失
2. **意图识别准确性**：新增意图可能影响现有意图识别，需要充分测试
3. **性能影响**：新增Agent可能增加系统负载，需要监控性能

### 7.2 注意事项

1. **向后兼容**：确保新增功能不影响现有功能
2. **代码一致性**：严格按照血压Agent的实现模式，保持代码风格一致
3. **错误处理**：所有工具和Agent都需要完善的错误处理
4. **日志记录**：确保所有操作都有适当的日志记录

## 8. 验收标准

### 8.1 功能验收

- [ ] 三个新Agent都能正确创建和配置
- [ ] 所有数据都能正确入库
- [ ] 支持记录、查询、更新三种操作
- [ ] 支持多轮对话和槽位填充
- [ ] 意图识别能正确路由到对应Agent

### 8.2 质量验收

- [ ] 所有代码通过单元测试
- [ ] 集成测试通过
- [ ] 代码符合项目规范
- [ ] 文档完整

## 9. 后续优化建议

1. **数据统计**：为每个Agent添加数据统计功能
2. **数据导出**：支持导出用户数据
3. **数据关联**：支持关联不同记录（如症状与用药的关联）
4. **智能提醒**：基于记录数据提供健康提醒

## 10. 参考文档

- 血压Agent实现：`domain/agents/blood_pressure/`
- 血压工具实现：`domain/tools/blood_pressure/`
- 血压模型实现：`infrastructure/database/models/blood_pressure.py`
- 路由图实现：`domain/router/graph.py`
- Agent工厂：`domain/agents/factory.py`
