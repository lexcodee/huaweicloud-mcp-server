"""Test: SSE endpoint callback path carries the correct mount prefix.

This is a regression test for the known MCP SDK bug where mounting
FastMCP.sse_app() under Starlette Mount("/ecs", ...) causes the SSE
``event: endpoint`` message to emit ``/messages/`` instead of
``/ecs/messages/``, breaking the client's subsequent POST.

The fix: call ``sse_app(mount_path="/ecs")`` which tells FastMCP to
prepend the prefix when building the endpoint URI.

We verify by inspecting the SseServerTransport's endpoint attribute
(which is the URL the server writes into the SSE event stream) and
confirming it includes the mount prefix.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.routing import Mount, Route


class TestMountPathEndpointPrefix:
    def test_sse_transport_endpoint_includes_prefix(self):
        """When sse_app(mount_path="/ecs") is called, the SSE transport's
        message endpoint must be /ecs/messages (not bare /messages)."""
        mcp = FastMCP("test-ecs")
        app = mcp.sse_app(mount_path="/ecs")

        # The SSE transport is created inside sse_app and stored on the
        # handle_sse closure. We can reach it by inspecting the route
        # handler's closure variables.
        endpoint = _extract_sse_endpoint(app)
        assert endpoint.startswith("/ecs/"), f"SSE endpoint {endpoint!r} should start with /ecs/"

    def test_bare_sse_app_has_no_prefix(self):
        """Without mount_path, the endpoint is bare /messages/."""
        mcp = FastMCP("test-bare")
        app = mcp.sse_app()
        endpoint = _extract_sse_endpoint(app)
        assert endpoint.rstrip("/") == "/messages", f"Bare endpoint should be /messages, got {endpoint!r}"

    def test_pipeline_prefix(self):
        mcp = FastMCP("test-pipeline")
        app = mcp.sse_app(mount_path="/pipeline")
        endpoint = _extract_sse_endpoint(app)
        assert endpoint.startswith("/pipeline/"), f"SSE endpoint {endpoint!r} should start with /pipeline/"

    def test_cts_prefix(self):
        mcp = FastMCP("test-cts")
        app = mcp.sse_app(mount_path="/cts")
        endpoint = _extract_sse_endpoint(app)
        assert endpoint.startswith("/cts/"), f"SSE endpoint {endpoint!r} should start with /cts/"

    def test_settings_mount_path_is_set(self):
        """After sse_app(mount_path=...) the instance's settings.mount_path
        should reflect the prefix."""
        mcp = FastMCP("test-settings")
        mcp.sse_app(mount_path="/ecs")
        assert mcp.settings.mount_path == "/ecs"

    def test_mount_path_normalisation(self):
        """The _normalize_path helper should produce /ecs/messages from
        mount_path=/ecs and message_path=/messages."""
        mcp = FastMCP("test-norm")
        app = mcp.sse_app(mount_path="/ecs")
        # The normalised endpoint is what the SSE transport emits.
        endpoint = _extract_sse_endpoint(app)
        assert endpoint.rstrip("/") == "/ecs/messages"


def _extract_sse_endpoint(app):
    """Extract the SSE transport's message endpoint from the Starlette app.

    The sse_app() creates a SseServerTransport whose ``endpoint`` attribute
    is the URL that gets written into the ``event: endpoint`` SSE frame.
    We find it by walking the route handlers' closure variables.
    """
    for route in app.routes:
        if isinstance(route, Route) and route.path == "/sse":
            handler = route.endpoint
            # The handler is either the raw handle_sse or a wrapper.
            # Walk its closure to find the SseServerTransport.
            transport = _find_sse_transport(handler)
            if transport is not None:
                return getattr(transport, "endpoint", None) or getattr(transport, "_endpoint", None)
    return None


def _find_sse_transport(func, depth=0):
    """Recursively search a function's closure for an SseServerTransport."""
    if depth > 5:
        return None
    from mcp.server.sse import SseServerTransport

    if isinstance(func, SseServerTransport):
        return func

    # Check closure cells.
    closure = getattr(func, "__closure__", None) or []
    for cell in closure:
        try:
            val = cell.cell_contents
        except ValueError:
            continue
        if isinstance(val, SseServerTransport):
            return val
        if callable(val):
            found = _find_sse_transport(val, depth + 1)
            if found:
                return found
        # Check attributes (e.g. bound methods).
        for attr_name in dir(val):
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(val, attr_name)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(attr, SseServerTransport):
                return attr
    return None
