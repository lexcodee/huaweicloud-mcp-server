# CodeArts Pipeline MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that wraps
the **Huawei Cloud CodeArts Pipeline** API as 6 LLM-callable tools. Designed
to slot into the same Hermes / Claude Desktop gateway as the ECS MCP server
in this org — same env-var conventions, same `{ok, data|error}` response
envelope, same secret-masking and confirm-gating policies.

```
+--------------------+     stdio JSON-RPC      +------------------------+
| Hermes / Claude /  |  <-------------------+  |  codearts-pipeline-    |
| Slack agent        |                         |  mcp-server            |
+--------------------+                         +-----------+------------+
                                                           |
                                                           v
                                          huaweicloudsdkcodeartspipeline
                                                           |
                                                           v
                                       https://codearts-pipeline.<region>.
                                              myhuaweicloud.com
```

## Tools at a glance

| Tool                  | API                | Purpose                                       | Destructive? |
|-----------------------|--------------------|-----------------------------------------------|--------------|
| `pipeline_list`       | ListPipelines      | List pipelines + latest-run snapshot          | No           |
| `pipeline_get_detail` | ShowPipelineDetail | Full config (sources, definition, schedules…) | No           |
| `pipeline_run`        | RunPipeline        | Trigger a run (default or branch override)    | No           |
| `pipeline_update_info`| UpdatePipelineInfo | Change `default_branch` and/or first-stage `pre.task` | ⚠ Yes (full PUT) — needs `confirm=true` |
| `pipeline_set_status` | Enable/DisablePipeline | Toggle ban state (`status="enabled"\|"disabled"`) | ⚠ Yes when `status="disabled"` — needs `confirm=true` |

Every tool returns the same envelope:

```json
{"ok": true,  "data": {...}}
{"ok": false, "error": {"code": "...", "message": "...", "request_id": "...", "status_code": 4xx}}
```

## Install

Python 3.10 or newer.

```bash
git clone <this repo>
cd codearts-pipeline-mcp-server
pip install -e ".[dev]"        # editable + dev tooling (pytest etc.)
# or:
uv sync
```

The console script `codearts-pipeline-mcp-server` is installed on `PATH`.

## Configure

Copy `.env.example` to `.env` (or set the variables in your shell / process
manager) and fill in real values:

| Variable                          | Required? | Description |
|-----------------------------------|-----------|-------------|
| `HUAWEICLOUD_ACCESS_KEY_ID`       | yes       | IAM AK |
| `HUAWEICLOUD_SECRET_ACCESS_KEY`   | yes       | IAM SK |
| `CODEARTS_REGION`                 | yes       | CodeArts Pipeline region id (e.g. `af-south-1`, `cn-north-4`). **NOT interchangeable with `HUAWEICLOUD_REGION`** — they are different services with different region catalogues. |
| `CODEARTS_DEFAULT_PROJECT_ID`     | no        | Default CodeArts project UUID. Used when a tool call omits `project_id`. |
| `PIPELINE_MCP_LOG_LEVEL`          | no        | `INFO` (default) / `WARNING` / `DEBUG` |
| `PIPELINE_MCP_LOG_FILE`           | no        | Optional rotating file log. stderr is always used. |
| `PIPELINE_MCP_HTTP_TIMEOUT`       | no        | Per-request timeout in seconds (default `30`) |
| `PIPELINE_MCP_NETWORK_RETRIES`    | no        | Network-error retries (default `2`; business errors are never retried) |

Required IAM permissions (CodeArts uses a two-layer model):

1. The IAM identity (or agency) needs the policy
   `DEVPIPE::FullAccess` (or a finer-grained equivalent).
2. The same identity must be a **member of the CodeArts project** whose
   pipelines you want to manage. Without project membership,
   `pipeline_list` returns `total: 0` and `pipeline_get_detail` returns
   `DEVPIPE.00011412`.

The server fails fast (exit code `2`) when any required variable is missing.

## Run as a standalone process

```bash
codearts-pipeline-mcp-server
# stdio JSON-RPC on stdin/stdout, logs on stderr
```

The server logs every tool call with a per-call id, duration, and outcome,
and masks AK/SK / random base64 strings before emitting any log line.

## Hermes Agent integration

```bash
hermes config set "mcp_servers.codearts-pipeline.command" \
    /path/to/scripts/run-with-env.sh
hermes config set "mcp_servers.codearts-pipeline.timeout" 60
hermes config set "mcp_servers.codearts-pipeline.connect_timeout" 30

hermes mcp test codearts-pipeline   # connects, lists tools, prints latency
```

`scripts/run-with-env.sh` (recommended — keeps AK/SK out of `~/.hermes/config.yaml`):

```bash
#!/usr/bin/env bash
set -e
ENV_FILE="${CODEARTS_PIPELINE_MCP_ENV_FILE:-$HOME/.huaweicloud/codearts.env}"
[[ -f "$ENV_FILE" ]] && { set -a; source "$ENV_FILE"; set +a; }
exec /usr/local/bin/codearts-pipeline-mcp-server "$@"
```

## Claude Desktop integration

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "codearts-pipeline": {
      "command": "codearts-pipeline-mcp-server",
      "env": {
        "HUAWEICLOUD_ACCESS_KEY_ID": "AKIDxxxxxxxxxxxxxxxx",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "SKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "CODEARTS_REGION": "af-south-1",
        "CODEARTS_DEFAULT_PROJECT_ID": "ddb5e3259e81494f9d083c917e173e5b"
      }
    }
  }
}
```
Restart Claude Desktop after adding the entry. The 6 tools should appear
under "🔌 Tools".

## Tool examples

### List pipelines

```json
{"name": "pipeline_list", "arguments": {}}
```

```json
{"name": "pipeline_list", "arguments": {"name": "Taifa", "status": ["FAILED"], "limit": 5}}
```

### Pipeline detail

```json
{"name": "pipeline_get_detail",
 "arguments": {"pipeline_id": "c2b549113a92491e866d1305aef896ed"}}
```

### Trigger a run (default branch)

```json
{"name": "pipeline_run",
 "arguments": {"pipeline_id": "c2b549113a92491e866d1305aef896ed"}}
```

### Trigger a run on a different branch

```json
{"name": "pipeline_run",
 "arguments": {
   "pipeline_id": "c2b549113a92491e866d1305aef896ed",
   "sources": [{"params": {"default_branch": "feature/login-flow"}}]
 }}
```

### Update only the default branch

```json
{"name": "pipeline_update_info",
 "arguments": {
   "pipeline_id": "c2b549113a92491e866d1305aef896ed",
   "new_default_branch": "release/2.0",
   "confirm": true
 }}
```

For multi-source pipelines pass `source_alias`:

```json
{"name": "pipeline_update_info",
 "arguments": {
   "pipeline_id": "...",
   "source_alias": "primary",
   "new_default_branch": "release/2.0",
   "confirm": true
 }}
```

### Switch the first-stage trigger from auto to manual

```json
{"name": "pipeline_update_info",
 "arguments": {
   "pipeline_id": "...",
   "new_pre_task": "official_devcloud_manualTrigger",
   "confirm": true
 }}
```

Allowed values:

| `new_pre_task`                       | meaning                          |
|--------------------------------------|----------------------------------|
| `official_devcloud_manualTrigger`    | first stage requires manual click|
| `official_devcloud_autoTrigger`      | first stage starts automatically |

### Disable / re-enable

```json
{"name": "pipeline_set_status",
 "arguments": {"pipeline_id": "...", "status": "disabled", "confirm": true}}
```

```json
{"name": "pipeline_set_status",
 "arguments": {"pipeline_id": "...", "status": "enabled"}}
```

## Safety policies

- **`pipeline_update_info` and `pipeline_set_status` with
  `status="disabled"` require `confirm=true`.**
  The `wrap_tool` decorator returns `CONFIRM_REQUIRED` *before* any HTTPS
  request, so a forgetful LLM cannot accidentally trigger a destructive
  call.
- **`pipeline_update_info` is a full-record PUT.** The tool first calls
  `ShowPipelineDetail`, mutates only the requested fields in memory
  (`default_branch` and/or `definition.stages[0].pre[].task`), then sends
  the merged record back. There is a small race window for concurrent
  edits, surfaced in the tool description so the LLM can warn the user.
  A diff log is emitted on every successful call:
  ```
  pipeline_update_info pipeline_id=... project_id=...
    definition_hash 1234abcd56ef -> 78900badc0ff;
    before_summary={...} after_summary={...};
    changes={"pre_task": {...}}
  ```
- **AK/SK never appear in logs or tool responses.** A `logging.Filter`
  matches both exact-string secrets (loaded from settings) and heuristic
  AK/SK shapes; `Settings.masked()` is what gets logged at startup.
- **Timeouts and retries** — every call uses `PIPELINE_MCP_HTTP_TIMEOUT`
  (default 30 s); the SDK retries network failures up to
  `PIPELINE_MCP_NETWORK_RETRIES` times (default 2). Business errors
  (4xx/5xx) are never retried.

## Testing

```bash
PYTHONPATH=src pytest tests/        # 34 unit tests, < 1 s
python3 tests/smoke_stdio.py        # full stdio handshake with fake creds
```

The most important regression suite is `tests/test_update_info_merge_logic.py`:
it asserts that after `pipeline_update_info` mutates a single field (default
branch or pre-task), the PUT request body still carries every other field
verbatim from `ShowPipelineDetail` (variables, schedules, triggers,
manifest_version, group_id, …). Drift here would cause silent data loss
on production pipelines.

## Project layout

```
codearts-pipeline-mcp-server/
├── pyproject.toml
├── README.md
├── TEST_REPORT.md
├── .env.example
├── src/
│   └── pipeline_mcp_server/
│       ├── __init__.py
│       ├── server.py              # FastMCP entrypoint + main()
│       ├── config.py              # env loading, fail-fast, masked()
│       ├── client.py              # cached SDK client + raw-PUT helper
│       ├── logging_setup.py       # stderr + secret-masking filter
│       ├── errors.py              # ToolError + @wrap_tool + require_confirm
│       ├── definition_utils.py    # safe parse / mutate / dump of `definition`
│       ├── models.py              # Pydantic input models for every tool
│       ├── serializers.py         # SDK obj -> compact LLM-friendly dict
│       └── tools/
│           ├── query.py           # pipeline_list, pipeline_get_detail
│           ├── execution.py       # pipeline_run
│           ├── update.py          # pipeline_update_info (read-modify-write)
│           └── lifecycle.py       # pipeline_set_status
└── tests/
    ├── conftest.py
    ├── test_config_and_logging.py
    ├── test_definition_utils.py
    ├── test_query_tools.py
    ├── test_run_and_lifecycle.py
    ├── test_update_info_merge_logic.py
    └── smoke_stdio.py
```
