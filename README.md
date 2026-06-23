# 华为云 MCP Server

[English](README.en.md) | **中文**

一个 MCP Server 覆盖全部华为云服务。Agent 只需对接 **一个 URL**，即可访问所有已启用的云服务工具。按需启动服务子集，JWT 鉴权保障生产安全，新增云服务无需 Agent 侧任何配置变更。

**已上线**：ECS（云主机）、CodeArts Pipeline（流水线）、CTS（审计日志）、CCE（云容器引擎）
**开发中**：OBS（对象存储）、RDS（关系数据库）、VPC（虚拟网络）…

```
https://example.com/hwc/sse    ← 全部华为云工具 (ecs_*, pipeline_*, cts_*, obs_*, …)
https://example.com/healthz    ← 网关探活（免鉴权）
```

**核心设计**：

| 特性 | 说明 |
|------|------|
| 单 URL 对接 | Agent 配置一个 MCP Server 条目，永久不变 |
| 按需启用 | `MCP_ENABLED_SERVICES=ecs,pipeline` 仅加载所需服务 |
| JWT 鉴权 | 生产环境 RS256 签验 + 角色 RBAC；本地开发免鉴权 |
| 两阶段提交 | 破坏性操作（删除/关机/变更规格）需用户显式确认 |
| 零配置扩展 | 新增云服务只改服务端，Agent 无感知 |

---

## 项目结构

```
huaweicloud-mcp-server/          # ← workspace 根目录
├── start.sh                       ← 启动脚本（加载 .env + 启动网关）
├── .env                           ← 统一环境变量（AK/SK + JWT + 配置）
├── .env.example                   ← 全量模板
├── manifest.yaml                  ← 服务拓扑（策略 1：单挂载 /hwc）
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
│           └── cce/               ← 6 工具 (query clusters/nodes/nodepools, update nodepool, get_job)
│
├── mcp-auth-common/               ← 共享鉴权库 (Identity / AutoAuth / require_role)
│   └── src/mcp_auth_common/
│
└── mcp-gateway/                   ← ASGI 网关 (Starlette Mount + JWT 中间件)
    ├── src/mcp_gateway/
    └── deploy/                    ← systemd + Nginx 配置
```

### huaweicloud_mcp 内部架构

```
huaweicloud_mcp/
├── __init__.py
├── config.py          # 统一 Settings dataclass + load_settings()
├── client.py          # SDK 客户端工厂: get_client("ecs", settings) — lru_cached
├── errors.py          # ToolError, wrap_tool 装饰器, PendingActions（两阶段提交）
├── logging_setup.py   # SecretMaskingFilter + setup_logging()
├── server.py          # build_server(enabled={"ecs","pipeline","cts","cce"}) → FastMCP
├── app.py             # ASGI 入口（SSE/HTTP，含 keep-alive 中间件）
└── services/
    ├── ecs/
    │   ├── make_tools.py    # make_tools(settings) → dict
    │   ├── models.py        # Pydantic 输入模型
    │   ├── serializers.py   # SDK 响应 → plain dict
    │   └── tools/
    │       ├── query.py     # list_servers, get_server, list_flavors
    │       ├── lifecycle.py # power_action, delete_server, resize_server, confirm_destructive
    │       └── job.py       # get_job_status
    ├── pipeline/
    │   ├── make_tools.py
    │   ├── models.py
    │   ├── serializers.py
    │   ├── client_helpers.py    # SDK 类型/非类型 API 绕行
    │   ├── definition_utils.py  # 流水线定义 JSON 操作
    │   └── tools/
    │       ├── query.py      # list, get_detail
    │       ├── execution.py  # run
    │       ├── lifecycle.py  # set_status, confirm_destructive
    │       └── update.py     # update_info, confirm_destructive
    └── cts/
        ├── make_tools.py
        ├── models.py
        ├── serializers.py
        ├── time_utils.py     # 人类可读时间 → 13 位 UTC 毫秒
        ├── mask_utils.py     # 敏感值脱敏
        └── tools/
            ├── search.py     # search_traces
            └── detail.py     # get_trace_detail
    └── cce/
        ├── make_tools.py
        ├── models.py
        ├── serializers.py
        └── tools/
            ├── query.py      # query_clusters, query_nodes, query_nodepools
            ├── update.py     # update_nodepool, confirm_destructive
            └── job.py        # get_job
```

### 共享基础设施

| 模块 | 用途 |
|------|------|
| `config.py` | 单一 `Settings` dataclass — AK/SK/region/project_id/timezone。`load_settings()` 从环境变量读取，校验必需项，缺失时快速退出。 |
| `client.py` | `get_client(service, settings)` → 缓存的 SDK 客户端。ECS、Pipeline、CTS、CCE 共用一个工厂，共享 HttpConfig（超时、重试）。 |
| `errors.py` | `ToolError` 异常 + `wrap_tool` 装饰器：捕获 SDK 错误，标准化为 `{ok: false, error: {...}}` 信封，记录结构化事件。`PendingActions` 实现两阶段提交。 |
| `logging_setup.py` | `SecretMaskingFilter` 在日志中脱敏 AK/SK。`setup_logging()` 配置仅 stderr（stdio 安全）或文件日志。 |

---

## MCP 工具一览（21 个）

### ECS — 云主机生命周期管理（8 个）

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

### Pipeline — CodeArts 流水线管理（6 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `pipeline_list` | 列出流水线 + 最近运行状态 | readonly |
| `pipeline_get_detail` | 查看流水线完整配置 | readonly |
| `pipeline_run` | 触发流水线执行 | operator |
| `pipeline_set_status` | ⚠ 启用 / 禁用流水线 | admin |
| `pipeline_update_info` | ⚠ 修改默认分支 / 触发方式 | admin |
| `pipeline_confirm_destructive` | 确认执行待定的破坏性操作 | — |

### CTS — 审计日志检索（2 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `cts_search_traces` | 按时间 + 条件搜索审计事件（7 天窗口） | readonly |
| `cts_get_trace_detail` | 查看单条事件的完整请求/响应体（敏感值脱敏） | readonly |

### CCE — 云容器引擎管理（6 个）

| 工具 | 说明 | 最低角色 |
|------|------|----------|
| `cce_query_clusters` | 列出集群 / 查看单个集群详情 | readonly |
| `cce_query_nodes` | 列出集群节点 / 查看单个节点详情 | readonly |
| `cce_query_nodepools` | 列出节点池 / 查看单个节点池详情 | readonly |
| `cce_update_nodepool` | ⚠ 调整节点池期望节点数（缩容需两阶段确认；DefaultPool 不支持缩放） | operator |
| `cce_get_job` | 查询异步任务状态（集群创建/升级/节点池缩放等） | readonly |
| `cce_confirm_destructive` | 确认执行待定的破坏性操作（缩容） | — |

> 角色层级：**admin** ⊃ **operator** ⊃ **readonly**

---

## 两阶段提交（破坏性操作）

破坏性工具（关机、重启、删除、变更规格、禁用流水线、修改流水线、缩容节点池）遵循两阶段提交模式，防止误操作：

```
阶段 1: 工具调用返回预览 + approval_id（TTL 120 秒）
         → {status: "pending_approval", approval_id: "...", preview: {...}}

阶段 2: 用户显式确认
         → ecs_confirm_destructive(approval_id="...")
         → 操作执行，返回 {ok: true, data: {...}}
```

若 approval_id 过期，重新发起原始调用获取新的 ID。

---

## 网关架构（策略 1）

```
                          ┌──────────────────────────────────────┐
                          │       MCP Gateway (port 8080)        │
                          │                                      │
  Agent ──Bearer JWT──▶  │  GatewayAuthMiddleware                │
                          │    ├─ JWT 验签 (RS256)               │
                          │    ├─ 路径 RBAC（粗粒度）            │
                          │    └─ 注入 Identity → scope          │
                          │                                      │
                          │  单挂载点：                           │
                          │    /hwc  → build_server(             │
                          │             enabled=[ecs,pipeline,cts│
                          │                        ,cce]         │
                          │           )                           │
                          └──────────────────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  统一 FastMCP     │
                          │  21 个工具：      │
                          │    ecs_* (8)      │
                          │    pipeline_* (6) │
                          │    cts_* (2)      │
                          │    cce_* (5+1)    │
                          └──────────────────┘
```

### 鉴权分层

| 层级 | 职责 | 粒度 | 示例 |
|------|------|------|------|
| 网关中间件 | 验签 JWT → 解析 Identity → 路径 RBAC → 注入 scope | `/hwc/*` | 无 hwc 权限 → 403 |
| MCP Server | 从 scope 读 Identity → 按 tool 名做角色判断 | `ecs_delete` vs `ecs_list` | 非 admin 调 delete → ToolError |

### Server 侧鉴权：自动检测，零配置

| 场景 | 行为 | 说明 |
|------|------|------|
| 在网关后面 | `scope["mcp_identity"]` 存在 → 直接使用 | 网关已验签，Identity 可信 |
| 独立启动（stdio/SSE） | 无 gateway identity → 合成 dev Identity + ⚠ WARN | 本地开发，自动放行 |

### 网关鉴权模式

| 模式 | 环境变量 | 行为 | 场景 |
|------|---------|------|------|
| `jwt` | `MCP_GATEWAY_AUTH_MODE=jwt`（默认） | 完整 JWT 验签 + 路径 RBAC | 生产 |
| `dev` | `MCP_GATEWAY_AUTH_MODE=dev` | 跳过 JWT，合成 Identity | 非生产 |

dev 模式通过 `MCP_DEV_LOOPBACK_ONLY` 控制来源限制：

| 子模式 | 环境变量 | 行为 | 场景 |
|--------|---------|------|------|
| loopback-only | `MCP_DEV_LOOPBACK_ONLY=true`（默认） | 仅 loopback 调用者放行 | 本地开发 |
| open | `MCP_DEV_LOOPBACK_ONLY=false` | 任何来源放行（CRITICAL 日志） | CI / 隔离测试 |

---

## 快速开始

### 前置条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- 华为云 AK/SK

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

编辑根目录 `.env`：

```bash
# 华为云凭证（所有服务共用）
HUAWEICLOUD_ACCESS_KEY_ID=your-ak
HUAWEICLOUD_SECRET_ACCESS_KEY=your-sk
HUAWEICLOUD_REGION=cn-north-4
HUAWEICLOUD_PROJECT_ID=your-project-id
CODEARTS_DEFAULT_PROJECT_ID=your-codearts-project-id

# 网关鉴权模式（本地用 dev，生产用 jwt）
MCP_GATEWAY_AUTH_MODE=dev
MCP_GATEWAY_HOST=127.0.0.1
```

### 3. 启动网关

三种方式任选其一：

**方式 A — 启动脚本（推荐）**

自动加载 `.env`，默认 `127.0.0.1:8080`：

```bash
./start.sh
```

**方式 B — CLI 命令**

```bash
mcp-gateway serve --manifest manifest.yaml --host 0.0.0.0 --port 8080 --log-level info
```

常用选项：

| 选项 | 环境变量 | 默认值 | 说明 |
|------|---------|--------|------|
| `--manifest` | `MCP_GATEWAY_MANIFEST` | `manifest.yaml` | 服务拓扑文件 |
| `--enable <svc>` | `MCP_GATEWAY_ENABLED_SERVICES` | — | 启用指定服务（覆盖 manifest + 环境变量） |
| `--disable <svc>` | — | — | 禁用指定服务 |
| `--host` | `MCP_GATEWAY_HOST` | `0.0.0.0` | 监听地址 |
| `--port` | `MCP_GATEWAY_PORT` | `8080` | 监听端口 |
| `--log-level` | `MCP_GATEWAY_LOG_LEVEL` | `info` | 日志级别 |
| `--print-only` | — | — | 仅构建 app 打印挂载计划，不启动 uvicorn（调试用） |

**方式 C — uvicorn 直接加载 ASGI app**

```bash
uvicorn mcp_gateway.gateway:app --factory --host 0.0.0.0 --port 8080
```

模块级 `app` 是 lazy factory callable，需配合 `--factory` 使用，uvicorn 在首次请求时才解析，避免 import-time 副作用。

### 4. 验证

```bash
curl http://127.0.0.1:8080/healthz
# {"status":"ok","mounted":[{"name":"huaweicloud","mount_path":"/hwc"}]}
```

### 5. 签发 JWT Token（生产环境）

```bash
# 生成密钥对
mcp-gateway token keygen

# 签发 token
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# 携带 token 调用网关
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/hwc/sse
```

## 独立 stdio 模式（本地开发，无需网关）

统一 Server 可直接通过 stdio 运行，无需网关或 JWT：

```bash
# 全部服务（21 个工具）
huaweicloud-mcp-server

# 仅启用子集
MCP_ENABLED_SERVICES=ecs,pipeline huaweicloud-mcp-server

# SSE 模式
MCP_TRANSPORT=sse MCP_PORT=8000 huaweicloud-mcp-server
```

---

## Agent 配置

> stdio 模式下 AK/SK/Region 等凭证必须通过 `env` 传入（进程不继承 shell 环境变量）。
> SSE 模式通过网关鉴权，凭证在网关侧配置，Agent 侧仅传 JWT token。

### Hermes Agent

添加到 `~/.hermes/config.yaml`。

**stdio（本地开发，推荐）**

```yaml
mcp_servers:
  huaweicloud:
    command: /path/to/.venv/bin/huaweicloud-mcp-server
    timeout: 120
    env:
      HUAWEICLOUD_ACCESS_KEY_ID: your_ak
      HUAWEICLOUD_SECRET_ACCESS_KEY: your_sk
      HUAWEICLOUD_REGION: af-south-1
      HUAWEICLOUD_PROJECT_ID: your_project_id
      CODEARTS_DEFAULT_PROJECT_ID: your_pipeline_project_id
    # 可选：仅启用服务子集
    # env:
    #   MCP_ENABLED_SERVICES: ecs,pipeline
```

**SSE via 网关（生产）**

```yaml
mcp_servers:
  huaweicloud:
    url: http://127.0.0.1:8080/hwc/sse
    transport: sse
    timeout: 120
    connect_timeout: 30
    headers:
      Authorization: Bearer eyJhbG...
```

验证：

```bash
hermes mcp test huaweicloud
#   ✓ Connected (643ms)
#   ✓ Tools discovered: 21
```

### Claude Code

添加到 `~/.claude/mcp.json`（或项目级 `.claude/mcp.json`）。

**stdio（本地开发）**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "command": "/path/to/.venv/bin/huaweicloud-mcp-server",
      "timeout": 120,
      "env": {
        "HUAWEICLOUD_ACCESS_KEY_ID": "your_ak",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "your_sk",
        "HUAWEICLOUD_REGION": "af-south-1",
        "HUAWEICLOUD_PROJECT_ID": "your_project_id",
        "CODEARTS_DEFAULT_PROJECT_ID": "your_pipeline_project_id"
      }
    }
  }
}
```

**SSE via 网关（生产）**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "url": "http://127.0.0.1:8080/hwc/sse",
      "transport": "sse",
      "timeout": 120,
      "headers": {
        "Authorization": "Bearer eyJhbG..."
      }
    }
  }
}
```

### Claude Desktop / Cursor / Cline

添加到 `claude_desktop_config.json`（macOS: `~/Library/Application Support/Claude/`，
Windows: `%APPDATA%\Claude\`）。

**stdio（本地开发）**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "command": "/path/to/.venv/bin/huaweicloud-mcp-server",
      "env": {
        "HUAWEICLOUD_ACCESS_KEY_ID": "your_ak",
        "HUAWEICLOUD_SECRET_ACCESS_KEY": "your_sk",
        "HUAWEICLOUD_REGION": "af-south-1",
        "HUAWEICLOUD_PROJECT_ID": "your_project_id"
      }
    }
  }
}
```

**SSE via 网关（生产）**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "url": "http://127.0.0.1:8080/hwc/sse",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer eyJhbG..."
      }
    }
  }
}
```

> **核心要点**：无论未来新增多少华为云服务，Agent 始终只需配置**一个** MCP Server 条目。新服务以新工具名（`obs_*`、`rds_*`、…）自动出现，无需 Agent 侧任何配置变更。

---

## Token CLI

网关内置 Token 管理命令行工具。

### `mcp-gateway token keygen` — 生成 RSA 密钥对

```bash
mcp-gateway token keygen                              # 默认: jwt-private.pem / jwt-public.pem / 2048 位
mcp-gateway token keygen --bits 4096                  # 更强密钥
mcp-gateway token keygen --private-key /etc/mcp/jwt-private.pem \
                          --public-key  /etc/mcp/jwt-public.pem
```

### `mcp-gateway token create` — 签发 JWT

```bash
# 最简 — 输出原始 JWT 字符串
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# 完整选项
mcp-gateway token create \
  --sub ops-bot \
  --roles operator,readonly \
  --private-key jwt-private.pem \
  --issuer mcp-gateway \
  --audience mcp-api \
  --tenant proj-abc \
  --ttl 7200 \
  --format json

# 永久 token（不过期）
mcp-gateway token create --sub service-account --roles admin --private-key jwt-private.pem --ttl 0
```

| 标志 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `--sub` | 是 | — | 主体（用户或服务账号 ID） |
| `--roles` | 是 | — | 逗号分隔角色列表 |
| `--private-key` | 否 | `jwt-private.pem` | RSA 私钥 PEM 路径 |
| `--issuer` | 否 | `mcp-gateway` | JWT `iss` 声明 |
| `--audience` | 否 | — | JWT `aud` 声明 |
| `--tenant` | 否 | — | 租户 / 项目 ID |
| `--ttl` | 否 | `3600` | 有效期秒数；`0` = 永久 |
| `--format` | 否 | `token` | `token`（原始 JWT）或 `json`（含元数据） |

### `mcp-gateway token verify` — 验证 JWT

```bash
mcp-gateway token verify --public-key jwt-public.pem --token "eyJ..."
# 或从 stdin 传入：
echo "eyJ..." | mcp-gateway token verify --public-key jwt-public.pem
```

---

## 新增华为云服务

1. 在 `huaweicloud_mcp/services/<name>/` 下创建 `make_tools(settings) → dict`
2. 在 `server.py:build_server()` 中添加 `if "<name>" in enabled` 分支
3. 在 `manifest.yaml` 的 `build_kwargs.enabled` 中追加 `"<name>"`
4. 重启网关 — 新工具自动出现

**无需改 Nginx。无需改网关代码。无需改 Agent 配置。**

---

## 生产部署

### systemd

参见 `mcp-gateway/deploy/mcp-gateway.service`：

```ini
[Service]
WorkingDirectory=/opt/mcp-servers
EnvironmentFile=/etc/mcp-gateway/.env
ExecStart=/opt/mcp-servers/start.sh \
    --manifest /opt/mcp-servers/manifest.yaml
```

### Nginx（仅 TLS 终结）

参见 `mcp-gateway/deploy/nginx.conf.example`。关键属性：**一条** `location /` 规则。新增/移除 MCP 服务**不需要**改 Nginx。

---

## 选择性启用服务

三层覆盖（优先级从低到高）：

| 层级 | 来源 | 示例 |
|------|------|------|
| 1 | `manifest.yaml` 的 `enabled` 字段 | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` 环境变量 | `huaweicloud` |
| 3 | CLI `--enable` / `--disable` | `./start.sh --enable ecs,pipeline` |

启动日志明确打印已挂载/已跳过的服务及跳过原因。

---

## 环境变量

### 华为云凭证

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | 是 | | Access Key ID |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | 是 | | Secret Access Key |
| `HUAWEICLOUD_REGION` | 是 | | 区域，如 `af-south-1` |
| `HUAWEICLOUD_PROJECT_ID` | ECS/CTS | | 项目 UUID |
| `CODEARTS_DEFAULT_PROJECT_ID` | Pipeline | `=HUAWEICLOUD_PROJECT_ID` | Pipeline 项目回退 |
| `CTS_DEFAULT_TIMEZONE` | 否 | `Asia/Shanghai` | CTS 时间解析时区 |

### MCP Server

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `MCP_TRANSPORT` | 否 | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | 否 | `127.0.0.1` | SSE/HTTP 绑定地址 |
| `MCP_PORT` | 否 | `8000` | SSE/HTTP 绑定端口 |
| `MCP_ENABLED_SERVICES` | 否 | `ecs,pipeline,cts,cce` | 逗号分隔的服务子集 |
| `HUAWEICLOUD_MCP_LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `HUAWEICLOUD_MCP_LOG_FILE` | 否 | stderr | 日志文件路径 |
| `HUAWEICLOUD_MCP_HTTP_TIMEOUT` | 否 | `30` | SDK HTTP 超时（秒） |
| `HUAWEICLOUD_MCP_NETWORK_RETRIES` | 否 | `2` | SDK 重试次数 |

### 网关鉴权

| 变量 | 必需 | 说明 |
|------|------|------|
| `MCP_GATEWAY_AUTH_MODE` | ✅ | 网关鉴权：`jwt` / `dev` |
| `MCP_GATEWAY_HOST` | ✅ | 监听地址（dev 建议 `127.0.0.1`） |
| `MCP_GATEWAY_PORT` | 可选 | 监听端口，默认 `8080` |
| `MCP_DEV_LOOPBACK_ONLY` | 可选 | dev 来源限制：`true`（默认）/ `false` |
| `MCP_GATEWAY_LOG_FORMAT` | 可选 | 日志格式：`text`（默认）/ `json` |
| `MCP_JWT_PUBLIC_KEY` | jwt 必需 | RS256 公钥（`file:` / `env:` / 内联 PEM） |
| `MCP_JWT_ISSUER` | 推荐 | JWT 签发者，默认 `mcp-gateway` |

完整列表见 `.env.example`。

---

## 共享鉴权库（mcp-auth-common）

| 组件 | 说明 |
|------|------|
| `Identity` | pydantic v2 模型：`sub` / `roles` / `tenant` / `iat` / `exp` |
| `AutoAuth` | 自动检测鉴权策略：有 gateway identity → 使用；否则合成 dev Identity + WARN |
| `AuthStrategy` | 抽象基类 |
| `require_role()` | 角色校验，支持 admin ⊃ operator ⊃ readonly 层级 |
| `set_request_scope()` / `current_scope()` | contextvar 管道，工具函数无需 `ctx` 参数即可获取 scope |

---

## 开发

### 安装

```bash
# 在 workspace 根目录
uv sync
```

### 运行测试

```bash
# 统一 Server（182 个测试）
uv run pytest huaweicloud-mcp-server/tests/ -q

# 网关（120 个测试）
uv run pytest mcp-gateway/tests/ -q

# 全部（302 个测试）
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

### 测试结构

| 类别 | 数量 | 覆盖内容 |
|------|------|----------|
| ECS 工具 | 52 | list/get/power/delete/resize/confirm/job |
| Pipeline 工具 | 48 | list/get/run/update/toggle/confirm |
| CTS 工具 | 36 | search/detail + time_utils + mask_utils + 7 天窗口 |
| CCE 工具 | 30 | query clusters/nodes/nodepools + update nodepool + get_job + confirm + DefaultPool 拒绝 |
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

---

## 许可证

MIT
