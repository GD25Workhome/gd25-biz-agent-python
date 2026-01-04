# 01_Agent - 动态流程系统 MVP

## 项目说明

本项目是V7.2版本动态流程系统的最小可行版本（MVP），旨在验证核心架构设计，实现最基本的流程配置化和动态加载能力。

## 项目结构

```
01_Agent/
├── .env                          # 环境变量配置
├── README.md                     # 项目说明
├── requirements.txt              # Python依赖
├── backend/                      # 后端代码
│   ├── main.py                   # FastAPI应用入口
│   ├── app/                      # 应用层
│   ├── domain/                   # 领域层
│   └── infrastructure/            # 基础设施层
├── frontend/                     # 前端代码（简化版）
└── config/                       # 配置文件
```

## 开发阶段

### 第一阶段：基础架构搭建（已完成）

- [x] 创建项目目录结构
- [x] 配置环境变量（.env文件）
- [x] 创建requirements.txt（依赖管理）
- [x] 实现配置管理模块（app/config.py）
- [x] 实现模型供应商管理模块（infrastructure/llm/providers/）
  - [x] 实现ProviderRegistry（供应商注册表）
  - [x] 实现ProviderManager（供应商管理器）
  - [x] 创建模型供应商配置文件（config/model_providers.yaml）
- [x] 实现LLM客户端（infrastructure/llm/client.py）

## 技术栈

- **Web框架**：FastAPI
- **图执行引擎**：LangGraph
- **LLM框架**：LangChain
- **配置管理**：PyYAML
- **类型检查**：Pydantic

## 环境要求

- Python 3.10+
- 虚拟环境（推荐使用conda）

## 快速开始

1. 安装依赖：
```bash
cd 01_Agent
pip install -r requirements.txt
```

2. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的配置（至少配置一个模型供应商的API密钥）
```

3. 验证系统初始化：
```bash
cd backend
python init_system.py
```

4. 运行测试：
```bash
# 安装pytest（如果未安装）
pip install pytest

# 运行测试
pytest cursor_test/test_flow_system.py -v
```

5. 启动应用：
```bash
# 方式1：使用 run.py（推荐，可从任意目录运行）
cd 01_Agent
python run.py
# 或者从任意目录：
python /path/to/01_Agent/run.py

# 方式2：直接运行 main.py（可从任意目录运行）
python 01_Agent/backend/main.py
# 或者使用绝对路径：
python /path/to/01_Agent/backend/main.py

# 方式3：使用 uvicorn 直接运行（需要在项目根目录）
cd 01_Agent
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

应用启动后，访问：
- API文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- 前端界面：http://localhost:8000/static/index.html

**注意**：如果应用运行在不同端口，请相应调整URL中的端口号（例如：http://localhost:9001/static/index.html）

## 已实现的功能

### 1. 配置管理（backend/app/config.py）
- 使用 Pydantic Settings 管理配置
- 支持从 .env 文件读取环境变量
- 自动查找项目根目录

### 2. 模型供应商管理（backend/infrastructure/llm/providers/）
- **ProviderRegistry**：供应商注册表，用于缓存供应商配置
- **ProviderManager**：供应商管理器，负责加载和管理供应商配置
- 支持从 YAML 配置文件加载供应商信息
- 支持环境变量替换（如 `${DOUBAO_API_KEY}`）

### 3. LLM客户端（backend/infrastructure/llm/client.py）
- 支持多厂商、多模型的 LLM 客户端创建
- 根据供应商配置自动设置 API 密钥和 Base URL
- 兼容所有 OpenAI API 格式的供应商

## 配置文件说明

### config/model_providers.yaml
模型供应商配置文件，定义所有可用的模型供应商及其配置信息。

示例：
```yaml
providers:
  - provider: "doubao"
    api_key: "${DOUBAO_API_KEY}"  # 从环境变量读取
    base_url: "https://ark.cn-beijing.volces.com/api/v3"
```

### .env
环境变量配置文件，包含各模型供应商的 API 密钥。

示例：
```
DOUBAO_API_KEY=your_api_key_here
```

