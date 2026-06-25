# MCP 工具一览（34 个）

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

> 常用 namespace 速查：`SYS.ECS`（云服务器）、`SYS.RDS`（关系数据库）、`SYS.DCS`（Redis 缓存）、`SYS.ELB`（负载均衡）、`SYS.CCE`（容器集群节点）、`SYS.FunctionGraph`（函数工作流）
