# Contributing

## Development setup

```bash
# From workspace root
uv sync
```

## Run tests

```bash
# Unified server
uv run pytest huaweicloud-mcp-server/tests/ -q

# Gateway
uv run pytest mcp-gateway/tests/ -q

# All
uv run pytest huaweicloud-mcp-server/tests/ mcp-gateway/tests/ -q
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full test breakdown.

## Adding a new Huawei Cloud service

1. Create `huaweicloud_mcp/services/<name>/` with `make_tools(settings) → dict`
2. Add `if "<name>" in enabled` branch in `server.py:build_server()`
3. Append `"<name>"` to `build_kwargs.enabled` in `manifest.yaml`
4. Restart gateway — new tools appear automatically

**No Nginx change. No gateway code change. No Agent config change.**

## Project structure

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full project tree and shared infrastructure details.
