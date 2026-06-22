"""Test: AutoAuth strategy — auto-detect gateway identity or dev fallback."""
from __future__ import annotations

import pytest

from mcp_auth_common import AutoAuth, Identity
from mcp_auth_common.errors import AuthError


class TestAutoAuthGatewayMode:
    """When scope carries mcp_identity, use it (gateway mode)."""

    def test_scope_with_identity_passes(self):
        auth = AutoAuth()
        identity = Identity(sub="alice", roles=["admin"])
        scope = {"mcp_identity": identity}
        result = auth.resolve(scope)
        assert result.sub == "alice"
        assert result.roles == ["admin"]

    def test_dict_identity_converted(self):
        """If someone put a dict instead of Identity, it should be coerced."""
        auth = AutoAuth()
        scope = {"mcp_identity": {"sub": "bob", "roles": ["readonly"], "tenant": "t1"}}
        result = auth.resolve(scope)
        assert isinstance(result, Identity)
        assert result.sub == "bob"
        assert result.tenant == "t1"

    def test_invalid_identity_raises(self):
        auth = AutoAuth()
        scope = {"mcp_identity": "not-a-valid-identity"}
        with pytest.raises(AuthError) as exc_info:
            auth.resolve(scope)
        assert exc_info.value.status == 401


class TestAutoAuthDevFallback:
    """When scope has no mcp_identity, synthesise dev identity with WARN."""

    def test_empty_scope_dev_fallback(self):
        auth = AutoAuth()
        identity = auth.resolve({})
        assert identity.sub == "dev-local"
        assert "admin" in identity.roles

    def test_none_scope_dev_fallback(self):
        auth = AutoAuth()
        identity = auth.resolve(None)
        assert identity.sub == "dev-local"
        assert "admin" in identity.roles

    def test_scope_without_identity_dev_fallback(self):
        auth = AutoAuth()
        identity = auth.resolve({"type": "http", "path": "/ecs/sse"})
        assert identity.sub == "dev-local"

    def test_custom_subject_and_roles(self):
        auth = AutoAuth(dev_subject="test-user", dev_roles=["readonly", "operator"])
        identity = auth.resolve(None)
        assert identity.sub == "test-user"
        assert "readonly" in identity.roles
        assert "operator" in identity.roles

    def test_warning_emitted_once(self, caplog):
        """First fallback emits WARNING, subsequent ones are DEBUG."""
        import logging
        auth = AutoAuth()
        with caplog.at_level(logging.WARNING, logger="mcp_auth_common"):
            auth.resolve(None)  # first → WARNING
            auth.resolve(None)  # second → DEBUG only
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "NOT behind the MCP gateway" in warnings[0].message
