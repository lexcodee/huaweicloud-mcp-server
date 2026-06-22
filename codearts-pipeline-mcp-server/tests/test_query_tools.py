"""Tests for the read-only query tools (pipeline_list, pipeline_get_detail)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from pipeline_mcp_server.tools.query import make_query_tools


def test_pipeline_list_returns_compact_envelope(settings, mock_client):
    fake_resp = SimpleNamespace(
        offset=0,
        limit=20,
        total=1,
        pipelines=[
            SimpleNamespace(
                pipeline_id="p1",
                name="taifa-dev",
                project_id="proj",
                project_name="Taifa Leo Dev",
                component_id=None,
                is_publish=False,
                is_collect=None,
                manifest_version="3.0",
                create_time=1700000000,
                latest_run=SimpleNamespace(
                    pipeline_id="p1",
                    pipeline_run_id="r-1",
                    executor_id="u",
                    executor_name="alice",
                    stage_status_list=[
                        SimpleNamespace(
                            name="Build", status="COMPLETED",
                            category=None, start_time=1, end_time=2,
                        ),
                    ],
                    status="COMPLETED",
                    run_number=12,
                    trigger_type="MANUAL",
                    build_params=SimpleNamespace(target_branch="main", commit_id="abc"),
                    artifact_params=None,
                    start_time=1, end_time=2,
                    modify_url=None, detail_url="https://example.com",
                ),
                convert_sign=None,
                security_level=None,
            ),
        ],
    )
    mock_client.list_pipelines.return_value = fake_resp

    tool = make_query_tools(settings)["pipeline_list"]
    result = tool()

    assert result["ok"] is True
    data = result["data"]
    assert data["total"] == 1
    p = data["pipelines"][0]
    assert p["pipeline_id"] == "p1"
    assert p["name"] == "taifa-dev"
    lr = p["latest_run"]
    assert lr["status"] == "COMPLETED"
    assert lr["target_branch"] == "main"
    assert lr["stage_status_list"][0]["name"] == "Build"


def test_pipeline_list_rejects_unknown_status(settings, mock_client):
    tool = make_query_tools(settings)["pipeline_list"]
    result = tool(status=["BANANA"])
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_PARAMS"
    mock_client.list_pipelines.assert_not_called()


def test_pipeline_get_detail_decodes_definition_string(settings, mock_client):
    definition_obj = {"stages": [{"name": "s1", "pre": [{"task": "x", "sequence": 0}]}]}
    fake_detail = SimpleNamespace(
        id="p1", name="taifa-dev", description=None, manifest_version="3.0",
        is_publish=False, creator_id="u", creator_name="alice",
        create_time=1, update_time=2,
        sources=[SimpleNamespace(
            type="code",
            params=SimpleNamespace(
                git_type="github", default_branch="main",
                alias="primary", endpoint_id="e1",
                git_url="g", ssh_git_url=None, web_url=None,
                repo_name="r", codehub_id=None,
            ),
        )],
        variables=None, schedules=None, triggers=None,
        group_id="g1", project_id="proj", component_id=None,
        security_level=None,
        definition=json.dumps(definition_obj),
    )
    mock_client.show_pipeline_detail.return_value = fake_detail

    tool = make_query_tools(settings)["pipeline_get_detail"]
    result = tool(pipeline_id="p1")

    assert result["ok"] is True
    data = result["data"]
    # definition is decoded to a dict, not the raw string
    assert isinstance(data["definition"], dict)
    assert data["definition"]["stages"][0]["pre"][0]["task"] == "x"
    assert data["sources"][0]["params"]["default_branch"] == "main"


def test_missing_project_id_when_no_default(monkeypatch, mock_client):
    """When neither caller nor settings supplies project_id, fail cleanly."""
    from pipeline_mcp_server.config import Settings

    s = Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        region="af-south-1",
        default_project_id=None,
        log_level="WARNING",
        log_file=None,
        http_timeout=30,
        network_retries=2,
    )
    tool = make_query_tools(s)["pipeline_list"]
    result = tool()
    assert result["ok"] is False
    assert result["error"]["code"] == "MISSING_PROJECT_ID"
    mock_client.list_pipelines.assert_not_called()
