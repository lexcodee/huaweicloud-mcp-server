"""Tests for cts_get_trace_detail — single-event full body retrieval."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cts_mcp_server.config import Settings
from cts_mcp_server.tools.detail import make_detail_tools


def _make_trace(trace_id: str, **overrides) -> MagicMock:
    t = MagicMock()
    t.trace_id = trace_id
    t.trace_name = overrides.get("trace_name", "deleteEip")
    t.trace_rating = overrides.get("trace_rating", "warning")
    t.trace_type = overrides.get("trace_type", "system")
    t.time = 1718900000000
    t.record_time = 1718900000000
    t.service_type = overrides.get("service_type", "VPC")
    t.resource_type = "eip"
    t.resource_name = "eip-prod-01"
    t.resource_id = "eip-id-001"
    t.source_ip = "10.1.2.3"
    t.code = "200"
    t.message = ""
    t.api_version = "v1"
    t.endpoint = "vpc.af-south-1.myhuaweicloud.com"
    t.resource_url = None
    t.request_id = "req-001"
    t.enterprise_project_id = None
    t.read_only = False
    t.request = overrides.get("request", None)
    t.response = overrides.get("response", None)

    user = MagicMock()
    user.id = "user-id-001"
    user.name = "zhangsan"
    user.user_name = "zhangsan"
    user.account_id = "account-001"
    user.access_key_id = "AKIDXXXXXXXXXXXXXXXX"
    user.principal_urn = None
    user.type = "IAMUser"
    domain = MagicMock()
    domain.name = "my-domain"
    domain.id = "domain-id-001"
    user.domain = domain
    t.user = user
    return t


def _make_response(traces):
    resp = MagicMock()
    resp.traces = traces
    resp.meta_data = MagicMock()
    resp.meta_data.marker = None
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


class TestGetTraceDetail:
    def test_found(self):
        settings = _settings()
        tools = make_detail_tools(settings)
        detail = tools["cts_get_trace_detail"]

        trace = _make_trace("TR-001")
        resp = _make_response([trace])

        with patch("cts_mcp_server.tools.detail.get_cts_client") as mock_get:
            mock_client = MagicMock()
            mock_client.list_traces.return_value = resp
            mock_get.return_value = mock_client

            result = detail(trace_id="TR-001")

        assert result["ok"] is True
        data = result["data"]
        assert data["trace_id"] == "TR-001"
        assert data["trace_name"] == "deleteEip"
        assert data["trace_rating"] == "warning"
        assert data["user"]["user_name"] == "zhangsan"

    def test_not_found(self):
        settings = _settings()
        tools = make_detail_tools(settings)
        detail = tools["cts_get_trace_detail"]

        resp = _make_response([])

        with patch("cts_mcp_server.tools.detail.get_cts_client") as mock_get:
            mock_client = MagicMock()
            mock_client.list_traces.return_value = resp
            mock_get.return_value = mock_client

            result = detail(trace_id="TR-NONEXISTENT")

        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    def test_request_password_masked(self):
        """Verify password in request body is masked."""
        settings = _settings()
        tools = make_detail_tools(settings)
        detail = tools["cts_get_trace_detail"]

        trace = _make_trace(
            "TR-002",
            request='{"password":"hunter2","name":"alice"}',
        )
        resp = _make_response([trace])

        with patch("cts_mcp_server.tools.detail.get_cts_client") as mock_get:
            mock_client = MagicMock()
            mock_client.list_traces.return_value = resp
            mock_get.return_value = mock_client

            result = detail(trace_id="TR-002")

        assert result["ok"] is True
        data = result["data"]
        assert "***MASKED***" in data["request"]
        assert "hunter2" not in data["request"]
        assert "alice" in data["request"]

    def test_trace_id_passed_to_sdk(self):
        """Verify trace_id is passed to the SDK request."""
        settings = _settings()
        tools = make_detail_tools(settings)
        detail = tools["cts_get_trace_detail"]

        trace = _make_trace("TR-003")
        resp = _make_response([trace])

        with patch("cts_mcp_server.tools.detail.get_cts_client") as mock_get:
            mock_client = MagicMock()
            mock_client.list_traces.return_value = resp
            mock_get.return_value = mock_client

            result = detail(trace_id="TR-003", trace_type="data")

        assert result["ok"] is True
        req = mock_client.list_traces.call_args[0][0]
        assert req.trace_id == "TR-003"
        assert req.trace_type == "data"

    def test_long_body_truncated(self):
        """Body > 5000 chars should be truncated with flag."""
        settings = _settings()
        tools = make_detail_tools(settings)
        detail = tools["cts_get_trace_detail"]

        long_body = '{"data":"' + "x" * 10000 + '"}'
        trace = _make_trace("TR-004", request=long_body)
        resp = _make_response([trace])

        with patch("cts_mcp_server.tools.detail.get_cts_client") as mock_get:
            mock_client = MagicMock()
            mock_client.list_traces.return_value = resp
            mock_get.return_value = mock_client

            result = detail(trace_id="TR-004")

        assert result["ok"] is True
        data = result["data"]
        assert data["request_truncated"] is True
        assert "truncate_hint" in data
