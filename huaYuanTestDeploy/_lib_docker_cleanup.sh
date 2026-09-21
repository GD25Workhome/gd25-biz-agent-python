#!/usr/bin/env bash
# 本机 Docker 历史镜像定向清理：只删本仓库推包脚本打过的旧 tag。
# 供 push-*.sh source，不要单独执行。
#
# 环境变量：
#   BUILD_MAC=0            是否额外构建本机可跑的镜像并打 :local（Apple Silicon 为 linux/arm64）
#   MAC_PLATFORM           BUILD_MAC=1 时的平台，默认按 uname -m 推断
#   CLEAN_OLD_IMAGES=1     推送成功后清理（默认开）
#   KEEP_OLD_TAGS=0        额外保留几个历史 tag（不含 latest/当前 tag；BUILD_MAC=1 时 :local 也会保留）
#   PRUNE_BUILD_CACHE=0    是否压缩 BuildKit 缓存（默认关）
#   KEEP_BUILD_CACHE_SIZE  开启 PRUNE_BUILD_CACHE 时保留的缓存上限，默认 4GB

# 本机 Docker 是否需要 :local（仅 BUILD_MAC=1）
_docker_want_local_tag() {
  [[ "${BUILD_MAC:-0}" == "1" ]]
}

# Apple Silicon -> linux/arm64；Intel Mac -> linux/amd64
_docker_mac_platform() {
  if [[ -n "${MAC_PLATFORM:-}" ]]; then
    printf '%s\n' "$MAC_PLATFORM"
    return 0
  fi
  case "$(uname -m)" in
    arm64|aarch64) printf '%s\n' "linux/arm64" ;;
    *) printf '%s\n' "linux/amd64" ;;
  esac
}

# 构建远程 K8s 用的 linux/amd64，只打 TCR tag，默认不打 :local
_docker_build_remote() {
  local dockerfile="$1"
  local context="$2"
  local full_ref="$3"
  local latest_ref="$4"
  local platform="${PLATFORM:-linux/amd64}"
  echo "==> docker build remote (${platform})"
  docker build --platform "$platform" \
    -f "$dockerfile" \
    -t "$full_ref" \
    -t "$latest_ref" \
    "$context"
}

# 仅 BUILD_MAC=1 时再打一份本机架构，tag 为 镜像名:local，不推 TCR
_docker_maybe_build_mac() {
  local dockerfile="$1"
  local context="$2"
  local image_name="$3"
  local mac_platform=""
  _docker_want_local_tag || return 0
  mac_platform="$(_docker_mac_platform)"
  echo "==> docker build Mac/local (${mac_platform} -> ${image_name}:local)"
  docker build --platform "$mac_platform" \
    -f "$dockerfile" \
    -t "${image_name}:local" \
    "$context"
}

# 仓库是否属于本次推包的镜像名（短名或 registry/proj/name）
_docker_repo_matches_image() {
  local repo="${1:-}"
  local name="${2:-}"
  [[ -n "$repo" && -n "$name" ]] || return 1
  [[ "$repo" == "$name" || "$repo" == */"$name" ]]
}

# 推送成功后：删除本镜像的历史时间戳 tag，保留当前 tag / latest。
# BUILD_MAC=1 时额外保留 :local。参数：镜像短名、本次 tag。
_docker_cleanup_old_images() {
  local image_name="${1:-}"
  local keep_tag="${2:-}"
  local clean="${CLEAN_OLD_IMAGES:-1}"
  local keep_n="${KEEP_OLD_TAGS:-0}"
  local prune_cache="${PRUNE_BUILD_CACHE:-0}"
  local keep_cache_size="${KEEP_BUILD_CACHE_SIZE:-4GB}"
  local created="" repo="" tag="" ref="" line="" skip_n=0 deleted=0
  local candidates=""
  local to_delete=""
  local force_delete=""

  if [[ "$clean" != "1" ]]; then
    echo "==> 跳过历史镜像清理（CLEAN_OLD_IMAGES=${clean}）"
    return 0
  fi
  if [[ -z "$image_name" || -z "$keep_tag" ]]; then
    echo "WARN: 清理参数不完整，跳过 image=${image_name} tag=${keep_tag}" >&2
    return 0
  fi
  case "$keep_n" in
    ''|*[!0-9]*) keep_n=0 ;;
  esac

  echo "==> 清理本仓库历史镜像: ${image_name}"
  if _docker_want_local_tag; then
    echo "    保留 :local / :latest / :${keep_tag} ，额外 KEEP_OLD_TAGS=${keep_n}"
  else
    echo "    保留 :latest / :${keep_tag} （默认不保留 :local），额外 KEEP_OLD_TAGS=${keep_n}"
  fi

  while IFS='|' read -r created repo tag; do
    created="${created:-}"
    repo="${repo:-}"
    tag="${tag:-}"
    [[ -n "$repo" && -n "$tag" && "$tag" != "<none>" ]] || continue
    _docker_repo_matches_image "$repo" "$image_name" || continue
    case "$tag" in
      latest|"$keep_tag") continue ;;
      local)
        if _docker_want_local_tag; then
          continue
        fi
        # 未开 BUILD_MAC 时 :local 一律删，不占用 KEEP_OLD_TAGS
        force_delete="${force_delete}${repo}:${tag}"$'\n'
        continue
        ;;
    esac
    candidates="${candidates}${created}|${repo}:${tag}"$'\n'
  done < <(docker images --format '{{.CreatedAt}}|{{.Repository}}|{{.Tag}}' 2>/dev/null || true)

  if [[ -z "${candidates//[$'\n']/}" && -z "${force_delete//[$'\n']/}" ]]; then
    echo "    没有可删的历史 tag"
  else
    skip_n=0
    while IFS= read -r line; do
      [[ -n "${line:-}" ]] || continue
      if [[ "$skip_n" -lt "$keep_n" ]]; then
        echo "    保留历史 tag: ${line#*|}"
        skip_n=$((skip_n + 1))
        continue
      fi
      to_delete="${to_delete}${line#*|}"$'\n'
    done < <(printf '%s' "$candidates" | sort -r)
  fi
  to_delete="${force_delete}${to_delete}"

  deleted=0
  while IFS= read -r ref; do
    [[ -n "${ref:-}" ]] || continue
    echo "    docker rmi ${ref}"
    if docker rmi "$ref"; then
      deleted=$((deleted + 1))
    else
      echo "WARN: 删除失败（可能被容器占用）: ${ref}" >&2
    fi
  done < <(printf '%s' "$to_delete")

  echo "    已删除历史 tag: ${deleted}"
  # 只清无 tag 的 dangling，不会删掉其它仍带名字的镜像
  docker image prune -f >/dev/null || true

  if [[ "$prune_cache" == "1" ]]; then
    echo "==> 压缩 BuildKit 缓存（保留 ${keep_cache_size}）"
    docker builder prune -f --keep-storage "$keep_cache_size" || true
  fi
}
