# MCP 工具一览（63 个）

> 角色层级：**admin** ⊃ **operator** ⊃ **readonly**

---

## ECS — 云主机生命周期管理（8 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `ecs_list_servers` | 列出云主机（支持 name/status/IP/tags 过滤） | readonly |
| `ecs_get_server` | 查看单台详情或轻量状态快照 | readonly |
| `ecs_list_flavors` | 列出可用规格 | readonly |
| `ecs_get_job_status` | 查询异步任务状态 | readonly |
| `ecs_power_action` | 批量开机 / 关机 / 重启 | operator / admin |
| `ecs_delete_server` | ⚠ 删除云主机（可选释放 EIP + 磁盘） | admin |
| `ecs_resize_server` | ⚠ 变更规格（vCPU/RAM） | admin |
| `ecs_confirm_destructive` | 确认执行待定的破坏性操作 | — |

## Pipeline — CodeArts 流水线管理（6 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `pipeline_list` | 列出流水线 + 最近运行状态 | readonly |
| `pipeline_get_detail` | 查看流水线完整配置 | readonly |
| `pipeline_run` | 触发流水线执行 | operator |
| `pipeline_set_status` | ⚠ 启用 / 禁用流水线 | admin |
| `pipeline_update_info` | ⚠ 修改默认分支 / 触发方式 | admin |
| `pipeline_confirm_destructive` | 确认执行待定的破坏性操作 | — |

## CTS — 审计日志检索（2 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `cts_search_traces` | 按时间 + 条件搜索审计事件（7 天窗口） | readonly |
| `cts_get_trace_detail` | 查看单条事件的完整请求/响应体（敏感值脱敏） | readonly |

## CCE — 云容器引擎管理（6 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `cce_query_clusters` | 列出集群 / 查看单个集群详情 | readonly |
| `cce_query_nodes` | 列出集群节点 / 查看单个节点详情 | readonly |
| `cce_query_nodepools` | 列出节点池 / 查看单个节点池详情 | readonly |
| `cce_update_nodepool` | ⚠ 调整节点池期望节点数（缩容需两阶段确认；DefaultPool 不支持缩放） | operator |
| `cce_get_job` | 查询异步任务状态（集群创建/升级/节点池缩放等） | readonly |
| `cce_confirm_destructive` | 确认执行待定的破坏性操作（缩容） | — |

## LTS — 日志服务（6 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `lts_query_log_resources` | 列出日志组 / 列出组下日志流（dispatch: log_group_id=None → 组列表, 设置 → 流列表） | readonly |
| `lts_search_logs` | 关键词 / SQL 搜索日志内容 | readonly |
| `lts_get_log_context` | 获取指定行号前后的上下文日志（因果链分析） | readonly |
| `lts_query_histogram` | 时间桶计数（定位日志尖峰） | readonly |
| `lts_query_alarm_rules` | 列出告警规则 / 查看单条规则详情（dispatch: rule_id=None → 列表, 设置 → 详情） | readonly |
| `lts_list_alarm_history` | 查询最近触发的告警事件 | readonly |

## CES — 云监控（6 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `ces_list_metrics` | 查询指标列表（按 namespace/维度/资源 ID 过滤），是 `ces_get_metric_data` 的前置发现步骤 | readonly |
| `ces_get_metric_data` | 查询指标时序数据，支持多指标批量查询（合并了 get_metric_data + batch_get_metric_data） | readonly |
| `ces_query_alarm_rules` | 列出告警规则 / 查看单条规则详情含策略和资源（dispatch: alarm_id=None → 列表, 设置 → 详情） | readonly |
| `ces_list_alarm_histories` | 查询告警历史记录（复盘事故时间线） | readonly |
| `ces_query_resource_groups` | 列出资源分组 / 查看分组详情含资源列表（dispatch: group_id=None → 列表, 设置 → 详情） | readonly |
| `ces_list_event_data` | 查询事件监控数据 / 查看事件详情（dispatch: event_name=None → 列表, 设置 → 详情） | readonly |

## VPC — 虚拟网络 + 安全组管理（19 个）

### 网络资源（只读）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `vpc_describe_vpcs` | 列出 VPC / 查看单个 VPC 详情（dispatch: vpc_id=None → 列表, 设置 → 详情） | readonly |
| `vpc_describe_subnets` | 列出子网 / 查看单个子网详情含可用 IP 数（dispatch: subnet_id=None → 列表, 设置 → 详情） | readonly |
| `vpc_describe_vpc_peerings` | 列出 VPC 对等连接 / 查看单个对等连接详情（dispatch: peering_id=None → 列表, 设置 → 详情） | readonly |
| `vpc_describe_route_tables` | 列出路由表 / 查看单个路由表详情含路由条目（dispatch: route_table_id=None → 列表, 设置 → 详情） | readonly |
| `vpc_describe_eips` | 列出弹性公网 IP / 查看单个 EIP 详情（dispatch: eip_id=None → 列表, 设置 → 详情） | readonly |
| `vpc_list_flow_logs` | 列出 VPC 流日志配置 / 查看单个流日志详情（dispatch: flow_log_id=None → 列表, 设置 → 详情） | readonly |

### 安全组工具

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `vpc_query_security_groups` | 列出安全组 / 查看单个安全组详情含规则（dispatch: security_group_id=None → 列表, 设置 → 详情） | readonly |
| `vpc_audit_security_group` | 审计安全组高风险规则（SSH/ICMP 对 0.0.0.0/0 开放、敏感端口） | readonly |
| `vpc_check_port_reachability` | 检查指定端口在安全组上是否可达（入方向/出方向） | readonly |
| `vpc_list_sg_associated_instances` | 列出安全组关联的 ECS 实例（跨调用 ECS SDK） | readonly |
| `vpc_create_security_group` | 创建安全组 | operator |
| `vpc_add_security_group_rule` | 添加安全组规则 | operator |
| `vpc_remove_security_group_rule` | ⚠ 删除安全组规则（两阶段确认） | admin |

### 写操作

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `vpc_associate_eip` | 将 EIP 绑定到 ECS 网卡 / NAT / ELB 端口 | operator |
| `vpc_disassociate_eip` | ⚠ 解绑 EIP（两阶段确认） | admin |
| `vpc_add_route` | 添加自定义路由条目 | operator |
| `vpc_delete_route` | ⚠ 删除路由条目（两阶段确认） | admin |
| `vpc_confirm_destructive` | 确认执行待定的破坏性操作（解绑 EIP / 删除路由 / 删除安全组规则） | — |

### 流日志数据查询

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `vpc_query_flow_log_data` | 查询 VPC 流日志实际记录（来自 LTS，五元组 + 动作 accept/reject）。先通过 VPC SDK 查流日志配置获取 LTS group/topic，再搜索 LTS。过滤：src_ip, dst_ip, dst_port, action | readonly |

> VPC 流日志记录字段：version, project_id, interface_id, srcaddr, dstaddr, srcport, dstport, protocol, packets, bytes, start, end, action, log_status

> 常用 namespace 速查：`SYS.ECS`（云服务器）、`SYS.RDS`（关系数据库）、`SYS.DCS`（Redis 缓存）、`SYS.ELB`（负载均衡）、`SYS.CCE`（容器集群节点）、`SYS.FunctionGraph`（函数工作流）

## RDS — 关系数据库服务管理（10 个）

### 实例与资源查询（只读）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `rds_describe_instances` | 列出实例 / 查看单个实例详情（dispatch: instance_id=None → 列表, 设置 → 详情含节点、磁盘、备份策略、连接地址、存储用量） | readonly |
| `rds_get_db_logs` | 查询错误日志（log_type='error'）或慢查询统计（log_type='slow'）。慢日志返回按 SQL 模式聚合的数据：sql_text, avg_duration_ms, execution_count, lock_time_ms — 供 AI 分析索引优化。过滤：min_duration_ms, database, sort_by (duration/count) | readonly |
| `rds_list_db_resources` | 列出数据库（resource_type='databases': 名称, 字符集）或数据库账号（resource_type='accounts': 名称, 主机, 库权限） | readonly |
| `rds_list_backups` | 列出自动/手动备份，支持按实例、类型、状态、时间范围过滤 | readonly |
| `rds_get_instance_metrics` | 查询 RDS 实例的 CES 监控指标（CPU、内存、IOPS、连接数、磁盘）。跨调用 CES v1 SDK，namespace=SYS.RDS | readonly |
| `rds_describe_parameter_group` | 列出参数组 / 查看参数组详情 / 查看实例已应用参数（dispatch: instance_id → 实例配置, config_id → 参数组详情, 均不设 → 列出全部） | readonly |
| `rds_list_replicas` | 列出主实例的只读副本及复制延迟状态 | readonly |
| `rds_audit_instance_security` | 复合安全审计：公网 IP 暴露、root % 远程登录、存储 >85%、7 天无备份、SSL 未开启、无只读副本。返回 risk_items[] 含严重级别和修复建议 | readonly |

### 写操作（两阶段确认）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `rds_create_manual_backup` | ⚠ 创建手动备份快照（两阶段确认 — 用户批准后调用 rds_confirm_destructive） | operator |
| `rds_confirm_destructive` | 确认执行待定的 RDS 破坏性操作（创建手动备份） | operator |
