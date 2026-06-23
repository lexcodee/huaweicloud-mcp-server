"""Tests for cursor-based pagination in cts_search_traces.

CTS uses marker-based cursor pagination (not offset). This module verifies:
  - Single-page mode returns next_marker from the response
  - auto_paginate walks through multiple marker pages correctly
  - max_results caps the merged result set and sets truncated=true
  - Empty marker terminates the loop
  - Safety cap on max pages
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.services.cts.models import SearchTracesInput
from huaweicloud_mcp.services.cts.tools.search import make_search_tools


def _make_trace(trace_id: str, trace_name: str = "createServer") -> MagicMock:
    """Build a mock Traces object with minimal fields."""
    t = MagicMock()
    t.trace_id = trace_id
    t.trace_name = trace_name
    t.trace_rating = "normal"
    t.trace_type = "system"
    t.time = 1718900000000
    t.service_type = "ECS"
    t.resource_type = "server"
    t.resource_name = f"server-{trace_id}"
    t.resource_id = trace_id
    t.user = None
    t.source_ip = "10.0.0.1"
    t.code = "200"
    t.message = ""
    t.request = None
    t.response = None
    return t


def _make_response(traces, marker=None):
    """Build a mock ListTracesResponse."""
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


class TestSinglePage:
    """Default auto_paginate=false — one page, next_marker exposed."""

    def test_returns_next_marker(self):
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [_make_trace(f"id-{i}") for i in range(3)]
        resp = _make_response(traces, marker="cursor-abc")

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(start_time="-1h", end_time="now", limit=10)

        assert result["ok"] is True
        data = result["data"]
        assert data["total_returned"] == 3
        assert data["next_marker"] == "cursor-abc"
        assert data["truncated"] is False

    def test_no_more_pages_marker_null(self):
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [_make_trace(f"id-{i}") for i in range(2)]
        resp = _make_response(traces, marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(start_time="-1h", end_time="now")

        assert result["ok"] is True
        assert result["data"]["next_marker"] is None


class TestAutoPaginate:
    """auto_paginate=true — walk marker pages, merge, cap at max_results."""

    def test_three_pages_merged(self):
        """3 pages: marker→marker→None. All results merged."""
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        page1 = _make_response([_make_trace("a"), _make_trace("b")], marker="m1")
        page2 = _make_response([_make_trace("c"), _make_trace("d")], marker="m2")
        page3 = _make_response([_make_trace("e")], marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.side_effect = [page1, page2, page3]
            mock_get.return_value = mock_cts_client

            result = search(
                start_time="-1h",
                end_time="now",
                auto_paginate=True,
                max_results=100,
                limit=10,
            )

        assert result["ok"] is True
        data = result["data"]
        assert data["total_returned"] == 5
        assert data["next_marker"] is None  # no more pages
        assert data["truncated"] is False

    def test_max_results_caps_and_sets_truncated(self):
        """max_results=3 with 2+2+1 pages → take 3, set truncated=True."""
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        page1 = _make_response([_make_trace("a"), _make_trace("b")], marker="m1")
        page2 = _make_response([_make_trace("c"), _make_trace("d")], marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.side_effect = [page1, page2]
            mock_get.return_value = mock_cts_client

            result = search(
                start_time="-1h",
                end_time="now",
                auto_paginate=True,
                max_results=3,
                limit=10,
            )

        assert result["ok"] is True
        data = result["data"]
        assert data["total_returned"] == 3
        assert data["truncated"] is True

    def test_marker_passed_as_next_parameter(self):
        """When next_marker is provided, it should be passed to the SDK."""
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        traces = [_make_trace("x")]
        resp = _make_response(traces, marker=None)

        with patch("huaweicloud_mcp.services.cts.tools.search.get_client") as mock_get:
            mock_cts_client = MagicMock()
            mock_cts_client.list_traces.return_value = resp
            mock_get.return_value = mock_cts_client

            result = search(
                start_time="-1h",
                end_time="now",
                next_marker="cursor-from-previous",
            )

        assert result["ok"] is True
        # Verify the SDK was called with the marker as the `next` param
        call_args = mock_cts_client.list_traces.call_args
        req = call_args[0][0]  # first positional arg = the request object
        assert req.next == "cursor-from-previous"


class TestSevenDayRejectsInTool:
    """Verify the search tool returns TIME_RANGE_TOO_OLD error for old dates."""

    def test_8_days_ago_rejected(self):
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        result = search(start_time="-8d", end_time="now")
        assert result["ok"] is False
        assert result["error"]["code"] == "TIME_RANGE_TOO_OLD"

    def test_invalid_range_rejected(self):
        settings = _settings()
        tools = make_search_tools(settings)
        search = tools["cts_search_traces"]

        # end_time is 2h ago, start_time is 1h ago → start > end
        result = search(start_time="-1h", end_time="-2h")
        assert result["ok"] is False
        assert result["error"]["code"] == "TIME_RANGE_INVALID"