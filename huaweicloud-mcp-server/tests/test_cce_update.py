"""Tests for cce_update_nodepool — scale up vs scale down vs no-op."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.errors import pending_actions
from huaweicloud_mcp.services.cce.tools.update import make_update_tools

VALID_ID = "abc12345-6789-4abc-def0-0123456789ab"


def _fake_pool(initial: int, current: int, job_id="job-xyz"):
    md = SimpleNamespace(
        uid=VALID_ID, name="np-1", annotations=None,
        creation_timestamp=None, update_timestamp=None,
        resource_version="1",
    )
    tmpl = SimpleNamespace(
        flavor="s6.large.2", az="af-south-1a", os="EulerOS 2.10",
        billing_mode=0, count=1,
        root_volume=None, data_volumes=[], runtime=None,
        k8s_tags={}, user_tags=[], taints=[],
    )
    sp = SimpleNamespace(
        type="vm", node_template=tmpl, initial_node_count=initial,
        autoscaling=None, node_management=None,
    )
    st = SimpleNamespace(
        current_node=current, creating_node=0, deleting_node=0,
        configuration_synced_node_count=current, phase="Synchronized",
        job_id=job_id, conditions=None,
    )
    return SimpleNamespace(metadata=md, spec=sp, status=st)


def _setup_show_then_update(mock_cce_client, current_initial, current_node, after_initial):
    """Common fixture: show returns the 'before' pool; update returns 'after'."""
    mock_cce_client.show_node_pool.return_value = _fake_pool(
        current_initial, current_node
    )
    mock_cce_client.update_node_pool.return_value = _fake_pool(
        after_initial, after_initial, job_id="job-new"
    )


def test_scale_up_executes_immediately(cce_settings, mock_cce_client):
    _setup_show_then_update(mock_cce_client, current_initial=2, current_node=2, after_initial=5)

    tools = make_update_tools(cce_settings)
    out = tools["cce_update_nodepool"](
        cluster_id=VALID_ID, nodepool_id=VALID_ID, initial_node_count=5
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["action"] == "scale_up"
    assert data["from"] == 2
    assert data["to"] == 5
    assert data["job_id"] == "job-new"
    # SDK update WAS called
    mock_cce_client.update_node_pool.assert_called_once()
    body = mock_cce_client.update_node_pool.call_args[0][0].body
    assert body.spec.initial_node_count == 5


def test_scale_down_returns_pending_approval(cce_settings, mock_cce_client):
    _setup_show_then_update(mock_cce_client, current_initial=5, current_node=5, after_initial=2)

    tools = make_update_tools(cce_settings)
    out = tools["cce_update_nodepool"](
        cluster_id=VALID_ID, nodepool_id=VALID_ID, initial_node_count=2
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "pending_approval"
    assert data["action"] == "scale_down"
    assert data["from"] == 5
    assert data["to"] == 2
    assert "approval_id" in data
    # update was NOT called yet
    mock_cce_client.update_node_pool.assert_not_called()


def test_confirm_destructive_executes_scale_down(cce_settings, mock_cce_client):
    _setup_show_then_update(mock_cce_client, current_initial=5, current_node=5, after_initial=2)

    tools = make_update_tools(cce_settings)
    pending = tools["cce_update_nodepool"](
        cluster_id=VALID_ID, nodepool_id=VALID_ID, initial_node_count=2
    )["data"]
    approval_id = pending["approval_id"]

    out = tools["cce_confirm_destructive"](approval_id=approval_id)
    assert out["ok"] is True
    data = out["data"]
    assert data["action"] == "scale_down"
    assert data["from"] == 5
    assert data["to"] == 2
    assert data["job_id"] == "job-new"
    mock_cce_client.update_node_pool.assert_called_once()


def test_confirm_destructive_unknown_approval(cce_settings, mock_cce_client):
    tools = make_update_tools(cce_settings)
    out = tools["cce_confirm_destructive"](approval_id="apr-nope")
    assert out["ok"] is False
    assert out["error"]["code"] == "APPROVAL_NOT_FOUND"


def test_noop_when_count_unchanged(cce_settings, mock_cce_client):
    mock_cce_client.show_node_pool.return_value = _fake_pool(3, 3)
    tools = make_update_tools(cce_settings)
    out = tools["cce_update_nodepool"](
        cluster_id=VALID_ID, nodepool_id=VALID_ID, initial_node_count=3
    )
    assert out["ok"] is True
    assert out["data"]["status"] == "noop"
    assert out["data"]["current"] == 3
    mock_cce_client.update_node_pool.assert_not_called()


def test_pool_not_found(cce_settings, mock_cce_client):
    mock_cce_client.show_node_pool.return_value = SimpleNamespace(
        metadata=None, spec=None, status=None
    )
    tools = make_update_tools(cce_settings)
    out = tools["cce_update_nodepool"](
        cluster_id=VALID_ID, nodepool_id=VALID_ID, initial_node_count=2
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


def test_invalid_count_rejected(cce_settings, mock_cce_client):
    tools = make_update_tools(cce_settings)
    out = tools["cce_update_nodepool"](
        cluster_id=VALID_ID, nodepool_id=VALID_ID, initial_node_count=-1
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_cce_client.show_node_pool.assert_not_called()


def test_scale_up_default_pool_rejected(cce_settings, mock_cce_client):
    """DefaultPool does not support scaling — return NOT_SUPPORTED error."""
    tools = make_update_tools(cce_settings)
    out = tools["cce_update_nodepool"](
        cluster_id=VALID_ID, nodepool_id="DefaultPool", initial_node_count=1
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_SUPPORTED"
    assert "DefaultPool" in out["error"]["message"]
    # SDK should never be called
    mock_cce_client.show_node_pool.assert_not_called()
