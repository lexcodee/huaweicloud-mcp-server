"""Pytest fixtures for ECS MCP tests."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from ecs_mcp_server.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Don't accidentally hit a real cloud during tests."""
    for k in [
        "HUAWEICLOUD_ACCESS_KEY_ID",
        "HUAWEICLOUD_SECRET_ACCESS_KEY",
        "HUAWEICLOUD_PROJECT_ID",
        "HUAWEICLOUD_REGION",
        "ECS_MCP_LOG_FILE",
        "ECS_MCP_LOG_LEVEL",
    ]:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def mock_client(monkeypatch):
    """Replace get_ecs_client with a MagicMock; tools see the mock as the
    Huawei Cloud client.
    """
    fake = MagicMock(name="EcsClient")
    monkeypatch.setattr(
        "ecs_mcp_server.tools.query.get_ecs_client", lambda settings: fake
    )
    monkeypatch.setattr(
        "ecs_mcp_server.tools.lifecycle.get_ecs_client", lambda settings: fake
    )
    monkeypatch.setattr(
        "ecs_mcp_server.tools.job.get_ecs_client", lambda settings: fake
    )
    return fake
