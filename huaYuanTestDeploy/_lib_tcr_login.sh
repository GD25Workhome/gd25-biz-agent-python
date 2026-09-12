#!/usr/bin/env bash
# TCR 自动登录：读取本机 ~/.config/unidt/tcr.env（或已 export 的 TCR_*）。
# 供 push-*.sh source，不要单独执行。

_TCR_DEFAULT_ENV_FILE="${HOME}/.config/unidt/tcr.env"
_TCR_DEFAULT_REGISTRY="bj-unidt.tencentcloudcr.com"

# 加载本机 TCR 环境变量；文件不存在时不报错，留给 _tcr_auto_login 检查。
_tcr_load_env() {
  local env_file="${TCR_ENV_FILE:-$_TCR_DEFAULT_ENV_FILE}"
  if [[ -f "$env_file" ]]; then
    # shellcheck disable=SC1090
    source "$env_file"
  fi
}

# 使用 TCR_USERNAME / TCR_PASSWORD 登录。可选参数：registry host。
_tcr_auto_login() {
  local host="${1:-}"
  local user pass env_file

  _tcr_load_env
  env_file="${TCR_ENV_FILE:-$_TCR_DEFAULT_ENV_FILE}"
  host="${host:-${TCR_REGISTRY:-$_TCR_DEFAULT_REGISTRY}}"
  user="${TCR_USERNAME:-}"
  pass="${TCR_PASSWORD:-}"

  if [[ -z "$user" || -z "$pass" ]]; then
    echo "ERROR: 未找到 TCR 账号/口令。" >&2
    echo "请在 ${env_file} 写入 TCR_USERNAME / TCR_PASSWORD，或先 export 这两个变量。" >&2
    echo "参考: huaYuanTestDeploy/README.md" >&2
    return 1
  fi

  echo "==> 自动登录 TCR: $host (user=$user)"
  # 密码走 stdin，避免出现在 ps 参数里
  printf '%s' "$pass" | docker login "$host" --username "$user" --password-stdin
}
