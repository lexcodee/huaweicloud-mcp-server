"""Smoke test for cts_search_traces — end-to-end with mocked SDK."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.services.cts.tools.search import make_search_tools


def _make_trace(trace_id: str, **overrides) -> MagicMock:
    t = MagicMock()
    t.trace_id = trace_id
    t.trace_name = overrides.get("trace_name", "createServer")
    t.trace_rating = overrides.get("trace_rating", "normal")
    t.trace_type = overrides.get("trace_type", "system")
    t.time = 1718900000000
    t.service_type = overrides.get("service_type", "ECS")
    t.resource_type = overrides.get("resource_type", "server")
    t.resource_name = overrides.get("resource_name", f"server-{trace_id}")
    t.resource_id = trace_id
    t.user = None
    t.source_ip = "10.0.0.1"
    t.code = "200"
    t.message = ""
    t.request = overrides.get("request", None)
    t.response = overrides.get("response", None)
    return t


def _make_response(traces, marker=None):
    resp = MagicMock()
    resp.traces = traces
    resp.meta_data = MagicMock()
    resp.meta_data.marker = marker
    resp.meta_data.count = len(traces)
    return resp


def _settings():
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        default_timezone="UTC",
        log_file=None,
        log_level="WARNING",
    )


class TestSearchSmoke:
    def test_basic_search(self):
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [_make_trace("id-1"), _make_trace("id-2")]
        resp = _make_response(traces, marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(start_time="-1h", end_time="now")

        assert result["ok"] is True
        data = result["data"]
        assert data["total_returned"] == 2
        assert len(data["traces"]) == 2
        assert data["traces"][0]["trace_id"] == "id-1"

    def test_search_with_service_filter(self):
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [_make_trace("id-1", service_type="OBS")]
        resp = _make_response(traces, marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(start_time="-1h", end_time="now", service_type="OBS")

        assert result["ok"] is True
        # Verify service_type was passed to the SDK request
        req = mock_cts_client.list_traces.call_args[0][0]
        assert req.service_type == "OBS"

    def test_search_with_trace_rating(self):
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [_make_trace("id-1", trace_rating="incident")]
        resp = _make_response(traces, marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(start_time="-1h", end_time="now", trace_rating="incident")

        assert result["ok"] is True
        req = mock_cts_client.list_traces.call_args[0][0]
        assert req.trace_rating == "incident"

    def test_request_response_masked_in_summary(self):
        """Verify that password in request body is masked in the summary."""
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [
            _make_trace(
                "id-1",
                request='{"password": "***","name":"alice"}',
                response='{"code":200}',
            )
        ]
        resp = _make_response(traces, marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(start_time="-1h", end_time="now")

        assert result["ok"] is True
        trace = result["data"]["traces"][0]
        assert "***MASKED***" in trace["request_summary"]
        assert "hunter2" not in trace["request_summary"]
        assert "alice" in trace["request_summary"]

    def test_data_trace_type(self):
        """trace_type=data should be passed through."""
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [_make_trace("id-1", trace_type="data")]
        resp = _make_response(traces, marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(start_time="-1h", end_time="now", trace_type="data")

        assert result["ok"] is True
        req = mock_cts_client.list_traces.call_args[0][0]
        assert req.trace_type == "data"