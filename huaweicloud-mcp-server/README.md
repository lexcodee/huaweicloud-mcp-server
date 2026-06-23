# huaweicloud-mcp-server

[English](README.en.md) | **中文**

统一华为云 MCP Server — 将 **ECS**、**CodeArts Pipeline**、**CTS** 合并为单一包，共享基础设施（配置、鉴权、日志、错误处理）和按服务划分的工具模块。

取代原有的三个独立包（`ecs-mcp-server`、`codearts-pipeline-mcp-server`、`cts-mcp-server`），统一代码库、统一凭证、单一 FastMCP 实例。

---

## 快速开始

```bash
# 1. 设置凭证
export HUAWEICLOUD_ACCESS_KEY_ID=your_ak
export HUAWEICLOUD_SECRET_ACCESS_KEY=*** HUAWEICLOUD_REGION=af-south-1
export HUAWEICLOUD_PROJECT_ID=your_project_id   # ECS/CTS 需要
export CODEARTS_DEFAULT_PROJECT_ID=your_pipeline_project_id  # Pipeline 回退

# 2a. stdio 模式（全部服务）— 本地 AI 客户端
uv run huaweicloud-mcp-server

# 2b. SSE / Streamable-HTTP 模式 — 远程客户端
MCP_TRANSPORT=sse MCP_PORT=8000 uv run huaweicloud-mcp-server

# 2c. 仅启用子集
MCP_ENABLED_SERVICES=ecs,pipeline uv run huaweicloud-mcp-server
```

---

## Agent 配置

### Hermes Agent

**模式 A — stdio（本地开发，推荐）**

添加到 `~/.hermes/config.yaml`：

```yaml
mcp_servers:
  huaweicloud:
    command: /path/to/.venv/bin/huaweicloud-mcp-server
    timeout: 120
    # 可选：仅启用服务子集
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

添加到 `~/.claude/mcp.json`（或项目级 `.claude/mcp.json`）：

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

添加到 `claude_desktop_config.json`（macOS: `~/Library/Application Support/Claude/`，
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

---

## 架构

```
huaweicloud_mcp/
├── __init__.py
├── config.py          # 统一 Settings dataclass + load_settings()
├── client.py          # SDK 客户端工厂: get_client("ecs", settings) — lru_cached
├── errors.py          # ToolError, wrap_tool 装饰器, PendingActions（两阶段提交）
├── logging_setup.py   # SecretMaskingFilter + setup_logging()
├── server.py          # build_server(enabled={"ecs","pipeline","cts"}) → FastMCP
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
```

### 共享基础设施

| 模块 | 用途 |
|------|------|
| `config.py` | 单一 `Settings` dataclass — AK/SK/region/project_id/timezone。`load_settings()` 从环境变量读取，校验必需项，缺失时快速退出。 |
| `client.py` | `get_client(service, settings)` → 缓存的 SDK 客户端。ECS、Pipeline、CTS 共用一个工厂，共享 HttpConfig（超时、重试）。 |
| `errors.py` | `ToolError` 异常 + `wrap_tool` 装饰器：捕获 SDK 错误，标准化为 `{ok: false, error: {...}}` 信封，记录结构化事件。`PendingActions` 实现两阶段提交。 |
| `logging_setup.py` | `SecretMaskingFilter` 在日志中脱敏 AK/SK。`setup_logging()` 配置仅 stderr（stdio 安全）或文件日志。 |

---

## 工具一览（16 个）

### ECS（8 个）

| 工具 | 说明 | 破坏性 |
|------|------|--------|
| `ecs_list_servers` | 列出云主机（支持 name/status/IP/tags 过滤） | 否 |
| `ecs_get_server` | 查看完整详情或轻量状态快照 | 否 |
| `ecs_list_flavors` | 列出可用规格（可按 AZ 过滤） | 否 |
| `ecs_power_action` | 批量开机 / 关机 / 重启 | 关机、重启（两阶段） |
| `ecs_delete_server` | 永久删除云主机（可选释放 EIP + 磁盘） | 是（两阶段） |
| `ecs_resize_server` | 变更规格（vCPU/RAM） | 是（两阶段） |
| `ecs_confirm_destructive` | 确认执行待定的破坏性操作 | — |
| `ecs_get_job_status` | 查询异步任务状态 | 否 |

### CodeArts Pipeline（6 个）

| 工具 | 说明 | 破坏性 |
|------|------|--------|
| `pipeline_list` | 列出流水线 + 最近运行状态 | 否 |
| `pipeline_get_detail` | 完整流水线配置 | 否 |
| `pipeline_run` | 触发流水线执行 | 否 |
| `pipeline_set_status` | 启用 / 禁用流水线 | 禁用（两阶段） |
| `pipeline_update_info` | 修改默认分支 / 首阶段前置任务 | 是（两阶段） |
| `pipeline_confirm_destructive` | 确认执行待定的破坏性操作 | — |

### CTS（2 个）

| 工具 | 说明 | 破坏性 |
|------|------|--------|
| `cts_search_traces` | 按时间范围 + 条件搜索审计事件（7 天窗口） | 否 |
| `cts_get_trace_detail` | 查看单条事件的完整脱敏请求/响应体 | 否 |

---

## 两阶段提交（破坏性操作）

破坏性工具（关机、重启、删除、变更规格、禁用流水线、修改流水线）遵循两阶段提交模式，防止误操作：

```
阶段 1: 工具调用返回预览 + approval_id（TTL 120 秒）
         → {status: "pending_approval", approval_id: "...", preview: {...}}

阶段 2: 用户显式确认
         → ecs_confirm_destructive(approval_id="...")
         → 操作执行，返回 {ok: true, data: {...}}
```

若 approval_id 过期，重新发起原始调用获取新的 ID。

---

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | 是 | | Access Key ID |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | 是 | | Secret Access Key |
| `HUAWEICLOUD_REGION` | 是 | | 区域，如 `af-south-1` |
| `HUAWEICLOUD_PROJECT_ID` | ECS/CTS | | 项目 UUID |
| `CODEARTS_DEFAULT_PROJECT_ID` | Pipeline | `=HUAWEICLOUD_PROJECT_ID` | Pipeline 项目回退 |
| `CTS_DEFAULT_TIMEZONE` | 否 | `Asia/Shanghai` | CTS 时间解析时区 |
| `HUAWEICLOUD_MCP_LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `HUAWEICLOUD_MCP_LOG_FILE` | 否 | stderr | 日志文件路径 |
| `HUAWEICLOUD_MCP_HTTP_TIMEOUT` | 否 | `30` | SDK HTTP 超时（秒） |
| `HUAWEICLOUD_MCP_NETWORK_RETRIES` | 否 | `2` | SDK 重试次数 |
| `MCP_TRANSPORT` | 否 | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | 否 | `127.0.0.1` | SSE/HTTP 绑定地址 |
| `MCP_PORT` | 否 | `8000` | SSE/HTTP 绑定端口 |
| `MCP_ENABLED_SERVICES` | 否 | `ecs,pipeline,cts` | 逗号分隔的服务子集 |

---

## 部署模式

### 1. 独立 stdio（本地 AI 客户端）

```bash
uv run huaweicloud-mcp-server
```

默认挂载全部三个服务。使用 `MCP_ENABLED_SERVICES` 可仅注册子集。

### 2. 独立 SSE / HTTP（远程客户端）

```bash
MCP_TRANSPORT=sse MCP_PORT=8000 uv run huaweicloud-mcp-server
```

端点：
- `GET /sse` — SSE 事件流（含 15 秒 keep-alive 帧）
- `POST /messages/?session_id=...` — 客户端 → 服务端消息

Streamable-HTTP 模式：

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=8000 uv run huaweicloud-mcp-server
```

### 3. MCP 网关（策略 1：单 URL，单挂载）

统一 Server 通过 `mcp-gateway` 挂载到 `/hwc`。Agent 连接**一个 URL** 即可获取所有已启用的工具。

`manifest.yaml`：

```yaml
services:
  - name: huaweicloud
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, pipeline, cts]
    mount_path: /hwc
    required_roles: [readonly, operator, admin]
```

网关启动时调用 `huaweicloud_mcp.build_server(enabled=["ecs","pipeline","cts"])`。工具名按服务前缀命名（`ecs_*`、`pipeline_*`、`cts_*`），无命名冲突。

网关额外提供：
- JWT 鉴权（签发者、受众、公钥）
- 基于角色的工具授权（readonly / operator / admin）
- 结构化访问日志（logfmt 或 JSON）

**新增云服务**（Agent 侧 0 配置变更）：

1. 在 `huaweicloud_mcp/services/<name>/` 下创建 `make_tools(settings) → dict`
2. 在 `server.py:build_server()` 中添加 `if "<name>" in enabled` 分支
3. 在 `manifest.yaml` 的 `build_kwargs.enabled` 中追加 `"<name>"`
4. 重启网关 — 工具自动出现

---

## 开发

### 安装

```bash
# 在 workspace 根目录
uv sync
```

### 运行测试

```bash
# 统一 Server 测试（152 个）
uv run pytest huaweicloud-mcp-server/tests/ -q

# 网关测试（106 个）
uv run pytest mcp-gateway/tests/ -q

# 全部（258 个）
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

### 测试结构

测试按服务组织，共享 `conftest.py` 提供：
- `_isolate_env`（autouse）— 每个测试之间清除所有云环境变量
- `settings` / `ecs_settings` / `pipeline_settings` / `cts_settings` — 预配置的 Settings fixture
- `mock_ecs_client` / `mock_pipeline_client` / `mock_cts_client` — 通过 monkeypatch 注入的 MagicMock SDK 客户端

CTS 测试额外直接测试工具模块：
- `test_cts_time_utils.py` — 时间解析（人类可读字符串、ISO-8601、相对时间）
- `test_cts_mask_utils.py` — 敏感值脱敏
- `test_cts_seven_day.py` — 7 天窗口强制

---

## 从独立包迁移

三个原始包（`ecs-mcp-server`、`codearts-pipeline-mcp-server`、`cts-mcp-server`）已被统一包取代：

| 之前（3 个包） | 之后（1 个包） |
|------|------|
| `ecs_mcp_server.config.Settings` | `huaweicloud_mcp.config.Settings` |
| `ecs_mcp_server.tools.query` | `huaweicloud_mcp.services.ecs.tools.query` |
| `pipeline_mcp_server.X` | `huaweicloud_mcp.services.pipeline.X` |
| `cts_mcp_server.X` | `huaweicloud_mcp.services.cts.X` |
| 3 × 独立 AK/SK 配置 | 1 × 统一 Settings |
| 3 × 重复错误包装 | 1 × 共享 `wrap_tool` + `ToolError` |
| 3 × 独立客户端工厂 | 1 × `get_client(service, settings)` |
| 3 × manifest 条目（3 个模块） | 1 × manifest 条目 + `build_kwargs` |

### 导入深度约定

- 顶层模块（`config`、`errors`、`client`、`logging_setup`）：使用相对 `.` 或 `..` 导入
- 服务级模块（`models`、`serializers`、`make_tools`）：使用 `...`（3 个点）到达顶层包
- 工具模块（`services/{svc}/tools/` 下）：使用 `....`（4 个点）到达顶层包

---

## 项目布局（workspace）

```
huaweicloud-mcp-server/          # ← workspace 根目录
├── pyproject.toml               # uv workspace 定义
├── manifest.yaml                # MCP 网关服务清单（策略 1）
├── huaweicloud-mcp-server/      # ← 统一包（本 README）
│   ├── pyproject.toml
│   ├── src/huaweicloud_mcp/
│   └── tests/
├── mcp-auth-common/             # 共享鉴权策略（网关 + 独立）
└── mcp-gateway/                 # Starlette 网关（JWT 鉴权，单挂载 /hwc）
    ├── src/mcp_gateway/
    └── tests/
```
