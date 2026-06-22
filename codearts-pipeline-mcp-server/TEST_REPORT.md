# Test Report — codearts-pipeline-mcp-server

Date: 2026-06-21
Python: 3.10.12
SDK: huaweicloudsdkcodeartspipeline (verified locally)
Test runner: pytest 9.1.1

> NOTE: Later on 2026-06-21 the `pipeline_enable` / `pipeline_disable`
> pair was merged into a single `pipeline_set_status(status="enabled"|"disabled")`
> tool to shrink the MCP startup context. The numbers below predate that
> merge; the consolidated suite still passes (29 tests). See README.md
> for the current tool list.

## Summary

| Suite                                        | Tests | Pass | Notes |
|----------------------------------------------|-------|------|-------|
| tests/test_config_and_logging.py             | 4     | 4    | Fail-fast on missing env vars; secret masking on stderr/file |
| tests/test_definition_utils.py               | 14    | 14   | JSON-string parse/mutate/dump invariants; allow-list enforcement |
| tests/test_query_tools.py                    | 4     | 4    | Compact list envelope; `definition` decoded; project_id resolution |
| tests/test_run_and_lifecycle.py              | 5     | 5    | Default-config run; branch override; ban/unban URI routing; confirm gate |
| tests/test_update_info_merge_logic.py        | 7     | 7    | **Read-modify-write merge correctness — see below** |
| tests/smoke_stdio.py (E2E stdio handshake)   | 1     | 1    | All 6 tools advertised, schemas non-empty |
| **Total**                                    | **35**| **35** | All green |

Run command:

```bash
PYTHONPATH=src pytest tests/        # 34 in 0.22 s
python3 tests/smoke_stdio.py        # < 1 s
```

## `pipeline_update_info` — "read-modify-write" verification

The CodeArts `UpdatePipelineInfo` API is a full **PUT replacement**. Any
field omitted from the request body is reset to empty on the server. The
tool therefore must:

1. fetch the full current configuration via `ShowPipelineDetail`,
2. mutate **only** the field(s) the caller passed,
3. PUT the merged record back unchanged in every other respect.

`tests/test_update_info_merge_logic.py` proves the merge is correct by
intercepting the SDK call (`mock_client.update_pipeline_info`), pulling
the captured `PipelineDTO` body, and asserting field-by-field that:

| Aspect                        | Result |
|-------------------------------|--------|
| target field flipped (default_branch) | ✅ `main` → `release/2.0` |
| target field flipped (definition.stages[0].pre[].task) | ✅ `auto` → `manual` |
| `name` preserved              | ✅ `taifa-dev` round-tripped |
| `is_publish` preserved        | ✅ `false` round-tripped |
| `manifest_version` preserved  | ✅ `3.0` round-tripped |
| `description` preserved       | ✅ `dev pipeline` round-tripped |
| `group_id` preserved          | ✅ `grp-1` round-tripped |
| `definition` byte-identical when no pre_task change | ✅ JSON-equal to original |
| `definition.stages[1]` not touched when only stage 0's pre_task is changed | ✅ second stage's `pre[0].task` stays `autoTrigger` |
| **`variables[]` preserved** (incl. `is_secret=true`) | ✅ both vars round-trip with all attrs |
| **`schedules[]` preserved** (incl. `days_of_week`, `time_zone`) | ✅ verbatim |
| **`triggers[]` preserved** (incl. `endpoint_id`, `events`) | ✅ verbatim |
| non-target source-params (git_type, endpoint_id, alias, repo_name, …) preserved | ✅ |

Refusal paths (no `update_pipeline_info` call is made):

| Scenario                                            | Returned error code        |
|-----------------------------------------------------|----------------------------|
| `confirm=false`                                     | `CONFIRM_REQUIRED`         |
| neither `new_default_branch` nor `new_pre_task` set | `NO_FIELDS_TO_UPDATE`      |
| `new_pre_task` outside the allow-list               | `INVALID_PRE_TASK`         |
| pipeline has multiple sources without `source_alias`| `SOURCE_ALIAS_REQUIRED`    |

These are enforced **before** the SDK is touched, so no partial PUT can
ever escape.

## Diff log emitted by `pipeline_update_info`

For every successful update, an INFO-level log line records:

```
pipeline_update_info pipeline_id=... project_id=...
  definition_hash <12-hex-before> -> <12-hex-after>;
  before_summary={'stage_count': 2, 'stages': [{'name': 'Stage 1', 'pre_tasks': ['official_devcloud_autoTrigger'], 'job_count': 1}, ...]}
  after_summary ={'stage_count': 2, 'stages': [{'name': 'Stage 1', 'pre_tasks': ['official_devcloud_manualTrigger'], 'job_count': 1}, ...]}
  changes={'pre_task': {'diffs': [{'sequence': 0, 'before': 'official_devcloud_autoTrigger', 'after': 'official_devcloud_manualTrigger'}], 'applied_to_count': 1}}
```

Two SHA-256-truncated hashes plus the before/after `summarise_definition()`
output give an at-a-glance audit trail without dumping the (potentially
large) full definition into the log.

## stdio smoke test (full handshake against fake credentials)

```
init.result.serverInfo: {'name': 'codearts-pipeline-mcp-server', 'version': '1.28.0'}
tools: ['pipeline_disable', 'pipeline_enable', 'pipeline_get_detail',
        'pipeline_list', 'pipeline_run', 'pipeline_update_info']
OK ✔ smoke test passed
```

This validates:

1. The package's console script entrypoint launches without error.
2. Logging goes to **stderr** only — stdout is reserved for JSON-RPC and is
   verified clean (`captured.out == ""` in `test_setup_logging_writes_to_stderr_only`).
3. The MCP `initialize` → `notifications/initialized` → `tools/list` round
   trip succeeds.
4. All six expected tools are advertised with non-empty descriptions.

## Manual entrypoint check

```
$ codearts-pipeline-mcp-server </dev/null
ERROR: codearts-pipeline-mcp-server: missing required env vars:
HUAWEICLOUD_ACCESS_KEY_ID, HUAWEICLOUD_SECRET_ACCESS_KEY, CODEARTS_REGION
exit: 2
```

Fail-fast (exit code `2` = configuration error) confirmed. Logs masked
correctly when starting with valid (fake) credentials:

```
INFO ... starting codearts-pipeline-mcp-server with config={
  'access_key_id': '******', 'secret_access_key': '******',
  'region': 'af-south-1', 'default_project_id': None, ...}
```

## Live-backend test (recommended next step)

For real-credential validation, run the same JSON-RPC smoke pattern but
with a populated `.env`:

```bash
set -a && source ~/.huaweicloud/codearts.env && set +a
python3 - <<'PY'
import json, subprocess, sys, os
proc = subprocess.Popen(
    [sys.executable, "-m", "pipeline_mcp_server.server"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env={**os.environ, "PYTHONPATH": "src"}, text=True, bufsize=1,
)
def rpc(msg):
    proc.stdin.write(json.dumps(msg) + "\n"); proc.stdin.flush()
    return json.loads(proc.stdout.readline())
print(rpc({"jsonrpc":"2.0","id":1,"method":"initialize",
          "params":{"protocolVersion":"2024-11-05","capabilities":{},
                    "clientInfo":{"name":"manual","version":"0.0"}}}))
proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}) + "\n")
proc.stdin.flush()
print(rpc({"jsonrpc":"2.0","id":2,"method":"tools/call",
          "params":{"name":"pipeline_list","arguments":{"limit":5}}}))
proc.stdin.close()
PY
```

A healthy live response shows `{ok: true, data: {total: N, pipelines: [...]}}`.
If the inner `ok` is `false` with `status_code: 401/403`, the MCP layer
itself is fine — fix the AK/SK or project membership at the IAM/CodeArts
console.

## Coverage of the requirements

| Requirement                                           | Where verified |
|-------------------------------------------------------|----------------|
| 6 tools wrap the 6 documented APIs                    | `tests/smoke_stdio.py` advertises all 6; per-tool tests verify the API call shape |
| Pydantic-validated inputs                             | `models.py` + assertions in `test_*` |
| Compact response envelopes (no SDK passthrough)       | `serializers.py` + `test_query_tools` |
| `definition` decoded for the LLM                      | `test_pipeline_get_detail_decodes_definition_string` |
| `pipeline_update_info` does read-modify-write         | `test_update_info_merge_logic.py` (7 tests) |
| `pipeline_update_info` requires `confirm=true`        | `test_refuses_without_confirm` |
| `pipeline_disable` requires `confirm=true`            | `test_pipeline_disable_requires_confirm` |
| Unified `{ok, data\|error}` envelope                   | every tool test |
| AK/SK never leaks to logs / responses                 | `test_setup_logging_writes_to_stderr_only`, `test_secret_masking_filter_replaces_known_secret` |
| 30 s timeout, 2-3 retry policy on network errors      | `client._build_http_config`, `Settings.network_retries` |
| Fail-fast on missing env vars                         | `test_load_settings_fails_fast_when_missing` (includes CODEARTS_REGION in error) |
| HUAWEICLOUD_REGION does NOT substitute for CODEARTS_REGION | `test_load_settings_does_not_fall_back_to_huaweicloud_region` |
| `project_id` optional → falls back to default         | `test_missing_project_id_when_no_default` and per-tool tests |
