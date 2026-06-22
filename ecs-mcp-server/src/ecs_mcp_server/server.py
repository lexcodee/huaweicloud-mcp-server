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
    ``8000``). For FunctionGraph deploy, ``ecs_mcp_server.app:app`` is the
    ASGI entry — uvicorn / FunctionGraph runtime hosts it directly without
    going through ``main()``.
  * ``streamable-http``   — single-endpoint ``POST /mcp`` streaming
    transport (newer MCP spec). Same host/port env vars.

Examples::

    # stdio (Hermes default)
    HUAWEICLOUD_ACCESS_KEY_ID=... HUAWEICLOUD_SECRET_ACCESS_KEY=... \\
        ecs-mcp-server

    # local SSE for testing
    MCP_TRANSPORT=sse MCP_PORT=8000 ecs-mcp-server

    # FunctionGraph (uvicorn boots app.py directly)
    uvicorn ecs_mcp_server.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .logging_setup import setup_logging
from .tools.job import make_job_tools
from .tools.lifecycle import make_lifecycle_tools
from .tools.query import make_query_tools

VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")

SERVER_NAME = "huaweicloud-ecs-mcp-server"
SERVER_INSTRUCTIONS = (
    "Tools for managing Huawei Cloud ECS instances: list/inspect, start, "
    "stop, reboot, delete, resize, and poll async jobs. Destructive "
    "operations (stop/reboot/delete/resize) use two-phase commit: the "
    "first call returns a preview + approval_id (NO execution); you MUST "
    "present the preview to the user and ask for explicit approval before "
    "calling ecs_confirm_destructive(approval_id). Do NOT call "
    "ecs_confirm_destructive without user approval. "
    "All write operations are asynchronous — poll with ecs_get_job_status."
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
    tools.update(make_query_tools(settings))
    tools.update(make_lifecycle_tools(settings))
    tools.update(make_job_tools(settings))

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
