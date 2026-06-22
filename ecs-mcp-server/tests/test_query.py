"""Tests for query tools."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ecs_mcp_server.tools.query import make_query_tools

VALID_UUID = "12345678-1234-1234-1234-123456789012"


def _fake_server(server_id=VALID_UUID, name="test-srv", status="ACTIVE"):
    s = MagicMock()
    s.id = server_id
    s.name = name
    s.status = status
    s.flavor = MagicMock(id="s6.large.2", name="s6.large.2", vcpus="2", ram=4096, disk=0)
    s.image = MagicMock(id="img-uuid")
    s.addresses = {
        "vpc-1": [
            MagicMock(
                addr="192.168.0.10",
                version=4,
                **{
                    "OS-EXT-IPS:type": "fixed",
                    "OS-EXT-IPS-MAC:mac_addr": "fa:16:3e:00:00:01",
                },
            )
        ]
    }
    s.created = "2024-01-01T00:00:00Z"
    s.updated = "2024-01-02T00:00:00Z"
    s.tags = ["env=prod"]
    return s


def test_list_servers_passes_filters_and_returns_compact(settings, mock_client):
    resp = MagicMock()
    resp.servers = [_fake_server()]
    resp.count = 1
    mock_client.list_servers_details.return_value = resp

    tools = make_query_tools(settings)
    out = tools["ecs_list_servers"](
        name="prod", status="ACTIVE", limit=10, offset=1, tags="env=prod"
    )

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 1
    assert data["limit"] == 10
    assert data["servers"][0]["id"] == VALID_UUID
    assert data["servers"][0]["status"] == "ACTIVE"
    assert data["servers"][0]["flavor_id"] == "s6.large.2"

    # SDK was called with our filters
    sent_req = mock_client.list_servers_details.call_args[0][0]
    assert sent_req.name == "prod"
    assert sent_req.status == "ACTIVE"
    assert sent_req.limit == 10
    assert sent_req.tags == "env=prod"


def test_list_servers_drops_null_fields_for_token_efficiency(settings, mock_client):
    """list view must omit null/empty fields and use flat IP shape.

    This is the contract callers depend on: server entries in list responses
    should NOT carry task_state/power_state/image_id/availability_zone/
    flavor_name/updated when the API returns null for those — every byte
    counts when an LLM is scanning dozens of servers.
    """
    s = _fake_server()
    # Simulate Huawei Cloud's typical list-API response: many fields null.
    s.configure_mock(
        **{
            "OS-EXT-STS:task_state": None,
            "OS-EXT-STS:power_state": None,
            "OS-EXT-AZ:availability_zone": None,
            "os_ext_sts_task_state": None,
            "os_ext_sts_power_state": None,
            "os_ext_az_availability_zone": None,
        }
    )
    resp = MagicMock()
    resp.servers = [s]
    resp.count = 1
    mock_client.list_servers_details.return_value = resp

    tools = make_query_tools(settings)
    out = tools["ecs_list_servers"]()
    assert out["ok"] is True
    entry = out["data"]["servers"][0]

    # These fields must NOT appear when null/empty.
    forbidden = {
        "task_state",
        "power_state",
        "image_id",
        "availability_zone",
        "flavor_name",
        "updated",
    }
    leaked = forbidden & set(entry.keys())
    assert not leaked, f"list view leaked verbose fields: {leaked}"

    # Required core fields must be present.
    for required in ("id", "name", "status", "flavor_id", "addresses", "created"):
        assert required in entry, f"list view missing core field {required!r}"

    # Addresses must be the flat IP-string shape, not the rich NIC dict.
    addrs = entry["addresses"]
    assert addrs == {"vpc-1": ["192.168.0.10"]}, addrs


def test_list_servers_invalid_status_rejected(settings, mock_client):
    tools = make_query_tools(settings)
    out = tools["ecs_list_servers"](status="WAT")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_client.list_servers_details.assert_not_called()


def test_get_server_full_invalid_uuid(settings, mock_client):
    tools = make_query_tools(settings)
    out = tools["ecs_get_server"](server_id="not-a-uuid")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"


def test_get_server_full_not_found(settings, mock_client):
    resp = MagicMock(); resp.servers = []
    mock_client.list_servers_details.return_value = resp
    tools = make_query_tools(settings)
    out = tools["ecs_get_server"](server_id=VALID_UUID)
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


def test_get_server_invalid_detail_level(settings, mock_client):
    tools = make_query_tools(settings)
    out = tools["ecs_get_server"](server_id=VALID_UUID, detail_level="verbose")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_client.list_servers_details.assert_not_called()
    mock_client.show_server.assert_not_called()


def test_get_server_full_returns_rich_fields(settings, mock_client):
    """detail_level='full' must include the verbose fields the summary drops."""
    s = _fake_server()
    sg = MagicMock(id="sg-1")
    sg.name = "default"
    s.configure_mock(
        **{
            "OS-EXT-STS:power_state": 1,
            "OS-EXT-AZ:availability_zone": "af-south-1a",
            "key_name": "my-key",
            "host_id": "host-abc",
            "enterprise_project_id": "0",
            "description": "prod web",
            "metadata": {"role": "web"},
            "security_groups": [sg],
            "os_extended_volumes_volumes_attached": [
                MagicMock(
                    id="vol-1", device="/dev/vda", boot_index=0,
                    delete_on_termination=True,
                )
            ],
        }
    )
    resp = MagicMock()
    resp.servers = [s]
    mock_client.list_servers_details.return_value = resp

    tools = make_query_tools(settings)
    out = tools["ecs_get_server"](server_id=VALID_UUID)  # default detail_level=full
    assert out["ok"] is True
    data = out["data"]

    # Detail-only fields must be present.
    assert data["image_id"] == "img-uuid"
    assert data["availability_zone"] == "af-south-1a"
    assert data["power_state"] == 1
    assert data["updated"] == "2024-01-02T00:00:00Z"
    assert data["key_name"] == "my-key"
    assert data["flavor"]["vcpus"] == "2"
    assert data["flavor"]["ram"] == 4096
    assert data["security_groups"] == [{"id": "sg-1", "name": "default"}]
    assert data["volumes_attached"][0]["id"] == "vol-1"
    assert data["metadata"] == {"role": "web"}

    # Detail addresses must include rich NIC info (type/mac) — not just IPs.
    nic = data["addresses"]["vpc-1"][0]
    assert nic["addr"] == "192.168.0.10"
    assert nic["type"] == "fixed"
    assert nic["mac"] == "fa:16:3e:00:00:01"


def test_get_server_status_compact(settings, mock_client):
    show_resp = MagicMock()
    show_resp.server = _fake_server()
    mock_client.show_server.return_value = show_resp

    tools = make_query_tools(settings)
    out = tools["ecs_get_server"](server_id=VALID_UUID, detail_level="status")
    assert out["ok"] is True
    data = out["data"]
    assert set(data.keys()) >= {"server_id", "name", "status"}
    # status path must use the cheap ShowServer call, not list_servers_details
    mock_client.show_server.assert_called_once()
    mock_client.list_servers_details.assert_not_called()


def test_list_flavors_applies_client_side_limit(settings, mock_client):
    resp = MagicMock()
    fs = []
    for i in range(5):
        f = MagicMock(); f.id = f"flv-{i}"; f.name = f"flv-{i}"
        f.vcpus = "2"; f.ram = 4096; f.disk = 0; f.os_extra_specs = None
        fs.append(f)
    resp.flavors = fs
    mock_client.list_flavors.return_value = resp

    tools = make_query_tools(settings)
    out = tools["ecs_list_flavors"](limit=3)
    assert out["ok"] is True
    assert out["data"]["count"] == 3
    assert len(out["data"]["flavors"]) == 3
