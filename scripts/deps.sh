#!/usr/bin/env bash
#
# 一键管理本项目依赖的 Docker 服务：Redis、PostgreSQL、Langfuse
#
# 用法:
#   ./scripts/deps.sh start    # 按顺序启动并等待就绪
#   ./scripts/deps.sh stop     # 停止 Langfuse 栈 + Redis/PG 容器
#   ./scripts/deps.sh status   # 查看依赖服务状态
#   ./scripts/deps.sh restart  # 先 stop 再 start
#
# 配置: 复制 docker/deps.env.example 为 docker/deps.env 并按本机路径修改

set -uo pipefail

# ---------------------------------------------------------------------------
# 路径与默认配置
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPS_ENV="${PROJECT_ROOT}/docker/deps.env"

REDIS_CONTAINER="${REDIS_CONTAINER:-redis_no_pwd}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-postgres_db}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
LANGFUSE_COMPOSE_DIR="${LANGFUSE_COMPOSE_DIR:-}"
REDIS_PORT="${REDIS_PORT:-6379}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
LANGFUSE_PORT="${LANGFUSE_PORT:-3000}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-120}"
# macOS：Docker 未运行时是否自动 open -a Docker（默认开启）
AUTO_START_DOCKER_DESKTOP="${AUTO_START_DOCKER_DESKTOP:-true}"
DOCKER_DESKTOP_TIMEOUT="${DOCKER_DESKTOP_TIMEOUT:-180}"

LANGFUSE_CONTAINERS=(
    langfuse-web
    langfuse-worker
    langfuse-clickhouse
    langfuse-minio
)

# 加载本地配置
if [[ -f "${DEPS_ENV}" ]]; then
    # shellcheck disable=SC1090
    source "${DEPS_ENV}"
fi

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
log_info() {
    echo "[INFO] $*"
}

log_warn() {
    echo "[WARN] $*" >&2
}

log_error() {
    echo "[ERROR] $*" >&2
}

die() {
    log_error "$*"
    exit 1
}

docker_daemon_ready() {
    docker info >/dev/null 2>&1
}

try_start_docker_desktop() {
    # 仅 macOS 支持通过 open 启动 Docker Desktop
    if [[ "$(uname -s)" != "Darwin" ]]; then
        return 1
    fi
    if [[ ! -d "/Applications/Docker.app" ]]; then
        log_warn "未找到 /Applications/Docker.app，无法自动启动"
        return 1
    fi
    log_info "正在启动 Docker Desktop（open -a Docker）..."
    open -a Docker
    return 0
}

wait_for_docker_daemon() {
    local elapsed=0
    log_info "等待 Docker 引擎就绪（最长 ${DOCKER_DESKTOP_TIMEOUT}s）..."
    while (( elapsed < DOCKER_DESKTOP_TIMEOUT )); do
        if docker_daemon_ready; then
            log_info "Docker 引擎已就绪"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        if (( elapsed % 15 == 0 )); then
            log_info "仍在等待 Docker Desktop... (${elapsed}s)"
        fi
    done
    return 1
}

ensure_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        die "未找到 docker 命令，请先安装 Docker Desktop"
    fi
    if docker_daemon_ready; then
        return 0
    fi

    if [[ "${AUTO_START_DOCKER_DESKTOP}" == "true" ]]; then
        try_start_docker_desktop || true
        if wait_for_docker_daemon; then
            return 0
        fi
        die "Docker Desktop 启动超时（${DOCKER_DESKTOP_TIMEOUT}s），请确认应用已正常打开"
    fi

    die "Docker 未运行。可手动打开 Docker Desktop，或在 docker/deps.env 中设置 AUTO_START_DOCKER_DESKTOP=true"
}

container_exists() {
    local name="$1"
    docker inspect "$name" >/dev/null 2>&1
}

container_running() {
    local name="$1"
    [[ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || echo false)" == "true" ]]
}

container_health() {
    local name="$1"
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$name" 2>/dev/null || echo "missing"
}

start_container() {
    local name="$1"
    if ! container_exists "$name"; then
        die "容器 ${name} 不存在，请先用 docker compose 或 docker run 创建"
    fi
    if container_running "$name"; then
        log_info "容器已在运行: ${name}"
        return 0
    fi
    log_info "启动容器: ${name}"
    docker start "$name" >/dev/null
}

wait_for_redis() {
    local elapsed=0
    log_info "等待 Redis 就绪 (${REDIS_CONTAINER})..."
    while (( elapsed < STARTUP_TIMEOUT )); do
        if container_running "${REDIS_CONTAINER}" \
            && docker exec "${REDIS_CONTAINER}" redis-cli ping 2>/dev/null | grep -q PONG; then
            log_info "Redis 已就绪 (localhost:${REDIS_PORT})"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    die "Redis 在 ${STARTUP_TIMEOUT}s 内未就绪"
}

wait_for_postgres() {
    local elapsed=0
    log_info "等待 PostgreSQL 就绪 (${POSTGRES_CONTAINER})..."
    while (( elapsed < STARTUP_TIMEOUT )); do
        if container_running "${POSTGRES_CONTAINER}" \
            && docker exec "${POSTGRES_CONTAINER}" pg_isready -U "${POSTGRES_USER}" >/dev/null 2>&1; then
            log_info "PostgreSQL 已就绪 (localhost:${POSTGRES_PORT})"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    die "PostgreSQL 在 ${STARTUP_TIMEOUT}s 内未就绪"
}

# 在 Langfuse compose 目录执行 docker compose，避免宿主 shell 环境变量污染插值
# （常见：终端已 source 本项目 .env，DATABASE_URL=postgresql+psycopg://... 会覆盖 Langfuse 的 .env）
run_langfuse_compose() {
    local langfuse_env_file="${LANGFUSE_COMPOSE_DIR}/.env"
    (
        cd "${LANGFUSE_COMPOSE_DIR}" || die "无法进入目录: ${LANGFUSE_COMPOSE_DIR}"
        unset DATABASE_URL DIRECT_URL REDIS_CONNECTION_STRING \
            POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB \
            DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME
        if [[ -f "${langfuse_env_file}" ]]; then
            docker compose --env-file "${langfuse_env_file}" "$@"
        else
            log_warn "未找到 ${langfuse_env_file}，将仅使用 compose 默认值"
            docker compose "$@"
        fi
    )
}

start_langfuse() {
    if [[ -z "${LANGFUSE_COMPOSE_DIR}" ]]; then
        die "未配置 LANGFUSE_COMPOSE_DIR，请在 docker/deps.env 中设置 Langfuse compose 目录"
    fi
    if [[ ! -f "${LANGFUSE_COMPOSE_DIR}/docker-compose.yml" ]] \
        && [[ ! -f "${LANGFUSE_COMPOSE_DIR}/docker-compose.yaml" ]]; then
        die "Langfuse compose 目录无效: ${LANGFUSE_COMPOSE_DIR}"
    fi

    log_info "启动 Langfuse 栈: ${LANGFUSE_COMPOSE_DIR}"
    run_langfuse_compose up -d
}

wait_for_langfuse() {
    local elapsed=0
    local url="http://localhost:${LANGFUSE_PORT}/api/public/health"
    log_info "等待 Langfuse 就绪 (${url})..."
    while (( elapsed < STARTUP_TIMEOUT )); do
        if curl -sf "${url}" >/dev/null 2>&1; then
            log_info "Langfuse 已就绪 (http://localhost:${LANGFUSE_PORT})"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    log_warn "Langfuse 健康检查超时，请稍后手动访问 http://localhost:${LANGFUSE_PORT}"
}

stop_container_if_running() {
    local name="$1"
    if container_running "$name"; then
        log_info "停止容器: ${name}"
        docker stop "$name" >/dev/null
    else
        log_info "容器未运行，跳过: ${name}"
    fi
}

stop_langfuse() {
    if [[ -n "${LANGFUSE_COMPOSE_DIR}" ]] \
        && { [[ -f "${LANGFUSE_COMPOSE_DIR}/docker-compose.yml" ]] || [[ -f "${LANGFUSE_COMPOSE_DIR}/docker-compose.yaml" ]]; }; then
        log_info "停止 Langfuse 栈: ${LANGFUSE_COMPOSE_DIR}"
        run_langfuse_compose stop
        return 0
    fi

    log_warn "未找到 Langfuse compose 目录，尝试按容器名停止"
    local name
    for name in "${LANGFUSE_CONTAINERS[@]}"; do
        stop_container_if_running "$name"
    done
}

print_connection_summary() {
    echo
    echo "========== 依赖服务连接信息 =========="
    echo "Redis:      redis://localhost:${REDIS_PORT}"
    echo "PostgreSQL: postgresql://localhost:${POSTGRES_PORT}"
    echo "Langfuse:   http://localhost:${LANGFUSE_PORT}"
    echo "======================================"
    echo
    echo "项目 .env 参考:"
    echo "  DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:${POSTGRES_PORT}/gd25_biz_agent_python?sslmode=disable"
    echo "  LANGFUSE_HOST=http://localhost:${LANGFUSE_PORT}"
    echo
}

print_status_line() {
    local name="$1"
    if ! container_exists "$name"; then
        printf "  %-22s %s\n" "$name" "不存在"
        return
    fi
    local running health port
    running="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || echo false)"
    health="$(container_health "$name")"
    port="$(docker inspect -f '{{range $p, $conf := .NetworkSettings.Ports}}{{if $conf}}{{(index $conf 0).HostPort}} {{end}}{{end}}' "$name" 2>/dev/null | xargs)"
    if [[ "$running" == "true" ]]; then
        printf "  %-22s 运行中 (health=%s, ports=%s)\n" "$name" "$health" "${port:-—}"
    else
        printf "  %-22s 已停止\n" "$name"
    fi
}

# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
cmd_start() {
    ensure_docker
    log_info "========== 启动依赖服务 =========="

    start_container "${REDIS_CONTAINER}"
    start_container "${POSTGRES_CONTAINER}"
    wait_for_redis
    wait_for_postgres

    start_langfuse
    wait_for_langfuse

    log_info "========== 全部依赖已启动 =========="
    print_connection_summary
}

cmd_stop() {
    ensure_docker
    log_info "========== 停止依赖服务 =========="

    stop_langfuse
    stop_container_if_running "${POSTGRES_CONTAINER}"
    stop_container_if_running "${REDIS_CONTAINER}"

    log_info "========== 依赖服务已停止 =========="
}

cmd_status() {
    ensure_docker
    echo "========== 依赖服务状态 =========="
    print_status_line "${REDIS_CONTAINER}"
    print_status_line "${POSTGRES_CONTAINER}"
    local name
    for name in "${LANGFUSE_CONTAINERS[@]}"; do
        print_status_line "$name"
    done
    echo "=================================="

    if container_running "${REDIS_CONTAINER}" \
        && container_running "${POSTGRES_CONTAINER}" \
        && container_running "langfuse-web"; then
        echo
        print_connection_summary
    fi
}

cmd_restart() {
    cmd_stop
    echo
    cmd_start
}

usage() {
    cat <<EOF
用法: $(basename "$0") <start|stop|status|restart>

  start    启动 Redis、PostgreSQL，再 docker compose up Langfuse
  stop     停止 Langfuse 栈及 Redis、PostgreSQL 容器
  status   查看各容器运行与健康状态
  restart  先 stop 再 start

配置文件: docker/deps.env（可从 docker/deps.env.example 复制）
EOF
}

main() {
    local action="${1:-}"
    case "$action" in
        start) cmd_start ;;
        stop) cmd_stop ;;
        status) cmd_status ;;
        restart) cmd_restart ;;
        -h|--help|help|"") usage ;;
        *) die "未知命令: ${action}，使用 --help 查看用法" ;;
    esac
}

main "$@"
