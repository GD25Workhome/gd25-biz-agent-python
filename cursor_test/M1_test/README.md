# Milestone 1 单元测试

本目录包含 Milestone 1 的所有单元测试用例。

## 目录结构

```
M1_test/
├── __init__.py
├── conftest.py                    # 共享的 fixtures
├── README.md                      # 本文件
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

## 运行测试

### 运行所有测试

```bash
pytest cursor_test/M1_test/
```

### 运行特定模块测试

```bash
# 基础设施层
pytest cursor_test/M1_test/infrastructure/

# 领域层
pytest cursor_test/M1_test/domain/

# 应用层
pytest cursor_test/M1_test/app/
```

### 运行特定文件测试

```bash
pytest cursor_test/M1_test/infrastructure/test_repositories.py
```

### 运行并显示覆盖率

```bash
pytest cursor_test/M1_test/ --cov=. --cov-report=html --cov-report=term
```

### 运行并显示详细输出

```bash
pytest cursor_test/M1_test/ -v
```

## 测试计划

详细的测试计划请参考：[Milestone1单元测试计划方案.md](../../doc/设计V2.0/Milestone1单元测试计划方案.md)

## 注意事项

1. 测试使用 SQLite 内存数据库，无需配置 PostgreSQL
2. 所有外部依赖（LLM API、Java 微服务）都使用 Mock
3. 测试数据在 `conftest.py` 中定义，可以在测试中复用

