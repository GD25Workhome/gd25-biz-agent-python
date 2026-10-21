# 华院规则二评分服务 — 一键推包

只打一个镜像：**规则二评分 API + event worker**。  
提供 `POST /api/v1/huayuan/radar-event-score` 与 `GET /health`；不含画像、chat、新闻抓取、知识库 / Milvus。

推送前会自动读本机 `~/.config/unidt/tcr.env` 做 `docker login`。

| 脚本 | 打什么 | 默认镜像 |
|------|--------|----------|
| `push-huayuan-agent.sh` | 规则二评分 API（`Dockerfile`） | `bj-unidt.tencentcloudcr.com/unidt-repo/unidt-exhibition-opportunity-py-agent:<tag>` |

旧 `push-radar-crawl.sh` / `push-all.sh` 已删除；巨潮 / 抓取不再由本仓交付。

发布环境变量见 [`环境变量.md`](./环境变量.md)（可整段贴到发布页）。**密钥不要提交进 git。**

## 用法

```bash
# 华院规则二评分服务
./huaYuanTestDeploy/push-huayuan-agent.sh
./huaYuanTestDeploy/push-huayuan-agent.sh v1-261020

# 只构建、不推送（也不登录）
PUSH=0 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 已登录过、想跳过自动登录
SKIP_LOGIN=1 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 跳过镜像内 import / pip check 烟测（不推荐）
SMOKE=0 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 推送后仍保留本机全部历史 tag（默认会清）
CLEAN_OLD_IMAGES=0 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 额外再留 2 个历史 tag，并压缩 BuildKit 缓存
KEEP_OLD_TAGS=2 PRUNE_BUILD_CACHE=1 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 额外构建本机可跑的 Mac 镜像（Apple Silicon 为 linux/arm64，tag=:local，不推 TCR）
BUILD_MAC=1 ./huaYuanTestDeploy/push-huayuan-agent.sh
```

未传参数时 tag 默认为时间戳 `YYYYMMDD-HHMMSS`（同天多次打包互不覆盖）。同时会打一份 `:latest`。

**烟测**：构建后会在镜像内执行 `import backend.main, radar_score` 与 `pip check`；镜像体积超过 `SIZE_WARN_MB`（默认 500MB）会告警。

推送成功后会**定向清理本机 Docker 历史镜像**：只删当前这个镜像名下的旧时间戳 tag，保留 `:latest` / 本次 tag（`BUILD_MAC=1` 时才保留 `:local`）。不会 `docker system prune`，以免误删无关镜像。`PUSH=0` 只构建不推送时不清理。磁盘仍紧时再开 `PRUNE_BUILD_CACHE=1`。

## 认证（本机环境变量，不要进仓库）

```bash
docker login bj-unidt.tencentcloudcr.com --username '<服务级账号>' --password-stdin
```

推荐使用**服务级账号**（CSV 里「服务级账号名称」如 `tcr$suanfa`），不要用个人 UIN + 临时 JWT。

口令放在本机文件 `~/.config/unidt/tcr.env`（权限 `600`），与 exhibition 仓库共用同一份，**不要**写进本仓库。内容示例：

```bash
export TCR_REGISTRY=bj-unidt.tencentcloudcr.com
# 用户名含 $，必须单引号，否则 source 时会被 bash 展开
export TCR_USERNAME='tcr$suanfa'
export TCR_PASSWORD='<登录密码>'
```

脚本会 `source` 该文件，并用 `--password-stdin` 登录。可用 `TCR_ENV_FILE=/其它路径` 覆盖文件位置；也可事先 `export TCR_USERNAME` / `TCR_PASSWORD`。

## 发布约定

| 服务 | 镜像名 | 容器端口 | K8s 服务名 | 说明 |
|------|--------|----------|------------|------|
| 规则二评分 | `unidt-exhibition-opportunity-py-agent` | 8000 | `exhibition-opportunity-agent` | HTTP + event worker |

展厅 Java 通过 `AGENT_BASE_URL=http://exhibition-opportunity-agent:8000` 调本服务。

必配密钥：`HUAYUAN_API_KEY`、`DEEPSEEK_SEARCH_KEY`、`EXHIBITION_MYSQL_*`。  
`RADAR_SCORE_WORKER_IN_APP=true` 时 API 进程内同时跑 event worker；也可单独运行 `python -m radar_score`。

## 常见问题

1. **Docker Hub 超时**：Dockerfile 已默认 DaoCloud 前缀 `docker.m.daocloud.io/library/`。  
   **PyPI 超时**（`files.pythonhosted.org` / `orjson`）：pip 已默认清华源；仍失败可换 `--build-arg PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple`。
2. **本机 `docker` 命令异常**：脚本会优先用 `/Applications/开发/Docker.app/.../docker`（并保证 `docker-credential-desktop` 在 PATH）。
3. **`unauthorized`**：多半是凭据过期或账号类型不对；用控制台导出的服务级账号 CSV 更新 `tcr.env` 后重试。
4. **用户名变成 `tcr`**：`tcr$suanfa` 未加单引号，`$suanfa` 被 bash 吃掉了。
5. **本机 Docker 磁盘变满**：时间戳 tag 默认互不覆盖，旧镜像会留在本机。推送成功后脚本会定向删除本仓库历史 tag；若仍紧，用 `PRUNE_BUILD_CACHE=1` 压缩构建缓存，不要手动 `docker system prune -a`。
6. **评分调不通**：确认 `HUAYUAN_API_KEY`、`DEEPSEEK_SEARCH_KEY`、`EXHIBITION_MYSQL_*` 已注入；见 [`环境变量.md`](./环境变量.md)。
