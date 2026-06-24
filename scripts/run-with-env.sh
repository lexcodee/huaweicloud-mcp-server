#!/usr/bin/env bash
# Wrapper that loads .env then execs the MCP server.
# Lets ~/.hermes/config.yaml stay free of credentials.
set -e

ENV_FILE="${HWC_MCP_ENV_FILE:-/root/huaweicloud-mcp-server/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

exec /root/huaweicloud-mcp-server/.venv/bin/huaweicloud-mcp-server "$@"
