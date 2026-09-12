# 华院测试环境一键推包

两个推包脚本**互不依赖**；推送前会自动读本机 `~/.config/unidt/tcr.env` 做 `docker login`。

| 脚本 | 打什么 | 默认镜像 |
|------|--------|----------|
| `push-huayuan-agent.sh` | 华院 API（`Dockerfile`） | `bj-unidt.tencentcloudcr.com/unidt-repo/unidt-exhibition-opportunity-py-agent:<tag>` |
| `push-radar-crawl.sh` | 采集 Worker（`Dockerfile.radar-crawl`） | `bj-unidt.tencentcloudcr.com/unidt-repo/unidt-exhibition-opportunity-py-crawl:<tag>` |

## 用法

```bash
# 华院 API（自动登录 + build + push）
./huaYuanTestDeploy/push-huayuan-agent.sh
./huaYuanTestDeploy/push-huayuan-agent.sh v1-260911

# 采集 Worker
./huaYuanTestDeploy/push-radar-crawl.sh
./huaYuanTestDeploy/push-radar-crawl.sh v1-260911

# 只构建、不推送（也不登录）
PUSH=0 ./huaYuanTestDeploy/push-huayuan-agent.sh

# 已登录过、想跳过自动登录
SKIP_LOGIN=1 ./huaYuanTestDeploy/push-radar-crawl.sh
```

未传参数时 tag 默认为时间戳 `YYYYMMDD-HHMMSS`（同天多次打包互不覆盖）。同时会打一份 `:latest`。

## 认证（本机环境变量，不要进仓库）

口令放在本机文件 `~/.config/unidt/tcr.env`（权限 `600`），与 exhibition 仓库共用同一份，**不要**写进本仓库。内容示例：

```bash
export TCR_REGISTRY=bj-unidt.tencentcloudcr.com
export TCR_USERNAME='<账号>'
export TCR_PASSWORD='<口令>'
```

脚本会 `source` 该文件，并用 `--password-stdin` 登录。可用 `TCR_ENV_FILE=/其它路径` 覆盖文件位置；也可事先 `export TCR_USERNAME` / `TCR_PASSWORD`。

```bash
mkdir -p ~/.config/unidt
chmod 700 ~/.config/unidt
chmod 600 ~/.config/unidt/tcr.env
```

## 常见问题

构建卡在 `FROM python:3.11-slim` / `auth.docker.io` 超时：国内访问 Docker Hub 不通。  
两个 Dockerfile 已默认用 DaoCloud 前缀 `docker.m.daocloud.io/library/`（与 exhibition 一致）。重新跑推包脚本即可。

# 发布后的地址说明
- agent的k8s服务name是 `exhibition-opportunity-agent`
