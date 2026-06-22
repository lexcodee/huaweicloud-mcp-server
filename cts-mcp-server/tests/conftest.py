"""Pytest fixtures for CTS MCP tests."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from cts_mcp_server.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Don't accidentally hit a real cloud during tests."""
    for k in [
        "HUAWEICLOUD_ACCESS_KEY_ID",
        "HUAWEICLOUD_SECRET_ACCESS_KEY",
        "HUAWEICLOUD_PROJECT_ID",
        "HUAWEICLOUD_REGION",
        "CTS_DEFAULT_TIMEZONE",
        "CTS_MCP_LOG_FILE",
        "CTS_MCP_LOG_LEVEL",
    ]:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        default_timezone="Asia/Shanghai",
        log_file=None,
        log_level="INFO",
    )
