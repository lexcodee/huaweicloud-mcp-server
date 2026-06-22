# Test Report — huaweicloud-ecs-mcp-server v0.1.0

Date: 2026-06-19

> NOTE: This report predates the 2026-06-21 tool consolidation. The pairs
> `ecs_get_server_{detail,status}` were merged into `ecs_get_server` (with
> `detail_level`), and `ecs_{start,stop,reboot}_server` were merged into
> `ecs_power_action` (with `action`). The names referenced below have been
> superseded; see README.md for the current tool list.

## Environment

- Python 3.10.12 / Linux x86_64
- `huaweicloudsdkcore` 3.1.200, `huaweicloudsdkecs` 3.1.200
- `mcp` 1.28.0, `pydantic` 2.13.4
- `pytest` 9.1.1

All tests use `unittest.mock` to replace the Huawei Cloud client. No real
ECS resources are created or modified. To validate live behaviour, set real
AK/SK and re-run the manual checklist at the bottom.

## Automated test results

```
$ PYTHONPATH=src pytest tests/
============================== 25 passed in 0.22s ==============================
```

| Module | Tests | Verdict |
|---|---|---|
| `test_config.py` | 5 | ✅ all pass |
| `test_query.py` | 6 | ✅ all pass |
| `test_lifecycle.py` | 11 | ✅ all pass |
| `test_job.py` | 3 | ✅ all pass |

### What's covered

- **Config**:
  - Missing required env vars → `SystemExit(2)`
  - Defaults applied for project_id / region / log
  - `mask_secret()` masking shape
  - `Settings.masked()` does not leak full AK/SK
- **Query tools (4)**:
  - `ecs_list_servers`: filters and pagination plumbed through to SDK
    `ListServersDetailsRequest`; response compacted to summary fields
  - Invalid `status` enum → `INVALID_PARAMS` (no SDK call)
  - `ecs_get_server_detail`: invalid UUID rejected; `NOT_FOUND` when 0 hits
  - `ecs_get_server_status`: returns minimal status payload
  - `ecs_list_flavors`: client-side limit applied
- **Lifecycle tools (5)**:
  - `ecs_start_server`: returns `job_id`; SDK called with correct ServerId list
  - `ecs_stop_server` / `ecs_reboot_server` / `ecs_delete_server` /
    `ecs_resize_server`: confirm=false → `CONFIRM_REQUIRED`, no SDK call
  - `ecs_stop_server` SOFT/HARD type passed through
  - `ecs_reboot_server` defaults to SOFT
  - `ecs_delete_server`: `delete_publicip` / `delete_volume` flags forwarded
  - `ecs_resize_server`: `flavor_ref` and `mode` forwarded; server_id in URL
  - Invalid UUIDs rejected with `INVALID_PARAMS`
  - `ClientRequestException` from SDK → unified error envelope with
    `code`, `request_id`, `status_code`
- **Job tool (1)**:
  - SUCCESS path includes sub_jobs
  - FAIL path carries `error_code` and `fail_reason`
  - Empty job_id does not crash

## Stdio MCP-protocol smoke test

Launches the actual server subprocess and walks `initialize` →
`notifications/initialized` → `tools/list`, then closes stdin.

```
$ python tests/smoke_stdio.py
init.result.serverInfo: {'name': 'huaweicloud-ecs-mcp-server', 'version': '1.28.0'}
tools: ['ecs_list_servers', 'ecs_get_server_detail', 'ecs_get_server_status',
        'ecs_list_flavors', 'ecs_start_server', 'ecs_stop_server',
        'ecs_reboot_server', 'ecs_delete_server', 'ecs_resize_server',
        'ecs_get_job_status']
OK ✔ smoke test passed
```

Confirms:
- Server boots over stdio with valid env
- 10 tools advertised to the client with proper JSON Schema
- No stdout pollution from logging (logs correctly go to stderr)
- AK/SK appear masked in the startup log line

## Manual integration checklist (requires live AK/SK)

These steps are NOT automated because they touch real Huawei Cloud
resources and would incur cost / state changes. Run by hand once with a
test account in a non-production project:

| # | Tool | Steps | Expected |
|---|---|---|---|
| 1 | `ecs_list_servers` | call with `limit=5` | `ok=true`, real servers returned |
| 2 | `ecs_get_server_detail` | pass an id from #1 | full detail dict |
| 3 | `ecs_get_server_status` | same id | status string |
| 4 | `ecs_list_flavors` | no args | non-empty list |
| 5 | `ecs_stop_server` | confirm=false | `CONFIRM_REQUIRED` |
| 6 | `ecs_stop_server` | confirm=true on a test VM | `job_id` returned |
| 7 | `ecs_get_job_status` | poll #6's job_id | reaches SUCCESS |
| 8 | `ecs_start_server` | same VM | `job_id` returned |
| 9 | `ecs_reboot_server` | confirm=true | `job_id` returned |
| 10 | `ecs_resize_server` | confirm=true with new flavor | `job_id` returned |
| 11 | `ecs_delete_server` | confirm=true on a throwaway VM | `job_id` returned |

## Known limitations

- Region is validated only when the SDK actually builds the EcsClient (lazy).
  Misspelled `HUAWEICLOUD_REGION` will surface as a Huawei SDK error on the
  first tool call rather than at startup. Acceptable for v0.1.
- `ecs_list_flavors` uses client-side `limit` truncation because the SDK
  endpoint does not accept a limit query param.
- HTTP retry policy is the SDK default (3 retries on transient failures);
  no custom backoff curve is wired in for v0.1.

## Verdict

All automated tests pass. The server is functional end-to-end via stdio.
Live verification still requires a manual pass against a real Huawei
Cloud project.
