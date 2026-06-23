"""Test: wrap_tool maps AuthError to FORBIDDEN/UNAUTHORIZED, not INTERNAL_ERROR.

Verifies the fix for wrap_tool catching AuthError from require_role and
returning a structured error instead of the generic INTERNAL_ERROR fallback.
"""
from __future__ import annotations

import pytest

from mcp_auth_common.errors import AuthError
from huaweicloud_mcp.errors import ToolError, wrap_tool


class TestWrapToolAuthError:
    def test_auth_error_403_returns_forbidden(self):
        @wrap_tool
        def guarded():
            raise AuthError(403, "role-required:admin;caller-has:[readonly]")

        result = guarded()
        assert result["ok"] is False
        assert result["error"]["code"] == "FORBIDDEN"
        assert result["error"]["status_code"] == 403
        assert "admin" in result["error"]["message"]

    def test_auth_error_401_returns_unauthorized(self):
        @wrap_tool
        def guarded():
            raise AuthError(401, "jwt-missing-sub: 'sub' claim is required")

        result = guarded()
        assert result["ok"] is False
        assert result["error"]["code"] == "UNAUTHORIZED"
        assert result["error"]["status_code"] == 401

    def test_tool_error_still_works(self):
        @wrap_tool
        def normal_error():
            raise ToolError(code="NOT_FOUND", message="server xyz not found")

        result = normal_error()
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_unexpected_exception_still_internal_error(self):
        @wrap_tool
        def boom():
            raise RuntimeError("something broke")

        result = boom()
        assert result["ok"] is False
        assert result["error"]["code"] == "INTERNAL_ERROR"
