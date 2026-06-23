"""Integration test for CCE service registration in the unified server."""
from __future__ import annotations

import os

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.server import ALL_SERVICES, build_server


@pytest.fixture
def env_credentials(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AKID" + "X" * 16)
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SK" + "Y" * 38)
    monkeypatch.setenv("HUAWEICLOUD_REGION", "af-south-1")
    monkeypatch.setenv("HUAWEICLOUD_PROJECT_ID", "15f2d47addb14784b82eb910447250a9")


def test_cce_is_in_all_services():
    assert "cce" in ALL_SERVICES


def test_build_server_registers_cce_tools(env_credentials):
    mcp = build_server(enabled=["cce"])
    # FastMCP keeps tools in an internal manager — use the public list_tools API.
    # The simplest probe is to inspect mcp._tool_manager (private but stable).
    tm = getattr(mcp, "_tool_manager", None)
    assert tm is not None
    names = set(tm._tools.keys())
    expected = {
        "cce_query_clusters",
        "cce_query_nodes",
        "cce_query_nodepools",
        "cce_update_nodepool",
        "cce_get_job",
        "cce_confirm_destructive",
    }
    missing = expected - names
    assert not missing, f"missing CCE tools: {missing}"


def test_build_server_isolates_cce_when_only_other_services(env_credentials):
    mcp = build_server(enabled=["ecs"])
    tm = mcp._tool_manager
    names = set(tm._tools.keys())
    cce_tools = {n for n in names if n.startswith("cce_")}
    assert not cce_tools, f"CCE tools leaked when enabled=ecs only: {cce_tools}"
