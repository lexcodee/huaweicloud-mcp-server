"""Tests for config loading and secret-masking log filter."""
from __future__ import annotations

import logging
from io import StringIO

import pytest

from huaweicloud_mcp.config import load_settings
from huaweicloud_mcp.logging_setup import SecretMaskingFilter, setup_logging


def test_load_settings_fails_fast_when_missing(monkeypatch, capsys):
    monkeypatch.delenv("HUAWEICLOUD_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("HUAWEICLOUD_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("HUAWEICLOUD_REGION", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert exc.value.code == 2
    captured = capsys.readouterr().err
    assert "missing required env vars" in captured
    assert "HUAWEICLOUD_REGION" in captured


def test_load_settings_happy(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AKID" + "X" * 16)
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SK" + "Y" * 38)
    monkeypatch.setenv("HUAWEICLOUD_REGION", "af-south-1")
    monkeypatch.setenv("CODEARTS_DEFAULT_PROJECT_ID", "proj-1")

    s = load_settings()
    assert s.region == "af-south-1"
    assert s.default_project_id == "proj-1"
    masked = s.masked()
    assert masked["access_key_id"].startswith("AKID")
    assert "*" in masked["access_key_id"]
    # Middle of the SK must be masked (not all Y's preserved)
    assert masked["secret_access_key"].count("*") >= 30
    assert masked["secret_access_key"].startswith("SKYY")


def test_secret_masking_filter_replaces_known_secret():
    f = SecretMaskingFilter(known_secrets=["SUPERSECRETVALUE12345"])
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="leaked SUPERSECRETVALUE12345 here", args=(), exc_info=None,
    )
    assert f.filter(record) is True
    assert "SUPERSECRETVALUE12345" not in record.getMessage()


def test_setup_logging_writes_to_stderr_only(capsys):
    log = setup_logging(level="INFO", known_secrets=["AKIDLEAKEDLEAKED1234"])
    log.info("hi from leaked AKIDLEAKEDLEAKED1234 token")
    captured = capsys.readouterr()
    assert "AKIDLEAKEDLEAKED1234" not in captured.err
    assert "AKIDLEAKEDLEAKED1234" not in captured.out
    # stdout MUST stay clean for stdio MCP transport
    assert captured.out == ""