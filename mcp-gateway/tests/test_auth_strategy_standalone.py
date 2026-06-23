"""Test: StandaloneAuth — used internally by gateway middleware for JWT verify."""
from __future__ import annotations

import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_auth_common import Identity
from mcp_auth_common.errors import AuthError
from mcp_auth_common.strategy import StandaloneAuth


@pytest.fixture(scope="module")
def rsa_keys():
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


def _make_token(priv_pem, **overrides):
    now = int(time.time())
    payload = {"sub": "alice", "roles": ["readonly"], "iss": "mcp-gateway", "iat": now, "exp": now + 3600}
    payload.update(overrides)
    return jwt.encode(payload, priv_pem, algorithm="RS256")


def _scope_with_bearer(token: str) -> dict:
    return {"headers": [(b"authorization", f"Bearer {token}".encode())]}


class TestStandaloneAuth:
    """StandaloneAuth is used by the gateway middleware internally."""

    def test_valid_token(self, rsa_keys):
        pub, priv = rsa_keys
        auth = StandaloneAuth(public_key=pub, issuer="mcp-gateway")
        token = _make_token(priv)
        identity = auth.resolve(_scope_with_bearer(token))
        assert identity.sub == "alice"
        assert identity.roles == ["readonly"]

    def test_missing_bearer_401(self, rsa_keys):
        pub, _ = rsa_keys
        auth = StandaloneAuth(public_key=pub, issuer="mcp-gateway")
        with pytest.raises(AuthError) as exc_info:
            auth.resolve({"headers": []})
        assert exc_info.value.status == 401

    def test_expired_token_401(self, rsa_keys):
        pub, priv = rsa_keys
        auth = StandaloneAuth(public_key=pub, issuer="mcp-gateway", leeway=5)
        token = _make_token(priv, exp=int(time.time()) - 120)
        with pytest.raises(AuthError) as exc_info:
            auth.resolve(_scope_with_bearer(token))
        assert exc_info.value.status == 401

    def test_wrong_issuer_401(self, rsa_keys):
        pub, priv = rsa_keys
        auth = StandaloneAuth(public_key=pub, issuer="mcp-gateway")
        token = _make_token(priv, iss="wrong")
        with pytest.raises(AuthError) as exc_info:
            auth.resolve(_scope_with_bearer(token))
        assert exc_info.value.status == 401

    def test_roles_as_string(self, rsa_keys):
        """JWT 'roles' claim as a comma-separated string should be parsed."""
        pub, priv = rsa_keys
        auth = StandaloneAuth(public_key=pub, issuer="mcp-gateway")
        token = _make_token(priv, roles="admin,operator")
        identity = auth.resolve(_scope_with_bearer(token))
        assert "admin" in identity.roles
        assert "operator" in identity.roles

    def test_none_scope_401(self, rsa_keys):
        pub, _ = rsa_keys
        auth = StandaloneAuth(public_key=pub, issuer="mcp-gateway")
        with pytest.raises(AuthError) as exc_info:
            auth.resolve(None)
        assert exc_info.value.status == 401


class TestLoadPublicKeyChaining:
    """Test _load_public_key chaining: env var value can be file:/path."""

    def test_env_var_with_file_prefix(self, rsa_keys, tmp_path, monkeypatch):
        """env:VAR where VAR='file:/path/to/key.pem' resolves the file."""
        pub, _ = rsa_keys
        key_file = tmp_path / "pub.pem"
        key_file.write_text(pub)
        monkeypatch.setenv("TEST_PUB_KEY", f"file:{key_file}")
        from mcp_auth_common.strategy import _load_public_key
        result = _load_public_key("env:TEST_PUB_KEY")
        assert result.strip().startswith("-----BEGIN PUBLIC KEY-----")

    def test_env_var_with_inline_pem(self, rsa_keys, monkeypatch):
        """env:VAR where VAR='<PEM body>' returns PEM verbatim (no chaining)."""
        pub, _ = rsa_keys
        monkeypatch.setenv("TEST_PUB_KEY", pub)
        from mcp_auth_common.strategy import _load_public_key
        result = _load_public_key("env:TEST_PUB_KEY")
        assert result == pub

    def test_chaining_depth_limit(self, monkeypatch):
        """Circular env: refs raise RuntimeError."""
        monkeypatch.setenv("A", "env:B")
        monkeypatch.setenv("B", "env:A")
        from mcp_auth_common.strategy import _load_public_key
        with pytest.raises(RuntimeError, match="max depth"):
            _load_public_key("env:A")

    def test_file_spec_direct(self, rsa_keys, tmp_path):
        """file:/path/to/key.pem still works (no env: involved)."""
        pub, _ = rsa_keys
        key_file = tmp_path / "pub.pem"
        key_file.write_text(pub)
        from mcp_auth_common.strategy import _load_public_key
        result = _load_public_key(f"file:{key_file}")
        assert result.strip().startswith("-----BEGIN PUBLIC KEY-----")
