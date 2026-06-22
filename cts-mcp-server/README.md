# Huawei Cloud CTS MCP Server

MCP Server for querying Huawei Cloud **CTS (Cloud Trace Service)** audit events — "who did what to which resource, and when?" — via natural language.

Part of the **Hermes Agent** operations suite alongside the [ECS MCP Server](../ecs-mcp-server/) and [CodeArts Pipeline MCP Server](../codearts-pipeline-mcp-server/).

## Features

- **`cts_search_traces`** — Search audit events by time range, cloud service, operating user, event severity, resource, and more. Supports cursor-based pagination and auto-pagination with result caps.
- **`cts_get_trace_detail`** — Retrieve the full (masked) request/response body of a specific audit event.
- **7-day window enforcement** — The CTS ListTraces API only retains 7 days of data. This tool validates the time range *before* issuing any SDK call and returns a clear error if the range is too old.
- **Sensitive-value masking** — Passwords, secrets, tokens, access keys, and credentials in request/response bodies are automatically replaced with `***MASKED***`.
- **Flexible time input** — Accepts ISO8601 (`2026-06-20T22:00:00+08:00`), local format (`2026-06-20 22:00:00`), and relative times (`-1h`, `-2d`).

## ⚠️ Important CTS Limitations

| Limitation | Detail |
|---|---|
| **7-day window** | ListTraces only returns events from the last 7 days. Older events must be retrieved from the OBS bucket configured on the CTS tracker. |
| **Cursor pagination** | Uses `marker`-based cursor pagination, not offset. Pass `next_marker` from a previous response to get the next page. |
| **13-digit ms timestamps** | The API uses millisecond-precision UTC timestamps. This tool converts human-readable times automatically. |
| **trace_type required** | Must be `system` (management events, default) or `data` (data events). Most filters only work with `system`. |
| **trace_id overrides** | When `trace_id` is specified, all other filters are ignored by the API. |

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Huawei Cloud AK/SK with CTS read permissions

### Installation

```bash
cd cts-mcp-server
uv pip install -e .
```

### Environment Variables

All variables are read from the shared `../../.env` file (or from the process environment). CTS reuses the same credentials as the sibling MCP servers:

| Variable | Required | Default | Description |
|---|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY_ID` | ✅ | — | Huawei Cloud AK |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | ✅ | — | Huawei Cloud SK |
| `HUAWEICLOUD_PROJECT_ID` | ✅ | — | **Project ID** — CTS is a project-scoped service; this MUST be set and is passed to `BasicCredentials` for correct request signing |
| `HUAWEICLOUD_REGION` | ✅ | — | Region ID (e.g. `af-south-1`, `cn-north-4`) |
| `CTS_DEFAULT_TIMEZONE` | — | `Asia/Shanghai` | Timezone for interpreting naive datetime strings |
| `CTS_MCP_LOG_FILE` | — | — | Optional log file path |
| `CTS_MCP_LOG_LEVEL` | — | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |

### Running

```bash
# stdio transport (default, for Claude Desktop / Hermes)
cts-mcp-server

# SSE transport (local testing)
MCP_TRANSPORT=sse MCP_PORT=8000 cts-mcp-server

# With env file wrapper
./scripts/run-with-env.sh
```

## Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "huaweicloud-cts": {
      "command": "cts-mcp-server",
      "env": {
        "HUAWEICLOUD_ACCESS_KEY_ID": "AKIDxxxxxxxxxxxxxxxx",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "SKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "HUAWEICLOUD_PROJECT_ID": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "HUAWEICLOUD_REGION": "af-south-1",
        "CTS_DEFAULT_TIMEZONE": "Asia/Shanghai"
      }
    }
  }
}
```

Or use the shared `.env` file with the wrapper script:

```json
{
  "mcpServers": {
    "huaweicloud-cts": {
      "command": "./cts-mcp-server/scripts/run-with-env.sh"
    }
  }
}
```

## Example Queries

### Search by time + service
> "查一下昨晚 10 点到 12 点 ECS 相关的操作记录"

```
cts_search_traces(
  start_time="2026-06-20 22:00:00",
  end_time="2026-06-21 00:00:00",
  service_type="ECS"
)
```

### Search by user
> "看看张三这个账号最近有没有删除过 OBS 桶"

```
cts_search_traces(
  start_time="-7d",
  user="zhangsan",
  service_type="OBS",
  trace_name="deleteBucket",
  auto_paginate=True,
  max_results=200
)
```

### Search by event severity
> "最近有没有等级是 incident 的审计事件"

```
cts_search_traces(
  start_time="-1d",
  trace_rating="incident",
  auto_paginate=True
)
```

### Get full event detail
> "这条事件的完整请求内容是什么"

```
cts_get_trace_detail(trace_id="TR-xxxx-xxxx")
```

### Paginate through results
```
# First page
result = cts_search_traces(start_time="-1h", limit=50)

# Next page
cts_search_traces(start_time="-1h", limit=50, next_marker=result["next_marker"])
```

## Architecture

```
src/cts_mcp_server/
├── server.py          # FastMCP entrypoint + transport selection
├── config.py          # Env var loading & validation
├── client.py          # CtsClient singleton (project_id injected!)
├── errors.py          # Unified error handling (wrap_tool decorator)
├── logging_setup.py   # Secret-masking log filter
├── models.py          # Pydantic input models + time-range validation
├── time_utils.py      # Human time ↔ 13-digit ms conversion
├── mask_utils.py      # Sensitive-value masking (password, secret, token…)
├── serializers.py     # SDK Traces → trimmed/full dict mapping
└── tools/
    ├── search.py      # cts_search_traces
    └── detail.py      # cts_get_trace_detail
```

## License

MIT
