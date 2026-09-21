# 华院测试环境一键推包（Agent + 采集）

两个推包脚本**互不依赖**；推送前会自动读本机 `~/.config/unidt/tcr.env` 做 `docker login`。

| 脚本 | 打什么 | 默认镜像 |
|------|--------|----------|
| `push-huayuan-agent.sh` | 华院 API（`Dockerfile`） | `bj-unidt.tencentcloudcr.com/unidt-repo/unidt-exhibition-opportunity-py-agent:<tag>` |
| `push-radar-crawl.sh` | 采集 Worker（`Dockerfile.radar-crawl`） | `bj-unidt.tencentcloudcr.com/unidt-repo/unidt-exhibition-opportunity-py-crawl:<tag>` |
| `push-all.sh` | 上面两个按同一 tag 顺序执行 | 同上 |

发布时要配的环境变量见 [`环境变量.md`](./环境变量.md)。**密钥不进镜像**，由 K8s Secret 注入。

## 用法

```bash
# 华院 API
./huaYuanTestDeploy/push-huayuan-agent.sh
./huaYuanTestDeploy/push-huayuan-agent.sh v1-260911

# 采集 Worker
./huaYuanTestDeploy/push-radar-crawl.sh
./huaYuanTestDeploy/push-radar-crawl.sh v1-260911

# 两个一起（同一 tag）
./huaYuanTestDeploy/push-all.sh
./huaYuanTestDeploy/push-all.sh v1-260911

# 只构建、不推送（也不登录）
PUSH=0 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 已登录过、想跳过自动登录
SKIP_LOGIN=1 ./huaYuanTestDeploy/push-radar-crawl.sh

# 推送后仍保留本机全部历史 tag（默认会清）
CLEAN_OLD_IMAGES=0 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 额外再留 2 个历史 tag，并压缩 BuildKit 缓存
KEEP_OLD_TAGS=2 PRUNE_BUILD_CACHE=1 ./huaYuanTestDeploy/push-radar-crawl.sh

# 额外构建本机可跑的 Mac 镜像（Apple Silicon 为 linux/arm64，tag=:local，不推 TCR）
BUILD_MAC=1 ./huaYuanTestDeploy/push-huayuan-agent.sh
BUILD_MAC=1 ./huaYuanTestDeploy/push-all.sh
```

未传参数时 tag 默认为时间戳 `YYYYMMDD-HHMMSS`（同天多次打包互不覆盖）。同时会打一份 `:latest`。

**镜像平台：** 默认只构建远程 K8s 用的 `linux/amd64`，并打 TCR 的 `<tag>` / `:latest`。不会再打 `:local`，也不会为 Mac 再构建一份 `linux/arm64`。本机要跑容器时再加 `BUILD_MAC=1`。

推送成功后会**定向清理本机 Docker 历史镜像**：只删当前这个镜像名下的旧时间戳 tag，保留 `:latest` / 本次 tag（`BUILD_MAC=1` 时才保留 `:local`）。不会 `docker system prune`，以免误删无关镜像。`PUSH=0` 只构建不推送时不清理。磁盘仍紧时再开 `PRUNE_BUILD_CACHE=1`。

## 认证（本机环境变量，不要进仓库）

连接方式与腾讯云 TCR 控制台导出的 CSV「登录指令」相同，都是：

```bash
docker login bj-unidt.tencentcloudcr.com --username '<服务级账号>' --password-stdin
```

推荐使用**服务级账号**（CSV 里「服务级账号名称」如 `tcr$suanfa`），不要用个人 UIN + 临时 JWT（易过期，之前 `unauthorized` 多半因此）。

口令放在本机文件 `~/.config/unidt/tcr.env`（权限 `600`），与 exhibition 仓库共用同一份，**不要**写进本仓库。内容示例：

```bash
export TCR_REGISTRY=bj-unidt.tencentcloudcr.com
# 用户名含 $，必须单引号，否则 source 时会被 bash 展开
export TCR_USERNAME='tcr$suanfa'
export TCR_PASSWORD='<登录密码>'
```

脚本会 `source` 该文件，并用 `--password-stdin` 登录。可用 `TCR_ENV_FILE=/其它路径` 覆盖文件位置；也可事先 `export TCR_USERNAME` / `TCR_PASSWORD`。

```bash
mkdir -p ~/.config/unidt
chmod 700 ~/.config/unidt
chmod 600 ~/.config/unidt/tcr.env
```

## 发布约定（与现网一致）

| 服务 | 镜像名 | 容器端口 | K8s 服务名 | 关键环境变量 |
|------|--------|----------|------------|--------------|
| Agent API | `unidt-exhibition-opportunity-py-agent` | 8000 | `exhibition-opportunity-agent` | `HUAYUAN_API_KEY`（必配） |
| 采集 Worker | `unidt-exhibition-opportunity-py-crawl` | 无 HTTP | 按发布页 | `RADAR_DB_*`（不需要模型 key） |

展厅 Java 通过 `AGENT_BASE_URL=http://exhibition-opportunity-agent:8000` 调本服务。

## 常见问题

1. **Docker Hub 超时**：Dockerfile 已默认 DaoCloud 前缀 `docker.m.daocloud.io/library/`。
2. **本机 `docker` 命令异常**：脚本会优先用 `/Applications/开发/Docker.app/.../docker`（并保证 `docker-credential-desktop` 在 PATH）。
3. **`unauthorized`**：多半是凭据过期或账号类型不对；用控制台导出的服务级账号 CSV 更新 `tcr.env` 后重试。
4. **用户名变成 `tcr`**：`tcr$suanfa` 未加单引号，`$suanfa` 被 bash 吃掉了。
5. **本机 Docker 磁盘变满**：时间戳 tag 默认互不覆盖，旧镜像会留在本机。推送成功后脚本会定向删除本仓库历史 tag；若仍紧，用 `PRUNE_BUILD_CACHE=1` 压缩构建缓存，不要手动 `docker system prune -a`。
6. **对话/画像/雷达评分调不通**：现网流程走 `provider: huayuan`，密钥是 `HUAYUAN_API_KEY`，**不是** `DOUBAO_API_KEY` / `OPENAI_API_KEY`。见 [`环境变量.md`](./环境变量.md)。
