# GD25 Biz Agent Python 架构分析文档

## 文档说明

本文档基于对 `/Users/m684620/work/github_GD25/gd25-biz-agent-python` 项目的深入分析，总结其代码架构设计、分层结构和设计模式，为后续项目架构改进提供参考。

**文档版本**：V1.0  
**创建时间**：2025-01-XX  
**分析项目**：gd25-biz-agent-python

---

## 目录

1. [项目概述](#一项目概述)
2. [架构设计](#二架构设计)
3. [分层结构详解](#三分层结构详解)
4. [设计模式应用](#四设计模式应用)
5. [核心组件设计](#五核心组件设计)
6. [架构优点总结](#六架构优点总结)

---

## 一、项目概述

### 1.1 项目定位

GD25 Biz Agent Python 是一个基于 LangGraph 的多智能体医疗健康助手系统，采用 Supervisor 模式实现智能体路由，支持血压管理、诊断咨询、预约挂号等功能。

### 1.2 技术栈

- **框架**：FastAPI、LangGraph、LangChain
- **数据库**：PostgreSQL（含 pgvector 扩展）
- **ORM**：SQLAlchemy（异步）
- **配置管理**：Pydantic Settings、YAML
- **数据库迁移**：Alembic

### 1.3 核心特性

- **Supervisor 路由模式**：使用 LLM 作为 Supervisor 进行智能体路由
- **配置驱动**：通过 YAML 配置文件管理智能体和工具
- **Repository 模式**：封装数据访问逻辑
- **工厂模式**：动态创建智能体实例
- **依赖注入**：工具通过 config 获取用户信息

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    应用层 (app/)                          │
│  - main.py: FastAPI 应用入口                             │
│  - api/routes.py: API 路由定义                            │
│  - core/config.py: 配置管理                              │
│  - schemas/: Pydantic 数据模型                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   领域层 (domain/)                        │
│  - router/: 路由逻辑（Supervisor）                        │
│  - agents/: 智能体定义（基类、工厂）                      │
│  - tools/: 业务工具（血压、预约、搜索）                  │
│  - workflows/: 工作流定义（可选）                         │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                基础设施层 (infrastructure/)                │
│  - database/: 数据库连接、模型、仓储                      │
│  - llm/: LLM 客户端封装                                   │
│  - rag/: RAG 服务（向量存储、嵌入）                       │
└─────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
gd25-biz-agent-python/
├── app/                    # 应用层
│   ├── __init__.py
│   ├── main.py             # FastAPI 应用入口
│   ├── api/                # API 路由
│   │   ├── __init__.py
│   │   └── routes.py       # 聊天接口
│   ├── core/               # 核心配置
│   │   ├── __init__.py
│   │   └── config.py       # 配置管理（Pydantic Settings）
│   └── schemas/            # 数据模型
│       ├── __init__.py
│       └── chat.py         # 请求/响应模型
│
├── domain/                 # 领域层
│   ├── __init__.py
│   ├── router/             # 路由逻辑
│   │   ├── __init__.py
│   │   ├── state.py        # 路由状态定义
│   │   └── supervisor.py  # Supervisor 节点和工作流
│   ├── agents/             # 智能体
│   │   ├── __init__.py
│   │   ├── base.py         # 智能体基类
│   │   ├── factory.py      # 智能体工厂
│   │   └── diagnosis/      # 诊断智能体（可选）
│   ├── tools/              # 业务工具
│   │   ├── __init__.py
│   │   ├── blood_pressure.py
│   │   ├── appointment.py
│   │   └── search.py
│   └── workflows/          # 工作流（可选）
│       └── __init__.py
│
├── infrastructure/         # 基础设施层
│   ├── __init__.py
│   ├── database/           # 数据库
│   │   ├── __init__.py
│   │   ├── base.py         # SQLAlchemy Base
│   │   ├── connection.py   # 数据库连接
│   │   ├── models.py        # ORM 模型
│   │   └── repository.py   # 仓储模式
│   ├── llm/                # LLM 服务
│   │   ├── __init__.py
│   │   └── client.py       # LLM 客户端封装
│   └── rag/                # RAG 服务
│       ├── __init__.py
│       ├── embeddings.py   # 嵌入服务
│       └── vector_store.py # 向量存储
│
├── config/                 # 配置文件
│   ├── agents.yaml         # 智能体配置
│   └── prompts/            # 提示词文件（可选）
│
├── alembic/                # 数据库迁移
│   ├── env.py
│   └── versions/
│
├── scripts/                # 脚本工具
│   └── ...
│
├── tests/                  # 测试
│   └── ...
│
└── web/                    # 前端（可选）
    └── qa/
```

---

## 三、分层结构详解

### 3.1 应用层 (app/)

**职责**：
- FastAPI 应用初始化和生命周期管理
- API 路由定义和请求处理
- 配置管理（环境变量、设置）
- 数据模型定义（Pydantic Schemas）

**关键设计**：

1. **生命周期管理**：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: 初始化连接池、checkpointer、工作流
    pool = AsyncConnectionPool(...)
    checkpointer = AsyncPostgresSaver(pool)
    workflow = create_workflow(checkpointer=checkpointer)
    app.state.pool = pool
    app.state.checkpointer = checkpointer
    app.state.workflow = workflow
    yield
    # Shutdown: 清理资源
    await pool.close()
```

2. **配置管理**：
```python
class Settings(BaseSettings):
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    # ...
    
    @property
    def DB_URI(self) -> str:
        """计算属性，动态生成 URI"""
        return f"postgresql+psycopg://..."
    
    model_config = SettingsConfigDict(env_file=".env")
```

3. **API 路由**：
- 支持流式响应（SSE）
- 使用 `app.state` 存储全局对象
- 清晰的错误处理

### 3.2 领域层 (domain/)

**职责**：
- 业务逻辑实现
- 智能体定义和管理
- 工具实现
- 路由逻辑

**关键设计**：

1. **路由层 (router/)**：
   - **Supervisor 模式**：使用 LLM 作为 Supervisor 进行路由决策
   - **状态管理**：使用 TypedDict 定义 RouterState
   - **工作流构建**：使用 StateGraph 构建路由图

2. **智能体层 (agents/)**：
   - **基类模式**：`BaseAgent` 定义通用接口
   - **工厂模式**：`AgentFactory` 根据配置动态创建智能体
   - **配置驱动**：从 YAML 文件加载智能体配置

3. **工具层 (tools/)**：
   - **依赖注入**：通过 `RunnableConfig` 获取用户信息
   - **Repository 模式**：工具内部使用 Repository 访问数据库
   - **异步支持**：所有工具都是异步函数

### 3.3 基础设施层 (infrastructure/)

**职责**：
- 数据库连接和模型定义
- LLM 客户端封装
- RAG 服务实现
- 外部服务集成

**关键设计**：

1. **数据库层 (database/)**：
   - **ORM 模型**：使用 SQLAlchemy 定义数据模型
   - **Repository 模式**：封装数据访问逻辑
   - **连接管理**：使用异步 Session 和依赖注入

2. **LLM 层 (llm/)**：
   - **统一封装**：`get_llm()` 函数统一创建 LLM 实例
   - **配置驱动**：从 Settings 读取配置

3. **RAG 层 (rag/)**：
   - **向量存储**：封装 pgvector 操作
   - **嵌入服务**：支持本地和远程嵌入模型

---

## 四、设计模式应用

### 4.1 工厂模式 (Factory Pattern)

**应用场景**：智能体创建

**实现**：
```python
class AgentFactory:
    _config: Dict[str, Any] = {}
    
    @classmethod
    def create_agent(cls, agent_key: str):
        agent_config = cls._config.get(agent_key)
        llm = get_llm(...)
        tools = [TOOL_REGISTRY[name] for name in tool_names]
        return create_react_agent(model=llm, tools=tools, prompt=system_prompt)
```

**优点**：
- 解耦智能体创建逻辑
- 支持配置驱动
- 易于扩展新智能体

### 4.2 仓储模式 (Repository Pattern)

**应用场景**：数据访问

**实现**：
```python
class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

class BloodPressureRepository(BaseRepository):
    async def add_record(self, user_id: int, ...):
        record = BloodPressureRecord(...)
        self.session.add(record)
        await self.session.commit()
        return record
```

**优点**：
- 封装数据访问逻辑
- 便于测试（可 Mock Repository）
- 统一的数据访问接口

### 4.3 依赖注入 (Dependency Injection)

**应用场景**：工具获取用户信息

**实现**：
```python
@tool
async def add_blood_pressure(..., config: RunnableConfig):
    configuration = config.get("configurable", {})
    username = configuration.get("username", "guest")
    # 使用 username 进行后续操作
```

**优点**：
- 解耦工具和用户信息获取
- 支持测试（可注入 Mock config）
- 符合 LangChain 的设计理念

### 4.4 Supervisor 模式

**应用场景**：智能体路由

**实现**：
```python
async def supervisor_node(state: RouterState):
    # 使用 LLM 分析对话历史，决定下一个 Agent
    response = await llm.ainvoke([SystemMessage(...)] + messages)
    next_agent = parse_response(response.content)
    return {"next_agent": next_agent}
```

**优点**：
- 灵活的路由决策
- 支持自然语言理解
- 易于扩展新的路由规则

### 4.5 配置驱动模式

**应用场景**：智能体配置管理

**实现**：
```yaml
# config/agents.yaml
agents:
  blood_pressure_agent:
    name: "BloodPressureSpecialist"
    model: "deepseek-chat"
    temperature: 0.1
    system_prompt: |
      你是一个专业的血压管理专家...
    tools:
      - "add_blood_pressure"
      - "query_blood_pressure_history"
```

**优点**：
- 无需修改代码即可调整智能体配置
- 支持多环境配置
- 易于维护和版本管理

---

## 五、核心组件设计

### 5.1 数据库设计

**模型定义**：
- 使用 SQLAlchemy ORM
- 清晰的模型关系（User、BloodPressureRecord、Appointment）
- 支持向量存储（KnowledgeBase 使用 pgvector）

**连接管理**：
- 异步连接池
- 依赖注入模式（`get_db()`）
- 自动事务管理

### 5.2 智能体工厂

**工具注册表**：
```python
TOOL_REGISTRY: Dict[str, BaseTool] = {
    "add_blood_pressure": add_blood_pressure,
    "query_blood_pressure_history": query_blood_pressure_history,
    "search_knowledge_base": search_knowledge_base
}
```

**配置加载**：
- 从 YAML 文件加载配置
- 支持动态工具注册
- 自动创建 ReAct Agent

### 5.3 路由工作流

**图结构**：
```
Supervisor -> [BloodPressureAgent | DiagnosisAgent | AppointmentAgent | FINISH]
     ^                    |                 |                 |
     |____________________|_________________|_________________|
```

**特点**：
- 所有 Agent 执行完后回到 Supervisor
- 支持多轮对话
- 使用 Checkpointer 持久化状态

### 5.4 工具设计

**设计原则**：
- 所有工具都是异步函数
- 使用 `@tool` 装饰器
- 通过 `RunnableConfig` 获取上下文信息
- 内部使用 Repository 访问数据库

**示例**：
```python
@tool
async def add_blood_pressure(
    systolic: int, 
    diastolic: int, 
    heart_rate: int, 
    config: RunnableConfig
) -> str:
    configuration = config.get("configurable", {})
    username = configuration.get("username", "guest")
    
    async for session in get_db():
        user_repo = UserRepository(session)
        bp_repo = BloodPressureRepository(session)
        user = await user_repo.get_or_create(username)
        record = await bp_repo.add_record(user.id, systolic, diastolic, heart_rate)
        return f"已成功记录: ..."
```

---

## 六、架构优点总结

### 6.1 分层清晰

**优点**：
- **职责分离**：应用层、领域层、基础设施层职责明确
- **易于维护**：修改某一层不影响其他层
- **便于测试**：可以 Mock 基础设施层进行单元测试

### 6.2 设计模式应用

**优点**：
- **工厂模式**：解耦智能体创建逻辑
- **仓储模式**：封装数据访问，便于测试
- **依赖注入**：降低耦合度
- **配置驱动**：无需修改代码即可调整配置

### 6.3 可扩展性

**优点**：
- **添加新智能体**：只需在 YAML 配置文件中添加配置
- **添加新工具**：在工具注册表中注册即可
- **添加新路由规则**：修改 Supervisor 提示词即可

### 6.4 代码质量

**优点**：
- **类型提示**：使用 TypedDict、Pydantic 模型
- **异步支持**：全面使用异步编程
- **错误处理**：清晰的异常处理机制
- **文档完善**：代码注释和文档字符串完整

### 6.5 配置管理

**优点**：
- **环境变量**：使用 Pydantic Settings 管理配置
- **YAML 配置**：智能体配置使用 YAML 文件
- **计算属性**：使用 `@property` 动态生成配置值

### 6.6 数据库设计

**优点**：
- **ORM 模型**：使用 SQLAlchemy 定义清晰的模型
- **Repository 模式**：封装数据访问逻辑
- **迁移管理**：使用 Alembic 管理数据库迁移

---

## 七、可改进点

### 7.1 当前架构的不足

1. **缺少服务层**：
   - 业务逻辑直接写在工具中
   - 建议添加 `domain/services/` 层封装业务逻辑

2. **错误处理不够统一**：
   - 建议添加统一的异常处理机制
   - 使用自定义异常类

3. **缺少中间件**：
   - 建议添加日志、监控、限流等中间件

4. **测试覆盖不足**：
   - 建议添加单元测试和集成测试

### 7.2 建议的改进方向

1. **添加服务层**：
   ```
   domain/
     ├── services/
     │   ├── blood_pressure_service.py
     │   ├── appointment_service.py
     │   └── diagnosis_service.py
   ```

2. **统一异常处理**：
   ```
   app/
     ├── exceptions.py
     └── middleware/
         └── exception_handler.py
   ```

3. **添加中间件**：
   ```
   app/
     └── middleware/
         ├── logging.py
         ├── monitoring.py
         └── rate_limit.py
   ```

---

## 八、总结

GD25 Biz Agent Python 项目采用了清晰的分层架构和多种设计模式，具有以下特点：

1. **分层清晰**：应用层、领域层、基础设施层职责明确
2. **设计模式**：工厂模式、仓储模式、依赖注入等应用得当
3. **配置驱动**：通过 YAML 配置文件管理智能体
4. **可扩展性强**：易于添加新智能体、工具和路由规则
5. **代码质量高**：类型提示、异步支持、文档完善

该架构设计为后续项目提供了很好的参考，特别是在分层结构、设计模式应用和配置管理方面值得借鉴。

---

**文档版本**：V1.0  
**创建时间**：2025-01-XX  
**维护者**：开发团队

