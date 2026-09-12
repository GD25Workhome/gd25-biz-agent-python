# 华院最小后端镜像（路线 B）
# 构建：docker build -t unidt-exhibition-opportunity-py-agent:latest .
# 运行：docker run --rm -p 8000:8000 \
#   -e ENABLE_DATABASE=false \
#   -e LANGFUSE_ENABLED=false \
#   -e DOUBAO_API_KEY=xxx \
#   -e ANY_SEARCH_API_KEY=xxx \
#   -e BO_CHA_APIKEY=xxx \
#   unidt-exhibition-opportunity-py-agent:latest
#
# 基础镜像默认走 DaoCloud（国内直连 Docker Hub 常超时）；可覆盖：
#   docker build --build-arg BASE_REGISTRY=docker.io/library/ ...

ARG BASE_REGISTRY=docker.m.daocloud.io/library/

FROM ${BASE_REGISTRY}python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENABLE_DATABASE=false \
    LANGFUSE_ENABLED=false \
    PROMPT_SOURCE_MODE=local

# 系统依赖：尽量精简；httpx/ssl 用镜像自带证书
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-huayuan.txt .
RUN pip install --no-cache-dir -r requirements-huayuan.txt

# 仅拷贝运行期需要的后端与配置
COPY backend/ backend/
COPY config/model_providers.yaml config/model_providers.yaml
COPY config/flow_loader.yaml config/flow_loader.yaml
COPY config/flows/huayuan_simple_agent/ config/flows/huayuan_simple_agent/
COPY config/flows/huayuan_react_agent/ config/flows/huayuan_react_agent/
COPY config/flows/huayuan_radar_event_agent/ config/flows/huayuan_radar_event_agent/

# 删除镜像内仍存在但不需要的重型/医疗模块，防止误 import
RUN find backend -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf \
      backend/pipeline \
      backend/domain/batch \
      backend/domain/autogen \
      backend/domain/planning \
      backend/domain/embeddings \
      backend/infrastructure/database \
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
         -delete

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
