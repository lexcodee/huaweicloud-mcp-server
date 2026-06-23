# 华为云 MCP Server — Monorepo

[English](README.en.md) | **中文**

基于 [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) 的 monorepo，包含**统一**的华为云 MCP Server 和 ASGI 网关（单 URL 挂载 + JWT 鉴权）。内置 ECS、CodeArts Pipeline、CTS 三个云服务；新增云服务**无需 Agent 侧任何配置变更**。

```
https://example.com/hwc/sse    ← 全部华为云工具 (ecs_*, pipeline_*, cts_*, …)
https://example.com/healthz    ← 网关探活（免鉴权）
```

## 项目结构

```
huaweicloud-mcp-server/
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
│       └── services/
│           ├── ecs/               ← 8 工具 (list/get/power/delete/resize)
│           ├── pipeline/          ← 6 工具 (list/get/run/update/toggle)
│           └── cts/               ← 2 工具 (search/get 审计事件)
│
├── mcp-auth-common/               ← 共享鉴权库 (Identity / AutoAuth / require_role)
│   └── src/mcp_auth_common/
│
└── mcp-gateway/                   ← ASGI 网关 (Starlette Mount + JWT 中间件)
    ├── src/mcp_gateway/
    ├── tests/                     ← 106 个测试
    ├── deploy/                    ← systemd + Nginx 配置
    └── README.md
```

## MCP 工具一览（16 个）

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

> 角色层级：**admin** ⊃ **operator** ⊃ **readonly**

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
                          │             enabled=[ecs,pipeline,cts]│
                          │           )                           │
                          └──────────────────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  统一 FastMCP     │
                          │  16 个工具：      │
                          │    ecs_* (8)      │
                          │    pipeline_* (6) │
                          │    cts_* (2)      │
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
HUAWEICLOUD_SECRET_ACCESS_KEY=*** Region
HUAWEICLOUD_REGION=cn-north-4
HUAWEICLOUD_PROJECT_ID=your-project-id
CODEARTS_DEFAULT_PROJECT_ID=your-codearts-project-id

# 网关鉴权模式（本地用 dev，生产用 jwt）
MCP_GATEWAY_AUTH_MODE=dev
MCP_GATEWAY_HOST=127.0.0.1
```

### 3. 启动网关

```bash
./start.sh
```

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
curl -H "Authorization: Bearer *** http://127.0.0.1:8080/hwc/sse
```

## 独立 stdio 模式（本地开发，无需网关）

统一 Server 可直接通过 stdio 运行，无需网关或 JWT：

```bash
# 全部服务（16 个工具）
huaweicloud-mcp-server

# 仅启用子集
MCP_ENABLED_SERVICES=ecs,pipeline huaweicloud-mcp-server

# SSE 模式
MCP_TRANSPORT=sse MCP_PORT=8000 huaweicloud-mcp-server
```

## Agent 配置

### Hermes Agent

**模式 A — stdio（本地开发，推荐）**

`~/.hermes/config.yaml`：

```yaml
mcp_servers:
  huaweicloud:
    command: /path/to/.venv/bin/huaweicloud-mcp-server
    timeout: 120
    # 可选：仅启用子集
    # env:
    #   MCP_ENABLED_SERVICES: ecs,pipeline
```

**模式 B — SSE via 网关（生产）**

```yaml
mcp_servers:
  huaweicloud:
    url: http://127.0.0.1:8080/hwc/sse
    transport: sse
    timeout: 120
    connect_timeout: 30
```

验证：

```bash
hermes mcp test huaweicloud
#   ✓ Connected (643ms)
#   ✓ Tools discovered: 16
```

### Claude Code

`~/.claude/mcp.json`（或项目级 `.claude/mcp.json`）：

**stdio 模式：**

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

**SSE 模式（via 网关）：**

```json
{
  "mcpServers": {
    "huaweicloud": {
      "url": "http://127.0.0.1:8080/hwc/sse",
      "transport": "sse",
      "timeout": 120
    }
  }
}
```

### Claude Desktop / Cursor / Cline

`claude_desktop_config.json`（macOS: `~/Library/Application Support/Claude/`，
Windows: `%APPDATA%\Claude\`）：

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

> **核心要点**：无论未来新增多少华为云服务，Agent 始终只需配置**一个** MCP Server 条目。新服务以新工具名（`obs_*`、`rds_*`、…）自动出现，无需 Agent 侧任何配置变更。

## 新增华为云服务

1. 在 `huaweicloud_mcp/services/<name>/` 下创建 `make_tools(settings) → dict`
2. 在 `server.py:build_server()` 中添加 `if "<name>" in enabled` 分支
3. 在 `manifest.yaml` 的 `build_kwargs.enabled` 中追加 `"<name>"`
4. 重启网关 — 新工具自动出现

**无需改 Nginx。无需改网关代码。无需改 Agent 配置。**

## 生产部署

### JWT 密钥对

```bash
mcp-gateway token keygen
# 或
openssl genrsa -out jwt-private.pem 2048
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
```

### 签发 Token

```bash
# admin 角色 token（默认 1 小时有效）
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# operator + readonly 角色，自定义 TTL
mcp-gateway token create --sub ops-bot --roles operator,readonly \
  --private-key jwt-private.pem --ttl 7200 --tenant proj-abc

# 验证 token
mcp-gateway token verify --public-key jwt-public.pem --token "eyJ..."
```

在 `.env` 中设置：

```bash
MCP_GATEWAY_AUTH_MODE=jwt
MCP_GATEWAY_HOST=0.0.0.0
MCP_JWT_PUBLIC_KEY=file:/etc/mcp-gateway/jwt-public.pem
MCP_JWT_ISSUER=mcp-gateway
```

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

## 选择性启用服务

三层覆盖（优先级从低到高）：

| 层级 | 来源 | 示例 |
|------|------|------|
| 1 | `manifest.yaml` 的 `enabled` 字段 | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` 环境变量 | `huaweicloud` |
| 3 | CLI `--enable` / `--disable` | `./start.sh --enable ecs,pipeline` |

启动日志明确打印已挂载/已跳过的服务及跳过原因。

## 共享鉴权库（mcp-auth-common）

| 组件 | 说明 |
|------|------|
| `Identity` | pydantic v2 模型：`sub` / `roles` / `tenant` / `iat` / `exp` |
| `AutoAuth` | 自动检测鉴权策略：有 gateway identity → 使用；否则合成 dev Identity + WARN |
| `AuthStrategy` | 抽象基类 |
| `require_role()` | 角色校验，支持 admin ⊃ operator ⊃ readonly 层级 |
| `set_request_scope()` / `current_scope()` | contextvar 管道，工具函数无需 `ctx` 参数即可获取 scope |

## 测试

```bash
# 统一 Server（152 个测试）
uv run pytest huaweicloud-mcp-server/tests/ -q

# 网关（106 个测试）
uv run pytest mcp-gateway/tests/ -q

# 全部（258 个测试）
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

| 类别 | 数量 | 覆盖内容 |
|------|------|----------|
| ECS 工具 | 52 | list/get/power/delete/resize/confirm/job |
| Pipeline 工具 | 48 | list/get/run/update/toggle/confirm |
| CTS 工具 | 36 | search/detail + time_utils + mask_utils + 7 天窗口 |
| 配置 / 客户端 | 16 | Settings 校验、客户端工厂、缓存 |
| 网关鉴权 | 9 | JWT 验签 + RBAC + Identity 注入 |
| 网关 dev 模式 | 10 | 免 JWT / loopback / open / disabled |
| 结构化日志 | 9 | JSON 格式 / extra 字段 / 审计事件 |
| 工具级 RBAC | 14 | 角色层级 + 三服务授权矩阵 |
| Manifest 覆盖 | 9 | 三层覆盖 + 跳过原因 + 去重 |
| 工厂模式 | 9 | build_kwargs 解析 + 工厂调用 + 异常 |
| SSE 前缀回归 | 1 | 无 /hwc/hwc 双前缀 |
| Token CLI | 14 | keygen + create + verify + 端到端往返 |
| 组合 lifespan | 4 | 多 FastMCP 挂载 |

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | ✅ | 华为云 AK（共用） |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | ✅ | 华为云 SK（共用） |
| `HUAWEICLOUD_PROJECT_ID` | ✅ | IAM 项目 ID（ECS/CTS） |
| `HUAWEICLOUD_REGION` | ✅ | 区域（所有服务共用） |
| `CODEARTS_DEFAULT_PROJECT_ID` | 推荐 | CodeArts 项目 UUID |
| `MCP_GATEWAY_AUTH_MODE` | ✅ | 网关鉴权：`jwt` / `dev` |
| `MCP_GATEWAY_HOST` | ✅ | 监听地址（dev 建议 `127.0.0.1`） |
| `MCP_GATEWAY_PORT` | 可选 | 监听端口，默认 `8080` |
| `MCP_DEV_LOOPBACK_ONLY` | 可选 | dev 来源限制：`true`（默认）/ `false` |
| `MCP_GATEWAY_LOG_FORMAT` | 可选 | 日志格式：`text`（默认）/ `json` |
| `MCP_JWT_PUBLIC_KEY` | jwt 必需 | RS256 公钥（`file:` / `env:` / 内联 PEM） |
| `MCP_JWT_ISSUER` | 推荐 | JWT 签发者，默认 `mcp-gateway` |
| `MCP_ENABLED_SERVICES` | 可选 | 独立 stdio/sse 模式的服务子集 |
| `MCP_TRANSPORT` | 可选 | 独立传输方式：`stdio` / `sse` / `streamable-http` |

完整列表见 `.env.example`。

## 许可证

MIT
