"""Unified FastMCP server entrypoint.

build_server(enabled={"ecs", "pipeline", "cts"}) builds a single FastMCP
instance with tools from the selected Huawei Cloud services. Each service
module exposes a make_tools(settings) -> dict[str, callable] function.

Transport is selected via MCP_TRANSPORT env var (stdio | sse | streamable-http),
same as the original per-service servers.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .config import load_settings, Settings
from .logging_setup import setup_logging

VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")

SERVER_NAME = "huaweicloud-mcp-server"

ALL_SERVICES = ("ecs", "pipeline", "cts")


def build_server(
    enabled: Optional[list[str] | set[str]] = None,
    *,
    settings: Optional[Settings] = None,
) -> FastMCP:
    """Build a fully wired FastMCP server.

    Args:
        enabled: Subset of {"ecs", "pipeline", "cts"} to register.
                 Accepts a list (from YAML manifest) or set. Defaults to all three.
        settings: Pre-loaded Settings. If None, loads from env.
    """
    if settings is None:
        settings = load_settings()

    log = setup_logging(
        level=settings.log_level,
        log_file=settings.log_file,
        known_secrets=[settings.access_key_id, settings.secret_access_key],
    )

    if enabled is None:
        env_services = os.environ.get("MCP_ENABLED_SERVICES", "")
        if env_services:
            enabled = [s.strip() for s in env_services.split(",") if s.strip()]
        else:
            enabled = list(ALL_SERVICES)

    # Normalise to set for internal use, regardless of caller type.
    enabled_set = set(enabled)
    unknown = enabled_set - set(ALL_SERVICES)
    if unknown:
        raise ValueError(
            f"Unknown services: {unknown}. Valid: {sorted(ALL_SERVICES)}"
        )

    log.info("starting %s services=%s config=%s", SERVER_NAME, sorted(enabled_set), settings.masked())

    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8000"))

    # Build instructions dynamically based on enabled services.
    instructions_parts: list[str] = []
    if "ecs" in enabled:
        instructions_parts.append(
            "ECS: list/inspect servers, power actions (start/stop/reboot), "
            "delete, resize, poll async jobs. Destructive ops use two-phase "
            "commit — first call returns preview + approval_id; call "
            "ecs_confirm_destructive(approval_id) only after explicit user approval."
        )
    if "pipeline" in enabled:
        instructions_parts.append(
            "CodeArts Pipeline: list/get pipelines, run, enable/disable, "
            "update config. Destructive ops (disable, update) use two-phase "
            "commit — call pipeline_confirm_destructive(approval_id) only "
            "after explicit user approval."
        )
    if "cts" in enabled:
        instructions_parts.append(
            "CTS: search audit traces and get trace detail. Read-only. "
            "Only the last 7 days are queryable. Sensitive values are masked."
        )

    mcp = FastMCP(
        SERVER_NAME,
        instructions="\n\n".join(instructions_parts),
        host=host,
        port=port,
    )

    tools: dict = {}

    if "ecs" in enabled:
        from .services.ecs.make_tools import make_tools as _ecs_tools
        tools.update(_ecs_tools(settings))

    if "pipeline" in enabled:
        from .services.pipeline.make_tools import make_tools as _pipeline_tools
        tools.update(_pipeline_tools(settings))

    if "cts" in enabled:
        from .services.cts.make_tools import make_tools as _cts_tools
        tools.update(_cts_tools(settings))

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
