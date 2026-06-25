# Huawei Cloud MCP Server — Agent Prompt Examples

This document collects **natural-language prompt examples** for calling each tool in this MCP Server from an Agent (Hermes / Claude Code / etc.). Copy-paste ready. All prompts are written from the perspective of a frontline SRE / DevOps / backend engineer.

> Covers 7 services, 53 tools: ECS · Pipeline · CTS · CCE · LTS · CES · VPC

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

## 7. VPC — Virtual Network + Security Groups

### Network Resource Queries

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| List all VPCs | "List all VPCs in the current project" | `vpc_describe_vpcs` |
| VPC detail | "Get the full detail of VPC vpc-id-xxx including CIDR and status" | `vpc_describe_vpcs(vpc_id=...)` |
| List subnets | "What subnets are in VPC vpc-id-xxx?" | `vpc_describe_subnets` |
| Subnet IP exhaustion | "Which subnets are running low on available IPs?" | `vpc_describe_subnets` |
| Subnet detail | "Get the detail of subnet subnet-id-xxx including AZ and available IP count" | `vpc_describe_subnets(subnet_id=...)` |
| List VPC peerings | "Show all VPC peering connections and their status" | `vpc_describe_vpc_peerings` |
| Peering detail | "Is peering connection peer-id-xxx active?" | `vpc_describe_vpc_peerings(peering_id=...)` |
| List route tables | "List all route tables and their associated subnets" | `vpc_describe_route_tables` |
| Route table detail | "Show the route entries in route table rt-id-xxx" | `vpc_describe_route_tables(route_table_id=...)` |
| List EIPs | "List all elastic public IPs and their binding status" | `vpc_describe_eips` |
| EIP detail | "What instance is EIP eip-id-xxx bound to?" | `vpc_describe_eips(eip_id=...)` |
| List flow logs | "What VPC flow log configurations exist?" | `vpc_list_flow_logs` |
| Flow log detail | "Get the detail of flow log fl-id-xxx including LTS group/topic" | `vpc_list_flow_logs(flow_log_id=...)` |

### Security Group Queries

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| List SGs | "List all security groups" | `vpc_query_security_groups` |
| SG detail with rules | "Show all rules in security group sg-id-xxx" | `vpc_query_security_groups(security_group_id=...)` |
| SG audit | "Audit security group sg-id-xxx for high-risk rules (SSH open to 0.0.0.0/0)" | `vpc_audit_security_group` |
| Port reachability | "Is port 443 reachable on sg-id-xxx from 10.0.0.0/8?" | `vpc_check_port_reachability` |
| SG associated instances | "Which ECS instances are using security group sg-id-xxx?" | `vpc_list_sg_associated_instances` |
| Create SG | "Create a security group named 'web-sg' in VPC vpc-id-xxx" | `vpc_create_security_group` |
| Add SG rule | "Add an ingress rule to sg-id-xxx allowing TCP 443 from 10.0.0.0/8" | `vpc_add_security_group_rule` |
| Remove SG rule | "Remove rule rule-id-xxx from sg-id-xxx" | `vpc_remove_security_group_rule` ⚠ |

### Write Operations (two-phase confirmation)

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| Bind EIP | "Bind EIP eip-id-xxx to ECS port port-id-yyy" | `vpc_associate_eip` |
| Unbind EIP | "Unbind EIP eip-id-xxx from its port" | `vpc_disassociate_eip` ⚠ |
| Add route | "Add a route to rt-id-xxx: destination 10.1.0.0/16 via peering peer-id-xxx" | `vpc_add_route` |
| Delete route | "Delete route to 10.1.0.0/16 from rt-id-xxx" | `vpc_delete_route` ⚠ |
| Confirm execution | "Confirm the EIP unbind, approval_id=abc-123" | `vpc_confirm_destructive` |

### Flow Log Data Query

| Scenario | Prompt Example | Triggered Tool |
|----------|---------------|----------------|
| Recent flow logs | "Show flow log records for fl-id-xxx in the past hour" | `vpc_query_flow_log_data` |
| Rejected traffic | "What traffic was rejected in flow log fl-id-xxx in the past 30 minutes?" | `vpc_query_flow_log_data(action=reject)` |
| Filter by source | "Show flow logs from 10.0.1.5 in fl-id-xxx" | `vpc_query_flow_log_data(src_ip=10.0.1.5)` |
| Filter by destination | "Show traffic to 10.0.2.100 port 443 in fl-id-xxx" | `vpc_query_flow_log_data(dst_ip=10.0.2.100,dst_port=443)` |

### Composite Scenarios

- "Which subnets have less than 10 available IPs? List them with their VPC and AZ"
- "Is VPC peering peer-id-xxx active? If so, show the route tables that route through it"
- "EIP eip-id-xxx is bound to which instance? Show me that instance's security groups and audit them for risk"
- "Flow log fl-id-xxx shows rejected traffic from 10.0.1.5 to port 3306 — check if the destination's security group allows that port"

---

## 8. Cross-Service Composite Scenarios (Agent Orchestration)

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

### 6. Network Connectivity Diagnosis

> "ECS i-xxx cannot reach 10.0.2.100:443. Help me diagnose:
>  1. Which VPC and subnet is i-xxx in?
>  2. Is there a route to 10.0.2.0/24 in its route table?
>  3. Does its security group allow egress to 10.0.2.100:443?
>  4. Does the destination's security group allow ingress on port 443?
>  5. Check flow logs for rejected traffic from i-xxx to 10.0.2.100"

Tools: `ecs_get_server` → `vpc_describe_subnets` → `vpc_describe_route_tables` → `vpc_check_port_reachability` → `vpc_query_flow_log_data`

---

## 9. Two-Phase Confirmation (Destructive Operations) Usage Guide

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
