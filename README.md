# 华院规则二：展厅项目需求评分服务

基于 FastAPI + LangGraph 的**规则二评分服务**。只保留：

- `POST /api/v1/huayuan/radar-event-score`：展厅项目需求评分
- `radar_score` **event worker**：认领 `radar_event_job` → 算分 → 自检 → 直写 `radar_event` / `radar_event_evidence` / 任务收口
- 规则二 v3 flow：`react → rule_gate → auditor`
- 检索工具：DeepSeek Search / Fetch + 区域字典

画像、chat、新闻 URL 抓取、Claude Agent SDK、`radar_kb` / `radar_crawl` / `company_news_crawl`、Milvus / AnySearch / 博查、非华院 Agent 均已删除。

## 目录

```text
backend/
  main.py                         # FastAPI 入口（只挂规则二）
  app/api/routes/huayuan_radar_event.py
  app/api/schemas/huayuan_radar_event.py
  domain/flows/                   # agent / function 两类节点
  domain/tools/                   # deepseek + region only
  infrastructure/                 # LLM provider / prompts / langfuse
radar_score/                      # event-only 调度、算分、自检、落库
config/
  flow_loader.yaml                # 只 preload v3
  model_providers.yaml            # 只 huayuan
  flows/huayuan_radar_event_agent_v3/
Dockerfile
requirements-huayuan.txt
huaYuanTestDeploy/push-huayuan-agent.sh
```

## 本地运行

```bash
conda activate py311_GD25_base
pip install -r requirements-huayuan.txt

cp .env.example .env
# 填 HUAYUAN_API_KEY / DEEPSEEK_SEARCH_KEY / EXHIBITION_MYSQL_*

# HTTP API
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 另起 event worker（或在 .env 设 RADAR_SCORE_WORKER_IN_APP=true）
python -m radar_score
```

健康检查：`GET /health`。

## 打包 / 发布

```bash
# 只构建
PUSH=0 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 构建并推送 TCR
./huaYuanTestDeploy/push-huayuan-agent.sh
```

构建后在镜像内执行 `import backend.main, radar_score` + `pip check`，并打印镜像体积；目标未压缩 < 500MB。

## 依赖

`requirements-huayuan.txt` 只装规则二直接依赖：FastAPI / uvicorn / LangGraph / LangChain / langchain-openai / pydantic / pydantic-settings / httpx / pyyaml / simpleeval / pymysql / python-dotenv。

不再安装：`claude-agent-sdk`、`pymilvus`、`pandas`、`numpy`、`trafilatura`、`curl_cffi`、`selectolax`、`lxml`、`beautifulsoup4`。

## 当前设计文档

- `华院Agent设计/00-当前技术设计-总览.md`
- `华院Agent设计/02-技术设计/01-HTTP契约与Agent流程.md`
- `华院Agent设计/02-技术设计/02-评分、自检与落库规则.md`
- `华院Agent设计/02-技术设计/03-Worker调度与数据模型.md`
- `华院Agent设计/02-技术设计/04-配置、部署与验证.md`
- `华院Agent设计/03-决策记录/`（4 篇当前决策）
- `cairn/华院-展厅需求终评与提示词.md`
- `cairn/华院-雷达事件落库与展示.md`
- `cairn/华院-部署与依赖切分.md`

## 发布环境变量

见 `huaYuanTestDeploy/环境变量.md`。必配：`HUAYUAN_API_KEY`、`DEEPSEEK_SEARCH_KEY`、`EXHIBITION_MYSQL_*`。
