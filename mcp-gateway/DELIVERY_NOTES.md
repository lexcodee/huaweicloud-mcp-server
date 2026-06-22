# MCP Gateway — Delivery Notes

## Deliverables

| # | Item | Location |
|---|------|----------|
| 1 | `mcp-gateway` complete runnable project | `mcp-gateway/` |
| 2 | `mcp-auth-common` shared auth package | `mcp-auth-common/` |
| 3 | Three existing servers: export interface unified + AuthStrategy embedded | `ecs-mcp-server/`, `codearts-pipeline-mcp-server/`, `cts-mcp-server/` |
| 4 | Root workspace `pyproject.toml` | `pyproject.toml` |
| 5 | `manifest.yaml` example | `mcp-gateway/manifest.yaml` |
| 6 | `.env.example` | `mcp-gateway/.env.example` |
| 7 | `deploy/mcp-gateway.service` | `mcp-gateway/deploy/mcp-gateway.service` |
| 8 | `deploy/nginx.conf.example` | `mcp-gateway/deploy/nginx.conf.example` |
| 9 | `scripts/start.sh` | `mcp-gateway/scripts/start.sh` |
| 10 | `README.md` | `mcp-gateway/README.md` |
| 11 | `TEST_REPORT.md` | `mcp-gateway/TEST_REPORT.md` |
| 12 | 7 test files, 58 tests, all passing | `mcp-gateway/tests/` |

## Differences from the original prompt

| Prompt assumption | Actual finding | Resolution |
|---|---|---|
| Module names: `huaweicloud_ecs_mcp_server`, `codearts_pipeline_mcp_server`, `cts_trace_mcp_server` | Actual: `ecs_mcp_server`, `pipeline_mcp_server`, `cts_mcp_server` | Used actual module names in `manifest.yaml` and all code |
| ECS tools: `ecs_start_server`, `ecs_stop_server`, `ecs_reboot_server` | Actual: merged into `ecs_power_action(action=...)` | RBAC dispatches on `action` parameter: `start` → operator, `stop`/`reboot` → admin |
| Pipeline tools: `pipeline_enable`, `pipeline_disable` | Actual: merged into `pipeline_set_status(status=...)` | RBAC requires `admin` for any status change |
| `AuthStrategy.resolve()` is `async` | Made `sync` because all work is in-process (dict lookup or PyJWT verify) | This lets existing sync `@wrap_tool` tool bodies call `auth.resolve(current_scope())` without `await` |
| `__init__.py` should `from .server import mcp` | Used `__getattr__` lazy import instead | Avoids crashing the importer when Huawei Cloud credentials aren't configured (e.g. during gateway startup before env is loaded) |
| `mcp-gateway/pyproject.toml` lists three MCP servers as `dependencies` | Removed from `dependencies` list (kept in `[tool.uv.sources]`) | `pip` can't resolve workspace-internal deps; `uv` can. The gateway uses `importlib.import_module()` which finds them on `sys.path` regardless |
| Prompt structure has `auth/` subpackage with `middleware.py`, `strategy.py`, `identity.py`, `errors.py` | Created as re-export facades; actual code lives in `auth_middleware.py` (top-level) and `mcp_auth_common` | The `auth/` subpackage re-exports everything so imports like `from mcp_gateway.auth.middleware import GatewayAuthMiddleware` work as the spec expects |

## How to run

```bash
# Install all packages (pip, no uv)
pip install -e ./mcp-auth-common
pip install -e ./ecs-mcp-server
pip install -e ./codearts-pipeline-mcp-server
pip install -e ./cts-mcp-server
pip install -e ./mcp-gateway

# Set JWT public key (generate with openssl if needed)
export MCP_JWT_PUBLIC_KEY="$(cat /path/to/jwt-public.pem)"
export MCP_AUTH_MODE=gateway

# Set Huawei Cloud credentials
export HUAWEICLOUD_ACCESS_KEY_ID=...
export HUAWEICLOUD_SECRET_ACCESS_KEY=...
export HUAWEICLOUD_REGION=cn-north-4

# Run the gateway
mcp-gateway --manifest mcp-gateway/manifest.yaml

# Or selectively
mcp-gateway --manifest mcp-gateway/manifest.yaml --enable ecs,cts

# Or via the convenience script
./mcp-gateway/scripts/start.sh ecs,pipeline
```

## With `uv` workspace (recommended for production)

```bash
# The root pyproject.toml declares the workspace
uv sync                    # resolves all workspace members
uv run mcp-gateway          # runs the gateway
```
