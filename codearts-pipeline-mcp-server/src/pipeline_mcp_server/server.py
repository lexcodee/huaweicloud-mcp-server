"""FastMCP entrypoint for the Huawei Cloud CodeArts Pipeline MCP server."""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from .config import Settings, load_settings
from .logging_setup import setup_logging
from .tools.execution import make_execution_tools
from .tools.lifecycle import make_lifecycle_tools
from .tools.query import make_query_tools
from .tools.update import make_update_tools

NAME = "codearts-pipeline-mcp-server"
INSTRUCTIONS = (
    "Manage Huawei Cloud CodeArts pipelines: list, inspect, run, update "
    "default branch / first-stage pre-task, and toggle enabled/disabled "
    "state via pipeline_set_status. Destructive operations "
    "(pipeline_update_info, pipeline_set_status with status='disabled') "
    "use two-phase commit: the first call returns a preview + approval_id "
    "(NO execution); you MUST present the preview to the user and ask for "
    "explicit approval before calling pipeline_confirm_destructive(approval_id). "
    "Do NOT call pipeline_confirm_destructive without user approval."
)

log = logging.getLogger("pipeline_mcp_server.server")


def build_server(settings: Settings | None = None) -> FastMCP:
    if settings is None:
        settings = load_settings()
    setup_logging(
        level=settings.log_level,
        log_file=settings.log_file,
        known_secrets=[settings.access_key_id, settings.secret_access_key],
    )
    log.info("starting %s with config=%s", NAME, settings.masked())

    mcp = FastMCP(NAME, instructions=INSTRUCTIONS)

    tools: dict = {}
    tools.update(make_query_tools(settings))
    tools.update(make_execution_tools(settings))
    tools.update(make_update_tools(settings))
    tools.update(make_lifecycle_tools(settings))

    for name, fn in tools.items():
        mcp.add_tool(fn, name=name)

    log.info("registered %d tools: %s", len(tools), sorted(tools.keys()))
    return mcp


def main() -> None:
    try:
        mcp = build_server()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        logging.getLogger("pipeline_mcp_server.server").exception(
            "fatal error while starting server"
        )
        sys.exit(1)
    mcp.run()  # default transport: stdio


if __name__ == "__main__":
    main()
