# LangGraphFlow Multi-Agent Router V2.0

多智能体路由系统，基于 LangGraph 和 LangChain 构建。

## 项目简介

本项目是一个基于 LangGraph 的多智能体路由系统，支持根据用户意图自动路由到对应的专业智能体进行处理。当前版本（MVP）实现了血压记录和复诊管理两个智能体。

## 功能特性

### Milestone 1 (MVP) 功能

- ✅ **血压记录智能体**：支持记录、查询、更新血压数据
- ✅ **复诊管理智能体**：支持创建、查询、更新预约
- ✅ **智能路由系统**：根据用户意图自动路由到对应智能体
- ✅ **数据库支持**：PostgreSQL 数据库，支持异步操作
- ✅ **配置驱动**：通过 YAML 配置文件管理智能体和工具

## 技术栈

- **Python**: 3.10+
- **FastAPI**: Web 框架
- **LangGraph**: 多智能体框架
- **LangChain**: LLM 调用和工具支持
- **PostgreSQL**: 数据库
- **SQLAlchemy**: ORM
- **Pydantic**: 数据验证

## 项目结构

```
gd25-biz-agent-python_cursor/
├── app/                    # 应用层
│   ├── main.py            # FastAPI 应用入口
│   ├── api/               # API 路由
│   ├── core/              # 核心配置
│   ├── schemas/           # 数据模型
│   └── middleware/        # 中间件
├── domain/                # 领域层
│   ├── router/           # 路由系统
│   ├── agents/           # 智能体
│   └── tools/            # 业务工具
├── infrastructure/        # 基础设施层
│   ├── database/         # 数据库
│   ├── llm/              # LLM 客户端
│   └── external/         # 外部服务集成
├── config/               # 配置文件
│   ├── agents.yaml       # 智能体配置
│   └── prompts/         # 提示词文件
├── alembic/              # 数据库迁移
└── tests/                # 测试
```

## 快速开始

### 1. 环境准备

确保已安装：
- Python 3.10+
- PostgreSQL 14+
- Conda（推荐）

### 2. 安装依赖

```bash
# 创建 conda 环境（推荐）
conda create -n langgraphflow python=3.10
conda activate langgraphflow

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置数据库和 LLM API 密钥：

```env
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=langgraphflow

# LLM 配置
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### 4. 初始化数据库

```bash
# 运行数据库迁移
alembic upgrade head
```

### 5. 启动应用

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 测试接口

访问健康检查接口：
```bash
curl http://localhost:8000/health
```

## API 文档

启动应用后，访问以下地址查看 API 文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 聊天接口

**POST** `/api/v1/chat`

请求示例：
```json
{
  "message": "我想记录血压，收缩压120，舒张压80",
  "session_id": "session_123",
  "user_id": "user_456"
}
```

响应示例：
```json
{
  "response": "成功记录血压：收缩压 120 mmHg，舒张压 80 mmHg",
  "session_id": "session_123",
  "intent": "blood_pressure",
  "agent": "blood_pressure_agent"
}
```

## 开发计划

### Milestone 1: MVP 版本 ✅（基础骨架已完成）

- [x] 基础架构搭建
- [x] 血压记录智能体
- [x] 复诊管理智能体
- [x] 基础路由功能

### Milestone 2: 功能增强（待开始）

- [ ] 诊断智能体系统
- [ ] RAG 检索功能
- [ ] 路由逻辑扩展

### Milestone 3: 生产就绪（待开始）

- [ ] 安全审核
- [ ] 性能优化
- [ ] 完善测试和文档

详细开发计划请参考：[开发计划与里程碑.md](./doc/设计V2.0/开发计划与里程碑.md)

## 开发规范

- 代码格式：使用 `black` 格式化
- 代码检查：使用 `ruff` 检查
- 类型检查：使用 `mypy` 检查
- 测试：使用 `pytest` 运行测试

## 注意事项

1. **工具中的数据库会话**：当前工具实现中，数据库会话需要从 LangGraph 的 `RunnableConfig` 中获取。这部分需要在后续开发中完善。

2. **意图识别**：当前使用简化的关键词匹配，后续可以使用 LLM 进行更智能的意图识别。

3. **时间解析**：预约时间解析目前只支持 ISO 格式，后续可以增强支持自然语言时间描述。

## 许可证

详见 [LICENSE](./LICENSE) 文件。
