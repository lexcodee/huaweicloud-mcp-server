# Huawei Cloud MCP Server

**English** | [中文](README.md)

One MCP Server for all Huawei Cloud services. Agents connect to **one URL** and
access every enabled cloud service tool. Enable only the services you need,
secure production with JWT auth, and add new cloud services with **zero
Agent-side config change**.

**Available**: ECS (cloud servers), CodeArts Pipeline (CI/CD), CTS (audit logs)
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

## Project structure

```
huaweicloud-mcp-server/
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
│       └── services/
│           ├── ecs/               ← 8 tools (list/get/power/delete/resize)
│           ├── pipeline/          ← 6 tools (list/get/run/update/toggle)
│           └── cts/               ← 2 tools (search/get audit traces)
│
├── mcp-auth-common/               ← Shared auth (Identity / AutoAuth / require_role)
│   └── src/mcp_auth_common/
│
└── mcp-gateway/                   ← ASGI gateway (Starlette Mount + JWT middleware)
    ├── src/mcp_gateway/
    ├── tests/                     ← 106 tests
    ├── deploy/                    ← systemd + Nginx config
    └── README.md
```

## MCP tools (16 total)

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

| Tool | Description | Min role |
|------|-------------|----------|
| `cts_search_traces` | Search audit events (7-day window) | readonly |
| `cts_get_trace_detail` | Full masked request/response body | readonly |

> Role hierarchy: **admin** ⊃ **operator** ⊃ **readonly**

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
                          │             enabled=[ecs,pipeline,cts]│
                          │           )                           │
                          └──────────────────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  Unified FastMCP  │
                          │  16 tools:        │
                          │    ecs_* (8)      │
                          │    pipeline_* (6) │
                          │    cts_* (2)      │
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
HUAWEICLOUD_SECRET_ACCESS_KEY=*** Region
HUAWEICLOUD_REGION=cn-north-4
HUAWEICLOUD_PROJECT_ID=your-project-id
CODEARTS_DEFAULT_PROJECT_ID=your-codearts-project-id

# Gateway auth mode (dev for local, jwt for production)
MCP_GATEWAY_AUTH_MODE=dev
M...n### 3. Start the gateway

```bash
./start.sh
```

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
# All services (16 tools)
huaweicloud-mcp-server

# Subset only
MCP_ENABLED_SERVICES=ecs,pipeline huaweicloud-mcp-server

# SSE mode
MCP_TRANSPORT=sse MCP_PORT=8000 huaweicloud-mcp-server
```

## Agent configuration

### Hermes Agent

**Mode A — stdio (local dev, recommended)**

`~/.hermes/config.yaml`:

```yaml
mcp_servers:
  huaweicloud:
    command: /path/to/.venv/bin/huaweicloud-mcp-server
    timeout: 120
    # Optional: enable only a subset
    # env:
    #   MCP_ENABLED_SERVICES: ecs,pipeline
```

**Mode B — SSE via gateway (production)**

```yaml
mcp_servers:
  huaweicloud:
    url: http://127.0.0.1:8080/hwc/sse
    transport: sse
    timeout: 120
    connect_timeout: 30
```

Verify:

```bash
hermes mcp test huaweicloud
#   ✓ Connected (643ms)
#   ✓ Tools discovered: 16
```

### Claude Code

`~/.claude/mcp.json` (or project-level `.claude/mcp.json`):

**stdio mode:**

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

**SSE mode (via gateway):**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "url": "http://127.0.0.1:8080/hwc/sse",
      "transport": "sse",
      "timeout": 120
    }
  }
}
```

### Claude Desktop / Cursor / Cline

`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`):

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

> **Key point**: Regardless of how many Huawei Cloud services are added, the
> Agent always configures **one** MCP server entry. New services appear as
> additional tools (`obs_*`, `rds_*`, …) without any Agent-side config change.

## Adding a new Huawei Cloud service

1. Create `huaweicloud_mcp/services/<name>/` with `make_tools(settings) → dict`
2. Add `if "<name>" in enabled` branch in `server.py:build_server()`
3. Append `"<name>"` to `build_kwargs.enabled` in `manifest.yaml`
4. Restart gateway — new tools appear automatically

**No Nginx change. No gateway code change. No Agent config change.**

## Production deployment

### JWT key pair

```bash
mcp-gateway token keygen
# or
openssl genrsa -out jwt-private.pem 2048
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
```

### Issue tokens

```bash
# Admin token (1h default)
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# Operator + readonly, custom TTL
mcp-gateway token create --sub ops-bot --roles operator,readonly \
  --private-key jwt-private.pem --ttl 7200 --tenant proj-abc

# Verify token
mcp-gateway token verify --public-key jwt-public.pem --token "eyJ..."
```

In `.env`:

```bash
MCP_GATEWAY_AUTH_MODE=jwt
M...n### systemd

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

## Selective service enable

Three override layers (low → high priority):

| Layer | Source | Example |
|-------|--------|---------|
| 1 | `manifest.yaml` `enabled` field | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` env var | `huaweicloud` |
| 3 | CLI `--enable` / `--disable` | `./start.sh --enable ecs,pipeline` |

Startup logs clearly print mounted/skipped services and skip reasons.

## Shared auth library (mcp-auth-common)

| Component | Description |
|-----------|-------------|
| `Identity` | pydantic v2 model: `sub` / `roles` / `tenant` / `iat` / `exp` |
| `AutoAuth` | Auto-detect: gateway identity → use; else synthesize dev Identity + WARN |
| `AuthStrategy` | Abstract base class |
| `require_role()` | Role check with admin ⊃ operator ⊃ readonly hierarchy |
| `set_request_scope()` / `current_scope()` | contextvar pipe for scope access without `ctx` param |

## Tests

```bash
# Unified server (152 tests)
uv run pytest huaweicloud-mcp-server/tests/ -q

# Gateway (106 tests)
uv run pytest mcp-gateway/tests/ -q

# All (258 tests)
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

| Category | Count | What it covers |
|----------|-------|----------------|
| ECS tools | 52 | list/get/power/delete/resize/confirm/job |
| Pipeline tools | 48 | list/get/run/update/toggle/confirm |
| CTS tools | 36 | search/detail + time_utils + mask_utils + 7-day window |
| Config / client | 16 | Settings validation, client factory, caching |
| Gateway auth | 9 | JWT verify + RBAC + Identity injection |
| Gateway dev mode | 10 | No JWT / loopback / open / disabled |
| Structured logging | 9 | JSON format / extra fields / audit events |
| Tool-level RBAC | 14 | Role hierarchy + 3-service auth matrix |
| Manifest override | 9 | 3-layer override + skip reasons + dedup |
| Factory mode | 9 | build_kwargs parsing + factory call + errors |
| SSE prefix regression | 1 | No double /hwc/hwc in endpoint event |
| Token CLI | 14 | keygen + create + verify + e2e round-trip |
| Combined lifespan | 4 | Multi-FastMCP mount |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | ✅ | Huawei Cloud AK (shared) |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | ✅ | Huawei Cloud SK (shared) |
| `HUAWEICLOUD_PROJECT_ID` | ✅ | IAM project ID (ECS/CTS) |
| `HUAWEICLOUD_REGION` | ✅ | Region (shared by all services) |
| `CODEARTS_DEFAULT_PROJECT_ID` | recommended | CodeArts project UUID |
| `MCP_GATEWAY_AUTH_MODE` | ✅ | Gateway auth: `jwt` / `dev` |
| `MCP_GATEWAY_HOST` | ✅ | Listen address (`127.0.0.1` for dev) |
| `MCP_GATEWAY_PORT` | optional | Listen port, default `8080` |
| `MCP_DEV_LOOPBACK_ONLY` | optional | Dev source restriction: `true` (default) / `false` |
| `MCP_GATEWAY_LOG_FORMAT` | optional | Log format: `text` (default) / `json` |
| `MCP_JWT_PUBLIC_KEY` | jwt required | RS256 public key (`file:` / `env:` / inline PEM) |
| `MCP_JWT_ISSUER` | recommended | JWT issuer, default `mcp-gateway` |
| `MCP_ENABLED_SERVICES` | optional | Service subset for standalone stdio/sse mode |
| `MCP_TRANSPORT` | optional | Standalone transport: `stdio` / `sse` / `streamable-http` |

Full list in `.env.example`.

## License

MIT
