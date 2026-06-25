# Configuration

## Selective service enable

Three override layers (low → high priority):

| Layer | Source | Example |
|-------|--------|---------|
| 1 | `manifest.yaml` `enabled` field | `enabled: false` |
| 2 | `MCP_GATEWAY_ENABLED_SERVICES` env var | `huaweicloud` |
| 3 | CLI `--enable` / `--disable` | `./start.sh --enable ecs,pipeline` |

Startup logs clearly print mounted/skipped services and skip reasons.

---

## Selecting a subset of tools (finer than service)

Beyond service-level toggles you can narrow further to individual tools using
**fnmatch globs** declared in the manifest. Typical uses:

- **RBAC**: give readonly tokens a mount that has no mutating tools
- **Shrink the LLM tool list**: scenario-specific clients expose only what they need (less noise, fewer tokens)
- **Temporarily disable risky tools**: e.g. drop `*_delete_*` in production

### Manifest declaration

```yaml
services:
  - name: huaweicloud
    module: huaweicloud_mcp
    attr: build_server
    build_kwargs:
      enabled: [ecs, pipeline, cts, cce]
      include: [ecs_*, cts_*]              # optional: keep only matches first
      exclude: ["*_confirm_destructive"]   # optional: then remove matches
    mount_path: /hwc
```

### Env vars (used when kwargs are absent)

| Variable | Description |
|----------|-------------|
| `MCP_INCLUDE_TOOLS` | Comma-separated globs; keep only matches |
| `MCP_EXCLUDE_TOOLS` | Comma-separated globs; remove matches (after include) |

```bash
MCP_EXCLUDE_TOOLS="*_confirm_destructive,*_set_status,*_delete_*" ./start.sh
```

### RBAC pattern: multi-mount + role isolation

Cheapest readonly / operator split — no protocol-level interception, just mount
two FastMCP instances:

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

Readonly tokens hit `/hwc/ro` and never see mutating tools; operator tokens hit
`/hwc` and get the full toolset. Each mount is an independent FastMCP instance
built once — zero runtime overhead.

### Precedence

`build_kwargs.include / exclude` (explicit) > `MCP_INCLUDE_TOOLS / MCP_EXCLUDE_TOOLS`
(env) > no filtering. Patterns that match no tool produce a WARNING only — never
an error.

### Preview: `mcp-gateway config preview`

Want to see the effect of a manifest change without spinning up uvicorn? Use the
dry-run:

```bash
mcp-gateway config preview --manifest manifest.yaml --show-filtered
```

Sample output:

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

- Every dropped tool is attributed to **the specific glob that matched it** —
  typos and overly broad patterns become obvious instantly.
- Exit codes: `0` on success, `1` if any service factory raises (safe to wire
  into CI as a pre-merge check on manifest changes).
- `--format json` for downstream tooling / dashboards.
- No network calls, no credentials required (placeholder env is injected
  automatically).

Same service-level overrides as `serve`:

| Option | Description |
|--------|-------------|
| `--manifest <path>` | Manifest path, same default as `serve` |
| `--enable` / `--disable` | Service-level overrides (preview only) |
| `--show-filtered` | In text mode, list each dropped tool with the matching pattern |
| `--format text\|json` | Output format, default text |

---

## Environment variables

### Huawei Cloud credentials

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HUAWEICLOUD_ACCESS_KEY_ID` | yes | | Access key ID |
| `HUAWEICLOUD_SECRET_ACCESS_KEY` | yes | | Secret access key |
| `HUAWEICLOUD_REGION` | yes | | Region, e.g. `af-south-1` |
| `HUAWEICLOUD_PROJECT_ID` | ECS/CTS | | Project UUID (IaaS project — **different** from the CodeArts project) |
| `CODEARTS_DEFAULT_PROJECT_ID` | Pipeline | | CodeArts project UUID (distinct from `HUAWEICLOUD_PROJECT_ID`; **no fallback**) |
| `CTS_DEFAULT_TIMEZONE` | no | `Asia/Shanghai` | CTS time parsing timezone |

### MCP Server

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_TRANSPORT` | no | `stdio` | `stdio` / `sse` / `streamable-http` |
| `MCP_HOST` | no | `127.0.0.1` | SSE/HTTP bind host |
| `MCP_PORT` | no | `8000` | SSE/HTTP bind port |
| `MCP_ENABLED_SERVICES` | no | `ecs,pipeline,cts,cce,lts,ces,vpc,rds` | Comma-separated service subset |
| `MCP_INCLUDE_TOOLS` | no | — | Comma-separated fnmatch globs; keep only matching tools |
| `MCP_EXCLUDE_TOOLS` | no | — | Comma-separated fnmatch globs; remove matching tools (after include) |
| `HUAWEICLOUD_MCP_LOG_LEVEL` | no | `INFO` | Log level |
| `HUAWEICLOUD_MCP_LOG_FILE` | no | stderr | Log file path |
| `HUAWEICLOUD_MCP_HTTP_TIMEOUT` | no | `30` | SDK HTTP timeout (seconds) |
| `HUAWEICLOUD_MCP_NETWORK_RETRIES` | no | `2` | SDK retry count |

### Gateway auth

| Variable | Required | Description |
|----------|----------|-------------|
| `MCP_GATEWAY_AUTH_MODE` | ✅ | Gateway auth: `jwt` / `dev` |
| `MCP_GATEWAY_HOST` | ✅ | Listen address (`127.0.0.1` for dev) |
| `MCP_GATEWAY_PORT` | optional | Listen port, default `8080` |
| `MCP_DEV_LOOPBACK_ONLY` | optional | Dev source restriction: `true` (default) / `false` |
| `MCP_GATEWAY_LOG_FORMAT` | optional | Log format: `text` (default) / `json` |
| `MCP_JWT_PUBLIC_KEY` | jwt required | RS256 public key (`file:` / `env:` / inline PEM) |
| `MCP_JWT_ISSUER` | recommended | JWT issuer, default `mcp-gateway` |

Full list in `.env.example`.
