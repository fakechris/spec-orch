#!/usr/bin/env bash

resolve_shared_repo_root() {
  local common_dir=""
  common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"
  if [ -z "$common_dir" ]; then
    return 1
  fi
  case "$common_dir" in
    /*) ;;
    *) common_dir="$REPO_ROOT/$common_dir" ;;
  esac
  cd "$(dirname "$common_dir")" && pwd
}

resolve_env_file() {
  if [ -f .env ]; then
    printf '%s\n' ".env"
    return 0
  fi
  local shared_root=""
  shared_root="$(resolve_shared_repo_root || true)"
  if [ -n "$shared_root" ] && [ -f "$shared_root/.env" ]; then
    printf '%s\n' "$shared_root/.env"
    return 0
  fi
  return 1
}

resolve_uv_project_environment() {
  if [ -n "${UV_PROJECT_ENVIRONMENT:-}" ]; then
    printf '%s\n' "$UV_PROJECT_ENVIRONMENT"
    return 0
  fi
  local shared_root=""
  shared_root="$(resolve_shared_repo_root || true)"
  if [ -n "$shared_root" ] && [ -d "$shared_root/.venv-py313" ]; then
    printf '%s\n' "$shared_root/.venv-py313"
    return 0
  fi
  return 1
}

activate_shared_worktree_context() {
  local env_file=""
  env_file="$(resolve_env_file || true)"
  if [ -n "$env_file" ] && [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi

  if [ -z "${UV_PROJECT_ENVIRONMENT:-}" ]; then
    local shared_uv_env=""
    shared_uv_env="$(resolve_uv_project_environment || true)"
    if [ -n "$shared_uv_env" ]; then
      export UV_PROJECT_ENVIRONMENT="$shared_uv_env"
    fi
  fi
}
