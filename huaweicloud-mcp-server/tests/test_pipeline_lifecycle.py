"""Tests for the run + lifecycle tools — two-phase commit for destructive ops."""
from __future__ import annotations

from types import SimpleNamespace

from huaweicloud_mcp.errors import pending_actions
from huaweicloud_mcp.services.pipeline.tools.execution import make_execution_tools
from huaweicloud_mcp.services.pipeline.tools.lifecycle import make_lifecycle_tools

def test_pipeline_run_with_default_config(settings, mock_pipeline_client):
    mock_pipeline_client.run_pipeline.return_value = SimpleNamespace(
        pipeline_run_id="r-1",
        to_dict=lambda: {"pipeline_run_id": "r-1"},
    )
    tool = make_execution_tools(settings)["pipeline_run"]
    result = tool(pipeline_id="p1")

    assert result["ok"] is True
    assert result["data"]["pipeline_run_id"] == "r-1"
    # Body must be empty so the API uses pipeline defaults
    call = mock_pipeline_client.run_pipeline.call_args
    request = call.args[0] if call.args else call.kwargs["request"]
    body = request.body
    # No fields should be set
    assert body.sources is None
    assert body.variables is None
    assert body.description is None


def test_pipeline_run_with_branch_override(settings, mock_pipeline_client):
    mock_pipeline_client.run_pipeline.return_value = SimpleNamespace(
        pipeline_run_id="r-2",
        to_dict=lambda: {"pipeline_run_id": "r-2"},
    )
    tool = make_execution_tools(settings)["pipeline_run"]
    result = tool(
        pipeline_id="p1",
        sources=[{"params": {"default_branch": "release/2.0"}}],
        variables=[{"name": "ENV", "value": "staging"}],
        description="kick the tyres",
    )
    assert result["ok"] is True
    body = mock_pipeline_client.run_pipeline.call_args.args[0].body
    assert body.sources[0].params.default_branch == "release/2.0"
    assert body.variables[0].name == "ENV"
    assert body.variables[0].value == "staging"
    assert body.description == "kick the tyres"


def test_pipeline_set_status_enabled_calls_unban_endpoint(settings, mock_pipeline_client):
    mock_pipeline_client.do_http_request.return_value = True
    tool = make_lifecycle_tools(settings)["pipeline_set_status"]
    result = tool(pipeline_id="p1", status="enabled")
    assert result["ok"] is True
    assert result["data"]["enabled"] is True
    assert result["data"]["status"] == "enabled"
    call = mock_pipeline_client.do_http_request.call_args
    assert call.kwargs["method"] == "PUT"
    assert call.kwargs["resource_path"] == \
        "/v5/{project_id}/api/pipelines/{pipeline_id}/unban"
    assert call.kwargs["path_params"] == {
        "project_id": settings.default_project_id,
        "pipeline_id": "p1",
    }


def test_pipeline_set_status_enabled_executes_immediately(settings, mock_pipeline_client):
    """status='enabled' is non-destructive — executes immediately."""
    mock_pipeline_client.do_http_request.return_value = True
    tool = make_lifecycle_tools(settings)["pipeline_set_status"]
    result = tool(pipeline_id="p1", status="enabled")
    assert result["ok"] is True
    mock_pipeline_client.do_http_request.assert_called_once()


def test_pipeline_set_status_disabled_returns_pending_approval(settings, mock_pipeline_client):
    """status='disabled' is destructive — returns pending_approval, NOT execute."""
    tool = make_lifecycle_tools(settings)["pipeline_set_status"]
    result = tool(pipeline_id="p1", status="disabled")
    assert result["ok"] is True
    data = result["data"]
    assert data["status"] == "pending_approval"
    assert data["approval_id"].startswith("apr-")
    assert data["action"] == "disable_pipeline"
    # Nothing executed yet
    mock_pipeline_client.do_http_request.assert_not_called()


def test_pipeline_set_status_disabled_confirm_executes(settings, mock_pipeline_client):
    """Confirming a disable approval actually executes the ban."""
    mock_pipeline_client.do_http_request.return_value = True
    tools = make_lifecycle_tools(settings)

    # Phase 1: request disable
    out1 = tools["pipeline_set_status"](pipeline_id="p1", status="disabled")
    approval_id = out1["data"]["approval_id"]

    # Phase 2: confirm
    out2 = tools["pipeline_confirm_destructive"](approval_id=approval_id)
    assert out2["ok"] is True
    assert out2["data"]["enabled"] is False
    assert out2["data"]["status"] == "disabled"
    call = mock_pipeline_client.do_http_request.call_args
    assert call.kwargs["resource_path"] == \
        "/v5/{project_id}/api/pipelines/{pipeline_id}/ban"


def test_pipeline_confirm_destructive_invalid_id(settings, mock_pipeline_client):
    tools = make_lifecycle_tools(settings)
    result = tools["pipeline_confirm_destructive"](approval_id="apr-nonexistent")
    assert result["ok"] is False
    assert result["error"]["code"] == "APPROVAL_NOT_FOUND"


def test_pipeline_set_status_invalid_status_rejected(settings, mock_pipeline_client):
    tool = make_lifecycle_tools(settings)["pipeline_set_status"]
    result = tool(pipeline_id="p1", status="paused")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PARAMS"
    mock_pipeline_client.do_http_request.assert_not_called()