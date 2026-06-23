#!/usr/bin/env bash
# Wrapper that loads the shared Huawei Cloud .env then execs the unified
# MCP server. Keeps AK/SK out of ~/.hermes/config.yaml.
#
# Default .env: /root/huaweicloud-mcp-server/.env (chmod 600)
# Override:     HUAWEICLOUD_MCP_ENV_FILE=/path/to/.env
#
# All three services (ECS, Pipeline, CTS) are enabled by default.
# To mount a subset, set MCP_ENABLED_SERVICES in the .env file, e.g.:
#   MCP_ENABLED_SERVICES=ecs,pipeline
set -e
ENV_FILE="${HUAWEICLOUD_MCP_ENV_FILE:-/root/huaweicloud-mcp-server/.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
exec /root/huaweicloud-mcp-server/.venv/bin/huaweicloud-mcp-server "$@"
