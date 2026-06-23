# huaweicloud-mcp-server

**English** | [中文](README.md)

One MCP Server for all Huawei Cloud services. Agents connect to **one URL** and
access every enabled cloud service tool. Enable only the services you need,
secure production with JWT auth, and add new cloud services with **zero
Agent-side config change**.

**Available**: ECS (cloud servers), CodeArts Pipeline (CI/CD), CTS (audit logs)
**Coming soon**: OBS (object storage), RDS (relational DB), VPC (virtual network)…

---

## Quick start

```bash
# 1. Set credentials
export HUAWEICLOUD_ACCESS_KEY_ID=your_ak
export HUAWEICLOUD_SECRET_ACCESS_KEY=*** HUAWEICLOUD_REGION=af-south-1
export HUAWEICLOUD_PROJECT_ID=your_project_id   # required for ECS/CTS
export CODEARTS_DEFAULT_PROJECT_ID=your_pipeline_project_id  # Pipeline fallback

# 2a. stdio mode (all services) — for local AI clients
uv run huaweicloud-mcp-server

# 2b. SSE / Streamable-HTTP mode — for remote clients
MCP_TRANSPORT=sse MCP_PORT=8000 uv run huaweicloud-mcp-server

# 2c. Subset of services only
MCP_ENABLED_SERVICES=ecs,pipeline uv run huaweicloud-mcp-server
```

---

## Agent configuration

### Hermes Agent

**Mode A — stdio (local dev, recommended)**

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  huaweicloud:
    command: /path/to/.venv/bin/huaweicloud-mcp-server
    timeout: 120
    # Optional: enable only a subset of services
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

Add to `~/.claude/mcp.json` (or project-level `.claude/mcp.json`):

**stdio mode (local dev):**

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

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
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

> **Key point**: Regardless of how many Huawei Cloud services are added in the
> future, the Agent always configures **one** MCP server entry. New services
> appear as additional tools (`obs_*`, `rds_*`, …) without any Agent-side
> config change.

---

## Architecture

```
huaweicloud_mcp/
├── __init__.py
├── config.py          # Unified Settings dataclass + load_settings()
├── client.py          # SDK client factory: get_client("ecs", settings) — lru_cached
├── errors.py          # ToolError, wrap_tool decorator, PendingActions (two-phase commit)
├── logging_setup.py   # SecretMaskingFilter + setup_logging()
├── server.py          # build_server(enabled={"ecs","pipeline","cts"}) → FastMCP
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
```

### Shared infrastructure

| Module | Purpose |
|---|---|
| `config.py` | Single `Settings` dataclass — AK/SK/region/project_id/timezone. `load_settings()` reads from env, validates required vars, exits fast on missing. |
| `client.py` | `get_client(service, settings)` → cached SDK client. One factory for ECS, Pipeline, CTS clients with shared HttpConfig (timeout, retries). |
| `errors.py` | `ToolError` exception + `wrap_tool` decorator that catches SDK errors, normalizes them to `{ok: false, error: {...}}` envelopes, and logs structured events. `PendingActions` implements the two-phase commit for destructive ops. |
| `logging_setup.py` | `SecretMaskingFilter` redacts AK/SK in log output. `setup_logging()` configures stderr-only (stdio-safe) or file logging. |

---

## Tools (16 total)

### ECS (8 tools)

| Tool | Description | Destructive |
|---|---|---|
| `ecs_list_servers` | List ECS servers with filters (name, status, IP, tags) | No |
| `ecs_get_server` | Get full server detail or lightweight status snapshot | No |
| `ecs_list_flavors` | List available instance types (optionally by AZ) | No |
| `ecs_power_action` | Batch start / stop / reboot | Stop, Reboot (two-phase) |
| `ecs_delete_server` | Permanently delete servers (optionally EIP + volumes) | Yes (two-phase) |
| `ecs_resize_server` | Change server flavor (vCPU/RAM) | Yes (two-phase) |
| `ecs_confirm_destructive` | Execute a pending destructive op after user approval | — |
| `ecs_get_job_status` | Poll async job status (start/stop/reboot/delete/resize) | No |

### CodeArts Pipeline (6 tools)

| Tool | Description | Destructive |
|---|---|---|
| `pipeline_list` | List pipelines + latest-run status with filters | No |
| `pipeline_get_detail` | Full pipeline detail (sources, variables, schedules, triggers, definition) | No |
| `pipeline_run` | Trigger a pipeline run with optional branch/variables override | No |
| `pipeline_set_status` | Enable or disable a pipeline | Disable (two-phase) |
| `pipeline_update_info` | Update default branch and/or first-stage pre-task | Yes (two-phase) |
| `pipeline_confirm_destructive` | Execute a pending destructive op after user approval | — |

### CTS (2 tools)

| Tool | Description | Destructive |
|---|---|---|
| `cts_search_traces` | Search audit events by time range + filters (7-day window) | No |
| `cts_get_trace_detail` | Get full masked request/response body of a single trace | No |

---

## Two-phase commit (destructive operations)

Destructive tools (stop, reboot, delete, resize, disable pipeline, update pipeline)
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

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY_ID` | yes | | Access key ID |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | yes | | Secret access key |
| `HUAWEICLOUD_REGION` | yes | | Region, e.g. `af-south-1` |
| `HUAWEICLOUD_PROJECT_ID` | ECS/CTS | | Project UUID |
| `CODEARTS_DEFAULT_PROJECT_ID` | Pipeline | `=HUAWEICLOUD_PROJECT_ID` | Pipeline project fallback |
| `CTS_DEFAULT_TIMEZONE` | no | `Asia/Shanghai` | CTS time parsing timezone |
| `HUAWEICLOUD_MCP_LOG_LEVEL` | no | `INFO` | Log level |
| `HUAWEICLOUD_MCP_LOG_FILE` | no | stderr | Log file path |
| `HUAWEICLOUD_MCP_HTTP_TIMEOUT` | no | `30` | SDK HTTP timeout (seconds) |
| `HUAWEICLOUD_MCP_NETWORK_RETRIES` | no | `2` | SDK retry count |
| `MCP_TRANSPORT` | no | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | no | `127.0.0.1` | SSE/HTTP bind host |
| `MCP_PORT` | no | `8000` | SSE/HTTP bind port |
| `MCP_ENABLED_SERVICES` | no | `ecs,pipeline,cts` | Comma-separated service subset |

---

## Deployment modes

### 1. Standalone stdio (local AI clients)

```bash
uv run huaweicloud-mcp-server
```

All three services are mounted by default. Use `MCP_ENABLED_SERVICES` to
register a subset.

### 2. Standalone SSE / HTTP (remote clients)

```bash
MCP_TRANSPORT=sse MCP_PORT=8000 uv run huaweicloud-mcp-server
```

Endpoints:
- `GET /sse` — SSE event stream (with 15s keep-alive frames)
- `POST /messages/?session_id=...` — client → server messages

For Streamable-HTTP:
```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8000 uv run huaweicloud-mcp-server
```

### 3. MCP Gateway (Strategy 1: single URL, single mount)

The unified server is mounted at `/hwc` via the `mcp-gateway`. Agents connect
to **one URL** and receive all enabled tools in a single list.

`manifest.yaml`:

```yaml
services:
  - name: huaweicloud
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, pipeline, cts]
    mount_path: /hwc
    required_roles: [readonly, operator, admin]
```

The gateway calls `huaweicloud_mcp.build_server(enabled=["ecs","pipeline","cts"])`
once at startup. Tool names are service-prefixed (`ecs_*`, `pipeline_*`,
`cts_*`) so there is no collision.

The gateway adds:
- JWT authentication (issuer, audience, public key)
- Role-based tool authorization (readonly / operator / admin)
- Structured access logging (logfmt or JSON)

**Adding a new cloud service** (Agent-side 0 config change):

1. Add `huaweicloud_mcp/services/<name>/` with `make_tools(settings) → dict`
2. Add the `if "<name>" in enabled` branch in `server.py:build_server()`
3. Append `"<name>"` to `build_kwargs.enabled` in `manifest.yaml`
4. Restart gateway — tools appear automatically

---

## Development

### Install

```bash
# From workspace root
uv sync
```

### Run tests

```bash
# Unified server tests (152 tests)
uv run pytest huaweicloud-mcp-server/tests/ -q

# Gateway tests (106 tests)
uv run pytest mcp-gateway/tests/ -q

# Both (258 tests)
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

### Test structure

Tests are organized by service with a shared `conftest.py` providing:
- `_isolate_env` (autouse) — strips all cloud env vars between tests
- `settings` / `ecs_settings` / `pipeline_settings` / `cts_settings` — pre-configured Settings fixtures
- `mock_ecs_client` / `mock_pipeline_client` / `mock_cts_client` — MagicMock SDK clients injected via monkeypatch

CTS tests additionally test utility modules directly:
- `test_cts_time_utils.py` — time parsing (human strings, ISO-8601, relative)
- `test_cts_mask_utils.py` — sensitive value masking
- `test_cts_seven_day.py` — 7-day window enforcement

---

## Migration from standalone packages

The three original packages (`ecs-mcp-server`, `codearts-pipeline-mcp-server`,
`cts-mcp-server`) have been replaced by the unified package:

| Before (3 packages) | After (1 package) |
|---|---|
| `ecs_mcp_server.config.Settings` | `huaweicloud_mcp.config.Settings` |
| `ecs_mcp_server.tools.query` | `huaweicloud_mcp.services.ecs.tools.query` |
| `pipeline_mcp_server.X` | `huaweicloud_mcp.services.pipeline.X` |
| `cts_mcp_server.X` | `huaweicloud_mcp.services.cts.X` |
| 3 × separate AK/SK config | 1 × unified Settings |
| 3 × duplicate error wrapping | 1 × shared `wrap_tool` + `ToolError` |
| 3 × separate client factories | 1 × `get_client(service, settings)` |
| 3 × manifest entries with 3 modules | 1 × manifest entry with `build_kwargs` |

### Import depth convention

- Top-level modules (`config`, `errors`, `client`, `logging_setup`): imported via relative `.` or `..`
- Service-level modules (`models`, `serializers`, `make_tools`): use `...` (3 dots) to reach top-level package
- Tool modules (under `services/{svc}/tools/`): use `....` (4 dots) to reach top-level package

---

## Project layout (workspace)

```
huaweicloud-mcp-server/          # ← workspace root
├── pyproject.toml               # uv workspace definition
├── manifest.yaml                # MCP Gateway service manifest (Strategy 1)
├── huaweicloud-mcp-server/      # ← unified package (this README)
│   ├── pyproject.toml
│   ├── src/huaweicloud_mcp/
│   └── tests/
├── mcp-auth-common/             # Shared auth strategy (gateway + standalone)
└── mcp-gateway/                 # Starlette gateway (JWT auth, single mount /hwc)
    ├── src/mcp_gateway/
    └── tests/
```
