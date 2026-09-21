#!/usr/bin/env bash
# TCR 自动登录：读取本机 ~/.config/unidt/tcr.env（或已 export 的 TCR_*）。
# 供 push-*.sh source，不要单独执行。
#
# 连接方式与腾讯云控制台导出的「登录指令」相同：
#   docker login <registry> --username '<服务级账号>' --password-stdin
# 例：用户名 tcr$suanfa（服务级账号），仓库 bj-unidt.tencentcloudcr.com

_TCR_DEFAULT_ENV_FILE="${HOME}/.config/unidt/tcr.env"
_TCR_DEFAULT_REGISTRY="bj-unidt.tencentcloudcr.com"
_TCR_DOCKER_DESKTOP_BIN="/Applications/开发/Docker.app/Contents/Resources/bin"

# 保证 docker 与 docker-credential-desktop 同在 PATH（仅写绝对路径调 docker 会丢 helper）
_tcr_ensure_docker_path() {
  if [[ -x "$_TCR_DOCKER_DESKTOP_BIN/docker" ]]; then
    case ":$PATH:" in
      *":$_TCR_DOCKER_DESKTOP_BIN:"*) ;;
      *) export PATH="$_TCR_DOCKER_DESKTOP_BIN:$PATH" ;;
    esac
  fi
}

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

  _tcr_ensure_docker_path
  _tcr_load_env
  env_file="${TCR_ENV_FILE:-$_TCR_DEFAULT_ENV_FILE}"
  host="${host:-${TCR_REGISTRY:-$_TCR_DEFAULT_REGISTRY}}"
  user="${TCR_USERNAME:-}"
  pass="${TCR_PASSWORD:-}"

  if [[ -z "$user" || -z "$pass" ]]; then
    echo "ERROR: 未找到 TCR 账号/口令。" >&2
    echo "请在 ${env_file} 写入 TCR_USERNAME / TCR_PASSWORD，或先 export 这两个变量。" >&2
    echo "参考: huaYuanTestDeploy/README.md" >&2
    echo "服务级账号用户名常含 \$（如 tcr\$suanfa），env 文件里必须用单引号包裹。" >&2
    return 1
  fi

  # 常见误配：export TCR_USERNAME=tcr$suanfa（无引号）→ source 后变成 tcr
  if [[ "$user" == "tcr" ]]; then
    echo "ERROR: TCR_USERNAME 看起来被 bash 吃掉了 \$ 后面的部分（当前值: '$user'）。" >&2
    echo "请在 ${env_file} 写成: export TCR_USERNAME='tcr\$suanfa'" >&2
    return 1
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: 找不到 docker，请先安装/启动 Docker Desktop" >&2
    return 1
  fi

  echo "==> 自动登录 TCR: $host (user=$user)"
  # 密码走 stdin，避免出现在 ps 参数里；与控制台 CSV「登录指令」等价
  printf '%s' "$pass" | docker login "$host" --username "$user" --password-stdin
}
