"""Tests for VPC route table tools: describe, add_route, delete_route."""
from __future__ import annotations

from unittest.mock import MagicMock

from huaweicloud_mcp.services.vpc.tools.route import make_route_tools
from huaweicloud_mcp.services.vpc.tools.manage import make_manage_tools

RT_ID = "rt-11111111-1111-1111-1111-111111111111"
VPC_ID = "vpc-22222222-2222-2222-2222-222222222222"


def _fake_route(destination="10.1.0.0/16", nexthop="peering-12345", type="peering",
                description=None, route_id="route-aaa"):
    r = MagicMock()
    r.id = route_id
    r.destination = destination
    r.nexthop = nexthop
    r.type = type
    r.description = description
    return r


def _fake_route_table(rt_id=RT_ID, name="rt-01", vpc_id=VPC_ID, routes=None,
                      default=False):
    rt = MagicMock()
    rt.id = rt_id
    rt.name = name
    rt.vpc_id = vpc_id
    rt.default = default
    rt.subnets = ["subnet-11111111"]
    rt.description = None
    rt.created_at = "2024-01-01T00:00:00"
    rt.routes = routes or []
    return rt


# ============================================================
# describe_route_tables — LIST mode
# ============================================================
def test_rt_list(settings, mock_vpc_client):
    resp = MagicMock()
    resp.routetables = [_fake_route_table(), _fake_route_table(rt_id="rt-2", name="rt-02")]
    mock_vpc_client.list_route_tables.return_value = resp

    tools = make_route_tools(settings)
    out = tools["vpc_describe_route_tables"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["route_tables"][0]["name"] == "rt-01"
    # LIST mode should not include routes
    assert "routes" not in data["route_tables"][0]
    mock_vpc_client.list_route_tables.assert_called_once()
    mock_vpc_client.show_route_table.assert_not_called()


def test_rt_list_by_vpc(settings, mock_vpc_client):
    resp = MagicMock()
    resp.routetables = [_fake_route_table()]
    mock_vpc_client.list_route_tables.return_value = resp

    tools = make_route_tools(settings)
    out = tools["vpc_describe_route_tables"](vpc_id=VPC_ID)

    assert out["ok"] is True
    call_args = mock_vpc_client.list_route_tables.call_args
    req = call_args.args[0]
    assert req.vpc_id == VPC_ID


# ============================================================
# describe_route_tables — DETAIL mode
# ============================================================
def test_rt_detail(settings, mock_vpc_client):
    routes = [_fake_route(), _fake_route(destination="10.2.0.0/16", nexthop="vpn-67890", type="vpn")]
    resp = MagicMock()
    resp.routetable = _fake_route_table(routes=routes)
    mock_vpc_client.show_route_table.return_value = resp

    tools = make_route_tools(settings)
    out = tools["vpc_describe_route_tables"](routetable_id=RT_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["id"] == RT_ID
    assert len(data["routes"]) == 2
    assert data["routes"][0]["destination"] == "10.1.0.0/16"
    assert data["routes"][0]["type"] == "peering"


def test_rt_detail_not_found(settings, mock_vpc_client):
    resp = MagicMock()
    resp.routetable = None
    mock_vpc_client.show_route_table.return_value = resp

    tools = make_route_tools(settings)
    out = tools["vpc_describe_route_tables"](routetable_id="nonexistent")

    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ============================================================
# add_route
# ============================================================
def test_add_route(settings, mock_vpc_client):
    routes = [_fake_route()]
    resp = MagicMock()
    resp.routetable = _fake_route_table(routes=routes)
    mock_vpc_client.update_route_table.return_value = resp

    tools = make_route_tools(settings)
    out = tools["vpc_add_route"](
        routetable_id=RT_ID,
        destination="10.1.0.0/16",
        nexthop="peering-12345",
        type="peering",
        description="route to peered VPC",
    )

    assert out["ok"] is True
    data = out["data"]
    assert data["id"] == RT_ID
    assert len(data["routes"]) == 1
    mock_vpc_client.update_route_table.assert_called_once()


# ============================================================
# delete_route — two-phase
# ============================================================
def test_delete_route_pending_approval(settings, mock_vpc_client):
    tools = make_route_tools(settings)
    out = tools["vpc_delete_route"](
        routetable_id=RT_ID,
        destination="10.1.0.0/16",
        nexthop="peering-12345",
        type="peering",
    )

    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "pending_approval"
    assert "approval_id" in data
    assert data["action"] == "delete_route"
    assert data["destination"] == "10.1.0.0/16"
    # update_route_table should NOT have been called yet
    mock_vpc_client.update_route_table.assert_not_called()


def test_delete_route_confirm_executes(settings, mock_vpc_client):
    route_tools = make_route_tools(settings)
    manage_tools = make_manage_tools(settings)
    tools = {**route_tools, **manage_tools}

    pending = tools["vpc_delete_route"](
        routetable_id=RT_ID,
        destination="10.1.0.0/16",
        nexthop="peering-12345",
        type="peering",
    )
    approval_id = pending["data"]["approval_id"]

    out = tools["vpc_confirm_destructive"](approval_id=approval_id)

    assert out["ok"] is True
    assert out["data"]["deleted"] is True
    assert out["data"]["destination"] == "10.1.0.0/16"
    mock_vpc_client.update_route_table.assert_called_once()
