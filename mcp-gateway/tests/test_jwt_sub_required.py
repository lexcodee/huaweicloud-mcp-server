"""Test: JWT without 'sub' claim is rejected (401).

Verifies the fix for _identity_from_claims raising AuthError when
the 'sub' claim is missing or empty.
"""
from __future__ import annotations

import pytest

from mcp_auth_common.errors import AuthError
from mcp_auth_common.strategy import _identity_from_claims


class TestSubClaimRequired:
    def test_missing_sub_raises_401(self):
        with pytest.raises(AuthError) as exc_info:
            _identity_from_claims({"roles": ["admin"]})
        assert exc_info.value.status == 401
        assert "sub" in exc_info.value.reason

    def test_empty_sub_raises_401(self):
        with pytest.raises(AuthError) as exc_info:
            _identity_from_claims({"sub": "", "roles": ["admin"]})
        assert exc_info.value.status == 401

    def test_whitespace_sub_raises_401(self):
        with pytest.raises(AuthError) as exc_info:
            _identity_from_claims({"sub": "  ", "roles": ["admin"]})
        assert exc_info.value.status == 401

    def test_valid_sub_succeeds(self):
        identity = _identity_from_claims({"sub": "alice", "roles": ["admin"]})
        assert identity.sub == "alice"

    def test_numeric_sub_coerced_to_string(self):
        identity = _identity_from_claims({"sub": 12345, "roles": ["readonly"]})
        assert identity.sub == "12345"
