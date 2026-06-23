"""Tests for cce_get_job."""
from __future__ import annotations

from types import SimpleNamespace

from huaweicloud_mcp.services.cce.tools.job import make_job_tools

VALID_ID = "abc12345-6789-4abc-def0-0123456789ab"


def _fake_job(phase="Success"):
    md = SimpleNamespace(uid=VALID_ID, creation_timestamp="t0", update_timestamp="t1")
    sub_md = SimpleNamespace(uid="sub-1", creation_timestamp="t0", update_timestamp="t1")
    sub_sp = SimpleNamespace(
        type="CreateNode", resource_id="ecs-x", resource_name="node-1",
    )
    sub_st = SimpleNamespace(phase="Success", reason=None)
    sub = SimpleNamespace(metadata=sub_md, spec=sub_sp, status=sub_st)
    sp = SimpleNamespace(
        type="CreateCluster", cluster_uid="cluster-x", resource_id="cluster-x",
        resource_name="cce-prod", extend_param=None, sub_jobs=[sub],
    )
    st = SimpleNamespace(phase=phase, reason=None)
    return SimpleNamespace(metadata=md, spec=sp, status=st)


def test_cce_get_job_success(cce_settings, mock_cce_client):
    mock_cce_client.show_job.return_value = _fake_job()
    tools = make_job_tools(cce_settings)
    out = tools["cce_get_job"](job_id=VALID_ID)
    assert out["ok"] is True
    data = out["data"]
    assert data["job_id"] == VALID_ID
    assert data["phase"] == "Success"
    assert data["type"] == "CreateCluster"
    assert data["cluster_id"] == "cluster-x"
    assert data["sub_jobs_total"] == 1
    assert data["sub_jobs"][0]["resource_name"] == "node-1"
    sent = mock_cce_client.show_job.call_args[0][0]
    assert sent.job_id == VALID_ID


def test_cce_get_job_failed_phase(cce_settings, mock_cce_client):
    mock_cce_client.show_job.return_value = _fake_job(phase="Failed")
    tools = make_job_tools(cce_settings)
    out = tools["cce_get_job"](job_id=VALID_ID)
    assert out["ok"] is True
    assert out["data"]["phase"] == "Failed"


def test_cce_get_job_invalid_id(cce_settings, mock_cce_client):
    tools = make_job_tools(cce_settings)
    out = tools["cce_get_job"](job_id="!")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_cce_client.show_job.assert_not_called()
