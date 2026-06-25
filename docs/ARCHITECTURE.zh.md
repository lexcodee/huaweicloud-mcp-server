# 架构

## 项目结构

```
huaweicloud-mcp-server/          # ← workspace 根目录
├── start.sh                       ← 启动脚本（加载 .env + 启动网关）
├── start.ps1                      ← Windows 等价脚本（PowerShell）
├── .env                           ← 统一环境变量（AK/SK + JWT + 配置）
├── .env.example                   ← 全量模板
├── manifest.yaml                  ← 服务拓扑（单挂载 /hwc）
├── pyproject.toml                 ← uv workspace 声明
│
├── huaweicloud-mcp-server/        ← 统一华为云 MCP Server
│   └── src/huaweicloud_mcp/
│       ├── server.py              ← build_server(enabled=[...]) → FastMCP
│       ├── config.py              ← 统一 Settings (AK/SK/region/project_id)
│       ├── client.py              ← get_client(service, settings) — lru_cached
│       ├── errors.py              ← ToolError, 两阶段提交
│       ├── logging_setup.py       ← SecretMaskingFilter + 脱敏日志
│       └── services/
│           ├── ecs/               ← 8 工具 (list/get/power/delete/resize)
│           ├── pipeline/          ← 6 工具 (list/get/run/update/toggle)
│           ├── cts/               ← 2 工具 (search/get 审计事件)
│           ├── cce/               ← 6 工具 (query clusters/nodes/nodepools, update nodepool, get_job)
│           ├── lts/               ← 6 工具 (query log resources, search logs, alarm rules/history)
│           ├── ces/               ← 6 工具 (list metrics, get metric data, alarm rules/history, resource groups, events)
│           ├── vpc/               ← 19 工具 (VPC/子网/对等连接/路由表/EIP/流日志查询, 安全组审计, EIP/路由写操作)
│           └── rds/               ← 10 工具 (实例查询, 错误/慢日志, 数据库资源, 备份, 监控指标, 参数组, 只读副本, 安全审计)
│
├── mcp-auth-common/               ← 共享鉴权库 (Identity / AutoAuth / require_role)
│   └── src/mcp_auth_common/
│
└── mcp-gateway/                   ← ASGI 网关 (Starlette Mount + JWT 中间件)
    ├── src/mcp_gateway/
    └── deploy/                    ← systemd + Nginx 配置
```

## 共享基础设施

| 模块 | 用途 |
|------|------|
| `config.py` | 单一 `Settings` dataclass — AK/SK/region/project_id/timezone。`load_settings()` 从环境变量读取，校验必需项，缺失时快速退出。 |
| `client.py` | `get_client(service, settings)` → 缓存的 SDK 客户端。ECS、Pipeline、CTS、CCE、LTS、CES、VPC、EIP、RDS 共用一个工厂，共享 HttpConfig（超时、重试）。 |
| `errors.py` | `ToolError` 异常 + `wrap_tool` 装饰器：捕获 SDK 错误，标准化为 `{ok: false, error: {...}}` 信封，记录结构化事件。`PendingActions` 实现两阶段提交。 |
| `logging_setup.py` | `SecretMaskingFilter` 在日志中脱敏 AK/SK。`setup_logging()` 配置仅 stderr（stdio 安全）或文件日志。 |

## 共享鉴权库（mcp-auth-common）

| 组件 | 说明 |
|------|------|
| `Identity` | pydantic v2 模型：`sub` / `roles` / `tenant` / `iat` / `exp` |
| `AutoAuth` | 自动检测鉴权策略：有 gateway identity → 使用；否则合成 dev Identity + WARN |
| `AuthStrategy` | 抽象基类 |
| `require_role()` | 角色校验，支持 admin ⊃ operator ⊃ readonly 层级 |
| `set_request_scope()` / `current_scope()` | contextvar 管道，工具函数无需 `ctx` 参数即可获取 scope |

## 测试结构

```bash
# 统一 Server
uv run pytest huaweicloud-mcp-server/tests/ -q

# 网关
uv run pytest mcp-gateway/tests/ -q

# 全部
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

| 类别 | 数量 | 覆盖内容 |
|------|------|----------|
| ECS 工具 | 52 | list/get/power/delete/resize/confirm/job |
| Pipeline 工具 | 48 | list/get/run/update/toggle/confirm |
| CTS 工具 | 36 | search/detail + time_utils + mask_utils + 7 天窗口 |
| CCE 工具 | 30 | query clusters/nodes/nodepools + update nodepool + get_job + confirm + DefaultPool 拒绝 |
| LTS 工具 | 30 | discovery + search + alarm rules/history + histogram + context |
| CES 工具 | 16 | list metrics + get metric data + alarm rules/histories + resource groups + event data |
| VPC 工具 | 33 | SG query/audit + network describe + EIP associate/disassociate + route add/delete + flow-log query + confirm |
| RDS 工具 | 24 | describe_instances + get_db_logs (error+slow) + list_db_resources + list_backups + get_instance_metrics + describe_parameter_group + list_replicas + create_manual_backup (two-phase) + audit_instance_security |
| 配置 / 客户端 | 16 | Settings 校验、客户端工厂、缓存 |
| 网关鉴权 | 10 | JWT 验签 + RBAC + Identity 注入 + 永久 token |
| 网关 dev 模式 | 10 | 免 JWT / loopback / open / disabled |
| 结构化日志 | 9 | JSON 格式 / extra 字段 / 审计事件 |
| 工具级 RBAC | 14 | 角色层级 + 四服务授权矩阵 |
| Manifest 覆盖 | 9 | 三层覆盖 + 跳过原因 + 去重 |
| 工厂模式 | 9 | build_kwargs 解析 + 工厂调用 + 异常 |
| SSE 前缀回归 | 1 | 无 /hwc/hwc 双前缀 |
| Token CLI | 18 | keygen + create + verify + 永久 token + 端到端往返 |
| 组合 lifespan | 4 | 多 FastMCP 挂载 |
