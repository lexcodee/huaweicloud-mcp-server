"""Critical regression tests for pipeline_update_info.

Goal: prove that the read-modify-write logic only changes the explicitly
requested fields and preserves *every other* field on the pipeline record.
Any drift here is a real-world data-loss bug because UpdatePipelineInfo
is a full PUT replacement.

All tests updated for two-phase commit: pipeline_update_info now returns
pending_approval + approval_id. Use pipeline_confirm_destructive to execute.
"""
from __future__ import annotations

import json

from pipeline_mcp_server.errors import pending_actions
from pipeline_mcp_server.tools.update import make_update_tools
from pipeline_mcp_server.tools.lifecycle import make_lifecycle_tools


def _captured_dto(mock_client):
    """Pull the PipelineDTO body out of the captured update_pipeline_info call."""
    call = mock_client.update_pipeline_info.call_args
    request = call.args[0] if call.args else call.kwargs["request"]
    return request.body


# ---------------------------------------------------------------------------
# Happy paths (two-phase: update returns pending_approval, confirm executes)
# ---------------------------------------------------------------------------

def test_update_default_branch_only_preserves_other_fields(
    settings, mock_client, sample_pipeline_detail
):
    mock_client.show_pipeline_detail.return_value = sample_pipeline_detail
    mock_client.update_pipeline_info.return_value.to_dict = lambda: {
        "pipeline_id": "pipeline-uuid"
    }
    tools_update = make_update_tools(settings)
    tools_lifecycle = make_lifecycle_tools(settings)

    # Phase 1: request update
    result = tools_update["pipeline_update_info"](
        pipeline_id="pipeline-uuid",
        new_default_branch="release/2.0",
    )
    assert result["ok"] is True
    data = result["data"]
    assert data["status"] == "pending_approval"
    assert data["approval_id"].startswith("apr-")
    assert data["changes"]["default_branch"]["before"] == "main"
    assert data["changes"]["default_branch"]["after"] == "release/2.0"
    assert "pre_task" not in data["changes"]

    # Phase 2: confirm
    result2 = tools_lifecycle["pipeline_confirm_destructive"](
        approval_id=data["approval_id"]
    )
    assert result2["ok"] is True

    dto = _captured_dto(mock_client)
    # ----- target field flipped ----------------------------------------
    assert dto.sources[0].params.default_branch == "release/2.0"
    # ----- name / publish / manifest preserved -------------------------
    assert dto.name == "taifa-dev"
    assert dto.is_publish is False
    assert dto.manifest_version == "3.0"
    # ----- description / group_id preserved ----------------------------
    assert dto.description == "dev pipeline"
    assert dto.group_id == "grp-1"
    # ----- definition string is byte-identical to original (because we
    #       didn't mutate it). Allow JSON-equal check to be tolerant of
    #       separator/ordering choices made by the dumper. -------------
    assert json.loads(dto.definition) == json.loads(sample_pipeline_detail.definition)
    # ----- variables preserved verbatim --------------------------------
    assert len(dto.variables) == 2
    assert dto.variables[0].name == "VAR_A"
    assert dto.variables[0].value == "alpha"
    assert dto.variables[1].name == "SECRET_TOKEN"
    assert dto.variables[1].is_secret is True
    # ----- schedules preserved -----------------------------------------
    assert len(dto.schedules) == 1
    assert dto.schedules[0].uuid == "sched-1"
    assert dto.schedules[0].days_of_week == [1, 2, 3, 4, 5]
    assert dto.schedules[0].time_zone == "Asia/Shanghai"
    # ----- triggers preserved ------------------------------------------
    assert len(dto.triggers) == 1
    assert dto.triggers[0].git_url == "https://github.com/example/repo.git"
    assert dto.triggers[0].is_auto_commit is True
    assert dto.triggers[0].endpoint_id == "endpoint-1"
    # ----- non-target source-params fields preserved -------------------
    p = dto.sources[0].params
    assert p.git_type == "github"
    assert p.endpoint_id == "endpoint-1"
    assert p.git_url == "https://github.com/example/repo.git"
    assert p.alias == "primary"
    assert p.repo_name == "repo"


def test_update_pre_task_only_preserves_other_fields(
    settings, mock_client, sample_pipeline_detail
):
    mock_client.show_pipeline_detail.return_value = sample_pipeline_detail
    mock_client.update_pipeline_info.return_value.to_dict = lambda: {
        "pipeline_id": "pipeline-uuid"
    }
    tools_update = make_update_tools(settings)
    tools_lifecycle = make_lifecycle_tools(settings)

    result = tools_update["pipeline_update_info"](
        pipeline_id="pipeline-uuid",
        new_pre_task="official_devcloud_manualTrigger",
    )
    assert result["ok"] is True
    data = result["data"]
    assert data["status"] == "pending_approval"
    assert "default_branch" not in data["changes"]
    assert data["changes"]["pre_task"]["applied_to_count"] == 1

    # Confirm
    result2 = tools_lifecycle["pipeline_confirm_destructive"](
        approval_id=data["approval_id"]
    )
    assert result2["ok"] is True

    dto = _captured_dto(mock_client)
    parsed_def = json.loads(dto.definition)
    # First stage pre updated
    assert parsed_def["stages"][0]["pre"][0]["task"] == "official_devcloud_manualTrigger"
    # Second stage NOT touched
    assert parsed_def["stages"][1]["pre"][0]["task"] == "official_devcloud_autoTrigger"
    # Default branch unchanged
    assert dto.sources[0].params.default_branch == "main"


def test_update_both_fields_in_one_call(
    settings, mock_client, sample_pipeline_detail
):
    mock_client.show_pipeline_detail.return_value = sample_pipeline_detail
    mock_client.update_pipeline_info.return_value.to_dict = lambda: {}
    tools_update = make_update_tools(settings)
    tools_lifecycle = make_lifecycle_tools(settings)

    result = tools_update["pipeline_update_info"](
        pipeline_id="pipeline-uuid",
        new_default_branch="develop",
        new_pre_task="official_devcloud_manualTrigger",
    )
    assert result["ok"] is True
    assert result["data"]["status"] == "pending_approval"

    # Confirm
    result2 = tools_lifecycle["pipeline_confirm_destructive"](
        approval_id=result["data"]["approval_id"]
    )
    assert result2["ok"] is True

    dto = _captured_dto(mock_client)
    assert dto.sources[0].params.default_branch == "develop"
    parsed_def = json.loads(dto.definition)
    assert parsed_def["stages"][0]["pre"][0]["task"] == "official_devcloud_manualTrigger"


# ---------------------------------------------------------------------------
# Refusals (must not call update_pipeline_info)
# ---------------------------------------------------------------------------

def test_update_returns_pending_approval_not_execute(settings, mock_client, sample_pipeline_detail):
    """Without confirm, the tool returns pending_approval — no execution."""
    mock_client.show_pipeline_detail.return_value = sample_pipeline_detail
    tool = make_update_tools(settings)["pipeline_update_info"]

    result = tool(
        pipeline_id="pipeline-uuid",
        new_default_branch="develop",
    )
    assert result["ok"] is True
    assert result["data"]["status"] == "pending_approval"
    assert result["data"]["approval_id"].startswith("apr-")
    # Nothing executed yet
    mock_client.update_pipeline_info.assert_not_called()


def test_refuses_when_no_field_to_update(settings, mock_client):
    tool = make_update_tools(settings)["pipeline_update_info"]
    result = tool(pipeline_id="pipeline-uuid")
    assert result["ok"] is False
    assert result["error"]["code"] == "NO_FIELDS_TO_UPDATE"
    mock_client.show_pipeline_detail.assert_not_called()
    mock_client.update_pipeline_info.assert_not_called()


def test_refuses_invalid_pre_task_value(settings, mock_client):
    tool = make_update_tools(settings)["pipeline_update_info"]
    result = tool(
        pipeline_id="pipeline-uuid",
        new_pre_task="something_wrong",
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PRE_TASK"
    mock_client.update_pipeline_info.assert_not_called()


def test_refuses_when_alias_required_for_multi_source(settings, mock_client):
    """Multiple sources without disambiguating alias must fail before PUT."""
    from types import SimpleNamespace

    detail = SimpleNamespace(
        id="pid", name="x", description=None, manifest_version="3.0",
        is_publish=False, sources=[
            SimpleNamespace(type="code", params=SimpleNamespace(
                alias="a", default_branch="main", git_type="git",
                git_url=None, ssh_git_url=None, web_url=None,
                repo_name=None, codehub_id=None, endpoint_id=None,
            )),
            SimpleNamespace(type="code", params=SimpleNamespace(
                alias="b", default_branch="dev", git_type="git",
                git_url=None, ssh_git_url=None, web_url=None,
                repo_name=None, codehub_id=None, endpoint_id=None,
            )),
        ],
        variables=None, schedules=None, triggers=None,
        group_id=None, definition='{"stages":[]}',
        security_level=None, component_id=None, project_id="p",
    )
    mock_client.show_pipeline_detail.return_value = detail
    tool = make_update_tools(settings)["pipeline_update_info"]

    result = tool(
        pipeline_id="pid", new_default_branch="release",
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "SOURCE_ALIAS_REQUIRED"
    mock_client.update_pipeline_info.assert_not_called()
