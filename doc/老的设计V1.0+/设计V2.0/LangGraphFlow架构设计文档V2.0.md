# LangGraphFlow 架构设计文档 V2.0

## 文档说明

本文档基于 V1.0 版本的设计方案，结合 LangGraphFlow 系统核心功能设计文档和 GD25 Biz Agent Python 架构分析文档，重新设计并优化了系统架构，制定了清晰的开发计划和里程碑。

**文档版本**：V2.0  
**创建时间**：2025-01-XX  
**基于文档**：
- LangGraphFlow 系统核心功能设计文档 V1.0
- GD25 Biz Agent Python 架构分析文档 V1.0
- LangGraphFlow 改进代码架构设计文档 V2.0

---

## 目录

1. [架构设计概述](#一架构设计概述)
2. [分层架构设计](#二分层架构设计)
3. [目录结构设计](#三目录结构设计)
4. [核心组件设计](#四核心组件设计)
5. [技术选型](#五技术选型)
6. [开发计划与里程碑](#六开发计划与里程碑)

---

## 一、架构设计概述

### 1.1 设计目标

V2.0 版本在保留 V1.0 核心功能的基础上，重点优化以下方面：

1. **清晰的分层架构**：应用层、领域层、基础设施层职责明确
2. **设计模式应用**：工厂模式、仓储模式、依赖注入等
3. **配置驱动**：通过 YAML 配置文件管理智能体和工具
4. **可扩展性**：易于添加新智能体、工具和路由规则
5. **代码质量**：类型提示、异步支持、文档完善
6. **渐进式开发**：采用里程碑式开发，MVP 版本只实现核心功能

### 1.2 核心改进点

#### 1.2.1 架构优化

- **统一的分层架构**：借鉴 GD25 Biz Agent Python 的分层设计
- **Repository 模式**：统一数据访问接口，便于测试和维护
- **工厂模式**：智能体和工具通过工厂模式创建，支持配置驱动
- **依赖注入**：通过 `RunnableConfig` 传递上下文信息

#### 1.2.2 功能简化（MVP 版本）

- **只实现两个智能体**：血压记录智能体和复诊管理智能体
- **简化路由逻辑**：只支持血压和预约两种意图
- **基础工具集**：只实现必要的工具，其他功能后续迭代

#### 1.2.3 开发流程优化

- **里程碑式开发**：分阶段实现功能，每个里程碑都有可用版本
- **测试驱动**：每个里程碑都包含测试验证
- **文档同步**：开发过程中同步更新文档

---

## 二、分层架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                    应用层 (app/)                          │
│  - main.py: FastAPI 应用入口和生命周期管理                │
│  - api/: API 路由定义（聊天、健康检查等）                 │
│  - core/: 核心配置（Settings、中间件）                   │
│  - schemas/: Pydantic 数据模型（请求/响应）               │
│  - middleware/: 中间件（日志、异常处理）                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   领域层 (domain/)                        │
│  - router/: 路由逻辑（意图识别、路由决策）                │
│  - agents/: 智能体定义（工厂、各专门智能体）              │
│  - tools/: 业务工具（血压、预约）                        │
│  - services/: 业务服务层（可选，封装复杂业务逻辑）        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                基础设施层 (infrastructure/)                │
│  - database/: 数据库（连接、模型、仓储）                  │
│  - llm/: LLM 客户端封装                                  │
│  - external/: 外部服务集成（Java微服务等）                │
└─────────────────────────────────────────────────────────┘
```

### 2.2 分层职责说明

#### 应用层 (app/)

**职责**：
- FastAPI 应用初始化和生命周期管理
- API 路由定义和请求处理
- 配置管理（环境变量、设置）
- 数据模型定义（Pydantic Schemas）
- 中间件（日志、异常处理）

**特点**：
- 薄层设计，只负责请求处理和响应
- 不包含业务逻辑
- 通过依赖注入获取领域服务

#### 领域层 (domain/)

**职责**：
- 业务逻辑实现
- 智能体定义和管理
- 工具实现
- 路由逻辑
- 业务服务（可选）

**特点**：
- 核心业务逻辑所在
- 不依赖具体的技术实现
- 通过接口依赖基础设施层

#### 基础设施层 (infrastructure/)

**职责**：
- 数据库连接和模型定义
- LLM 客户端封装
- 外部服务集成

**特点**：
- 技术实现细节
- 可以被 Mock 用于测试
- 提供统一的接口给领域层

---

## 三、目录结构设计

### 3.1 完整目录结构

```
gd25-biz-agent-python_cursor/
├── app/                           # 应用层
│   ├── __init__.py
│   ├── main.py                    # FastAPI 应用入口
│   ├── api/                       # API 路由
│   │   ├── __init__.py
│   │   └── routes.py              # 聊天接口、健康检查等
│   ├── core/                      # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py              # 配置管理（Pydantic Settings）
│   │   └── dependencies.py        # 依赖注入（可选）
│   ├── schemas/                   # 数据模型
│   │   ├── __init__.py
│   │   ├── chat.py                # 聊天请求/响应模型
│   │   └── common.py              # 通用模型
│   └── middleware/                # 中间件
│       ├── __init__.py
│       ├── logging.py             # 日志中间件
│       └── exception_handler.py   # 异常处理中间件
│
├── domain/                        # 领域层
│   ├── __init__.py
│   ├── router/                    # 路由逻辑
│   │   ├── __init__.py
│   │   ├── state.py               # 路由状态定义（RouterState）
│   │   ├── graph.py               # 路由图构建
│   │   ├── node.py                # 路由节点实现
│   │   └── tools/                 # 路由工具
│   │       ├── __init__.py
│   │       └── router_tools.py   # 意图识别工具
│   │
│   ├── agents/                    # 智能体
│   │   ├── __init__.py
│   │   ├── factory.py             # 智能体工厂
│   │   ├── blood_pressure/        # 血压记录智能体
│   │   │   ├── __init__.py
│   │   │   ├── agent.py           # 智能体节点工厂函数
│   │   │   └── prompt.py          # 系统提示词
│   │   └── appointment/           # 复诊管理智能体
│   │       ├── __init__.py
│   │       ├── agent.py
│   │       └── prompt.py
│   │
│   ├── tools/                     # 业务工具
│   │   ├── __init__.py
│   │   ├── registry.py            # 工具注册表
│   │   ├── blood_pressure/        # 血压记录工具
│   │   │   ├── __init__.py
│   │   │   ├── record.py          # 记录血压工具
│   │   │   ├── query.py           # 查询血压工具
│   │   │   └── update.py          # 更新血压工具
│   │   └── appointment/           # 复诊管理工具
│   │       ├── __init__.py
│   │       ├── create.py          # 创建预约工具
│   │       ├── query.py           # 查询预约工具
│   │       └── update.py          # 更新预约工具
│   │
│   └── services/                  # 业务服务层（可选）
│       ├── __init__.py
│       ├── blood_pressure_service.py
│       └── appointment_service.py
│
├── infrastructure/                # 基础设施层
│   ├── __init__.py
│   ├── database/                  # 数据库
│   │   ├── __init__.py
│   │   ├── base.py                # SQLAlchemy Base
│   │   ├── connection.py          # 数据库连接和连接池
│   │   ├── models/                # ORM 模型
│   │   │   ├── __init__.py
│   │   │   ├── user.py            # 用户模型
│   │   │   ├── blood_pressure.py  # 血压记录模型
│   │   │   └── appointment.py     # 预约模型
│   │   └── repository/            # 仓储模式
│   │       ├── __init__.py
│   │       ├── base.py             # 基础仓储类
│   │       ├── user_repository.py
│   │       ├── blood_pressure_repository.py
│   │       └── appointment_repository.py
│   │
│   ├── llm/                       # LLM 服务
│   │   ├── __init__.py
│   │   └── client.py              # LLM 客户端封装
│   │
│   └── external/                  # 外部服务集成
│       ├── __init__.py
│       └── java_service.py        # Java 微服务客户端
│
├── config/                        # 配置文件
│   ├── agents.yaml                # 智能体配置
│   └── prompts/                   # 提示词文件（可选）
│       ├── blood_pressure_prompt.txt
│       └── appointment_prompt.txt
│
├── alembic/                       # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── scripts/                       # 脚本工具
│   ├── init_db.py                 # 初始化数据库
│   └── ...
│
├── tests/                         # 测试
│   ├── __init__.py
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   └── fixtures/                  # 测试数据
│
├── cursor_docs/                   # 文档（项目特定）
│   └── ...
│
├── doc/                           # 设计文档
│   ├── 设计V1.0/
│   └── 设计V2.0/
│       ├── LangGraphFlow架构设计文档V2.0.md
│       └── 开发计划与里程碑.md
│
├── .env.example                   # 环境变量示例
├── .gitignore
├── requirements.txt               # Python 依赖
├── requirements.lock              # 依赖锁定文件
├── README.md
└── LICENSE
```

### 3.2 关键目录说明

#### app/ - 应用层

- **main.py**：FastAPI 应用入口，生命周期管理
- **api/**：API 路由定义，处理 HTTP 请求
- **core/**：核心配置和依赖注入
- **schemas/**：Pydantic 数据模型
- **middleware/**：中间件（日志、异常处理）

#### domain/ - 领域层

- **router/**：路由逻辑（意图识别、路由决策）
- **agents/**：智能体定义（工厂、各专门智能体）
- **tools/**：业务工具（按功能模块组织）
- **services/**：业务服务层（可选，封装复杂业务逻辑）

#### infrastructure/ - 基础设施层

- **database/**：数据库（连接、模型、仓储）
- **llm/**：LLM 客户端封装
- **external/**：外部服务集成（Java微服务）

---

## 四、核心组件设计

### 4.1 应用层设计

#### 4.1.1 main.py - FastAPI 应用入口

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from app.api.routes import router
from app.core.config import settings
from domain.router.graph import create_router_graph
from infrastructure.database.connection import create_db_pool

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup
    print("Starting up...")
    
    # 初始化数据库连接池（用于 Checkpointer）
    checkpointer_pool = AsyncConnectionPool(
        conninfo=settings.CHECKPOINTER_DB_URI,
        max_size=20,
        kwargs={"autocommit": True}
    )
    await checkpointer_pool.open()
    
    # 初始化业务数据库连接池
    db_pool = await create_db_pool()
    
    # 初始化 Checkpointer
    checkpointer = AsyncPostgresSaver(checkpointer_pool)
    await checkpointer.setup()
    
    # 初始化 Store（长期记忆）
    store = AsyncPostgresStore(checkpointer_pool)
    await store.setup()
    
    # 创建路由图
    router_graph = create_router_graph(
        checkpointer=checkpointer,
        pool=db_pool,
        store=store
    )
    
    # 存储到 app.state
    app.state.checkpointer_pool = checkpointer_pool
    app.state.db_pool = db_pool
    app.state.checkpointer = checkpointer
    app.state.store = store
    app.state.router_graph = router_graph
    
    yield
    
    # Shutdown
    print("Shutting down...")
    await checkpointer_pool.close()
    await db_pool.close()

# 创建 FastAPI 应用
app = FastAPI(
    title="LangGraphFlow Multi-Agent Router",
    description="多智能体路由系统 V2.0",
    version="2.0.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok", "version": "2.0.0"}
```

#### 4.1.2 core/config.py - 配置管理

```python
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "langgraphflow"
    
    @property
    def DB_URI(self) -> str:
        """同步数据库连接 URI"""
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def ASYNC_DB_URI(self) -> str:
        """异步数据库连接 URI"""
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def CHECKPOINTER_DB_URI(self) -> str:
        """Checkpointer 专用连接 URI"""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # LLM 配置
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.0
    
    # 路由配置
    INTENT_CONFIDENCE_THRESHOLD: float = 0.8
    
    # Java 微服务配置
    JAVA_SERVICE_BASE_URL: Optional[str] = None
    JAVA_SERVICE_TIMEOUT: int = 30
    
    # 应用配置
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
```

### 4.2 领域层设计

#### 4.2.1 router/state.py - 路由状态定义

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
    current_intent: Optional[str]  # 当前意图：blood_pressure, appointment, unclear
    current_agent: Optional[str]  # 当前活跃的智能体名称
    need_reroute: bool  # 是否需要重新路由
    session_id: str  # 会话ID
    user_id: str  # 用户ID


class IntentResult(BaseModel):
    """意图识别结果"""
    intent_type: str  # "blood_pressure", "appointment", "unclear"
    confidence: float  # 0.0-1.0
    entities: Dict[str, Any]  # 提取的实体信息
    need_clarification: bool  # 是否需要澄清
    reasoning: Optional[str] = None  # 识别理由（可选）
```

#### 4.2.2 agents/factory.py - 智能体工厂

```python
"""
智能体工厂
根据配置动态创建智能体实例
"""
import yaml
import os
from typing import Dict, List, Any, Optional
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from langchain_core.language_models import BaseChatModel

from infrastructure.llm.client import get_llm
from domain.tools.registry import TOOL_REGISTRY
from app.core.config import settings

class AgentFactory:
    """智能体工厂类"""
    
    _config: Dict[str, Any] = {}
    _config_path: str = "config/agents.yaml"
    
    @classmethod
    def load_config(cls, config_path: Optional[str] = None):
        """加载智能体配置文件"""
        if config_path:
            cls._config_path = config_path
        
        # 支持相对路径和绝对路径
        if not os.path.isabs(cls._config_path):
            config_path = os.path.join(os.getcwd(), cls._config_path)
        else:
            config_path = cls._config_path
        
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cls._config = yaml.safe_load(f).get("agents", {})
        else:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    @classmethod
    def create_agent(
        cls,
        agent_key: str,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None
    ):
        """
        根据配置创建智能体
        
        Args:
            agent_key: 智能体键名（如 blood_pressure_agent）
            llm: LLM 实例（可选，如果不提供则从配置创建）
            tools: 工具列表（可选，如果不提供则从配置加载）
        
        Returns:
            CompiledGraph: 已编译的 LangGraph Agent 实例
        """
        if not cls._config:
            cls.load_config()
        
        agent_config = cls._config.get(agent_key)
        if not agent_config:
            raise ValueError(f"智能体配置不存在: {agent_key}")
        
        # 1. 获取 LLM 实例
        if not llm:
            llm_config = agent_config.get("llm", {})
            llm = get_llm(
                model=llm_config.get("model", settings.LLM_MODEL),
                temperature=llm_config.get("temperature", settings.LLM_TEMPERATURE)
            )
        
        # 2. 获取工具列表
        if not tools:
            tool_names = agent_config.get("tools", [])
            tools = [
                TOOL_REGISTRY[name]
                for name in tool_names
                if name in TOOL_REGISTRY
            ]
        
        # 3. 获取系统提示词
        system_prompt = agent_config.get("system_prompt", "")
        # 支持从文件加载提示词
        prompt_path = agent_config.get("system_prompt_path")
        if prompt_path and os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        
        # 4. 创建 ReAct Agent
        return create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_prompt
        )
    
    @classmethod
    def list_agents(cls) -> List[str]:
        """列出所有可用的智能体"""
        if not cls._config:
            cls.load_config()
        return list(cls._config.keys())

# 模块加载时自动读取配置
AgentFactory.load_config()
```

#### 4.2.3 tools/registry.py - 工具注册表

```python
"""
工具注册表
统一管理所有业务工具
"""
from typing import Dict
from langchain_core.tools import BaseTool

# 导入所有工具
from domain.tools.blood_pressure.record import record_blood_pressure
from domain.tools.blood_pressure.query import query_blood_pressure
from domain.tools.blood_pressure.update import update_blood_pressure
from domain.tools.appointment.create import create_appointment
from domain.tools.appointment.query import query_appointment
from domain.tools.appointment.update import update_appointment

# 工具注册表
TOOL_REGISTRY: Dict[str, BaseTool] = {
    # 血压记录工具
    "record_blood_pressure": record_blood_pressure,
    "query_blood_pressure": query_blood_pressure,
    "update_blood_pressure": update_blood_pressure,
    
    # 复诊管理工具
    "create_appointment": create_appointment,
    "query_appointment": query_appointment,
    "update_appointment": update_appointment,
}

def register_tool(name: str, tool: BaseTool):
    """注册新工具"""
    TOOL_REGISTRY[name] = tool

def get_tool(name: str) -> BaseTool:
    """获取工具"""
    if name not in TOOL_REGISTRY:
        raise ValueError(f"工具不存在: {name}")
    return TOOL_REGISTRY[name]
```

### 4.3 基础设施层设计

#### 4.3.1 database/repository/base.py - 基础仓储类

```python
"""
基础仓储类
封装通用的数据库操作
"""
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from infrastructure.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """基础仓储类"""
    
    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        """
        初始化仓储
        
        Args:
            session: 数据库会话
            model: ORM 模型类
        """
        self.session = session
        self.model = model
    
    async def get_by_id(self, id: int) -> Optional[ModelType]:
        """根据 ID 查询"""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """查询所有记录"""
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
    
    async def create(self, **kwargs) -> ModelType:
        """创建记录"""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance
    
    async def update(self, id: int, **kwargs) -> Optional[ModelType]:
        """更新记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return None
        
        for key, value in kwargs.items():
            setattr(instance, key, value)
        
        await self.session.flush()
        return instance
    
    async def delete(self, id: int) -> bool:
        """删除记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return False
        
        await self.session.delete(instance)
        await self.session.flush()
        return True
```

---

## 五、技术选型

### 5.1 核心技术栈

- **Python**: 3.10+
- **FastAPI**: 0.100+ (Web 框架)
- **LangGraph**: 0.2+ (多智能体框架)
- **LangChain**: 0.3+ (LLM 调用和工具支持)
- **PostgreSQL**: 14+ (数据库)
- **SQLAlchemy**: 2.0+ (ORM)
- **Pydantic**: 2.0+ (数据验证)
- **Alembic**: (数据库迁移)

### 5.2 开发工具

- **pytest**: 测试框架
- **black**: 代码格式化
- **mypy**: 类型检查
- **ruff**: 代码检查

### 5.3 部署工具

- **Docker**: 容器化
- **docker-compose**: 本地开发环境

---

## 六、开发计划与里程碑

详细的开发计划请参考：[开发计划与里程碑.md](./开发计划与里程碑.md)

### 6.1 里程碑概览

1. **Milestone 1: MVP 版本（血压 + 预约）**
   - 实现基础架构
   - 实现血压记录智能体
   - 实现复诊管理智能体
   - 基础路由功能

2. **Milestone 2: 功能增强**
   - 添加诊断智能体系统
   - 添加 RAG 检索功能
   - 完善路由逻辑

3. **Milestone 3: 生产就绪**
   - 添加安全审核
   - 性能优化
   - 完善测试和文档

---

**文档版本**：V2.0  
**创建时间**：2025-01-XX  
**维护者**：开发团队

