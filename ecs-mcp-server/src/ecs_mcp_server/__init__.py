"""ecs-mcp-server package.

Exposes the module-level :data:`mcp` FastMCP instance so the gateway can
``import ecs_mcp_server; ecs_mcp_server.mcp``. The instance is built
lazily on first access (not at import time) to avoid crashing the
importer when Huawei Cloud credentials are not configured (e.g. during
gateway startup before the full env is loaded).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "mcp":
        from .server import build_server

        return build_server()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
