# MCP Gateway

A single-process ASGI gateway that mounts multiple Huawei Cloud FastMCP servers
on one `uvicorn` port, with JWT authentication and path-level RBAC at the
perimeter and tool-level fine-grained authorization inside each server.

```
https://example.com/ecs/sse         ← ECS lifecycle tools
https://example.com/pipeline/sse    ← CodeArts Pipeline tools
https://example.com/cts/sse         ← CTS audit trace tools
https://example.com/healthz         ← Liveness probe (no auth required)
```

## Architecture

```
                          ┌──────────────────────────────────────┐
                          │          MCP Gateway (port 8080)     │
                          │                                      │
  Client ──Bearer JWT──▶ │  GatewayAuthMiddleware                │
                          │    ├─ JWT verify (RS256)             │
                          │    ├─ Path RBAC (coarse)             │
                          │    └─ Inject identity → scope        │
                          │                                      │
                          │  Starlette Mount-based routing:      │
                          │    /ecs     → ecs_mcp_server.sse_app │
                          │    /pipeline → pipeline_mcp_server   │
                          │    /cts     → cts_mcp_server.sse_app │
                          └──────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
             ┌──────────┐   ┌──────────┐   ┌──────────┐
             │ ECS MCP  │   │Pipeline  │   │  CTS MCP │
             │  Server  │   │  MCP Svr │   │  Server  │
             │──────────│   │──────────│   │──────────│
             │AuthStrat │   │AuthStrat │   │AuthStrat │
             │ tool RBAC│   │ tool RBAC│   │ tool RBAC│
             └──────────┘   └──────────┘   └──────────┘
```

### Why single-process mount, not Nginx reverse-proxy?

Each MCP server is an ASGI sub-app mounted at its path prefix. Nginx sees
one upstream on one port — a single `location / { proxy_pass ...; }` is
sufficient. Adding or removing a server only requires editing
`manifest.yaml` and restarting the gateway; **Nginx never changes**.

### Auth architecture: Gateway authentication + Server tool authorization

| Layer | Responsibility | Granularity | Example |
|-------|---------------|-------------|---------|
| Gateway middleware | Verify JWT → parse Identity → path RBAC → inject scope | `/ecs/*` | No ecs role → 403 |
| MCP Server | Read Identity from scope → per-tool role check | `ecs_delete` vs `ecs_list` | Non-admin calls delete → ToolError |

**Why both layers?** The gateway only sees HTTP paths — it cannot
distinguish `ecs_list_servers` from `ecs_delete_server` within a single
SSE connection. Without server-side checks, path RBAC is all-or-nothing.
Conversely, putting all auth in each server means duplicated JWT
verification and any server that forgets to check is exposed.

**Key principle: there is no "no auth" path.** Every MCP server must
contain an AuthStrategy (see below). Even if started standalone, it
requires a valid JWT.

## `manifest.yaml`

```yaml
jwt:
  issuer: mcp-gateway
  public_key: env:MCP_JWT_PUBLIC_KEY    # or file:/path/to/key.pem

services:
  - name: ecs
    enabled: true
    module: ecs_mcp_server
    attr: mcp
    mount_path: /ecs
    required_roles: [readonly, operator, admin]

  - name: pipeline
    enabled: true
    module: pipeline_mcp_server
    attr: mcp
    mount_path: /pipeline
    required_roles: [readonly, operator, admin]

  - name: cts
    enabled: true
    module: cts_mcp_server
    attr: mcp
    mount_path: /cts
    required_roles: [readonly, operator, admin]
```

### Fields

| Field | Description |
|-------|-------------|
| `jwt.issuer` | Expected `iss` claim in incoming JWTs. |
| `jwt.public_key` | RS256 public key. Accepts `file:/path`, `env:VAR_NAME`, or inline PEM. |
| `services[].name` | Unique service identifier. |
| `services[].module` | Python module to import (must expose `mcp` attribute). |
| `services[].attr` | Attribute name on the module (default: `mcp`). |
| `services[].mount_path` | URL prefix for this service (e.g. `/ecs`). |
| `services[].required_roles` | Roles that grant access to this path (any match suffices). |
| `services[].enabled` | Default on/off; can be overridden by env/CLI. |

## Three-layer override (selective startup)

| Priority | Source | Example |
|----------|--------|---------|
| 1 (low) | `manifest.yaml` `enabled` field | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` env var | `ecs,cts` (only these) |
| 3 (high) | CLI `--enable` / `--disable` | `--enable ecs --disable cts` |

Startup log shows exactly which services were mounted and which were
skipped (with reason).

## AuthStrategy: two modes, zero bypasses

Each MCP server contains an `AuthStrategy` that resolves an `Identity`
from the current request:

| Mode | Env var | Behaviour |
|------|---------|-----------|
| `gateway` | `MCP_AUTH_MODE=gateway` | Read `scope["mcp_identity"]` injected by the gateway middleware. Missing → 401. |
| `standalone` | `MCP_AUTH_MODE=standalone` (default) | Verify the JWT itself using the same public key. No token → 401. |

**Default is standalone.** A server accidentally started without the
gateway still requires authentication.

There is **no** `none` mode. The only escape hatch is `MCP_AUTH_MODE=dev`,
which synthesises a full-admin identity for loopback callers only and
emits a `WARNING` log on every invocation.

## Tool-level authorization matrix

### ECS Server

| Tool | Minimum role | Notes |
|------|-------------|-------|
| `ecs_list_servers`, `ecs_get_server`, `ecs_list_flavors`, `ecs_get_job_status` | `readonly` | Read-only queries |
| `ecs_power_action(action="start")` | `operator` | Start servers |
| `ecs_power_action(action="stop"/"reboot")`, `ecs_delete_server`, `ecs_resize_server` | `admin` | Destructive operations |

### Pipeline Server

| Tool | Minimum role | Notes |
|------|-------------|-------|
| `pipeline_list`, `pipeline_get_detail` | `readonly` | Read-only queries |
| `pipeline_run` | `operator` | Trigger execution |
| `pipeline_update_info`, `pipeline_set_status` | `admin` | Configuration changes |

### CTS Server

| Tool | Minimum role | Notes |
|------|-------------|-------|
| `cts_search_traces`, `cts_get_trace_detail` | `readonly` | Audit queries (data may be sensitive) |

Role hierarchy: **admin** ⊃ **operator** ⊃ **readonly**.

## Quick start

```bash
# 1. Generate an RSA key pair for JWT signing
openssl genrsa -out jwt-private.pem 2048
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem

# 2. Edit the root .env — set JWT key, AK/SK, region, etc.
#    MCP_JWT_PUBLIC_KEY="$(cat jwt-public.pem)"
#    MCP_AUTH_MODE=gateway
#    HUAWEICLOUD_ACCESS_KEY_ID=...
#    HUAWEICLOUD_SECRET_ACCESS_KEY=...

# 3. Run the gateway (from workspace root)
./start.sh                     # all enabled services
./start.sh ecs,pipeline        # only these two
./start.sh ecs --port 9000     # custom port
```

## Development / local debugging

```bash
# Dev mode: no JWT required from loopback, WARN on every call
# Set in .env:  MCP_AUTH_MODE=dev
./start.sh --host 127.0.0.1 --port 8080
```

⚠ **DEV MODE IS UNSAFE.** It must never be used on a network-accessible
port. The startup log will print a `WARNING` on every request.

## Deployment

### systemd

See `deploy/mcp-gateway.service`. Key points:

- `ExecStart` uses the workspace-root `start.sh` (loads `.env` + delegates to CLI).
- `EnvironmentFile` points to the single root `.env` (all credentials + config).
- Resource caps and security hardening are applied.

### Nginx (TLS termination only)

See `deploy/nginx.conf.example`. Key property: **one** `location /` block.
Adding/removing MCP servers never requires an Nginx change.

## Adding a 4th MCP server

1. Create the server package with an `AuthStrategy` in its tools.
2. Add it to the `uv` workspace in the root `pyproject.toml`.
3. Add it as a dependency in `mcp-gateway/pyproject.toml`.
4. Add a service entry in `manifest.yaml`.
5. Restart the gateway.

No Nginx changes. No gateway code changes.

## Known pitfalls (verified by tests)

1. **SSE mount prefix loss** — `sse_app(mount_path="/ecs")` ensures the
   client's POST callback includes the prefix. Test:
   `test_mount_path_endpoint_prefix.py`.

2. **Combined lifespan** — `AsyncExitStack` enters all session managers.
   Test: `test_combined_lifespan.py`.

3. **Standalone auth default** — servers default to standalone, never
   unauthenticated. Test: `test_auth_strategy_standalone.py`.

4. **Tool-level RBAC** — `readonly` caller invoking an `admin` tool
   receives `AuthError(403)`. Test: `test_tool_authorization.py`.
