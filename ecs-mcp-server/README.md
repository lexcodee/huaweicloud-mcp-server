# Huawei Cloud ECS MCP Server

A Model Context Protocol (MCP) server that exposes Huawei Cloud ECS (Elastic
Cloud Server) lifecycle operations as tools, callable from any MCP-compatible
client — Hermes Agent, Claude Desktop, Claude Code, etc.

It wraps the official Huawei Cloud Python SDK
(`huaweicloudsdkcore` + `huaweicloudsdkecs`) and exposes 10 typed tools.
Authentication is via Access Key / Secret Key (AK/SK), read from environment
variables — no credentials in code.

## Features

- 10 ECS tools, named `ecs_<verb>_<noun>`
- Pydantic input validation — bad inputs are rejected before they reach
  Huawei Cloud
- Compact, JSON-friendly responses — no SDK metadata noise
- Destructive operations (`stop` / `reboot` / `delete` / `resize`) are gated
  behind an explicit `confirm=true` parameter
- Structured logging to stderr with AK/SK masking; optional file output
- Standard error envelope `{ok: false, error: {code, message, request_id}}`
  for every tool, so the LLM can explain failures to the user

## Tools

| Tool | Type | Confirm | Description |
|---|---|---|---|
| `ecs_list_servers` | query | – | Paginated server list with filters |
| `ecs_get_server` | query | – | Inspect one server. `detail_level="full"` (default) returns rich detail; `"status"` returns a lightweight power snapshot |
| `ecs_list_flavors` | query | – | Available flavors (instance types) |
| `ecs_power_action` | lifecycle | ✅ for stop/reboot | Batch power op. `action="start" \| "stop" \| "reboot"`; SOFT/HARD via `type` |
| `ecs_delete_server` | lifecycle | ✅ | Delete (irreversible) |
| `ecs_resize_server` | lifecycle | ✅ | Change flavor (vCPU/RAM) |
| `ecs_get_job_status` | job | – | Poll async job result |

All write tools are asynchronous on Huawei Cloud's side and return a
`job_id`; use `ecs_get_job_status` to poll completion.

## Install

```bash
git clone <this repo>
cd huaweicloud-ecs-mcp-server

# Option A: pip
pip install -e .

# Option B: uv
uv pip install -e .
```

Python 3.10+ required.

## Configure

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
# then edit .env
```

| Variable | Required | Default |
|---|---|---|
| `HUAWEICLOUD_ACCESS_KEY_ID` | yes | – |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | yes | – |
| `HUAWEICLOUD_PROJECT_ID` | no | `15f2d47addb14784b82eb910447250a9` |
| `HUAWEICLOUD_REGION` | no | `af-south-1` |
| `ECS_MCP_LOG_FILE` | no | (stderr only) |
| `ECS_MCP_LOG_LEVEL` | no | `INFO` |

The server validates required vars at startup and exits with code 2 if any
are missing.

## Run (stdio)

```bash
ecs-mcp-server
# or
python -m ecs_mcp_server.server
```

The server speaks JSON-RPC on stdin/stdout. Logs go to stderr.

## Claude Desktop integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "huaweicloud-ecs": {
      "command": "ecs-mcp-server",
      "env": {
        "HUAWEICLOUD_ACCESS_KEY_ID": "your-ak",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "your-sk",
        "HUAWEICLOUD_PROJECT_ID": "15f2d47addb14784b82eb910447250a9",
        "HUAWEICLOUD_REGION": "af-south-1"
      }
    }
  }
}
```

If `ecs-mcp-server` isn't on your `PATH`, use the absolute Python path:

```json
"command": "/path/to/python",
"args": ["-m", "ecs_mcp_server.server"]
```

## Hermes Agent integration

Edit `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  huaweicloud-ecs:
    command: ecs-mcp-server
    env:
      HUAWEICLOUD_ACCESS_KEY_ID: your-ak
      HUAWEICLOUD_SECRET_ACCESS_KEY: your-sk
      HUAWEICLOUD_PROJECT_ID: 15f2d47addb14784b82eb910447250a9
      HUAWEICLOUD_REGION: af-south-1
```

## Example tool calls

List running servers:
```json
{"name": "ecs_list_servers", "arguments": {"status": "ACTIVE", "limit": 20}}
```

Stop two servers (note `confirm`):
```json
{"name": "ecs_stop_server",
 "arguments": {"server_ids": ["uuid-a", "uuid-b"], "type": "SOFT", "confirm": true}}
```

Poll job:
```json
{"name": "ecs_get_job_status", "arguments": {"job_id": "ff80...e1"}}
```

## Response shape

Every tool returns one of:

```json
{"ok": true, "data": { ... }}
{"ok": false, "error": {"code": "...", "message": "...", "request_id": "..."}}
```

## Safety notes

- `confirm=true` is required for `stop`, `reboot`, `delete`, `resize`. The
  server REFUSES the call otherwise.
- `ecs_delete_server` with `delete_volume=true` permanently deletes data
  disks. The LLM should always echo the target server ids back to the user
  for explicit confirmation before passing `confirm=true`.
- AK / SK never appear in logs — the secret-masking filter scrubs both
  known values and heuristic AK/SK shapes.

## Development & testing

```bash
pip install -e ".[dev]"
PYTHONPATH=src pytest tests/
```

Tests use `unittest.mock` to replace the Huawei Cloud client; no real
network calls are made. A separate stdio smoke test boots the actual server
and walks the MCP handshake:

```bash
python tests/smoke_stdio.py
```

## Project layout

```
src/ecs_mcp_server/
  server.py          # FastMCP entrypoint; registers tools
  config.py          # env loading + secret masking
  client.py          # cached EcsClient builder
  logging_setup.py   # stderr/file logging + secret filter
  errors.py          # ToolError + @wrap_tool decorator
  models.py          # Pydantic input models
  serializers.py     # SDK obj -> compact dict
  tools/
    query.py         # 4 read-only tools
    lifecycle.py     # 5 write tools
    job.py           # 1 polling tool
tests/
  conftest.py        # mock client fixture
  test_*.py
  smoke_stdio.py     # full MCP-protocol smoke test
```

## License

MIT
