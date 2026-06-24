"""Pydantic input models for CES MCP tools.

CES uses two SDK versions:
  - v1: list_metrics, show_metric_data, list_events, list_event_detail
  - v2: batch_list_specified_metric_data, list_alarm_rules,
        list_alarm_histories, list_resource_groups, show_resource_group

Tools follow the project's list/detail dispatch pattern where applicable.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ces_list_metrics — v1 ListMetricsRequest
# ---------------------------------------------------------------------------
class ListMetricsInput(BaseModel):
    namespace: Optional[str] = Field(
        default=None,
        description=(
            "Service namespace, e.g. 'SYS.ECS'. When set, only metrics "
            "for that service are returned. When None, returns all."
        ),
    )
    metric_name: Optional[str] = Field(
        default=None,
        description="Metric name filter, e.g. 'cpu_util'.",
    )
    dim_0: Optional[str] = Field(
        default=None,
        description=(
            "First dimension filter, format: 'key,value' "
            "e.g. 'instance_id,6f3c6f91-4b24-4e1b-b7d1-a94ac1cb011d'."
        ),
    )
    dim_1: Optional[str] = Field(
        default=None,
        description="Second dimension filter (same format as dim_0).",
    )
    dim_2: Optional[str] = Field(
        default=None,
        description="Third dimension filter (same format as dim_0).",
    )
    start: Optional[str] = Field(
        default=None,
        description="Pagination cursor from a previous response.",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=1000,
        description="Page size (1..1000).",
    )


# ---------------------------------------------------------------------------
# ces_get_metric_data — v2 BatchListSpecifiedMetricData
# ---------------------------------------------------------------------------
class MetricSpec(BaseModel):
    """A single metric specification for batch query."""

    namespace: str = Field(
        ..., description="Service namespace, e.g. 'SYS.ECS'."
    )
    metric_name: str = Field(
        ..., description="Metric name, e.g. 'cpu_util'."
    )
    dimensions: str = Field(
        default="",
        description=(
            "Resource dimensions, comma-separated 'name,value' pairs. "
            "e.g. 'instance_id,abc123' or multi-dim "
            "'instance_id,abc123,process_name,sshd'. "
            "Leave empty for ALL_INSTANCE type queries."
        ),
    )


class GetMetricDataInput(BaseModel):
    metrics: list[MetricSpec] = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "List of metric specs to query. Each item: "
            "{namespace, metric_name, dimensions}. Max 500 items."
        ),
    )
    from_time: Optional[str] = Field(
        default=None,
        description=(
            "Inclusive start of the query window. Accepts '-1h', '-30m', "
            "ISO8601, 'YYYY-MM-DD HH:MM:SS', or 13-digit epoch ms. "
            "Default '-5m' (CES requires from-to interval <= 5 min for "
            "raw data; the tool auto-chunks larger windows)."
        ),
    )
    to_time: Optional[str] = Field(
        default=None,
        description="Exclusive end of the query window. Default 'now'.",
    )
    period: Optional[int] = Field(
        default=None,
        description=(
            "Aggregation period in seconds. "
            "1=original, 300=5min, 1200=20min, 3600=1h, 14400=4h, 86400=1d. "
            "Default: 1 (original sampling period)."
        ),
    )
    filter: Literal["average", "max", "min", "sum", "variance"] = Field(
        default="average",
        description="Aggregation function.",
    )


# ---------------------------------------------------------------------------
# ces_query_alarm_rules — v2 ListAlarmRules + policies + resources
# ---------------------------------------------------------------------------
class QueryAlarmRulesInput(BaseModel):
    alarm_id: Optional[str] = Field(
        default=None,
        description=(
            "Alarm rule id. If None/empty, returns the LIST of alarm rules. "
            "If set, returns DETAIL for that single rule (including "
            "policies and associated resources)."
        ),
    )
    namespace: Optional[str] = Field(
        default=None,
        description="List-mode filter: namespace, e.g. 'SYS.ECS'.",
    )
    name: Optional[str] = Field(
        default=None,
        description="List-mode filter: alarm rule name (fuzzy match).",
    )
    status: Optional[str] = Field(
        default=None,
        description="List-mode filter: alarm status (ok/alarm/invalid).",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (1..100).",
    )
    offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Page offset.",
    )


# ---------------------------------------------------------------------------
# ces_list_alarm_histories — v2 ListAlarmHistories
# ---------------------------------------------------------------------------
class ListAlarmHistoriesInput(BaseModel):
    alarm_id: Optional[str] = Field(
        default=None,
        description="Filter by alarm rule id.",
    )
    status: Optional[str] = Field(
        default=None,
        description="Filter by status: ok / alarm / invalid / insufficient_data.",
    )
    level: Optional[int] = Field(
        default=None,
        ge=1,
        le=4,
        description="Filter by severity: 1=Critical, 2=Major, 3=Minor, 4=Info.",
    )
    namespace: Optional[str] = Field(
        default=None,
        description="Filter by namespace, e.g. 'SYS.ECS'.",
    )
    name: Optional[str] = Field(
        default=None,
        description="Filter by alarm name (fuzzy match).",
    )
    from_time: Optional[str] = Field(
        default=None,
        description="Inclusive start. Default '-7d'.",
    )
    to_time: Optional[str] = Field(
        default=None,
        description="Exclusive end. Default 'now'.",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (1..100).",
    )
    offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Page offset.",
    )


# ---------------------------------------------------------------------------
# ces_query_resource_groups — v2 ListResourceGroups / ShowResourceGroup
# ---------------------------------------------------------------------------
class QueryResourceGroupsInput(BaseModel):
    group_id: Optional[str] = Field(
        default=None,
        description=(
            "Resource group id. If None/empty, returns the LIST of groups. "
            "If set, returns DETAIL for that group (including resources)."
        ),
    )
    group_name: Optional[str] = Field(
        default=None,
        description="List-mode filter: group name.",
    )
    status: Optional[str] = Field(
        default=None,
        description="List-mode filter: health status (health/unhealthy/no_alarm_rule).",
    )
    type: Optional[str] = Field(
        default=None,
        description="List-mode filter: group type (EPS/custom).",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (1..100).",
    )
    offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Page offset.",
    )


# ---------------------------------------------------------------------------
# ces_list_event_data — v1 ListEvents / ListEventDetail
# ---------------------------------------------------------------------------
class ListEventDataInput(BaseModel):
    event_name: Optional[str] = Field(
        default=None,
        description=(
            "Event name. If None/empty, returns the LIST of events. "
            "If set, returns DETAIL for that event."
        ),
    )
    event_type: Optional[Literal["EVENT.SYS", "EVENT.CUSTOM"]] = Field(
        default="EVENT.SYS",
        description="Event type: EVENT.SYS (system) or EVENT.CUSTOM (custom).",
    )
    sub_event_type: Optional[str] = Field(
        default=None,
        description="Event sub-type: SUB_EVENT.OPS / SUB_EVENT.PLAN / SUB_EVENT.CUSTOM.",
    )
    event_source: Optional[str] = Field(
        default=None,
        description="Detail-mode filter: event source (namespace), e.g. 'SYS.ECS'.",
    )
    event_level: Optional[Literal["Critical", "Major", "Minor", "Info"]] = Field(
        default=None,
        description="Detail-mode filter: event severity.",
    )
    event_state: Optional[Literal["normal", "warning", "incident"]] = Field(
        default=None,
        description="Detail-mode filter: event state.",
    )
    from_time: Optional[str] = Field(
        default=None,
        description="Inclusive start. Default '-1d'.",
    )
    to_time: Optional[str] = Field(
        default=None,
        description="Exclusive end. Default 'now'.",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (1..100).",
    )
    start: Optional[str] = Field(
        default=None,
        description="Pagination cursor from a previous response.",
    )
