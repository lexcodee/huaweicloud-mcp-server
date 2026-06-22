#!/usr/bin/env bash
# Wrapper that loads .env then execs the MCP server.
# Lets ~/.hermes/config.yaml stay free of credentials.
set -e
ENV_FILE="${CTS_MCP_ENV_FILE:-../../.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
exec /usr/local/bin/cts-mcp-server "$@"
