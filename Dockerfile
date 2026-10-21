# 华院规则二最小后端镜像（只提供 /api/v1/huayuan/radar-event-score）
#
# 构建：docker build -t unidt-exhibition-opportunity-py-agent:latest .
# 运行：docker run --rm -p 8000:8000 \
#   -e HUAYUAN_API_KEY=xxx \
#   -e DEEPSEEK_SEARCH_KEY=xxx \
#   -e EXHIBITION_MYSQL_HOST=xxx \
#   -e EXHIBITION_MYSQL_USER=xxx \
#   -e EXHIBITION_MYSQL_PASSWORD=xxx \
#   -e EXHIBITION_MYSQL_DB=unidt_exhibition \
#   -e RADAR_SCORE_WORKER_IN_APP=true \
#   unidt-exhibition-opportunity-py-agent:latest
#
# 密钥不要 COPY 进镜像；.dockerignore 已排除 .env。
#
# 基础镜像默认走 DaoCloud（国内直连 Docker Hub 常超时）；可覆盖：
#   docker build --build-arg BASE_REGISTRY=docker.io/library/ ...
# pip 默认清华源；可覆盖：
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
    LANGFUSE_ENABLED=false

# 非 root 运行；先建用户，后续 COPY 直接用 --chown，避免 chown -R 产生 overlay 复制层
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /app \
       --shell /usr/sbin/nologin app

COPY --chown=app:app requirements-huayuan.txt .
RUN pip install --no-cache-dir --default-timeout=120 \
      -i "${PIP_INDEX_URL}" \
      --trusted-host "${PIP_TRUSTED_HOST}" \
      -r requirements-huayuan.txt

# 运行期 pip 检查也不要在 /app 下建缓存
ENV PIP_NO_CACHE_DIR=1

# 只 COPY 规则二运行闭包
COPY --chown=app:app backend/ backend/
COPY --chown=app:app config/ config/
COPY --chown=app:app radar_score/ radar_score/

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
