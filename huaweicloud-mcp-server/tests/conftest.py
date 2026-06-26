"""Unified pytest fixtures for huaweicloud-mcp-server tests.

Combines ECS, Pipeline, and CTS fixtures from the three original packages.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.errors import pending_actions


# --------------------------------------------------------------------------- #
# Environment isolation
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Don't accidentally hit a real cloud during tests."""
    for k in [
        "HUAWEICLOUD_ACCESS_KEY_ID",
        "HUAWEICLOUD_SECRET_ACCESS_KEY",
        "HUAWEICLOUD_PROJECT_ID",
        "HUAWEICLOUD_REGION",
        "CODEARTS_DEFAULT_PROJECT_ID",
        "CTS_DEFAULT_TIMEZONE",
        "HUAWEICLOUD_MCP_LOG_LEVEL",
        "HUAWEICLOUD_MCP_LOG_FILE",
        "HUAWEICLOUD_MCP_HTTP_TIMEOUT",
        "HUAWEICLOUD_MCP_NETWORK_RETRIES",
        "ECS_MCP_LOG_FILE",
        "ECS_MCP_LOG_LEVEL",
        "PIPELINE_MCP_LOG_LEVEL",
        "PIPELINE_MCP_LOG_FILE",
        "PIPELINE_MCP_HTTP_TIMEOUT",
        "PIPELINE_MCP_NETWORK_RETRIES",
        "CTS_MCP_LOG_FILE",
        "CTS_MCP_LOG_LEVEL",
        "MCP_ENABLED_SERVICES",
    ]:
        monkeypatch.delenv(k, raising=False)
    # Clear any pending destructive actions between tests
    pending_actions._store.clear()


# --------------------------------------------------------------------------- #
# Settings fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def settings() -> Settings:
    """Full settings with all fields populated (ECS + Pipeline + CTS)."""
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        region="af-south-1",
        project_id="15f2d47addb14784b82eb910447250a9",
        default_project_id="ddb5e3259e81494f9d083c917e173e5b",
        default_timezone="Asia/Shanghai",
        log_level="INFO",
        log_file=None,
        http_timeout=30,
        network_retries=2,
    )


@pytest.fixture
def ecs_settings() -> Settings:
    """Settings shaped like the old ECS conftest."""
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def pipeline_settings() -> Settings:
    """Settings shaped like the old Pipeline conftest."""
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
def cts_settings() -> Settings:
    """Settings shaped like the old CTS conftest."""
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        default_timezone="Asia/Shanghai",
        log_file=None,
        log_level="INFO",
    )


# --------------------------------------------------------------------------- #
# Mock client fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def mock_ecs_client(monkeypatch):
    """Replace get_client in ECS tool modules with a single MagicMock."""
    fake = MagicMock(name="EcsClient")
    for mod in (
        "huaweicloud_mcp.services.ecs.tools.query",
        "huaweicloud_mcp.services.ecs.tools.lifecycle",
        "huaweicloud_mcp.services.ecs.tools.job",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def mock_pipeline_client(monkeypatch):
    """Replace get_client in Pipeline tool modules with a single MagicMock."""
    fake = MagicMock(name="CodeArtsPipelineClient")
    for mod in (
        "huaweicloud_mcp.services.pipeline.tools.query",
        "huaweicloud_mcp.services.pipeline.tools.execution",
        "huaweicloud_mcp.services.pipeline.tools.update",
        "huaweicloud_mcp.services.pipeline.tools.lifecycle",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def mock_cts_client(monkeypatch):
    """Replace get_client in CTS tool modules with a single MagicMock."""
    fake = MagicMock(name="CtsClient")
    for mod in (
        "huaweicloud_mcp.services.cts.tools.search",
        "huaweicloud_mcp.services.cts.tools.detail",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def cce_settings() -> Settings:
    """Settings shaped for CCE tests (same shape as ECS)."""
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def mock_cce_client(monkeypatch):
    """Replace get_client in CCE tool modules with a single MagicMock."""
    fake = MagicMock(name="CceClient")
    for mod in (
        "huaweicloud_mcp.services.cce.tools.query",
        "huaweicloud_mcp.services.cce.tools.update",
        "huaweicloud_mcp.services.cce.tools.job",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def lts_settings() -> Settings:
    """Settings shaped for LTS tests."""
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        default_timezone="Asia/Shanghai",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def mock_lts_client(monkeypatch):
    """Replace get_client in LTS tool modules with a single MagicMock."""
    fake = MagicMock(name="LtsClient")
    for mod in (
        "huaweicloud_mcp.services.lts.tools.discovery",
        "huaweicloud_mcp.services.lts.tools.search",
        "huaweicloud_mcp.services.lts.tools.alarm",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def mock_vpc_client(monkeypatch):
    """Replace get_client in VPC tool modules with a single MagicMock."""
    fake = MagicMock(name="VpcClient")
    for mod in (
        "huaweicloud_mcp.services.vpc.tools.query",
        "huaweicloud_mcp.services.vpc.tools.manage",
        "huaweicloud_mcp.services.vpc.tools.network",
        "huaweicloud_mcp.services.vpc.tools.route",
        "huaweicloud_mcp.services.vpc.tools.flow_log",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def mock_eip_client(monkeypatch):
    """Replace get_client('eip', ...) in EIP tool module with a MagicMock."""
    fake = MagicMock(name="EipClient")
    monkeypatch.setattr(
        "huaweicloud_mcp.services.vpc.tools.eip.get_client",
        lambda service, settings, _f=fake: _f,
    )
    return fake


@pytest.fixture
def mock_lts_client_for_vpc(monkeypatch):
    """Replace get_client in VPC flow_log tool with a dual mock.

    Returns a dict {"vpc": vpc_fake, "lts": lts_fake} so tests can set
    return values on the correct client. The flow_log module calls
    get_client("vpc", ...) and get_client("lts", ...).
    """
    vpc_fake = MagicMock(name="VpcClient")
    lts_fake = MagicMock(name="LtsClient")
    _clients = {"vpc": vpc_fake, "lts": lts_fake}
    monkeypatch.setattr(
        "huaweicloud_mcp.services.vpc.tools.flow_log.get_client",
        lambda service, settings, _c=_clients: _c[service],
    )
    return _clients


@pytest.fixture
def obs_settings() -> Settings:
    """Settings shaped for OBS tests."""
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def mock_obs_client(monkeypatch):
    """Replace get_client in OBS tool modules with a single MagicMock."""
    fake = MagicMock(name="ObsClient")
    for mod in (
        "huaweicloud_mcp.services.obs.tools.query",
        "huaweicloud_mcp.services.obs.tools.manage",
        "huaweicloud_mcp.services.obs.tools.audit",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


# --------------------------------------------------------------------------- #
# Backward-compat aliases — old test files use `mock_client` and `settings`
# for whichever service they test. These are overridden per-test-directory
# by the service-specific fixtures above, but some tests import `mock_client`
# generically. We provide both names pointing to the same mock.
# --------------------------------------------------------------------------- #

# NOTE: Tests that use `mock_client` without specifying a service will fail
# if they run alongside another service's tests. The migrated test files
# should use the service-specific fixture names (mock_ecs_client, etc.).
# The `settings` fixture above is the unified one with all fields.


# --------------------------------------------------------------------------- #
# Pipeline-specific helper fixtures
# --------------------------------------------------------------------------- #

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
