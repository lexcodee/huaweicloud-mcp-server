"""Huawei Cloud CodeArts Pipeline — MCP server package.

Exposes the module-level :data:`mcp` FastMCP instance so the gateway can
``import pipeline_mcp_server; pipeline_mcp_server.mcp``. The instance is
built lazily on first access.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

__all__ = ["server"]
__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "mcp":
        from .server import build_server

        return build_server()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
