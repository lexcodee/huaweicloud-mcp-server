# MCP Tools (34 total)

> Role hierarchy: **admin** ⊃ **operator** ⊃ **readonly**

---

## ECS — Cloud server lifecycle management (8 tools)

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

## Pipeline — CodeArts pipeline management (6 tools)

| Tool | Description | Min role |
|------|-------------|----------|
| `pipeline_list` | List pipelines + latest-run status | readonly |
| `pipeline_get_detail` | Full pipeline config | readonly |
| `pipeline_run` | Trigger a run | operator |
| `pipeline_set_status` | ⚠ Enable/disable pipeline | admin |
| `pipeline_update_info` | ⚠ Update default branch / trigger | admin |
| `pipeline_confirm_destructive` | Execute pending destructive op | — |

## CTS — Audit log search (2 tools)

| Tool | Description | Min role |
|------|-------------|----------|
| `cts_search_traces` | Search audit events (7-day window) | readonly |
| `cts_get_trace_detail` | Full masked request/response body | readonly |

## CCE — Cloud container engine management (6 tools)

| Tool | Description | Min role |
|------|-------------|----------|
| `cce_query_clusters` | List clusters / get single cluster detail | readonly |
| `cce_query_nodes` | List cluster nodes / get single node detail | readonly |
| `cce_query_nodepools` | List node pools / get single pool detail | readonly |
| `cce_update_nodepool` | ⚠ Resize node pool desired count (scale-down requires two-phase confirm; DefaultPool scaling not supported) | operator |
| `cce_get_job` | Poll async job status (cluster create/upgrade/node-pool resize etc.) | readonly |
| `cce_confirm_destructive` | Execute pending destructive op (scale-down) | — |

## LTS — Log Tank Service (6 tools)

| Tool | Description | Min role |
|------|-------------|----------|
| `lts_query_log_resources` | List log groups / list streams under a group (dispatch: log_group_id=None → groups, set → streams) | readonly |
| `lts_search_logs` | Keyword / SQL log search | readonly |
| `lts_get_log_context` | Fetch N lines around a specific line_num (causal-chain analysis) | readonly |
| `lts_query_histogram` | Time-bucketed counts (locate log spikes) | readonly |
| `lts_query_alarm_rules` | List alarm rules / get single rule detail (dispatch: rule_id=None → list, set → detail) | readonly |
| `lts_list_alarm_history` | Recently triggered alarm events | readonly |

## CES — Cloud Eye Service (6 tools)

| Tool | Description | Min role |
|------|-------------|----------|
| `ces_list_metrics` | List available metrics (filter by namespace/dimension/resource ID); prerequisite for `ces_get_metric_data` | readonly |
| `ces_get_metric_data` | Query metric time-series data; accepts multiple metrics in one call (merges get_metric_data + batch_get_metric_data) | readonly |
| `ces_query_alarm_rules` | List alarm rules / get single rule detail with policies and resources (dispatch: alarm_id=None → list, set → detail) | readonly |
| `ces_list_alarm_histories` | Query alarm history records (incident post-mortem) | readonly |
| `ces_query_resource_groups` | List resource groups / get group detail with resources (dispatch: group_id=None → list, set → detail) | readonly |
| `ces_list_event_data` | List event monitoring data / get event detail (dispatch: event_name=None → list, set → detail) | readonly |

> Common namespaces: `SYS.ECS` (cloud servers), `SYS.RDS` (relational DB), `SYS.DCS` (Redis cache), `SYS.ELB` (load balancer), `SYS.CCE` (container cluster nodes), `SYS.FunctionGraph` (function compute)
