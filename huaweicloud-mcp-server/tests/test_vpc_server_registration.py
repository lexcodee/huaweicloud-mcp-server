"""Integration test for VPC service registration in the unified server."""
from __future__ import annotations

import pytest

from huaweicloud_mcp.server import ALL_SERVICES, build_server


@pytest.fixture
def env_credentials(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AKID" + "X" * 16)
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SK" + "Y" * 38)
    monkeypatch.setenv("HUAWEICLOUD_REGION", "af-south-1")
    monkeypatch.setenv("HUAWEICLOUD_PROJECT_ID", "15f2d47addb14784b82eb910447250a9")


def test_vpc_is_in_all_services():
    assert "vpc" in ALL_SERVICES


def test_build_server_registers_vpc_tools(env_credentials):
    mcp = build_server(enabled=["vpc"])
    tm = getattr(mcp, "_tool_manager", None)
    assert tm is not None
    names = set(tm._tools.keys())
    expected = {
        "vpc_query_security_groups",
        "vpc_add_security_group_rule",
        "vpc_remove_security_group_rule",
        "vpc_list_sg_associated_instances",
        "vpc_audit_security_group",
        "vpc_check_port_reachability",
        "vpc_create_security_group",
        "vpc_confirm_destructive",
        "vpc_describe_vpcs",
        "vpc_describe_subnets",
        "vpc_describe_vpc_peerings",
        "vpc_describe_route_tables",
        "vpc_describe_eips",
        "vpc_associate_eip",
        "vpc_disassociate_eip",
        "vpc_add_route",
        "vpc_delete_route",
        "vpc_list_flow_logs",
        "vpc_query_flow_log_data",
    }
    missing = expected - names
    assert not missing, f"missing VPC tools: {missing}"


def test_build_server_isolates_vpc_when_only_other_services(env_credentials):
    mcp = build_server(enabled=["ecs"])
    tm = mcp._tool_manager
    names = set(tm._tools.keys())
    vpc_tools = {n for n in names if n.startswith("vpc_")}
    assert not vpc_tools, f"VPC tools leaked when enabled=ecs only: {vpc_tools}"
