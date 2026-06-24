"""Tests for lts_search_logs / lts_get_log_context / lts_query_histogram."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from huaweicloud_mcp.services.lts.tools.search import (
    _parse_histogram_payload,
    make_search_tools,
)

GID = "abc12345-6789-4abc-def0-0123456789ab"
SID = "11112222-6789-4abc-def0-0123456789ab"


def _fake_log(line_num="100", content="ERROR something failed", labels=None):
    return SimpleNamespace(
        line_num=line_num,
        content=content,
        labels=labels or {"level": "ERROR"},
    )


# ============================================================
# lts_search_logs
# ============================================================
def test_search_logs_keyword_mode(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.logs = [_fake_log("101"), _fake_log("100")]
    resp.count = 2
    resp.is_query_complete = True
    resp.analysis_logs = None
    mock_lts_client.list_logs.return_value = resp

    tools = make_search_tools(lts_settings)
    out = tools["lts_search_logs"](
        log_group_id=GID,
        log_stream_id=SID,
        keywords="ERROR",
        limit=50,
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 2
    assert data["total_returned"] == 2
    assert data["query"]["mode"] == "keyword"
    assert data["query"]["keywords"] == "ERROR"
    assert data["logs"][0]["line_num"] == "101"
    # SDK call: body propagated correctly
    sent_req = mock_lts_client.list_logs.call_args[0][0]
    assert sent_req.log_group_id == GID
    assert sent_req.log_stream_id == SID
    assert sent_req.body.keywords == "ERROR"
    assert sent_req.body.is_desc is True


def test_search_logs_sql_mode_attaches_analysis(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.logs = []
    resp.count = 5
    resp.is_query_complete = True
    resp.analysis_logs = [{"service": "api", "c": 5}]
    mock_lts_client.list_logs.return_value = resp

    tools = make_search_tools(lts_settings)
    out = tools["lts_search_logs"](
        log_group_id=GID,
        log_stream_id=SID,
        query="level:ERROR | stats count() by service",
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["query"]["mode"] == "sql"
    assert data["query"]["query"].startswith("level:ERROR")
    assert data["analysis_logs"] == [{"service": "api", "c": 5}]
    sent_req = mock_lts_client.list_logs.call_args[0][0]
    assert sent_req.body.query.startswith("level:ERROR")
    # SQL mode forces is_analysis_query
    assert sent_req.body.is_analysis_query is True


def test_search_logs_invalid_ids(lts_settings, mock_lts_client):
    tools = make_search_tools(lts_settings)
    out = tools["lts_search_logs"](log_group_id="!!", log_stream_id=SID)
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_lts_client.list_logs.assert_not_called()


def test_search_logs_bad_time_range(lts_settings, mock_lts_client):
    tools = make_search_tools(lts_settings)
    out = tools["lts_search_logs"](
        log_group_id=GID,
        log_stream_id=SID,
        start_time="2026-06-20 22:00:00",
        end_time="2026-06-20 21:00:00",
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "TIME_RANGE_INVALID"
    mock_lts_client.list_logs.assert_not_called()


def test_search_logs_time_range_too_wide(lts_settings, mock_lts_client):
    tools = make_search_tools(lts_settings)
    out = tools["lts_search_logs"](
        log_group_id=GID,
        log_stream_id=SID,
        start_time="-90d",
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "TIME_RANGE_TOO_WIDE"


def test_search_logs_pagination_via_line_num(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.logs = []
    resp.count = 0
    resp.is_query_complete = True
    resp.analysis_logs = None
    mock_lts_client.list_logs.return_value = resp

    tools = make_search_tools(lts_settings)
    tools["lts_search_logs"](
        log_group_id=GID,
        log_stream_id=SID,
        line_num="42",
    )
    sent_req = mock_lts_client.list_logs.call_args[0][0]
    assert sent_req.body.line_num == "42"
    assert sent_req.body.search_type == "forwards"


def test_search_logs_long_content_truncated(lts_settings, mock_lts_client):
    huge = "x" * 5000
    resp = MagicMock()
    resp.logs = [_fake_log(content=huge)]
    resp.count = 1
    resp.is_query_complete = True
    resp.analysis_logs = None
    mock_lts_client.list_logs.return_value = resp

    tools = make_search_tools(lts_settings)
    out = tools["lts_search_logs"](log_group_id=GID, log_stream_id=SID, keywords="x")
    entry = out["data"]["logs"][0]
    assert entry["truncated"] is True
    assert len(entry["content"]) == 2000


# ============================================================
# lts_get_log_context
# ============================================================
def test_get_log_context_basic(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.logs = [_fake_log("99"), _fake_log("100"), _fake_log("101")]
    mock_lts_client.list_log_context.return_value = resp

    tools = make_search_tools(lts_settings)
    out = tools["lts_get_log_context"](
        log_group_id=GID,
        log_stream_id=SID,
        line_num="100",
        backwards=1,
        forwards=1,
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["pivot"]["line_num"] == "100"
    assert data["total_returned"] == 3
    sent = mock_lts_client.list_log_context.call_args[0][0]
    assert sent.log_group_id == GID
    assert sent.body.line_num == "100"
    assert sent.body.backwards_size == 1
    assert sent.body.forwards_size == 1


def test_get_log_context_zero_window_rejected(lts_settings, mock_lts_client):
    tools = make_search_tools(lts_settings)
    out = tools["lts_get_log_context"](
        log_group_id=GID, log_stream_id=SID, line_num="100", backwards=0, forwards=0
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_lts_client.list_log_context.assert_not_called()


def test_get_log_context_validation_size(lts_settings, mock_lts_client):
    tools = make_search_tools(lts_settings)
    out = tools["lts_get_log_context"](
        log_group_id=GID, log_stream_id=SID, line_num="100", backwards=9999, forwards=1
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"


# ============================================================
# lts_query_histogram
# ============================================================
def test_histogram_payload_parser_list_of_objects():
    raw = json.dumps([{"time": 1000, "count": 5}, {"time": 2000, "count": 7}])
    out = _parse_histogram_payload(raw)
    assert out == [{"ts_ms": 1000, "count": 5}, {"ts_ms": 2000, "count": 7}]


def test_histogram_payload_parser_handles_invalid():
    out = _parse_histogram_payload("not json")
    assert out and "raw" in out[0]


def test_histogram_payload_parser_empty():
    assert _parse_histogram_payload(None) == []
    assert _parse_histogram_payload("") == []


def test_query_histogram_basic(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.histogram = json.dumps([{"time": 1000, "count": 5}])
    resp.count = 5
    resp.is_query_complete = True
    mock_lts_client.list_log_histogram.return_value = resp

    tools = make_search_tools(lts_settings)
    out = tools["lts_query_histogram"](
        log_group_id=GID, log_stream_id=SID, step="15m", keyword="ERROR"
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["count"] == 5
    assert data["step"] == "15m"
    assert data["step_ms"] == 15 * 60_000
    assert data["buckets"] == [{"ts_ms": 1000, "count": 5}]
    sent = mock_lts_client.list_log_histogram.call_args[0][0]
    assert sent.body.group_id == GID
    assert sent.body.stream_id == SID
    assert sent.body.key_word == "ERROR"
    assert sent.body.step_interval == 15 * 60_000


def test_query_histogram_invalid_step(lts_settings, mock_lts_client):
    tools = make_search_tools(lts_settings)
    out = tools["lts_query_histogram"](
        log_group_id=GID, log_stream_id=SID, step="3m"
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_lts_client.list_log_histogram.assert_not_called()
