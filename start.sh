#!/usr/bin/env bash
# Strategy 1 deployment: single mount /hwc, all Huawei Cloud tools in one place.
#
# Starts the mcp-gateway with the unified manifest. Agents connect to
# http://127.0.0.1:8080/hwc/sse and see all enabled tools (ecs_*, pipeline_*,
# cts_*) in one list.
#
# Env vars consumed via .env:
#   HUAWEICLOUD_AK / SK / PROJECT_ID / REGION  (passed to huaweicloud_mcp)
#   MCP_JWT_PUBLIC_KEY                          (gateway JWT)
#   MCP_GATEWAY_AUTH                            (set to "disabled" for dev)
#   MCP_GATEWAY_PORT                            (default 8080)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${SCRIPT_DIR}/.env"
  set +a
fi

exec uv run mcp-gateway serve \
  --manifest "${SCRIPT_DIR}/manifest.yaml" \
  --port "${MCP_GATEWAY_PORT:-8080}" \
  --host "${MCP_GATEWAY_HOST:-127.0.0.1}" \
  --log-level "${MCP_GATEWAY_LOG_LEVEL:-info}" \
  "$@"
