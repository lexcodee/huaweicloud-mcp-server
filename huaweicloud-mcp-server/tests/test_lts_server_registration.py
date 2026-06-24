"""Integration test for LTS service registration in the unified server."""
from __future__ import annotations

import pytest

from huaweicloud_mcp.server import ALL_SERVICES, build_server


@pytest.fixture
def env_credentials(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AKID" + "X" * 16)
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SK" + "Y" * 38)
    monkeypatch.setenv("HUAWEICLOUD_REGION", "af-south-1")
    monkeypatch.setenv("HUAWEICLOUD_PROJECT_ID", "15f2d47addb14784b82eb910447250a9")


def test_lts_is_in_all_services():
    assert "lts" in ALL_SERVICES


def test_build_server_registers_lts_tools(env_credentials):
    mcp = build_server(enabled=["lts"])
    tm = getattr(mcp, "_tool_manager", None)
    assert tm is not None
    names = set(tm._tools.keys())
    expected = {
        "lts_query_log_resources",
        "lts_search_logs",
        "lts_get_log_context",
        "lts_query_histogram",
        "lts_query_alarm_rules",
        "lts_list_alarm_history",
    }
    missing = expected - names
    assert not missing, f"missing LTS tools: {missing}"
    # No accidental extras under the lts_ namespace
    extras = {n for n in names if n.startswith("lts_")} - expected
    assert not extras, f"unexpected LTS tools: {extras}"


def test_build_server_isolates_lts_when_only_other_services(env_credentials):
    mcp = build_server(enabled=["ecs"])
    tm = mcp._tool_manager
    names = set(tm._tools.keys())
    lts_tools = {n for n in names if n.startswith("lts_")}
    assert not lts_tools, f"LTS tools leaked when enabled=ecs only: {lts_tools}"


def test_build_server_lts_alongside_others(env_credentials):
    mcp = build_server(enabled=["cce", "lts"])
    tm = mcp._tool_manager
    names = set(tm._tools.keys())
    assert any(n.startswith("lts_") for n in names)
    assert any(n.startswith("cce_") for n in names)
