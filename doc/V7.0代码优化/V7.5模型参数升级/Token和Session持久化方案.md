# Token和Session持久化方案

## 一、背景与需求

### 1.1 问题描述

当前系统中，Token和Session数据存储在`ContextManager`的内存字典中（`_token_contexts`和`_session_contexts`）。当服务重启时，这些缓存数据会丢失，导致前端无法使用原有的token和session进行请求。

### 1.2 需求目标

1. **持久化存储**：将Token和Session数据持久化到数据库中
2. **自动恢复**：系统启动时自动从数据库加载缓存数据到内存
3. **实时同步**：创建或更新Token/Session时，同时更新数据库和内存缓存
4. **简化设计**：暂不考虑过期机制，保持方案简单

### 1.3 业务场景

- **Token场景**：用户通过`/login/token`接口创建Token，系统将`UserInfo`对象存储到`_token_contexts[user_id]`
- **Session场景**：用户通过`/login/session`接口创建Session，系统将包含`user_id`、`flow_info`、`doctor_info`的字典存储到`_session_contexts[session_id]`

## 二、技术方案分析

### 2.1 方案可行性评估

✅ **方案可行**，理由如下：

1. **数据库基础设施完善**：
   - 已有SQLAlchemy ORM框架
   - 已有Alembic迁移工具
   - 已有BaseRepository基础仓储模式
   - 已有异步数据库连接池

2. **启动流程支持**：
   - `main.py`的`lifespan`函数提供了启动时初始化入口
   - 可以在启动时加载数据库缓存到`ContextManager`

3. **数据模型简单**：
   - Token数据：`user_id` + `UserInfo`对象（可序列化为JSON）
   - Session数据：`session_id` + 字典对象（可序列化为JSON）

### 2.2 技术实现路径

#### 2.2.1 数据库表设计

**表1：Token缓存表（`gd2502_token_cache`）**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | String(50) | 主键，直接使用token_id（即user_id）作为ID |
| `data_info` | JSONB | UserInfo对象序列化后的数据（JSON格式） |

**表2：Session缓存表（`gd2502_session_cache`）**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | String(200) | 主键，直接使用session_id作为ID |
| `data_info` | JSONB | Session上下文字典序列化后的数据（JSON格式） |

**设计说明**：
- 每张表只有两个字段：`id`（主键）和`data_info`（JSONB类型）
- 所有业务数据都存储在`data_info`字段中，保持表结构简洁
- 使用JSONB类型支持高效的JSON查询和索引

#### 2.2.2 实现步骤

1. **创建数据库模型**：
   - `TokenCache`模型（`backend/infrastructure/database/models/token_cache.py`）
   - `SessionCache`模型（`backend/infrastructure/database/models/session_cache.py`）

2. **创建Repository**：
   - `TokenCacheRepository`（`backend/infrastructure/database/repository/token_cache_repository.py`）
   - `SessionCacheRepository`（`backend/infrastructure/database/repository/session_cache_repository.py`）

3. **修改登录接口**：
   - `create_token`接口：保存/更新Token到数据库
   - `create_session`接口：保存/更新Session到数据库

4. **实现启动时加载**：
   - 在`main.py`的`lifespan`函数中加载缓存
   - 从数据库读取所有Token和Session数据
   - 反序列化并加载到`ContextManager`的内存字典中

5. **创建数据库迁移**：
   - 使用Alembic创建迁移脚本

## 三、详细设计

### 3.1 数据库模型设计

#### 3.1.1 TokenCache模型

```python
class TokenCache(Base):
    """Token缓存模型"""
    
    __tablename__ = f"{TABLE_PREFIX}token_cache"
    
    id = Column(String(50), primary_key=True, comment="Token ID（直接使用token_id/user_id）")
    data_info = Column(JSONB, nullable=False, comment="UserInfo对象序列化数据（JSON格式）")
```

**设计说明**：
- 使用`token_id`（即`user_id`）作为主键，简化查询逻辑
- `data_info`存储`UserInfo`对象的完整数据（通过`UserInfo.data`属性获取）
- 使用JSONB类型支持高效的JSON查询和索引
- 表结构极简，只有核心字段

#### 3.1.2 SessionCache模型

```python
class SessionCache(Base):
    """Session缓存模型"""
    
    __tablename__ = f"{TABLE_PREFIX}session_cache"
    
    id = Column(String(200), primary_key=True, comment="Session ID（直接使用session_id）")
    data_info = Column(JSONB, nullable=False, comment="Session上下文字典数据（JSON格式）")
```

**设计说明**：
- 使用`session_id`作为主键（格式：`user_id_doctor_id_flow_name`，最长约200字符）
- `data_info`存储完整的Session上下文字典
- 支持通过`session_id`快速查询
- 表结构极简，只有核心字段

### 3.2 Repository设计

#### 3.2.1 TokenCacheRepository

```python
class TokenCacheRepository(BaseRepository[TokenCache]):
    """Token缓存仓储类"""
    
    async def upsert_token(self, token_id: str, data_info: Dict[str, Any]) -> TokenCache:
        """创建或更新Token缓存（upsert操作）
        
        Args:
            token_id: Token ID（即user_id）
            data_info: UserInfo对象序列化后的数据字典
            
        Returns:
            TokenCache: 创建或更新后的Token缓存记录
        """
```

**关键方法**：
- `upsert_token`：实现"存在则更新，不存在则创建"的逻辑
- 使用`token_id`作为主键，`data_info`存储所有业务数据

#### 3.2.2 SessionCacheRepository

```python
class SessionCacheRepository(BaseRepository[SessionCache]):
    """Session缓存仓储类"""
    
    async def upsert_session(self, session_id: str, data_info: Dict[str, Any]) -> SessionCache:
        """创建或更新Session缓存（upsert操作）
        
        Args:
            session_id: Session ID
            data_info: Session上下文字典数据
            
        Returns:
            SessionCache: 创建或更新后的Session缓存记录
        """
```

**关键方法**：
- `upsert_session`：实现"存在则更新，不存在则创建"的逻辑
- 使用`session_id`作为主键，`data_info`存储所有业务数据

### 3.3 接口修改设计

#### 3.3.1 create_token接口修改

**当前逻辑**：
```python
# 创建UserInfo对象
user_info = UserInfo(user_id=user_id)
if user.user_info:
    user_info.set_user_info(user.user_info)

# 存储到内存
context_manager._token_contexts[user_id] = user_info
```

**修改后逻辑**：
```python
# 创建UserInfo对象
user_info = UserInfo(user_id=user_id)
if user.user_info:
    user_info.set_user_info(user.user_info)

# 存储到内存
context_manager._token_contexts[user_id] = user_info

# 持久化到数据库（新增）
token_repo = TokenCacheRepository(session)
await token_repo.upsert_token(
    token_id=user_id,  # 使用user_id作为token_id
    data_info=user_info.data  # 序列化UserInfo数据到data_info字段
)
await session.commit()
```

#### 3.3.2 create_session接口修改

**当前逻辑**：
```python
# 构建session上下文字典
session_context = {
    "user_id": user_id,
    "flow_info": flow_info,
    "doctor_info": doctor_info
}

# 存储到内存
context_manager._session_contexts[session_id] = session_context
```

**修改后逻辑**：
```python
# 构建session上下文字典
session_context = {
    "user_id": user_id,
    "flow_info": flow_info,
    "doctor_info": doctor_info
}

# 存储到内存
context_manager._session_contexts[session_id] = session_context

# 持久化到数据库（新增）
session_repo = SessionCacheRepository(session)
await session_repo.upsert_session(
    session_id=session_id,
    data_info=session_context  # Session上下文数据存储到data_info字段
)
await session.commit()
```

**注意**：`create_session`接口当前没有`session`参数，需要添加数据库会话依赖。

### 3.4 启动时加载缓存设计

#### 3.4.1 加载逻辑

在`main.py`的`lifespan`函数中添加缓存加载步骤：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ... 现有初始化步骤 ...
    
    # 5. 加载Token和Session缓存（新增）
    logger.info("5. 加载Token和Session缓存...")
    await load_context_cache()
    logger.info("   ✓ 缓存加载完成")
    
    yield
```

#### 3.4.2 load_context_cache函数实现

```python
async def load_context_cache():
    """从数据库加载Token和Session缓存到ContextManager"""
    from backend.infrastructure.database.connection import get_session_factory
    from backend.infrastructure.database.repository.token_cache_repository import TokenCacheRepository
    from backend.infrastructure.database.repository.session_cache_repository import SessionCacheRepository
    from backend.domain.context.context_manager import get_context_manager
    from backend.domain.context.user_info import UserInfo
    
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            context_manager = get_context_manager()
            
            # 加载Token缓存
            token_repo = TokenCacheRepository(session)
            token_records = await token_repo.get_all(limit=10000)  # 加载所有Token
            
            for token_record in token_records:
                # 反序列化UserInfo对象
                token_id = token_record.id  # id字段就是token_id（即user_id）
                user_info = UserInfo(user_id=token_id)
                if token_record.data_info:
                    user_info.update(token_record.data_info)
                context_manager._token_contexts[token_id] = user_info
            
            logger.info(f"   ✓ 加载了 {len(token_records)} 个Token缓存")
            
            # 加载Session缓存
            session_repo = SessionCacheRepository(session)
            session_records = await session_repo.get_all(limit=10000)  # 加载所有Session
            
            for session_record in session_records:
                # 直接使用字典数据
                session_id = session_record.id  # id字段就是session_id
                context_manager._session_contexts[session_id] = session_record.data_info
            
            logger.info(f"   ✓ 加载了 {len(session_records)} 个Session缓存")
            
        except Exception as e:
            logger.error(f"加载缓存失败: {e}", exc_info=True)
            # 不抛出异常，允许系统继续启动（缓存加载失败不影响系统运行）
```

**设计说明**：
- 使用`get_async_session()`生成器获取数据库会话
- 加载所有Token和Session记录（限制10000条，可根据实际情况调整）
- Token数据需要反序列化为`UserInfo`对象
- Session数据直接使用字典
- 加载失败时记录日志但不阻止系统启动

## 四、实现细节

### 4.1 数据序列化/反序列化

#### 4.1.1 UserInfo序列化

**序列化**：
```python
data_info = user_info.data  # 获取UserInfo的完整数据字典，存储到data_info字段
```

**反序列化**：
```python
token_id = token_record.id  # 从id字段获取token_id（即user_id）
user_info = UserInfo(user_id=token_id)
if token_record.data_info:
    user_info.update(token_record.data_info)  # 从data_info字段恢复UserInfo对象
```

#### 4.1.2 Session数据序列化

**序列化**：
```python
data_info = session_context  # Session上下文字典直接存储到data_info字段
```

**反序列化**：
```python
session_id = session_record.id  # 从id字段获取session_id
session_context = session_record.data_info  # 从data_info字段获取Session上下文数据
```

**说明**：Session数据本身就是字典，可以直接存储到JSONB字段，无需特殊处理。

### 4.2 Upsert操作实现

**TokenCacheRepository.upsert_token**：
```python
async def upsert_token(self, token_id: str, data_info: Dict[str, Any]) -> TokenCache:
    """创建或更新Token缓存"""
    existing = await self.get_by_id(token_id)
    if existing:
        # 更新
        existing.data_info = data_info
        await self.session.flush()
        return existing
    else:
        # 创建
        return await self.create(
            id=token_id,
            data_info=data_info
        )
```

**SessionCacheRepository.upsert_session**：
```python
async def upsert_session(self, session_id: str, data_info: Dict[str, Any]) -> SessionCache:
    """创建或更新Session缓存"""
    existing = await self.get_by_id(session_id)
    if existing:
        # 更新
        existing.data_info = data_info
        await self.session.flush()
        return existing
    else:
        # 创建
        return await self.create(
            id=session_id,
            data_info=data_info
        )
```

### 4.3 错误处理

1. **数据库操作失败**：
   - 记录错误日志
   - 回滚事务
   - 抛出HTTPException（接口层面）

2. **缓存加载失败**：
   - 记录错误日志
   - 不阻止系统启动
   - 系统可以继续运行，只是缓存为空

3. **数据格式错误**：
   - 在反序列化时捕获异常
   - 记录错误日志
   - 跳过该条记录，继续加载其他记录

## 五、数据库迁移

### 5.1 创建迁移脚本

使用Alembic创建迁移：

```bash
alembic revision -m "add_token_and_session_cache_tables"
```

### 5.2 迁移脚本内容

```python
def upgrade():
    # 创建token_cache表（极简设计：只有id和data_info两个字段）
    op.create_table(
        'gd2502_token_cache',
        sa.Column('id', sa.String(50), primary_key=True, comment='Token ID（即user_id）'),
        sa.Column('data_info', postgresql.JSONB, nullable=False, comment='UserInfo对象序列化数据'),
    )
    
    # 创建session_cache表（极简设计：只有id和data_info两个字段）
    op.create_table(
        'gd2502_session_cache',
        sa.Column('id', sa.String(200), primary_key=True, comment='Session ID'),
        sa.Column('data_info', postgresql.JSONB, nullable=False, comment='Session上下文字典数据'),
    )

def downgrade():
    op.drop_table('gd2502_session_cache')
    op.drop_table('gd2502_token_cache')
```

**迁移脚本说明**：
- 表结构极简，只有`id`（主键）和`data_info`（JSONB）两个字段
- 所有业务数据都存储在`data_info`字段中
- 无需额外的索引字段，因为主键已经提供了唯一性保证

## 六、测试方案

### 6.1 单元测试

1. **Repository测试**：
   - 测试`upsert_token`的创建和更新逻辑
   - 测试`upsert_session`的创建和更新逻辑
   - 测试查询方法

2. **接口测试**：
   - 测试`create_token`接口是否保存到数据库
   - 测试`create_session`接口是否保存到数据库
   - 测试重复创建时的更新逻辑

### 6.2 集成测试

1. **缓存加载测试**：
   - 在数据库中插入测试数据
   - 重启应用
   - 验证缓存是否正确加载到`ContextManager`

2. **持久化测试**：
   - 创建Token和Session
   - 重启应用
   - 验证Token和Session是否仍然可用

## 七、潜在问题与解决方案

### 7.1 数据一致性问题

**问题**：内存缓存和数据库数据可能不一致

**解决方案**：
- 采用"数据库为主，内存为辅"的策略
- 每次创建/更新时同时更新数据库和内存
- 启动时从数据库加载，确保一致性

### 7.2 性能问题

**问题**：启动时加载大量缓存可能影响启动速度

**解决方案**：
- 使用批量查询（`get_all`方法）
- 异步加载，不阻塞其他初始化步骤
- 如果数据量很大，可以考虑分页加载或延迟加载

### 7.3 内存占用问题

**问题**：大量Token和Session数据占用内存

**解决方案**：
- 当前方案暂不考虑过期，后续可以添加：
  - 定期清理过期数据
  - LRU缓存策略
  - 限制最大缓存数量

### 7.4 并发安全问题

**问题**：多线程/多进程环境下，缓存更新可能存在竞态条件

**解决方案**：
- FastAPI是单进程多线程模型，`ContextManager`是单例
- 数据库操作通过SQLAlchemy的会话管理保证一致性
- 如果后续需要多进程部署，可以考虑使用Redis等分布式缓存

## 八、实施计划

### 8.1 开发步骤

1. **阶段1：数据库模型和Repository**（1-2小时）
   - 创建`TokenCache`和`SessionCache`模型
   - 创建对应的Repository
   - 更新`models/__init__.py`和`repository/__init__.py`

2. **阶段2：数据库迁移**（0.5小时）
   - 创建Alembic迁移脚本
   - 执行迁移测试

3. **阶段3：接口修改**（1小时）
   - 修改`create_token`接口
   - 修改`create_session`接口（添加数据库会话依赖）

4. **阶段4：启动时加载**（1小时）
   - 实现`load_context_cache`函数
   - 在`lifespan`中调用

5. **阶段5：测试验证**（1-2小时）
   - 单元测试
   - 集成测试
   - 手动验证重启场景

### 8.2 验收标准

- ✅ 创建Token后，数据保存到数据库
- ✅ 创建Session后，数据保存到数据库
- ✅ 系统重启后，Token和Session缓存自动恢复
- ✅ 前端可以使用原有的Token和Session继续请求
- ✅ 重复创建Token/Session时，数据正确更新

## 九、总结

### 9.1 方案优势

1. **简单可靠**：使用现有数据库基础设施，无需引入额外组件
2. **自动恢复**：系统启动时自动加载，无需手动干预
3. **实时同步**：创建/更新时同时更新数据库和内存，保证一致性
4. **易于扩展**：后续可以添加过期机制、清理策略等

### 9.2 注意事项

1. **数据量控制**：如果Token/Session数量很大，需要考虑性能优化
2. **过期机制**：当前方案不考虑过期，后续可能需要添加
3. **清理策略**：长期运行后，可能需要定期清理无效数据

### 9.3 后续优化方向

1. **添加过期机制**：为Token和Session添加过期时间字段
2. **定期清理**：添加定时任务清理过期数据
3. **性能优化**：如果数据量很大，考虑使用Redis等缓存中间件
4. **监控告警**：添加缓存加载失败的监控和告警

---

**文档版本**：V1.0  
**创建时间**：2025-01-27  
**作者**：AI Assistant
