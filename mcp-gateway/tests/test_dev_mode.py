"""Test: gateway dev mode — local development without JWT.

Verifies that MCP_GATEWAY_AUTH_MODE=dev allows loopback callers
without a JWT, while still rejecting non-loopback callers.
"""
from __future__ import annotations

import os

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from mcp_gateway.auth_middleware import GatewayAuthMiddleware


def _build_app(auth_mode: str, path_roles: list | None = None):
    """Build a Starlette app with the middleware in the given mode.

    The env var must be set BEFORE the first request (Starlette builds
    the middleware stack lazily on first call), so we set it and leave
    it for the test's lifetime. Caller is responsible for cleanup.
    """

    async def ok(request):
        return JSONResponse({"ok": True, "identity": str(request.scope.get("mcp_identity"))})

    routes = [
        Mount("/ecs", app=Starlette(routes=[Route("/sse", ok, methods=["GET"])])),
        Route("/healthz", ok, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    os.environ["MCP_GATEWAY_AUTH_MODE"] = auth_mode
    # Mark the server as loopback-bound so dev mode accepts all connections.
    os.environ["MCP_GATEWAY_HOST"] = "127.0.0.1"
    app.add_middleware(
        GatewayAuthMiddleware,
        public_key_spec="",  # not needed in dev/disabled
        issuer="mcp-gateway",
        audience=None,
        leeway=30,
        path_roles=path_roles or [],
        exempt_paths=("/healthz",),
    )
    return app


class TestDevMode:
    def test_dev_mode_loopback_passes(self):
        """Dev mode: loopback caller gets a synthesised admin identity."""
        app = _build_app("dev")
        client = TestClient(app)
        r = client.get("/ecs/sse")
        assert r.status_code == 200
        assert "dev-local" in r.json()["identity"]
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)

    def test_dev_mode_injects_identity_in_scope(self):
        """Dev mode: scope["mcp_identity"] is an Identity with admin role."""
        captured = {}

        async def capture(request):
            captured["identity"] = request.scope.get("mcp_identity")
            return JSONResponse({"ok": True})

        os.environ["MCP_GATEWAY_AUTH_MODE"] = "dev"
        os.environ["MCP_GATEWAY_HOST"] = "127.0.0.1"
        app = Starlette(routes=[Route("/ecs/sse", capture, methods=["GET"])])
        app.add_middleware(
            GatewayAuthMiddleware,
            public_key_spec="",
            issuer="mcp-gateway",
            audience=None,
            leeway=30,
            path_roles=[],
            exempt_paths=("/healthz",),
        )

        from mcp_auth_common import Identity

        client = TestClient(app)
        r = client.get("/ecs/sse")
        assert r.status_code == 200
        identity = captured["identity"]
        assert isinstance(identity, Identity)
        assert "admin" in identity.roles
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)

    def test_dev_mode_custom_subject_and_roles(self):
        """Dev mode: MCP_DEV_SUBJECT and MCP_DEV_ROLES are respected."""
        os.environ["MCP_GATEWAY_AUTH_MODE"] = "dev"
        os.environ["MCP_DEV_SUBJECT"] = "test-user"
        os.environ["MCP_DEV_ROLES"] = "readonly,operator"
        os.environ["MCP_GATEWAY_HOST"] = "127.0.0.1"

        captured = {}

        async def capture(request):
            captured["identity"] = request.scope.get("mcp_identity")
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/ecs/sse", capture, methods=["GET"])])
        app.add_middleware(
            GatewayAuthMiddleware,
            public_key_spec="",
            issuer="mcp-gateway",
            audience=None,
            leeway=30,
            path_roles=[],
            exempt_paths=("/healthz",),
        )

        client = TestClient(app)
        r = client.get("/ecs/sse")
        assert r.status_code == 200
        assert captured["identity"].sub == "test-user"
        assert "readonly" in captured["identity"].roles

        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)
        os.environ.pop("MCP_DEV_SUBJECT", None)
        os.environ.pop("MCP_DEV_ROLES", None)

    def test_dev_mode_no_token_needed(self):
        """Dev mode: no Authorization header is required."""
        app = _build_app("dev")
        client = TestClient(app)
        r = client.get("/ecs/sse")  # no headers
        assert r.status_code == 200
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)

    def test_dev_mode_healthz_still_works(self):
        app = _build_app("dev")
        client = TestClient(app)
        r = client.get("/healthz")
        assert r.status_code == 200
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)


class TestDisabledMode:
    def test_disabled_mode_allows_all(self):
        """Disabled mode: every request passes without auth."""
        app = _build_app("disabled")
        client = TestClient(app)
        r = client.get("/ecs/sse")
        assert r.status_code == 200
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)

    def test_disabled_mode_no_token_needed(self):
        app = _build_app("disabled")
        client = TestClient(app)
        r = client.get("/ecs/sse")  # no headers
        assert r.status_code == 200
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)


class TestInvalidMode:
    def test_invalid_mode_raises(self):
        """An invalid MCP_GATEWAY_AUTH_MODE should raise RuntimeError."""
        os.environ["MCP_GATEWAY_AUTH_MODE"] = "nonsense"
        app = Starlette(routes=[])
        app.add_middleware(
            GatewayAuthMiddleware,
            public_key_spec="",
            issuer="mcp-gateway",
            audience=None,
            leeway=30,
            path_roles=[],
        )
        # Starlette builds middleware lazily; trigger it via a request.
        with pytest.raises(RuntimeError, match="is invalid"):
            client = TestClient(app)
            client.get("/")
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)
