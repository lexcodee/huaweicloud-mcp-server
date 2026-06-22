"""Tests for mask_utils — sensitive-value masking and truncation.

Key scenarios:
  - password/secret/token values are masked
  - resource_name / user_password_policy_name are NOT masked (interior keyword)
  - access_key_id is NOT masked (CTS identity metadata, not a secret)
  - access_key / accessKey / secret_key ARE masked (trailing keyword)
  - nested JSON is walked
  - stringly-encoded JSON is recursed into
  - regex fallback for non-JSON text
"""
from __future__ import annotations

import json

import pytest

from cts_mcp_server.mask_utils import (
    MASK_PLACEHOLDER,
    _is_sensitive_key,
    mask_and_truncate,
    mask_sensitive,
    truncate,
)


class TestIsSensitiveKey:
    """Token-boundary logic for the structured walk."""

    def test_password(self):
        assert _is_sensitive_key("password") is True

    def test_new_password(self):
        assert _is_sensitive_key("new_password") is True

    def test_newPassword_camel(self):
        assert _is_sensitive_key("newPassword") is True

    def test_user_password_policy_name_interior(self):
        """'password' is interior, not trailing → NOT sensitive."""
        assert _is_sensitive_key("user_password_policy_name") is False

    def test_password_policy_name_interior(self):
        assert _is_sensitive_key("password_policy_name") is False

    def test_resource_name_not_sensitive(self):
        assert _is_sensitive_key("resource_name") is False

    def test_access_key_id_not_sensitive(self):
        """'access_key_id' — trailing pair is ('key', 'id'), not in pairs."""
        assert _is_sensitive_key("access_key_id") is False

    def test_access_key_trailing(self):
        assert _is_sensitive_key("access_key") is True

    def test_secret_key_trailing(self):
        assert _is_sensitive_key("secret_key") is True

    def test_private_key_trailing(self):
        assert _is_sensitive_key("private_key") is True

    def test_api_key_trailing(self):
        assert _is_sensitive_key("api_key") is True

    def test_client_secret_trailing(self):
        assert _is_sensitive_key("client_secret") is True

    def test_token_trailing(self):
        assert _is_sensitive_key("token") is True

    def test_auth_token_trailing(self):
        assert _is_sensitive_key("auth_token") is True

    def test_refresh_token_trailing(self):
        assert _is_sensitive_key("refresh_token") is True

    def test_bearer_token_trailing(self):
        assert _is_sensitive_key("bearer_token") is True

    def test_concatenated_accesskey(self):
        assert _is_sensitive_key("accesskey") is True

    def test_concatenated_accessKey_camel(self):
        assert _is_sensitive_key("accessKey") is True

    def test_empty(self):
        assert _is_sensitive_key("") is False

    def test_unrelated(self):
        assert _is_sensitive_key("display_name") is False


class TestMaskSensitiveStructured:
    """Structured JSON walk."""

    def test_password_masked(self):
        payload = {"password": "hunter2"}
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        assert parsed["password"] == MASK_PLACEHOLDER

    def test_resource_name_preserved(self):
        payload = {"resource_name": "my-bucket-password-policy"}
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        assert parsed["resource_name"] == "my-bucket-password-policy"

    def test_mixed_keys(self):
        """user_password_policy_name kept, new_password masked."""
        payload = {
            "user_password_policy_name": "strict",
            "new_password": "hunter2",
        }
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        assert parsed["user_password_policy_name"] == "strict"
        assert parsed["new_password"] == MASK_PLACEHOLDER

    def test_access_key_id_kept(self):
        """CTS routinely records access_key_id in user info — must not mask."""
        payload = {"access_key_id": "AKIDXXXXXXXXXXXXXXXX"}
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        assert parsed["access_key_id"] == "AKIDXXXXXXXXXXXXXXXX"

    def test_access_key_masked(self):
        payload = {"access_key": "AKIDXXXXXXXXXXXXXXXX"}
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        assert parsed["access_key"] == MASK_PLACEHOLDER

    def test_nested(self):
        payload = {"body": {"password": "secret123", "name": "alice"}}
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        assert parsed["body"]["password"] == MASK_PLACEHOLDER
        assert parsed["body"]["name"] == "alice"

    def test_stringly_encoded_json(self):
        """CTS sometimes stores request as a JSON string within a JSON field."""
        inner = json.dumps({"password": "hunter2"})
        payload = {"request": inner}
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        inner_parsed = json.loads(parsed["request"])
        assert inner_parsed["password"] == MASK_PLACEHOLDER

    def test_none_returns_empty(self):
        assert mask_sensitive(None) == ""

    def test_list_input(self):
        payload = [{"password": "a"}, {"name": "b"}]
        result = mask_sensitive(payload)
        parsed = json.loads(result)
        assert parsed[0]["password"] == MASK_PLACEHOLDER
        assert parsed[1]["name"] == "b"


class TestMaskSensitiveRegex:
    """Regex fallback for non-JSON text."""

    def test_form_style_password(self):
        text = "password=hunter2"
        result = mask_sensitive(text)
        assert MASK_PLACEHOLDER in result
        assert "hunter2" not in result

    def test_form_style_token(self):
        text = "token: abc123def"
        result = mask_sensitive(text)
        assert MASK_PLACEHOLDER in result
        assert "abc123def" not in result

    def test_resource_name_not_touched(self):
        text = "resource_name: my-bucket"
        result = mask_sensitive(text)
        assert "my-bucket" in result


class TestTruncate:
    def test_short(self):
        text, truncated = truncate("hello", 10)
        assert text == "hello"
        assert truncated is False

    def test_exact(self):
        text, truncated = truncate("hello", 5)
        assert text == "hello"
        assert truncated is False

    def test_long(self):
        text, truncated = truncate("hello world", 5)
        assert text.startswith("hello")
        assert "...[TRUNCATED]" in text
        assert truncated is True

    def test_none(self):
        text, truncated = truncate(None, 10)
        assert text == ""
        assert truncated is False


class TestMaskAndTruncate:
    def test_mask_then_truncate(self):
        payload = {"password": "x" * 600}
        text, truncated = mask_and_truncate(payload, 500)
        assert MASK_PLACEHOLDER in text
        # The result should be short because the value was masked to a short string
        assert len(text) <= 500 + len("...[TRUNCATED]")
