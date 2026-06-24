"""Tests for lts_query_alarm_rules and lts_list_alarm_history."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from huaweicloud_mcp.services.lts.tools.alarm import make_alarm_tools

RID_KW = "abc12345-6789-4abc-def0-0123456789ab"
RID_SQL = "11112222-6789-4abc-def0-0123456789ab"


def _fake_keyword_rule(rid=RID_KW, name="kw-rule"):
    freq = SimpleNamespace(type="HOURLY", hour_of_day=1, cron_expr=None,
                            day_of_week=None, fixed_rate=None, fixed_rate_unit=None)
    req = SimpleNamespace(
        keywords="ERROR",
        condition=">=",
        number=10,
        log_group_id="gid",
        log_stream_id="sid",
        search_time_range_unit="minute",
        search_time_range=5,
        log_group_name="grp",
        log_stream_name="strm",
        whether_global=False,
        expression=None,
    )
    return SimpleNamespace(
        keywords_alarm_rule_id=rid,
        keywords_alarm_rule_name=name,
        alarm_rule_alias=None,
        keywords_alarm_rule_description="prod errors",
        keywords_alarm_level="Critical",
        status="RUNNING",
        trigger_condition_count=1,
        trigger_condition_frequency=1,
        create_time=1700000000000,
        update_time=1700000001000,
        condition_expression=None,
        frequency=freq,
        notification_frequency=15,
        alarm_action_rule_name="action-1",
        whether_recovery_policy=True,
        recovery_policy=3,
        keywords_requests=[req],
        tags=None,
    )


def _fake_sql_rule(rid=RID_SQL, name="sql-rule"):
    freq = SimpleNamespace(type="FIXED_RATE", fixed_rate=5, fixed_rate_unit="minute",
                            cron_expr=None, hour_of_day=None, day_of_week=None)
    req = SimpleNamespace(
        sql="SELECT count(*) FROM logs WHERE level='ERROR'",
        log_group_id="gid",
        log_stream_id="sid",
        search_time_range_unit="minute",
        search_time_range=10,
        title="error count",
        log_group_name="grp",
        log_stream_name="strm",
        sql_request_id="sq-1",
    )
    return SimpleNamespace(
        sql_alarm_rule_id=rid,
        sql_alarm_rule_name=name,
        alarm_rule_alias=None,
        sql_alarm_rule_description="errors via sql",
        sql_alarm_level="Major",
        status="RUNNING",
        trigger_condition_count=1,
        trigger_condition_frequency=1,
        create_time=1700000000000,
        update_time=1700000001000,
        is_css_sql=False,
        condition_expression="x > 0",
        frequency=freq,
        notification_frequency=15,
        alarm_action_rule_name="action-1",
        whether_recovery_policy=True,
        recovery_policy=3,
        sql_requests=[req],
        topics=None,
        tags=None,
    )


# ============================================================
# lts_query_alarm_rules — LIST mode
# ============================================================
def test_alarm_rules_list_all(lts_settings, mock_lts_client):
    kw_resp = MagicMock()
    kw_resp.keywords_alarm_rules = [_fake_keyword_rule()]
    sql_resp = MagicMock()
    sql_resp.sql_alarm_rules = [_fake_sql_rule()]
    mock_lts_client.list_keywords_alarm_rules.return_value = kw_resp
    mock_lts_client.list_sql_alarm_rules.return_value = sql_resp

    tools = make_alarm_tools(lts_settings)
    out = tools["lts_query_alarm_rules"]()
    assert out["ok"] is True
    data = out["data"]
    assert data["mode"] == "list"
    assert data["rule_type"] == "all"
    assert data["count"] == 2
    types = {r["rule_type"] for r in data["rules"]}
    assert types == {"keyword", "sql"}


def test_alarm_rules_list_keyword_only(lts_settings, mock_lts_client):
    kw_resp = MagicMock()
    kw_resp.keywords_alarm_rules = [_fake_keyword_rule()]
    mock_lts_client.list_keywords_alarm_rules.return_value = kw_resp

    tools = make_alarm_tools(lts_settings)
    out = tools["lts_query_alarm_rules"](rule_type="keyword")
    assert out["ok"] is True
    assert out["data"]["count"] == 1
    assert out["data"]["rules"][0]["rule_type"] == "keyword"
    mock_lts_client.list_sql_alarm_rules.assert_not_called()


# ============================================================
# lts_query_alarm_rules — DETAIL mode
# ============================================================
def test_alarm_rules_detail_requires_type(lts_settings, mock_lts_client):
    tools = make_alarm_tools(lts_settings)
    out = tools["lts_query_alarm_rules"](rule_id=RID_KW)  # default rule_type=all
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_lts_client.list_keywords_alarm_rules.assert_not_called()


def test_alarm_rules_detail_keyword(lts_settings, mock_lts_client):
    kw_resp = MagicMock()
    kw_resp.keywords_alarm_rules = [
        _fake_keyword_rule(rid=RID_KW),
        _fake_keyword_rule(rid="other-id-aaaaaaaaaaaaaaaaaaa"),
    ]
    mock_lts_client.list_keywords_alarm_rules.return_value = kw_resp

    tools = make_alarm_tools(lts_settings)
    out = tools["lts_query_alarm_rules"](rule_id=RID_KW, rule_type="keyword")
    assert out["ok"] is True
    data = out["data"]
    assert data["mode"] == "detail"
    assert data["rule_type"] == "keyword"
    assert data["rule"]["rule_id"] == RID_KW
    # detail fields present
    assert data["rule"]["frequency"]["type"] == "HOURLY"
    assert data["rule"]["keywords_requests"][0]["keywords"] == "ERROR"


def test_alarm_rules_detail_sql(lts_settings, mock_lts_client):
    sql_resp = MagicMock()
    sql_resp.sql_alarm_rules = [_fake_sql_rule(rid=RID_SQL)]
    mock_lts_client.list_sql_alarm_rules.return_value = sql_resp

    tools = make_alarm_tools(lts_settings)
    out = tools["lts_query_alarm_rules"](rule_id=RID_SQL, rule_type="sql")
    assert out["ok"] is True
    assert out["data"]["rule_type"] == "sql"
    assert out["data"]["rule"]["sql_requests"][0]["sql"].startswith("SELECT")
    mock_lts_client.list_keywords_alarm_rules.assert_not_called()


def test_alarm_rules_detail_not_found(lts_settings, mock_lts_client):
    sql_resp = MagicMock()
    sql_resp.sql_alarm_rules = [_fake_sql_rule(rid="other-id-aaaaaaaaaaaaaaaaaaa")]
    mock_lts_client.list_sql_alarm_rules.return_value = sql_resp

    tools = make_alarm_tools(lts_settings)
    out = tools["lts_query_alarm_rules"](rule_id=RID_SQL, rule_type="sql")
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"


# ============================================================
# lts_list_alarm_history
# ============================================================
def _fake_event(eid="evt-1", severity="Critical"):
    md = SimpleNamespace(
        event_type="alarm",
        event_id=eid,
        event_severity=severity,
        event_name="High Error Rate",
        resource_type="LTS::LogStream",
        resource_id="sid",
        resource_provider="LTS",
        lts_alarm_type="KEYWORDS",
        log_group_name="grp",
        log_stream_name="strm",
        event_subtype=None,
    )
    ann = SimpleNamespace(
        message="500 errors > 10 in 5m",
        log_info=None,
        current_value="42",
        old_annotations=None,
        alarm_action_rule_name="action-1",
        alarm_rule_alias=None,
        alarm_rule_url="https://example.com/rule/1",
        alarm_status="alarm",
        condition_expression="count > 10",
        condition_expression_with_value="42 > 10",
        notification_frequency=15,
        record_id="rec-1",
        recovery_policy=3,
        results=None,
        frequency=None,
        type="keyword",
    )
    return SimpleNamespace(
        annotations=ann,
        metadata=md,
        arrives_at=1700000005000,
        ends_at=None,
        id=eid,
        starts_at=1700000000000,
        timeout=300,
        type="alarm",
    )


def test_list_alarm_history_active(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.events = [_fake_event(), _fake_event(eid="evt-2", severity="Major")]
    resp.page_info = SimpleNamespace(next_marker="cursor-x", previous_marker=None,
                                      current_count=2)
    mock_lts_client.list_active_or_history_alarms.return_value = resp

    tools = make_alarm_tools(lts_settings)
    out = tools["lts_list_alarm_history"](
        state="active", alarm_level="Critical", search="500", limit=20
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["state"] == "active"
    assert data["total_returned"] == 2
    assert data["next_marker"] == "cursor-x"
    e = data["events"][0]
    assert e["event_id"] == "evt-1"
    assert e["event_severity"] == "Critical"
    assert e["message"] == "500 errors > 10 in 5m"
    assert e["log_group_name"] == "grp"
    sent = mock_lts_client.list_active_or_history_alarms.call_args[0][0]
    assert sent.type == "active"
    assert sent.limit == 20
    # alarm_level mapped to id 1 (Critical)
    assert sent.body.alarm_level_ids == [1]
    assert sent.body.search == "500"


def test_list_alarm_history_invalid_state(lts_settings, mock_lts_client):
    tools = make_alarm_tools(lts_settings)
    out = tools["lts_list_alarm_history"](state="bogus")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_PARAMS"
    mock_lts_client.list_active_or_history_alarms.assert_not_called()


def test_list_alarm_history_bad_time_range(lts_settings, mock_lts_client):
    tools = make_alarm_tools(lts_settings)
    out = tools["lts_list_alarm_history"](
        start_time="2026-06-20 22:00:00",
        end_time="2026-06-20 21:00:00",
    )
    assert out["ok"] is False
    assert out["error"]["code"] == "TIME_RANGE_INVALID"


def test_list_alarm_history_history_state(lts_settings, mock_lts_client):
    resp = MagicMock()
    resp.events = []
    resp.page_info = None
    mock_lts_client.list_active_or_history_alarms.return_value = resp

    tools = make_alarm_tools(lts_settings)
    out = tools["lts_list_alarm_history"](state="history")
    assert out["ok"] is True
    assert out["data"]["state"] == "history"
    assert out["data"]["next_marker"] is None
    sent = mock_lts_client.list_active_or_history_alarms.call_args[0][0]
    assert sent.type == "history"
