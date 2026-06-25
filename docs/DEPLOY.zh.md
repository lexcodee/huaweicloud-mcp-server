# 生产部署

## 网关鉴权分层

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

## systemd

参见 `mcp-gateway/deploy/mcp-gateway.service`：

```ini
[Service]
WorkingDirectory=/opt/mcp-servers
EnvironmentFile=/etc/mcp-gateway/.env
ExecStart=/opt/mcp-servers/start.sh \
    --manifest /opt/mcp-servers/manifest.yaml
```

## Nginx（仅 TLS 终结）

参见 `mcp-gateway/deploy/nginx.conf.example`。关键属性：**一条** `location /` 规则。新增/移除 MCP 服务**不需要**改 Nginx。

## Windows

Python 代码本身跨平台。与 Linux/macOS 的差异：

| 方面 | Linux/macOS | Windows |
|------|-------------|---------|
| 启动脚本 | `./start.sh` | `powershell -File start.ps1` |
| 独立服务器 | `scripts/run-with-env.sh` | `powershell -File scripts/run-with-env.ps1` |
| venv 入口 | `.venv/bin/huaweicloud-mcp-server` | `.venv/Scripts/huaweicloud-mcp-server.exe` |
| JWT 公钥路径 | `file:/etc/mcp-gateway/jwt-public.pem` | `file:C:/mcp-gateway/jwt-public.pem` |
| 日志文件路径 | `/var/log/ecs-mcp-server.log` | `C:/Logs/ecs-mcp-server.log` |

> **Windows 防火墙**：绑定 `0.0.0.0` 可能触发防火墙提示或被静默阻止。本地开发建议使用 `--host 127.0.0.1` 或在 `.env` 中设置 `MCP_GATEWAY_HOST=127.0.0.1`。
