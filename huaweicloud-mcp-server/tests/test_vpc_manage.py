"""Tests for VPC security-group manage tools (create/clone, add/remove rules)."""
from __future__ import annotations

from unittest.mock import MagicMock

from huaweicloud_mcp.services.vpc.tools.manage import make_manage_tools

SG_ID = "12345678-1234-1234-1234-123456789012"
NEW_SG_ID = "99999999-9999-9999-9999-999999999999"
RULE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _fake_rule(
    rule_id=RULE_ID, direction="ingress", protocol="tcp",
    port_min=80, port_max=80, remote_ip_prefix="0.0.0.0/0",
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


def _fake_sg(sg_id=SG_ID, name="test-sg", rules=None, vpc_id=None):
    sg = MagicMock()
    sg.id = sg_id
    sg.name = name
    sg.vpc_id = vpc_id
    sg.enterprise_project_id = None
    sg.description = None
    sg.security_group_rules = rules or []
    return sg


# ============================================================
# create_security_group — PLAIN CREATE mode
# ============================================================
def test_create_plain(settings, mock_vpc_client):
    created = _fake_sg(sg_id=NEW_SG_ID, name="new-sg", vpc_id="vpc-1")
    create_resp = MagicMock()
    create_resp.security_group = created
    final_resp = MagicMock()
    final_resp.security_group = created
    mock_vpc_client.create_security_group.return_value = create_resp
    mock_vpc_client.show_security_group.return_value = final_resp

    tools = make_manage_tools(settings)
    out = tools["vpc_create_security_group"](name="new-sg", vpc_id="vpc-1")

    assert out["ok"] is True
    assert out["data"]["id"] == NEW_SG_ID
    assert out["data"]["name"] == "new-sg"
    # No cloned_rules_count in plain mode.
    assert "cloned_rules_count" not in out["data"]

    # Verify the SDK was called with the right option.
    sent_req = mock_vpc_client.create_security_group.call_args[0][0]
    assert sent_req.body.security_group.name == "new-sg"
    assert sent_req.body.security_group.vpc_id == "vpc-1"
    # No rule creation in plain mode.
    mock_vpc_client.create_security_group_rule.assert_not_called()


def test_create_plain_minimal(settings, mock_vpc_client):
    create_resp = MagicMock()
    create_resp.security_group = _fake_sg(sg_id=NEW_SG_ID, name="simple")
    final_resp = MagicMock()
    final_resp.security_group = _fake_sg(sg_id=NEW_SG_ID, name="simple")
    mock_vpc_client.create_security_group.return_value = create_resp
    mock_vpc_client.show_security_group.return_value = final_resp

    tools = make_manage_tools(settings)
    out = tools["vpc_create_security_group"](name="simple")
    assert out["ok"] is True


# ============================================================
# create_security_group — CLONE mode
# ============================================================
def test_create_clone(settings, mock_vpc_client):
    src_rules = [
        _fake_rule(direction="ingress", protocol="tcp", port_min=80, port_max=80),
        _fake_rule(direction="egress", protocol="tcp", port_min=443, port_max=443),
    ]
    src_resp = MagicMock()
    src_resp.security_group = _fake_sg(rules=src_rules, vpc_id="vpc-1")

    created_resp = MagicMock()
    created_resp.security_group = _fake_sg(sg_id=NEW_SG_ID, name="cloned-sg", vpc_id="vpc-1")

    final_resp = MagicMock()
    final_resp.security_group = _fake_sg(
        sg_id=NEW_SG_ID, name="cloned-sg",
        rules=src_rules, vpc_id="vpc-1",
    )

    # show_security_group called: 1st for source, 2nd for final re-fetch.
    mock_vpc_client.show_security_group.side_effect = [src_resp, final_resp]
    mock_vpc_client.create_security_group.return_value = created_resp
    mock_vpc_client.create_security_group_rule.return_value = MagicMock(
        security_group_rule=_fake_rule(),
    )

    tools = make_manage_tools(settings)
    out = tools["vpc_create_security_group"](
        name="cloned-sg", source_security_group_id=SG_ID,
    )

    assert out["ok"] is True
    data = out["data"]
    assert data["id"] == NEW_SG_ID
    assert data["cloned_rules_count"] == 2
    # Should have called create_security_group_rule twice.
    assert mock_vpc_client.create_security_group_rule.call_count == 2


def test_create_clone_inherits_source_vpc(settings, mock_vpc_client):
    """When vpc_id is omitted in clone mode, should inherit source's VPC."""
    src_resp = MagicMock()
    src_resp.security_group = _fake_sg(rules=[_fake_rule()], vpc_id="inherited-vpc")

    created_resp = MagicMock()
    created_resp.security_group = _fake_sg(sg_id=NEW_SG_ID, name="cloned", vpc_id="inherited-vpc")

    final_resp = MagicMock()
    final_resp.security_group = _fake_sg(sg_id=NEW_SG_ID, name="cloned", vpc_id="inherited-vpc")

    mock_vpc_client.show_security_group.side_effect = [src_resp, final_resp]
    mock_vpc_client.create_security_group.return_value = created_resp
    mock_vpc_client.create_security_group_rule.return_value = MagicMock(
        security_group_rule=_fake_rule(),
    )

    tools = make_manage_tools(settings)
    tools["vpc_create_security_group"](
        name="cloned", source_security_group_id=SG_ID,
    )

    # The create call should use the inherited VPC.
    sent_req = mock_vpc_client.create_security_group.call_args[0][0]
    assert sent_req.body.security_group.vpc_id == "inherited-vpc"


def test_create_clone_source_not_found(settings, mock_vpc_client):
    src_resp = MagicMock()
    src_resp.security_group = None
    mock_vpc_client.show_security_group.return_value = src_resp

    tools = make_manage_tools(settings)
    out = tools["vpc_create_security_group"](
        name="cloned", source_security_group_id=SG_ID,
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ============================================================
# add_security_group_rule
# ============================================================
def test_add_security_group_rule(settings, mock_vpc_client):
    created_rule = _fake_rule(rule_id="new-rule-id", port_min=443, port_max=443)
    resp = MagicMock()
    resp.security_group_rule = created_rule
    mock_vpc_client.create_security_group_rule.return_value = resp

    tools = make_manage_tools(settings)
    out = tools["vpc_add_security_group_rule"](
        security_group_id=SG_ID,
        direction="ingress",
        protocol="tcp",
        port_range_min=443,
        port_range_max=443,
        remote_ip_prefix="10.0.0.0/24",
        description="HTTPS from internal",
    )

    assert out["ok"] is True
    assert out["data"]["id"] == "new-rule-id"
    assert out["data"]["port_range_min"] == 443

    sent_req = mock_vpc_client.create_security_group_rule.call_args[0][0]
    opt = sent_req.body.security_group_rule
    assert opt.security_group_id == SG_ID
    assert opt.direction == "ingress"
    assert opt.protocol == "tcp"
    assert opt.port_range_min == 443
    assert opt.remote_ip_prefix == "10.0.0.0/24"


def test_add_rule_defaults_to_open_all(settings, mock_vpc_client):
    """When no source is specified, should default to 0.0.0.0/0."""
    resp = MagicMock()
    resp.security_group_rule = _fake_rule()
    mock_vpc_client.create_security_group_rule.return_value = resp

    tools = make_manage_tools(settings)
    tools["vpc_add_security_group_rule"](
        security_group_id=SG_ID,
        direction="ingress",
        protocol="tcp",
        port_range_min=80,
        port_range_max=80,
    )

    sent_req = mock_vpc_client.create_security_group_rule.call_args[0][0]
    assert sent_req.body.security_group_rule.remote_ip_prefix == "0.0.0.0/0"


def test_add_rule_conflicting_sources(settings, mock_vpc_client):
    tools = make_manage_tools(settings)
    out = tools["vpc_add_security_group_rule"](
        security_group_id=SG_ID,
        direction="ingress",
        protocol="tcp",
        port_range_min=80,
        port_range_max=80,
        remote_ip_prefix="0.0.0.0/0",
        remote_group_id="some-sg-id",
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "CONFLICTING_PARAMS"
    mock_vpc_client.create_security_group_rule.assert_not_called()


def test_add_rule_protocol_any(settings, mock_vpc_client):
    """Protocol 'any' should be sent as None to the SDK."""
    resp = MagicMock()
    resp.security_group_rule = _fake_rule()
    mock_vpc_client.create_security_group_rule.return_value = resp

    tools = make_manage_tools(settings)
    tools["vpc_add_security_group_rule"](
        security_group_id=SG_ID,
        direction="egress",
        protocol="any",
    )

    sent_req = mock_vpc_client.create_security_group_rule.call_args[0][0]
    assert sent_req.body.security_group_rule.protocol is None


# ============================================================
# remove_security_group_rule (two-phase)
# ============================================================
def test_remove_rule_returns_pending_approval(settings, mock_vpc_client):
    tools = make_manage_tools(settings)
    out = tools["vpc_remove_security_group_rule"](security_group_rule_id=RULE_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "pending_approval"
    assert "approval_id" in data
    assert data["action"] == "remove_rule"
    assert data["security_group_rule_id"] == RULE_ID
    # Must NOT have actually called delete yet.
    mock_vpc_client.delete_security_group_rule.assert_not_called()


def test_remove_rule_confirm_executes(settings, mock_vpc_client):
    tools = make_manage_tools(settings)

    # Phase 1: request deletion.
    out1 = tools["vpc_remove_security_group_rule"](security_group_rule_id=RULE_ID)
    approval_id = out1["data"]["approval_id"]

    # Phase 2: confirm.
    out2 = tools["vpc_confirm_destructive"](approval_id=approval_id)
    assert out2["ok"] is True
    assert out2["data"]["deleted"] is True
    assert out2["data"]["rule_id"] == RULE_ID

    # SDK delete was called with the right id.
    sent_req = mock_vpc_client.delete_security_group_rule.call_args[0][0]
    assert sent_req.security_group_rule_id == RULE_ID


def test_confirm_destructive_invalid_id(settings, mock_vpc_client):
    tools = make_manage_tools(settings)
    out = tools["vpc_confirm_destructive"](approval_id="nonexistent")
    assert out["ok"] is False
    assert out["error"]["code"] == "APPROVAL_NOT_FOUND"
