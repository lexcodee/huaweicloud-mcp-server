"""Tests for lts_query_log_resources (groups + streams dispatch)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from huaweicloud_mcp.services.lts.tools.discovery import make_discovery_tools

VALID_GID = "abc12345-6789-4abc-def0-0123456789ab"
VALID_GID2 = "abc12345-6789-4abc-def0-0123456789cd"
VALID_SID = "11112222-6789-4abc-def0-0123456789ab"


def _fake_group(gid=VALID_GID, name="grp-prod", ttl=30):
    return SimpleNamespace(
        log_group_id=gid,
        log_group_name=name,
        log_group_name_alias=None,
        ttl_in_days=ttl,
        creation_time=1700000000000,
        tag=None,
    )


def _fake_stream(sid=VALID_SID, name="stream-a"):
    return SimpleNamespace(
        log_stream_id=sid,
        log_stream_name=name,
        log_stream_name_alias=None,
        ttl_in_days=30,
        hot_storage_days=7,
        filter_count=0,
        whether_log_storage=True,
        creation_time=1700000000000,
        tag=None,
    )


def test_query_log_resources_lists_groups(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.log_groups = [_fake_group(), _fake_group(gid=VALID_GID2, name="grp-dev")]
    mock_lts_client.list_log_groups.return_value = resp

    tools = make_discovery_tools(lts_settings)
    out = tools["lts_query_log_resources"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["mode"] == "groups"
    assert data["count"] == 2
    assert data["log_groups"][0]["id"] == VALID_GID
    assert data["log_groups"][0]["ttl_in_days"] == 30
    mock_lts_client.list_log_groups.assert_called_once()
    mock_lts_client.list_log_stream.assert_not_called()


def test_query_log_resources_lists_streams(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.log_streams = [_fake_stream(), _fake_stream(sid=VALID_GID2, name="stream-b")]
    mock_lts_client.list_log_stream.return_value = resp

    tools = make_discovery_tools(lts_settings)
    out = tools["lts_query_log_resources"](log_group_id=VALID_GID)

    assert out["ok"] is True
    data = out["data"]
    assert data["mode"] == "streams"
    assert data["log_group_id"] == VALID_GID
    assert data["count"] == 2
    assert data["log_streams"][0]["log_group_id"] == VALID_GID  # stamped
    assert data["log_streams"][0]["id"] == VALID_SID
    mock_lts_client.list_log_groups.assert_not_called()
    sent = mock_lts_client.list_log_stream.call_args[0][0]
    assert sent.log_group_id == VALID_GID


def test_query_log_resources_invalid_group_id(lts_settings, mock_lts_client):
    tools = make_discovery_tools(lts_settings)
    out = tools["lts_query_log_resources"](log_group_id="!!")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_lts_client.list_log_groups.assert_not_called()
    mock_lts_client.list_log_stream.assert_not_called()


def test_query_log_resources_empty_string_treated_as_none(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.log_groups = []
    mock_lts_client.list_log_groups.return_value = resp
    tools = make_discovery_tools(lts_settings)
    out = tools["lts_query_log_resources"](log_group_id="")
    assert out["ok"] is True
    assert out["data"]["mode"] == "groups"
