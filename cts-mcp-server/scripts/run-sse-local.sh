#!/usr/bin/env bash
# Run the CTS MCP server locally with SSE transport for browser / Postman testing.
set -e
ENV_FILE="${CTS_MCP_ENV_FILE:-../../.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
MCP_TRANSPORT=sse MCP_PORT="${CTS_MCP_PORT:-8000}" exec cts-mcp-server "$@"
