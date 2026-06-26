# 华为云 MCP Server — Agent 提问案例

本文档汇总在 Agent（Hermes / Claude Code 等）中调用本 MCP Server 各工具的**自然语言提问案例**，可直接复制粘贴使用。所有提问均以一线 SRE / DevOps / 后端工程师视角组织。

> 覆盖 9 个服务、75 个工具：ECS · Pipeline · CTS · CCE · LTS · CES · VPC · RDS · OBS

---

## 一、ECS — 云主机生命周期管理

### 只读查询（readonly）

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 列出全部主机 | "列出当前项目下所有 ECS 云主机" | `ecs_list_servers` |
| 按状态筛选 | "把所有处于 SHUTOFF 状态的云主机列出来" | `ecs_list_servers` |
| 按 IP 段查询 | "找一下私网 IP 包含 192.168.10 的主机" | `ecs_list_servers` |
| 按标签查询 | "查出所有打了 env=prod 标签的云主机" | `ecs_list_servers` |
| 模糊名称匹配 | "名字里包含 'web' 的 ECS 都列出来" | `ecs_list_servers` |
| 单台详情 | "把 ECS xxx-yyy-zzz 的完整配置查出来，包括挂载的磁盘和安全组" | `ecs_get_server` |
| 轻量状态轮询 | "ECS xxx-yyy-zzz 现在是开机还是关机？只看电源状态" | `ecs_get_server (detail_level=status)` |
| 规格列表 | "在 af-south-1a 可用区有哪些 ECS 规格可以选？" | `ecs_list_flavors` |
| 任务轮询 | "ECS 异步任务 job-id-xxx 现在跑到哪一步了？" | `ecs_get_job_status` |

### 写操作（含两阶段确认）

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 启动 | "把 ECS xxx 开机" | `ecs_power_action(action=start)` |
| 关机 | "把 ECS xxx 关机" | `ecs_power_action(action=stop)` ⚠ 需确认 |
| 强制重启 | "强制重启 ECS xxx 和 yyy" | `ecs_power_action(action=reboot,type=HARD)` ⚠ |
| 删除 + 清理 | "删除 ECS xxx，同时释放 EIP 和数据盘" | `ecs_delete_server` ⚠ |
| 变更规格 | "把 ECS xxx 的规格升到 s6.xlarge.4，允许自动停机" | `ecs_resize_server` ⚠ |
| 确认执行 | "确认刚才的删除操作，approval_id=abc-123" | `ecs_confirm_destructive` |

### 复合场景

- "找出名字里有 'staging' 的所有主机，全部关机"
- "把 prod 环境运行中的 web 主机列出来，挑一台看一下完整配置"
- "ECS xxx 不响应了，强制重启一下，然后给我看下电源状态"

---

## 二、Pipeline — CodeArts 流水线管理

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 列出所有流水线 | "列出当前项目下全部流水线，按更新时间倒序" | `pipeline_list` |
| 看最近运行状态 | "哪些流水线最近一次运行失败了？" | `pipeline_list(status=[FAILED])` |
| 名称过滤 | "找一下名字里包含 'deploy' 的流水线" | `pipeline_list` |
| 流水线详情 | "把流水线 abc-123 的配置查出来，我想看一下 stages" | `pipeline_get_detail` |
| 默认分支 | "流水线 abc-123 的默认分支是哪个？" | `pipeline_get_detail` |
| 触发运行 | "用默认分支跑一下流水线 abc-123" | `pipeline_run` |
| 指定分支跑 | "用 release/2.0 分支跑流水线 abc-123" | `pipeline_run(sources=[{default_branch:release/2.0}])` |
| 仅跑某 stage | "只跑流水线 abc-123 的 build stage" | `pipeline_run(choose_stages=[...])` |
| 启用 | "把流水线 abc-123 重新启用" | `pipeline_set_status(enabled)` |
| 禁用 | "暂时禁用流水线 abc-123" | `pipeline_set_status(disabled)` ⚠ |
| 改默认分支 | "把流水线 abc-123 的默认分支改成 release/2.0" | `pipeline_update_info` ⚠ |
| 改成手动触发 | "把流水线 abc-123 的首个 stage 改成需要手动触发" | `pipeline_update_info(new_pre_task=manualTrigger)` ⚠ |

### 复合场景

- "把最近 24 小时内跑失败的流水线列出来，挑一条把最近一次失败的 stage 名字告诉我"
- "我们要冻结发布，把名字里有 'prod' 的流水线全部禁用"

---

## 三、CTS — 审计日志检索

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 默认窗口搜索 | "最近 1 小时有没有人调过华为云 API？" | `cts_search_traces` |
| 按服务过滤 | "过去 1 天内 ECS 服务有哪些操作？" | `cts_search_traces(service_type=ECS)` |
| 按用户 | "用户 alice 最近 7 天对云资源做了什么？" | `cts_search_traces(user=alice)` |
| 关注异常 | "过去 24 小时有哪些 incident 级别的审计事件？" | `cts_search_traces(trace_rating=incident)` |
| 按事件类型 | "最近有人删过 EIP 吗？查一下 deleteEip 事件" | `cts_search_traces(trace_name=deleteEip)` |
| 按资源 ID | "查一下 ECS i-xxx-yyy 这台机器最近 48 小时的所有操作" | `cts_search_traces(resource_id=...)` |
| 单条详情 | "把审计事件 trace-id-xxx 的完整请求/响应体打开看下" | `cts_get_trace_detail` |

### 复合场景

- "过去 2 小时谁动了我们 prod 环境的安全组？把对应的审计事件和详细请求体都给我"
- "查一下用户 alice 最近 24 小时是否调用过 deleteServer，如果有把详情列出来"

---

## 四、CCE — 云容器引擎

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 集群列表 | "我有哪些 CCE 集群？" | `cce_query_clusters` |
| 按版本过滤 | "v1.27 版本的集群有哪些？" | `cce_query_clusters(version=v1.27)` |
| 集群详情 | "把集群 cluster-id-xxx 的网络配置查出来（VPC/CIDR/Endpoint）" | `cce_query_clusters(cluster_id=...)` |
| 节点列表 | "列出集群 xxx 下所有节点和它们的私网 IP" | `cce_query_nodes` |
| 节点详情 | "节点 node-id-yyy 的污点、标签、磁盘配置是什么？" | `cce_query_nodes(node_id=...)` |
| 节点池列表 | "集群 xxx 有几个节点池？分别配置了什么规格？" | `cce_query_nodepools` |
| 节点池详情 | "节点池 pool-id-zzz 的弹性策略和模板配置查一下" | `cce_query_nodepools(nodepool_id=...)` |
| 扩容 | "把集群 xxx 节点池 pool-yyy 扩到 10 个节点" | `cce_update_nodepool` |
| 缩容 | "把节点池 pool-yyy 缩到 3 个节点" | `cce_update_nodepool` ⚠ |
| 任务轮询 | "CCE 缩容任务 job-xxx 现在啥状态？" | `cce_get_job` |
| 确认缩容 | "确认刚才的缩容操作，approval_id=..." | `cce_confirm_destructive` |

### 复合场景

- "集群 xxx 节点池 yyy 当前节点数是多少？需要扩容到 8 个准备承接流量"
- "把集群 xxx 的所有节点 IP 列一下，我要在防火墙上加白名单"

---

## 五、LTS — 日志服务

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 列出日志组 | "我项目下有哪些日志组？" | `lts_query_log_resources` |
| 列出日志流 | "日志组 group-xxx 下有哪些日志流？" | `lts_query_log_resources(log_group_id=...)` |
| 关键词搜索 | "在 group-xxx/stream-yyy 中搜过去 1 小时含 'OutOfMemory' 的日志" | `lts_search_logs` |
| 多关键词 AND | "查 ERROR 且包含 user_id=12345 的日志" | `lts_search_logs(keywords="ERROR user_id=12345")` |
| SQL 聚合 | "按 service 分组统计过去 1 小时的 ERROR 数" | `lts_search_logs(query="level:ERROR \| stats count() by service")` |
| 标签过滤 | "查 host=host-01 的所有日志" | `lts_search_logs(labels={host:host-01})` |
| 上下文 | "日志行号 12345 前后各 50 行给我看下" | `lts_get_log_context` |
| 时间桶 | "过去 6 小时按 5 分钟桶统计含 'timeout' 的日志数量，看看尖峰在哪" | `lts_query_histogram` |
| 告警规则列表 | "我配置了哪些 LTS 关键字告警和 SQL 告警？" | `lts_query_alarm_rules` |
| 告警规则详情 | "把告警规则 rule-xxx 的关键字配置和绑定的日志流查一下" | `lts_query_alarm_rules(rule_id=...)` |
| 活跃告警 | "现在有哪些 LTS 告警在 firing？" | `lts_list_alarm_history(state=active)` |
| 历史告警 | "过去 7 天 Critical 级别的告警都有哪些？" | `lts_list_alarm_history(state=history,level=Critical)` |

### 复合场景

- "过去 1 小时 group-xxx/stream-yyy 出现 OutOfMemory 的频次是多少？挑一个最近的事件把前后 30 行上下文给我"
- "现在告警中心有哪些活跃告警？挑一个最严重的，在对应日志流里搜对应关键字"

---

## 六、CES — 云监控

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 发现指标 | "SYS.ECS 这个 namespace 下有哪些指标可以查？" | `ces_list_metrics(namespace=SYS.ECS)` |
| 实例指标 | "ECS i-xxx 都暴露了哪些监控指标？" | `ces_list_metrics(dim_0="instance_id,i-xxx")` |
| 单指标时序 | "拉一下 ECS i-xxx 过去 1 小时的 CPU 利用率" | `ces_get_metric_data` |
| 批量指标 | "同时拉这 5 台 ECS 过去 1 小时的 CPU 和内存利用率，period=60" | `ces_get_metric_data` |
| 不同聚合 | "RDS 实例 xxx 过去 24 小时的最大连接数（max 聚合，period=3600）" | `ces_get_metric_data(filter=max,period=3600)` |
| 告警规则列表 | "我配置了多少条 CES 告警规则？哪些当前是 alarm 状态？" | `ces_query_alarm_rules(status=alarm)` |
| 告警规则详情 | "告警规则 alarm-xxx 的阈值是什么？绑定了哪些资源？" | `ces_query_alarm_rules(alarm_id=...)` |
| 告警历史 | "过去 7 天 Critical 级别（level=1）的告警都有哪些？" | `ces_list_alarm_histories(level=1)` |
| 资源分组列表 | "我有哪些 CES 资源分组？" | `ces_query_resource_groups` |
| 分组详情 | "资源分组 group-xxx 包含哪些实例？" | `ces_query_resource_groups(group_id=...)` |
| 系统事件 | "过去 24 小时有哪些 OPS 类系统事件？" | `ces_list_event_data(sub_event_type=SUB_EVENT.OPS)` |
| 事件详情 | "事件 modifyInstance 的详细信息查一下" | `ces_list_event_data(event_name=modifyInstance)` |

### 复合场景

- "ECS i-xxx 过去 1 小时 CPU 利用率持续高，把它对应的告警规则、告警历史、相关系统事件全部关联起来给我看"
- "RDS 实例 yyy 过去 6 小时连接数和 CPU 利用率走势，period=300 平均值"

---

## 七、VPC — 虚拟网络 + 安全组

### 网络资源查询

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 列出所有 VPC | "列出当前项目下所有 VPC" | `vpc_describe_vpcs` |
| VPC 详情 | "查看 VPC vpc-id-xxx 的详情，包括 CIDR 和状态" | `vpc_describe_vpcs(vpc_id=...)` |
| 列出子网 | "VPC vpc-id-xxx 下有哪些子网？" | `vpc_describe_subnets` |
| 子网 IP 耗尽 | "哪些子网可用 IP 不足了？" | `vpc_describe_subnets` |
| 子网详情 | "查看子网 subnet-id-xxx 的可用区、可用 IP 数" | `vpc_describe_subnets(subnet_id=...)` |
| 列出对等连接 | "查看所有 VPC 对等连接及其状态" | `vpc_describe_vpc_peerings` |
| 对等连接详情 | "对等连接 peer-id-xxx 是否已激活？" | `vpc_describe_vpc_peerings(peering_id=...)` |
| 列出路由表 | "列出所有路由表及关联子网" | `vpc_describe_route_tables` |
| 路由表详情 | "查看路由表 rt-id-xxx 的路由条目" | `vpc_describe_route_tables(route_table_id=...)` |
| 列出 EIP | "列出所有弹性公网 IP 及绑定状态" | `vpc_describe_eips` |
| EIP 详情 | "EIP eip-id-xxx 绑定在哪个实例上？" | `vpc_describe_eips(eip_id=...)` |
| 列出流日志 | "有哪些 VPC 流日志配置？" | `vpc_list_flow_logs` |
| 流日志详情 | "查看流日志 fl-id-xxx 的详情，包括 LTS 日志组/日志流" | `vpc_list_flow_logs(flow_log_id=...)` |

### 安全组查询

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 列出安全组 | "列出所有安全组" | `vpc_query_security_groups` |
| 安全组详情含规则 | "查看安全组 sg-id-xxx 的所有规则" | `vpc_query_security_groups(security_group_id=...)` |
| 安全组审计 | "审计安全组 sg-id-xxx 是否有高风险规则（SSH 对 0.0.0.0/0 开放）" | `vpc_audit_security_group` |
| 端口可达性 | "sg-id-xxx 上 443 端口从 10.0.0.0/8 是否可达？" | `vpc_check_port_reachability` |
| 关联实例 | "安全组 sg-id-xxx 关联了哪些 ECS 实例？" | `vpc_list_sg_associated_instances` |
| 创建安全组 | "在 VPC vpc-id-xxx 下创建名为 'web-sg' 的安全组" | `vpc_create_security_group` |
| 添加规则 | "给 sg-id-xxx 添加入方向规则，允许 TCP 443 从 10.0.0.0/8" | `vpc_add_security_group_rule` |
| 删除规则 | "从 sg-id-xxx 删除规则 rule-id-xxx" | `vpc_remove_security_group_rule` ⚠ |

### 写操作（含两阶段确认）

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 绑定 EIP | "把 EIP eip-id-xxx 绑定到 ECS 端口 port-id-yyy" | `vpc_associate_eip` |
| 解绑 EIP | "把 EIP eip-id-xxx 从端口解绑" | `vpc_disassociate_eip` ⚠ |
| 添加路由 | "给路由表 rt-id-xxx 添加路由：目的 10.1.0.0/16 下一跳对等连接 peer-id-xxx" | `vpc_add_route` |
| 删除路由 | "从路由表 rt-id-xxx 删除到 10.1.0.0/16 的路由" | `vpc_delete_route` ⚠ |
| 确认执行 | "确认解绑 EIP，approval_id=abc-123" | `vpc_confirm_destructive` |

### 流日志数据查询

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 最近流日志 | "查看流日志 fl-id-xxx 最近 1 小时的记录" | `vpc_query_flow_log_data` |
| 被拒绝的流量 | "流日志 fl-id-xxx 最近 30 分钟有哪些被拒绝的流量？" | `vpc_query_flow_log_data(action=reject)` |
| 按源 IP 过滤 | "查看流日志 fl-id-xxx 中来自 10.0.1.5 的流量" | `vpc_query_flow_log_data(src_ip=10.0.1.5)` |
| 按目的过滤 | "查看到 10.0.2.100 端口 443 的流量" | `vpc_query_flow_log_data(dst_ip=10.0.2.100,dst_port=443)` |

### 复合场景

- "哪些子网可用 IP 不到 10 个？列出它们的 VPC 和可用区"
- "对等连接 peer-id-xxx 是否激活？如果是，列出经过它的路由表"
- "EIP eip-id-xxx 绑定在哪个实例上？给我看那个实例的安全组并审计风险"
- "流日志 fl-id-xxx 显示 10.0.1.5 到端口 3306 的流量被拒绝——检查目的端安全组是否允许该端口"

---

## 八、RDS — 关系数据库服务

### 实例与资源查询

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 列出所有实例 | "列出当前项目下所有 RDS 实例" | `rds_describe_instances` |
| 按引擎过滤 | "列出所有 MySQL RDS 实例" | `rds_describe_instances(datastore_type=MySQL)` |
| 实例详情 | "查看 RDS rds-xxx 的完整详情，包括节点、磁盘、备份策略" | `rds_describe_instances(instance_id=...)` |
| 错误日志 | "查看 rds-xxx 过去 1 小时的错误日志" | `rds_get_db_logs(log_type=error)` |
| 按级别过滤错误日志 | "只看 rds-xxx 过去 2 小时 ERROR 级别的日志" | `rds_get_db_logs(log_type=error, level=error)` |
| 高频慢查询 | "找出 rds-xxx 过去 1 小时执行最频繁的慢 SQL" | `rds_get_db_logs(log_type=slow, sort_by=count)` |
| 最慢查询 | "找出 rds-xxx 过去 6 小时最慢的查询" | `rds_get_db_logs(log_type=slow, sort_by=duration)` |
| 过滤慢查询 | "查看 rds-xxx 上 mydb 库中平均耗时 > 500ms 的慢查询" | `rds_get_db_logs(log_type=slow, database=mydb, min_duration_ms=500)` |
| 列出数据库 | "RDS rds-xxx 上有哪些数据库？" | `rds_list_db_resources(resource_type=databases)` |
| 列出账号 | "列出 rds-xxx 的所有数据库账号及权限" | `rds_list_db_resources(resource_type=accounts)` |
| 备份列表 | "查看 rds-xxx 最近 10 个备份" | `rds_list_backups` |
| 仅手动备份 | "rds-xxx 有哪些手动备份？" | `rds_list_backups(backup_type=manual)` |
| 实例指标 | "拉一下 rds-xxx 过去 30 分钟的 CPU、内存、IOPS" | `rds_get_instance_metrics` |
| 自定义指标 | "查看 rds-xxx 过去 1 小时的活跃连接数，5 分钟平均值" | `rds_get_instance_metrics(metrics=[rds004_connections], period=300)` |
| 参数组列表 | "列出所有 RDS 参数组" | `rds_describe_parameter_group` |
| 实例参数 | "查看 rds-xxx 当前应用的参数配置" | `rds_describe_parameter_group(instance_id=...)` |
| 参数组详情 | "查看参数组 cfg-xxx 的参数列表" | `rds_describe_parameter_group(config_id=...)` |
| 只读副本 | "rds-xxx 有只读副本吗？复制延迟多少？" | `rds_list_replicas` |

### 安全审计与备份

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 安全审计 | "审计 RDS rds-xxx 的安全风险" | `rds_audit_instance_security` |
| 变更前备份 | "我要改 rds-xxx 的参数，先创建一个手动备份" | `rds_create_manual_backup` ⚠ |
| 确认备份 | "确认创建备份，approval_id=..." | `rds_confirm_destructive` |

### 复合场景

- "审计所有 RDS 实例的安全风险，列出有高危发现的实例"
- "rds-xxx 响应慢——先拉慢查询日志按频率排序，再拉 CPU/IOPS 指标关联分析"
- "变更 rds-xxx 参数前：检查当前配置、确认最近备份可用、创建手动备份"

---

## 九、OBS — 对象存储服务

### 桶与对象查询（只读）

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 列出所有桶 | "列出我账号下所有 OBS 桶" | `obs_describe_buckets` |
| 桶详情 | "查看桶 my-bucket 的存储类型和版本控制状态" | `obs_describe_buckets(bucket_name=...)` |
| 列出对象 | "列出桶 my-bucket 中的所有对象" | `obs_list_objects` |
| 前缀过滤 | "列出桶 my-bucket 中 logs/2024-06/ 前缀下的对象" | `obs_list_objects(prefix=logs/2024-06/)` |
| 目录结构 | "用 '/' 分隔符展示桶 my-bucket 的目录结构" | `obs_list_objects(delimiter=/)` |
| 对象元数据 | "查看 my-bucket/config/app.yaml 的大小和类型，不要下载" | `obs_get_object` |
| 对象内容 | "读取 my-bucket/config/app.yaml 的内容（小文件）" | `obs_get_object(include_content=True)` |
| 列出版本 | "列出 my-bucket/important.doc 的所有历史版本（已开启版本控制）" | `obs_list_objects(include_versions=True)` |
| 预签名下载 URL | "为 my-bucket/report.pdf 生成一个 1 小时有效的下载链接" | `obs_generate_presigned_url(method=GET, expires=3600)` |
| 预签名上传 URL | "为 my-bucket/uploads/file.txt 生成一个 2 小时有效的上传链接" | `obs_generate_presigned_url(method=PUT, expires=7200)` |
| 桶 ACL | "查看桶 my-bucket 的 ACL 和公开访问状态" | `obs_describe_bucket_policy` |
| 生命周期规则 | "桶 my-bucket 配了什么生命周期规则？" | `obs_describe_bucket_lifecycle` |

### 安全审计

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 桶安全审计 | "审计桶 my-bucket 的安全风险" | `obs_audit_bucket_security` |
| 批量审计 | "审计我所有 OBS 桶的公开访问和加密状态" | `obs_audit_bucket_security`（循环） |

### 写操作（含两阶段确认）

| 场景 | 提问案例 | 触发工具 |
|------|---------|---------|
| 上传配置 | "把这份 JSON 配置上传到 my-bucket/config/deploy.json" | `obs_upload_object` |
| 创建桶 | "在 af-south-1 创建一个私有桶 'ci-artifacts'" | `obs_create_bucket` |
| 删除对象 | "删除 my-bucket/temp/old-report.csv" | `obs_delete_object` ⚠ |
| 确认删除 | "确认删除对象，approval_id=..." | `obs_confirm_destructive` |
| 设置桶策略 | "给桶 my-bucket 设置公开读策略" | `obs_set_bucket_policy` ⚠ |
| 确认策略 | "确认更新桶策略，approval_id=..." | `obs_confirm_destructive` |

### 复合场景

- "审计所有 OBS 桶的安全风险，列出有高危发现的桶"
- "为 my-bucket/report.pdf 生成预签名下载链接，用 curl 验证可用"
- "列出 my-bucket/logs/ 前缀下过去 7 天的对象，再查生命周期规则看哪些即将被删除"
- "从 my-bucket 读取 deploy.json 配置，检查是否引用了 RDS 实例，审计这些实例的安全"

---

## 十、跨服务复合场景（Agent 编排）

下面这些场景需要 Agent 自主串联多个工具，体现 MCP Server 的真正价值：

### 1. 事故复盘 — 谁动了我的服务器

> "过去 2 小时 ECS i-xxx 网络中断，请帮我定位：
>  1. 这台机器现在的电源/网络状态
>  2. 过去 2 小时是否有人对它做过操作（审计）
>  3. CES 上 CPU/网络入流量曲线
>  4. 关联日志中是否有异常"

涉及工具：`ecs_get_server` → `cts_search_traces(resource_id=...)` → `ces_get_metric_data` → `lts_search_logs`

### 2. 流水线发布前置检查

> "我要上线流水线 abc-123：
>  1. 看下它当前配置和默认分支
>  2. 最近 5 次运行成功率
>  3. 触发执行
>  4. 监控 job 状态直到完成"

涉及工具：`pipeline_get_detail` → `pipeline_list` → `pipeline_run` → 轮询

### 3. CCE 容量规划

> "集群 cluster-xxx：
>  1. 当前所有节点池配置和节点数
>  2. 节点的 CES CPU/内存使用率
>  3. 找出利用率 < 30% 的节点池，建议缩容到 X 节点"

涉及工具：`cce_query_nodepools` → `cce_query_nodes` → `ces_get_metric_data` → `cce_update_nodepool`

### 4. 告警风暴定位

> "现在 LTS 和 CES 各有哪些活跃告警？
>  按时间排序合并，挑前 3 个：
>  1. LTS 告警 → 关联日志流上下文
>  2. CES 告警 → 关联指标曲线 + 告警历史"

涉及工具：`lts_list_alarm_history` + `ces_list_alarm_histories` → `lts_get_log_context` + `ces_get_metric_data`

### 5. 资源审计快照

> "给我打一份当前项目的资源快照：
>  - ECS 总数、状态分布
>  - CCE 集群数、节点总数
>  - 流水线总数、最近 24h 失败数
>  - 当前 firing 告警数（LTS + CES）"

涉及工具：`ecs_list_servers` + `cce_query_clusters` + `cce_query_nodes` + `pipeline_list` + `lts_list_alarm_history` + `ces_query_alarm_rules`

### 6. 网络连通性诊断

> "ECS i-xxx 访问不到 10.0.2.100:443，帮我排查：
>  1. i-xxx 在哪个 VPC 和子网？
>  2. 它的路由表里有没有到 10.0.2.0/24 的路由？
>  3. 安全组是否允许出方向到 10.0.2.100:443？
>  4. 目的端安全组是否允许入方向 443 端口？
>  5. 查流日志看 i-xxx 到 10.0.2.100 有没有被拒绝"

涉及工具：`ecs_get_server` → `vpc_describe_subnets` → `vpc_describe_route_tables` → `vpc_check_port_reachability` → `vpc_query_flow_log_data`

### 7. RDS 慢查询性能分析

> "RDS rds-xxx 性能劣化：
>  1. 找出高频慢 SQL 模式（按执行次数排序）
>  2. 拉 CPU 和 IOPS 指标确认资源瓶颈
>  3. 检查参数组的 buffer pool / query cache 配置
>  4. 基于 SQL 模式给出索引优化建议"

涉及工具：`rds_get_db_logs(log_type=slow, sort_by=count)` → `rds_get_instance_metrics` → `rds_describe_parameter_group` → AI 分析

### 8. RDS 数据库连接超时诊断

> "应用报 rds-xxx 数据库连接超时：
>  1. 实例状态是否正常？连接数是否打满？
>  2. 拉过去 30 分钟的连接数和 CPU 指标
>  3. 查错误日志是否有 too many connections
>  4. 检查只读副本延迟
>  5. 验证安全组是否放通 3306 端口"

涉及工具：`rds_describe_instances` → `rds_get_instance_metrics` → `rds_get_db_logs(log_type=error)` → `rds_list_replicas` → `vpc_check_port_reachability`

### 9. RDS 变更前安全检查

> "我要修改 rds-xxx 的参数：
>  1. 确认最近备份存在且状态正常
>  2. 审计当前安全状态
>  3. 创建手动备份作为安全保障
>  4. 查看当前参数值以确认变更内容"

涉及工具：`rds_list_backups` → `rds_audit_instance_security` → `rds_create_manual_backup` → `rds_confirm_destructive` → `rds_describe_parameter_group(instance_id=...)`

### 10. OBS 桶安全批量扫描

> "审计我所有 OBS 桶：
>  1. 列出所有桶
>  2. 逐个检查公开 ACL、未加密、未开启版本控制
>  3. 标记有公开读 ACL 且包含敏感数据（配置文件、数据库导出）的桶
>  4. 生成报告并上传到安全桶"

涉及工具：`obs_describe_buckets` → `obs_audit_bucket_security`（循环）→ `obs_list_objects` → `obs_upload_object`

---

## 十一、两阶段确认（破坏性操作）使用提示

破坏性工具会返回 `{status: "pending_approval", approval_id: "..."}`，Agent 应：

1. **复述变更** — 把 preview 内容（影响范围、from/to）原样展示给用户
2. **等待显式确认** — "确认执行 / yes / 继续" 才调用 `*_confirm_destructive`
3. **TTL 注意** — approval_id 120 秒后过期，超时需重新发起

示例对话：

```
用户: 把节点池 pool-yyy 缩到 3 个节点
Agent: ⚠ 即将缩容 pool-yyy: 当前 8 个节点 → 目标 3 个，将驱逐 5 个节点上的 Pod。
       approval_id=abc-123，确认执行请回复"确认"。
用户: 确认
Agent: [调用 cce_confirm_destructive(approval_id=abc-123)] → 任务已下发，job_id=...
```

---

## 附录：常用 namespace 速查（CES）

| Namespace | 服务 |
|-----------|------|
| `SYS.ECS` | 云服务器 |
| `SYS.RDS` | 关系数据库 |
| `SYS.DCS` | Redis 缓存 |
| `SYS.ELB` | 负载均衡 |
| `SYS.CCE` | 容器集群节点 |
| `SYS.FunctionGraph` | 函数工作流 |
| `SYS.VPC` | 虚拟私有云 |
| `SYS.EVS` | 云硬盘 |
