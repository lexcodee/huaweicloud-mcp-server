"""Compact JSON-serialisers for LTS SDK objects.

Same two-tier strategy as CCE / ECS:
- ``*_summary`` — minimal fields for list views (token-efficient)
- ``*_detail`` — full operational info for single-resource fetches

``_drop_nulls`` removes None/empty values so the LLM doesn't waste tokens
on absent fields.
"""
from __future__ import annotations

from typing import Any


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _drop_nulls(d: dict) -> dict:
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != [] and v != {} and v != ""
    }


# ---------------------------------------------------------------------------
# Log groups & streams
# ---------------------------------------------------------------------------
def log_group_summary(g: Any) -> dict:
    return _drop_nulls(
        {
            "id": _get(g, "log_group_id"),
            "name": _get(g, "log_group_name"),
            "alias": _get(g, "log_group_name_alias"),
            "ttl_in_days": _get(g, "ttl_in_days"),
            "created": _get(g, "creation_time"),
            "tag": _get(g, "tag"),
        }
    )


def log_stream_summary(s: Any) -> dict:
    return _drop_nulls(
        {
            "id": _get(s, "log_stream_id"),
            "name": _get(s, "log_stream_name"),
            "alias": _get(s, "log_stream_name_alias"),
            "log_group_id": _get(s, "log_group_id"),
            "ttl_in_days": _get(s, "ttl_in_days"),
            "hot_storage_days": _get(s, "hot_storage_days"),
            "filter_count": _get(s, "filter_count"),
            "whether_log_storage": _get(s, "whether_log_storage"),
            "created": _get(s, "creation_time"),
            "tag": _get(s, "tag"),
        }
    )


# ---------------------------------------------------------------------------
# Log entries (search / context)
# ---------------------------------------------------------------------------
def log_entry(item: Any, *, content_limit: int = 2000) -> dict:
    """Compact one ``LogContents`` item.

    LTS returns each log as ``{content, line_num, labels}``. We trim
    overly long content so a single huge stack trace can't blow the
    response budget; the LLM can re-fetch with smaller windows if needed.
    """
    content = _get(item, "content")
    truncated = False
    if isinstance(content, str) and len(content) > content_limit:
        content = content[:content_limit]
        truncated = True
    out = _drop_nulls(
        {
            "line_num": _get(item, "line_num"),
            "content": content,
            "labels": _get(item, "labels") or {},
        }
    )
    if truncated:
        out["truncated"] = True
    return out


# ---------------------------------------------------------------------------
# Alarm rules
# ---------------------------------------------------------------------------
def keyword_alarm_rule_summary(r: Any) -> dict:
    """Summarise a keyword-alarm rule (list-view)."""
    return _drop_nulls(
        {
            "rule_id": _get(r, "keywords_alarm_rule_id"),
            "rule_type": "keyword",
            "name": _get(r, "keywords_alarm_rule_name"),
            "alias": _get(r, "alarm_rule_alias"),
            "description": _get(r, "keywords_alarm_rule_description"),
            "level": _get(r, "keywords_alarm_level"),
            "status": _get(r, "status"),
            "trigger_condition_count": _get(r, "trigger_condition_count"),
            "trigger_condition_frequency": _get(r, "trigger_condition_frequency"),
            "create_time": _get(r, "create_time"),
            "update_time": _get(r, "update_time"),
        }
    )


def keyword_alarm_rule_detail(r: Any) -> dict:
    """Full detail of a keyword-alarm rule."""
    base = keyword_alarm_rule_summary(r)
    freq = _get(r, "frequency")
    recovery = _get(r, "recovery_policy")
    requests = _get(r, "keywords_requests") or []
    requests_out = []
    for kr in requests:
        requests_out.append(
            _drop_nulls(
                {
                    "keywords": _get(kr, "keywords"),
                    "condition": _get(kr, "condition"),
                    "number": _get(kr, "number"),
                    "log_group_id": _get(kr, "log_group_id"),
                    "log_stream_id": _get(kr, "log_stream_id"),
                    "search_time_range_unit": _get(kr, "search_time_range_unit"),
                    "search_time_range": _get(kr, "search_time_range"),
                    "log_group_name": _get(kr, "log_group_name"),
                    "log_stream_name": _get(kr, "log_stream_name"),
                    "whether_global": _get(kr, "whether_global"),
                    "expression": _get(kr, "expression"),
                }
            )
        )
    base.update(
        _drop_nulls(
            {
                "condition_expression": _get(r, "condition_expression"),
                "frequency": _drop_nulls(
                    {
                        "type": _get(freq, "type"),
                        "cron_expr": _get(freq, "cron_expr"),
                        "hour_of_day": _get(freq, "hour_of_day"),
                        "day_of_week": _get(freq, "day_of_week"),
                        "fixed_rate": _get(freq, "fixed_rate"),
                        "fixed_rate_unit": _get(freq, "fixed_rate_unit"),
                    }
                ) if freq else None,
                "notification_frequency": _get(r, "notification_frequency"),
                "alarm_action_rule_name": _get(r, "alarm_action_rule_name"),
                "whether_recovery_policy": _get(r, "whether_recovery_policy"),
                "recovery_policy": recovery,
                "keywords_requests": requests_out,
                "tags": _get(r, "tags"),
            }
        )
    )
    return base


def sql_alarm_rule_summary(r: Any) -> dict:
    """Summarise a SQL-alarm rule (list-view)."""
    return _drop_nulls(
        {
            "rule_id": _get(r, "sql_alarm_rule_id"),
            "rule_type": "sql",
            "name": _get(r, "sql_alarm_rule_name"),
            "alias": _get(r, "alarm_rule_alias"),
            "description": _get(r, "sql_alarm_rule_description"),
            "level": _get(r, "sql_alarm_level"),
            "status": _get(r, "status"),
            "trigger_condition_count": _get(r, "trigger_condition_count"),
            "trigger_condition_frequency": _get(r, "trigger_condition_frequency"),
            "create_time": _get(r, "create_time"),
            "update_time": _get(r, "update_time"),
        }
    )


def sql_alarm_rule_detail(r: Any) -> dict:
    """Full detail of a SQL-alarm rule."""
    base = sql_alarm_rule_summary(r)
    freq = _get(r, "frequency")
    requests = _get(r, "sql_requests") or []
    requests_out = []
    for sr in requests:
        requests_out.append(
            _drop_nulls(
                {
                    "sql": _get(sr, "sql"),
                    "log_group_id": _get(sr, "log_group_id"),
                    "log_stream_id": _get(sr, "log_stream_id"),
                    "search_time_range_unit": _get(sr, "search_time_range_unit"),
                    "search_time_range": _get(sr, "search_time_range"),
                    "title": _get(sr, "title"),
                    "log_group_name": _get(sr, "log_group_name"),
                    "log_stream_name": _get(sr, "log_stream_name"),
                    "sql_request_id": _get(sr, "sql_request_id"),
                }
            )
        )
    base.update(
        _drop_nulls(
            {
                "is_css_sql": _get(r, "is_css_sql"),
                "condition_expression": _get(r, "condition_expression"),
                "frequency": _drop_nulls(
                    {
                        "type": _get(freq, "type"),
                        "cron_expr": _get(freq, "cron_expr"),
                        "hour_of_day": _get(freq, "hour_of_day"),
                        "day_of_week": _get(freq, "day_of_week"),
                        "fixed_rate": _get(freq, "fixed_rate"),
                        "fixed_rate_unit": _get(freq, "fixed_rate_unit"),
                    }
                ) if freq else None,
                "notification_frequency": _get(r, "notification_frequency"),
                "alarm_action_rule_name": _get(r, "alarm_action_rule_name"),
                "whether_recovery_policy": _get(r, "whether_recovery_policy"),
                "recovery_policy": _get(r, "recovery_policy"),
                "sql_requests": requests_out,
                "topics": _get(r, "topics"),
                "tags": _get(r, "tags"),
            }
        )
    )
    return base


# ---------------------------------------------------------------------------
# Alarm history events (notifications)
# ---------------------------------------------------------------------------
def alarm_event_summary(e: Any) -> dict:
    """Summarise an alarm event from list_active_or_history_alarms.

    Each LTS Event has ``metadata`` (resource/severity), ``annotations``
    (alarm rule + message + condition), and timestamps. We flatten the
    most useful fields for triage.
    """
    md = _get(e, "metadata")
    ann = _get(e, "annotations")
    return _drop_nulls(
        {
            "event_id": _get(e, "id"),
            "starts_at": _get(e, "starts_at"),
            "ends_at": _get(e, "ends_at"),
            "arrives_at": _get(e, "arrives_at"),
            "timeout": _get(e, "timeout"),
            "type": _get(e, "type"),
            # Metadata block — what fired
            "event_name": _get(md, "event_name"),
            "event_severity": _get(md, "event_severity"),
            "event_type": _get(md, "event_type"),
            "event_subtype": _get(md, "event_subtype"),
            "lts_alarm_type": _get(md, "lts_alarm_type"),
            "log_group_name": _get(md, "log_group_name"),
            "log_stream_name": _get(md, "log_stream_name"),
            "resource_type": _get(md, "resource_type"),
            "resource_id": _get(md, "resource_id"),
            "resource_provider": _get(md, "resource_provider"),
            # Annotations block — why it fired
            "alarm_rule_alias": _get(ann, "alarm_rule_alias"),
            "alarm_action_rule_name": _get(ann, "alarm_action_rule_name"),
            "alarm_status": _get(ann, "alarm_status"),
            "condition_expression": _get(ann, "condition_expression"),
            "condition_expression_with_value": _get(ann, "condition_expression_with_value"),
            "current_value": _get(ann, "current_value"),
            "message": _get(ann, "message"),
            "notification_frequency": _get(ann, "notification_frequency"),
            "type_detail": _get(ann, "type"),
            "alarm_rule_url": _get(ann, "alarm_rule_url"),
            "record_id": _get(ann, "record_id"),
        }
    )
