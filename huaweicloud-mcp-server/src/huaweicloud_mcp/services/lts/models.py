"""Pydantic input models for LTS MCP tools.

LTS resource ids are 32-hex-char strings, sometimes with hyphens. We keep
validation lenient — Huawei Cloud's API will reject malformed ids with
its own precise error code.

Time fields accept the same humane shapes as CTS (``-1h``, ISO8601,
``YYYY-MM-DD HH:MM:SS``, naive strings interpreted in the configured
default timezone).
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# 16..64 hex/dash — same shape as CCE ids, matches LTS group/stream ids.
_ID_RE = re.compile(r"^[0-9a-fA-F\-]{16,64}$")

_RULE_TYPES = ("keyword", "sql")


def _check_id(v: str, field: str) -> str:
    if not _ID_RE.match(v):
        raise ValueError(f"{field} must be a 16..64 char hex/uuid string, got {v!r}")
    return v


# ---------------------------------------------------------------------------
# lts_query_log_resources — list groups, or list streams for one group
# ---------------------------------------------------------------------------
class QueryLogResourcesInput(BaseModel):
    log_group_id: Optional[str] = Field(
        default=None,
        description=(
            "Log group id. If None/empty, returns all log GROUPS in the "
            "project. If set, returns the STREAMS under that group."
        ),
    )

    @field_validator("log_group_id")
    @classmethod
    def _v_gid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _check_id(v, "log_group_id")


# ---------------------------------------------------------------------------
# lts_search_logs
# ---------------------------------------------------------------------------
class SearchLogsInput(BaseModel):
    log_group_id: str = Field(..., description="Log group id.")
    log_stream_id: str = Field(..., description="Log stream id within the group.")
    start_time: Optional[str] = Field(
        default=None,
        description=(
            "Inclusive start of the query window. Accepts '-1h', '-30m', "
            "'-2d', ISO8601 with offset, 'YYYY-MM-DD HH:MM:SS', or 13-digit "
            "epoch ms. Default '-1h'."
        ),
    )
    end_time: Optional[str] = Field(
        default=None,
        description="Exclusive end of the query window. Default 'now'.",
    )
    keywords: Optional[str] = Field(
        default=None,
        description=(
            "Whitespace-separated keywords. Each token is matched against "
            "the raw log line. Ignored when ``query`` is set."
        ),
    )
    query: Optional[str] = Field(
        default=None,
        description=(
            "Full LTS SQL/pipeline query string (e.g. "
            "`level:ERROR AND host:host-01 | stats count() by service`). "
            "When set, ``keywords`` is ignored and the call switches to "
            "structured mode."
        ),
    )
    labels: Optional[dict[str, str]] = Field(
        default=None,
        description=(
            "Equality filters on structured-log labels (e.g. "
            "{'level':'ERROR'}). Combined with AND."
        ),
    )
    is_desc: bool = Field(
        default=True,
        description="Sort by timestamp descending (newest first). Default True.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Page size (1..500). LTS default 50.",
    )
    line_num: Optional[str] = Field(
        default=None,
        description=(
            "Cursor token for pagination — pass the ``line_num`` of the "
            "boundary log returned in a previous response."
        ),
    )
    highlight: bool = Field(
        default=False,
        description="Ask LTS to wrap matched keywords in highlight markers.",
    )

    @field_validator("log_group_id")
    @classmethod
    def _v_gid(cls, v: str) -> str:
        return _check_id(v, "log_group_id")

    @field_validator("log_stream_id")
    @classmethod
    def _v_sid(cls, v: str) -> str:
        return _check_id(v, "log_stream_id")


# ---------------------------------------------------------------------------
# lts_get_log_context
# ---------------------------------------------------------------------------
class GetLogContextInput(BaseModel):
    log_group_id: str = Field(..., description="Log group id.")
    log_stream_id: str = Field(..., description="Log stream id within the group.")
    line_num: str = Field(
        ...,
        description=(
            "The ``line_num`` of the pivot log entry (returned by "
            "lts_search_logs). LTS expects a string."
        ),
    )
    backwards: int = Field(
        default=10,
        ge=0,
        le=500,
        description="How many lines BEFORE the pivot to return (0..500).",
    )
    forwards: int = Field(
        default=10,
        ge=0,
        le=500,
        description="How many lines AFTER the pivot to return (0..500).",
    )
    time_ms: Optional[int] = Field(
        default=None,
        description=(
            "Optional 13-digit epoch ms timestamp of the pivot line. LTS "
            "uses it to disambiguate when line_num collides across shards."
        ),
    )

    @field_validator("log_group_id")
    @classmethod
    def _v_gid(cls, v: str) -> str:
        return _check_id(v, "log_group_id")

    @field_validator("log_stream_id")
    @classmethod
    def _v_sid(cls, v: str) -> str:
        return _check_id(v, "log_stream_id")


# ---------------------------------------------------------------------------
# lts_query_histogram
# ---------------------------------------------------------------------------
_STEP_TO_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


class QueryHistogramInput(BaseModel):
    log_group_id: str = Field(..., description="Log group id.")
    log_stream_id: str = Field(..., description="Log stream id.")
    start_time: Optional[str] = Field(
        default=None, description="Inclusive start. Default '-1h'."
    )
    end_time: Optional[str] = Field(
        default=None, description="Exclusive end. Default 'now'."
    )
    keyword: Optional[str] = Field(
        default=None,
        description=(
            "Optional keyword filter. When omitted, every log line in the "
            "window is counted."
        ),
    )
    step: Literal["1m", "5m", "15m", "1h", "1d"] = Field(
        default="5m",
        description="Bucket width. One of 1m / 5m / 15m / 1h / 1d.",
    )

    @field_validator("log_group_id")
    @classmethod
    def _v_gid(cls, v: str) -> str:
        return _check_id(v, "log_group_id")

    @field_validator("log_stream_id")
    @classmethod
    def _v_sid(cls, v: str) -> str:
        return _check_id(v, "log_stream_id")


# ---------------------------------------------------------------------------
# lts_query_alarm_rules — list, or detail for one rule (by id + type)
# ---------------------------------------------------------------------------
class QueryAlarmRulesInput(BaseModel):
    rule_id: Optional[str] = Field(
        default=None,
        description=(
            "Rule id. If None/empty, returns the LIST of rules. If set, "
            "returns DETAIL for that single rule. Rule type must also be "
            "specified in DETAIL mode (via ``rule_type``)."
        ),
    )
    rule_type: Literal["keyword", "sql", "all"] = Field(
        default="all",
        description=(
            "Which family of rules to operate on. In LIST mode, 'all' "
            "(default) returns both keyword and SQL alarm rules merged with "
            "a ``rule_type`` field. In DETAIL mode it MUST be 'keyword' or "
            "'sql' so we can find the right rule."
        ),
    )

    @field_validator("rule_id")
    @classmethod
    def _v_rid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        # Rule ids are usually UUID-ish but not guaranteed; keep loose
        # validation similar to other LTS ids.
        return _check_id(v, "rule_id")


# ---------------------------------------------------------------------------
# lts_list_alarm_history — recently triggered alarms (notifications/events)
# ---------------------------------------------------------------------------
class ListAlarmHistoryInput(BaseModel):
    start_time: Optional[str] = Field(
        default=None,
        description="Inclusive window start. Default '-1d'.",
    )
    end_time: Optional[str] = Field(
        default=None,
        description="Exclusive window end. Default 'now'.",
    )
    state: Literal["active", "history"] = Field(
        default="active",
        description=(
            "'active' = currently firing alarms (active alarm pool). "
            "'history' = previously fired/cleared alarms."
        ),
    )
    alarm_level: Optional[
        Literal["Critical", "Major", "Minor", "Info"]
    ] = Field(
        default=None,
        description="Optional severity filter.",
    )
    search: Optional[str] = Field(
        default=None,
        description=(
            "Free-text search across alarm name / rule id / resource. "
            "Forwarded to the LTS ``search`` query parameter."
        ),
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Page size (1..200). LTS default 50.",
    )
    marker: Optional[str] = Field(
        default=None,
        description="Cursor from a previous response for pagination.",
    )
