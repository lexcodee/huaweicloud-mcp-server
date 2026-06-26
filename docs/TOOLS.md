# MCP Tools (75 total)

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

## VPC — Virtual network + security group management (19 tools)

### Network resources (read-only)

| Tool | Description | Min role |
|------|-------------|----------|
| `vpc_describe_vpcs` | List VPCs / get single VPC detail (dispatch: vpc_id=None → list, set → detail) | readonly |
| `vpc_describe_subnets` | List subnets / get single subnet detail with available IP count (dispatch: subnet_id=None → list, set → detail) | readonly |
| `vpc_describe_vpc_peerings` | List VPC peering connections / get single peering detail (dispatch: peering_id=None → list, set → detail) | readonly |
| `vpc_describe_route_tables` | List route tables / get single route table detail with route entries (dispatch: route_table_id=None → list, set → detail) | readonly |
| `vpc_describe_eips` | List elastic public IPs / get single EIP detail (dispatch: eip_id=None → list, set → detail) | readonly |
| `vpc_list_flow_logs` | List VPC flow log configs / get single flow log detail (dispatch: flow_log_id=None → list, set → detail) | readonly |

### Security group tools

| Tool | Description | Min role |
|------|-------------|----------|
| `vpc_query_security_groups` | List security groups / get single SG detail with rules (dispatch: security_group_id=None → list, set → detail) | readonly |
| `vpc_audit_security_group` | Audit SG for high-risk rules (SSH/ICMP open to 0.0.0.0/0, sensitive ports) | readonly |
| `vpc_check_port_reachability` | Check if a specific port is reachable on a SG (ingress/egress) | readonly |
| `vpc_list_sg_associated_instances` | List ECS instances associated with a security group (cross-calls ECS SDK) | readonly |
| `vpc_create_security_group` | Create a new security group | operator |
| `vpc_add_security_group_rule` | Add a rule to an existing security group | operator |
| `vpc_remove_security_group_rule` | ⚠ Remove a rule from a security group (two-phase confirm) | admin |

### Write operations

| Tool | Description | Min role |
|------|-------------|----------|
| `vpc_associate_eip` | Bind an EIP to an ECS NIC / NAT / ELB port | operator |
| `vpc_disassociate_eip` | ⚠ Unbind an EIP from its port (two-phase confirm) | admin |
| `vpc_add_route` | Add a custom route entry to a route table | operator |
| `vpc_delete_route` | ⚠ Delete a route entry from a route table (two-phase confirm) | admin |
| `vpc_confirm_destructive` | Execute pending destructive op (disassociate EIP / delete route / remove SG rule) | — |

### Flow log data query

| Tool | Description | Min role |
|------|-------------|----------|
| `vpc_query_flow_log_data` | Query actual VPC flow log records from LTS (5-tuple + action accept/reject). Looks up flow log config via VPC SDK, then searches LTS. Filters: src_ip, dst_ip, dst_port, action | readonly |

> Common VPC flow log record fields: version, project_id, interface_id, srcaddr, dstaddr, srcport, dstport, protocol, packets, bytes, start, end, action, log_status

> Common namespaces: `SYS.ECS` (cloud servers), `SYS.RDS` (relational DB), `SYS.DCS` (Redis cache), `SYS.ELB` (load balancer), `SYS.CCE` (container cluster nodes), `SYS.FunctionGraph` (function compute)

## RDS — Relational Database Service management (10 tools)

### Instance & resource queries (read-only)

| Tool | Description | Min role |
|------|-------------|----------|
| `rds_describe_instances` | List instances / get single instance detail (dispatch: instance_id=None → list, set → detail with nodes, volume, backup strategy, connection addresses, storage usage) | readonly |
| `rds_get_db_logs` | Query error logs (log_type='error') or slow query statistics (log_type='slow'). Slow logs return aggregated SQL-pattern data: sql_text, avg_duration_ms, execution_count, lock_time_ms — for AI-driven index optimization. Filters: min_duration_ms, database, sort_by (duration/count) | readonly |
| `rds_list_db_resources` | List databases (resource_type='databases': name, charset) or DB accounts (resource_type='accounts': name, hosts, database privileges) | readonly |
| `rds_list_backups` | List auto/manual backups with filters (instance_id, backup_type, status, time range) | readonly |
| `rds_get_instance_metrics` | Query CES monitoring metrics for an RDS instance (CPU, memory, IOPS, connections, disk). Cross-calls CES v1 SDK with namespace SYS.RDS | readonly |
| `rds_describe_parameter_group` | List parameter groups / show one group's params / show instance-applied params (dispatch: instance_id → instance config, config_id → group detail, both None → list all) | readonly |
| `rds_list_replicas` | List read-only replicas of a primary instance + replication delay status | readonly |
| `rds_audit_instance_security` | Composite security audit: public IP exposure, root % remote login, storage >85%, no backup in 7d, SSL disabled, no replica. Returns risk_items[] with severity + remediation suggestions | readonly |

### Write operations (two-phase confirmation)

| Tool | Description | Min role |
|------|-------------|----------|
| `rds_create_manual_backup` | ⚠ Create a manual backup snapshot (two-phase confirm — call rds_confirm_destructive after user approval) | operator |
| `rds_confirm_destructive` | Execute pending destructive RDS operation (create_manual_backup) | operator |

## OBS — Object Storage Service management (12 tools)

### Bucket & object queries (read-only)

| Tool | Description | Min role |
|------|-------------|----------|
| `obs_describe_buckets` | List all buckets / get single bucket detail (dispatch: bucket_name=None → list with region/storage class/versioning, set → detail with metadata + ACL) | readonly |
| `obs_list_objects` | List objects in a bucket with prefix/delimiter/pagination. Set include_versions=True to list object history versions (requires versioning enabled) | readonly |
| `obs_get_object` | Get object metadata via HEAD (default). Set include_content=True to download content (limited to 1 MB, text only — binary objects raise BINARY_CONTENT error) | readonly |
| `obs_generate_presigned_url` | Generate a time-limited download/upload URL (V2 HMAC-SHA1 signing, virtual-hosted-style). Method=GET for download, PUT for upload | readonly |
| `obs_describe_bucket_policy` | Get bucket ACL grants and public-access status | readonly |
| `obs_describe_bucket_lifecycle` | Query bucket lifecycle rules (transition storage class, expiration). Returns empty list if no config set | readonly |

### Security audit (read-only)

| Tool | Description | Min role |
|------|-------------|----------|
| `obs_audit_bucket_security` | Composite security audit: public ACL exposure, no server-side encryption, no versioning, missing public access block. Returns risk_items[] with severity + remediation suggestions | readonly |

### Write operations (two-phase confirmation)

| Tool | Description | Min role |
|------|-------------|----------|
| `obs_upload_object` | Upload text/small file content to a bucket path (stream upload, optional storage class) | operator |
| `obs_create_bucket` | Create a new bucket with ACL (default: private), optional storage class and encryption config | operator |
| `obs_delete_object` | ⚠ Delete a single object (two-phase confirm — call obs_confirm_destructive after user approval) | admin |
| `obs_set_bucket_policy` | ⚠ Set/update bucket policy JSON (two-phase confirm — call obs_confirm_destructive after user approval) | admin |
| `obs_confirm_destructive` | Execute pending destructive OBS operation (delete_object / set_bucket_policy) | — |
