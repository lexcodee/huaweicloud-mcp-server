# Architecture

## Project structure

```
huaweicloud-mcp-server/          # ← workspace root
├── start.sh                       ← Start script (loads .env + starts gateway)
├── start.ps1                      ← Windows equivalent (PowerShell)
├── .env                           ← Unified env vars (AK/SK + JWT + config)
├── .env.example                   ← Full template
├── manifest.yaml                  ← Service topology (single mount /hwc)
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
│           ├── cce/               ← 6 tools (query clusters/nodes/nodepools, update nodepool, get_job)
│           ├── lts/               ← 6 tools (query log resources, search logs, alarm rules/history)
│           ├── ces/               ← 6 tools (list metrics, get metric data, alarm rules/history, resource groups, events)
│           ├── vpc/               ← 19 tools (VPC/subnet/peering/route-table/EIP/flow-log query, SG audit, EIP/route write ops)
│           └── rds/               ← 10 tools (instance query, error/slow logs, DB resources, backups, metrics, parameter groups, replicas, security audit)
│
├── mcp-auth-common/               ← Shared auth (Identity / AutoAuth / require_role)
│   └── src/mcp_auth_common/
│
└── mcp-gateway/                   ← ASGI gateway (Starlette Mount + JWT middleware)
    ├── src/mcp_gateway/
    └── deploy/                    ← systemd + Nginx config
```

## Shared infrastructure

| Module | Purpose |
|--------|---------|
| `config.py` | Single `Settings` dataclass — AK/SK/region/project_id/timezone. `load_settings()` reads from env, validates required vars, exits fast on missing. |
| `client.py` | `get_client(service, settings)` → cached SDK client. One factory for ECS, Pipeline, CTS, CCE, LTS, CES, VPC, EIP, RDS clients with shared HttpConfig (timeout, retries). |
| `errors.py` | `ToolError` exception + `wrap_tool` decorator that catches SDK errors, normalizes them to `{ok: false, error: {...}}` envelopes, and logs structured events. `PendingActions` implements the two-phase commit for destructive ops. |
| `logging_setup.py` | `SecretMaskingFilter` redacts AK/SK in log output. `setup_logging()` configures stderr-only (stdio-safe) or file logging. |

## Shared auth library (mcp-auth-common)

| Component | Description |
|-----------|-------------|
| `Identity` | pydantic v2 model: `sub` / `roles` / `tenant` / `iat` / `exp` |
| `AutoAuth` | Auto-detect: gateway identity → use; else synthesize dev Identity + WARN |
| `AuthStrategy` | Abstract base class |
| `require_role()` | Role check with admin ⊃ operator ⊃ readonly hierarchy |
| `set_request_scope()` / `current_scope()` | contextvar pipe for scope access without `ctx` param |

## Test structure

```bash
# Unified server
uv run pytest huaweicloud-mcp-server/tests/ -q

# Gateway
uv run pytest mcp-gateway/tests/ -q

# All
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

| Category | Count | What it covers |
|----------|-------|----------------|
| ECS tools | 52 | list/get/power/delete/resize/confirm/job |
| Pipeline tools | 48 | list/get/run/update/toggle/confirm |
| CTS tools | 36 | search/detail + time_utils + mask_utils + 7-day window |
| CCE tools | 30 | query clusters/nodes/nodepools + update nodepool + get_job + confirm + DefaultPool rejection |
| LTS tools | 30 | discovery + search + alarm rules/history + histogram + context |
| CES tools | 16 | list metrics + get metric data + alarm rules/histories + resource groups + event data |
| VPC tools | 33 | SG query/audit + network describe + EIP associate/disassociate + route add/delete + flow-log query + confirm |
| RDS tools | 24 | describe_instances + get_db_logs (error+slow) + list_db_resources + list_backups + get_instance_metrics + describe_parameter_group + list_replicas + create_manual_backup (two-phase) + audit_instance_security |
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
