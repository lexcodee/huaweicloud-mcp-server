"""Tests for VPC security-group query and audit tools."""
from __future__ import annotations

from unittest.mock import MagicMock

from huaweicloud_mcp.services.vpc.tools.query import make_query_tools

SG_ID = "12345678-1234-1234-1234-123456789012"
RULE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _fake_rule(
    rule_id=RULE_ID, direction="ingress", protocol="tcp",
    port_min=22, port_max=22, remote_ip_prefix="0.0.0.0/0",
    remote_group_id=None, description=None,
):
    r = MagicMock()
    r.id = rule_id
    r.direction = direction
    r.protocol = protocol
    r.port_range_min = port_min
    r.port_range_max = port_max
    r.remote_ip_prefix = remote_ip_prefix
    r.remote_group_id = remote_group_id
    r.remote_address_group_id = None
    r.description = description
    r.ethertype = "IPv4"
    r.security_group_id = SG_ID
    return r


def _fake_sg(
    sg_id=SG_ID, name="default-sg", vpc_id=None,
    rules=None, description=None,
):
    sg = MagicMock()
    sg.id = sg_id
    sg.name = name
    sg.vpc_id = vpc_id
    sg.enterprise_project_id = None
    sg.description = description
    sg.security_group_rules = rules or []
    return sg


# ============================================================
# query_security_groups — LIST mode
# ============================================================
def test_query_list_basic(settings, mock_vpc_client):
    resp = MagicMock()
    resp.security_groups = [
        _fake_sg(name="web-sg", rules=[_fake_rule()]),
        _fake_sg(sg_id="22222222-2222-2222-2222-222222222222", name="db-sg"),
    ]
    mock_vpc_client.list_security_groups.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_query_security_groups"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["security_groups"][0]["name"] == "web-sg"
    assert len(data["security_groups"][0]["security_group_rules"]) == 1
    # list_security_groups was called, not show_security_group
    mock_vpc_client.list_security_groups.assert_called_once()
    mock_vpc_client.show_security_group.assert_not_called()


def test_query_list_name_filter(settings, mock_vpc_client):
    resp = MagicMock()
    resp.security_groups = [
        _fake_sg(name="web-sg"),
        _fake_sg(sg_id="22222222-2222-2222-2222-222222222222", name="db-sg"),
    ]
    mock_vpc_client.list_security_groups.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_query_security_groups"](name="db-sg")

    assert out["ok"] is True
    assert out["data"]["count"] == 1
    assert out["data"]["security_groups"][0]["name"] == "db-sg"


def test_query_list_passes_vpc_filter(settings, mock_vpc_client):
    resp = MagicMock()
    resp.security_groups = []
    mock_vpc_client.list_security_groups.return_value = resp

    tools = make_query_tools(settings)
    tools["vpc_query_security_groups"](vpc_id="vpc-123")

    sent_req = mock_vpc_client.list_security_groups.call_args[0][0]
    assert sent_req.vpc_id == "vpc-123"


# ============================================================
# query_security_groups — DETAIL mode
# ============================================================
def test_query_detail(settings, mock_vpc_client):
    rules = [_fake_rule(port_min=80, port_max=80), _fake_rule(direction="egress")]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules, description="web tier")
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_query_security_groups"](security_group_id=SG_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["id"] == SG_ID
    assert data["description"] == "web tier"
    assert len(data["security_group_rules"]) == 2
    # show_security_group was called, not list_security_groups
    mock_vpc_client.show_security_group.assert_called_once()
    mock_vpc_client.list_security_groups.assert_not_called()


def test_query_detail_not_found(settings, mock_vpc_client):
    resp = MagicMock()
    resp.security_group = None
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_query_security_groups"](security_group_id=SG_ID)
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ============================================================
# list_sg_associated_instances
# ============================================================
def test_list_sg_associated_instances(settings, mock_vpc_client):
    """Should return only servers whose SG set includes the target id."""
    s1 = MagicMock()
    s1.id = "srv-1"
    s1.name = "web-1"
    s1.status = "ACTIVE"
    s1.security_groups = [MagicMock(id=SG_ID)]

    s2 = MagicMock()
    s2.id = "srv-2"
    s2.name = "db-1"
    s2.status = "ACTIVE"
    s2.security_groups = [MagicMock(id="other-sg-id")]

    resp = MagicMock()
    resp.servers = [s1, s2]
    resp.count = 2
    mock_vpc_client.list_servers_details.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_list_sg_associated_instances"](security_group_id=SG_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 1
    assert data["instances"][0]["id"] == "srv-1"


def test_list_sg_associated_instances_no_matches(settings, mock_vpc_client):
    resp = MagicMock()
    resp.servers = []
    resp.count = 0
    mock_vpc_client.list_servers_details.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_list_sg_associated_instances"](security_group_id=SG_ID)
    assert out["ok"] is True
    assert out["data"]["count"] == 0


# ============================================================
# check_port_reachability
# ============================================================
def test_check_port_reachability_allowed(settings, mock_vpc_client):
    rules = [
        _fake_rule(direction="ingress", protocol="tcp", port_min=80, port_max=80,
                   remote_ip_prefix="0.0.0.0/0"),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules)
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_check_port_reachability"](
        security_group_id=SG_ID, protocol="tcp", port=80,
    )
    assert out["ok"] is True
    assert out["data"]["allowed"] is True
    assert len(out["data"]["matched_rules"]) == 1


def test_check_port_reachability_blocked(settings, mock_vpc_client):
    rules = [
        _fake_rule(direction="ingress", protocol="tcp", port_min=22, port_max=22,
                   remote_ip_prefix="0.0.0.0/0"),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules)
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_check_port_reachability"](
        security_group_id=SG_ID, protocol="tcp", port=3306,
    )
    assert out["ok"] is True
    assert out["data"]["allowed"] is False
    assert out["data"]["matched_rules"] == []


def test_check_port_reachability_direction_filter(settings, mock_vpc_client):
    """Egress rule should not match an ingress check."""
    rules = [
        _fake_rule(direction="egress", protocol="tcp", port_min=443, port_max=443),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules)
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_check_port_reachability"](
        security_group_id=SG_ID, protocol="tcp", port=443, direction="ingress",
    )
    assert out["data"]["allowed"] is False


def test_check_port_reachability_source_ip_filter(settings, mock_vpc_client):
    """Should match when source_ip falls within the rule's CIDR."""
    rules = [
        _fake_rule(direction="ingress", protocol="tcp", port_min=22, port_max=22,
                   remote_ip_prefix="10.0.0.0/24"),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules)
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    # IP in range → allowed
    out = tools["vpc_check_port_reachability"](
        security_group_id=SG_ID, protocol="tcp", port=22, source_ip="10.0.0.5",
    )
    assert out["data"]["allowed"] is True

    # IP out of range → blocked
    out = tools["vpc_check_port_reachability"](
        security_group_id=SG_ID, protocol="tcp", port=22, source_ip="192.168.1.5",
    )
    assert out["data"]["allowed"] is False


# ============================================================
# audit_security_group
# ============================================================
def test_audit_high_risk_ssh_open(settings, mock_vpc_client):
    rules = [
        _fake_rule(direction="ingress", protocol="tcp", port_min=22, port_max=22,
                   remote_ip_prefix="0.0.0.0/0"),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules, name="risky-sg")
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_audit_security_group"](security_group_id=SG_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["risk_level"] == "high"
    assert len(data["findings"]) == 1
    assert data["findings"][0]["service"] == "SSH"
    assert data["findings"][0]["port"] == 22


def test_audit_no_risk(settings, mock_vpc_client):
    rules = [
        _fake_rule(direction="ingress", protocol="tcp", port_min=80, port_max=80,
                   remote_ip_prefix="10.0.0.0/24"),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules)
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_audit_security_group"](security_group_id=SG_ID)

    assert out["ok"] is True
    assert out["data"]["risk_level"] == "none"
    assert out["data"]["findings"] == []


def test_audit_multiple_sensitive_ports(settings, mock_vpc_client):
    rules = [
        _fake_rule(direction="ingress", protocol="tcp", port_min=3306, port_max=3306,
                   remote_ip_prefix="0.0.0.0/0"),
        _fake_rule(direction="ingress", protocol="tcp", port_min=6379, port_max=6379,
                   remote_ip_prefix="0.0.0.0/0"),
        _fake_rule(direction="ingress", protocol="tcp", port_min=80, port_max=80,
                   remote_ip_prefix="0.0.0.0/0"),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules)
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_audit_security_group"](security_group_id=SG_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["risk_level"] == "high"
    # Port 80 is not in SENSITIVE_PORTS, so only 2 findings.
    assert len(data["findings"]) == 2
    services = {f["service"] for f in data["findings"]}
    assert "MySQL" in services
    assert "Redis" in services


def test_audit_egress_not_flagged(settings, mock_vpc_client):
    """Egress rules to 0.0.0.0/0 are normal (allow-all egress) — not high risk."""
    rules = [
        _fake_rule(direction="egress", protocol="tcp", port_min=22, port_max=22,
                   remote_ip_prefix="0.0.0.0/0"),
    ]
    resp = MagicMock()
    resp.security_group = _fake_sg(rules=rules)
    mock_vpc_client.show_security_group.return_value = resp

    tools = make_query_tools(settings)
    out = tools["vpc_audit_security_group"](security_group_id=SG_ID)
    assert out["data"]["risk_level"] == "none"
