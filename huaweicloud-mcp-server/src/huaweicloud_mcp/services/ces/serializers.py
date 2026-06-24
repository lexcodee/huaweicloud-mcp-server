"""Compact JSON-serialisers for CES SDK objects.

Two-tier strategy mirrors the CCE / LTS modules:
- ``*_summary`` — minimal fields for list views (token-efficient).
- ``*_detail`` — full operational info for single-resource fetches.

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
# Metric (v1 ListMetricsResponse.metrics items)
# ---------------------------------------------------------------------------
def metric_summary(m: Any) -> dict:
    """List-view metric item from v1 ListMetrics."""
    dims = _get(m, "dimensions") or []
    dims_out = [
        _drop_nulls({"name": _get(d, "name"), "value": _get(d, "value")})
        for d in dims
    ]
    return _drop_nulls(
        {
            "namespace": _get(m, "namespace"),
            "metric_name": _get(m, "metric_name"),
            "unit": _get(m, "unit"),
            "dimensions": dims_out,
        }
    )


# ---------------------------------------------------------------------------
# Metric data point (v2 MetricDataPoint)
# ---------------------------------------------------------------------------
def metric_data_point(dp: Any) -> dict:
    """Single data point from v2 BatchListSpecifiedMetricData."""
    dims = _get(dp, "dimensions") or []
    dims_out = [
        _drop_nulls({"name": _get(d, "name"), "value": _get(d, "value")})
        for d in dims
    ]
    return _drop_nulls(
        {
            "timestamp": _get(dp, "timestamp"),
            "value": _get(dp, "value"),
            "unit": _get(dp, "unit"),
            "dimensions": dims_out,
        }
    )


# ---------------------------------------------------------------------------
# Metric data point (v1 Datapoint from ShowMetricData)
# ---------------------------------------------------------------------------
def metric_data_point_v1(dp: Any, filter: str = "average") -> dict:
    """Single data point from v1 ShowMetricData.

    The v1 Datapoint has separate fields per aggregation (average, max,
    min, sum, variance).  We pick the one matching the requested filter
    as the primary ``value``, and include the others as extras.
    """
    value = _get(dp, filter)
    extras: dict = {}
    for agg in ("average", "max", "min", "sum", "variance"):
        v = _get(dp, agg)
        if v is not None and agg != filter:
            extras[agg] = v
    return _drop_nulls(
        {
            "timestamp": _get(dp, "timestamp"),
            "value": value,
            "unit": _get(dp, "unit"),
            **extras,
        }
    )


# ---------------------------------------------------------------------------
# Alarm rule (v2 ListAlarmRespBodyAlarms)
# ---------------------------------------------------------------------------
def alarm_rule_summary(a: Any) -> dict:
    """List-view alarm rule."""
    alarm_type = _get(a, "type")
    # AlarmTypeResp is an object with enum attributes
    type_str = None
    if alarm_type is not None:
        for attr in (
            "ALL_INSTANCE",
            "MULTI_INSTANCE",
            "RESOURCE_GROUP",
            "EVENT_SYS",
            "EVENT_CUSTOM",
            "DNSHEALTHCHECK",
        ):
            if getattr(alarm_type, attr, None) is not None:
                type_str = attr
                break
    return _drop_nulls(
        {
            "alarm_id": _get(a, "alarm_id"),
            "name": _get(a, "name"),
            "description": _get(a, "description"),
            "namespace": _get(a, "namespace"),
            "type": type_str,
            "enabled": _get(a, "enabled"),
            "notification_enabled": _get(a, "notification_enabled"),
            "alarm_template_id": _get(a, "alarm_template_id"),
        }
    )


def _policy_summary(p: Any) -> dict:
    """Compact alarm policy."""
    hierarchical = _get(p, "hierarchical_value")
    return _drop_nulls(
        {
            "metric_name": _get(p, "metric_name"),
            "namespace": _get(p, "namespace"),
            "period": _get(p, "period"),
            "filter": _get(p, "filter"),
            "comparison_operator": _get(p, "comparison_operator"),
            "value": _get(p, "value"),
            "count": _get(p, "count"),
            "unit": _get(p, "unit"),
            "level": _get(p, "level"),
            "suppress_duration": _get(p, "suppress_duration"),
            "hierarchical_value": _drop_nulls(
                {
                    "enabled": _get(hierarchical, "enabled"),
                    "level": _get(hierarchical, "level"),
                }
            )
            if hierarchical
            else None,
        }
    )


def _notification_summary(n: Any) -> dict:
    """Compact notification."""
    return _drop_nulls(
        {
            "type": _get(n, "type"),
            "notification_list": _get(n, "notification_list"),
        }
    )


def _resource_summary(r: Any) -> dict:
    """Compact resource in alarm rule."""
    dims = _get(r, "dimensions") or []
    dims_out = [
        _drop_nulls({"name": _get(d, "name"), "value": _get(d, "value")})
        for d in dims
    ]
    return _drop_nulls(
        {
            "resource_group_id": _get(r, "resource_group_id"),
            "resource_group_name": _get(r, "resource_group_name"),
            "dimensions": dims_out,
        }
    )


def alarm_rule_detail(a: Any, policies: list[Any] | None = None, resources: list[Any] | None = None) -> dict:
    """Full alarm rule detail including policies and resources."""
    base = alarm_rule_summary(a)

    policies_out = [_policy_summary(p) for p in (policies or [])]
    alarm_notifs = [_notification_summary(n) for n in (_get(a, "alarm_notifications") or [])]
    ok_notifs = [_notification_summary(n) for n in (_get(a, "ok_notifications") or [])]
    resources_out = [_resource_summary(r) for r in (resources or [])]

    extras = _drop_nulls(
        {
            "notification_begin_time": _get(a, "notification_begin_time"),
            "notification_end_time": _get(a, "notification_end_time"),
            "effective_timezone": _get(a, "effective_timezone"),
            "enterprise_project_id": _get(a, "enterprise_project_id"),
            "product_name": _get(a, "product_name"),
            "resource_level": _get(a, "resource_level"),
            "policies": policies_out,
            "alarm_notifications": alarm_notifs,
            "ok_notifications": ok_notifs,
            "resources": resources_out,
        }
    )
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Alarm history (v2 AlarmHistoryItemV2)
# ---------------------------------------------------------------------------
def alarm_history_summary(h: Any) -> dict:
    """Summarise an alarm history item."""
    metric = _get(h, "metric")
    condition = _get(h, "condition")
    additional = _get(h, "additional_info")

    metric_out = None
    if metric:
        dims = _get(metric, "dimensions") or []
        dims_out = [
            _drop_nulls({"name": _get(d, "name"), "value": _get(d, "value")})
            for d in dims
        ]
        metric_out = _drop_nulls(
            {
                "namespace": _get(metric, "namespace"),
                "metric_name": _get(metric, "metric_name"),
                "dimensions": dims_out,
            }
        )

    condition_out = None
    if condition:
        condition_out = _drop_nulls(
            {
                "comparison_operator": _get(condition, "comparison_operator"),
                "value": _get(condition, "value"),
                "count": _get(condition, "count"),
                "filter": _get(condition, "filter"),
                "period": _get(condition, "period"),
                "unit": _get(condition, "unit"),
                "suppress_duration": _get(condition, "suppress_duration"),
            }
        )

    additional_out = None
    if additional:
        additional_out = _drop_nulls(
            {
                "event_id": _get(additional, "event_id"),
                "resource_id": _get(additional, "resource_id"),
                "resource_name": _get(additional, "resource_name"),
            }
        )

    return _drop_nulls(
        {
            "record_id": _get(h, "record_id"),
            "alarm_id": _get(h, "alarm_id"),
            "name": _get(h, "name"),
            "status": _get(h, "status"),
            "level": _get(h, "level"),
            "type": _get(h, "type"),
            "action_enabled": _get(h, "action_enabled"),
            "begin_time": str(_get(h, "begin_time")) if _get(h, "begin_time") else None,
            "end_time": str(_get(h, "end_time")) if _get(h, "end_time") else None,
            "first_alarm_time": str(_get(h, "first_alarm_time")) if _get(h, "first_alarm_time") else None,
            "last_alarm_time": str(_get(h, "last_alarm_time")) if _get(h, "last_alarm_time") else None,
            "alarm_recovery_time": str(_get(h, "alarm_recovery_time")) if _get(h, "alarm_recovery_time") else None,
            "metric": metric_out,
            "condition": condition_out,
            "additional_info": additional_out,
        }
    )


# ---------------------------------------------------------------------------
# Resource group (v2 OneResourceGroupResp / ShowResourceGroupResponse)
# ---------------------------------------------------------------------------
def resource_group_summary(g: Any) -> dict:
    """List-view resource group."""
    return _drop_nulls(
        {
            "group_id": _get(g, "group_id"),
            "group_name": _get(g, "group_name"),
            "type": _get(g, "type"),
            "status": _get(g, "status"),
            "create_time": _get(g, "create_time"),
            "update_time": _get(g, "update_time"),
            "enterprise_project_id": _get(g, "enterprise_project_id"),
        }
    )


def resource_group_detail(g: Any, resources: list[Any] | None = None) -> dict:
    """Full resource group detail including resources."""
    base = resource_group_summary(g)

    resources_out = []
    for r in resources or []:
        dims = _get(r, "dimensions") or []
        dims_out = [
            _drop_nulls({"name": _get(d, "name"), "value": _get(d, "value")})
            for d in dims
        ]
        resources_out.append(
            _drop_nulls(
                {
                    "resource_name": _get(r, "resource_name"),
                    "status": _get(r, "status"),
                    "event_status": _get(r, "event_status"),
                    "enterprise_project_id": _get(r, "enterprise_project_id"),
                    "dimensions": dims_out,
                    "tags": _get(r, "tags"),
                }
            )
        )

    extras = _drop_nulls(
        {
            "association_alarm_templates": _get(g, "association_alarm_templates"),
            "product_names": _get(g, "product_names"),
            "resource_level": _get(g, "resource_level"),
            "tags": _get(g, "tags"),
            "resources": resources_out,
        }
    )
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Event data (v1 EventInfo / EventInfoDetailResp)
# ---------------------------------------------------------------------------
def event_summary(e: Any) -> dict:
    """List-view event item from v1 ListEvents."""
    return _drop_nulls(
        {
            "event_name": _get(e, "event_name"),
            "event_type": _get(e, "event_type"),
            "sub_event_type": _get(e, "sub_event_type"),
            "event_count": _get(e, "event_count"),
            "latest_event_source": _get(e, "latest_event_source"),
            "latest_occur_time": _get(e, "latest_occur_time"),
        }
    )


def event_detail(e: Any) -> dict:
    """Full event detail from v1 ListEventDetail."""
    event_info = _get(e, "event_info")
    return _drop_nulls(
        {
            "event_name": _get(e, "event_name"),
            "event_type": _get(e, "event_type"),
            "sub_event_type": _get(e, "sub_event_type"),
            "event_sources": _get(e, "event_sources"),
            "event_users": _get(e, "event_users"),
            "event_info": _drop_nulls(
                {
                    "event_count": _get(event_info, "event_count"),
                    "event_name": _get(event_info, "event_name"),
                    "event_type": _get(event_info, "event_type"),
                    "latest_event_source": _get(event_info, "latest_event_source"),
                    "latest_occur_time": _get(event_info, "latest_occur_time"),
                    "sub_event_type": _get(event_info, "sub_event_type"),
                }
            )
            if event_info
            else None,
        }
    )
