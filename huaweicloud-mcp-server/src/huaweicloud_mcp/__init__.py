"""Huawei Cloud MCP Server — unified package.

Provides MCP tools for ECS, CodeArts Pipeline, and CTS via a single
FastMCP server. Usage:

    from huaweicloud_mcp import build_server
    mcp = build_server()  # all services enabled
    mcp.run(transport="stdio")

Or select specific services:

    mcp = build_server(enabled={"ecs", "pipeline"})
"""
from __future__ import annotations

# Lazy __getattr__ so `import huaweicloud_mcp` doesn't eagerly build a server.
_ATTRS = {"build_server", "main", "mcp"}


def __getattr__(name: str):
    if name == "build_server":
        from .server import build_server
        return build_server
    if name == "main":
        from .server import main
        return main
    if name == "mcp":
        from .server import build_server
        return build_server()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["build_server", "main"]
