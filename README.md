# Huawei Cloud MCP Servers — Monorepo

A [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) monorepo containing Huawei Cloud MCP (Model Context Protocol) servers and a unified ASGI gateway that mounts them on a single port with JWT authentication. Currently ships with ECS, CodeArts Pipeline, and CTS servers; additional servers can be added without changing the gateway or Nginx.

```
https://example.com/ecs/sse         ← ECS 云主机生命周期管理
https://example.com/pipeline/sse    ← CodeArts 流水线管理
https://example.com/cts/sse         ← CTS 审计日志检索
https://example.com/healthz         ← 网关探活（免鉴权）
```

## 项目结构

```
mcp-servers/
├── start.sh                       ← 启动入口（加载 .env + 启动网关）
├── .env                           ← 统一环境变量（AK/SK + JWT + 各服务配置）
├── .env.example                   ← 全量模板
├── manifest.yaml                  ← 服务拓扑（挂载谁、路径、RBAC）
├── pyproject.toml                 ← uv workspace 声明
│
├── ecs-mcp-server/                ← ECS 云主机 MCP Server
│   └── src/ecs_mcp_server/
│
├── codearts-pipeline-mcp-server/  ← CodeArts 流水线 MCP Server
│   └── src/pipeline_mcp_server/
│
├── cts-mcp-server/                ← CTS 审计日志 MCP Server
│   └── src/cts_mcp_server/
│
├── mcp-auth-common/               ← 共享鉴权库（Identity / AutoAuth / require_role）
│   └── src/mcp_auth_common/
│
└── mcp-gateway/                   ← ASGI 网关（Starlette Mount + JWT 中间件）
    ├── src/mcp_gateway/
    ├── tests/                     ← 96 个测试，全部通过
    ├── deploy/                    ← systemd + Nginx 配置
    └── README.md                  ← 网关详细文档
```

## MCP Server 一览

### ECS Server — 云主机生命周期管理

| 工具 | 说明 | 最低角色 |
|------|------|---------|
| `ecs_list_servers` | 列出云主机（支持过滤/分页） | readonly |
| `ecs_get_server` | 查看单台云主机详情/状态 | readonly |
| `ecs_list_flavors` | 列出可用规格 | readonly |
| `ecs_get_job_status` | 查询异步任务状态 | readonly |
| `ecs_power_action(action="start")` | 批量开机 | operator |
| `ecs_power_action(action="stop"/"reboot")` | 批量关机/重启 | admin |
| `ecs_delete_server` | ⚠ 删除云主机 | admin |
| `ecs_resize_server` | ⚠ 变更规格 | admin |

### Pipeline Server — CodeArts 流水线管理

| 工具 | 说明 | 最低角色 |
|------|------|---------|
| `pipeline_list` | 列出流水线 | readonly |
| `pipeline_get_detail` | 查看流水线配置详情 | readonly |
| `pipeline_run` | 触发流水线执行 | operator |
| `pipeline_update_info` | ⚠ 修改流水线配置 | admin |
| `pipeline_set_status` | ⚠ 启用/禁用流水线 | admin |

### CTS Server — 审计日志检索

| 工具 | 说明 | 最低角色 |
|------|------|---------|
| `cts_search_traces` | 按时间+条件搜索审计事件 | readonly |
| `cts_get_trace_detail` | 查看单条事件完整请求/响应体 | readonly |

> 角色层级：**admin** ⊃ **operator** ⊃ **readonly**

## 网关架构

```
                          ┌──────────────────────────────────────┐
                          │       MCP Gateway (port 8080)        │
                          │                                      │
  Client ──Bearer JWT──▶ │  GatewayAuthMiddleware                │
                          │    ├─ JWT verify (RS256)             │
                          │    ├─ Path RBAC (coarse)             │
                          │    └─ Inject identity → scope        │
                          │                                      │
                          │  Starlette Mount-based routing:      │
                          │    /ecs     → ecs_mcp_server         │
                          │    /pipeline → pipeline_mcp_server   │
                          │    /cts     → cts_mcp_server         │
                          └──────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
             ┌──────────┐   ┌──────────┐   ┌──────────┐
             │ ECS MCP  │   │Pipeline  │   │  CTS MCP │
             │  Server  │   │  MCP Svr │   │  Server  │
             │──────────│   │──────────│   │──────────│
             │ AutoAuth │   │ AutoAuth │   │ AutoAuth │
             │ tool RBAC│   │ tool RBAC│   │ tool RBAC│
             └──────────┘   └──────────┘   └──────────┘
```

### 鉴权分层

| 层级 | 职责 | 粒度 | 示例 |
|------|------|------|------|
| 网关中间件 | 验签 JWT → 解析 Identity → 路径 RBAC → 注入 scope | `/ecs/*` | 无 ecs 权限 → 403 |
| MCP Server | 从 scope 读 Identity → 按 tool 名做角色判断 | `ecs_delete` vs `ecs_list` | 非 admin 调 delete → ToolError |

### Server 侧鉴权：自动检测，零配置

每个 MCP Server 使用 `AutoAuth` 策略，**无需配置任何环境变量**：

| 场景 | 行为 | 说明 |
|------|------|------|
| 在网关后面 | `scope["mcp_identity"]` 存在 → 直接使用 | 网关已验签，Identity 可信 |
| 独立启动（stdio / SSE） | 无 gateway identity → 合成 dev Identity + ⚠ WARN 日志 | 本地开发，自动放行 |

启动时日志会醒目提示：

```
⚠ No gateway identity found. Synthesising dev identity sub=dev-local
  roles=['admin']. This means the server is NOT behind the MCP gateway
  with JWT auth. If this is a production server, it is running WITHOUT
  authentication. If this is local development, this is expected and safe.
```

### 网关鉴权模式

| 模式 | 环境变量 | 行为 | 场景 |
|------|---------|------|------|
| `jwt` | `MCP_GATEWAY_AUTH_MODE=jwt`（默认） | 完整 JWT 验签 + 路径 RBAC | 生产 |
| `dev` | `MCP_GATEWAY_AUTH_MODE=dev` | 跳过 JWT，合成 Identity | 非生产 |

dev 模式通过 `MCP_DEV_LOOPBACK_ONLY` 控制来源限制：

| 子模式 | 环境变量 | 行为 | 场景 |
|--------|---------|------|------|
| loopback-only | `MCP_DEV_LOOPBACK_ONLY=true`（默认） | 仅 loopback 调用者放行，其余 403 | 本地开发 |
| open | `MCP_DEV_LOOPBACK_ONLY=false` | 任何来源放行（CRITICAL 日志） | CI / 隔离测试 |

## 快速开始

### 前置条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- 华为云 AK/SK

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e ./mcp-auth-common
pip install -e ./ecs-mcp-server
pip install -e ./codearts-pipeline-mcp-server
pip install -e ./cts-mcp-server
pip install -e ./mcp-gateway
```

### 2. 配置环境变量

编辑根目录 `.env`：

```bash
# 华为云凭证（三个 MCP Server 共用）
HUAWEICLOUD_ACCESS_KEY_ID=your-ak
HUAWEICLOUD_SECRET_ACCESS_KEY=your-sk
HUAWEICLOUD_PROJECT_ID=your-project-id

# 各服务 Region（共用）
HUAWEICLOUD_REGION=cn-north-4
CODEARTS_DEFAULT_PROJECT_ID=your-codearts-project-id

# 网关鉴权模式（本地开发用 dev，生产用 jwt）
MCP_GATEWAY_AUTH_MODE=dev
MCP_GATEWAY_HOST=127.0.0.1
```

### 3. 启动网关

```bash
# 启动所有 manifest.yaml 中 enabled=true 的服务
./start.sh

# 只启动 ecs 和 pipeline
./start.sh ecs,pipeline

# 自定义端口
./start.sh --port 9000

# 组合使用
./start.sh ecs --port 9000 --log-level debug
```

### 4. 签发 JWT Token（生产环境）

```bash
# 生成密钥对
mcp-gateway token keygen

# 签发 token
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# 调用网关（携带 token）
curl -H "Authorization: Bearer *** http://127.0.0.1:8080/ecs/sse
```

### 5. 验证

```bash
# 探活
curl http://127.0.0.1:8080/healthz

# 连接 ECS（用 MCP 客户端或 curl）
curl http://127.0.0.1:8080/ecs/sse
```

## 独立启动单个 MCP Server

每个 MCP Server 可以脱离网关独立运行，**无需任何鉴权配置**：

```bash
# stdio 模式（Hermes / Claude Desktop 本地调用）
ecs-mcp-server

# SSE 模式（本地浏览器/Postman 调试）
./ecs-mcp-server/scripts/run-sse-local.sh

# 带环境变量
./ecs-mcp-server/scripts/run-with-env.sh
```

启动时会打印 ⚠ 警告日志，提示当前未经过网关鉴权。这是预期行为——本地开发不需要 JWT。

## 生产部署

### 生成 JWT 密钥对

```bash
# 使用内置 CLI（推荐）
mcp-gateway token keygen

# 或使用 openssl
openssl genrsa -out jwt-private.pem 2048
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
```

### 签发 JWT Token

```bash
# 签发 admin 角色 token（默认 1 小时有效）
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# 签发 operator + readonly 角色，自定义 TTL 和租户
mcp-gateway token create --sub ops-bot --roles operator,readonly \
  --private-key jwt-private.pem --ttl 7200 --tenant proj-abc

# JSON 格式输出（含过期时间等元数据）
mcp-gateway token create --sub bob --roles readonly \
  --private-key jwt-private.pem --format json

# 验证/解码 token（调试用）
mcp-gateway token verify --public-key jwt-public.pem --token "eyJ..."
```

在 `.env` 中设置：

```bash
MCP_GATEWAY_AUTH_MODE=jwt
MCP_GATEWAY_HOST=0.0.0.0
MCP_JWT_PUBLIC_KEY=file:/etc/mcp-gateway/jwt-public.pem
MCP_JWT_ISSUER=mcp-gateway
```

下游 MCP Server 会自动检测到网关注入的 Identity，无需额外配置。

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

参见 `mcp-gateway/deploy/nginx.conf.example`。关键属性：**一条** `location /` 规则。新增/移除 MCP Server **不需要**改 Nginx。

## 选择性启动

通过三层覆盖控制本次启动哪些服务（优先级从低到高）：

| 层级 | 来源 | 示例 |
|------|------|------|
| 1 | `manifest.yaml` 的 `enabled` 字段 | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` 环境变量 | `ecs,cts` |
| 3 | CLI `--enable` / `--disable` | `./start.sh ecs,pipeline` |

启动日志明确打印"已挂载/已跳过"服务及跳过原因。

## 添加新的 MCP Server

1. 创建 Server 包，内嵌 AutoAuth（参考现有 Server 的 `tools/*.py`）
2. 在根 `pyproject.toml` 的 `[tool.uv.workspace] members` 中添加目录
3. 在 `manifest.yaml` 中添加一条服务记录
4. 在 `.env` / `.env.example` 中添加该服务所需的环境变量
5. 重启网关

**不需要改 Nginx，不需要改网关代码。**

## 共享鉴权库（mcp-auth-common）

所有 MCP Server 和网关共用，包含：

| 组件 | 说明 |
|------|------|
| `Identity` | pydantic v2 模型：`sub` / `roles` / `tenant` / `iat` / `exp` |
| `AutoAuth` | 自动检测鉴权策略：有 gateway identity → 使用；否则合成 dev Identity + WARN |
| `AuthStrategy` | 抽象基类 |
| `require_role()` | 角色校验，支持 admin ⊃ operator ⊃ readonly 层级 |
| `set_request_scope()` / `current_scope()` | contextvar 管道，让工具函数无需 `ctx` 参数即可获取 scope |

## 测试

```bash
cd mcp-gateway
python3 -m pytest tests/ -v
```

**96 个测试，全部通过**，覆盖：

| 类别 | 数量 | 验证内容 |
|------|------|---------|
| SSE 挂载前缀（Pitfall #1） | 6 | `sse_app(mount_path="/ecs")` → endpoint URL 带 `/ecs/` 前缀 |
| 组合 lifespan（Pitfall #2） | 4 | 多 FastMCP 实例正确挂载 |
| 网关鉴权中间件 | 9 | JWT 验签 + RBAC + Identity 注入 |
| AutoAuth 自动检测 | 6 | 网关模式读 scope / 独立模式合成 dev Identity + WARN |
| StandaloneAuth（网关内部） | 6 | JWT 自验签 / 过期拒绝 |
| 网关 dev 模式 | 10 | 免 JWT / loopback 放行 / open 模式 / disabled 不再有效 |
| 结构化日志 | 9 | JSON 格式化 / extra 字段提升 / 审计事件验证 / text 向后兼容 |
| 工具级 RBAC | 14 | 角色层级 + 三服务授权矩阵 |
| manifest 覆盖优先级 | 9 | 三层覆盖 + 跳过原因 + 重复检测 |
| SSE 前缀回归 | 6 | 传输层 endpoint 路径正确 |
| Token CLI（keygen / create / verify） | 14 | 密钥生成 + 签发 + 验签 + 错误处理 + 端到端往返 |

## 环境变量速查

| 变量 | 必需 | 说明 |
|------|------|------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | ✅ | 华为云 AK（三服务共用） |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | ✅ | 华为云 SK（三服务共用） |
| `HUAWEICLOUD_PROJECT_ID` | ✅ | IAM 项目 ID（ECS/CTS 使用） |
| `HUAWEICLOUD_REGION` | ✅ | 所有服务共用区域（ECS / CTS / CodeArts Pipeline） |
| `CODEARTS_DEFAULT_PROJECT_ID` | 推荐 | CodeArts 项目 UUID |
| `MCP_GATEWAY_AUTH_MODE` | ✅ | 网关鉴权模式：`jwt` / `dev` |
| `MCP_GATEWAY_HOST` | ✅ | 监听地址（dev 模式建议 `127.0.0.1`） |
| `MCP_GATEWAY_PORT` | 推荐 | 监听端口，默认 `8080` |
| `MCP_DEV_LOOPBACK_ONLY` | 可选 | dev 模式来源限制：`true`（默认，仅 loopback）/ `false`（任何来源） |
| `MCP_GATEWAY_LOG_FORMAT` | 可选 | 日志格式：`text`（默认）/ `json`（结构化，供 log shipper） |
| `MCP_JWT_PUBLIC_KEY` | jwt 模式必需 | RS256 公钥（`file:` / `env:` / 内联 PEM） |
| `MCP_JWT_ISSUER` | 推荐 | JWT 签发者，默认 `mcp-gateway` |
| `MCP_GATEWAY_ENABLED_SERVICES` | 可选 | 启用服务白名单（逗号分隔） |

完整列表见根目录 `.env.example`。

## 许可证

MIT
