"""Tests for config loading and secret masking."""
from __future__ import annotations

import pytest

from ecs_mcp_server.config import (
    DEFAULT_PROJECT_ID,
    DEFAULT_REGION,
    load_settings,
    mask_secret,
)


def test_mask_secret_short():
    assert mask_secret("abc") == "***"
    assert mask_secret("") == ""
    assert mask_secret(None) == ""  # type: ignore[arg-type]


def test_mask_secret_long():
    s = "AKIDABCDEF1234567890"  # 20 chars
    masked = mask_secret(s)
    assert masked.startswith("AKID")
    assert masked.endswith("7890")
    assert "*" in masked
    # Original chars in the middle should not appear
    assert "ABCDEF" not in masked


def test_load_settings_missing_required(monkeypatch):
    monkeypatch.delenv("HUAWEICLOUD_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("HUAWEICLOUD_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert exc.value.code == 2


def test_load_settings_defaults(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AK" + "X" * 18)
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SK" + "Y" * 38)
    s = load_settings()
    assert s.project_id == DEFAULT_PROJECT_ID
    assert s.region == DEFAULT_REGION
    assert s.log_file is None
    assert s.log_level == "INFO"


def test_settings_masked_no_full_secret_leak(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AKIDABCDEFGHIJ123456")
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SKABCDEFGHIJ" + "Z" * 30)
    s = load_settings()
    masked = s.masked()
    assert "ABCDEFGHIJ" not in masked["access_key_id"]
    assert "ABCDEFGHIJ" not in masked["secret_access_key"]
