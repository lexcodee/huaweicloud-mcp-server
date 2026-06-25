"""Tests for VPC flow log data query tool."""
from __future__ import annotations

from unittest.mock import MagicMock

from huaweicloud_mcp.services.vpc.tools.flow_log import make_flow_log_tools

FLOW_LOG_ID = "fl-44444444-4444-4444-4444-444444444444"


def _fake_flow_log_config():
    """Fake ShowFlowLogResponse.flow_log."""
    f = MagicMock()
    f.id = FLOW_LOG_ID
    f.log_group_id = "lg-12345"
    f.log_topic_id = "lt-67890"
    return f


def _fake_lts_log(content, line_num="100"):
    """Fake LTS log entry."""
    item = MagicMock()
    item.content = content
    item.line_num = line_num
    item.collect_time = 1700000000000
    return item


# A valid VPC flow log record (space-delimited, 14 fields):
# version project_id interface_id srcaddr dstaddr srcport dstport
# protocol packets bytes start end action log_status
FLOW_LOG_LINE_ACCEPT = (
    "2 123456789012 eni-abc123 10.0.0.1 10.0.0.2 80 443 6 100 5000 "
    "1700000000 1700000010 ACCEPT OK"
)
FLOW_LOG_LINE_REJECT = (
    "2 123456789012 eni-abc123 10.0.0.3 10.0.0.2 80 22 6 0 0 "
    "1700000000 1700000010 REJECT NO_DATA"
)


def _setup_flow_log_test(settings, mock_lts_client_for_vpc, logs):
    """Helper: set up VPC show_flow_log + LTS list_logs mocks."""
    vpc_fake = mock_lts_client_for_vpc["vpc"]
    lts_fake = mock_lts_client_for_vpc["lts"]

    fl_resp = MagicMock()
    fl_resp.flow_log = _fake_flow_log_config()
    vpc_fake.show_flow_log.return_value = fl_resp

    lts_resp = MagicMock()
    lts_resp.logs = logs
    lts_fake.list_logs.return_value = lts_resp

    return make_flow_log_tools(settings)


def test_query_flow_log_data_basic(settings, mock_lts_client_for_vpc):
    tools = _setup_flow_log_test(
        settings, mock_lts_client_for_vpc,
        [_fake_lts_log(FLOW_LOG_LINE_ACCEPT), _fake_lts_log(FLOW_LOG_LINE_REJECT)],
    )
    out = tools["vpc_query_flow_log_data"](flow_log_id=FLOW_LOG_ID)

    assert out["ok"] is True
    data = out["data"]
    assert data["flow_log_id"] == FLOW_LOG_ID
    assert data["total_returned"] == 2
    assert data["records"][0]["action"] == "accept"
    assert data["records"][0]["srcaddr"] == "10.0.0.1"
    assert data["records"][0]["dstport"] == 443
    assert data["records"][0]["protocol_name"] == "tcp"
    assert data["records"][1]["action"] == "reject"


def test_query_flow_log_data_filter_action(settings, mock_lts_client_for_vpc):
    tools = _setup_flow_log_test(
        settings, mock_lts_client_for_vpc,
        [_fake_lts_log(FLOW_LOG_LINE_ACCEPT), _fake_lts_log(FLOW_LOG_LINE_REJECT)],
    )
    out = tools["vpc_query_flow_log_data"](flow_log_id=FLOW_LOG_ID, action="reject")

    assert out["ok"] is True
    data = out["data"]
    assert data["total_returned"] == 1
    assert data["records"][0]["action"] == "reject"


def test_query_flow_log_data_filter_src_ip(settings, mock_lts_client_for_vpc):
    tools = _setup_flow_log_test(
        settings, mock_lts_client_for_vpc,
        [_fake_lts_log(FLOW_LOG_LINE_ACCEPT), _fake_lts_log(FLOW_LOG_LINE_REJECT)],
    )
    out = tools["vpc_query_flow_log_data"](flow_log_id=FLOW_LOG_ID, src_ip="10.0.0.1")

    assert out["ok"] is True
    data = out["data"]
    assert data["total_returned"] == 1
    assert data["records"][0]["srcaddr"] == "10.0.0.1"


def test_query_flow_log_data_filter_dst_port(settings, mock_lts_client_for_vpc):
    tools = _setup_flow_log_test(
        settings, mock_lts_client_for_vpc,
        [_fake_lts_log(FLOW_LOG_LINE_ACCEPT), _fake_lts_log(FLOW_LOG_LINE_REJECT)],
    )
    out = tools["vpc_query_flow_log_data"](flow_log_id=FLOW_LOG_ID, dst_port=22)

    assert out["ok"] is True
    data = out["data"]
    assert data["total_returned"] == 1
    assert data["records"][0]["dstport"] == 22


def test_query_flow_log_data_not_found(settings, mock_lts_client_for_vpc):
    vpc_fake = mock_lts_client_for_vpc["vpc"]
    fl_resp = MagicMock()
    fl_resp.flow_log = None
    vpc_fake.show_flow_log.return_value = fl_resp

    tools = make_flow_log_tools(settings)
    out = tools["vpc_query_flow_log_data"](flow_log_id="nonexistent")

    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


def test_query_flow_log_data_no_lts_config(settings, mock_lts_client_for_vpc):
    vpc_fake = mock_lts_client_for_vpc["vpc"]
    fl_resp = MagicMock()
    f = MagicMock()
    f.log_group_id = None
    f.log_topic_id = None
    fl_resp.flow_log = f
    vpc_fake.show_flow_log.return_value = fl_resp

    tools = make_flow_log_tools(settings)
    out = tools["vpc_query_flow_log_data"](flow_log_id=FLOW_LOG_ID)

    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_FLOW_LOG_CONFIG"


def test_query_flow_log_data_empty_results(settings, mock_lts_client_for_vpc):
    tools = _setup_flow_log_test(settings, mock_lts_client_for_vpc, [])
    out = tools["vpc_query_flow_log_data"](flow_log_id=FLOW_LOG_ID)

    assert out["ok"] is True
    assert out["data"]["total_returned"] == 0
    assert out["data"]["records"] == []
