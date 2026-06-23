# Huawei Cloud MCP Server

**English** | [中文](README.md)

One MCP Server for all Huawei Cloud services. Agents connect to **one URL** and
access every enabled cloud service tool. Enable only the services you need,
secure production with JWT auth, and add new cloud services with **zero
Agent-side config change**.

**Available**: ECS (cloud servers), CodeArts Pipeline (CI/CD), CTS (audit logs), CCE (cloud container engine)
**Coming soon**: OBS (object storage), RDS (relational DB), VPC (virtual network)…

```
https://example.com/hwc/sse    ← All Huawei Cloud tools (ecs_*, pipeline_*, cts_*, obs_*, …)
https://example.com/healthz    ← Gateway health (no auth)
```

**Key design**:

| Feature | Description |
|---------|-------------|
| Single URL | Agent configures one MCP server entry, forever |
| On-demand enable | `MCP_ENABLED_SERVICES=ecs,pipeline` loads only what you need |
| JWT auth | RS256 verification + role RBAC for production; no auth for local dev |
| Two-phase commit | Destructive ops (delete/stop/resize) require explicit user approval |
| Zero-config growth | New cloud services are server-side only, Agent is unaware |

---

## Project structure

```
huaweicloud-mcp-server/          # ← workspace root
├── start.sh                       ← Start script (loads .env + starts gateway)
├── .env                           ← Unified env vars (AK/SK + JWT + config)
├── .env.example                   ← Full template
├── manifest.yaml                  ← Service topology (Strategy 1: single mount /hwc)
├── pyproject.toml                 ← uv workspace declaration
│
├── huaweicloud-mcp-server/        ← Unified Huawei Cloud MCP Server
│   └── src/huaweicloud_mcp/
│       ├── server.py              ← build_server(enabled=[...]) → FastMCP
│       ├── config.py              ← Unified Settings (AK/SK/region/project_id)
│       ├── client.py              ← get_client(service, settings) — lru_cached
│       ├── errors.py              ← ToolError, two-phase commit
│       ├── logging_setup.py       ← SecretMaskingFilter + redacted logging
│       └── services/
│           ├── ecs/               ← 8 tools (list/get/power/delete/resize)
│           ├── pipeline/          ← 6 tools (list/get/run/update/toggle)
│           ├── cts/               ← 2 tools (search/get audit traces)
│           └── cce/               ← 6 tools (query clusters/nodes/nodepools, update nodepool, get_job)
│
├── mcp-auth-common/               ← Shared auth (Identity / AutoAuth / require_role)
│   └── src/mcp_auth_common/
│
└── mcp-gateway/                   ← ASGI gateway (Starlette Mount + JWT middleware)
    ├── src/mcp_gateway/
    └── deploy/                    ← systemd + Nginx config
```

### huaweicloud_mcp internal architecture

```
huaweicloud_mcp/
├── __init__.py
├── config.py          # Unified Settings dataclass + load_settings()
├── client.py          # SDK client factory: get_client("ecs", settings) — lru_cached
├── errors.py          # ToolError, wrap_tool decorator, PendingActions (two-phase commit)
├── logging_setup.py   # SecretMaskingFilter + setup_logging()
├── server.py          # build_server(enabled={"ecs","pipeline","cts","cce"}) → FastMCP
├── app.py             # ASGI entrypoint for SSE/HTTP (with keep-alive middleware)
└── services/
    ├── ecs/
    │   ├── make_tools.py    # make_tools(settings) → dict of tool callables
    │   ├── models.py        # Pydantic input models
    │   ├── serializers.py   # SDK response → plain dict
    │   └── tools/
    │       ├── query.py     # list_servers, get_server, list_flavors
    │       ├── lifecycle.py # power_action, delete_server, resize_server, confirm_destructive
    │       └── job.py       # get_job_status
    ├── pipeline/
    │   ├── make_tools.py
    │   ├── models.py
    │   ├── serializers.py
    │   ├── client_helpers.py    # SDK typed/untyped API workarounds
    │   ├── definition_utils.py  # pipeline definition JSON manipulation
    │   └── tools/
    │       ├── query.py      # list, get_detail
    │       ├── execution.py  # run
    │       ├── lifecycle.py  # set_status, confirm_destructive
    │       └── update.py     # update_info, confirm_destructive
    └── cts/
        ├── make_tools.py
        ├── models.py
        ├── serializers.py
        ├── time_utils.py     # human time → 13-digit UTC ms
        ├── mask_utils.py     # sensitive value masking
        └── tools/
            ├── search.py     # search_traces
            └── detail.py     # get_trace_detail
    └── cce/
        ├── make_tools.py
        ├── models.py
        ├── serializers.py
        └── tools/
            ├── query.py      # query_clusters, query_nodes, query_nodepools
            ├── update.py     # update_nodepool, confirm_destructive
            └── job.py        # get_job
```

### Shared infrastructure

| Module | Purpose |
|--------|---------|
| `config.py` | Single `Settings` dataclass — AK/SK/region/project_id/timezone. `load_settings()` reads from env, validates required vars, exits fast on missing. |
| `client.py` | `get_client(service, settings)` → cached SDK client. One factory for ECS, Pipeline, CTS, CCE clients with shared HttpConfig (timeout, retries). |
| `errors.py` | `ToolError` exception + `wrap_tool` decorator that catches SDK errors, normalizes them to `{ok: false, error: {...}}` envelopes, and logs structured events. `PendingActions` implements the two-phase commit for destructive ops. |
| `logging_setup.py` | `SecretMaskingFilter` redacts AK/SK in log output. `setup_logging()` configures stderr-only (stdio-safe) or file logging. |

---

## MCP tools (21 total)

### ECS — Cloud server lifecycle management (8 tools)

| Tool | Description | Min role |
|------|-------------|----------|
| `ecs_list_servers` | List servers (filters: name, status, IP, tags) | readonly |
| `ecs_get_server` | Server detail or status snapshot | readonly |
| `ecs_list_flavors` | Available instance types | readonly |
| `ecs_get_job_status` | Async job status poll | readonly |
| `ecs_power_action` | Batch start / stop / reboot | operator / admin |
| `ecs_delete_server` | ⚠ Delete servers (+ optional EIP/volumes) | admin |
| `ecs_resize_server` | ⚠ Change flavor (vCPU/RAM) | admin |
| `ecs_confirm_destructive` | Execute pending destructive op | — |

### Pipeline — CodeArts pipeline management (6 tools)

| Tool | Description | Min role |
|------|-------------|----------|
| `pipeline_list` | List pipelines + latest-run status | readonly |
| `pipeline_get_detail` | Full pipeline config | readonly |
| `pipeline_run` | Trigger a run | operator |
| `pipeline_set_status` | ⚠ Enable/disable pipeline | admin |
| `pipeline_update_info` | ⚠ Update default branch / trigger | admin |
| `pipeline_confirm_destructive` | Execute pending destructive op | — |

### CTS — Audit log search (2 tools)

|| Tool | Description | Min role |
|------|-------------|----------|
| `cts_search_traces` | Search audit events (7-day window) | readonly |
| `cts_get_trace_detail` | Full masked request/response body | readonly |

### CCE — Cloud container engine management (6 tools)

|| Tool | Description | Min role |
|------|-------------|----------|
| `cce_query_clusters` | List clusters / get single cluster detail | readonly |
| `cce_query_nodes` | List cluster nodes / get single node detail | readonly |
| `cce_query_nodepools` | List node pools / get single pool detail | readonly |
| `cce_update_nodepool` | ⚠ Resize node pool desired count (scale-down requires two-phase confirm; DefaultPool scaling not supported) | operator |
| `cce_get_job` | Poll async job status (cluster create/upgrade/node-pool resize etc.) | readonly |
| `cce_confirm_destructive` | Execute pending destructive op (scale-down) | — |

> Role hierarchy: **admin** ⊃ **operator** ⊃ **readonly**

---

## Two-phase commit (destructive operations)

Destructive tools (stop, reboot, delete, resize, disable pipeline, update pipeline,
scale-down node pool)
follow a two-phase commit pattern to prevent accidental execution:

```
Phase 1: Tool call returns a preview + approval_id (TTL 120s)
         → {status: "pending_approval", approval_id: "...", preview: {...}}

Phase 2: User explicitly approves
         → ecs_confirm_destructive(approval_id="...")
         → Operation executes, returns {ok: true, data: {...}}
```

If the approval ID expires, re-issue the original call to get a fresh one.

---

## Gateway architecture (Strategy 1)

```
                          ┌──────────────────────────────────────┐
                          │       MCP Gateway (port 8080)        │
                          │                                      │
  Agent ──Bearer JWT──▶  │  GatewayAuthMiddleware                │
                          │    ├─ JWT verify (RS256)             │
                          │    ├─ Path RBAC (coarse)             │
                          │    └─ Inject identity → scope        │
                          │                                      │
                          │  Single mount:                       │
                          │    /hwc  → build_server(             │
                          │             enabled=[ecs,pipeline,cts│
                          │                        ,cce]         │
                          │           )                           │
                          └──────────────────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  Unified FastMCP  │
                          │  21 tools:        │
                          │    ecs_* (8)      │
                          │    pipeline_* (6) │
                          │    cts_* (2)      │
                          │    cce_* (5+1)    │
                          └──────────────────┘
```

### Auth layers

| Layer | Responsibility | Granularity | Example |
|-------|---------------|-------------|---------|
| Gateway middleware | Verify JWT → parse Identity → path RBAC → inject scope | `/hwc/*` | No hwc permission → 403 |
| MCP Server | Read Identity from scope → per-tool role check | `ecs_delete` vs `ecs_list` | Non-admin calls delete → ToolError |

### Server-side auth: auto-detect, zero config

| Scenario | Behavior | Notes |
|----------|----------|-------|
| Behind gateway | `scope["mcp_identity"]` exists → use it | Gateway verified, Identity trusted |
| Standalone (stdio/SSE) | No gateway identity → synthesize dev Identity + ⚠ WARN | Local dev, auto-allow |

### Gateway auth modes

| Mode | Env var | Behavior | Use case |
|------|---------|----------|----------|
| `jwt` | `MCP_GATEWAY_AUTH_MODE=*** (default) | Full JWT verify + path RBAC | Production |
| `dev` | `MCP_GATEWAY_AUTH_MODE=*** | Skip JWT, synthesize Identity | Non-production |

Dev mode source restriction via `MCP_DEV_LOOPBACK_ONLY`:

| Sub-mode | Env var | Behavior | Use case |
|----------|---------|----------|----------|
| loopback-only | `MCP_DEV_LOOPBACK_ONLY=true` (default) | Only loopback callers allowed | Local dev |
| open | `MCP_DEV_LOOPBACK_ONLY=false` | Any source allowed (CRITICAL log) | CI / isolated test |

---

## Quick start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Huawei Cloud AK/SK

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

Edit `.env` in the repo root:

```bash
# Huawei Cloud credentials (shared by all services)
HUAWEICLOUD_ACCESS_KEY_ID=your-ak
HUAWEICLOUD_SECRET_ACCESS_KEY=your-s...n
# Gateway auth mode (dev for local, jwt for production)
MCP_GATEWAY_AUTH_MODE=dev
M...n### 3. Start the gateway

Three options — pick any:

**Option A — Start script (recommended)**

Auto-loads `.env`, defaults to `127.0.0.1:8080`:

```bash
./start.sh
```

**Option B — CLI command**

```bash
mcp-gateway serve --manifest manifest.yaml --host 0.0.0.0 --port 8080 --log-level info
```

Common options:

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--manifest` | `MCP_GATEWAY_MANIFEST` | `manifest.yaml` | Service topology file |
| `--enable <svc>` | `MCP_GATEWAY_ENABLED_SERVICES` | — | Enable specific services (overrides manifest + env) |
| `--disable <svc>` | — | — | Disable specific services |
| `--host` | `MCP_GATEWAY_HOST` | `0.0.0.0` | Listen address |
| `--port` | `MCP_GATEWAY_PORT` | `8080` | Listen port |
| `--log-level` | `MCP_GATEWAY_LOG_LEVEL` | `info` | Log level |
| `--print-only` | — | — | Build app and print mount plan without starting uvicorn (debug) |

**Option C — uvicorn direct ASGI app**

```bash
uvicorn mcp_gateway.gateway:app --factory --host 0.0.0.0 --port 8080
```

The module-level `app` is a lazy factory callable — `--factory` is required. Uvicorn resolves it on first request, avoiding import-time side effects.

### 4. Verify

```bash
curl http://127.0.0.1:8080/healthz
# {"status":"ok","mounted":[{"name":"huaweicloud","mount_path":"/hwc"}]}
```

### 5. Issue JWT tokens (production)

```bash
# Generate key pair
mcp-gateway token keygen

# Issue token
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# Call gateway with token
curl -H "Authorization: Bearer *** http://127.0.0.1:8080/hwc/sse
```

## Standalone stdio (local dev, no gateway)

The unified server can run directly via stdio — no gateway or JWT needed:

```bash
# All services (21 tools)
huaweicloud-mcp-server

# Subset only
MCP_ENABLED_SERVICES=ecs,pipeline huaweicloud-mcp-server

# SSE mode
MCP_TRANSPORT=sse MCP_PORT=8000 huaweicloud-mcp-server
```

---

## Agent configuration

> In stdio mode, credentials (AK/SK/Region) must be passed via `env` — the
> spawned process does not inherit shell environment variables.
> In SSE mode, auth is handled by the gateway; the Agent only sends a JWT token.

### Hermes Agent

Add to `~/.hermes/config.yaml`.

**stdio (local dev, recommended)**

```yaml
mcp_servers:
  huaweicloud:
    command: /path/to/.venv/bin/huaweicloud-mcp-server
    timeout: 120
    env:
      HUAWEICLOUD_ACCESS_KEY_ID: your_ak
      HUAWEICLOUD_SECRET_ACCESS_KEY: your_sk
      HUAWEICLOUD_REGION: af-south-1
      HUAWEICLOUD_PROJECT_ID: your_project_id
      CODEARTS_DEFAULT_PROJECT_ID: your_pipeline_project_id
    # Optional: enable only a subset of services
    # env:
    #   MCP_ENABLED_SERVICES: ecs,pipeline
```

**SSE via gateway (production)**

```yaml
mcp_servers:
  huaweicloud:
    url: http://127.0.0.1:8080/hwc/sse
    transport: sse
    timeout: 120
    connect_timeout: 30
    headers:
      Authorization: Bearer ***rmes mcp test huaweicloud
#   ✓ Connected (643ms)
#   ✓ Tools discovered: 21
```

### Claude Code

Add to `~/.claude/mcp.json` (or project-level `.claude/mcp.json`).

**stdio (local dev)**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "command": "/path/to/.venv/bin/huaweicloud-mcp-server",
      "timeout": 120,
      "env": {
        "HUAWEICLOUD_ACCESS_KEY_ID": "your_ak",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "your_sk",
        "HUAWEICLOUD_REGION": "af-south-1",
        "HUAWEICLOUD_PROJECT_ID": "your_project_id",
        "CODEARTS_DEFAULT_PROJECT_ID": "your_pipeline_project_id"
      }
    }
  }
}
```

**SSE via gateway (production)**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "url": "http://127.0.0.1:8080/hwc/sse",
      "transport": "sse",
      "timeout": 120,
      "headers": {
        "Authorization": "Bearer eyJhbG..."
      }
    }
  }
}
```

### Claude Desktop / Cursor / Cline

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`).

**stdio (local dev)**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "command": "/path/to/.venv/bin/huaweicloud-mcp-server",
      "env": {
        "HUAWEICLOUD_ACCESS_KEY_ID": "your_ak",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "your_sk",
        "HUAWEICLOUD_REGION": "af-south-1",
        "HUAWEICLOUD_PROJECT_ID": "your_project_id"
      }
    }
  }
}
```

**SSE via gateway (production)**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "url": "http://127.0.0.1:8080/hwc/sse",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer eyJhbG..."
      }
    }
  }
}
```

> **Key point**: Regardless of how many Huawei Cloud services are added, the
> Agent always configures **one** MCP server entry. New services appear as
> additional tools (`obs_*`, `rds_*`, …) without any Agent-side config change.

---

## Token CLI

The gateway ships a built-in token management CLI.

### `mcp-gateway token keygen` — Generate RSA key pair

```bash
mcp-gateway token keygen                              # defaults: jwt-private.pem / jwt-public.pem / 2048 bits
mcp-gateway token keygen --bits 4096                  # stronger key
mcp-gateway token keygen --private-key /etc/mcp/jwt-private.pem \
                          --public-key  /etc/mcp/jwt-public.pem
```

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

# Permanent token (never expires)
mcp-gateway token create --sub service-account --roles admin --private-key jwt-private.pem --ttl 0
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--sub` | Yes | — | Subject (user or service account id) |
| `--roles` | Yes | — | Comma-separated role list |
| `--private-key` | No | `jwt-private.pem` | Path to RSA private key PEM |
| `--issuer` | No | `mcp-gateway` | JWT `iss` claim |
| `--audience` | No | — | JWT `aud` claim |
| `--tenant` | No | — | Tenant / project id |
| `--ttl` | No | `3600` | Lifetime in seconds; `0` = permanent |
| `--format` | No | `token` | `token` (raw JWT) or `json` (with metadata) |

### `mcp-gateway token verify` — Decode and verify a JWT

```bash
mcp-gateway token verify --public-key jwt-public.pem --token "eyJ..."
# Or pipe from stdin:
echo "eyJ..." | mcp-gateway token verify --public-key jwt-public.pem
```

---

## Adding a new Huawei Cloud service

1. Create `huaweicloud_mcp/services/<name>/` with `make_tools(settings) → dict`
2. Add `if "<name>" in enabled` branch in `server.py:build_server()`
3. Append `"<name>"` to `build_kwargs.enabled` in `manifest.yaml`
4. Restart gateway — new tools appear automatically

**No Nginx change. No gateway code change. No Agent config change.**

---

## Production deployment

### systemd

See `mcp-gateway/deploy/mcp-gateway.service`:

```ini
[Service]
WorkingDirectory=/opt/mcp-servers
EnvironmentFile=/etc/mcp-gateway/.env
ExecStart=/opt/mcp-servers/start.sh \
    --manifest /opt/mcp-servers/manifest.yaml
```

### Nginx (TLS termination only)

See `mcp-gateway/deploy/nginx.conf.example`. Key property: **one** `location /`
rule. Adding/removing MCP services **does not** require Nginx changes.

---

## Selective service enable

Three override layers (low → high priority):

| Layer | Source | Example |
|-------|--------|---------|
| 1 | `manifest.yaml` `enabled` field | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` env var | `huaweicloud` |
| 3 | CLI `--enable` / `--disable` | `./start.sh --enable ecs,pipeline` |

Startup logs clearly print mounted/skipped services and skip reasons.

---

## Environment variables

### Huawei Cloud credentials

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | yes | | Access key ID |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | yes | | Secret access key |
| `HUAWEICLOUD_REGION` | yes | | Region, e.g. `af-south-1` |
| `HUAWEICLOUD_PROJECT_ID` | ECS/CTS | | Project UUID |
| `CODEARTS_DEFAULT_PROJECT_ID` | Pipeline | `=HUAWEICLOUD_PROJECT_ID` | Pipeline project fallback |
| `CTS_DEFAULT_TIMEZONE` | no | `Asia/Shanghai` | CTS time parsing timezone |

### MCP Server

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_TRANSPORT` | no | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | no | `127.0.0.1` | SSE/HTTP bind host |
| `MCP_PORT` | no | `8000` | SSE/HTTP bind port |
| `MCP_ENABLED_SERVICES` | no | `ecs,pipeline,cts,cce` | Comma-separated service subset |
| `HUAWEICLOUD_MCP_LOG_LEVEL` | no | `INFO` | Log level |
| `HUAWEICLOUD_MCP_LOG_FILE` | no | stderr | Log file path |
| `HUAWEICLOUD_MCP_HTTP_TIMEOUT` | no | `30` | SDK HTTP timeout (seconds) |
| `HUAWEICLOUD_MCP_NETWORK_RETRIES` | no | `2` | SDK retry count |

### Gateway auth

| Variable | Required | Description |
|----------|----------|-------------|
| `MCP_GATEWAY_AUTH_MODE` | ✅ | Gateway auth: `jwt` / `dev` |
| `MCP_GATEWAY_HOST` | ✅ | Listen address (`127.0.0.1` for dev) |
| `MCP_GATEWAY_PORT` | optional | Listen port, default `8080` |
| `MCP_DEV_LOOPBACK_ONLY` | optional | Dev source restriction: `true` (default) / `false` |
| `MCP_GATEWAY_LOG_FORMAT` | optional | Log format: `text` (default) / `json` |
| `MCP_JWT_PUBLIC_KEY` | jwt required | RS256 public key (`file:` / `env:` / inline PEM) |
| `MCP_JWT_ISSUER` | recommended | JWT issuer, default `mcp-gateway` |

Full list in `.env.example`.

---

## Shared auth library (mcp-auth-common)

| Component | Description |
|-----------|-------------|
| `Identity` | pydantic v2 model: `sub` / `roles` / `tenant` / `iat` / `exp` |
| `AutoAuth` | Auto-detect: gateway identity → use; else synthesize dev Identity + WARN |
| `AuthStrategy` | Abstract base class |
| `require_role()` | Role check with admin ⊃ operator ⊃ readonly hierarchy |
| `set_request_scope()` / `current_scope()` | contextvar pipe for scope access without `ctx` param |

---

## Development

### Install

```bash
# From workspace root
uv sync
```

### Run tests

```bash
# Unified server (182 tests)
uv run pytest huaweicloud-mcp-server/tests/ -q

# Gateway (120 tests)
uv run pytest mcp-gateway/tests/ -q

# All (302 tests)
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

### Test structure

| Category | Count | What it covers |
|----------|-------|----------------|
| ECS tools | 52 | list/get/power/delete/resize/confirm/job |
| Pipeline tools | 48 | list/get/run/update/toggle/confirm |
| CTS tools | 36 | search/detail + time_utils + mask_utils + 7-day window |
| CCE tools | 30 | query clusters/nodes/nodepools + update nodepool + get_job + confirm + DefaultPool rejection |
| Config / client | 16 | Settings validation, client factory, caching |
| Gateway auth | 10 | JWT verify + RBAC + Identity injection + permanent token |
| Gateway dev mode | 10 | No JWT / loopback / open / disabled |
| Structured logging | 9 | JSON format / extra fields / audit events |
| Tool-level RBAC | 14 | Role hierarchy + 4-service auth matrix |
| Manifest override | 9 | 3-layer override + skip reasons + dedup |
| Factory mode | 9 | build_kwargs parsing + factory call + errors |
| SSE prefix regression | 1 | No double /hwc/hwc in endpoint event |
| Token CLI | 18 | keygen + create + verify + permanent token + e2e round-trip |
| Combined lifespan | 4 | Multi-FastMCP mount |

---

## License

MIT
