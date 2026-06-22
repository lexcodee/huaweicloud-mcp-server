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

There is **no** `none` mode. The only escape hatch is
`MCP_GATEWAY_AUTH_MODE=dev`, which synthesises a full-admin identity
for callers without JWT verification. By default it restricts to
loopback callers only (`MCP_DEV_LOOPBACK_ONLY=true`). Set
`MCP_DEV_LOOPBACK_ONLY=false` to allow any caller — this is the
dangerous escape hatch for isolated CI/test environments.

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

## Token CLI

The gateway ships a built-in token management CLI with three subcommands:

### `mcp-gateway token keygen` — Generate RSA key pair

```bash
mcp-gateway token keygen                              # defaults: jwt-private.pem / jwt-public.pem / 2048 bits
mcp-gateway token keygen --bits 4096                  # stronger key
mcp-gateway token keygen --private-key /etc/mcp/jwt-private.pem \
                          --public-key  /etc/mcp/jwt-public.pem
```

Outputs the private key (mode 0600) and public key PEM files, and prints
the `MCP_JWT_PUBLIC_KEY` env var snippet for your `.env`.

### `mcp-gateway token create` — Sign a JWT

```bash
# Minimal — outputs raw JWT string
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# Full options
mcp-gateway token create \
  --sub ops-bot \
  --roles operator,readonly \
  --private-key jwt-private.pem \
  --issuer mcp-gateway \
  --audience mcp-api \
  --tenant proj-abc \
  --ttl 7200 \
  --format json
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--sub` | Yes | — | Subject (user or service account id) |
| `--roles` | Yes | — | Comma-separated role list |
| `--private-key` | No | `jwt-private.pem` | Path to RSA private key PEM |
| `--issuer` | No | `mcp-gateway` | JWT `iss` claim |
| `--audience` | No | — | JWT `aud` claim |
| `--tenant` | No | — | Tenant / project id |
| `--ttl` | No | `3600` | Token lifetime in seconds |
| `--format` | No | `token` | `token` (raw JWT) or `json` (with metadata) |

The `--format json` output includes the token plus decoded metadata
(`sub`, `roles`, `iss`, `iat`, `exp`, `expires_at`, `tenant`).

Unknown role names (outside `admin`/`operator`/`readonly`) produce a
stderr warning but are not rejected — custom hierarchies are valid.

### `mcp-gateway token verify` — Decode and verify a JWT

```bash
mcp-gateway token verify --public-key jwt-public.pem --token "eyJ..."
# Or pipe from stdin:
echo "eyJ..." | mcp-gateway token verify --public-key jwt-public.pem
```

Prints the decoded payload as pretty-printed JSON (with a human-readable
`_expires_at` field). Returns exit code 1 on expired / invalid /
wrong-issuer tokens.

### Typical workflow

```bash
# 1. Generate keys (once)
mcp-gateway token keygen

# 2. Sign a token
TOKEN=*** token create --sub ops-bot --roles operator,readonly)

# 3. Call the gateway
curl -H "Authorization: Bearer *** https://gateway:8080/ecs/sse

# 4. Debug / inspect
mcp-gateway token verify --token "$TOKEN"
```

## Quick start

```bash
# 1. Generate an RSA key pair for JWT signing
mcp-gateway token keygen
# Or manually:
#   openssl genrsa -out jwt-private.pem 2048
#   openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem

# 2. Sign a JWT token
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# 3. Edit the root .env — set JWT key, AK/SK, region, etc.
#    MCP_JWT_PUBLIC_KEY="file:jwt-public.pem"
#    MCP_GATEWAY_AUTH_MODE=jwt
#    HUAWEICLOUD_ACCESS_KEY_ID=...
#    HUAWEICLOUD_SECRET_ACCESS_KEY=...

# 4. Run the gateway (from workspace root)
./start.sh                     # all enabled services
./start.sh ecs,pipeline        # only these two
./start.sh ecs --port 9000     # custom port
```

## Development / local debugging

```bash
# Dev mode (loopback only): no JWT required from loopback, WARN on every call
# Set in .env:  MCP_GATEWAY_AUTH_MODE=*** --host 127.0.0.1 --port 8080

# Dev mode (open — CI only): any caller allowed, CRITICAL on startup
# Set in .env:  MCP_GATEWAY_AUTH_MODE=*** --host 127.0.0.1 --port 8080
./start.sh --host 127.0.0.1 --port 8080

# Or sign a real token for local testing:
mcp-gateway token keygen
TOKEN=*** token create --sub dev --roles admin --private-key jwt-private.pem)
curl -H "Authorization: Bearer *** http://127.0.0.1:8080/ecs/sse
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
