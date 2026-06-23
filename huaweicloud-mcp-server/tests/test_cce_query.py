"""Tests for cce_query_clusters / cce_query_nodes / cce_query_nodepools.

Each tool dispatches list-vs-detail based on whether the id is set; we
exercise both paths plus input validation and NOT_FOUND.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.services.cce.tools.query import make_query_tools

VALID_ID = "abc12345-6789-4abc-def0-0123456789ab"
OTHER_ID = "abc12345-6789-4abc-def0-0123456789cd"


# ----------------------------- Cluster --------------------------------------

def _fake_cluster(uid=VALID_ID, name="cce-prod"):
    md = SimpleNamespace(
        uid=uid, name=name, alias=None,
        labels={"env": "prod"}, annotations=None,
        creation_timestamp="2024-01-01T00:00:00Z",
        update_timestamp="2024-01-02T00:00:00Z",
        timezone="Asia/Shanghai",
    )
    sp = SimpleNamespace(
        type="VirtualMachine", flavor="cce.s1.small",
        version="v1.27", platform_version="cce.10.0",
        category="CCE", billing_mode=0, description="prod cluster",
        host_network=SimpleNamespace(vpc="vpc-x", subnet="subnet-y", security_group=None),
        container_network=SimpleNamespace(mode="overlay_l2", cidr="172.16.0.0/16"),
        service_network=SimpleNamespace(ipv4cidr="10.247.0.0/16"),
        kubernetes_svc_ip_range="10.247.0.0/16",
        kube_proxy_mode="iptables",
        ipv6enable=False,
    )
    st = SimpleNamespace(
        phase="Available", job_id=None, reason=None, message=None,
        endpoints=[
            SimpleNamespace(url="https://192.168.0.1:5443", type="Internal"),
            SimpleNamespace(url="https://eip.example.com:5443", type="External"),
        ],
    )
    return SimpleNamespace(kind="Cluster", api_version="v3", metadata=md, spec=sp, status=st)


def test_cce_query_clusters_list_mode(cce_settings, mock_cce_client):
    resp = MagicMock()
    resp.items = [_fake_cluster(), _fake_cluster(uid=OTHER_ID, name="cce-dev")]
    mock_cce_client.list_clusters.return_value = resp

    tools = make_query_tools(cce_settings)
    out = tools["cce_query_clusters"](type="VirtualMachine", status="Available")

    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["clusters"][0]["id"] == VALID_ID
    assert data["clusters"][0]["phase"] == "Available"
    assert data["clusters"][0]["type"] == "VirtualMachine"

    # SDK filters propagated
    sent = mock_cce_client.list_clusters.call_args[0][0]
    assert sent.type == "VirtualMachine"
    assert sent.status == "Available"
    mock_cce_client.show_cluster.assert_not_called()


def test_cce_query_clusters_detail_mode(cce_settings, mock_cce_client):
    mock_cce_client.show_cluster.return_value = _fake_cluster()

    tools = make_query_tools(cce_settings)
    out = tools["cce_query_clusters"](cluster_id=VALID_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["id"] == VALID_ID
    assert data["host_network"] == {"vpc": "vpc-x", "subnet": "subnet-y"}
    assert data["container_network"] == {"mode": "overlay_l2", "cidr": "172.16.0.0/16"}
    assert any(ep["type"] == "Internal" for ep in data["endpoints"])
    # List path NOT used
    mock_cce_client.list_clusters.assert_not_called()


def test_cce_query_clusters_invalid_status(cce_settings, mock_cce_client):
    tools = make_query_tools(cce_settings)
    out = tools["cce_query_clusters"](status="DoesNotExist")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_cce_client.list_clusters.assert_not_called()


def test_cce_query_clusters_detail_not_found(cce_settings, mock_cce_client):
    # An empty response object simulates "no resource" — metadata/spec are None.
    empty = SimpleNamespace(metadata=None, spec=None, status=None)
    mock_cce_client.show_cluster.return_value = empty
    tools = make_query_tools(cce_settings)
    out = tools["cce_query_clusters"](cluster_id=VALID_ID)
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ----------------------------- Node -----------------------------------------

def _fake_node(uid=VALID_ID, name="node-1"):
    md = SimpleNamespace(
        uid=uid, name=name, labels={"k": "v"}, annotations=None,
        creation_timestamp="2024-01-01T00:00:00Z",
        update_timestamp=None, owner_references=None,
    )
    sp = SimpleNamespace(
        flavor="s6.large.2", az="af-south-1a", os="EulerOS 2.10",
        billing_mode=0, count=1,
        root_volume=SimpleNamespace(volumetype="SSD", size=40),
        data_volumes=[SimpleNamespace(volumetype="SAS", size=100)],
        runtime=SimpleNamespace(name="containerd"),
        node_nic_spec=None, login=None, public_ip=None,
        k8s_tags={"role": "worker"}, user_tags=[], taints=[],
        dedicated_host_id=None, ecs_group_id=None,
        server_enterprise_project_id=None,
    )
    st = SimpleNamespace(
        phase="Active", private_ip="192.168.0.10", public_ip=None,
        server_id="ecs-uuid", job_id=None,
        last_probe_time="2024-01-02T00:00:00Z",
        private_i_pv6_ip=None, delete_status=None,
        configuration_up_to_date=True,
    )
    return SimpleNamespace(kind="Node", api_version="v3", metadata=md, spec=sp, status=st)


def test_cce_query_nodes_list_mode(cce_settings, mock_cce_client):
    resp = MagicMock()
    resp.items = [_fake_node(), _fake_node(uid=OTHER_ID, name="node-2")]
    mock_cce_client.list_nodes.return_value = resp

    tools = make_query_tools(cce_settings)
    out = tools["cce_query_nodes"](cluster_id=VALID_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["cluster_id"] == VALID_ID
    assert data["count"] == 2
    n = data["nodes"][0]
    assert n["id"] == VALID_ID
    assert n["flavor"] == "s6.large.2"
    assert n["private_ip"] == "192.168.0.10"
    # SDK called with cluster_id
    assert mock_cce_client.list_nodes.call_args[0][0].cluster_id == VALID_ID


def test_cce_query_nodes_detail_mode(cce_settings, mock_cce_client):
    mock_cce_client.show_node.return_value = _fake_node()
    tools = make_query_tools(cce_settings)
    out = tools["cce_query_nodes"](cluster_id=VALID_ID, node_id=VALID_ID)
    assert out["ok"] is True
    data = out["data"]
    assert data["root_volume"] == {"volumetype": "SSD", "size": 40}
    assert data["data_volumes"] == [{"volumetype": "SAS", "size": 100}]
    assert data["runtime"] == {"name": "containerd"}
    mock_cce_client.list_nodes.assert_not_called()


def test_cce_query_nodes_invalid_cluster_id(cce_settings, mock_cce_client):
    tools = make_query_tools(cce_settings)
    out = tools["cce_query_nodes"](cluster_id="!!")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"


# ----------------------------- Node Pool ------------------------------------

def _fake_nodepool(uid=VALID_ID, name="np-1", initial=3, current=3):
    md = SimpleNamespace(
        uid=uid, name=name, annotations=None,
        creation_timestamp="2024-01-01T00:00:00Z",
        update_timestamp=None, resource_version="1",
    )
    autoscaling = SimpleNamespace(
        enable=True, min_node_count=1, max_node_count=5,
        scale_down_cooldown_time=10, priority=0,
    )
    tmpl = SimpleNamespace(
        flavor="s6.large.2", az="af-south-1a", os="EulerOS 2.10",
        billing_mode=0, count=1,
        root_volume=SimpleNamespace(volumetype="SSD", size=40),
        data_volumes=[],
        runtime=SimpleNamespace(name="containerd"),
        k8s_tags={"role": "worker"}, user_tags=[], taints=[],
    )
    sp = SimpleNamespace(
        type="vm", node_template=tmpl, initial_node_count=initial,
        autoscaling=autoscaling, node_management=None,
        pod_security_groups=None, extension_scale_groups=None,
        custom_security_groups=None,
    )
    st = SimpleNamespace(
        current_node=current, creating_node=0, deleting_node=0,
        configuration_synced_node_count=current, phase="Synchronized",
        job_id=None, conditions=None, scale_group_statuses=None,
    )
    return SimpleNamespace(kind="NodePool", api_version="v3", metadata=md, spec=sp, status=st)


def test_cce_query_nodepools_list_mode(cce_settings, mock_cce_client):
    resp = MagicMock()
    resp.items = [_fake_nodepool()]
    mock_cce_client.list_node_pools.return_value = resp

    tools = make_query_tools(cce_settings)
    out = tools["cce_query_nodepools"](cluster_id=VALID_ID, show_default_node_pool=True)
    assert out["ok"] is True
    data = out["data"]
    assert data["cluster_id"] == VALID_ID
    p = data["nodepools"][0]
    assert p["initial_node_count"] == 3
    assert p["current_node"] == 3
    assert p["autoscaling_enabled"] is True
    assert p["min_node_count"] == 1
    sent = mock_cce_client.list_node_pools.call_args[0][0]
    assert sent.cluster_id == VALID_ID
    assert sent.show_default_node_pool is True


def test_cce_query_nodepools_detail_mode(cce_settings, mock_cce_client):
    mock_cce_client.show_node_pool.return_value = _fake_nodepool()
    tools = make_query_tools(cce_settings)
    out = tools["cce_query_nodepools"](cluster_id=VALID_ID, nodepool_id=VALID_ID)
    assert out["ok"] is True
    data = out["data"]
    assert data["node_template"]["flavor"] == "s6.large.2"
    assert data["node_template"]["runtime"] == {"name": "containerd"}
    assert data["autoscaling"]["max_node_count"] == 5
    mock_cce_client.list_node_pools.assert_not_called()


def test_cce_query_nodepools_detail_default_pool(cce_settings, mock_cce_client):
    """DefaultPool is a valid non-UUID nodepool_id accepted by Huawei Cloud."""
    mock_cce_client.show_node_pool.return_value = _fake_nodepool()
    tools = make_query_tools(cce_settings)
    out = tools["cce_query_nodepools"](cluster_id=VALID_ID, nodepool_id="DefaultPool")
    assert out["ok"] is True
    mock_cce_client.show_node_pool.assert_called_once()
    sent = mock_cce_client.show_node_pool.call_args[0][0]
    assert sent.nodepool_id == "DefaultPool"
