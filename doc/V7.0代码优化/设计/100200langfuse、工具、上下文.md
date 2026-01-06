# Langfuse、工具、上下文开发设计文档

## 文档说明

本文档详细描述动态流程系统中数据库CRUD基础模块、工具系统、上下文管理和Langfuse可观测性的开发设计要点。这些模块是系统核心功能的重要组成部分。

**文档版本**：V1.0  
**创建时间**：2026-01-04  
**对应总体设计**：`100000动态流程总体设计.md`

---

## 目录

1. [数据库CRUD基础模块设计](#一数据库crud基础模块设计)
2. [工具系统设计](#二工具系统设计)
3. [上下文管理设计](#三上下文管理设计)
4. [Langfuse可观测性设计](#四langfuse可观测性设计)
5. [开发要点总结](#五开发要点总结)

---

## 一、数据库CRUD基础模块设计

### 1.1 设计原则

**核心原则**：独立业务表设计，支持Alembic数据库迁移

- ✅ 使用SQLAlchemy ORM进行数据访问
- ✅ 使用Alembic管理数据库schema变更
- ✅ 表名前缀统一使用`gd2502_`，独立于其他业务表
- ✅ 基础Repository模式封装通用CRUD操作
- ✅ 异步操作支持（async/await）
- ✅ 使用ULID作为主键ID生成器

### 1.2 架构设计

```
数据库CRUD基础模块架构：
┌─────────────────────────────────────────┐
│       数据库连接层 (connection)          │
│  - 异步数据库引擎                        │
│  - 连接池管理                            │
│  - 会话工厂 (SessionFactory)             │
└──────────────────┬──────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐   ┌────────▼─────────┐
│   数据模型层    │   │   Repository层    │
│  (SQLAlchemy)  │   │  (BaseRepository) │
│  - Base定义    │   │  - CRUD操作      │
│  - 业务模型    │   │  - 查询封装      │
│  - 表前缀配置  │   │  - 事务管理      │
└───────┬────────┘   └────────┬─────────┘
        │                     │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │    Alembic迁移      │
        │  - 版本管理         │
        │  - 自动生成脚本     │
        │  - 升级/降级       │
        └─────────────────────┘
```

### 1.3 核心组件

#### 1.3.1 数据库连接层

**职责**：管理数据库连接和会话

**设计要点**：

1. **异步引擎**：使用SQLAlchemy异步引擎
2. **连接池**：配置连接池参数（pool_size、max_overflow等）
3. **会话工厂**：提供异步会话工厂
4. **配置管理**：从配置文件读取数据库连接信息

**需要开发**（新模块）：
- 文件路径：`backend/infrastructure/database/connection.py`

**代码示例**：
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from backend.app.config import settings

# 异步数据库引擎（单例）
_async_engine = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

def get_async_engine():
    """获取异步数据库引擎（单例模式）"""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            settings.DB_URI,  # 从配置读取
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _async_engine

def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取异步会话工厂（单例模式）"""
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory

async def get_async_session() -> AsyncSession:
    """获取异步数据库会话（生成器）"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
```

#### 1.3.2 Base定义

**职责**：定义SQLAlchemy Base和通用功能

**设计要点**：

1. **Base定义**：使用declarative_base创建Base
2. **ID生成器**：使用ULID生成唯一ID
3. **表前缀配置**：配置表名前缀为`gd2502_`

**需要开发**（新模块）：
- 文件路径：`backend/infrastructure/database/base.py`

**代码示例**：
```python
from ulid import ULID
from sqlalchemy.orm import declarative_base

# 表名前缀配置
TABLE_PREFIX = "gd2502_"

Base = declarative_base()

def generate_ulid() -> str:
    """
    生成ULID（Universally Unique Lexicographically Sortable Identifier）
    
    Returns:
        str: ULID字符串（26个字符）
    """
    return str(ULID())
```

#### 1.3.3 数据模型

**职责**：定义业务数据模型

**设计要点**：

1. **表名前缀**：所有表名使用`gd2502_`前缀
2. **ID字段**：使用ULID作为主键
3. **时间戳字段**：包含created_at、updated_at字段
4. **注释**：为所有字段添加中文注释

**需要开发**（新模块）：
- 文件路径：`backend/infrastructure/database/models/`
- 示例：`backend/infrastructure/database/models/__init__.py`

**代码示例**：
```python
from sqlalchemy import Column, String, DateTime, func
from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid

class ExampleModel(Base):
    """示例模型"""
    
    __tablename__ = f"{TABLE_PREFIX}example"  # 表名：gd2502_example
    
    id = Column(
        String(50),
        primary_key=True,
        index=True,
        default=generate_ulid,
        comment="记录ID"
    )
    name = Column(String(100), nullable=False, comment="名称")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间"
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
```

#### 1.3.4 BaseRepository

**职责**：封装通用CRUD操作

**设计要点**：

1. **泛型设计**：使用TypeVar和Generic支持任意模型类型
2. **CRUD方法**：提供create、read、update、delete方法
3. **查询方法**：提供get_by_id、get_all等查询方法
4. **异步支持**：所有方法使用async/await

**需要开发**（新模块）：
- 文件路径：`backend/infrastructure/database/repository/base.py`

**代码示例**：
```python
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.infrastructure.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """基础仓储类"""
    
    def __init__(self, session: AsyncSession, model: Type[ModelType]):
        """
        初始化仓储
        
        Args:
            session: 数据库会话
            model: ORM模型类
        """
        self.session = session
        self.model = model
    
    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """根据ID查询"""
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
    
    async def update(self, id: str, **kwargs) -> Optional[ModelType]:
        """更新记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return None
        
        for key, value in kwargs.items():
            setattr(instance, key, value)
        
        await self.session.flush()
        return instance
    
    async def delete(self, id: str) -> bool:
        """删除记录"""
        instance = await self.get_by_id(id)
        if not instance:
            return False
        
        await self.session.delete(instance)
        await self.session.flush()
        return True
```

#### 1.3.5 业务Repository

**职责**：扩展BaseRepository，实现业务特定的查询方法

**设计要点**：

1. **继承BaseRepository**：复用通用CRUD操作
2. **业务查询**：添加业务特定的查询方法
3. **类型安全**：使用泛型指定模型类型

**需要开发**（示例）：
- 文件路径：`backend/infrastructure/database/repository/example_repository.py`

**代码示例**：
```python
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.infrastructure.database.repository.base import BaseRepository
from backend.infrastructure.database.models.example import ExampleModel

class ExampleRepository(BaseRepository[ExampleModel]):
    """示例Repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, ExampleModel)
    
    async def get_by_name(self, name: str) -> Optional[ExampleModel]:
        """根据名称查询"""
        result = await self.session.execute(
            select(self.model).where(self.model.name == name)
        )
        return result.scalar_one_or_none()
    
    async def get_by_ids(self, ids: List[str]) -> List[ExampleModel]:
        """根据ID列表批量查询"""
        result = await self.session.execute(
            select(self.model).where(self.model.id.in_(ids))
        )
        return list(result.scalars().all())
```

### 1.4 Alembic集成设计

#### 1.4.1 Alembic配置

**职责**：配置Alembic数据库迁移工具

**设计要点**：

1. **配置文件**：创建`alembic.ini`配置文件（在项目根目录）
2. **环境配置**：配置`alembic/env.py`，连接数据库和导入模型
3. **版本管理**：迁移脚本存放在`alembic/versions/`目录
4. **表前缀配置**：确保迁移脚本中的表名使用`gd2502_`前缀

**需要开发**：
- 文件路径：`alembic.ini`（在项目根目录）
- 文件路径：`alembic/env.py`（需要修改，适配01_Agent/backend）

**配置文件示例**（`alembic.ini`）：
```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN

[logger_alembic]
level = INFO
```

**环境配置示例**（`alembic/env.py`）：
```python
"""
Alembic环境配置
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# 添加backend目录到路径（用于导入backend模块）
backend_path = project_root / "01_Agent" / "backend"
sys.path.insert(0, str(backend_path))

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio

# 导入配置和模型
from backend.app.config import settings
from backend.infrastructure.database.base import Base
from backend.infrastructure.database import models  # 导入所有模型

# Alembic配置
config = context.config

# 设置数据库URL（从配置读取）
config.set_main_option("sqlalchemy.url", settings.DB_URI)

# 目标元数据
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """离线模式运行迁移"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    """执行迁移"""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """在线模式运行迁移（异步）"""
    connectable = create_async_engine(
        settings.DB_URI,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

#### 1.4.2 数据库配置

**职责**：在应用配置中添加数据库连接配置

**设计要点**：

1. **配置项**：添加数据库连接相关的配置项
2. **环境变量**：从环境变量读取数据库连接信息
3. **URI构建**：构建数据库连接URI

**需要开发**（修改现有配置）：
- 文件路径：`backend/app/config.py`

**代码示例**：
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_NAME: Optional[str] = None
    
    @property
    def DB_URI(self) -> str:
        """数据库连接URI（同步）"""
        if not all([self.DB_HOST, self.DB_PORT, self.DB_USER, self.DB_PASSWORD, self.DB_NAME]):
            raise ValueError("数据库配置不完整")
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def ASYNC_DB_URI(self) -> str:
        """数据库连接URI（异步）"""
        return self.DB_URI  # 异步和同步使用相同的URI格式
```

#### 1.4.3 迁移脚本生成

**职责**：使用Alembic生成数据库迁移脚本

**设计要点**：

1. **自动生成**：使用`alembic revision --autogenerate`自动生成迁移脚本
2. **表前缀检查**：确保生成的表名使用`gd2502_`前缀
3. **脚本审查**：生成后需要审查迁移脚本，确保正确性

**命令示例**：
```bash
# 自动生成迁移脚本
alembic revision --autogenerate -m "add example table"

# 执行迁移（升级到最新版本）
alembic upgrade head

# 查看当前版本
alembic current

# 查看迁移历史
alembic history
```

### 1.5 使用示例

#### 1.5.1 Repository使用

**代码示例**：
```python
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.example_repository import ExampleRepository

# 获取会话工厂
session_factory = get_session_factory()

# 使用Repository
async with session_factory() as session:
    repo = ExampleRepository(session)
    
    # 创建记录
    instance = await repo.create(name="示例")
    await session.commit()
    
    # 查询记录
    instance = await repo.get_by_id(instance.id)
    
    # 更新记录
    await repo.update(instance.id, name="新名称")
    await session.commit()
    
    # 删除记录
    await repo.delete(instance.id)
    await session.commit()
```

#### 1.5.2 工具中使用Repository

**代码示例**：
```python
from backend.infrastructure.database.connection import get_session_factory
from backend.infrastructure.database.repository.example_repository import ExampleRepository

@tool
async def example_tool(name: str, token_id: str = "") -> str:
    """示例工具"""
    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = ExampleRepository(session)
        
        # 创建记录
        instance = await repo.create(name=name, user_id=token_id)
        await session.commit()
        
        return f"成功创建记录：{instance.id}"
```

### 1.6 开发要点

**需要开发的内容**：

1. ✅ **数据库连接层**（`backend/infrastructure/database/connection.py`）
   - 实现异步数据库引擎
   - 实现会话工厂
   - 实现连接池管理

2. ✅ **Base定义**（`backend/infrastructure/database/base.py`）
   - 定义SQLAlchemy Base
   - 实现ULID生成器
   - 配置表名前缀常量

3. ✅ **数据模型**（`backend/infrastructure/database/models/`）
   - 创建模型目录和`__init__.py`
   - 根据业务需求创建业务模型（示例：`example.py`）
   - 确保所有表名使用`gd2502_`前缀

4. ✅ **BaseRepository**（`backend/infrastructure/database/repository/base.py`）
   - 实现基础Repository类
   - 提供通用CRUD方法
   - 支持异步操作

5. ✅ **业务Repository**（`backend/infrastructure/database/repository/`）
   - 创建Repository目录和`__init__.py`
   - 根据业务需求创建业务Repository（示例：`example_repository.py`）

6. ✅ **Alembic配置**（项目根目录）
   - 创建或修改`alembic.ini`配置文件
   - 修改`alembic/env.py`，适配backend模块
   - 确保迁移脚本中的表名使用`gd2502_`前缀

7. ✅ **数据库配置**（`backend/app/config.py`）
   - 添加数据库连接配置项
   - 实现数据库URI构建

8. ✅ **模块初始化**（`backend/infrastructure/database/__init__.py`）
   - 导出核心类和函数
   - 导入所有模型（供Alembic使用）

**参考现有代码**：

- `infrastructure/database/connection.py`：数据库连接实现（可参考）
- `infrastructure/database/base.py`：Base定义（可参考）
- `infrastructure/database/repository/base.py`：BaseRepository实现（可参考）
- `alembic/env.py`：Alembic环境配置（可参考）

**注意事项**：

1. **表前缀统一**：所有表名必须使用`gd2502_`前缀
2. **独立数据库**：如果与根目录的数据库是同一个，需要注意表名不能冲突
3. **Alembic路径**：确保Alembic能正确导入backend模块
4. **异步支持**：所有数据库操作使用异步方式
5. **事务管理**：Repository操作需要显式提交事务（`await session.commit()`）

---

## 二、工具系统设计

### 1.1 设计原则

**核心原则**：完全遵循LangGraph和LangChain标准机制

- ✅ 使用LangChain标准工具机制（`BaseTool`、`@tool`装饰器）
- ✅ 工具注册表统一管理所有工具
- ✅ 工具包装器自动注入TokenContext
- ✅ Agent从注册表获取工具，无需定制化改造

### 1.2 架构设计

```
工具系统架构：
┌─────────────────────────────────────────┐
│        工具注册表 (ToolRegistry)         │
│  - 统一管理所有业务工具                   │
│  - 提供工具注册、获取、查询接口           │
└──────────────────┬──────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐   ┌────────▼─────────┐
│  工具包装器     │   │   业务工具        │
│ TokenInjectedTool│   │  (标准LangChain) │
│  - 自动注入tokenId│   │  - @tool装饰器   │
│  - 透明包装      │   │  - BaseTool实现  │
└───────┬────────┘   └────────┬─────────┘
        │                     │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │    TokenContext     │
        │  (contextvars实现)   │
        │  - 线程安全         │
        │  - 上下文隔离       │
        └─────────────────────┘
```

### 1.3 核心组件

#### 1.3.1 工具注册表（ToolRegistry）

**职责**：统一管理所有业务工具

**设计要点**：

1. **单例模式**：确保全局唯一实例
2. **工具存储**：使用字典存储工具，key为工具名称
3. **接口设计**：
   - `register(tool: BaseTool)`：注册工具
   - `get_tool(name: str)`：获取工具
   - `get_all_tools()`：获取所有工具
   - `clear()`：清空所有工具（测试用）

**实现参考**：
- `01_Agent/backend/domain/tools/registry.py`（新设计）
- `domain/tools/registry.py`（现有实现，可借鉴）

**代码示例**：
```python
class ToolRegistry:
    """工具注册表（单例模式）"""
    
    _instance: 'ToolRegistry' = None
    _tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
```

#### 1.3.2 工具包装器（TokenInjectedTool）

**职责**：自动注入TokenContext到工具参数中

**设计要点**：

1. **透明包装**：包装原始工具，保持所有属性和行为
2. **自动注入**：在`invoke/ainvoke`时，从TokenContext获取token_id
3. **参数注入**：自动将token_id注入到工具参数中（参数名默认为`token_id`）
4. **可选注入**：支持配置是否必须token_id（`require_token`参数）

**实现参考**：
- `domain/tools/wrapper.py`（现有实现，可直接复用）

**关键机制**：
```python
class TokenInjectedTool(BaseTool):
    """工具包装器：自动注入tokenId"""
    
    def invoke(self, tool_input: Any, **kwargs) -> Any:
        # 1. 从TokenContext获取token_id
        token_id = get_token_id()
        
        # 2. 注入到工具参数中
        if isinstance(tool_input, dict):
            tool_input["token_id"] = token_id
        
        # 3. 调用原始工具
        return self._original_tool.invoke(tool_input, **kwargs)
```

#### 1.3.3 TokenContext（Token上下文）

**职责**：提供线程安全的token_id传递机制

**设计要点**：

1. **使用contextvars**：实现线程安全的上下文变量
2. **上下文管理器**：提供`with TokenContext(token_id)`语法
3. **API设计**：
   - `set_token_id(token_id: str)`：设置token_id
   - `get_token_id()`：获取token_id
   - `TokenContext(token_id)`：上下文管理器

**实现参考**：
- `domain/tools/context.py`（现有实现，可直接复用）

**代码示例**：
```python
# 使用contextvars实现
_token_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'token_id', default=None
)

def get_token_id() -> Optional[str]:
    """获取当前上下文的tokenId"""
    return _token_id_context.get()

class TokenContext:
    """工具上下文管理器"""
    def __enter__(self):
        self._token = _token_id_context.set(self.token_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            _token_id_context.reset(self._token)
```

#### 1.3.4 业务工具实现

**设计要点**：

1. **标准LangChain工具**：使用`@tool`装饰器或继承`BaseTool`
2. **参数设计**：工具参数中可包含`token_id`参数（由包装器自动注入）
3. **工具注册**：在系统启动时通过`init_tools()`函数注册所有工具

**实现参考**：
- `domain/tools/blood_pressure/record.py`（现有实现）
- `01_Agent/backend/domain/tools/blood_pressure.py`（简化版）

**代码示例**：
```python
@tool(args_schema=RecordBloodPressureInput)
async def record_blood_pressure(
    systolic: int,
    diastolic: int,
    token_id: str = "",  # 由系统自动注入
    heart_rate: Optional[int] = None,
    **kwargs
) -> str:
    """记录血压数据"""
    # 使用token_id进行数据库操作
    pass
```

### 1.4 工具初始化流程

**启动时初始化**（在`backend/main.py`的`startup_event`中）：

```python
# 1. 初始化工具注册表
from backend.domain.tools import init_tools

init_tools()  # 注册所有业务工具
```

**初始化步骤**：

1. **导入所有工具**：从各个工具模块导入工具函数
2. **注册工具**：将工具注册到ToolRegistry
3. **工具包装**：在Agent创建时，使用TokenInjectedTool包装工具

**代码示例**（`backend/domain/tools/__init__.py`）：
```python
def init_tools():
    """初始化工具注册表"""
    from backend.domain.tools.blood_pressure import record_blood_pressure
    
    tool_registry = ToolRegistry()
    tool_registry.register(record_blood_pressure)
    # ... 注册其他工具
```

### 1.5 Agent中使用工具

**设计要点**：

1. **获取工具**：从ToolRegistry获取工具列表
2. **工具包装**：使用TokenInjectedTool包装工具（在TokenContext中调用）
3. **Agent创建**：将包装后的工具列表传递给Agent

**代码示例**：
```python
# 在Agent创建时
tools = []
for tool_name in agent_config.get("tools", []):
    tool = tool_registry.get_tool(tool_name)
    if tool:
        # 使用TokenInjectedTool包装
        wrapped_tool = TokenInjectedTool(tool)
        tools.append(wrapped_tool)

# 创建Agent（在TokenContext中调用工具）
with TokenContext(token_id=token_id):
    agent.invoke(messages)
```

### 1.6 开发要点

**需要开发的内容**：

1. ✅ **工具注册表**（`backend/domain/tools/registry.py`）
   - 实现单例模式的ToolRegistry
   - 提供注册、获取、查询接口

2. ✅ **工具初始化**（`backend/domain/tools/__init__.py`）
   - 实现`init_tools()`函数
   - 导入并注册所有业务工具

3. ✅ **工具包装器**（可选，如果现有实现可用则复用）
   - 如果`domain/tools/wrapper.py`可用，则直接复用
   - 否则在`backend/domain/tools/wrapper.py`中实现

4. ✅ **TokenContext**（可选，如果现有实现可用则复用）
   - 如果`domain/tools/context.py`可用，则直接复用
   - 否则在`backend/domain/tools/context.py`中实现

**参考现有代码**：

- `domain/tools/registry.py`：工具注册表实现
- `domain/tools/wrapper.py`：工具包装器实现
- `domain/tools/context.py`：TokenContext实现
- `domain/tools/blood_pressure/record.py`：业务工具示例

---

## 三、上下文管理设计

### 3.1 设计原则

**核心原则**：分层上下文设计，职责清晰

- **RouterState**：LangGraph状态（LangGraph标准机制）
- **FlowContext**：流程级别的共享数据（Agent间数据传递）
- **UserContext**：用户相关信息（用户信息、偏好等）
- **TokenContext**：Token上下文（工具参数注入）
- **ContextManager**：上下文管理器（生命周期管理）

### 3.2 上下文层次结构

```
上下文层次结构：
┌─────────────────────────────────────┐
│      RouterState (LangGraph状态)     │
│  - messages: List[BaseMessage]      │
│  - current_intent: Optional[str]    │
│  - session_id: str                  │
│  - token_id: str                    │
│  - trace_id: Optional[str]          │
│  - user_info: Optional[str]         │
│  - history_msg: Optional[str]       │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┐
        │             │
┌───────▼──────┐ ┌───▼─────────┐
│ FlowContext  │ │ UserContext │
│ (流程上下文)  │ │ (用户上下文) │
│              │ │             │
│ - extracted_data│ │ - user_id   │
│ - shared_data  │ │ - preferences│
│ - agent_data   │ │ - settings   │
└───────┬──────┘ └─────────────┘
        │
┌───────▼──────────┐
│  TokenContext    │
│  (Token上下文)    │
│  - token_id      │
│  (contextvars)   │
└──────────────────┘
```

### 3.3 核心组件

#### 3.3.1 RouterState（LangGraph状态）

**职责**：LangGraph标准状态定义

**设计要点**：

1. **TypedDict定义**：使用TypedDict定义状态结构
2. **标准字段**：遵循LangGraph标准（messages、session_id等）
3. **扩展字段**：根据业务需求扩展字段

**实现参考**：
- `domain/router/state.py`（现有实现）
- `01_Agent/backend/domain/state.py`（简化版）

**代码示例**：
```python
class FlowState(TypedDict, total=False):
    """流程状态数据结构"""
    messages: List[BaseMessage]  # 消息列表
    session_id: str  # 会话ID
    intent: Optional[str]  # 当前意图
    # 可以根据需要扩展其他字段
```

**保持不变**：RouterState保持现有设计，无需修改

#### 3.3.2 FlowContext（流程上下文）

**职责**：流程级别的共享数据，用于Agent间数据传递

**设计要点**：

1. **数据存储**：使用字典存储流程级别的共享数据
2. **生命周期**：与流程执行周期绑定
3. **数据访问**：提供统一的访问接口
4. **提示词替换**：作为提示词占位符替换的数据源

**需要开发**（新模块）：
- 文件路径：`backend/domain/context/flow_context.py`

**代码示例**：
```python
class FlowContext:
    """流程上下文：流程级别的共享数据"""
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
    
    def set(self, key: str, value: Any) -> None:
        """设置数据"""
        self._data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取数据"""
        return self._data.get(key, default)
    
    def update(self, data: Dict[str, Any]) -> None:
        """批量更新数据"""
        self._data.update(data)
    
    def clear(self) -> None:
        """清空数据"""
        self._data.clear()
    
    @property
    def data(self) -> Dict[str, Any]:
        """获取所有数据"""
        return self._data.copy()
```

**使用场景**：

1. **Agent间数据传递**：Agent A提取的数据传递给Agent B
2. **提示词占位符替换**：`{{extracted_data}}`从FlowContext获取
3. **流程状态共享**：流程执行过程中的中间结果

#### 3.3.3 UserContext（用户上下文）

**职责**：用户相关信息的管理

**设计要点**：

1. **用户信息**：存储用户基本信息
2. **用户偏好**：存储用户偏好设置
3. **生命周期**：与用户会话绑定（可持久化）
4. **数据访问**：提供统一的访问接口

**需要开发**（新模块）：
- 文件路径：`backend/domain/context/user_context.py`

**代码示例**：
```python
class UserContext:
    """用户上下文：用户相关信息"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._data: Dict[str, Any] = {
            "user_id": user_id,
            "preferences": {},
            "settings": {},
        }
    
    def set_preference(self, key: str, value: Any) -> None:
        """设置用户偏好"""
        self._data["preferences"][key] = value
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        return self._data["preferences"].get(key, default)
    
    def set_setting(self, key: str, value: Any) -> None:
        """设置用户设置"""
        self._data["settings"][key] = value
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取用户设置"""
        return self._data["settings"].get(key, default)
    
    @property
    def data(self) -> Dict[str, Any]:
        """获取所有数据"""
        return self._data.copy()
```

**使用场景**：

1. **提示词个性化**：根据用户偏好定制提示词
2. **用户信息访问**：在工具和Agent中访问用户信息
3. **用户设置管理**：存储和访问用户设置

#### 3.3.4 ContextManager（上下文管理器）

**职责**：管理上下文的生命周期

**设计要点**：

1. **上下文创建**：在流程开始时创建FlowContext和UserContext
2. **上下文传递**：在流程执行过程中传递上下文
3. **上下文清理**：在流程结束时清理上下文（可选）
4. **上下文获取**：提供统一的上下文获取接口

**需要开发**（新模块）：
- 文件路径：`backend/domain/context/manager.py`

**代码示例**：
```python
class ContextManager:
    """上下文管理器：管理上下文生命周期"""
    
    def __init__(self):
        self._flow_contexts: Dict[str, FlowContext] = {}
        self._user_contexts: Dict[str, UserContext] = {}
    
    def create_flow_context(self, flow_id: str) -> FlowContext:
        """创建流程上下文"""
        context = FlowContext()
        self._flow_contexts[flow_id] = context
        return context
    
    def get_flow_context(self, flow_id: str) -> Optional[FlowContext]:
        """获取流程上下文"""
        return self._flow_contexts.get(flow_id)
    
    def create_user_context(self, user_id: str) -> UserContext:
        """创建用户上下文"""
        if user_id not in self._user_contexts:
            context = UserContext(user_id)
            self._user_contexts[user_id] = context
        return self._user_contexts[user_id]
    
    def get_user_context(self, user_id: str) -> Optional[UserContext]:
        """获取用户上下文"""
        return self._user_contexts.get(user_id)
    
    def clear_flow_context(self, flow_id: str) -> None:
        """清理流程上下文"""
        if flow_id in self._flow_contexts:
            del self._flow_contexts[flow_id]
```

**使用场景**：

1. **流程启动**：创建FlowContext和UserContext
2. **流程执行**：在节点中获取和更新上下文
3. **流程结束**：清理上下文（可选，也可保留用于后续会话）

### 3.4 上下文使用流程

**流程启动时**：

```python
# 1. 创建上下文管理器（单例或全局实例）
context_manager = ContextManager()

# 2. 创建流程上下文
flow_context = context_manager.create_flow_context(flow_id=session_id)

# 3. 创建或获取用户上下文
user_context = context_manager.create_user_context(user_id=token_id)

# 4. 初始化用户上下文（从数据库加载用户信息）
user_info = await load_user_info(token_id)
user_context.update(user_info)
```

**流程执行中**：

```python
# 在Agent节点中
async def agent_node(state: FlowState):
    # 1. 获取上下文
    flow_context = context_manager.get_flow_context(state["session_id"])
    user_context = context_manager.get_user_context(state["token_id"])
    
    # 2. 使用上下文数据
    extracted_data = flow_context.get("extracted_data")
    user_preference = user_context.get_preference("language")
    
    # 3. 更新上下文
    flow_context.set("extracted_data", new_data)
    user_context.set_preference("last_used_agent", agent_name)
    
    # 4. 提示词替换（从上下文获取数据）
    prompt = render_prompt(
        template=prompt_template,
        flow_context=flow_context,
        user_context=user_context
    )
```

**流程结束时**（可选）：

```python
# 清理流程上下文（可选）
context_manager.clear_flow_context(flow_id=session_id)

# 用户上下文可保留，用于后续会话
```

### 3.5 开发要点

**需要开发的内容**：

1. ✅ **FlowContext**（`backend/domain/context/flow_context.py`）
   - 实现流程上下文类
   - 提供数据存储和访问接口

2. ✅ **UserContext**（`backend/domain/context/user_context.py`）
   - 实现用户上下文类
   - 提供用户信息和偏好管理接口

3. ✅ **ContextManager**（`backend/domain/context/manager.py`）
   - 实现上下文管理器
   - 提供上下文生命周期管理接口

4. ✅ **模块初始化**（`backend/domain/context/__init__.py`）
   - 导出核心类和函数
   - 创建全局上下文管理器实例（可选）

**参考现有代码**：

- `domain/router/state.py`：RouterState定义（保持不变）
- `domain/tools/context.py`：TokenContext实现（可直接复用）

---

## 四、Langfuse可观测性设计

### 4.1 设计原则

**核心原则**：Langfuse作为唯一的可观测性方案

- ✅ **仅保留Langfuse**：移除数据库日志功能
- ✅ **统一可观测性**：所有可观测性功能通过Langfuse实现
- ✅ **错误隔离**：Langfuse失败不影响主流程

### 4.2 架构设计

```
Langfuse可观测性架构：
┌─────────────────────────────────────┐
│      Langfuse客户端 (单例)           │
│  - 全局客户端实例                    │
│  - 延迟初始化                        │
│  - 错误隔离                         │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┐
        │             │
┌───────▼──────┐ ┌───▼─────────┐
│ Trace追踪    │ │ Span记录     │
│ - 请求链路   │ │ - 节点执行   │
│ - 用户标记   │ │ - 工具调用   │
│ - 会话标记   │ │ - 元数据     │
└──────────────┘ └─────────────┘
        │
┌───────▼──────────┐
│ LLM调用日志      │
│ - 输入/输出      │
│ - 参数记录       │
│ - 思考过程       │
└──────────────────┘
```

### 4.3 核心组件

#### 4.3.1 Langfuse客户端

**职责**：管理Langfuse客户端实例

**设计要点**：

1. **单例模式**：全局唯一客户端实例
2. **延迟初始化**：首次使用时初始化
3. **错误隔离**：初始化失败不影响主流程
4. **配置管理**：从环境变量读取配置

**实现参考**：
- `infrastructure/observability/langfuse_handler.py`（现有实现，可直接复用）

**关键功能**：

1. **客户端创建**：`_get_langfuse_client()`
2. **配置检查**：`is_langfuse_available()`
3. **客户端获取**：`get_langfuse_client()`

**代码示例**：
```python
_langfuse_client: Optional["Langfuse"] = None

def _get_langfuse_client() -> Optional["Langfuse"]:
    """获取或创建Langfuse客户端实例"""
    global _langfuse_client
    
    if not settings.LANGFUSE_ENABLED:
        return None
    
    if _langfuse_client is None:
        _langfuse_client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
    
    return _langfuse_client
```

#### 4.3.2 Trace追踪

**职责**：追踪完整的请求链路

**设计要点**：

1. **Trace创建**：在API路由层创建Trace
2. **上下文设置**：设置Trace的user_id、session_id、metadata
3. **Trace ID**：支持自定义Trace ID（用于分布式追踪）

**实现参考**：
- `infrastructure/observability/langfuse_handler.py`：`set_langfuse_trace_context()`
- `app/api/routes.py`：Trace上下文设置示例

**代码示例**：
```python
# 在API路由层（app/api/routes.py或backend/app/api/routes.py）
from infrastructure.observability.langfuse_handler import set_langfuse_trace_context

@router.post("/chat")
async def chat(request: ChatRequest):
    # 设置Langfuse trace上下文
    trace_id = set_langfuse_trace_context(
        name="chat_request",
        user_id=request.token_id,
        session_id=request.session_id,
        trace_id=x_trace_id,  # 可选，从请求头获取
        metadata={
            "message_length": len(request.message),
            "history_count": len(request.conversation_history) if request.conversation_history else 0,
        }
    )
    
    # 后续的LLM调用和节点执行会自动关联到此Trace
    ...
```

#### 4.3.3 LLM调用日志

**职责**：记录所有LLM调用

**设计要点**：

1. **CallbackHandler**：使用Langfuse的CallbackHandler
2. **自动记录**：在LLM调用时自动记录
3. **思考过程**：支持提取和记录reasoning_content

**实现参考**：
- `infrastructure/observability/langfuse_handler.py`：`create_langfuse_handler()`
- `infrastructure/llm/client.py`：LLM客户端集成示例

**代码示例**：
```python
# 创建Langfuse CallbackHandler
from infrastructure.observability.langfuse_handler import create_langfuse_handler

# 在创建LLM客户端时
langfuse_handler = create_langfuse_handler(context=log_context)

llm = ChatOpenAI(
    model=model_name,
    temperature=temperature,
    callbacks=[langfuse_handler],  # 添加CallbackHandler
    **kwargs
)
```

**EnhancedLangfuseCallbackHandler**：

现有实现中已包含`EnhancedLangfuseCallbackHandler`，用于提取和记录reasoning_content（思考过程）。该实现可直接复用。

#### 4.3.4 Span记录

**职责**：记录节点执行和工具调用

**设计要点**：

1. **节点Span**：记录每个节点的执行情况
2. **工具Span**：记录工具调用（可选，LLM调用已自动记录）
3. **元数据**：记录相关的元数据信息

**实现参考**：
- `infrastructure/observability/langfuse_handler.py`：`get_langfuse_client()`

**代码示例**：
```python
# 在节点执行时记录Span（可选）
from infrastructure.observability.langfuse_handler import get_langfuse_client

langfuse_client = get_langfuse_client()
if langfuse_client:
    with langfuse_client.start_as_current_span(
        name="agent_node",
        input={"agent_name": agent_name},
        metadata={"session_id": session_id}
    ):
        # 执行节点逻辑
        result = await agent_node(state)
```

### 4.4 集成流程

#### 4.4.1 系统启动

**无需特殊初始化**：Langfuse客户端采用延迟初始化，首次使用时自动初始化。

**配置检查**（可选）：

```python
# 在启动时检查配置（可选）
from infrastructure.observability.langfuse_handler import is_langfuse_available

if not is_langfuse_available():
    logger.warning("Langfuse未启用，可观测性功能将不可用")
```

#### 4.4.2 API请求处理

**Trace创建**（在API路由层）：

```python
# 1. 设置Trace上下文
trace_id = set_langfuse_trace_context(
    name="chat_request",
    user_id=request.token_id,
    session_id=request.session_id,
    trace_id=x_trace_id,
    metadata={...}
)

# 2. 执行流程（LLM调用和节点执行会自动关联到Trace）
result = await flow.invoke(state)
```

#### 4.4.3 Agent节点执行

**LLM调用自动记录**：

```python
# 在创建LLM客户端时添加CallbackHandler
langfuse_handler = create_langfuse_handler(context=log_context)

llm = ChatOpenAI(
    model=model_name,
    callbacks=[langfuse_handler],
    **kwargs
)

# LLM调用会自动记录到Langfuse
response = await llm.ainvoke(messages)
```

#### 4.4.4 工具调用

**工具调用Span记录** 

```python
# 如果需要记录工具调用的Span（可选）
langfuse_client = get_langfuse_client()
if langfuse_client:
    with langfuse_client.start_as_current_span(
        name=f"tool_{tool_name}",
        input=tool_input,
        metadata={"tool_name": tool_name}
    ):
        result = await tool.ainvoke(tool_input)
```

### 4.5 数据库日志移除

**移除内容**：

- `infrastructure/observability/llm_logger.py`：数据库日志功能（可移除或标记为废弃）

**影响范围**：

- ✅ LLM调用日志：改为使用Langfuse记录
- ✅ 不再需要数据库日志表：移除相关的数据库模型和Repository
- ✅ 配置清理：移除数据库日志相关的配置项

**迁移步骤**：

1. **确认Langfuse正常工作**：确保所有LLM调用都能记录到Langfuse
2. **移除数据库日志代码**：删除`llm_logger.py`中的数据库写入逻辑
3. **清理配置**：移除数据库日志相关的配置项
4. **更新文档**：更新相关文档，说明可观测性方案变更

### 4.6 开发要点

**需要开发的内容**：

1. ✅ **Langfuse集成**（已存在，直接复用）
   - `infrastructure/observability/langfuse_handler.py`：可直接复用
   - 无需修改，保持现有实现

2. ✅ **API路由层集成**（需要适配）
   - 在`backend/app/api/routes.py`中集成Trace创建
   - 参考`app/api/routes.py`的实现

3. ✅ **LLM客户端集成**（需要适配）
   - 在LLM客户端创建时添加CallbackHandler
   - 参考`infrastructure/llm/client.py`的实现

4. ✅ **数据库日志移除**（清理工作）
   - 移除或标记废弃`infrastructure/observability/llm_logger.py`
   - 清理相关的数据库模型和Repository

**参考现有代码**：

- `infrastructure/observability/langfuse_handler.py`：Langfuse集成实现（可直接复用）
- `app/api/routes.py`：API路由层Trace创建示例
- `infrastructure/llm/client.py`：LLM客户端集成示例

---

## 五、开发要点总结

### 5.1 数据库CRUD基础模块开发要点

**核心任务**：

1. ✅ **数据库连接层**（`backend/infrastructure/database/connection.py`）
   - 实现异步数据库引擎
   - 实现会话工厂
   - 实现连接池管理

2. ✅ **Base定义**（`backend/infrastructure/database/base.py`）
   - 定义SQLAlchemy Base
   - 实现ULID生成器
   - 配置表名前缀常量（`gd2502_`）

3. ✅ **数据模型**（`backend/infrastructure/database/models/`）
   - 创建模型目录和`__init__.py`
   - 根据业务需求创建业务模型
   - 确保所有表名使用`gd2502_`前缀

4. ✅ **BaseRepository**（`backend/infrastructure/database/repository/base.py`）
   - 实现基础Repository类
   - 提供通用CRUD方法
   - 支持异步操作

5. ✅ **业务Repository**（`backend/infrastructure/database/repository/`）
   - 创建Repository目录和`__init__.py`
   - 根据业务需求创建业务Repository

6. ✅ **Alembic配置**（项目根目录）
   - 创建或修改`alembic.ini`配置文件
   - 修改`alembic/env.py`，适配backend模块
   - 确保迁移脚本中的表名使用`gd2502_`前缀

7. ✅ **数据库配置**（`backend/app/config.py`）
   - 添加数据库连接配置项
   - 实现数据库URI构建

8. ✅ **模块初始化**（`backend/infrastructure/database/__init__.py`）
   - 导出核心类和函数
   - 导入所有模型（供Alembic使用）

**参考代码**：

- `infrastructure/database/connection.py`：数据库连接实现（可参考）
- `infrastructure/database/base.py`：Base定义（可参考）
- `infrastructure/database/repository/base.py`：BaseRepository实现（可参考）
- `alembic/env.py`：Alembic环境配置（可参考）

**集成点**：

- 系统启动时：初始化数据库连接池
- Repository使用：在工具和API中使用Repository进行数据操作
- Alembic迁移：使用Alembic管理数据库schema变更

### 5.2 工具系统开发要点

**核心任务**：

1. ✅ **工具注册表**（`backend/domain/tools/registry.py`）
   - 实现单例模式的ToolRegistry
   - 提供注册、获取、查询接口

2. ✅ **工具初始化**（`backend/domain/tools/__init__.py`）
   - 实现`init_tools()`函数
   - 导入并注册所有业务工具

3. ✅ **工具包装器和TokenContext**（可选，如果现有实现可用则复用）
   - 如果`domain/tools/wrapper.py`和`domain/tools/context.py`可用，则直接复用
   - 否则在`backend/domain/tools/`中实现

**参考代码**：

- `domain/tools/registry.py`：工具注册表实现
- `domain/tools/wrapper.py`：工具包装器实现
- `domain/tools/context.py`：TokenContext实现
- `domain/tools/blood_pressure/record.py`：业务工具示例

**集成点**：

- 系统启动时：调用`init_tools()`初始化工具注册表
- Agent创建时：从ToolRegistry获取工具，使用TokenInjectedTool包装
- 工具调用时：在TokenContext中调用工具，自动注入token_id

### 5.3 上下文管理开发要点

**核心任务**：

1. ✅ **FlowContext**（`backend/domain/context/flow_context.py`）
   - 实现流程上下文类
   - 提供数据存储和访问接口

2. ✅ **UserContext**（`backend/domain/context/user_context.py`）
   - 实现用户上下文类
   - 提供用户信息和偏好管理接口

3. ✅ **ContextManager**（`backend/domain/context/manager.py`）
   - 实现上下文管理器
   - 提供上下文生命周期管理接口

4. ✅ **模块初始化**（`backend/domain/context/__init__.py`）
   - 导出核心类和函数
   - 创建全局上下文管理器实例（可选）

**参考代码**：

- `domain/router/state.py`：RouterState定义（保持不变）
- `domain/tools/context.py`：TokenContext实现（可直接复用）

**集成点**：

- 流程启动时：创建FlowContext和UserContext
- 流程执行中：在节点中获取和更新上下文
- 提示词替换：从上下文获取数据替换占位符
- 流程结束时：清理上下文（可选）

### 5.4 Langfuse可观测性开发要点

**核心任务**：

1. ✅ **Langfuse集成**（已存在，直接复用）
   - `infrastructure/observability/langfuse_handler.py`：可直接复用
   - 无需修改，保持现有实现

2. ✅ **API路由层集成**（需要适配）
   - 在`backend/app/api/routes.py`中集成Trace创建
   - 参考`app/api/routes.py`的实现

3. ✅ **LLM客户端集成**（需要适配）
   - 在LLM客户端创建时添加CallbackHandler
   - 参考`infrastructure/llm/client.py`的实现

4. ✅ **数据库日志移除**（清理工作）
   - 移除或标记废弃`infrastructure/observability/llm_logger.py`
   - 清理相关的数据库模型和Repository

**参考代码**：

- `infrastructure/observability/langfuse_handler.py`：Langfuse集成实现（可直接复用）
- `app/api/routes.py`：API路由层Trace创建示例
- `infrastructure/llm/client.py`：LLM客户端集成示例

**集成点**：

- API路由层：创建Trace上下文
- LLM客户端：添加CallbackHandler自动记录LLM调用
- 节点执行：可选记录Span（通常不需要）
- 工具调用：可选记录Span（通常不需要）

### 5.5 开发优先级

**高优先级**（核心功能，依赖关系）：

1. **数据库CRUD基础模块**：数据库连接、模型、Repository（必需，其他模块的基础）
2. **工具系统**：工具注册表和初始化（必需）
3. **TokenContext**：工具参数注入（必需）
4. **Langfuse集成**：可观测性功能（重要）

**中优先级**（功能增强）：

1. **FlowContext**：流程上下文（Agent间数据传递）
2. **UserContext**：用户上下文（用户信息管理）
3. **ContextManager**：上下文管理器（生命周期管理）

**低优先级**（优化和清理）：

1. **数据库日志移除**：清理废弃代码（可选）
2. **工具包装器优化**：如果现有实现有问题（可选）

### 5.6 开发注意事项

1. **代码复用**：
   - 优先复用现有代码（`domain/tools/`、`infrastructure/observability/langfuse_handler.py`）
   - 确保新代码与现有代码兼容

2. **向后兼容**：
   - 保持现有API接口不变（如果可能）
   - 支持渐进式迁移

3. **错误处理**：
   - Langfuse失败不影响主流程（错误隔离）
   - 工具注册失败应该有明确的错误提示

4. **测试覆盖**：
   - 工具注册和获取功能需要测试
   - 上下文管理功能需要测试
   - Langfuse集成需要测试（可选，集成测试）

---

## 六、里程碑开发计划

### 6.1 里程碑划分

本文档将按照里程碑的方式组织开发工作，每个里程碑都有明确的目标和交付物。

**里程碑列表**：

1. **里程碑1：数据库CRUD基础模块 + 前端数据管理（血压CRUD）**
2. **里程碑2：工具系统开发**
3. **里程碑3：上下文管理开发**
4. **里程碑4：Langfuse可观测性集成**

---

### 6.2 里程碑1：数据库CRUD基础模块 + 前端数据管理（血压CRUD）

#### 6.2.1 里程碑目标

**核心目标**：
1. 完成数据库CRUD基础模块的开发
2. 实现血压模块的数据库CRUD操作（API接口）
3. 实现前端数据管理界面（血压CRUD功能）

**交付物**：
- 数据库连接层、模型层、Repository层完整实现
- Alembic数据库迁移工具集成完成
- 血压模块API接口（CRUD）
- 前端数据管理界面（血压CRUD）
- 数据库表结构（使用`gd2502_`前缀）

#### 6.2.2 实施要点

##### 6.2.2.1 数据库模块开发

**任务1：数据库连接层开发**

- **文件路径**：`backend/infrastructure/database/connection.py`
- **实施要点**：
  - 实现异步数据库引擎（`get_async_engine()`）
  - 实现会话工厂（`get_session_factory()`）
  - 实现会话获取函数（`get_async_session()`）
  - 从配置读取数据库连接信息
  - 配置连接池参数（pool_size=10, max_overflow=20）
  - 参考代码：`infrastructure/database/connection.py`

**任务2：Base定义开发**

- **文件路径**：`backend/infrastructure/database/base.py`
- **实施要点**：
  - 定义SQLAlchemy Base（`declarative_base()`）
  - 实现ULID生成器（`generate_ulid()`）
  - 定义表名前缀常量（`TABLE_PREFIX = "gd2502_"`）
  - 参考代码：`infrastructure/database/base.py`

**任务3：数据模型开发（血压记录模型）**

- **文件路径**：`backend/infrastructure/database/models/blood_pressure.py`
- **实施要点**：
  - 定义血压记录模型（`BloodPressureRecord`）
  - 表名：`gd2502_blood_pressure_records`
  - 字段设计：
    - `id`：主键（ULID，String(50)）
    - `user_id`：用户ID（String(50)，索引）
    - `systolic`：收缩压（Integer，必填）
    - `diastolic`：舒张压（Integer，必填）
    - `heart_rate`：心率（Integer，可选）
    - `record_time`：记录时间（DateTime，可选，索引）
    - `notes`：备注（Text，可选）
    - `created_at`：创建时间（DateTime，自动生成）
    - `updated_at`：更新时间（DateTime，自动更新）
  - 所有字段添加中文注释
  - 参考代码：`infrastructure/database/models/blood_pressure.py`

**任务4：模型模块初始化**

- **文件路径**：`backend/infrastructure/database/models/__init__.py`
- **实施要点**：
  - 导入所有模型类
  - 导出模型类供Alembic使用
  - 示例代码：
    ```python
    from backend.infrastructure.database.models.blood_pressure import BloodPressureRecord
    
    __all__ = [
        "BloodPressureRecord",
    ]
    ```

**任务5：BaseRepository开发**

- **文件路径**：`backend/infrastructure/database/repository/base.py`
- **实施要点**：
  - 实现泛型BaseRepository类
  - 提供通用CRUD方法：
    - `get_by_id(id: str)`：根据ID查询
    - `get_all(limit, offset)`：查询所有记录
    - `create(**kwargs)`：创建记录
    - `update(id: str, **kwargs)`：更新记录
    - `delete(id: str)`：删除记录
  - 所有方法使用async/await
  - 参考代码：`infrastructure/database/repository/base.py`

**任务6：血压Repository开发**

- **文件路径**：`backend/infrastructure/database/repository/blood_pressure_repository.py`
- **实施要点**：
  - 继承BaseRepository[BloodPressureRecord]
  - 实现业务特定查询方法：
    - `get_by_user_id(user_id, limit, offset)`：根据用户ID查询
    - `get_by_date_range(user_id, start_date, end_date)`：根据日期范围查询（可选）
  - 参考代码：`infrastructure/database/repository/blood_pressure_repository.py`

**任务7：Repository模块初始化**

- **文件路径**：`backend/infrastructure/database/repository/__init__.py`
- **实施要点**：
  - 导出BaseRepository和业务Repository
  - 示例代码：
    ```python
    from backend.infrastructure.database.repository.base import BaseRepository
    from backend.infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
    
    __all__ = [
        "BaseRepository",
        "BloodPressureRepository",
    ]
    ```

**任务8：数据库模块初始化**

- **文件路径**：`backend/infrastructure/database/__init__.py`
- **实施要点**：
  - 导出Base、连接函数、Repository等
  - 导入所有模型（供Alembic使用）
  - 示例代码：
    ```python
    from backend.infrastructure.database.base import Base, TABLE_PREFIX, generate_ulid
    from backend.infrastructure.database.connection import (
        get_async_engine,
        get_session_factory,
        get_async_session,
    )
    from backend.infrastructure.database import models  # 导入所有模型
    
    __all__ = [
        "Base",
        "TABLE_PREFIX",
        "generate_ulid",
        "get_async_engine",
        "get_session_factory",
        "get_async_session",
    ]
    ```

**任务9：数据库配置**

- **文件路径**：`backend/app/config.py`
- **实施要点**：
  - 添加数据库连接配置项：
    - `DB_HOST`：数据库主机
    - `DB_PORT`：数据库端口
    - `DB_USER`：数据库用户
    - `DB_PASSWORD`：数据库密码
    - `DB_NAME`：数据库名称
  - 添加数据库URI属性：
    - `DB_URI`：同步数据库URI
    - `ASYNC_DB_URI`：异步数据库URI（与同步相同）
  - 从环境变量读取配置
  - 参考代码：`app/core/config.py`

**任务10：Alembic配置**

- **文件路径**：`alembic/env.py`（修改）
- **实施要点**：
  - 修改Alembic环境配置，适配backend模块
  - 添加backend路径到sys.path
  - 导入backend模块的配置和模型
  - 设置数据库URL（从backend配置读取）
  - 设置目标元数据（backend.Base.metadata）
  - 参考代码：`alembic/env.py`（现有实现）

**任务11：Alembic迁移脚本生成**

- **命令**：`alembic revision --autogenerate -m "init schema with gd2502 prefix"`
- **实施要点**：
  - 生成初始schema迁移脚本
  - 检查生成的表名是否正确（使用`gd2502_`前缀）
  - 如果表名不正确，手动修改迁移脚本
  - 执行迁移：`alembic upgrade head`
  - 验证数据库表结构

##### 6.2.2.2 血压模块API接口开发

**任务12：API Schema定义（模块化设计）**

- **文件结构**：采用模块化设计，按业务功能拆分Schema文件
  - `backend/app/api/schemas/__init__.py`：导出所有Schema类
  - `backend/app/api/schemas/chat.py`：聊天相关Schema
  - `backend/app/api/schemas/blood_pressure.py`：血压记录相关Schema
  - `backend/app/api/schemas/users.py`：用户相关Schema

- **文件路径**：`backend/app/api/schemas/blood_pressure.py`
- **实施要点**：
  - 添加血压记录相关的Schema：
    - `BloodPressureRecordCreate`：创建请求模型
    - `BloodPressureRecordUpdate`：更新请求模型
    - `BloodPressureRecordResponse`：响应模型
  - 字段验证：收缩压、舒张压范围验证
  - 示例代码：
    ```python
    from typing import Optional
    from datetime import datetime
    from pydantic import BaseModel, Field
    
    class BloodPressureRecordCreate(BaseModel):
        """创建血压记录请求"""
        user_id: str = Field(description="用户ID")
        systolic: int = Field(ge=50, le=250, description="收缩压（50-250 mmHg）")
        diastolic: int = Field(ge=30, le=200, description="舒张压（30-200 mmHg）")
        heart_rate: Optional[int] = Field(None, ge=30, le=200, description="心率（30-200 bpm）")
        record_time: Optional[datetime] = Field(None, description="记录时间")
        notes: Optional[str] = Field(None, description="备注")
    
    class BloodPressureRecordUpdate(BaseModel):
        """更新血压记录请求"""
        systolic: Optional[int] = Field(None, ge=50, le=250, description="收缩压")
        diastolic: Optional[int] = Field(None, ge=30, le=200, description="舒张压")
        heart_rate: Optional[int] = Field(None, ge=30, le=200, description="心率")
        record_time: Optional[datetime] = Field(None, description="记录时间")
        notes: Optional[str] = Field(None, description="备注")
    
    class BloodPressureRecordResponse(BaseModel):
        """血压记录响应"""
        id: str
        user_id: str
        systolic: int
        diastolic: int
        heart_rate: Optional[int]
        record_time: Optional[datetime]
        notes: Optional[str]
        created_at: datetime
        updated_at: Optional[datetime]
    ```

**任务13：API路由开发（模块化设计）**

- **文件结构**：采用模块化设计，按业务功能拆分路由文件
  - `backend/app/api/routes/__init__.py`：聚合所有子路由
  - `backend/app/api/routes/chat.py`：聊天相关路由
  - `backend/app/api/routes/blood_pressure.py`：血压记录CRUD路由
  - `backend/app/api/routes/users.py`：用户CRUD路由

- **文件路径**：`backend/app/api/routes/blood_pressure.py`
- **实施要点**：
  - 添加血压记录CRUD路由：
    - `GET /api/blood-pressure`：查询列表（支持user_id、limit、offset参数）
    - `GET /api/blood-pressure/{id}`：根据ID查询
    - `POST /api/blood-pressure`：创建记录
    - `PUT /api/blood-pressure/{id}`：更新记录
    - `DELETE /api/blood-pressure/{id}`：删除记录
  - 使用Repository进行数据库操作
  - 异常处理：404、400等HTTP异常
  - 示例代码：
    ```python
    from fastapi import APIRouter, HTTPException, Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.infrastructure.database.connection import get_async_session
    from backend.infrastructure.database.repository.blood_pressure_repository import BloodPressureRepository
    from backend.app.api.schemas.blood_pressure import (
        BloodPressureRecordCreate,
        BloodPressureRecordUpdate,
        BloodPressureRecordResponse,
    )
    
    @router.get("/api/blood-pressure", response_model=List[BloodPressureRecordResponse])
    async def list_blood_pressure(
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        session: AsyncSession = Depends(get_async_session)
    ):
        """查询血压记录列表"""
        repo = BloodPressureRepository(session)
        if user_id:
            records = await repo.get_by_user_id(user_id, limit, offset)
        else:
            records = await repo.get_all(limit, offset)
        await session.commit()
        return records
    
    @router.post("/api/blood-pressure", response_model=BloodPressureRecordResponse)
    async def create_blood_pressure(
        data: BloodPressureRecordCreate,
        session: AsyncSession = Depends(get_async_session)
    ):
        """创建血压记录"""
        repo = BloodPressureRepository(session)
        record = await repo.create(**data.dict())
        await session.commit()
        return record
    
    # ... 其他路由
    ```

**任务14：API路由注册**

- **文件路径**：`backend/main.py`（修改）
- **实施要点**：
  - 确保API路由已注册到FastAPI应用
  - 检查路由前缀是否正确

##### 6.2.2.3 前端数据管理界面开发

**任务15：前端Tab页结构改造**

- **文件路径**：`frontend/index.html`（修改）
- **实施要点**：
  - 添加Tab页导航（聊天/数据管理）
  - 修改页面布局，支持Tab页切换
  - 保留现有聊天界面作为第一个Tab页
  - 添加数据管理Tab页作为第二个Tab页
  - 数据管理Tab页中包含子Tab页（血压）
  - CSS样式：Tab页样式、子Tab页样式

**任务16：血压CRUD界面开发**

- **文件路径**：`frontend/index.html`（修改）
- **实施要点**：
  - 血压列表页面：
    - 表格展示血压记录列表
    - 支持分页（limit、offset）
    - 支持按user_id筛选
    - 显示字段：ID、用户ID、收缩压、舒张压、心率、记录时间、备注、操作（编辑/删除）
    - 添加"新建"按钮
  - 血压创建/编辑表单：
    - 表单字段：用户ID、收缩压、舒张压、心率、记录时间、备注
    - 字段验证（前端验证）
    - 提交按钮
    - 取消按钮
  - JavaScript功能：
    - 列表查询（GET /api/blood-pressure）
    - 创建记录（POST /api/blood-pressure）
    - 更新记录（PUT /api/blood-pressure/{id}）
    - 删除记录（DELETE /api/blood-pressure/{id}）
    - 表单验证
    - 错误处理
    - 成功提示

**任务17：前端样式优化**

- **文件路径**：`frontend/index.html`（修改）
- **实施要点**：
  - Tab页样式（选中状态、hover状态）
  - 表格样式（边框、间距、对齐）
  - 表单样式（输入框、按钮、验证错误提示）
  - 响应式设计（适配不同屏幕尺寸）
  - 保持与现有聊天界面风格一致

##### 6.2.2.4 测试验证

**任务18：数据库模块测试**

- **测试内容**：
  - 数据库连接测试
  - 模型创建测试
  - Repository CRUD操作测试
  - 事务管理测试

**任务19：API接口测试**

- **测试内容**：
  - 血压记录CRUD API接口测试
  - 参数验证测试
  - 异常处理测试
  - 可以使用Postman或curl进行测试

**任务20：前端功能测试**

- **测试内容**：
  - Tab页切换功能
  - 血压记录列表展示
  - 创建血压记录
  - 编辑血压记录
  - 删除血压记录
  - 表单验证
  - 错误提示

#### 6.2.3 里程碑1验收标准

1. ✅ 数据库连接层、模型层、Repository层完整实现
2. ✅ Alembic数据库迁移工具集成完成，能够生成和执行迁移脚本
3. ✅ 血压记录表已创建（表名：`gd2502_blood_pressure_records`）
4. ✅ 用户表已创建（表名：`gd2502_users`）
5. ✅ 血压模块API接口完整实现（CRUD）
6. ✅ 用户模块API接口完整实现（CRUD）
7. ✅ API代码采用模块化设计（Schema和路由按业务功能拆分）
8. ✅ 前端数据管理界面完整实现（血压CRUD、用户CRUD）
9. ✅ 前端Tab页切换正常
10. ✅ 所有功能测试通过
11. ✅ 代码符合项目规范（注释、类型提示等）

#### 6.2.4 模块化设计说明

**设计原则**：
- 按业务功能模块拆分代码，提高代码可维护性和可扩展性
- 每个模块独立管理自己的Schema和路由
- 通过`__init__.py`统一导出，保持向后兼容

**API Schema模块化结构**：
```
backend/app/api/schemas/
├── __init__.py          # 导出所有Schema类
├── chat.py              # 聊天相关Schema
├── blood_pressure.py    # 血压记录相关Schema
└── users.py             # 用户相关Schema
```

**API路由模块化结构**：
```
backend/app/api/routes/
├── __init__.py          # 聚合所有子路由
├── chat.py              # 聊天相关路由
├── blood_pressure.py    # 血压记录CRUD路由
└── users.py             # 用户CRUD路由
```

**优势**：
1. **代码组织清晰**：每个业务模块的代码集中管理，便于查找和维护
2. **易于扩展**：新增业务模块只需添加新的Schema和路由文件
3. **降低耦合**：各模块之间相互独立，修改一个模块不影响其他模块
4. **便于测试**：可以针对单个模块进行单元测试
5. **团队协作**：不同开发者可以并行开发不同模块，减少代码冲突

---

### 6.3 里程碑2：工具系统开发

#### 6.3.1 里程碑目标

**核心目标**：
1. 完成工具注册表开发
2. 完成工具包装器开发（TokenContext注入）
3. 完成TokenContext开发
4. 工具初始化流程实现
5. Agent中使用工具的集成

**交付物**：
- 工具注册表（ToolRegistry）
- 工具包装器（TokenInjectedTool）
- TokenContext（Token上下文）
- 工具初始化代码
- 文档中的工具系统设计完整实现

#### 6.3.2 前置任务：升级聊天接口和前端

在开始工具系统开发之前，需要先升级聊天接口的Schema和前端界面，以支持token_id、conversation_history、user_info、current_date等字段，以及TraceId追踪功能。

##### 6.3.2.0.1 升级ChatRequest Schema

- **文件路径**：`backend/app/api/schemas/chat.py`
- **实施要点**：
  - 添加`token_id`字段（必填）：令牌ID（当前阶段等于用户ID）
  - 添加`conversation_history`字段（可选）：对话历史列表
  - 添加`user_info`字段（可选）：患者基础信息（多行文本）
  - 添加`current_date`字段（可选）：当前日期时间（格式：YYYY-MM-DD HH:mm）
  - 参考代码：`app/schemas/chat.py`
- **验收标准**：
  - ChatRequest包含所有必需字段
  - 字段类型和验证规则正确
  - 与现有路由兼容

##### 6.3.2.0.2 升级前端聊天界面

- **文件路径**：`01_Agent/frontend/js/chat.js`
- **实施要点**：
  - 添加TraceId相关功能：
    - TraceId输入框（支持手动输入或自动生成）
    - 自动生成TraceId开关（每次发送重新生成）
    - 生成TraceId按钮
  - 添加记录日期时间字段：
    - 日期时间输入框（datetime-local类型，支持降级为text）
    - 自动保存到localStorage
    - 从localStorage恢复上次的值
  - 添加用户选择功能：
    - 用户选择按钮（打开用户选择弹框）
    - 用户选择弹框（搜索、选择用户）
    - 自动填充患者基础信息
  - 添加患者基础信息输入框：
    - 多行文本输入框
    - 支持手动编辑
    - 选择用户时自动填充
  - 更新发送消息逻辑：
    - 包含token_id、conversation_history、user_info、current_date字段
    - 在请求头中包含X-Trace-ID（如果提供了traceId）
    - 维护conversation_history状态
  - 参考代码：`web/chat.html`
- **验收标准**：
  - 前端界面包含所有必需字段
  - TraceId功能正常（生成、自动生成开关）
  - 日期时间字段正常（保存、恢复）
  - 用户选择功能正常（选择、搜索、自动填充）
  - 发送消息时包含所有必需字段

##### 6.3.2.0.3 更新聊天路由

- **文件路径**：`backend/app/api/routes/chat.py`
- **实施要点**：
  - 从请求头获取X-Trace-ID（如果提供）
  - 使用request.token_id设置TokenContext
  - 使用request.conversation_history构建消息历史
  - 使用request.user_info和request.current_date（如果提供）
  - 支持Langfuse Trace追踪（如果配置了Langfuse）
- **验收标准**：
  - 路由正确处理所有新字段
  - TokenContext正确设置
  - Trace追踪正常工作（如果配置了Langfuse）

#### 6.3.3 实施要点

##### 6.3.3.1 工具注册表开发

- **文件路径**：`backend/domain/tools/registry.py`
- **实施要点**：
  - 实现单例模式的ToolRegistry
  - 提供注册、获取、查询接口
  - 参考代码：`domain/tools/registry.py`

##### 6.3.3.2 TokenContext开发

- **文件路径**：`backend/domain/tools/context.py`
- **实施要点**：
  - 使用contextvars实现TokenContext
  - 提供上下文管理器接口
  - 参考代码：`domain/tools/context.py`

##### 6.3.3.3 工具包装器开发

- **文件路径**：`backend/domain/tools/wrapper.py`
- **实施要点**：
  - 实现TokenInjectedTool包装器
  - 自动注入token_id到工具参数
  - 参考代码：`domain/tools/wrapper.py`

##### 6.3.3.4 工具初始化

- **文件路径**：`backend/domain/tools/__init__.py`
- **实施要点**：
  - 实现`init_tools()`函数
  - 注册所有业务工具
  - 在系统启动时调用初始化函数

##### 6.3.3.5 Agent集成

- **实施要点**：
  - 在Agent创建时从ToolRegistry获取工具
  - 使用TokenInjectedTool包装工具
  - 在TokenContext中调用工具

#### 6.3.4 里程碑2验收标准

**前置任务验收标准**：
1. ✅ ChatRequest Schema包含所有必需字段（token_id、conversation_history、user_info、current_date）
2. ✅ 前端界面包含TraceId、日期时间、用户选择、患者基础信息等字段
3. ✅ 聊天路由正确处理所有新字段并设置TokenContext
4. ✅ Trace追踪功能正常（如果配置了Langfuse）

**工具系统验收标准**：
1. ✅ 工具注册表完整实现
2. ✅ TokenContext完整实现
3. ✅ 工具包装器完整实现
4. ✅ 工具初始化流程正常
5. ✅ Agent能够正确使用工具
6. ✅ TokenContext注入功能正常

---

### 6.4 里程碑3：上下文管理开发

#### 6.4.1 里程碑目标

**核心目标**：
1. 完成FlowContext开发
2. 完成UserContext开发
3. 完成ContextManager开发
4. 上下文在流程中的使用集成

**交付物**：
- FlowContext（流程上下文）
- UserContext（用户上下文）
- ContextManager（上下文管理器）
- 文档中的上下文管理设计完整实现

#### 6.4.2 实施要点

##### 6.4.2.1 FlowContext开发

- **文件路径**：`backend/domain/context/flow_context.py`
- **实施要点**：
  - 实现流程上下文类
  - 提供数据存储和访问接口
  - 支持Agent间数据传递

##### 6.4.2.2 UserContext开发

- **文件路径**：`backend/domain/context/user_context.py`
- **实施要点**：
  - 实现用户上下文类
  - 提供用户信息和偏好管理接口

##### 6.4.2.3 ContextManager开发

- **文件路径**：`backend/domain/context/manager.py`
- **实施要点**：
  - 实现上下文管理器
  - 提供上下文生命周期管理接口

##### 6.4.2.4 流程集成

- **实施要点**：
  - 在流程启动时创建FlowContext和UserContext
  - 在节点中获取和更新上下文
  - 在提示词替换中使用上下文数据

#### 6.4.3 里程碑3验收标准

1. ✅ FlowContext完整实现 - **已完成** (2026-01-05)
2. ✅ UserContext完整实现 - **已完成** (2026-01-05)
3. ✅ ContextManager完整实现 - **已完成** (2026-01-05)
4. ✅ 上下文在流程中正确使用 - **已完成** (2026-01-05)
5. ✅ 上下文数据能够正确传递 - **已完成** (2026-01-05)

**实现文件**：
- `backend/domain/context/flow_context.py` - FlowContext实现
- `backend/domain/context/user_context.py` - UserContext实现
- `backend/domain/context/manager.py` - ContextManager实现
- `backend/domain/context/__init__.py` - 模块导出
- `backend/app/api/routes/chat.py` - 在API路由层集成上下文
- `backend/infrastructure/prompts/manager.py` - 提示词管理器支持上下文占位符替换
- `cursor_test/test_context_management.py` - 测试用例

---

### 6.5 里程碑4：Langfuse可观测性集成

#### 6.5.1 里程碑目标

**核心目标**：
1. 集成Langfuse可观测性功能
2. 实现Trace追踪
3. 实现LLM调用日志记录
4. 移除数据库日志功能（可选）

**交付物**：
- Langfuse集成完整实现
- API路由层Trace创建
- LLM客户端CallbackHandler集成
- 文档中的Langfuse可观测性设计完整实现

#### 6.5.2 实施要点

##### 6.5.2.1 Langfuse集成复用

- **实施要点**：
  - 复用现有Langfuse集成代码（`infrastructure/observability/langfuse_handler.py`）
  - 检查配置是否正确

##### 6.5.2.2 API路由层集成

- **文件路径**：`backend/app/api/routes.py`（修改）
- **实施要点**：
  - 在API路由层创建Trace上下文
  - 参考代码：`app/api/routes.py`

##### 6.5.2.3 LLM客户端集成

- **文件路径**：`backend/infrastructure/llm/client.py`（修改）
- **实施要点**：
  - 在LLM客户端创建时添加CallbackHandler
  - 参考代码：`infrastructure/llm/client.py`

##### 6.5.2.4 数据库日志移除（可选）

- **实施要点**：
  - 移除或标记废弃数据库日志功能
  - 清理相关代码

#### 6.5.3 里程碑4验收标准

1. ✅ Langfuse集成正常工作 - **已完成** (2026-01-05)
2. ✅ Trace追踪功能正常 - **已完成** (2026-01-05)
3. ✅ LLM调用日志记录正常 - **已完成** (2026-01-05)
4. ✅ 可观测性功能完整实现 - **已完成** (2026-01-05)

**实现文件**：
- `backend/infrastructure/observability/langfuse_handler.py` - Langfuse集成模块
- `backend/infrastructure/observability/__init__.py` - 模块导出
- `backend/app/api/routes/chat.py` - API路由层Trace创建
- `backend/infrastructure/llm/client.py` - LLM客户端集成CallbackHandler
- `requirements.txt` - 添加langfuse依赖
- `cursor_test/test_langfuse_integration.py` - 测试用例

**配置要求**：
- 环境变量：`LANGFUSE_ENABLED=true`
- 环境变量：`LANGFUSE_PUBLIC_KEY=your_public_key`
- 环境变量：`LANGFUSE_SECRET_KEY=your_secret_key`
- 环境变量：`LANGFUSE_HOST=https://cloud.langfuse.com` (可选，默认值)

---

### 6.6 开发计划总结

**开发顺序**：

1. **里程碑1**：数据库CRUD基础模块 + 前端数据管理（血压CRUD）
   - 优先级：最高（其他模块的基础）
   - 预计时间：5-7天

2. **里程碑2**：工具系统开发
   - 优先级：高（核心功能）
   - 预计时间：3-5天

3. **里程碑3**：上下文管理开发
   - 优先级：中（功能增强）
   - 预计时间：3-5天

4. **里程碑4**：Langfuse可观测性集成
   - 优先级：中（可观测性功能）
   - 预计时间：2-3天

**总预计时间**：13-20天

**注意事项**：

1. 里程碑1是其他里程碑的基础，必须优先完成
2. 里程碑2和里程碑3可以并行开发（如果资源允许）
3. 里程碑4可以在其他里程碑完成后进行
4. 每个里程碑完成后需要进行验收测试
5. 建议使用Git分支管理，每个里程碑一个分支

---

**文档版本**：V1.0  
**创建时间**：2026-01-04  
**对应代码路径**：`/Users/m684620/work/github_GD25/gd25-biz-agent-python_cursor/01_Agent/backend`

