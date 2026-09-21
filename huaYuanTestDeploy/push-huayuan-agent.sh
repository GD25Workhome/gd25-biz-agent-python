#!/usr/bin/env bash
# 华院 Agent API — 一键构建并推送到公司 TCR
# （与 push-radar-crawl.sh 相互独立）
#
# 用法：
#   ./huaYuanTestDeploy/push-huayuan-agent.sh              # tag = YYYYMMDD-HHMMSS
#   ./huaYuanTestDeploy/push-huayuan-agent.sh v1-260911    # 自定义 tag
#   PUSH=0 ./huaYuanTestDeploy/push-huayuan-agent.sh       # 只构建不推送
#   SKIP_LOGIN=1 ./huaYuanTestDeploy/push-huayuan-agent.sh # 跳过自动登录
#   CLEAN_OLD_IMAGES=0 ./huaYuanTestDeploy/push-huayuan-agent.sh  # 推送后不删本机历史 tag
#   BUILD_MAC=1 ./huaYuanTestDeploy/push-huayuan-agent.sh         # 额外打本机 :local（Apple Silicon=arm64）
#
# 推送前会读取 ~/.config/unidt/tcr.env 自动 docker login。
# 默认只构建远程 linux/amd64。推送成功后清理历史时间戳 tag，保留 :latest / 当前 tag。
# 密钥不进镜像：HUAYUAN_API_KEY 等由 K8s Secret 注入（见 环境变量.md）。

set -euo pipefail

PROJ="${PROJ:-unidt-repo}"
IMAGE_NAME="${IMAGE_NAME:-unidt-exhibition-opportunity-py-agent}"
TAG="${1:-$(date +%Y%m%d-%H%M%S)}"
PUSH="${PUSH:-1}"
SKIP_LOGIN="${SKIP_LOGIN:-0}"
PLATFORM="${PLATFORM:-linux/amd64}"
BUILD_MAC="${BUILD_MAC:-0}"
CLEAN_OLD_IMAGES="${CLEAN_OLD_IMAGES:-1}"
KEEP_OLD_TAGS="${KEEP_OLD_TAGS:-0}"
PRUNE_BUILD_CACHE="${PRUNE_BUILD_CACHE:-0}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKERFILE="$ROOT_DIR/Dockerfile"

if [[ -x "/Applications/开发/Docker.app/Contents/Resources/bin/docker" ]]; then
  export PATH="/Applications/开发/Docker.app/Contents/Resources/bin:$PATH"
fi

# shellcheck source=./_lib_tcr_login.sh
source "$SCRIPT_DIR/_lib_tcr_login.sh"
# shellcheck source=./_lib_docker_cleanup.sh
source "$SCRIPT_DIR/_lib_docker_cleanup.sh"
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

echo "==> 项目:      华院 Agent API"
echo "==> 仓库根:    $ROOT_DIR"
echo "==> Dockerfile: $DOCKERFILE"
echo "==> platform:  $PLATFORM"
echo "==> 镜像:      $FULL_REF"
echo "==> 推送:      $PUSH"
echo "==> 清理历史镜像: $CLEAN_OLD_IMAGES"
echo "==> 本机 Mac 镜像: $BUILD_MAC"
echo

if [[ "$PUSH" == "1" && "$SKIP_LOGIN" != "1" ]]; then
  _tcr_auto_login "$REG"
  echo
fi

_docker_build_remote "$DOCKERFILE" "$ROOT_DIR" "$FULL_REF" "$LATEST_REF"
_docker_maybe_build_mac "$DOCKERFILE" "$ROOT_DIR" "$IMAGE_NAME"

if [[ "$PUSH" == "1" ]]; then
  echo "==> docker push"
  docker push "$FULL_REF"
  docker push "$LATEST_REF"
  _docker_cleanup_old_images "$IMAGE_NAME" "$TAG" \
    || echo "WARN: 历史镜像清理失败，本次推送本身已成功" >&2
fi

echo
echo "Done. 镜像地址（填 K8s / 公司部署页）："
echo "  $FULL_REF"
[[ "$PUSH" == "1" ]] && echo "  $LATEST_REF"
echo
echo "容器端口: 8000"
echo "启动: 镜像默认 CMD（uvicorn backend.main:app --host 0.0.0.0 --port 8000）"
echo "必配密钥: HUAYUAN_API_KEY（华院 LLM）；新闻抓取另需 ANTHROPIC_AUTH_TOKEN"
echo "完整环境变量见: huaYuanTestDeploy/环境变量.md"
