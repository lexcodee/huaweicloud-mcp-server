"""Single-process ASGI gateway for multiple FastMCP servers.

Public entry points:

* :func:`build_app` constructs the Starlette application; ``uvicorn
  mcp_gateway.gateway:app`` boots it.
* :func:`mcp_gateway.cli.main` parses ``--enable`` / ``--disable`` / ``--manifest``
  and runs uvicorn.
"""
from __future__ import annotations

from .gateway import build_app

__all__ = ["build_app"]
__version__ = "0.1.0"
