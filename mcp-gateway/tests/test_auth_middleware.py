"""Test: gateway auth middleware — JWT verification, path RBAC, identity injection.

These tests use a generated RS256 key pair so we can sign and verify real
JWTs without hitting an external service.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import jwt
import pytest
from mcp.server.fastmcp import FastMCP
from mcp_auth_common import Identity
from mcp_auth_common.errors import AuthError
from mcp_gateway.auth_middleware import GatewayAuthMiddleware
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def _force_jwt_mode():
    """Ensure MCP_GATEWAY_AUTH_MODE=jwt for every test in this module."""
    old = os.environ.get("MCP_GATEWAY_AUTH_MODE")
    os.environ["MCP_GATEWAY_AUTH_MODE"] = "jwt"
    yield
    if old is None:
        os.environ.pop("MCP_GATEWAY_AUTH_MODE", None)
    else:
        os.environ["MCP_GATEWAY_AUTH_MODE"] = old


# ---------------------------------------------------------------------------
# RSA key pair for test JWTs
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rsa_keys(tmp_path_factory):
    """Generate an RS256 key pair once per module."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    return pub_pem, priv_pem


def _make_token(priv_pem: str, sub: str = "alice", roles: list[str] | None = None,
                issuer: str = "mcp-gateway", exp_offset: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "roles": roles or ["readonly"],
        "iss": issuer,
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(payload, priv_pem, algorithm="RS256")


def _build_protected_app(pub_pem: str, path_roles: list[tuple[str, list[str]]]):
    """Build a Starlette app with GatewayAuthMiddleware + dummy routes."""
    async def ok(request):
        return JSONResponse({"ok": True})

    routes = [
        Mount("/ecs", app=Starlette(routes=[Route("/sse", ok, methods=["GET"])])),
        Mount("/pipeline", app=Starlette(routes=[Route("/sse", ok, methods=["GET"])])),
        Route("/healthz", ok, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        GatewayAuthMiddleware,
        public_key_spec=pub_pem,
        issuer="mcp-gateway",
        audience=None,
        leeway=30,
        path_roles=path_roles,
        exempt_paths=("/healthz",),
    )
    return app


class TestJwtVerification:
    def test_valid_token_passes(self, rsa_keys):
        pub, priv = rsa_keys
        token = _make_token(priv, roles=["readonly"])
        app = _build_protected_app(pub, [("/ecs", ["readonly"])])
        client = TestClient(app)
        r = client.get("/ecs/sse", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_missing_token_401(self, rsa_keys):
        pub, _ = rsa_keys
        app = _build_protected_app(pub, [("/ecs", ["readonly"])])
        client = TestClient(app)
        r = client.get("/ecs/sse")
        assert r.status_code == 401

    def test_expired_token_401(self, rsa_keys):
        pub, priv = rsa_keys
        # Expired 120s ago — well beyond the 30s leeway.
        token = _make_token(priv, exp_offset=-120)
        app = _build_protected_app(pub, [("/ecs", ["readonly"])])
        client = TestClient(app)
        r = client.get("/ecs/sse", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401

    def test_wrong_issuer_401(self, rsa_keys):
        pub, priv = rsa_keys
        token = _make_token(priv, issuer="wrong-issuer")
        app = _build_protected_app(pub, [("/ecs", ["readonly"])])
        client = TestClient(app)
        r = client.get("/ecs/sse", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


class TestPathRbac:
    def test_role_match_passes(self, rsa_keys):
        pub, priv = rsa_keys
        token = _make_token(priv, roles=["ecs-user"])
        app = _build_protected_app(pub, [("/ecs", ["ecs-user"])])
        client = TestClient(app)
        r = client.get("/ecs/sse", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_role_mismatch_403(self, rsa_keys):
        pub, priv = rsa_keys
        token = _make_token(priv, roles=["cts-user"])
        app = _build_protected_app(pub, [("/ecs", ["ecs-user"])])
        client = TestClient(app)
        r = client.get("/ecs/sse", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_no_required_roles_passes(self, rsa_keys):
        pub, priv = rsa_keys
        token = _make_token(priv, roles=["anything"])
        app = _build_protected_app(pub, [("/ecs", [])])
        client = TestClient(app)
        r = client.get("/ecs/sse", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200


class TestIdentityInjection:
    def test_scope_receives_identity(self, rsa_keys):
        """After the middleware, scope["mcp_identity"] should be an Identity."""
        pub, priv = rsa_keys
        token = _make_token(priv, sub="bob", roles=["admin"])

        captured = {}

        async def capture(request):
            # The middleware should have injected the identity into the scope.
            captured["identity"] = request.scope.get("mcp_identity")
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/ecs/sse", capture, methods=["GET"])])
        app.add_middleware(
            GatewayAuthMiddleware,
            public_key_spec=pub,
            issuer="mcp-gateway",
            audience=None,
            leeway=30,
            path_roles=[("/ecs", ["admin"])],
            exempt_paths=("/healthz",),
        )
        client = TestClient(app)
        r = client.get("/ecs/sse", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        identity = captured["identity"]
        assert isinstance(identity, Identity)
        assert identity.sub == "bob"
        assert "admin" in identity.roles


class TestExemptPaths:
    def test_healthz_no_token(self, rsa_keys):
        pub, _ = rsa_keys
        app = _build_protected_app(pub, [("/ecs", ["readonly"])])
        client = TestClient(app)
        r = client.get("/healthz")
        assert r.status_code == 200
