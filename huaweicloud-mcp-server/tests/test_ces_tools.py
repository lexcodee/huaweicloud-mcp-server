"""Tests for CES MCP tools.

Covers:
  - Server registration (ces in ALL_SERVICES, tools appear)
  - ces_list_metrics (v1 SDK)
  - ces_get_metric_data (v1 SDK, ShowMetricData)
  - ces_query_alarm_rules (list + detail dispatch)
  - ces_list_alarm_histories
  - ces_query_resource_groups (list + detail dispatch)
  - ces_list_event_data (list + detail dispatch)
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.server import ALL_SERVICES, build_server
from huaweicloud_mcp.services.ces.tools.metric import make_metric_tools
from huaweicloud_mcp.services.ces.tools.alarm import make_alarm_tools
from huaweicloud_mcp.services.ces.tools.resource_group import make_resource_group_tools
from huaweicloud_mcp.services.ces.tools.event import make_event_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ces_settings() -> Settings:
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
def mock_ces_client(monkeypatch):
    """Replace get_client for 'ces' (v2) with a MagicMock."""
    fake = MagicMock(name="CesClient")
    for mod in (
        "huaweicloud_mcp.services.ces.tools.metric",
        "huaweicloud_mcp.services.ces.tools.alarm",
        "huaweicloud_mcp.services.ces.tools.resource_group",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def mock_ces_v1_client(monkeypatch):
    """Replace get_client for 'ces_v1' with a MagicMock."""
    fake = MagicMock(name="CesV1Client")
    for mod in (
        "huaweicloud_mcp.services.ces.tools.metric",
        "huaweicloud_mcp.services.ces.tools.event",
    ):
        # Need a dispatcher: return v1 fake when service=='ces_v1', else v2
        pass
    return fake


@pytest.fixture
def mock_both_ces_clients(monkeypatch):
    """Replace get_client with a dispatcher returning v1 or v2 mock."""
    fake_v2 = MagicMock(name="CesClient")
    fake_v1 = MagicMock(name="CesV1Client")

    def _get_client(service, settings):
        if service == "ces_v1":
            return fake_v1
        return fake_v2

    for mod in (
        "huaweicloud_mcp.services.ces.tools.metric",
        "huaweicloud_mcp.services.ces.tools.alarm",
        "huaweicloud_mcp.services.ces.tools.resource_group",
        "huaweicloud_mcp.services.ces.tools.event",
    ):
        monkeypatch.setattr(f"{mod}.get_client", _get_client)

    return fake_v2, fake_v1


@pytest.fixture
def env_credentials(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AKID" + "X" * 16)
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SK" + "Y" * 38)
    monkeypatch.setenv("HUAWEICLOUD_REGION", "af-south-1")
    monkeypatch.setenv("HUAWEICLOUD_PROJECT_ID", "15f2d47addb14784b82eb910447250a9")


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------

def test_ces_is_in_all_services():
    assert "ces" in ALL_SERVICES


def test_build_server_registers_ces_tools(env_credentials):
    mcp = build_server(enabled=["ces"])
    tm = getattr(mcp, "_tool_manager", None)
    assert tm is not None
    names = set(tm._tools.keys())
    expected = {
        "ces_list_metrics",
        "ces_get_metric_data",
        "ces_query_alarm_rules",
        "ces_list_alarm_histories",
        "ces_query_resource_groups",
        "ces_list_event_data",
    }
    missing = expected - names
    assert not missing, f"missing CES tools: {missing}"


def test_build_server_isolates_ces_when_only_other_services(env_credentials):
    mcp = build_server(enabled=["ecs"])
    tm = mcp._tool_manager
    names = set(tm._tools.keys())
    ces_tools = {n for n in names if n.startswith("ces_")}
    assert not ces_tools, f"CES tools leaked when enabled=ecs only: {ces_tools}"


# ---------------------------------------------------------------------------
# ces_list_metrics
# ---------------------------------------------------------------------------

def _fake_metric(namespace="SYS.ECS", metric_name="cpu_util", unit="%"):
    dim = SimpleNamespace(name="instance_id", value="abc-123")
    return SimpleNamespace(
        namespace=namespace,
        metric_name=metric_name,
        unit=unit,
        dimensions=[dim],
    )


def test_ces_list_metrics(ces_settings, mock_both_ces_clients):
    fake_v2, fake_v1 = mock_both_ces_clients
    resp = MagicMock()
    resp.metrics = [_fake_metric(), _fake_metric(metric_name="mem_util")]
    fake_v1.list_metrics.return_value = resp

    tools = make_metric_tools(ces_settings)
    out = tools["ces_list_metrics"](namespace="SYS.ECS")

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["metrics"][0]["namespace"] == "SYS.ECS"
    assert data["metrics"][0]["metric_name"] == "cpu_util"
    assert len(data["metrics"][0]["dimensions"]) == 1

    # SDK filter propagated
    sent = fake_v1.list_metrics.call_args[0][0]
    assert sent.namespace == "SYS.ECS"


def test_ces_list_metrics_empty(ces_settings, mock_both_ces_clients):
    fake_v2, fake_v1 = mock_both_ces_clients
    resp = MagicMock()
    resp.metrics = []
    fake_v1.list_metrics.return_value = resp

    tools = make_metric_tools(ces_settings)
    out = tools["ces_list_metrics"]()

    assert out["ok"] is True
    assert out["data"]["count"] == 0


# ---------------------------------------------------------------------------
# ces_get_metric_data
# ---------------------------------------------------------------------------

def _fake_v1_datapoint(timestamp=1700000000000, average=45.2, unit="%"):
    """Fake v1 Datapoint (has average/max/min/sum/variance fields)."""
    return SimpleNamespace(
        timestamp=timestamp,
        average=average,
        max=None,
        min=None,
        sum=None,
        variance=None,
        unit=unit,
    )


def test_ces_get_metric_data_single(ces_settings, mock_both_ces_clients):
    fake_v2, fake_v1 = mock_both_ces_clients
    resp = MagicMock()
    resp.metric_name = "cpu_util"
    resp.datapoints = [_fake_v1_datapoint()]
    fake_v1.show_metric_data.return_value = resp

    tools = make_metric_tools(ces_settings)
    out = tools["ces_get_metric_data"](
        metrics=[{"namespace": "SYS.ECS", "metric_name": "cpu_util", "dimensions": "instance_id,abc-123"}],
        from_time="-5m",
    )

    assert out["ok"] is True
    data = out["data"]
    assert data["total_returned"] == 1
    assert data["results"][0]["metric_name"] == "cpu_util"
    assert len(data["results"][0]["data_points"]) == 1
    assert data["results"][0]["data_points"][0]["value"] == 45.2


def test_ces_get_metric_data_batch(ces_settings, mock_both_ces_clients):
    fake_v2, fake_v1 = mock_both_ces_clients
    resp1 = MagicMock()
    resp1.metric_name = "cpu_util"
    resp1.datapoints = [_fake_v1_datapoint(average=45.0)]
    resp2 = MagicMock()
    resp2.metric_name = "mem_util"
    resp2.datapoints = [_fake_v1_datapoint(average=72.5)]
    fake_v1.show_metric_data.side_effect = [resp1, resp2]

    tools = make_metric_tools(ces_settings)
    out = tools["ces_get_metric_data"](
        metrics=[
            {"namespace": "SYS.ECS", "metric_name": "cpu_util", "dimensions": "instance_id,abc-123"},
            {"namespace": "SYS.ECS", "metric_name": "mem_util", "dimensions": "instance_id,abc-123"},
        ],
        from_time="-5m",
    )

    assert out["ok"] is True
    data = out["data"]
    assert data["total_returned"] == 2
    assert data["results"][0]["metric_name"] == "cpu_util"
    assert data["results"][1]["metric_name"] == "mem_util"


def test_ces_get_metric_data_invalid_spec(ces_settings, mock_both_ces_clients):
    tools = make_metric_tools(ces_settings)
    out = tools["ces_get_metric_data"](
        metrics=[{"namespace": ""}],  # missing metric_name
    )
    assert out["ok"] is False
    assert "INVALID_PARAMS" in (out["error"].get("code") or "")


# ---------------------------------------------------------------------------
# ces_query_alarm_rules
# ---------------------------------------------------------------------------

def _fake_alarm_rule(alarm_id="al12345678901234567890ab", name="cpu_high"):
    alarm_type = SimpleNamespace(
        ALL_INSTANCE=SimpleNamespace(),
        MULTI_INSTANCE=None,
        RESOURCE_GROUP=None,
        EVENT_SYS=None,
        EVENT_CUSTOM=None,
        DNSHEALTHCHECK=None,
    )
    return SimpleNamespace(
        alarm_id=alarm_id,
        name=name,
        description="CPU exceeds 80%",
        namespace="SYS.ECS",
        type=alarm_type,
        enabled=True,
        notification_enabled=True,
        alarm_template_id=None,
        notification_begin_time="00:00",
        notification_end_time="24:00",
        effective_timezone=None,
        enterprise_project_id="0",
        product_name=None,
        resource_level=None,
        alarm_notifications=[],
        ok_notifications=[],
        policies=[],
        resources=[],
        tags=[],
    )


def test_ces_query_alarm_rules_list(ces_settings, mock_ces_client):
    resp = MagicMock()
    resp.alarms = [_fake_alarm_rule(), _fake_alarm_rule(alarm_id="al99999999999999999999999cd", name="mem_high")]
    mock_ces_client.list_alarm_rules.return_value = resp

    tools = make_alarm_tools(ces_settings)
    out = tools["ces_query_alarm_rules"](namespace="SYS.ECS")

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["alarms"][0]["alarm_id"] == "al12345678901234567890ab"
    assert data["alarms"][0]["name"] == "cpu_high"


def test_ces_query_alarm_rules_detail(ces_settings, mock_ces_client):
    alarm = _fake_alarm_rule()
    resp = MagicMock()
    resp.alarms = [alarm]
    mock_ces_client.list_alarm_rules.return_value = resp

    pol_resp = MagicMock()
    pol_resp.policies = []
    mock_ces_client.list_alarm_rule_policies.return_value = pol_resp

    res_resp = MagicMock()
    res_resp.resources = []
    mock_ces_client.list_alarm_rule_resources.return_value = res_resp

    tools = make_alarm_tools(ces_settings)
    out = tools["ces_query_alarm_rules"](alarm_id="al12345678901234567890ab")

    assert out["ok"] is True
    data = out["data"]
    assert data["alarm_id"] == "al12345678901234567890ab"
    assert data["name"] == "cpu_high"


def test_ces_query_alarm_rules_not_found(ces_settings, mock_ces_client):
    resp = MagicMock()
    resp.alarms = []
    mock_ces_client.list_alarm_rules.return_value = resp

    tools = make_alarm_tools(ces_settings)
    out = tools["ces_query_alarm_rules"](alarm_id="al_notexist")

    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# ces_list_alarm_histories
# ---------------------------------------------------------------------------

def _fake_alarm_history(record_id="ah12345678901234567890ab"):
    metric = SimpleNamespace(
        namespace="SYS.ECS",
        metric_name="cpu_util",
        dimensions=[SimpleNamespace(name="instance_id", value="abc-123")],
    )
    condition = SimpleNamespace(
        comparison_operator=">",
        value=80.0,
        count=3,
        filter="average",
        period=300,
        unit="%",
        suppress_duration=0,
    )
    return SimpleNamespace(
        record_id=record_id,
        alarm_id="al12345678901234567890ab",
        name="cpu_high",
        status="alarm",
        level=1,
        type="MULTI_INSTANCE",
        action_enabled=True,
        begin_time="2024-01-01T00:00:00Z",
        end_time=None,
        first_alarm_time="2024-01-01T00:00:00Z",
        last_alarm_time="2024-01-01T00:05:00Z",
        alarm_recovery_time=None,
        metric=metric,
        condition=condition,
        additional_info=None,
        alarm_actions=[],
        ok_actions=[],
        data_points=[],
        mask_status=None,
    )


def test_ces_list_alarm_histories(ces_settings, mock_ces_client):
    resp = MagicMock()
    resp.alarm_histories = [_fake_alarm_history()]
    mock_ces_client.list_alarm_histories.return_value = resp

    tools = make_alarm_tools(ces_settings)
    out = tools["ces_list_alarm_histories"](from_time="-1h")

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 1
    assert data["alarm_histories"][0]["record_id"] == "ah12345678901234567890ab"
    assert data["alarm_histories"][0]["status"] == "alarm"


# ---------------------------------------------------------------------------
# ces_query_resource_groups
# ---------------------------------------------------------------------------

def _fake_resource_group(group_id="rg12345678901234567890ab", group_name="prod-group"):
    return SimpleNamespace(
        group_id=group_id,
        group_name=group_name,
        type="custom",
        status="health",
        create_time="2024-01-01T00:00:00Z",
        update_time="2024-01-02T00:00:00Z",
        enterprise_project_id="0",
        association_alarm_templates=None,
        product_names=None,
        resource_level=None,
        tags=None,
    )


def test_ces_query_resource_groups_list(ces_settings, mock_ces_client):
    resp = MagicMock()
    resp.resource_groups = [_fake_resource_group()]
    mock_ces_client.list_resource_groups.return_value = resp

    tools = make_resource_group_tools(ces_settings)
    out = tools["ces_query_resource_groups"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 1
    assert data["resource_groups"][0]["group_id"] == "rg12345678901234567890ab"


def test_ces_query_resource_groups_detail(ces_settings, mock_ces_client):
    group = _fake_resource_group()
    mock_ces_client.show_resource_group.return_value = group

    res_resp = MagicMock()
    res_resp.resources = []
    mock_ces_client.list_resource_groups_services_resources.return_value = res_resp

    tools = make_resource_group_tools(ces_settings)
    out = tools["ces_query_resource_groups"](group_id="rg12345678901234567890ab")

    assert out["ok"] is True
    data = out["data"]
    assert data["group_id"] == "rg12345678901234567890ab"
    assert data["group_name"] == "prod-group"


# ---------------------------------------------------------------------------
# ces_list_event_data
# ---------------------------------------------------------------------------

def _fake_event_info(event_name="restartServer", event_type="EVENT.SYS"):
    return SimpleNamespace(
        event_name=event_name,
        event_type=event_type,
        sub_event_type="SUB_EVENT.OPS",
        event_count=2,
        latest_event_source="SYS.ECS",
        latest_occur_time=1700000000000,
    )


def test_ces_list_event_data_list(ces_settings, mock_both_ces_clients):
    fake_v2, fake_v1 = mock_both_ces_clients
    resp = MagicMock()
    resp.events = [_fake_event_info()]
    fake_v1.list_events.return_value = resp

    tools = make_event_tools(ces_settings)
    out = tools["ces_list_event_data"](event_type="EVENT.SYS", from_time="-1d")

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 1
    assert data["events"][0]["event_name"] == "restartServer"


def test_ces_list_event_data_detail(ces_settings, mock_both_ces_clients):
    fake_v2, fake_v1 = mock_both_ces_clients
    resp = MagicMock()
    resp.event_name = "restartServer"
    resp.event_type = "EVENT.SYS"
    resp.sub_event_type = "SUB_EVENT.OPS"
    resp.event_sources = ["SYS.ECS"]
    resp.event_users = ["user1"]
    resp.event_info = _fake_event_info()
    fake_v1.list_event_detail.return_value = resp

    tools = make_event_tools(ces_settings)
    out = tools["ces_list_event_data"](event_name="restartServer", from_time="-1d")

    assert out["ok"] is True
    data = out["data"]
    assert data["event_name"] == "restartServer"
