# Production Deployment

## Gateway auth layers

| Layer | Responsibility | Granularity | Example |
|-------|---------------|-------------|---------|
| Gateway middleware | Verify JWT → parse Identity → path RBAC → inject scope | `/hwc/*` | No hwc permission → 403 |
| MCP Server | Read Identity from scope → per-tool role check | `ecs_delete` vs `ecs_list` | Non-admin calls delete → ToolError |

### Server-side auth: auto-detect, zero config

| Scenario | Behavior | Notes |
|----------|----------|-------|
| Behind gateway | `scope["mcp_identity"]` exists → use it | Gateway verified, Identity trusted |
| Standalone (stdio/SSE) | No gateway identity → synthesize dev Identity + ⚠ WARN | Local dev, auto-allow |

### Gateway auth modes

| Mode | Env var | Behavior | Use case |
|------|---------|----------|----------|
| `jwt` | `MCP_GATEWAY_AUTH_MODE=jwt` (default) | Full JWT verify + path RBAC | Production |
| `dev` | `MCP_GATEWAY_AUTH_MODE=dev` | Skip JWT, synthesize Identity | Non-production |

Dev mode source restriction via `MCP_DEV_LOOPBACK_ONLY`:

| Sub-mode | Env var | Behavior | Use case |
|----------|---------|----------|----------|
| loopback-only | `MCP_DEV_LOOPBACK_ONLY=true` (default) | Only loopback callers allowed | Local dev |
| open | `MCP_DEV_LOOPBACK_ONLY=false` | Any source allowed (CRITICAL log) | CI / isolated test |

---

## Token CLI

The gateway ships a built-in token management CLI.

### `mcp-gateway token keygen` — Generate RSA key pair

```bash
mcp-gateway token keygen                              # defaults: jwt-private.pem / jwt-public.pem / 2048 bits
mcp-gateway token keygen --bits 4096                  # stronger key
mcp-gateway token keygen --private-key /etc/mcp/jwt-private.pem \
                          --public-key  /etc/mcp/jwt-public.pem
```

### `mcp-gateway token create` — Sign a JWT

```bash
# Minimal — outputs raw JWT string
mcp-gateway token create --sub alice --roles admin --private-key jwt-private.pem

# Full options
mcp-gateway token create \
  --sub ops-bot \
  --roles operator,readonly \
  --private-key jwt-private.pem \
  --issuer mcp-gateway \
  --audience mcp-api \
  --tenant proj-abc \
  --ttl 7200 \
  --format json

# Permanent token (never expires)
mcp-gateway token create --sub service-account --roles admin --private-key jwt-private.pem --ttl 0
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--sub` | Yes | — | Subject (user or service account id) |
| `--roles` | Yes | — | Comma-separated role list |
| `--private-key` | No | `jwt-private.pem` | Path to RSA private key PEM |
| `--issuer` | No | `mcp-gateway` | JWT `iss` claim |
| `--audience` | No | — | JWT `aud` claim |
| `--tenant` | No | — | Tenant / project id |
| `--ttl` | No | `3600` | Lifetime in seconds; `0` = permanent |
| `--format` | No | `token` | `token` (raw JWT) or `json` (with metadata) |

### `mcp-gateway token verify` — Decode and verify a JWT

```bash
mcp-gateway token verify --public-key jwt-public.pem --token "eyJ..."
# Or pipe from stdin:
echo "eyJ..." | mcp-gateway token verify --public-key jwt-public.pem
```

---

## systemd

See `mcp-gateway/deploy/mcp-gateway.service`:

```ini
[Service]
WorkingDirectory=/opt/mcp-servers
EnvironmentFile=/etc/mcp-gateway/.env
ExecStart=/opt/mcp-servers/start.sh \
    --manifest /opt/mcp-servers/manifest.yaml
```

## Nginx (TLS termination only)

See `mcp-gateway/deploy/nginx.conf.example`. Key property: **one** `location /`
rule. Adding/removing MCP services **does not** require Nginx changes.

## Windows

The Python code is cross-platform. Differences from Linux/macOS:

| Area | Linux/macOS | Windows |
|------|-------------|---------|
| Start script | `./start.sh` | `powershell -File start.ps1` |
| Standalone server | `scripts/run-with-env.sh` | `powershell -File scripts/run-with-env.ps1` |
| venv entry point | `.venv/bin/huaweicloud-mcp-server` | `.venv/Scripts/huaweicloud-mcp-server.exe` |
| JWT public key path | `file:/etc/mcp-gateway/jwt-public.pem` | `file:C:/mcp-gateway/jwt-public.pem` |
| Log file path | `/var/log/ecs-mcp-server.log` | `C:/Logs/ecs-mcp-server.log` |

> **Windows Firewall**: binding to `0.0.0.0` may trigger a firewall prompt or be
> blocked silently. For local dev, use `--host 127.0.0.1` or set
> `MCP_GATEWAY_HOST=127.0.0.1` in `.env`.
