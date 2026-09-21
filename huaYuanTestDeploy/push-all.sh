#!/usr/bin/env bash
# 先 Agent API、再采集 Worker，一次推完（共用同一个 tag）
#
# 用法：
#   ./huaYuanTestDeploy/push-all.sh
#   ./huaYuanTestDeploy/push-all.sh v1-260911
#   BUILD_MAC=1 ./huaYuanTestDeploy/push-all.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TAG="${1:-$(date +%Y%m%d-%H%M%S)}"

"$SCRIPT_DIR/push-huayuan-agent.sh" "$TAG"
"$SCRIPT_DIR/push-radar-crawl.sh" "$TAG"
