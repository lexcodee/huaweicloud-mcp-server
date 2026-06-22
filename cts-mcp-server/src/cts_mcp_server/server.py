"""FastMCP server entrypoint.

Transports
----------
Selected via the ``MCP_TRANSPORT`` env var:

  * ``stdio`` (default) — line-delimited JSON over stdin/stdout. Used by
    Hermes / Claude Desktop in local mode.
  * ``sse``               — Server-Sent Events. Two HTTP endpoints exposed:
        GET  /sse                       (event stream, server -> client)
        POST /messages/?session_id=...  (client -> server)
    Bound to ``MCP_HOST`` (default ``127.0.0.1``) / ``MCP_PORT`` (default
    ``8000``). For FunctionGraph deploy, ``cts_mcp_server.app:app`` is the
    ASGI entry — uvicorn / FunctionGraph runtime hosts it directly without
    going through ``main()``.
  * ``streamable-http``   — single-endpoint ``POST /mcp`` streaming
    transport (newer MCP spec). Same host/port env vars.

Examples::

    # stdio (Hermes default)
    HUAWEICLOUD_ACCESS_KEY_ID=... HUAWEICLOUD_SECRET_ACCESS_KEY=... \\
        cts-mcp-server

    # local SSE for testing
    MCP_TRANSPORT=sse MCP_PORT=8000 cts-mcp-server

    # FunctionGraph (uvicorn boots app.py directly)
    uvicorn cts_mcp_server.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .logging_setup import setup_logging
from .tools.detail import make_detail_tools
from .tools.search import make_search_tools

VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")

SERVER_NAME = "huaweicloud-cts-mcp-server"
SERVER_INSTRUCTIONS = (
    "Tools for querying Huawei Cloud CTS (Cloud Trace Service) audit events. "
    "Use cts_search_traces to find events by time range, cloud service, user, "
    "or severity; use cts_get_trace_detail to inspect a specific event's full "
    "request/response body. IMPORTANT: this API only covers the last 7 days — "
    "older history must be retrieved from the OBS bucket on the CTS tracker."
)


def build_server() -> FastMCP:
    """Build a fully wired FastMCP server. Loads settings, sets up logging."""
    settings = load_settings()
    log = setup_logging(
        level=settings.log_level,
        log_file=settings.log_file,
        known_secrets=[settings.access_key_id, settings.secret_access_key],
    )
    log.info("starting %s with config=%s", SERVER_NAME, settings.masked())

    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8000"))

    mcp = FastMCP(
        SERVER_NAME,
        instructions=SERVER_INSTRUCTIONS,
        host=host,
        port=port,
    )

    tools: dict = {}
    tools.update(make_search_tools(settings))
    tools.update(make_detail_tools(settings))

    for name, fn in tools.items():
        mcp.add_tool(fn, name=name)

    log.info("registered %d tools: %s", len(tools), sorted(tools.keys()))
    return mcp


def main() -> None:
    """CLI entrypoint. Selects transport from MCP_TRANSPORT env var."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport not in VALID_TRANSPORTS:
        sys.stderr.write(
            f"ERROR: invalid MCP_TRANSPORT={transport!r}. "
            f"Valid: {', '.join(VALID_TRANSPORTS)}\n"
        )
        sys.exit(2)

    try:
        server = build_server()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        logging.exception("fatal error during server startup")
        sys.exit(1)

    server.run(transport=transport)


if __name__ == "__main__":
    main()
