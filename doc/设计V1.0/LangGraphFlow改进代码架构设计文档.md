# LangGraphFlow 改进代码架构设计文档

## 文档说明

本文档基于对 `langGraphFlow系统核心功能设计文档.md` 和 `gd25-biz-agent-python架构分析文档.md` 的深入分析，结合两个项目的优点，提出改进后的代码架构设计方案。

**文档版本**：V2.0  
**创建时间**：2025-01-XX  
**基于文档**：
- LangGraphFlow 系统核心功能设计文档 V1.0
- GD25 Biz Agent Python 架构分析文档 V1.0

---

## 目录

1. [架构改进概述](#一架构改进概述)
2. [改进后的分层架构](#二改进后的分层架构)
3. [目录结构设计](#三目录结构设计)
4. [核心组件设计](#四核心组件设计)
5. [设计模式应用](#五设计模式应用)
6. [实现指南](#六实现指南)

---

## 一、架构改进概述

### 1.1 改进目标

在保留 LangGraphFlow 原有功能的基础上，借鉴 GD25 Biz Agent Python 的优秀设计，实现以下改进：

1. **清晰的分层架构**：应用层、领域层、基础设施层职责明确
2. **设计模式应用**：工厂模式、仓储模式、依赖注入等
3. **配置驱动**：通过配置文件管理智能体和工具
4. **可扩展性**：易于添加新智能体、工具和路由规则
5. **代码质量**：类型提示、异步支持、文档完善

### 1.2 核心改进点

1. **分层架构优化**：
   - 引入 `infrastructure/` 层统一管理基础设施
   - 引入 `app/` 层统一管理应用入口和配置
   - 优化 `domain/` 层的组织结构

2. **设计模式应用**：
   - 智能体工厂模式（配置驱动）
   - Repository 模式（数据访问）
   - 依赖注入（工具上下文）

3. **配置管理优化**：
   - YAML 配置文件管理智能体
   - Pydantic Settings 管理环境配置
   - 工具注册表模式

4. **数据库设计优化**：
   - SQLAlchemy ORM 模型
   - Repository 模式封装数据访问
   - 清晰的模型关系定义

---

## 二、改进后的分层架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                    应用层 (app/)                          │
│  - main.py: FastAPI 应用入口和生命周期管理                │
│  - api/: API 路由定义（聊天、健康检查等）                 │
│  - core/: 核心配置（Settings、中间件）                   │
│  - schemas/: Pydantic 数据模型（请求/响应）               │
│  - middleware/: 中间件（日志、异常处理、安全审核）        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                   领域层 (domain/)                        │
│  - router/: 路由逻辑（意图识别、路由决策）                │
│  - agents/: 智能体定义（基类、工厂、各专门智能体）        │
│  - tools/: 业务工具（血压、预约、诊断检索等）             │
│  - services/: 业务服务层（可选，封装复杂业务逻辑）        │
│  - workflows/: 工作流定义（可选）                         │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                基础设施层 (infrastructure/)                │
│  - database/: 数据库（连接、模型、仓储）                  │
│  - llm/: LLM 客户端封装                                  │
│  - rag/: RAG 服务（向量存储、嵌入、检索）                 │
│  - cache/: 缓存服务（Redis，可选）                        │
│  - external/: 外部服务集成（Java微服务、审核服务等）      │
└─────────────────────────────────────────────────────────┘
```

### 2.2 分层职责说明

#### 应用层 (app/)

**职责**：
- FastAPI 应用初始化和生命周期管理
- API 路由定义和请求处理
- 配置管理（环境变量、设置）
- 数据模型定义（Pydantic Schemas）
- 中间件（日志、异常处理、安全审核）

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
- RAG 服务实现
- 缓存服务
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
│   │   ├── routes.py              # 聊天接口、健康检查等
│   │   └── v1/                    # API 版本管理（可选）
│   │       ├── __init__.py
│   │       └── chat.py
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
│       ├── exception_handler.py   # 异常处理中间件
│       ├── security.py            # 安全审核中间件
│       └── rate_limit.py          # 限流中间件（可选）
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
│   │       ├── router_tools.py   # 意图识别、意图澄清工具
│   │       └── intent_parser.py   # 意图解析器（可选）
│   │
│   ├── agents/                    # 智能体
│   │   ├── __init__.py
│   │   ├── base.py                # 智能体基类（可选）
│   │   ├── factory.py             # 智能体工厂
│   │   ├── blood_pressure/        # 血压记录智能体
│   │   │   ├── __init__.py
│   │   │   ├── agent.py           # 智能体节点工厂函数
│   │   │   └── prompt.py          # 系统提示词
│   │   ├── appointment/           # 复诊管理智能体
│   │   │   ├── __init__.py
│   │   │   ├── agent.py
│   │   │   └── prompt.py
│   │   └── diagnosis/             # 诊断智能体系统
│   │       ├── __init__.py
│   │       ├── base.py             # 诊断智能体基类
│   │       ├── internal_medicine/ # 内科诊断智能体
│   │       │   ├── __init__.py
│   │       │   ├── agent.py
│   │       │   └── prompt.py
│   │       ├── surgery/            # 外科诊断智能体
│   │       ├── pediatrics/         # 儿科诊断智能体
│   │       ├── gynecology/        # 妇科诊断智能体
│   │       ├── cardiology/        # 心血管科诊断智能体
│   │       └── general/           # 通用诊断智能体
│   │
│   ├── tools/                     # 业务工具
│   │   ├── __init__.py
│   │   ├── registry.py            # 工具注册表
│   │   ├── blood_pressure/        # 血压记录工具
│   │   │   ├── __init__.py
│   │   │   ├── record.py          # 记录血压工具
│   │   │   ├── query.py           # 查询血压工具
│   │   │   └── update.py          # 更新血压工具
│   │   ├── appointment/           # 复诊管理工具
│   │   │   ├── __init__.py
│   │   │   ├── create.py          # 创建预约工具
│   │   │   ├── query.py           # 查询预约工具
│   │   │   └── update.py          # 更新预约工具
│   │   └── diagnosis/             # 诊断工具
│   │       ├── __init__.py
│   │       └── retrieve.py        # 检索诊断知识工具
│   │
│   └── services/                  # 业务服务层（可选）
│       ├── __init__.py
│       ├── blood_pressure_service.py
│       ├── appointment_service.py
│       └── diagnosis_service.py
│
├── infrastructure/                # 基础设施层
│   ├── __init__.py
│   ├── database/                  # 数据库
│   │   ├── __init__.py
│   │   ├── base.py                # SQLAlchemy Base
│   │   ├── connection.py          # 数据库连接和连接池
│   │   ├── models.py              # ORM 模型
│   │   │   ├── user.py            # 用户模型
│   │   │   ├── blood_pressure.py  # 血压记录模型
│   │   │   ├── appointment.py     # 预约模型
│   │   │   └── knowledge_base.py  # 知识库模型
│   │   └── repository/            # 仓储模式
│   │       ├── __init__.py
│   │       ├── base.py             # 基础仓储类
│   │       ├── user_repository.py
│   │       ├── blood_pressure_repository.py
│   │       ├── appointment_repository.py
│   │       └── knowledge_base_repository.py
│   │
│   ├── llm/                       # LLM 服务
│   │   ├── __init__.py
│   │   ├── client.py              # LLM 客户端封装
│   │   ├── factory.py             # LLM 工厂（可选）
│   │   └── models.py               # LLM 模型配置（可选）
│   │
│   ├── rag/                       # RAG 服务
│   │   ├── __init__.py
│   │   ├── embeddings.py          # 嵌入服务
│   │   ├── vector_store.py        # 向量存储接口
│   │   ├── vector_store_factory.py # 向量存储工厂
│   │   ├── pgvector_store.py      # PgVector 实现
│   │   ├── adb_pg_store.py        # ADB PG 实现
│   │   ├── document_loader.py     # 文档加载器
│   │   ├── text_splitter.py       # 文本分割器
│   │   └── retriever.py           # RAG 检索器
│   │
│   ├── cache/                     # 缓存服务（可选）
│   │   ├── __init__.py
│   │   └── redis_client.py        # Redis 客户端
│   │
│   └── external/                  # 外部服务集成
│       ├── __init__.py
│       ├── java_service.py        # Java 微服务客户端
│       └── review_service.py     # 审核服务客户端（可选）
│
├── config/                        # 配置文件
│   ├── agents.yaml                # 智能体配置
│   ├── prompts/                   # 提示词文件（可选）
│   │   ├── blood_pressure_prompt.txt
│   │   ├── appointment_prompt.txt
│   │   └── diagnosis_prompts/
│   └── tools.yaml                 # 工具配置（可选）
│
├── alembic/                       # 数据库迁移
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── scripts/                       # 脚本工具
│   ├── init_db.py                 # 初始化数据库
│   ├── load_knowledge_base.py     # 加载知识库
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
│   └── 设计V1.0/
│       ├── langGraphFlow系统核心功能设计文档.md
│       ├── gd25-biz-agent-python架构分析文档.md
│       └── LangGraphFlow改进代码架构设计文档.md
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
- **middleware/**：中间件（日志、异常处理、安全审核）

#### domain/ - 领域层

- **router/**：路由逻辑（意图识别、路由决策）
- **agents/**：智能体定义（基类、工厂、各专门智能体）
- **tools/**：业务工具（按功能模块组织）
- **services/**：业务服务层（可选，封装复杂业务逻辑）

#### infrastructure/ - 基础设施层

- **database/**：数据库（连接、模型、仓储）
- **llm/**：LLM 客户端封装
- **rag/**：RAG 服务（向量存储、嵌入、检索）
- **cache/**：缓存服务（Redis）
- **external/**：外部服务集成（Java微服务、审核服务）

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
    description="多智能体路由系统",
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
    
    # Redis 配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    @property
    def REDIS_URL(self) -> str:
        """Redis 连接 URL"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    # LLM 配置
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.0
    
    # Embedding 配置
    EMBEDDING_MODEL: str = "moka-ai/m3e-base"
    EMBEDDING_DIMENSION: int = 768
    USE_LOCAL_EMBEDDING: bool = True
    HF_ENDPOINT: str = "https://hf-mirror.com"
    
    # 路由配置
    INTENT_CONFIDENCE_THRESHOLD: float = 0.8
    
    # 安全审核配置
    ENABLE_SECURITY_REVIEW: bool = True
    SECURITY_REVIEW_API_URL: Optional[str] = None
    
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

#### 4.2.1 agents/factory.py - 智能体工厂

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

#### 4.2.2 tools/registry.py - 工具注册表

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
from domain.tools.diagnosis.retrieve import retrieve_diagnosis_knowledge

# 工具注册表
TOOL_REGISTRY: Dict[str, BaseTool] = {
    # 血压记录工具
    "record_blood_pressure": record_blood_pressure,
    "query_blood_pressure": query_blood_pressure,
    "update_blood_pressure": update_blood_pressure,
    
    # 复诊管理工具
    "create_appointment": create_appointment,
    "query_appointment": query_appointment,
    
    # 诊断工具
    "retrieve_diagnosis_knowledge": retrieve_diagnosis_knowledge,
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
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

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

#### 4.3.2 database/repository/blood_pressure_repository.py - 血压记录仓储

```python
"""
血压记录仓储
封装血压记录相关的数据访问逻辑
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models.blood_pressure import BloodPressureRecord
from infrastructure.database.repository.base import BaseRepository

class BloodPressureRepository(BaseRepository[BloodPressureRecord]):
    """血压记录仓储类"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, BloodPressureRecord)
    
    async def create_record(
        self,
        user_id: int,
        systolic: int,
        diastolic: int,
        measurement_time: Optional[datetime] = None,
        notes: Optional[str] = None
    ) -> BloodPressureRecord:
        """创建血压记录"""
        return await self.create(
            user_id=user_id,
            systolic=systolic,
            diastolic=diastolic,
            measurement_time=measurement_time or datetime.now(),
            notes=notes
        )
    
    async def get_by_user_id(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[BloodPressureRecord]:
        """查询用户的血压记录"""
        stmt = (
            select(BloodPressureRecord)
            .where(BloodPressureRecord.user_id == user_id)
        )
        
        if start_date:
            stmt = stmt.where(BloodPressureRecord.measurement_time >= start_date)
        if end_date:
            stmt = stmt.where(BloodPressureRecord.measurement_time <= end_date)
        
        stmt = stmt.order_by(desc(BloodPressureRecord.measurement_time)).limit(limit)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_statistics(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """获取统计信息"""
        records = await self.get_by_user_id(user_id, start_date, end_date, limit=1000)
        
        if not records:
            return {
                "count": 0,
                "avg_systolic": 0,
                "avg_diastolic": 0,
                "max_systolic": 0,
                "min_systolic": 0,
                "max_diastolic": 0,
                "min_diastolic": 0
            }
        
        systolic_values = [r.systolic for r in records]
        diastolic_values = [r.diastolic for r in records]
        
        return {
            "count": len(records),
            "avg_systolic": sum(systolic_values) / len(systolic_values),
            "avg_diastolic": sum(diastolic_values) / len(diastolic_values),
            "max_systolic": max(systolic_values),
            "min_systolic": min(systolic_values),
            "max_diastolic": max(diastolic_values),
            "min_diastolic": min(diastolic_values)
        }
```

---

## 五、设计模式应用

### 5.1 工厂模式

**应用场景**：
- 智能体创建（`AgentFactory`）
- LLM 客户端创建（`get_llm()`）
- 向量存储创建（`VectorStoreFactory`）

**优点**：
- 解耦创建逻辑
- 支持配置驱动
- 易于扩展

### 5.2 仓储模式

**应用场景**：
- 数据访问（`BaseRepository`、`BloodPressureRepository` 等）

**优点**：
- 封装数据访问逻辑
- 便于测试（可 Mock Repository）
- 统一的数据访问接口

### 5.3 依赖注入

**应用场景**：
- 工具获取用户信息（通过 `RunnableConfig`）
- 数据库会话管理（通过 `get_db()`）
- 应用状态管理（通过 `app.state`）

**优点**：
- 降低耦合度
- 支持测试
- 符合框架设计理念

### 5.4 注册表模式

**应用场景**：
- 工具注册表（`TOOL_REGISTRY`）

**优点**：
- 统一管理工具
- 支持动态注册
- 易于扩展

### 5.5 配置驱动模式

**应用场景**：
- 智能体配置（YAML 文件）
- 环境配置（Pydantic Settings）

**优点**：
- 无需修改代码即可调整配置
- 支持多环境配置
- 易于维护和版本管理

---

## 六、实现指南

### 6.1 迁移步骤

1. **创建新的目录结构**
   - 按照设计的目录结构创建文件夹
   - 保持原有代码功能不变

2. **迁移应用层代码**
   - 将 FastAPI 相关代码迁移到 `app/`
   - 配置管理迁移到 `app/core/config.py`
   - API 路由迁移到 `app/api/`

3. **迁移领域层代码**
   - 路由逻辑迁移到 `domain/router/`
   - 智能体代码迁移到 `domain/agents/`
   - 工具代码迁移到 `domain/tools/`

4. **迁移基础设施层代码**
   - 数据库相关代码迁移到 `infrastructure/database/`
   - LLM 客户端迁移到 `infrastructure/llm/`
   - RAG 服务迁移到 `infrastructure/rag/`

5. **重构数据访问**
   - 引入 Repository 模式
   - 重构工具使用 Repository

6. **引入工厂模式**
   - 创建 `AgentFactory`
   - 创建工具注册表
   - 配置 YAML 文件

7. **测试和验证**
   - 运行单元测试
   - 运行集成测试
   - 验证功能完整性

### 6.2 配置文件示例

#### config/agents.yaml

```yaml
agents:
  blood_pressure_agent:
    name: "BloodPressureSpecialist"
    llm:
      model: "deepseek-chat"
      temperature: 0.1
    system_prompt: |
      你是一个专业的血压管理专家。你的职责是帮助用户记录、查询和分析血压数据。
      
      你有以下工具可以使用：
      1. record_blood_pressure: 记录血压数据
      2. query_blood_pressure: 查询历史记录
      3. update_blood_pressure: 更新血压记录
      
      请保持回答简洁、专业，并给出健康建议。
    tools:
      - "record_blood_pressure"
      - "query_blood_pressure"
      - "update_blood_pressure"
  
  appointment_agent:
    name: "AppointmentScheduler"
    llm:
      model: "deepseek-chat"
      temperature: 0.1
    system_prompt_path: "config/prompts/appointment_prompt.txt"
    tools:
      - "create_appointment"
      - "query_appointment"
  
  internal_medicine_diagnosis_agent:
    name: "InternalMedicineDiagnostician"
    llm:
      model: "deepseek-chat"
      temperature: 0.2
    system_prompt_path: "config/prompts/diagnosis_prompts/internal_medicine.txt"
    tools:
      - "retrieve_diagnosis_knowledge"
```

### 6.3 工具实现示例

#### domain/tools/blood_pressure/record.py

```python
"""
记录血压工具
"""
from typing import Optional
from datetime import datetime
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

from infrastructure.database.connection import get_db
from infrastructure.database.repository.user_repository import UserRepository
from infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository

@tool
async def record_blood_pressure(
    systolic: int,
    diastolic: int,
    measurement_time: Optional[str] = None,
    notes: Optional[str] = None,
    config: RunnableConfig = None
) -> str:
    """
    记录用户的血压数据
    
    Args:
        systolic: 收缩压（50-300 mmHg）
        diastolic: 舒张压（30-200 mmHg）
        measurement_time: 测量时间（可选，支持相对时间）
        notes: 备注（可选）
        config: LangChain 运行时配置
    
    Returns:
        str: 操作结果描述
    """
    # 参数验证
    if not (50 <= systolic <= 300):
        return f"错误：收缩压必须在 50-300 mmHg 之间，当前值: {systolic}"
    if not (30 <= diastolic <= 200):
        return f"错误：舒张压必须在 30-200 mmHg 之间，当前值: {diastolic}"
    if systolic <= diastolic:
        return f"错误：收缩压必须大于舒张压，当前值: {systolic}/{diastolic}"
    
    # 从 config 获取用户信息
    configuration = config.get("configurable", {}) if config else {}
    user_id = configuration.get("user_id")
    if not user_id:
        return "错误：无法获取用户信息"
    
    # 解析时间（支持相对时间）
    measurement_datetime = None
    if measurement_time:
        # TODO: 实现时间解析逻辑
        pass
    
    # 使用 Repository 保存数据
    async for session in get_db():
        user_repo = UserRepository(session)
        bp_repo = BloodPressureRepository(session)
        
        # 确保用户存在
        user = await user_repo.get_by_id(user_id)
        if not user:
            return f"错误：用户不存在，ID: {user_id}"
        
        # 创建记录
        record = await bp_repo.create_record(
            user_id=user_id,
            systolic=systolic,
            diastolic=diastolic,
            measurement_time=measurement_datetime,
            notes=notes
        )
        
        await session.commit()
        
        return (
            f"已成功记录血压数据：\n"
            f"- 收缩压：{record.systolic} mmHg\n"
            f"- 舒张压：{record.diastolic} mmHg\n"
            f"- 测量时间：{record.measurement_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"- 记录ID：{record.id}"
        )
```

---

## 七、总结

### 7.1 改进要点

1. **清晰的分层架构**：应用层、领域层、基础设施层职责明确
2. **设计模式应用**：工厂模式、仓储模式、依赖注入等
3. **配置驱动**：通过 YAML 配置文件管理智能体
4. **可扩展性**：易于添加新智能体、工具和路由规则
5. **代码质量**：类型提示、异步支持、文档完善

### 7.2 优势

1. **易于维护**：清晰的分层结构，职责明确
2. **易于测试**：可以 Mock 基础设施层进行单元测试
3. **易于扩展**：添加新功能只需在相应层添加代码
4. **配置灵活**：通过配置文件调整行为，无需修改代码

### 7.3 后续工作

1. **实现服务层**：封装复杂业务逻辑
2. **统一异常处理**：添加自定义异常和异常处理中间件
3. **添加中间件**：日志、监控、限流等
4. **完善测试**：单元测试、集成测试、端到端测试

---

**文档版本**：V2.0  
**创建时间**：2025-01-XX  
**维护者**：开发团队

