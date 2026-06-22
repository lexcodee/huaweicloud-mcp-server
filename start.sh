#!/usr/bin/env bash
# =====================================================================
# MCP Gateway startup script
#
# Usage:
#   ./start.sh                  # 启动 manifest.yaml 中 enabled=true 的所有服务
#   ./start.sh ecs,pipeline     # 只挂载 ecs 和 pipeline
#   ./start.sh --port 9000      # 自定义端口
#   ./start.sh ecs --port 9000  # 组合：只挂载 ecs + 自定义端口
#
# 自动加载 workspace 根目录的 .env（包含全部共享凭证和各服务配置）。
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Load the unified .env from the workspace root.
if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${SCRIPT_DIR}/.env"
  set +a
fi

ARGS=()
if [[ $# -gt 0 && "$1" != --* ]]; then
  # First non-flag argument is the service list.
  ARGS+=("--enable" "$1")
  shift
fi

# Remaining arguments pass through to mcp-gateway CLI.
# Supports: --port, --host, --log-level, --manifest, --disable, etc.
# Default --manifest points to the root manifest.yaml (set via MCP_GATEWAY_MANIFEST
# in .env, or hardcoded here as a fallback).
ARGS+=("--manifest" "${SCRIPT_DIR}/manifest.yaml")
exec uv run mcp-gateway "${ARGS[@]}" "$@"
