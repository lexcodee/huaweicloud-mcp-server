"""Shared pytest fixtures for the CodeArts Pipeline MCP server tests."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipeline_mcp_server.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for k in [
        "HUAWEICLOUD_ACCESS_KEY_ID",
        "HUAWEICLOUD_SECRET_ACCESS_KEY",
        "HUAWEICLOUD_REGION",
        "CODEARTS_REGION",
        "CODEARTS_DEFAULT_PROJECT_ID",
        "PIPELINE_MCP_LOG_LEVEL",
        "PIPELINE_MCP_LOG_FILE",
        "PIPELINE_MCP_HTTP_TIMEOUT",
        "PIPELINE_MCP_NETWORK_RETRIES",
    ]:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        region="af-south-1",
        default_project_id="ddb5e3259e81494f9d083c917e173e5b",
        log_level="WARNING",
        log_file=None,
        http_timeout=30,
        network_retries=2,
    )


@pytest.fixture
def mock_client(monkeypatch):
    """Replace get_client in every tool module with a single MagicMock."""
    fake = MagicMock(name="CodeArtsPipelineClient")
    for mod in (
        "pipeline_mcp_server.tools.query",
        "pipeline_mcp_server.tools.execution",
        "pipeline_mcp_server.tools.update",
        "pipeline_mcp_server.tools.lifecycle",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda settings, _f=fake: _f)
    return fake


# ---------------------------------------------------------------------------
# Helpers — build SDK-shaped objects out of dicts, the way the real SDK does
# (each level is a SimpleNamespace whose attribute access mirrors openapi
# attribute_map).
# ---------------------------------------------------------------------------

def _ns(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


@pytest.fixture
def sample_definition_obj() -> dict:
    return {
        "stages": [
            {
                "name": "Stage 1",
                "pre": [
                    {"task": "official_devcloud_autoTrigger", "sequence": 0},
                ],
                "jobs": [
                    {"id": "job-1", "name": "Build"},
                ],
                "post": [],
            },
            {
                "name": "Stage 2",
                "pre": [
                    {"task": "official_devcloud_autoTrigger", "sequence": 0},
                ],
                "jobs": [
                    {"id": "job-2", "name": "Deploy"},
                ],
                "post": [],
            },
        ],
    }


@pytest.fixture
def sample_pipeline_detail(sample_definition_obj):
    """Mimics the SDK's ShowPipelineDetailResponse shape."""

    sources = [
        _ns(
            type="code",
            params=_ns(
                git_type="github",
                codehub_id=None,
                endpoint_id="endpoint-1",
                default_branch="main",
                git_url="https://github.com/example/repo.git",
                ssh_git_url="git@github.com:example/repo.git",
                web_url="https://github.com/example/repo",
                repo_name="repo",
                alias="primary",
                # PipelineSourceParam-only fields that should NOT leak into
                # CodeSourceParams (the update-write side):
                artifact_type=None,
                version="1.0",
                branch_filter="*",
                directory=None,
                directory_id=None,
                organization=None,
                package_name=None,
                version_strategy=None,
                source_system=None,
                artifact_type_name=None,
            ),
        )
    ]

    variables = [
        _ns(
            pipeline_id="p1", name="VAR_A", sequence=0, type="string",
            value="alpha", is_secret=False, description="first var",
            is_runtime=False, limits=None, is_reset=False,
            latest_value="alpha", runtime_value=None,
        ),
        _ns(
            pipeline_id="p1", name="SECRET_TOKEN", sequence=1, type="string",
            value="hidden", is_secret=True, description="api token",
            is_runtime=True, limits=[], is_reset=False,
            latest_value=None, runtime_value=None,
        ),
    ]
    schedules = [
        _ns(
            uuid="sched-1", type="weekly", name="nightly",
            enable=True, days_of_week=[1, 2, 3, 4, 5], time_zone="Asia/Shanghai",
        ),
    ]
    triggers = [
        _ns(
            pipeline_id="p1", git_url="https://github.com/example/repo.git",
            git_type="github", is_auto_commit=True,
            events=[_ns(type="push", enable=True)],
            hook_id="hook-99", repo_id="r-1", endpoint_id="endpoint-1",
            callback_url="https://example.com/cb", security_token="tok",
        ),
    ]

    detail = _ns(
        id="pipeline-uuid",
        name="taifa-dev",
        description="dev pipeline",
        manifest_version="3.0",
        is_publish=False,
        creator_id="u-1",
        creator_name="alice",
        create_time=1700000000,
        update_time=1700000010,
        sources=sources,
        variables=variables,
        schedules=schedules,
        triggers=triggers,
        group_id="grp-1",
        component_id=None,
        project_id="proj-1",
        security_level=None,
        definition=json.dumps(sample_definition_obj, ensure_ascii=False),
    )
    return detail
