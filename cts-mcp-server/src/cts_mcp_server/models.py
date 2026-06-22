"""Pydantic input models for MCP tools.

These models are used with FastMCP's tool registration so that FastMCP
emits a JSON Schema for each tool to clients (Hermes / Claude Desktop).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .time_utils import (
    SEVEN_DAY_TOLERANCE_MS,
    SEVEN_DAYS_MS,
    human_to_epoch_ms,
    now_ms,
)


_TIME_HELP = (
    "Accepted formats: ISO8601 with offset (e.g. '2026-06-20T22:00:00+08:00'), "
    "'YYYY-MM-DD HH:MM:SS' (interpreted in CTS_DEFAULT_TIMEZONE, default "
    "Asia/Shanghai), or relative '-Nh'/'-Nd' (e.g. '-1h' = one hour ago)."
)


class SearchTracesInput(BaseModel):
    """Input model for ``cts_search_traces``.

    CTS only retains 7 days of trace data on this API. Time-range validation
    is enforced via ``model_validator(mode='after')`` so a request that
    reaches into older history fails BEFORE any SDK call is issued.
    """

    start_time: Optional[str] = Field(
        default=None,
        description=(
            "Start of the search window (inclusive). " + _TIME_HELP +
            " Defaults to 'now - 1h' if omitted."
        ),
    )
    end_time: Optional[str] = Field(
        default=None,
        description=(
            "End of the search window (exclusive). " + _TIME_HELP +
            " Defaults to current time if omitted."
        ),
    )
    service_type: Optional[str] = Field(
        default=None,
        description=(
            "Filter by Huawei Cloud service abbreviation in UPPERCASE: e.g. "
            "ECS, OBS, VPC, IAM, EVS, ELB, CCE, RDS. Only effective when "
            "trace_type='system'."
        ),
    )
    user: Optional[str] = Field(
        default=None,
        description=(
            "Filter by the operating user's name (matches user.user_name in "
            "the trace). Only effective when trace_type='system'."
        ),
    )
    trace_rating: Optional[Literal["normal", "warning", "incident"]] = Field(
        default=None,
        description=(
            "Filter by event severity: 'normal' (informational), 'warning' "
            "(minor anomaly), 'incident' (security/availability incident)."
        ),
    )
    trace_type: Literal["system", "data"] = Field(
        default="system",
        description=(
            "'system' = management-plane events (control operations, IAM, "
            "API calls; the default). 'data' = data-plane events (e.g. OBS "
            "object access). Most filter fields (service_type, user, "
            "resource_*) ONLY apply when trace_type='system'."
        ),
    )
    trace_name: Optional[str] = Field(
        default=None,
        description="Exact event name, e.g. 'deleteEip', 'createServer'.",
    )
    resource_type: Optional[str] = Field(
        default=None,
        description="Filter by resource type (system events only).",
    )
    resource_name: Optional[str] = Field(
        default=None,
        description="Filter by resource name (system events only).",
    )
    resource_id: Optional[str] = Field(
        default=None,
        description="Filter by resource id (system events only).",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=200,
        description="Page size. CTS default is 10; max is 200.",
    )
    next_marker: Optional[str] = Field(
        default=None,
        description=(
            "Pagination cursor — pass the 'next_marker' value from a "
            "previous response. CTS uses cursor-based pagination, not "
            "offset-based; do NOT compute it yourself."
        ),
    )
    auto_paginate: bool = Field(
        default=False,
        description=(
            "If true, the tool loops through marker pages internally and "
            "merges results until either marker becomes empty or "
            "max_results is reached."
        ),
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=2000,
        description=(
            "Cap on total merged rows when auto_paginate=true. Protects "
            "against accidentally pulling tens of thousands of traces into "
            "the LLM context."
        ),
    )

    # Computed during validation, exposed via attributes for the tool body.
    _from_ms: Optional[int] = None
    _to_ms: Optional[int] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _validate(self) -> "SearchTracesInput":
        # The default-timezone for parsing is *only* known at runtime; the
        # tool body re-parses with the real default tz if it's been set in
        # env (see search.py). Here we just sanity-check parseability.
        # Concrete 7-day check happens in the tool body where the
        # configured timezone is available.
        return self


class GetTraceDetailInput(BaseModel):
    """Input model for ``cts_get_trace_detail``.

    CTS ListTraces returns ONLY the specified trace when ``trace_id`` is
    passed — all other filter conditions are silently ignored by the API.
    This is documented Huawei Cloud behaviour, not a bug; this tool
    therefore only exposes ``trace_id`` and ``trace_type``.
    """

    trace_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="The trace_id returned by cts_search_traces.",
    )
    trace_type: Literal["system", "data"] = Field(
        default="system",
        description=(
            "Must match the trace_type used at search time. Use 'system' "
            "for management-plane events (default), 'data' for data events."
        ),
    )

    model_config = {"extra": "forbid"}


# --- Helper: shared time-range resolution -----------------------------------

def resolve_time_range(
    start_time: Optional[str],
    end_time: Optional[str],
    default_tz: str,
) -> tuple[int, int]:
    """Resolve a (from_ms, to_ms) pair from the user's input, applying
    sensible defaults and enforcing the 7-day window.

    Raises:
        ValueError with a user-friendly message on:
          * unparseable input
          * start >= end
          * start older than 'now - 7d - 5min' (TIME_RANGE_TOO_OLD)
    """
    now = now_ms()
    to_ms = human_to_epoch_ms(end_time, default_tz) if end_time else now
    from_ms = (
        human_to_epoch_ms(start_time, default_tz)
        if start_time
        else (now - 3600_000)  # one hour ago, matching CTS default behaviour
    )

    if from_ms >= to_ms:
        raise ValueError(
            f"start_time ({from_ms}) must be strictly earlier than end_time "
            f"({to_ms}) — CTS uses a half-open interval [from, to)."
        )

    floor = now - SEVEN_DAYS_MS - SEVEN_DAY_TOLERANCE_MS
    if from_ms < floor:
        raise ValueError(
            "CTS ListTraces only retains the last 7 days of audit events. "
            "Your start_time falls outside that window. For older history, "
            "use the OBS bucket configured on the CTS tracker (CTS console → "
            "Tracker → Object Storage), or narrow start_time to within the "
            "last 7 days."
        )

    return from_ms, to_ms
