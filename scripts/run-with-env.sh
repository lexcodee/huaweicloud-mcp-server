#!/usr/bin/env bash
# Wrapper that loads .env then execs the MCP server.
# Lets ~/.hermes/config.yaml stay free of credentials.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${HWC_MCP_ENV_FILE:-${SCRIPT_DIR}/../.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# Try the venv entry point first; fall back to uv run.
VENV_BIN="${SCRIPT_DIR}/../.venv/bin/huaweicloud-mcp-server"
if [[ -x "$VENV_BIN" ]]; then
  exec "$VENV_BIN" "$@"
else
  exec uv run huaweicloud-mcp-server "$@"
fi
