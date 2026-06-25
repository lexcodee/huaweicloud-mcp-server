"""Tests for VPC network query tools: vpcs, subnets, peerings, flow logs."""
from __future__ import annotations

from unittest.mock import MagicMock

from huaweicloud_mcp.services.vpc.tools.network import make_network_tools

VPC_ID = "vpc-11111111-1111-1111-1111-111111111111"
SUBNET_ID = "subnet-22222222-2222-2222-2222-222222222222"
PEERING_ID = "peering-33333333-3333-3333-3333-333333333333"
FLOW_LOG_ID = "fl-44444444-4444-4444-4444-444444444444"


def _fake_vpc(vpc_id=VPC_ID, name="vpc-01", cidr="10.0.0.0/16", status="OK"):
    v = MagicMock()
    v.id = vpc_id
    v.name = name
    v.cidr = cidr
    v.status = status
    v.enterprise_project_id = "0"
    v.description = None
    v.created_at = "2024-01-01T00:00:00"
    v.updated_at = "2024-01-01T00:00:00"
    v.routes = []
    return v


def _fake_subnet(subnet_id=SUBNET_ID, name="subnet-01", cidr="10.0.0.0/24",
                 vpc_id=VPC_ID, available=253):
    s = MagicMock()
    s.id = subnet_id
    s.name = name
    s.cidr = cidr
    s.gateway_ip = "10.0.0.1"
    s.vpc_id = vpc_id
    s.availability_zone = "af-south-1a"
    s.status = "ACTIVE"
    s.available_ip_address_count = available
    s.ipv6_enable = False
    s.cidr_v6 = None
    s.dhcp_enable = True
    s.primary_dns = "100.125.1.250"
    s.secondary_dns = "100.125.21.250"
    s.description = None
    s.created_at = "2024-01-01T00:00:00"
    return s


def _fake_peering(peering_id=PEERING_ID, name="peering-01", status="ACTIVE"):
    p = MagicMock()
    p.id = peering_id
    p.name = name
    p.status = status
    p.description = None
    p.request_vpc_info = MagicMock(vpc_id=VPC_ID, tenant_id="tenant-aaa")
    p.accept_vpc_info = MagicMock(vpc_id="vpc-55555555", tenant_id="tenant-aaa")
    p.created_at = "2024-01-01T00:00:00"
    p.updated_at = "2024-01-01T00:00:00"
    return p


def _fake_flow_log(fl_id=FLOW_LOG_ID, name="flowlog-01"):
    f = MagicMock()
    f.id = fl_id
    f.name = name
    f.resource_type = "vpc"
    f.resource_id = VPC_ID
    f.traffic_type = "all"
    f.log_group_id = "lg-12345"
    f.log_topic_id = "lt-67890"
    f.log_store_type = "lts"
    f.status = "ACTIVE"
    f.admin_state = True
    f.description = None
    f.created_at = "2024-01-01T00:00:00"
    f.updated_at = "2024-01-01T00:00:00"
    return f


# ============================================================
# describe_vpcs
# ============================================================
def test_vpc_list(settings, mock_vpc_client):
    resp = MagicMock()
    resp.vpcs = [_fake_vpc(name="vpc-01"), _fake_vpc(vpc_id="vpc-2", name="vpc-02")]
    mock_vpc_client.list_vpcs.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_vpcs"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["vpcs"][0]["name"] == "vpc-01"
    assert data["vpcs"][0]["cidr"] == "10.0.0.0/16"
    mock_vpc_client.list_vpcs.assert_called_once()
    mock_vpc_client.show_vpc.assert_not_called()


def test_vpc_detail(settings, mock_vpc_client):
    resp = MagicMock()
    resp.vpc = _fake_vpc()
    mock_vpc_client.show_vpc.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_vpcs"](vpc_id=VPC_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["id"] == VPC_ID
    assert data["name"] == "vpc-01"
    mock_vpc_client.show_vpc.assert_called_once()
    mock_vpc_client.list_vpcs.assert_not_called()


def test_vpc_detail_not_found(settings, mock_vpc_client):
    resp = MagicMock()
    resp.vpc = None
    mock_vpc_client.show_vpc.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_vpcs"](vpc_id="nonexistent")

    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ============================================================
# describe_subnets
# ============================================================
def test_subnet_list(settings, mock_vpc_client):
    resp = MagicMock()
    resp.subnets = [_fake_subnet(name="subnet-01"), _fake_subnet(subnet_id="sub-2", name="subnet-02")]
    mock_vpc_client.list_subnets.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_subnets"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["subnets"][0]["available_ip_address_count"] == 253


def test_subnet_detail(settings, mock_vpc_client):
    resp = MagicMock()
    resp.subnet = _fake_subnet()
    mock_vpc_client.show_subnet.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_subnets"](subnet_id=SUBNET_ID)

    assert out["ok"] is True
    assert out["data"]["id"] == SUBNET_ID
    assert out["data"]["availability_zone"] == "af-south-1a"


def test_subnet_list_by_vpc(settings, mock_vpc_client):
    resp = MagicMock()
    resp.subnets = [_fake_subnet()]
    mock_vpc_client.list_subnets.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_subnets"](vpc_id=VPC_ID)

    assert out["ok"] is True
    assert out["data"]["count"] == 1
    # Verify vpc_id was passed to the request
    call_args = mock_vpc_client.list_subnets.call_args
    req = call_args.args[0]
    assert req.vpc_id == VPC_ID


# ============================================================
# describe_vpc_peerings
# ============================================================
def test_peering_list(settings, mock_vpc_client):
    resp = MagicMock()
    resp.peerings = [_fake_peering(), _fake_peering(peering_id="p-2", status="PENDING_ACCEPTANCE")]
    mock_vpc_client.list_vpc_peerings.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_vpc_peerings"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["peerings"][0]["status"] == "ACTIVE"
    assert data["peerings"][0]["request_vpc_id"] == VPC_ID


def test_peering_detail(settings, mock_vpc_client):
    resp = MagicMock()
    resp.peering = _fake_peering()
    mock_vpc_client.show_vpc_peering.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_describe_vpc_peerings"](peering_id=PEERING_ID)

    assert out["ok"] is True
    assert out["data"]["id"] == PEERING_ID
    assert out["data"]["accept_vpc_id"] == "vpc-55555555"


# ============================================================
# list_flow_logs
# ============================================================
def test_flow_log_list(settings, mock_vpc_client):
    resp = MagicMock()
    resp.flow_logs = [_fake_flow_log()]
    mock_vpc_client.list_flow_logs.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_list_flow_logs"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 1
    assert data["flow_logs"][0]["log_group_id"] == "lg-12345"
    assert data["flow_logs"][0]["log_topic_id"] == "lt-67890"


def test_flow_log_detail(settings, mock_vpc_client):
    resp = MagicMock()
    resp.flow_log = _fake_flow_log()
    mock_vpc_client.show_flow_log.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_list_flow_logs"](flow_log_id=FLOW_LOG_ID)

    assert out["ok"] is True
    assert out["data"]["id"] == FLOW_LOG_ID
    assert out["data"]["resource_type"] == "vpc"


def test_flow_log_detail_not_found(settings, mock_vpc_client):
    resp = MagicMock()
    resp.flow_log = None
    mock_vpc_client.show_flow_log.return_value = resp

    tools = make_network_tools(settings)
    out = tools["vpc_list_flow_logs"](flow_log_id="nonexistent")

    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"
