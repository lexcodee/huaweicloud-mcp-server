# Huawei Cloud MCP Server — Agent Prompt Examples

This document collects **natural-language prompt examples** for calling each tool in this MCP Server from an Agent (Hermes / Claude Code / etc.). Copy-paste ready. All prompts are written from the perspective of a frontline SRE / DevOps / backend engineer.

> Covers 6 services, 34 tools: ECS · Pipeline · CTS · CCE · LTS · CES

---

## 1. ECS — Cloud Server Lifecycle Management

### Read-only Queries

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| List all servers | "List all ECS servers in the current project" | `ecs_list_servers` |
| Filter by status | "Show all ECS servers that are in SHUTOFF state" | `ecs_list_servers` |
| Filter by IP range | "Find servers whose private IP contains 192.168.10" | `ecs_list_servers` |
| Filter by tag | "List all ECS servers tagged with env=prod" | `ecs_list_servers` |
| Fuzzy name match | "List all ECS servers whose name contains 'web'" | `ecs_list_servers` |
| Single server detail | "Get the full config of ECS xxx-yyy-zzz, including attached volumes and security groups" | `ecs_get_server` |
| Lightweight status poll | "Is ECS xxx-yyy-zzz powered on or off? Just the power state" | `ecs_get_server (detail_level=status)` |
| Flavor list | "What ECS flavors are available in AZ af-south-1a?" | `ecs_list_flavors` |
| Job poll | "What's the status of ECS async job job-id-xxx?" | `ecs_get_job_status` |

### Write Operations (two-phase confirmation)

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| Start | "Power on ECS xxx" | `ecs_power_action(action=start)` |
| Stop | "Power off ECS xxx" | `ecs_power_action(action=stop)` ⚠ requires confirmation |
| Hard reboot | "Hard reboot ECS xxx and yyy" | `ecs_power_action(action=reboot,type=HARD)` ⚠ |
| Delete + cleanup | "Delete ECS xxx, and also release its EIP and data disks" | `ecs_delete_server` ⚠ |
| Resize flavor | "Resize ECS xxx to flavor s6.xlarge.4, allow auto-stop" | `ecs_resize_server` ⚠ |
| Confirm execution | "Confirm the previous delete operation, approval_id=abc-123" | `ecs_confirm_destructive` |

### Composite Scenarios

- "Find all servers with 'staging' in the name and shut them all down"
- "List running web servers in the prod environment, then show me the full config of one"
- "ECS xxx is unresponsive — hard reboot it, then check its power state"

---

## 2. Pipeline — CodeArts Pipeline Management

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| List all pipelines | "List all pipelines in the current project, sorted by update time descending" | `pipeline_list` |
| Recent run status | "Which pipelines had a failed last run?" | `pipeline_list(status=[FAILED])` |
| Name filter | "Find pipelines whose name contains 'deploy'" | `pipeline_list` |
| Pipeline detail | "Get the config of pipeline abc-123, I want to see its stages" | `pipeline_get_detail` |
| Default branch | "What's the default branch of pipeline abc-123?" | `pipeline_get_detail` |
| Trigger run | "Run pipeline abc-123 with the default branch" | `pipeline_run` |
| Run with branch | "Run pipeline abc-123 on branch release/2.0" | `pipeline_run(sources=[{default_branch:release/2.0}])` |
| Run specific stage | "Only run the build stage of pipeline abc-123" | `pipeline_run(choose_stages=[...])` |
| Enable | "Re-enable pipeline abc-123" | `pipeline_set_status(enabled)` |
| Disable | "Temporarily disable pipeline abc-123" | `pipeline_set_status(disabled)` ⚠ |
| Change default branch | "Change the default branch of pipeline abc-123 to release/2.0" | `pipeline_update_info` ⚠ |
| Set manual trigger | "Set the first stage of pipeline abc-123 to require manual trigger" | `pipeline_update_info(new_pre_task=manualTrigger)` ⚠ |

### Composite Scenarios

- "List pipelines that failed in the last 24 hours, and tell me which stage failed in the most recent run of each"
- "We need a release freeze — disable all pipelines with 'prod' in the name"

---

## 3. CTS — Audit Log Search

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| Default window search | "Has anyone called Huawei Cloud APIs in the last hour?" | `cts_search_traces` |
| Filter by service | "What operations were performed on ECS in the past day?" | `cts_search_traces(service_type=ECS)` |
| Filter by user | "What did user alice do to cloud resources in the last 7 days?" | `cts_search_traces(user=alice)` |
| Look for anomalies | "Any incident-level audit events in the past 24 hours?" | `cts_search_traces(trace_rating=incident)` |
| Filter by event type | "Has anyone deleted an EIP recently? Search for deleteEip events" | `cts_search_traces(trace_name=deleteEip)` |
| Filter by resource ID | "Show all operations on ECS i-xxx-yyy in the last 48 hours" | `cts_search_traces(resource_id=...)` |
| Single trace detail | "Open the full request/response body of audit event trace-id-xxx" | `cts_get_trace_detail` |

### Composite Scenarios

- "Who modified our prod security groups in the past 2 hours? Show the audit events and their full request bodies"
- "Check if user alice called deleteServer in the last 24 hours — if so, list the details"

---

## 4. CCE — Cloud Container Engine

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| Cluster list | "What CCE clusters do I have?" | `cce_query_clusters` |
| Filter by version | "Which clusters are running Kubernetes v1.27?" | `cce_query_clusters(version=v1.27)` |
| Cluster detail | "Get the network config of cluster cluster-id-xxx (VPC/CIDR/Endpoint)" | `cce_query_clusters(cluster_id=...)` |
| Node list | "List all nodes in cluster xxx with their private IPs" | `cce_query_nodes` |
| Node detail | "What are the taints, labels, and disk config of node node-id-yyy?" | `cce_query_nodes(node_id=...)` |
| Node pool list | "How many node pools does cluster xxx have? What flavor is each?" | `cce_query_nodepools` |
| Node pool detail | "Check the autoscaling policy and node template of node pool pool-id-zzz" | `cce_query_nodepools(nodepool_id=...)` |
| Scale up | "Scale cluster xxx node pool pool-yyy to 10 nodes" | `cce_update_nodepool` |
| Scale down | "Scale node pool pool-yyy down to 3 nodes" | `cce_update_nodepool` ⚠ |
| Job poll | "What's the status of CCE scale-down job job-xxx?" | `cce_get_job` |
| Confirm scale-down | "Confirm the scale-down operation, approval_id=..." | `cce_confirm_destructive` |

### Composite Scenarios

- "How many nodes are currently in cluster xxx node pool yyy? Scale it to 8 to handle incoming traffic"
- "List all node IPs in cluster xxx — I need to whitelist them on the firewall"

---

## 5. LTS — Log Tank Service

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| List log groups | "What log groups are in my project?" | `lts_query_log_resources` |
| List log streams | "What log streams are under log group group-xxx?" | `lts_query_log_resources(log_group_id=...)` |
| Keyword search | "Search for 'OutOfMemory' in group-xxx/stream-yyy over the past hour" | `lts_search_logs` |
| Multi-keyword AND | "Find logs containing both ERROR and user_id=12345" | `lts_search_logs(keywords="ERROR user_id=12345")` |
| SQL aggregation | "Count ERRORs by service over the past hour" | `lts_search_logs(query="level:ERROR \| stats count() by service")` |
| Label filter | "Get all logs where host=host-01" | `lts_search_logs(labels={host:host-01})` |
| Log context | "Show me 50 lines before and after log line 12345" | `lts_get_log_context` |
| Time histogram | "Bucket 'timeout' logs in 5-minute intervals over the past 6 hours — find the spike" | `lts_query_histogram` |
| Alarm rule list | "What LTS keyword and SQL alarm rules have I configured?" | `lts_query_alarm_rules` |
| Alarm rule detail | "Check the keyword config and bound log streams of alarm rule rule-xxx" | `lts_query_alarm_rules(rule_id=...)` |
| Active alarms | "Which LTS alarms are currently firing?" | `lts_list_alarm_history(state=active)` |
| Historical alarms | "What Critical alarms fired in the past 7 days?" | `lts_list_alarm_history(state=history,level=Critical)` |

### Composite Scenarios

- "How often did OutOfMemory appear in group-xxx/stream-yyy in the past hour? Pick the most recent event and show 30 lines of context"
- "What active alarms are in the alarm center? Pick the most severe one and search for its keyword in the corresponding log stream"

---

## 6. CES — Cloud Eye Monitoring

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| Discover metrics | "What metrics are available under the SYS.ECS namespace?" | `ces_list_metrics(namespace=SYS.ECS)` |
| Instance metrics | "What monitoring metrics does ECS i-xxx expose?" | `ces_list_metrics(dim_0="instance_id,i-xxx")` |
| Single metric time series | "Pull CPU utilization for ECS i-xxx over the past hour" | `ces_get_metric_data` |
| Batch metrics | "Pull CPU and memory utilization for these 5 ECS instances over the past hour, period=60" | `ces_get_metric_data` |
| Different aggregation | "Max connections for RDS instance xxx over the past 24 hours (max aggregation, period=3600)" | `ces_get_metric_data(filter=max,period=3600)` |
| Alarm rule list | "How many CES alarm rules do I have? Which ones are currently in alarm state?" | `ces_query_alarm_rules(status=alarm)` |
| Alarm rule detail | "What's the threshold of alarm rule alarm-xxx? Which resources is it bound to?" | `ces_query_alarm_rules(alarm_id=...)` |
| Alarm history | "What Critical (level=1) alarms fired in the past 7 days?" | `ces_list_alarm_histories(level=1)` |
| Resource group list | "What CES resource groups do I have?" | `ces_query_resource_groups` |
| Group detail | "Which instances are in resource group group-xxx?" | `ces_query_resource_groups(group_id=...)` |
| System events | "What OPS-type system events occurred in the past 24 hours?" | `ces_list_event_data(sub_event_type=SUB_EVENT.OPS)` |
| Event detail | "Get the details of event modifyInstance" | `ces_list_event_data(event_name=modifyInstance)` |

### Composite Scenarios

- "ECS i-xxx has had high CPU utilization for the past hour — correlate its alarm rules, alarm history, and related system events"
- "Show the connection count and CPU utilization trend for RDS instance yyy over the past 6 hours, period=300 average"

---

## 7. Cross-Service Composite Scenarios (Agent Orchestration)

The following scenarios require the Agent to chain multiple tools autonomously — this is where the MCP Server delivers real value:

### 1. Incident Post-Mortem — Who Touched My Server

> "ECS i-xxx lost network in the past 2 hours. Help me investigate:
>  1. Current power/network state of this server
>  2. Any operations performed on it in the past 2 hours (audit)
>  3. CPU and network-in traffic curves on CES
>  4. Any anomalies in the associated logs"

Tools: `ecs_get_server` → `cts_search_traces(resource_id=...)` → `ces_get_metric_data` → `lts_search_logs`

### 2. Pipeline Pre-Deploy Check

> "I want to deploy pipeline abc-123:
>  1. Show its current config and default branch
>  2. Success rate of the last 5 runs
>  3. Trigger a run
>  4. Monitor job status until complete"

Tools: `pipeline_get_detail` → `pipeline_list` → `pipeline_run` → poll

### 3. CCE Capacity Planning

> "For cluster cluster-xxx:
>  1. Current node pool configs and node counts
>  2. CES CPU/memory utilization per node
>  3. Find node pools with utilization < 30% and suggest scaling down to X nodes"

Tools: `cce_query_nodepools` → `cce_query_nodes` → `ces_get_metric_data` → `cce_update_nodepool`

### 4. Alarm Storm Triage

> "What active alarms are there in both LTS and CES?
>  Merge and sort by time, pick the top 3:
>  1. LTS alarm → correlate log stream context
>  2. CES alarm → correlate metric curves + alarm history"

Tools: `lts_list_alarm_history` + `ces_list_alarm_histories` → `lts_get_log_context` + `ces_get_metric_data`

### 5. Resource Audit Snapshot

> "Give me a resource snapshot of the current project:
>  - ECS total count, status distribution
>  - CCE cluster count, total nodes
>  - Pipeline total count, failures in the last 24h
>  - Current firing alarms (LTS + CES)"

Tools: `ecs_list_servers` + `cce_query_clusters` + `cce_query_nodes` + `pipeline_list` + `lts_list_alarm_history` + `ces_query_alarm_rules`

---

## 8. Two-Phase Confirmation (Destructive Operations) Usage Guide

Destructive tools return `{status: "pending_approval", approval_id: "..."}`. The Agent should:

1. **Restate the change** — present the preview (scope, from/to) to the user
2. **Wait for explicit confirmation** — only call `*_confirm_destructive` after the user says "confirm / yes / proceed"
3. **TTL note** — approval_id expires after 120 seconds; if expired, re-issue the original operation

Example dialog:

```
User: Scale node pool pool-yyy down to 3 nodes
Agent: ⚠ About to scale down pool-yyy: current 8 nodes → target 3, which will evict Pods on 5 nodes.
       approval_id=abc-123. Reply "confirm" to proceed.
User: confirm
Agent: [calls cce_confirm_destructive(approval_id=abc-123)] → Job submitted, job_id=...
```

---

## Appendix: Common CES Namespace Quick Reference

| Namespace | Service |
|-----------|---------|
| `SYS.ECS` | Elastic Cloud Server |
| `SYS.RDS` | Relational Database |
| `SYS.DCS` | Distributed Cache Service (Redis) |
| `SYS.ELB` | Elastic Load Balancer |
| `SYS.CCE` | Cloud Container Engine (node metrics) |
| `SYS.FunctionGraph` | FunctionGraph |
| `SYS.VPC` | Virtual Private Cloud |
| `SYS.EVS` | Elastic Volume Service (disk) |
