"""Tests for VPC EIP tools: describe, associate, disassociate."""
from __future__ import annotations

from unittest.mock import MagicMock

from huaweicloud_mcp.services.vpc.tools.eip import make_eip_tools
from huaweicloud_mcp.services.vpc.tools.manage import make_manage_tools

EIP_ID = "eip-11111111-1111-1111-1111-111111111111"
PORT_ID = "port-22222222-2222-2222-2222-222222222222"


def _fake_eip(eip_id=EIP_ID, public_ip="1.2.3.4", status="DOWN", port_id=None,
              private_ip=None):
    e = MagicMock()
    e.id = eip_id
    e.public_ip_address = public_ip
    e.public_ipv6_address = None
    e.status = status
    e.type = "5_bgp"
    e.bandwidth_id = "bw-12345"
    e.bandwidth_name = "bw-01"
    e.bandwidth_size = 5
    e.bandwidth_share_type = "PER"
    e.port_id = port_id
    e.private_ip_address = private_ip
    e.enterprise_project_id = "0"
    e.alias = None
    e.create_time = "2024-01-01T00:00:00"
    return e


# ============================================================
# describe_eips — LIST mode
# ============================================================
def test_eip_list(settings, mock_eip_client):
    resp = MagicMock()
    resp.publicips = [_fake_eip(), _fake_eip(eip_id="eip-2", public_ip="5.6.7.8")]
    mock_eip_client.list_publicips.return_value = resp

    tools = make_eip_tools(settings)
    out = tools["vpc_describe_eips"]()

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["eips"][0]["public_ip_address"] == "1.2.3.4"
    mock_eip_client.list_publicips.assert_called_once()
    mock_eip_client.show_publicip.assert_not_called()


def test_eip_list_with_filters(settings, mock_eip_client):
    resp = MagicMock()
    resp.publicips = [_fake_eip()]
    mock_eip_client.list_publicips.return_value = resp

    tools = make_eip_tools(settings)
    out = tools["vpc_describe_eips"](public_ip_address="1.2.3.4")

    assert out["ok"] is True
    call_args = mock_eip_client.list_publicips.call_args
    req = call_args.args[0]
    assert req.public_ip_address == ["1.2.3.4"]


# ============================================================
# describe_eips — DETAIL mode
# ============================================================
def test_eip_detail(settings, mock_eip_client):
    resp = MagicMock()
    resp.publicip = _fake_eip(status="ACTIVE", port_id=PORT_ID, private_ip="10.0.0.10")
    mock_eip_client.show_publicip.return_value = resp

    tools = make_eip_tools(settings)
    out = tools["vpc_describe_eips"](eip_id=EIP_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["id"] == EIP_ID
    assert data["status"] == "ACTIVE"
    assert data["port_id"] == PORT_ID
    assert data["private_ip_address"] == "10.0.0.10"


def test_eip_detail_not_found(settings, mock_eip_client):
    resp = MagicMock()
    resp.publicip = None
    mock_eip_client.show_publicip.return_value = resp

    tools = make_eip_tools(settings)
    out = tools["vpc_describe_eips"](eip_id="nonexistent")

    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ============================================================
# associate_eip
# ============================================================
def test_associate_eip(settings, mock_eip_client):
    resp = MagicMock()
    resp.publicip = _fake_eip(status="ACTIVE", port_id=PORT_ID, private_ip="10.0.0.10")
    mock_eip_client.update_publicip.return_value = resp

    tools = make_eip_tools(settings)
    out = tools["vpc_associate_eip"](publicip_id=EIP_ID, port_id=PORT_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "ACTIVE"
    assert data["port_id"] == PORT_ID
    mock_eip_client.update_publicip.assert_called_once()


# ============================================================
# disassociate_eip — two-phase
# ============================================================
def test_disassociate_requires_confirm(settings, mock_eip_client):
    tools = make_eip_tools(settings)
    out = tools["vpc_disassociate_eip"](publicip_id=EIP_ID, confirm=False)

    assert out["ok"] is False
    assert out["error"]["code"] == "CONFIRM_REQUIRED"


def test_disassociate_pending_approval(settings, mock_eip_client):
    show_resp = MagicMock()
    show_resp.publicip = _fake_eip(status="ACTIVE", port_id=PORT_ID, private_ip="10.0.0.10")
    mock_eip_client.show_publicip.return_value = show_resp

    tools = make_eip_tools(settings)
    out = tools["vpc_disassociate_eip"](publicip_id=EIP_ID, confirm=True)

    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "pending_approval"
    assert "approval_id" in data
    assert data["action"] == "disassociate_eip"
    assert data["current"]["public_ip_address"] == "1.2.3.4"
    # update_publicip should NOT have been called yet (two-phase)
    mock_eip_client.update_publicip.assert_not_called()


def test_disassociate_confirm_executes(settings, mock_eip_client):
    show_resp = MagicMock()
    show_resp.publicip = _fake_eip(status="ACTIVE", port_id=PORT_ID)
    mock_eip_client.show_publicip.return_value = show_resp

    eip_tools = make_eip_tools(settings)
    manage_tools = make_manage_tools(settings)
    tools = {**eip_tools, **manage_tools}

    pending = tools["vpc_disassociate_eip"](publicip_id=EIP_ID, confirm=True)
    approval_id = pending["data"]["approval_id"]

    # Execute the confirmed action
    out = tools["vpc_confirm_destructive"](approval_id=approval_id)

    assert out["ok"] is True
    assert out["data"]["disassociated"] is True
    assert out["data"]["publicip_id"] == EIP_ID
    mock_eip_client.update_publicip.assert_called_once()
