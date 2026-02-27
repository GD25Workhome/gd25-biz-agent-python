# Milestone 1 单元测试计划方案

## 文档说明

本文档详细描述了 Milestone 1 (MVP 版本) 的单元测试计划，包括测试范围、测试策略、测试用例设计等。

**文档版本**：V1.0  
**创建时间**：2025-12-15  
**测试目标**：确保 Milestone 1 的各个模块功能正确、可靠

---

## 目录

1. [测试概述](#一测试概述)
2. [测试范围和目标](#二测试范围和目标)
3. [测试策略](#三测试策略)
4. [基础设施层测试计划](#四基础设施层测试计划)
5. [领域层测试计划](#五领域层测试计划)
6. [应用层测试计划](#六应用层测试计划)
7. [测试环境要求](#七测试环境要求)
8. [测试数据准备](#八测试数据准备)
9. [测试执行计划](#九测试执行计划)
10. [测试覆盖率目标](#十测试覆盖率目标)

---

## 一、测试概述

### 1.1 测试目的

- 验证 Milestone 1 各个模块的功能正确性
- 确保代码质量和可维护性
- 为后续开发提供可靠的基础
- 发现和修复潜在问题

### 1.2 测试原则

1. **独立性**：每个测试用例应该独立，不依赖其他测试的执行顺序
2. **可重复性**：测试结果应该可重复，不受外部环境影响
3. **快速执行**：单元测试应该快速执行，便于频繁运行
4. **隔离性**：使用 Mock 和 Fixture 隔离外部依赖
5. **全面性**：覆盖正常流程、异常流程和边界条件

---

## 二、测试范围和目标

### 2.1 测试范围

#### 基础设施层
- 数据库模型（User、BloodPressureRecord、Appointment）
- Repository 模式（BaseRepository、UserRepository、BloodPressureRepository、AppointmentRepository）
- 数据库连接管理（连接池、会话管理）
- LLM 客户端封装
- Java 微服务客户端

#### 领域层
- 路由系统（RouterState、路由节点、路由图、意图识别）
- 智能体工厂（AgentFactory）
- 工具注册表（TOOL_REGISTRY）
- 业务工具（血压记录工具、预约管理工具）

#### 应用层
- 配置管理（Settings）
- API 路由（聊天接口）
- 中间件（日志、异常处理）
- 数据模型（Pydantic Schemas）

### 2.2 测试目标

- **功能正确性**：验证每个模块的功能是否符合设计要求
- **异常处理**：验证异常情况的处理是否正确
- **边界条件**：验证边界条件的处理
- **代码覆盖率**：单元测试覆盖率 ≥ 70%

---

## 三、测试策略

### 3.1 测试框架

- **测试框架**：pytest
- **异步测试**：pytest-asyncio
- **Mock 框架**：unittest.mock、pytest-mock
- **数据库测试**：使用测试数据库或 SQLite 内存数据库
- **HTTP 测试**：使用 TestClient 测试 FastAPI 应用

### 3.2 测试组织结构

```
cursor_test/
└── M1_test/
    ├── __init__.py
    ├── conftest.py                    # 共享的 fixtures
    ├── infrastructure/                # 基础设施层测试
    │   ├── __init__.py
    │   ├── test_database_models.py    # 数据库模型测试
    │   ├── test_repositories.py       # Repository 测试
    │   ├── test_database_connection.py # 数据库连接测试
    │   ├── test_llm_client.py         # LLM 客户端测试
    │   └── test_java_service.py        # Java 微服务客户端测试
    ├── domain/                        # 领域层测试
    │   ├── __init__.py
    │   ├── test_router_state.py       # 路由状态测试
    │   ├── test_router_node.py        # 路由节点测试
    │   ├── test_router_tools.py       # 路由工具测试
    │   ├── test_router_graph.py       # 路由图测试
    │   ├── test_agent_factory.py       # 智能体工厂测试
    │   ├── test_tool_registry.py       # 工具注册表测试
    │   ├── test_blood_pressure_tools.py # 血压记录工具测试
    │   └── test_appointment_tools.py   # 预约管理工具测试
    └── app/                           # 应用层测试
        ├── __init__.py
        ├── test_config.py             # 配置管理测试
        ├── test_schemas.py             # 数据模型测试
        ├── test_middleware.py          # 中间件测试
        └── test_api_routes.py          # API 路由测试
```

### 3.3 Mock 策略

1. **数据库**：使用测试数据库或 SQLite 内存数据库
2. **LLM API**：Mock HTTP 请求，避免实际调用 API
3. **外部服务**：Mock Java 微服务客户端
4. **LangGraph**：Mock 智能体执行，避免实际 LLM 调用

---

## 四、基础设施层测试计划

### 4.1 数据库模型测试

**文件**：`cursor_test/M1_test/infrastructure/test_database_models.py`

#### 4.1.1 User 模型测试

**测试用例**：
1. ✅ 创建用户（正常情况）
2. ✅ 创建用户（必填字段验证）
3. ✅ 创建用户（唯一性约束：username、phone、email）
4. ✅ 用户关系（blood_pressure_records、appointments）
5. ✅ 用户时间戳（created_at、updated_at）

**测试数据**：
```python
{
    "username": "test_user",
    "phone": "13800138000",
    "email": "test@example.com",
    "is_active": True
}
```

#### 4.1.2 BloodPressureRecord 模型测试

**测试用例**：
1. ✅ 创建血压记录（正常情况）
2. ✅ 创建血压记录（必填字段验证）
3. ✅ 创建血压记录（可选字段：heart_rate、notes）
4. ✅ 血压记录与用户关系
5. ✅ 血压记录时间戳

**测试数据**：
```python
{
    "user_id": 1,
    "systolic": 120,
    "diastolic": 80,
    "heart_rate": 72,
    "record_time": datetime.utcnow(),
    "notes": "测试记录"
}
```

#### 4.1.3 Appointment 模型测试

**测试用例**：
1. ✅ 创建预约（正常情况）
2. ✅ 创建预约（必填字段验证）
3. ✅ 预约状态枚举（pending、confirmed、completed、cancelled）
4. ✅ 预约与用户关系
5. ✅ 预约时间戳

**测试数据**：
```python
{
    "user_id": 1,
    "department": "内科",
    "doctor_name": "张医生",
    "appointment_time": datetime.utcnow(),
    "status": AppointmentStatus.PENDING,
    "notes": "测试预约"
}
```

### 4.2 Repository 测试

**文件**：`cursor_test/M1_test/infrastructure/test_repositories.py`

#### 4.2.1 BaseRepository 测试

**测试用例**：
1. ✅ get_by_id（存在记录）
2. ✅ get_by_id（不存在记录）
3. ✅ get_all（正常情况）
4. ✅ get_all（分页：limit、offset）
5. ✅ create（正常情况）
6. ✅ update（正常情况）
7. ✅ update（不存在记录）
8. ✅ delete（正常情况）
9. ✅ delete（不存在记录）

#### 4.2.2 UserRepository 测试

**测试用例**：
1. ✅ get_by_username（存在用户）
2. ✅ get_by_username（不存在用户）
3. ✅ get_by_phone（存在用户）
4. ✅ get_by_phone（不存在用户）
5. ✅ 继承 BaseRepository 的所有方法

#### 4.2.3 BloodPressureRepository 测试

**测试用例**：
1. ✅ get_by_user_id（正常情况）
2. ✅ get_by_user_id（分页）
3. ✅ get_by_user_id（无记录）
4. ✅ get_by_date_range（正常情况）
5. ✅ get_by_date_range（边界条件：开始时间、结束时间）
6. ✅ 继承 BaseRepository 的所有方法

#### 4.2.4 AppointmentRepository 测试

**测试用例**：
1. ✅ get_by_user_id（正常情况）
2. ✅ get_by_user_id（分页）
3. ✅ get_by_status（正常情况）
4. ✅ get_by_status（不同状态）
5. ✅ get_by_date_range（正常情况）
6. ✅ 继承 BaseRepository 的所有方法

### 4.3 数据库连接测试

**文件**：`cursor_test/M1_test/infrastructure/test_database_connection.py`

**测试用例**：
1. ✅ create_db_pool（创建连接池）
2. ✅ get_async_engine（获取引擎）
3. ✅ get_async_session_factory（获取会话工厂）
4. ✅ get_async_session（获取会话）
5. ✅ init_db（初始化数据库）
6. ✅ 连接池关闭

### 4.4 LLM 客户端测试 (已经完成)

**文件**：`cursor_test/M1_test/infrastructure/test_llm_client.py`

**测试用例**：
1. get_llm（使用默认配置）
2. get_llm（自定义模型）
3. get_llm（自定义温度）
4. get_llm（验证 API Key 和 Base URL）
5. LLM 调用（Mock HTTP 请求）

### 4.5 Java 微服务客户端测试 (不用编写-废弃)

**文件**：`cursor_test/M1_test/infrastructure/test_java_service.py`

**测试用例**：
1. create_appointment（正常情况）
2. create_appointment（HTTP 错误处理）
3. query_appointment（查询单个预约）
4. query_appointment（查询用户所有预约）
5. query_appointment（HTTP 错误处理）
6. update_appointment（正常情况）
7. update_appointment（HTTP 错误处理）
8. 超时处理
9. 未配置 Base URL 的情况

---

## 五、领域层测试计划

### 5.1 路由状态测试 ✅

**文件**：`cursor_test/M1_test/domain/test_router_state.py`

**测试用例**：
1. ✅ RouterState 类型定义验证
2. ✅ IntentResult 模型验证（正常情况）
3. ✅ IntentResult 模型验证（边界条件：confidence 0.0-1.0）
4. ✅ IntentResult 序列化/反序列化

**完成情况**：
- ✅ 所有测试用例已实现并通过
- ✅ 测试文件可直接运行：`python cursor_test/M1_test/domain/test_router_state.py`
- ✅ 已改进 `IntentResult` 模型，为 `confidence` 字段添加了 `Field(ge=0.0, le=1.0)` 约束，确保范围验证
- ✅ 测试验证了超出范围的值（< 0.0 或 > 1.0）会正确抛出 `ValidationError`

### 5.2 路由节点测试

**文件**：`cursor_test/M1_test/domain/test_router_node.py`

**测试用例**：
1. ✅ route_node（识别血压意图）
2. ✅ route_node（识别预约意图）
3. ✅ route_node（意图不明确）
4. ✅ route_node（已确定智能体，不需要重新路由）
5. ✅ route_node（需要重新路由）
6. ✅ 状态更新验证

**完成情况**：
- ✅ 所有测试用例已实现并通过
- ✅ 测试文件可直接运行：`python cursor_test/M1_test/domain/test_router_node.py`
- ✅ 测试不使用 pytest 框架，可直接通过 main 运行
- ✅ 测试包含详细的 print 日志，方便理解测试过程
- ✅ 修复了 `route_node` 中对 `identify_intent` 的调用方式，传递字典格式参数 `{"messages": state["messages"]}`
- ✅ 所有 6 个测试用例全部通过（6/6）

### 5.3 路由工具测试 ✅

**文件**：`cursor_test/M1_test/domain/test_router_tools.py`

**测试用例**：
1. ✅ identify_intent（血压意图识别）
2. ✅ identify_intent（预约意图识别）
3. ✅ identify_intent（意图不明确）
4. ✅ identify_intent（空消息列表）
5. ✅ identify_intent（多个关键词匹配）
6. ✅ identify_intent（置信度计算）
7. ✅ identify_intent（边界条件：大小写、标点符号）

**测试数据**：
```python
# 血压意图
"我想记录血压，收缩压120，舒张压80"
"查询我的血压记录"
"更新血压数据"

# 预约意图
"我想预约内科"
"查询我的预约"
"取消预约"

# 意图不明确
"你好"
"今天天气怎么样"
```

**完成情况**：
- ✅ 所有测试用例已实现并通过
- ✅ 测试文件可直接运行：`python cursor_test/M1_test/domain/test_router_tools.py`
- ✅ 测试不使用 pytest 框架，可直接通过 main 运行
- ✅ 测试包含详细的 print 日志，方便理解测试过程
- ✅ 所有 7 个测试用例全部通过（7/7）
- ✅ 测试覆盖了所有边界条件：空消息列表、多个关键词匹配、置信度计算、大小写和标点符号处理

### 5.4 路由图测试 ✅

**文件**：`cursor_test/M1_test/domain/test_router_graph.py`

**测试用例**：
1. ✅ create_router_graph（创建路由图）
2. ✅ 路由图节点验证（route、blood_pressure_agent、appointment_agent）
3. ✅ 路由图边验证（条件边、普通边）
4. ✅ 路由图执行（Mock 智能体执行）
5. ✅ 路由图配置（checkpointer、store）

**完成情况**：
- ✅ 所有测试用例已实现并通过
- ✅ 测试文件可直接运行：`python cursor_test/M1_test/domain/test_router_graph.py`
- ✅ 测试不使用 pytest 框架，可直接通过 main 运行
- ✅ 测试包含详细的 print 日志，方便理解测试过程
- ✅ 测试覆盖了路由图的创建、节点验证、边验证、执行和配置等所有功能
- ✅ 使用 Mock 技术隔离了 AgentFactory 和智能体的依赖
- ✅ 所有 5 个测试用例全部通过（5/5）

### 5.5 智能体工厂测试

**文件**：`cursor_test/M1_test/domain/test_agent_factory.py`

**测试用例**：
1. ✅ load_config（加载配置文件）
2. ✅ load_config（配置文件不存在）
3. ✅ create_agent（创建血压智能体）
4. ✅ create_agent（创建预约智能体）
5. ✅ create_agent（智能体配置不存在）
6. ✅ create_agent（自定义 LLM）
7. ✅ create_agent（自定义工具）
8. ✅ create_agent（从文件加载提示词）
9. ✅ list_agents（列出所有智能体）

### 5.6 工具注册表测试

**文件**：`cursor_test/M1_test/domain/test_tool_registry.py`

**测试用例**：
1. ✅ 工具注册（register_tool）
2. ✅ 工具获取（get_tool，存在）
3. ✅ 工具获取（get_tool，不存在）
4. ✅ 工具初始化（init_tools）
5. ✅ 所有工具已注册验证

### 5.7 血压记录工具测试 ✅ 已完成

**文件**：`cursor_test/M1_test/domain/test_blood_pressure_tools.py`

**状态**：✅ 已完成（17个测试用例全部通过）

#### 5.7.1 record_blood_pressure 测试

**测试用例**：
1. 记录血压（正常情况）
2. 记录血压（必填字段验证）
3. 记录血压（可选字段：heart_rate、notes）
4. 记录血压（时间解析：ISO 格式）
5. 记录血压（时间解析：错误格式）
6. 记录血压（数据库会话未提供）
7. 记录血压（数据库错误处理）

#### 5.7.2 query_blood_pressure 测试

**测试用例**：
1. 查询血压（正常情况）
2. 查询血压（有记录）
3. 查询血压（无记录）
4. 查询血压（分页：limit、offset）
5. 查询血压（数据库会话未提供）

#### 5.7.3 update_blood_pressure 测试

**测试用例**：
1. 更新血压（正常情况）
2. 更新血压（部分字段更新）
3. 更新血压（记录不存在）
4. 更新血压（没有提供更新字段）
5. 更新血压（数据库会话未提供）

### 5.8 预约管理工具测试 ✅ 已完成

**文件**：`cursor_test/M1_test/domain/test_appointment_tools.py`

**状态**：✅ 已完成（23个测试用例全部通过）

#### 5.8.1 create_appointment 测试

**测试用例**：
1. 创建预约（正常情况，使用本地数据库）
2. 创建预约（使用 Java 微服务）
3. 创建预约（Java 微服务失败，降级到本地数据库）
4. 创建预约（必填字段验证）
5. 创建预约（时间解析：ISO 格式）
6. 创建预约（时间解析：错误格式）
7. 创建预约（数据库会话未提供）

#### 5.8.2 query_appointment 测试

**测试用例**：
1. 查询预约（查询单个预约）
2. 查询预约（查询用户所有预约）
3. 查询预约（使用 Java 微服务）
4. 查询预约（Java 微服务失败，降级到本地数据库）
5. 查询预约（预约不存在）
6. 查询预约（无记录）
7. 查询预约（数据库会话未提供）

#### 5.8.3 update_appointment 测试

**测试用例**：
1. 更新预约（正常情况，使用本地数据库）
2. 更新预约（使用 Java 微服务）
3. 更新预约（Java 微服务失败，降级到本地数据库）
4. 更新预约（部分字段更新）
5. 更新预约（状态更新）
6. 更新预约（预约不存在）
7. 更新预约（无效状态）
8. 更新预约（时间格式错误）
9. 更新预约（数据库会话未提供）

---

## 六、应用层测试计划

### 6.1 配置管理测试

**文件**：`cursor_test/M1_test/app/test_config.py`

**测试用例**：
1. Settings 加载（从环境变量）
2. Settings 加载（从 .env 文件）
3. Settings 属性（DB_URI、ASYNC_DB_URI、CHECKPOINTER_DB_URI）
4. Settings 默认值验证
5. Settings 类型验证

### 6.2 数据模型测试

**文件**：`cursor_test/M1_test/app/test_schemas.py`

#### 6.2.1 ChatMessage 测试

**测试用例**：
1. 创建消息（user 角色）
2. 创建消息（assistant 角色）
3. 创建消息（system 角色）
4. 消息验证（必填字段）
5. 消息序列化/反序列化

#### 6.2.2 ChatRequest 测试

**测试用例**：
1. 创建请求（正常情况）
2. 创建请求（必填字段验证）
3. 创建请求（可选字段：conversation_history）
4. 请求序列化/反序列化

#### 6.2.3 ChatResponse 测试

**测试用例**：
1. 创建响应（正常情况）
2. 创建响应（可选字段：intent、agent）
3. 响应序列化/反序列化

### 6.3 中间件测试

**文件**：`cursor_test/M1_test/app/test_middleware.py`

#### 6.3.1 LoggingMiddleware 测试

**测试用例**：
1. 日志记录（正常请求）
2. 日志记录（请求时间统计）
3. 日志记录（客户端 IP）

#### 6.3.2 ExceptionHandler 测试

**测试用例**：
1. 全局异常处理（Exception）
2. 验证异常处理（RequestValidationError）
3. HTTP 异常处理（StarletteHTTPException）
4. 异常响应格式验证

### 6.4 API 路由测试

**文件**：`cursor_test/M1_test/app/test_api_routes.py`

**测试用例**：
1. POST /api/v1/chat（正常情况）
2. POST /api/v1/chat（路由图未初始化）
3. POST /api/v1/chat（有对话历史）
4. POST /api/v1/chat（无对话历史）
5. POST /api/v1/chat（请求验证失败）
6. POST /api/v1/chat（路由图执行错误）
7. POST /api/v1/chat（响应格式验证）
8. GET /health（健康检查）

---

## 七、测试环境要求

### 7.1 软件环境

- Python 3.10+
- pytest 7.4.0+
- pytest-asyncio 0.21.0+
- pytest-mock 3.11.0+
- SQLAlchemy 2.0+
- FastAPI TestClient

### 7.2 测试数据库

- **选项 1**：使用 SQLite 内存数据库（推荐，快速）
- **选项 2**：使用独立的 PostgreSQL 测试数据库
- **选项 3**：使用 Docker 容器运行测试数据库

### 7.3 环境变量

创建 `.env.test` 文件用于测试：
```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=test_user
DB_PASSWORD=test_password
DB_NAME=test_langgraphflow
OPENAI_API_KEY=test_key
OPENAI_BASE_URL=http://localhost:8000/mock
```

---

## 八、测试数据准备

### 8.1 Fixtures

在 `conftest.py` 中定义共享的 fixtures：

```python
@pytest.fixture
async def test_db_session():
    """测试数据库会话"""
    # 创建测试数据库会话
    pass

@pytest.fixture
def test_user():
    """测试用户数据"""
    return {
        "username": "test_user",
        "phone": "13800138000",
        "email": "test@example.com"
    }

@pytest.fixture
def test_blood_pressure_record():
    """测试血压记录数据"""
    return {
        "user_id": 1,
        "systolic": 120,
        "diastolic": 80,
        "heart_rate": 72
    }

@pytest.fixture
def test_appointment():
    """测试预约数据"""
    return {
        "user_id": 1,
        "department": "内科",
        "appointment_time": "2025-01-15T10:00:00"
    }
```

### 8.2 Mock 数据

- LLM API 响应 Mock
- Java 微服务响应 Mock
- LangGraph 智能体执行 Mock

---

## 九、测试执行计划

### 9.1 测试执行顺序

1. **第一阶段**：基础设施层测试
   - 数据库模型测试
   - Repository 测试
   - 数据库连接测试
   - LLM 客户端测试
   - Java 微服务客户端测试

2. **第二阶段**：领域层测试
   - 路由系统测试
   - 智能体工厂测试
   - 工具注册表测试
   - 业务工具测试

3. **第三阶段**：应用层测试
   - 配置管理测试
   - 数据模型测试
   - 中间件测试
   - API 路由测试

### 9.2 测试命令

```bash
# 运行所有测试
pytest cursor_test/M1_test/

# 运行特定模块测试
pytest cursor_test/M1_test/infrastructure/
pytest cursor_test/M1_test/domain/
pytest cursor_test/M1_test/app/

# 运行特定文件测试
pytest cursor_test/M1_test/infrastructure/test_repositories.py

# 运行并显示覆盖率
pytest cursor_test/M1_test/ --cov=. --cov-report=html

# 运行并显示详细输出
pytest cursor_test/M1_test/ -v

# 运行并停止在第一个失败
pytest cursor_test/M1_test/ -x
```

### 9.3 持续集成

- 每次代码提交自动运行测试
- 测试失败阻止合并
- 生成测试覆盖率报告

---

## 十、测试覆盖率目标

### 10.1 覆盖率要求

- **整体覆盖率**：≥ 70%
- **核心模块覆盖率**：≥ 80%
  - Repository：≥ 85%
  - 业务工具：≥ 80%
  - 路由系统：≥ 75%
  - API 路由：≥ 70%

### 10.2 覆盖率报告

使用 `pytest-cov` 生成覆盖率报告：

```bash
pytest cursor_test/M1_test/ --cov=. --cov-report=html --cov-report=term
```

---

## 十一、测试用例模板

### 11.1 标准测试用例模板

```python
import pytest
from datetime import datetime

class TestModuleName:
    """模块名称测试类"""
    
    @pytest.mark.asyncio
    async def test_function_name_success(self, fixture_name):
        """
        测试用例：功能名称 - 成功情况
        
        Args:
            fixture_name: 测试 fixture
        """
        # Arrange（准备）
        # 准备测试数据
        
        # Act（执行）
        # 执行被测试的功能
        
        # Assert（断言）
        # 验证结果
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_function_name_failure(self, fixture_name):
        """
        测试用例：功能名称 - 失败情况
        """
        # 测试异常情况
        with pytest.raises(ExpectedException):
            # 执行会抛出异常的操作
            pass
```

### 11.2 参数化测试模板

```python
@pytest.mark.parametrize("input,expected", [
    ("test_input_1", "expected_output_1"),
    ("test_input_2", "expected_output_2"),
])
async def test_function_with_params(input, expected):
    """参数化测试"""
    result = function_under_test(input)
    assert result == expected
```

---

## 十二、测试检查清单

### 12.1 测试前检查

- [ ] 测试环境已配置
- [ ] 测试数据库已准备
- [ ] 依赖包已安装
- [ ] Mock 数据已准备
- [ ] Fixtures 已定义

### 12.2 测试后检查

- [ ] 所有测试用例已执行
- [ ] 测试覆盖率达标
- [ ] 测试报告已生成
- [ ] 失败的测试已修复
- [ ] 测试文档已更新

---

## 十三、已知问题和限制

### 13.1 已知问题

1. **数据库会话传递**：工具中的数据库会话传递机制需要完善，测试时可能需要 Mock
2. **LangGraph 集成**：智能体执行需要 Mock，避免实际 LLM 调用
3. **外部服务依赖**：Java 微服务需要 Mock，避免实际 HTTP 请求

### 13.2 测试限制

- 不测试实际的 LLM API 调用
- 不测试实际的 Java 微服务调用
- 不测试数据库迁移（由 Alembic 负责）

---

## 十四、总结

本测试计划涵盖了 Milestone 1 的所有模块，包括：

- **基础设施层**：5 个测试文件，约 50+ 个测试用例
- **领域层**：8 个测试文件，约 80+ 个测试用例
- **应用层**：4 个测试文件，约 30+ 个测试用例

**总计**：17 个测试文件，约 160+ 个测试用例

测试用例将按照本计划在 `cursor_test/M1_test/` 目录中逐步实现。

---

**文档版本**：V1.0  
**创建时间**：2025-12-15  
**维护者**：开发团队

