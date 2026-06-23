"""Tests for lifecycle tools — two-phase commit for destructive ops."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.errors import pending_actions
from huaweicloud_mcp.services.ecs.tools.lifecycle import make_lifecycle_tools

UUID_A = "11111111-2222-3333-4444-555555555555"
UUID_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ============================================================
# ecs_power_action — start (non-destructive, executes immediately)
# ============================================================
def test_power_action_start_returns_job_id(settings, mock_ecs_client):
    """start is non-destructive — executes immediately, no approval needed."""
    mock_ecs_client.batch_start_servers.return_value = MagicMock(job_id="job-1")
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_power_action"](server_ids=[UUID_A], action="start")
    assert out["ok"] is True
    assert out["data"]["job_id"] == "job-1"
    assert out["data"]["action"] == "start"
    mock_ecs_client.batch_start_servers.assert_called_once()
    mock_ecs_client.batch_stop_servers.assert_not_called()
    mock_ecs_client.batch_reboot_servers.assert_not_called()


# ============================================================
# ecs_power_action — stop/reboot (destructive, two-phase)
# ============================================================
@pytest.mark.parametrize("action", ["stop", "reboot"])
def test_power_action_destructive_returns_pending_approval(settings, mock_ecs_client, action):
    """Destructive actions return pending_approval + approval_id, NOT execute."""
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_power_action"](server_ids=[UUID_A], action=action)
    assert out["ok"] is True
    data = out["data"]
    assert data["status"] == "pending_approval"
    assert data["approval_id"].startswith("apr-")
    assert data["action"] == action
    assert data["server_ids"] == [UUID_A]
    assert "message" in data
    # Nothing executed yet
    mock_ecs_client.batch_stop_servers.assert_not_called()
    mock_ecs_client.batch_reboot_servers.assert_not_called()


def test_power_action_stop_stores_correct_preview(settings, mock_ecs_client):
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_power_action"](
        server_ids=[UUID_A, UUID_B], action="stop", type="HARD"
    )
    data = out["data"]
    assert data["type"] == "HARD"
    assert data["server_ids"] == [UUID_A, UUID_B]


def test_power_action_reboot_default_soft(settings, mock_ecs_client):
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_power_action"](server_ids=[UUID_A], action="reboot")
    assert out["data"]["type"] == "SOFT"


def test_power_action_invalid_action_rejected(settings, mock_ecs_client):
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_power_action"](server_ids=[UUID_A], action="halt")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_ecs_client.batch_start_servers.assert_not_called()


def test_power_action_invalid_uuid_rejected(settings, mock_ecs_client):
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_power_action"](server_ids=["bad"], action="start")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_ecs_client.batch_start_servers.assert_not_called()


def test_power_action_start_propagates_huawei_client_exception(settings, mock_ecs_client):
    from huaweicloudsdkcore.exceptions.exceptions import (
        ClientRequestException,
        SdkError,
    )

    sdk_err = SdkError(
        error_code="Ecs.0001",
        error_msg="bad request",
        request_id="req-xyz",
    )
    e = ClientRequestException(400, sdk_err)
    mock_ecs_client.batch_start_servers.side_effect = e
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_power_action"](server_ids=[UUID_A], action="start")
    assert out["ok"] is False
    assert out["error"]["code"] == "Ecs.0001"
    assert out["error"]["request_id"] == "req-xyz"
    assert out["error"]["status_code"] == 400


# ============================================================
# ecs_confirm_destructive — phase 2
# ============================================================
def test_confirm_destructive_executes_stop(settings, mock_ecs_client):
    """Confirming a stop approval actually executes the stop."""
    mock_ecs_client.batch_stop_servers.return_value = MagicMock(job_id="job-stop")
    tools = make_lifecycle_tools(settings)

    # Phase 1: request stop
    out1 = tools["ecs_power_action"](
        server_ids=[UUID_A, UUID_B], action="stop", type="HARD"
    )
    approval_id = out1["data"]["approval_id"]

    # Phase 2: confirm
    out2 = tools["ecs_confirm_destructive"](approval_id=approval_id)
    assert out2["ok"] is True
    assert out2["data"]["job_id"] == "job-stop"
    assert out2["data"]["action"] == "stop"
    sent = mock_ecs_client.batch_stop_servers.call_args[0][0]
    assert sent.body.os_stop.type == "HARD"
    assert {s.id for s in sent.body.os_stop.servers} == {UUID_A, UUID_B}


def test_confirm_destructive_executes_reboot(settings, mock_ecs_client):
    """Confirming a reboot approval actually executes the reboot."""
    mock_ecs_client.batch_reboot_servers.return_value = MagicMock(job_id="job-rb")
    tools = make_lifecycle_tools(settings)

    out1 = tools["ecs_power_action"](server_ids=[UUID_A], action="reboot")
    approval_id = out1["data"]["approval_id"]

    out2 = tools["ecs_confirm_destructive"](approval_id=approval_id)
    assert out2["ok"] is True
    assert out2["data"]["job_id"] == "job-rb"
    assert out2["data"]["action"] == "reboot"
    sent = mock_ecs_client.batch_reboot_servers.call_args[0][0]
    assert sent.body.reboot.type == "SOFT"


def test_confirm_destructive_invalid_approval_id(settings, mock_ecs_client):
    """Confirming with a bogus approval_id returns error."""
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_confirm_destructive"](approval_id="apr-nonexistent")
    assert out["ok"] is False
    assert out["error"]["code"] == "APPROVAL_NOT_FOUND"


def test_confirm_destructive_double_use_rejected(settings, mock_ecs_client):
    """Approval IDs are single-use — second call fails."""
    mock_ecs_client.batch_reboot_servers.return_value = MagicMock(job_id="job-rb")
    tools = make_lifecycle_tools(settings)

    out1 = tools["ecs_power_action"](server_ids=[UUID_A], action="reboot")
    approval_id = out1["data"]["approval_id"]

    # First use: OK
    out2 = tools["ecs_confirm_destructive"](approval_id=approval_id)
    assert out2["ok"] is True

    # Second use: rejected
    out3 = tools["ecs_confirm_destructive"](approval_id=approval_id)
    assert out3["ok"] is False
    assert out3["error"]["code"] == "APPROVAL_NOT_FOUND"


# ============================================================
# ecs_delete_server (two-phase)
# ============================================================
def test_delete_returns_pending_approval(settings, mock_ecs_client):
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_delete_server"](server_ids=[UUID_A])
    assert out["ok"] is True
    assert out["data"]["status"] == "pending_approval"
    assert out["data"]["action"] == "delete"
    mock_ecs_client.delete_servers.assert_not_called()


def test_delete_confirm_executes(settings, mock_ecs_client):
    mock_ecs_client.delete_servers.return_value = MagicMock(job_id="job-del")
    tools = make_lifecycle_tools(settings)

    out1 = tools["ecs_delete_server"](
        server_ids=[UUID_A],
        delete_publicip=True,
        delete_volume=True,
    )
    approval_id = out1["data"]["approval_id"]

    out2 = tools["ecs_confirm_destructive"](approval_id=approval_id)
    assert out2["ok"] is True
    assert out2["data"]["job_id"] == "job-del"
    sent = mock_ecs_client.delete_servers.call_args[0][0]
    assert sent.body.delete_publicip is True
    assert sent.body.delete_volume is True


# ============================================================
# ecs_resize_server (two-phase)
# ============================================================
def test_resize_returns_pending_approval(settings, mock_ecs_client):
    tools = make_lifecycle_tools(settings)
    out = tools["ecs_resize_server"](
        server_id=UUID_A, target_flavor_ref="s6.large.4"
    )
    assert out["ok"] is True
    assert out["data"]["status"] == "pending_approval"
    assert out["data"]["action"] == "resize"
    mock_ecs_client.resize_server.assert_not_called()


def test_resize_confirm_executes(settings, mock_ecs_client):
    mock_ecs_client.resize_server.return_value = MagicMock(job_id="job-rsz")
    tools = make_lifecycle_tools(settings)

    out1 = tools["ecs_resize_server"](
        server_id=UUID_A,
        target_flavor_ref="s6.large.4",
        mode="withStopServer",
    )
    approval_id = out1["data"]["approval_id"]

    out2 = tools["ecs_confirm_destructive"](approval_id=approval_id)
    assert out2["ok"] is True
    assert out2["data"]["job_id"] == "job-rsz"
    sent = mock_ecs_client.resize_server.call_args[0][0]
    assert sent.server_id == UUID_A
    assert sent.body.resize.flavor_ref == "s6.large.4"
    assert sent.body.resize.mode == "withStopServer"