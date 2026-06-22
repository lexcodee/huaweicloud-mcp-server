#!/usr/bin/env bash
# Wrapper that loads CodeArts Pipeline MCP server credentials from a shared
# Huawei Cloud .env file (the same one used by the ECS MCP server), then
# execs the entrypoint. This keeps AK/SK out of ~/.hermes/config.yaml.
#
# Default location: /root/huaweicloud-mcp-server/.env (chmod 600)
# Override with:    CODEARTS_PIPELINE_MCP_ENV_FILE=/path/to/.env
set -e
ENV_FILE="${CODEARTS_PIPELINE_MCP_ENV_FILE:-/root/huaweicloud-mcp-server/.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
exec /usr/local/bin/codearts-pipeline-mcp-server "$@"
