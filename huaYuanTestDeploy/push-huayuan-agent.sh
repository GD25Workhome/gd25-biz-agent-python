#!/usr/bin/env bash
# 华院 Agent API — 一键构建并推送到公司 TCR（与 radar_crawl 脚本相互独立）
#
# 用法：
#   ./huaYuanTestDeploy/push-huayuan-agent.sh              # tag = YYYYMMDD-HHMMSS
#   ./huaYuanTestDeploy/push-huayuan-agent.sh v1-260911    # 自定义 tag
#   PUSH=0 ./huaYuanTestDeploy/push-huayuan-agent.sh       # 只构建不推送
#   SKIP_LOGIN=1 ./huaYuanTestDeploy/push-huayuan-agent.sh # 跳过自动登录
#
# 推送前会读取 ~/.config/unidt/tcr.env 自动 docker login。

set -euo pipefail

PROJ="${PROJ:-unidt-repo}"
IMAGE_NAME="${IMAGE_NAME:-unidt-exhibition-opportunity-py-agent}"
TAG="${1:-$(date +%Y%m%d-%H%M%S)}"
PUSH="${PUSH:-1}"
SKIP_LOGIN="${SKIP_LOGIN:-0}"
PLATFORM="${PLATFORM:-linux/amd64}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKERFILE="$ROOT_DIR/Dockerfile"

# 本机若 /usr/local/bin/docker 异常，优先用「开发」目录下的 Docker.app
if [[ -x "/Applications/开发/Docker.app/Contents/Resources/bin/docker" ]]; then
  export PATH="/Applications/开发/Docker.app/Contents/Resources/bin:$PATH"
fi

# shellcheck source=./_lib_tcr_login.sh
source "$SCRIPT_DIR/_lib_tcr_login.sh"
_tcr_load_env
REG="${REG:-${TCR_REGISTRY:-bj-unidt.tencentcloudcr.com}}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: 找不到 docker，请先安装/启动 Docker Desktop" >&2
  exit 1
fi

if [[ ! -f "$DOCKERFILE" ]]; then
  echo "ERROR: 找不到 Dockerfile: $DOCKERFILE" >&2
  exit 1
fi

FULL_REF="$REG/$PROJ/$IMAGE_NAME:$TAG"
LATEST_REF="$REG/$PROJ/$IMAGE_NAME:latest"

echo "==> 项目:     华院 Agent API"
echo "==> 仓库根:   $ROOT_DIR"
echo "==> Dockerfile: $DOCKERFILE"
echo "==> platform: $PLATFORM"
echo "==> 镜像:     $FULL_REF"
echo "==> 推送:     $PUSH"
echo

if [[ "$PUSH" == "1" && "$SKIP_LOGIN" != "1" ]]; then
  _tcr_auto_login "$REG"
  echo
fi

echo "==> docker build"
docker build --platform "$PLATFORM" \
  -f "$DOCKERFILE" \
  -t "$IMAGE_NAME:local" \
  -t "$FULL_REF" \
  -t "$LATEST_REF" \
  "$ROOT_DIR"

if [[ "$PUSH" == "1" ]]; then
  echo "==> docker push"
  docker push "$FULL_REF"
  docker push "$LATEST_REF"
fi

echo
echo "Done. 镜像地址（填 K8s / 公司部署页）："
echo "  $FULL_REF"
[[ "$PUSH" == "1" ]] && echo "  $LATEST_REF"
echo
echo "启动命令示例: uvicorn backend.main:app --host 0.0.0.0 --port 8000"
echo "容器端口: 8000"
