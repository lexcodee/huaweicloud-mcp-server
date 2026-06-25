# 华为云 MCP Server — Agent 提问案例

本文档汇总在 Agent（Hermes / Claude Code 等）中调用本 MCP Server 各工具的**自然语言提问案例**，可直接复制粘贴使用。所有提问均以一线 SRE / DevOps / 后端工程师视角组织。

> 覆盖 6 个服务、34 个工具：ECS · Pipeline · CTS · CCE · LTS · CES

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

## 七、跨服务复合场景（Agent 编排）

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

---

## 八、两阶段确认（破坏性操作）使用提示

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
