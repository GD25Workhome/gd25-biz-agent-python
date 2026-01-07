# 动态流程与Langfuse最小化测试

## 目录结构

```
cursor_test/langfuse/02flow/
├── README.md                     # 本文件
├── test_minimal_flow.py          # 测试主文件
├── core/                         # 核心模块
│   ├── __init__.py
│   ├── config.py                 # 配置（从项目根目录.env读取）
│   ├── state.py                  # 状态定义
│   └── definition.py             # 流程定义
├── langfuse_local/               # Langfuse相关（重命名避免与第三方库冲突）
│   ├── __init__.py
│   └── handler.py                # Langfuse Handler
├── flows/                        # 流程构建
│   ├── __init__.py
│   └── builder.py                # 流程构建器
├── agents/                       # Agent创建
│   ├── __init__.py
│   └── factory.py                # Agent工厂
└── llm/                          # LLM客户端
    ├── __init__.py
    ├── client.py                 # LLM客户端
    └── providers/
        ├── __init__.py
        ├── registry.py           # 供应商注册表
        └── manager.py            # 供应商管理器
```

## 运行方式

### 方式1：从项目根目录运行（推荐）

```bash
cd /path/to/gd25-biz-agent-python_cursor
python cursor_test/langfuse/02flow/test_minimal_flow.py
```

### 方式2：从测试目录运行

```bash
cd cursor_test/langfuse/02flow
python test_minimal_flow.py
```

### 方式3：作为模块运行

```bash
cd /path/to/gd25-biz-agent-python_cursor
python -m cursor_test.langfuse.02flow.test_minimal_flow
```

## 配置说明

所有配置从项目根目录的 `.env` 文件读取，包括：

- `LANGFUSE_ENABLED` - 是否启用Langfuse
- `LANGFUSE_PUBLIC_KEY` - Langfuse公钥
- `LANGFUSE_SECRET_KEY` - Langfuse密钥
- `LANGFUSE_HOST` - Langfuse服务器地址
- `DOUBAO_API_KEY` - 模型API密钥（或其他供应商）

## 代码特性

1. **自包含**：所有代码都在 `02flow` 目录下，不依赖项目根目录代码
2. **简化版**：移除了不必要的依赖（提示词文件、工具等）
3. **核心逻辑保留**：保留了Langfuse Handler创建、ContextVar传递等核心逻辑
4. **独立测试**：可以独立修改和测试，不影响生产代码

## 测试流程

1. 设置Trace上下文（`set_langfuse_trace_context`）
2. 创建流程定义（单节点Agent流程）
3. 构建图（`GraphBuilder.build_graph`）
4. 编译图
5. 执行流程
6. 验证结果

## 关键测试点

- ContextVar在节点函数中的传递
- Handler在运行时的创建
- LLM调用是否正确关联到Trace
- 多节点流程的Trace聚合

## 已知问题

1. **包名冲突**：原 `langfuse` 目录已重命名为 `langfuse_local`，避免与第三方库 `langfuse` 冲突
2. **trace_context参数**：如果 LangfuseCallbackHandler 版本不支持 `trace_context` 参数，需要更新 Langfuse 库版本

## 修改建议

在测试目录中可以自由修改代码，尝试不同的埋点方式：

1. 修改 `langfuse_local/handler.py` 中的Handler创建逻辑
2. 修改 `flows/builder.py` 中的节点函数创建逻辑
3. 修改 `test_minimal_flow.py` 中的测试场景

## 依赖库

需要安装以下依赖（已在项目根目录的 `requirements.txt` 中）：

- langchain
- langgraph
- langfuse
- pydantic
- pydantic-settings

---

**文档生成时间**：2025-01-07  
**目的**：用于实验和修复Langfuse动态流程记录日志问题

