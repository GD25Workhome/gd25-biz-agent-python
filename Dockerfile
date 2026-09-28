# 华院最小后端镜像（路线 B）
# 构建：docker build -t unidt-exhibition-opportunity-py-agent:latest .
# 运行：docker run --rm -p 8000:8000 \
#   -e ENABLE_DATABASE=false \
#   -e LANGFUSE_ENABLED=false \
#   -e HUAYUAN_API_KEY=xxx \
#   -e ANY_SEARCH_API_KEY=xxx \
#   -e BO_CHA_APIKEY=xxx \
#   unidt-exhibition-opportunity-py-agent:latest
# 华院 flow 走 provider=huayuan，密钥是 HUAYUAN_API_KEY（不要再注入 DOUBAO_API_KEY 当主模型）。
# 密钥不要 COPY 进镜像；.dockerignore 已排除 .env。
#
# 基础镜像默认走 DaoCloud（国内直连 Docker Hub 常超时）；可覆盖：
#   docker build --build-arg BASE_REGISTRY=docker.io/library/ ...
# pip 默认清华源（直连 files.pythonhosted.org 易超时）；可覆盖：
#   docker build --build-arg PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple \
#                --build-arg PIP_TRUSTED_HOST=mirrors.cloud.tencent.com ...

ARG BASE_REGISTRY=docker.m.daocloud.io/library/

FROM ${BASE_REGISTRY}python:3.11-slim AS runtime

# 须在 FROM 后再声明，构建期 pip 才能用到
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENABLE_DATABASE=false \
    LANGFUSE_ENABLED=false \
    PROMPT_SOURCE_MODE=local \
    HOME=/app

# 系统依赖：尽量精简；httpx/ssl 用镜像自带证书
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node.js + claude CLI（新闻 URL 抓取 Agent 的运行时依赖）
# ⚠️ SDK 是 CLI 子进程模型，镜像里必须有 claude 可执行文件（见
#    华院Agent设计/260914-整体重构/02-gd25侧详细设计.md §6.1）。
#   - Node 从 npmmirror 二进制镜像装（deb.nodesource.com 脚本国内构建机常不通）
#   - npm 源同样切 npmmirror；CLI 版本钉在与 SDK 0.2.152 联调验证过的 2.1.272
#   - claude-code 2.1.x 要求 Node >= 22（设计文档早期写的 20 已过时）
#   - HOME=/app：CLI 会把 ~/.claude 配置与缓存写到工作目录
ARG NODE_VERSION=22.20.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl xz-utils \
    && curl -fsSL -o /tmp/node.tar.xz \
       "https://registry.npmmirror.com/-/binary/node/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && npm config set registry https://registry.npmmirror.com \
    && npm install -g @anthropic-ai/claude-code@2.1.272 \
    && claude --version \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-huayuan.txt .
# 清华源 + BuildKit pip 缓存：直连 PyPI 易超时；重试时不必再下 100MB SDK
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 \
      -i "${PIP_INDEX_URL}" \
      --trusted-host "${PIP_TRUSTED_HOST}" \
      -r requirements-huayuan.txt

# 运行期代码与配置（config 整目录拷入，含 flow_rule 占位符）
COPY backend/ backend/
COPY config/ config/
COPY radar_kb/ radar_kb/
COPY radar_score/ radar_score/
COPY radar_crawl/ radar_crawl/
COPY company_news_crawl/ company_news_crawl/

# 删除镜像内仍存在但不需要的重型/医疗模块，防止误 import。
# exhibition MySQL 必留：load_news_document_tool → mysql_connection.py；
# 不能整目录删 database（否则启动即 ModuleNotFoundError）。
# 医疗 PG/SQLAlchemy（connection/base/models/repository）仍裁掉，并改写
# __init__.py，避免 import mysql_connection 时连带拉起 sqlalchemy。
RUN find backend -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf \
      backend/pipeline \
      backend/domain/batch \
      backend/domain/autogen \
      backend/domain/planning \
      backend/domain/embeddings \
      backend/infrastructure/database/models \
      backend/infrastructure/database/repository \
      backend/infrastructure/database/connection.py \
      backend/infrastructure/database/vector_connection.py \
      backend/infrastructure/database/base.py \
      backend/infrastructure/rag \
      backend/infrastructure/llm/autogen_client.py \
      backend/infrastructure/llm/embedding_client.py \
      backend/domain/flows/nodes/autogen_team_creator.py \
      backend/domain/flows/nodes/rag_agent_creator.py \
      backend/domain/flows/nodes/embedding_creator.py \
      backend/domain/flows/nodes/planner_creator.py \
      backend/domain/flows/nodes/plan_executor_creator.py \
      backend/domain/flows/nodes/replanner_creator.py \
      backend/app/api/routes/chat.py \
      backend/app/api/routes/login.py \
      backend/app/api/routes/users.py \
      backend/app/api/routes/blood_pressure.py \
      backend/app/api/routes/flows.py \
      backend/app/api/routes/articles.py \
      backend/app/api/routes/knowledge_base.py \
      backend/app/api/routes/data_cleaning.py \
      backend/app/api/routes/batch_jobs.py \
      backend/domain/tools/blood_pressure_tool.py \
      backend/domain/tools/medication_tool.py \
      backend/domain/tools/symptom_tool.py \
      backend/domain/tools/health_event_tool.py \
    && find backend/domain/flows/implementations -type f -name '*.py' \
         ! -name '__init__.py' \
         ! -name 'radar_evidence_gather_node.py' \
         ! -name 'evidence_gather_portrait_node.py' \
         -delete \
    && printf '%s\n' \
         '"""华院镜像仅保留 exhibition MySQL（mysql_connection）。"""' \
         > backend/infrastructure/database/__init__.py

# Claude CLI：bypassPermissions 禁止 root（本机 Mac 是普通用户所以能跑）。
# IS_SANDBOX 是官方容器豁免；K8s 若仍 runAsUser:0，build_claude_sdk_env 会再写一次。
ENV IS_SANDBOX=1
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /app \
       --shell /usr/sbin/nologin app \
    && mkdir -p /app/.claude_sdk_runtime \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
