#!/usr/bin/env bash
# Delegate to the workspace-root start.sh.
# This wrapper exists so `cd mcp-gateway && ./scripts/start.sh` still works,
# but the real logic lives in one place.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
exec "${ROOT}/start.sh" "$@"
