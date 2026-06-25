"""ASGI entrypoint for SSE / Streamable-HTTP deployment.

Usage:
    uvicorn huaweicloud_mcp.app:app --host 0.0.0.0 --port 8000

Endpoints exposed by FastMCP.sse_app():
    GET  /sse                   — SSE event stream (server -> client)
    POST /messages/?session_id= — client -> server messages

A keep-alive middleware injects ``: keepalive`` comments every 15s on the
SSE stream to survive APIG / FunctionGraph 60s idle timeouts.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator

from starlette.applications import Starlette
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .server import build_server

log = logging.getLogger("huaweicloud_mcp.app")

KEEPALIVE_INTERVAL_SECONDS = float(os.environ.get("HUAWEICLOUD_MCP_SSE_KEEPALIVE", "15"))
KEEPALIVE_FRAME = b": keepalive\n\n"


class SSEKeepAliveMiddleware:
    """Inject SSE comment frames during idle periods on /sse responses."""

    def __init__(self, app: ASGIApp, interval: float = KEEPALIVE_INTERVAL_SECONDS):
        self.app = app
        self.interval = interval

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_event_stream = False
        last_send_at = asyncio.get_running_loop().time()
        keepalive_task: asyncio.Task | None = None
        send_lock = asyncio.Lock()

        async def keepalive_loop() -> None:
            try:
                while True:
                    await asyncio.sleep(self.interval)
                    idle = asyncio.get_running_loop().time() - last_send_at
                    if idle < self.interval:
                        continue
                    async with send_lock:
                        try:
                            await send({
                                "type": "http.response.body",
                                "body": KEEPALIVE_FRAME,
                                "more_body": True,
                            })
                        except Exception:  # noqa: BLE001
                            return
            except asyncio.CancelledError:
                pass

        async def wrapped_send(message: Message) -> None:
            nonlocal is_event_stream, last_send_at, keepalive_task
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                for k, v in headers:
                    if k.lower() == b"content-type" and b"text/event-stream" in v.lower():
                        is_event_stream = True
                        break
                async with send_lock:
                    await send(message)
                if is_event_stream and keepalive_task is None:
                    keepalive_task = asyncio.create_task(keepalive_loop())
                return

            if message["type"] == "http.response.body":
                last_send_at = asyncio.get_running_loop().time()
                async with send_lock:
                    await send(message)
                if not message.get("more_body", False) and keepalive_task is not None:
                    keepalive_task.cancel()
                return

            async with send_lock:
                await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            if keepalive_task is not None and not keepalive_task.done():
                keepalive_task.cancel()


def build_app() -> Starlette:
    """Build the ASGI application — FastMCP SSE wrapped with keep-alive."""
    mcp = build_server()
    sse_app = mcp.sse_app()
    sse_app.add_middleware(SSEKeepAliveMiddleware, interval=KEEPALIVE_INTERVAL_SECONDS)
    log.info(
        "asgi app ready: sse keepalive=%.1fs endpoints=[GET /sse, POST /messages/]",
        KEEPALIVE_INTERVAL_SECONDS,
    )
    return sse_app


# Module-level app for `uvicorn huaweicloud_mcp.app:app`.
app = build_app()
