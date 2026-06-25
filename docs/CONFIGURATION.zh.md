# 配置

## 选择性启用服务

三层覆盖（优先级从低到高）：

| 层级 | 来源 | 示例 |
|------|------|------|
| 1 | `manifest.yaml` `enabled` 字段 | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` 环境变量 | `huaweicloud` |
| 3 | CLI `--enable` / `--disable` | `./start.sh --enable ecs,pipeline` |

启动日志明确打印已挂载/已跳过的服务及跳过原因。

---

## 按需启用 tools（service 子集精修）

service 级开关之外，可以用 **fnmatch glob** 在 manifest 里继续裁剪到具体工具，主要场景：

- **RBAC**：给 readonly token 一个不含写操作的挂载点
- **缩小 LLM 工具列表**：场景化客户端只暴露相关工具，降低噪音 / token
- **临时禁用风险工具**：例如生产线先关掉 `*_delete_*`

### 在 manifest 中声明

```yaml
services:
  - name: huaweicloud
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, pipeline, cts, cce]
      include: [ecs_*, cts_*]              # 先按 include 过滤（可选）
      exclude: ["*_confirm_destructive"]   # 再按 exclude 移除（可选）
    mount_path: /hwc
```

### 环境变量（覆盖默认值，不覆盖显式 kwargs）

| 变量 | 说明 |
|------|------|
| `MCP_INCLUDE_TOOLS` | 逗号分隔的 glob，仅保留匹配项 |
| `MCP_EXCLUDE_TOOLS` | 逗号分隔的 glob，移除匹配项（在 include 之后生效） |

```bash
MCP_EXCLUDE_TOOLS="*_confirm_destructive,*_set_status,*_delete_*" ./start.sh
```

### RBAC 模式：多挂载点 + role 隔离

最低成本实现 readonly / operator 分级 —— 不在协议层做拦截，直接挂两份：

```yaml
services:
  - name: huaweicloud-readonly
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, pipeline, cts, cce]
      exclude:
        - "*_confirm_destructive"
        - "*_set_status"
        - "*_update_*"
        - "*_delete_*"
        - "*_resize_*"
        - "*_power_action"
        - "pipeline_run"
    mount_path: /hwc/ro
    required_roles: [readonly, operator, admin]

  - name: huaweicloud
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, pipeline, cts, cce]
    mount_path: /hwc
    required_roles: [operator, admin]
```

readonly token 走 `/hwc/ro` 看不到任何写操作；operator token 走 `/hwc` 享有完整工具集。两份 FastMCP 实例各自构建，运行时零开销。

### 优先级

`build_kwargs.include / exclude`（显式） > `MCP_INCLUDE_TOOLS / MCP_EXCLUDE_TOOLS`（env） > 不过滤。pattern 未匹配到任何工具时只产生 WARNING 日志，不报错。

### 预览：`mcp-gateway config preview`

改完 manifest 不想拉起 uvicorn 就能看到效果？跑 dry-run：

```bash
mcp-gateway config preview --manifest manifest.yaml --show-filtered
```

输出示例：

```
Mount /hwc/ro  (huaweicloud-readonly)
  Roles:   readonly, operator, admin
  Module:  huaweicloud_mcp.build_server  [factory]
  Exclude: ['*_confirm_destructive', '*_delete_*', ...]
  Tools:   12 active, 10 filtered
    ✓ cce_query_clusters
    ✓ cts_search_traces
    ...
    ✗ ecs_delete_server  (excluded by '*_delete_*')
    ✗ pipeline_run       (excluded by 'pipeline_run')

Summary: 2 mount(s), 34 active tools, 10 filtered
```

- 每个被过滤的工具会标注**具体哪条 glob 匹配了它**——拼错 / 写太宽时一眼看到
- 退出码：构建成功 `0`，任一 service 工厂报错 `1`（可直接挂 CI pre-merge）
- `--format json` 给下游脚本 / 仪表盘消费
- 无网络调用、无凭证依赖（自动注入 placeholder env）

支持的选项：

| 选项 | 说明 |
|------|------|
| `--manifest <path>` | manifest 路径，默认与 serve 相同 |
| `--enable` / `--disable` | service 级覆盖（仅作用于本次预览） |
| `--show-filtered` | text 模式下逐项列出被过滤的工具及匹配的 pattern |
| `--format text\|json` | 输出格式，默认 text |

---

## 环境变量

### 华为云凭证

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | 是 | | Access Key ID |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | 是 | | Secret Access Key |
| `HUAWEICLOUD_REGION` | 是 | | 区域，如 `af-south-1` |
| `HUAWEICLOUD_PROJECT_ID` | ECS/CTS | | 项目 UUID（IaaS 项目，与 CodeArts 项目**不同**） |
| `CODEARTS_DEFAULT_PROJECT_ID` | Pipeline | | CodeArts 项目 UUID（与 `HUAWEICLOUD_PROJECT_ID` 不同，**不会回退**） |
| `CTS_DEFAULT_TIMEZONE` | 否 | `Asia/Shanghai` | CTS 时间解析时区 |

### MCP Server

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `MCP_TRANSPORT` | 否 | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | 否 | `127.0.0.1` | SSE/HTTP 绑定地址 |
| `MCP_PORT` | 否 | `8000` | SSE/HTTP 绑定端口 |
| `MCP_ENABLED_SERVICES` | 否 | `ecs,pipeline,cts,cce,lts,ces,vpc,rds` | 逗号分隔的服务子集 |
| `MCP_INCLUDE_TOOLS` | 否 | — | 逗号分隔的 fnmatch glob，仅保留匹配的工具 |
| `MCP_EXCLUDE_TOOLS` | 否 | — | 逗号分隔的 fnmatch glob，移除匹配的工具（在 include 之后生效） |
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
