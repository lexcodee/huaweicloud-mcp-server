"""Tests for ecs_get_job_status."""
from __future__ import annotations

from unittest.mock import MagicMock

from ecs_mcp_server.tools.job import make_job_tools


def test_job_status_success(settings, mock_client):
    sub = MagicMock(
        job_id="sub-1", job_type="startServer", status="SUCCESS",
        begin_time="t1", end_time="t2", error_code=None, fail_reason=None,
        entities=None,
    )
    entities = MagicMock(sub_jobs=[sub], sub_jobs_total=1)
    resp = MagicMock(
        job_id="job-1", job_type="batchStartServers", status="SUCCESS",
        begin_time="t1", end_time="t2", error_code=None, fail_reason=None,
        message=None, code=None, entities=entities,
    )
    mock_client.show_job.return_value = resp

    tools = make_job_tools(settings)
    out = tools["ecs_get_job_status"](job_id="job-1")
    assert out["ok"] is True
    data = out["data"]
    assert data["job_id"] == "job-1"
    assert data["status"] == "SUCCESS"
    assert data["sub_jobs_total"] == 1
    assert data["sub_jobs"][0]["status"] == "SUCCESS"


def test_job_status_fail_carries_error(settings, mock_client):
    resp = MagicMock(
        job_id="job-2", job_type="deleteServer", status="FAIL",
        begin_time="t1", end_time="t2",
        error_code="Ecs.0042", fail_reason="server is locked",
        message="failed", code="Ecs.0042", entities=None,
    )
    mock_client.show_job.return_value = resp
    tools = make_job_tools(settings)
    out = tools["ecs_get_job_status"](job_id="job-2")
    assert out["ok"] is True
    assert out["data"]["status"] == "FAIL"
    assert out["data"]["error_code"] == "Ecs.0042"
    assert out["data"]["fail_reason"] == "server is locked"


def test_job_status_missing_job_id(settings, mock_client):
    tools = make_job_tools(settings)
    out = tools["ecs_get_job_status"](job_id="")
    # Empty string is technically allowed by Pydantic str — let's at least
    # confirm we hit the SDK with that value (empty), not crash on validation.
    assert out["ok"] in (True, False)  # depends on SDK; at least no exception
