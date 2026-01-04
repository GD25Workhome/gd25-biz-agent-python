# SQLAlchemy的SQL日志实现方案

## 一、方案概述

### 1.1 目标

通过SQLAlchemy事件监听器机制，统一拦截和记录所有数据库SQL执行情况，包括：
- SQL语句内容
- 执行参数
- 执行时间
- 执行结果（成功/失败）
- 错误信息（如果失败）

### 1.2 技术方案

使用SQLAlchemy的事件系统（Event System）来监听数据库引擎的SQL执行事件，实现透明的日志记录，无需修改现有业务代码。

### 1.3 架构设计

```
┌─────────────────────────────────────────┐
│      SQLAlchemy Engine                   │
│  (create_async_engine)                   │
└──────────────┬──────────────────────────┘
               │
               │ 事件监听器注册
┌──────────────▼──────────────────────────┐
│   SQL事件监听器                          │
│  - before_cursor_execute                │
│  - after_cursor_execute                 │
│  - handle_error                         │
└──────────────┬──────────────────────────┘
               │
               │ 记录日志
┌──────────────▼──────────────────────────┐
│   Python Logging                        │
│  - 结构化日志格式                        │
│  - 可配置日志级别                        │
│  - 支持JSON格式输出                      │
└─────────────────────────────────────────┘
```

---

## 二、实现方案

### 2.1 核心实现位置

**文件**：`infrastructure/database/connection.py`

**函数**：`setup_db_logging()` - 设置SQL日志监听器

**调用时机**：在 `get_async_engine()` 函数中，引擎创建后立即注册事件监听器

### 2.2 事件监听器设计

#### 2.2.1 before_cursor_execute 事件

**触发时机**：SQL执行前

**功能**：
- 记录SQL语句和参数
- 记录执行开始时间
- 记录是否为批量执行（executemany）

**日志级别**：DEBUG（详细SQL信息）

#### 2.2.2 after_cursor_execute 事件

**触发时机**：SQL执行成功后

**功能**：
- 计算执行时间
- 记录执行结果摘要
- 记录影响行数（如果可用）

**日志级别**：INFO（正常执行）或 DEBUG（详细执行信息）

#### 2.2.3 handle_error 事件

**触发时机**：SQL执行出错时

**功能**：
- 记录错误信息
- 记录出错的SQL语句和参数
- 记录异常堆栈

**日志级别**：ERROR

### 2.3 配置项设计

在 `app/core/config.py` 的 `Settings` 类中添加以下配置项：

```python
# 数据库SQL日志配置
DB_SQL_LOG_ENABLED: bool = False  # 是否启用SQL日志（默认关闭）
DB_SQL_LOG_LEVEL: str = "INFO"   # SQL日志级别：DEBUG/INFO/WARNING/ERROR
DB_SQL_LOG_SLOW_QUERY_THRESHOLD: float = 1.0  # 慢查询阈值（秒）
DB_SQL_LOG_INCLUDE_PARAMS: bool = True  # 是否记录SQL参数（默认记录）
DB_SQL_LOG_MAX_SQL_LENGTH: int = 1000  # SQL语句最大记录长度（字符）
```

**配置说明**：
- `DB_SQL_LOG_ENABLED`：总开关，控制是否启用SQL日志
- `DB_SQL_LOG_LEVEL`：控制日志输出级别
- `DB_SQL_LOG_SLOW_QUERY_THRESHOLD`：超过此时间的查询会被标记为慢查询
- `DB_SQL_LOG_INCLUDE_PARAMS`：是否记录参数（可能包含敏感信息）
- `DB_SQL_LOG_MAX_SQL_LENGTH`：限制SQL语句记录长度，避免日志过大

### 2.4 日志格式设计

#### 2.4.1 结构化日志格式

使用JSON格式记录日志，便于日志聚合系统（如ELK、Loki）进行查询和分析。

**执行前日志（DEBUG级别）**：
```json
{
  "timestamp": "2024-01-01T12:00:00.000Z",
  "level": "DEBUG",
  "logger": "infrastructure.database.connection",
  "message": "Executing SQL",
  "event": "before_cursor_execute",
  "sql": "INSERT INTO biz_agent_blood_pressure_records (id, user_id, systolic, diastolic) VALUES ($1, $2, $3, $4)",
  "parameters": ["01ARZ3NDEKTSV4RRFFQ69G5FAV", "user123", 120, 80],
  "executemany": false
}
```

**执行后日志（INFO级别）**：
```json
{
  "timestamp": "2024-01-01T12:00:00.015Z",
  "level": "INFO",
  "logger": "infrastructure.database.connection",
  "message": "SQL executed successfully",
  "event": "after_cursor_execute",
  "sql": "INSERT INTO biz_agent_blood_pressure_records ...",
  "duration_ms": 15.5,
  "is_slow_query": false,
  "executemany": false
}
```

**慢查询日志（WARNING级别）**：
```json
{
  "timestamp": "2024-01-01T12:00:00.1200Z",
  "level": "WARNING",
  "logger": "infrastructure.database.connection",
  "message": "Slow SQL query detected",
  "event": "after_cursor_execute",
  "sql": "SELECT * FROM biz_agent_blood_pressure_records WHERE ...",
  "duration_ms": 1200.5,
  "is_slow_query": true,
  "threshold_ms": 1000.0
}
```

**错误日志（ERROR级别）**：
```json
{
  "timestamp": "2024-01-01T12:00:00.020Z",
  "level": "ERROR",
  "logger": "infrastructure.database.connection",
  "message": "SQL execution error",
  "event": "handle_error",
  "sql": "INSERT INTO biz_agent_blood_pressure_records ...",
  "parameters": ["01ARZ3NDEKTSV4RRFFQ69G5FAV", "user123", 120, 80],
  "error": "duplicate key value violates unique constraint",
  "error_type": "IntegrityError"
}
```

#### 2.4.2 日志字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| timestamp | string | 日志时间戳（ISO 8601格式） |
| level | string | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| logger | string | 日志记录器名称 |
| message | string | 日志消息 |
| event | string | 事件类型（before_cursor_execute/after_cursor_execute/handle_error） |
| sql | string | SQL语句（可能被截断） |
| parameters | array | SQL参数（可选，根据配置决定是否记录） |
| duration_ms | float | 执行时间（毫秒） |
| is_slow_query | boolean | 是否为慢查询 |
| threshold_ms | float | 慢查询阈值（毫秒） |
| executemany | boolean | 是否为批量执行 |
| error | string | 错误信息 |
| error_type | string | 错误类型 |

### 2.5 性能考虑

#### 2.5.1 性能影响

- **事件监听器开销**：SQLAlchemy事件监听器是同步执行的，但开销很小（微秒级）
- **日志记录开销**：日志记录是异步的（通过logging模块），不会阻塞SQL执行
- **参数序列化开销**：如果参数很大，序列化可能有一定开销

#### 2.5.2 优化策略

1. **条件记录**：只在启用日志时才注册事件监听器
2. **日志级别控制**：生产环境可以使用INFO级别，减少DEBUG日志
3. **SQL长度限制**：限制SQL语句记录长度，避免日志过大
4. **参数脱敏**：对敏感参数进行脱敏处理（可选）

### 2.6 安全考虑

#### 2.6.1 敏感信息处理

- **密码字段**：SQL参数中可能包含密码等敏感信息
- **解决方案**：
  - 通过配置项 `DB_SQL_LOG_INCLUDE_PARAMS` 控制是否记录参数
  - 可以扩展实现参数脱敏功能（后续优化）

#### 2.6.2 日志存储

- 生产环境的日志应该存储在安全的位置
- 日志文件权限应该限制访问
- 建议使用日志聚合系统，而不是直接写入文件

---

## 三、实现步骤

### 3.1 步骤1：添加配置项

在 `app/core/config.py` 的 `Settings` 类中添加SQL日志相关配置项。

### 3.2 步骤2：实现事件监听器

在 `infrastructure/database/connection.py` 中：
1. 创建 `setup_db_logging()` 函数
2. 实现三个事件监听器函数
3. 注册事件监听器到引擎

### 3.3 步骤3：集成到引擎创建流程

修改 `get_async_engine()` 函数，在引擎创建后调用 `setup_db_logging()`。

### 3.4 步骤4：测试验证

编写测试用例验证：
- 日志是否正确记录
- 配置项是否生效
- 性能影响是否可接受

---

## 四、代码实现细节

### 4.1 事件监听器实现要点

#### 4.1.1 时间记录

使用 `time.time()` 记录执行开始时间，存储在连接信息中：

```python
conn.info.setdefault('query_start_time', []).append(time.time())
```

使用栈结构（列表）支持嵌套查询（如子查询）。

#### 4.1.2 SQL语句处理

- 使用 `statement` 参数获取SQL语句
- 如果SQL过长，进行截断处理
- 移除多余的空白字符

#### 4.1.3 参数处理

- 使用 `parameters` 参数获取SQL参数
- 根据配置决定是否记录参数
- 对参数进行序列化（转换为可记录的格式）

#### 4.1.4 错误处理

- 使用 `exception_context` 获取错误信息
- 记录错误类型和错误消息
- 使用 `exc_info=True` 记录完整堆栈

### 4.2 日志记录器配置

使用独立的日志记录器：

```python
logger = logging.getLogger("infrastructure.database.connection")
```

这样可以：
- 独立控制SQL日志的级别
- 便于日志过滤和聚合
- 不影响其他模块的日志

### 4.3 异步引擎事件支持

SQLAlchemy的异步引擎（AsyncEngine）支持事件监听器，但需要注意：
- 事件监听器函数是同步的
- 不能使用 `await` 关键字
- 日志记录应该使用同步的logging API

---

## 五、使用示例

### 5.1 配置示例

在 `.env` 文件中配置：

```env
# 启用SQL日志
DB_SQL_LOG_ENABLED=true

# 设置日志级别为INFO（生产环境推荐）
DB_SQL_LOG_LEVEL=INFO

# 设置慢查询阈值为1秒
DB_SQL_LOG_SLOW_QUERY_THRESHOLD=1.0

# 记录SQL参数（开发环境可以开启，生产环境建议关闭）
DB_SQL_LOG_INCLUDE_PARAMS=true

# SQL语句最大长度
DB_SQL_LOG_MAX_SQL_LENGTH=1000
```

### 5.2 日志输出示例

**正常执行**：
```
2024-01-01 12:00:00.015 [INFO] infrastructure.database.connection: SQL executed successfully - duration_ms=15.5, sql="INSERT INTO ..."
```

**慢查询**：
```
2024-01-01 12:00:00.1200 [WARNING] infrastructure.database.connection: Slow SQL query detected - duration_ms=1200.5, threshold_ms=1000.0, sql="SELECT ..."
```

**错误**：
```
2024-01-01 12:00:00.020 [ERROR] infrastructure.database.connection: SQL execution error - error="duplicate key value violates unique constraint", sql="INSERT INTO ..."
```

### 5.3 日志查询示例

如果使用日志聚合系统（如ELK），可以查询：

- **查询慢查询**：`level:WARNING AND is_slow_query:true`
- **查询错误**：`level:ERROR AND event:handle_error`
- **查询特定SQL**：`sql:*blood_pressure*`
- **查询执行时间**：`duration_ms:>1000`

---

## 六、后续优化方向

### 6.1 参数脱敏

实现参数脱敏功能，自动识别和脱敏敏感字段（如密码、token等）。

### 6.2 性能统计

定期统计SQL执行性能指标：
- 平均执行时间
- 慢查询数量
- 错误率

### 6.3 采样率控制

在高并发场景下，可以添加采样率控制，只记录部分SQL执行情况。

### 6.4 日志聚合集成

与日志聚合系统（如ELK、Loki）集成，实现：
- 自动日志收集
- 日志分析和可视化
- 告警机制

---

## 七、总结

### 7.1 方案优势

1. **透明实现**：无需修改现有业务代码
2. **统一拦截**：可以记录所有ORM操作生成的SQL
3. **灵活配置**：通过配置项控制日志行为
4. **结构化日志**：便于日志分析和查询
5. **性能友好**：事件监听器开销小，日志记录异步

### 7.2 注意事项

1. **生产环境**：建议关闭参数记录，避免泄露敏感信息
2. **日志级别**：生产环境使用INFO级别，减少日志量
3. **慢查询阈值**：根据实际业务情况调整慢查询阈值
4. **日志存储**：确保日志存储安全，限制访问权限

### 7.3 实施建议

1. **开发环境**：启用DEBUG级别，记录详细SQL信息
2. **测试环境**：启用INFO级别，验证日志功能
3. **生产环境**：根据需求决定是否启用，建议使用INFO级别

