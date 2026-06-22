#!/usr/bin/env bash
# Local SSE smoke runner. Loads creds from /root/.huaweicloud/.env
# (override via ECS_MCP_ENV_FILE), then boots uvicorn on 127.0.0.1:8000.
set -euo pipefail

ENV_FILE="${ECS_MCP_ENV_FILE:-../../.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export MCP_HOST="${MCP_HOST:-127.0.0.1}"
export MCP_PORT="${MCP_PORT:-8000}"
export ECS_MCP_LOG_LEVEL="${ECS_MCP_LOG_LEVEL:-INFO}"

echo "starting uvicorn on ${MCP_HOST}:${MCP_PORT} (region=${HUAWEICLOUD_REGION:-unset})"
exec uvicorn ecs_mcp_server.app:app \
  --host "${MCP_HOST}" \
  --port "${MCP_PORT}" \
  --log-level info
