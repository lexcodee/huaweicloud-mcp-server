"""Log search, context, and histogram tools.

LTS time params are 13-digit epoch ms. We accept the same humane time
syntax as CTS (``-1h``, ISO8601, ``YYYY-MM-DD HH:MM:SS``, plain epoch)
and convert at the boundary.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from huaweicloudsdklts.v2 import (
    ListLogContextRequest,
    ListLogContextRequestBody,
    ListLogHistogramRequest,
    ListLogsRequest,
    QueryLogKeyWordCountRequestBody,
    QueryLtsLogParams,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ...cts.time_utils import human_to_epoch_ms, now_ms
from ..models import (
    _STEP_TO_MS,
    GetLogContextInput,
    QueryHistogramInput,
    SearchLogsInput,
)
from ..serializers import log_entry

log = logging.getLogger("huaweicloud_mcp.services.lts.tools.search")


# How long the user-supplied window is allowed to be in a single histogram /
# search call. Wider windows demand a bigger ``step`` to keep the bucket
# count under control.
_MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000  # 30 days


def _resolve_window(
    start: Optional[str],
    end: Optional[str],
    *,
    default_window_ms: int = 3600_000,
    tz: str = "Asia/Shanghai",
) -> tuple[int, int]:
    """Return (from_ms, to_ms). end defaults to now, start to now - default."""
    try:
        to_ms = human_to_epoch_ms(end, tz) if end else now_ms()
        from_ms = (
            human_to_epoch_ms(start, tz) if start else to_ms - default_window_ms
        )
    except ValueError as e:
        raise ToolError(code="TIME_RANGE_INVALID", message=str(e)) from e
    if from_ms >= to_ms:
        raise ToolError(
            code="TIME_RANGE_INVALID",
            message=f"start_time ({from_ms}) must be < end_time ({to_ms})",
        )
    if to_ms - from_ms > _MAX_WINDOW_MS:
        raise ToolError(
            code="TIME_RANGE_TOO_WIDE",
            message=(
                f"requested window is "
                f"{(to_ms - from_ms) // 86400000} days; max is "
                f"{_MAX_WINDOW_MS // 86400000} days per call."
            ),
            hint="Split the query into smaller windows.",
        )
    return from_ms, to_ms


def _parse_histogram_payload(raw: Optional[str]) -> list[dict]:
    """LTS returns the histogram as a JSON string in the ``histogram`` field.

    Different SDK versions emit different shapes — most commonly a list of
    objects with ``time``/``count`` keys, or with ``totalCount`` / ``startTs``.
    We normalise to ``[{ts_ms, count}, ...]``.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        log.warning("histogram payload was not valid JSON; returning raw")
        return [{"raw": raw}]
    out: list[dict] = []
    if not isinstance(parsed, list):
        return [{"raw": parsed}]
    for row in parsed:
        if not isinstance(row, dict):
            continue
        ts = (
            row.get("time")
            or row.get("startTs")
            or row.get("start_ts")
            or row.get("ts")
        )
        cnt = row.get("count") if "count" in row else row.get("totalCount")
        out.append({"ts_ms": ts, "count": cnt})
    return out


def make_search_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def lts_search_logs(
        log_group_id: str,
        log_stream_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        keywords: Optional[str] = None,
        query: Optional[str] = None,
        labels: Optional[dict] = None,
        is_desc: bool = True,
        limit: int = 50,
        line_num: Optional[str] = None,
        highlight: bool = False,
    ) -> dict:
        """Search LTS logs by keyword / SQL / label filters.

        Time fields accept relative forms (``'-1h'``, ``'-30m'``,
        ``'-2d'``), ISO8601 with offset (``'2026-06-20T22:00:00+08:00'``),
        plain ``'YYYY-MM-DD HH:MM:SS'`` (naive strings interpreted in the
        configured default timezone), or a 13-digit epoch-ms string.
        Defaults: start=now-1h, end=now.

        Querying modes (mutually exclusive):

          * Set ``query`` to run a full LTS SQL / pipeline expression
            (e.g. ``"level:ERROR AND host:host-01 | stats count() by service"``).
            The result then contains ``analysis_logs`` for any aggregated
            output in addition to raw log lines.
          * Otherwise set ``keywords`` (whitespace-separated tokens, all
            ANDed) and/or ``labels`` for equality filters on structured
            fields.

        Pagination is cursor-based via ``line_num`` — pass the
        ``line_num`` of the last entry in the previous page.

        Args:
            log_group_id: Group containing the stream to search.
            log_stream_id: Stream to search.
            start_time / end_time: Window bounds (see above).
            keywords: Whitespace-separated keyword tokens.
            query: Full LTS SQL/pipeline query (overrides ``keywords``).
            labels: Equality filters on structured-log labels.
            is_desc: Sort newest first when True (default).
            limit: Page size, 1..500.
            line_num: Cursor token from a previous response.
            highlight: Ask LTS to wrap matched keywords in markers.

        Returns:
            {
              "count": int,                    # total matching in window
              "total_returned": int,           # rows in this page
              "is_query_complete": bool,       # false → server still scanning
              "query": { "from_ms": int, "to_ms": int, "mode": str, ... },
              "logs": [ {line_num, content, labels, ...}, ... ],
              "analysis_logs": [...]           # only present in SQL mode
            }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = SearchLogsInput(
            log_group_id=log_group_id,
            log_stream_id=log_stream_id,
            start_time=start_time,
            end_time=end_time,
            keywords=keywords,
            query=query,
            labels=labels,
            is_desc=is_desc,
            limit=limit,
            line_num=line_num,
            highlight=highlight,
        )

        from_ms, to_ms = _resolve_window(
            params.start_time, params.end_time, tz=settings.default_timezone
        )

        # Translate `labels` dict to LTS' list of objects shape.
        # The SDK ``labels`` field on QueryLtsLogParams accepts a dict; it
        # serialises as a JSON object on the wire which matches LTS' spec.
        labels_payload = params.labels or None

        if params.query:
            # Pipeline / SQL mode
            body = QueryLtsLogParams(
                start_time=str(from_ms),
                end_time=str(to_ms),
                labels=labels_payload,
                is_count=True,
                line_num=params.line_num,
                is_desc=params.is_desc,
                search_type="init" if not params.line_num else "forwards",
                limit=params.limit,
                highlight=params.highlight,
                query=params.query,
                is_analysis_query=True,
            )
            mode = "sql"
        else:
            body = QueryLtsLogParams(
                start_time=str(from_ms),
                end_time=str(to_ms),
                labels=labels_payload,
                is_count=True,
                keywords=params.keywords,
                line_num=params.line_num,
                is_desc=params.is_desc,
                search_type="init" if not params.line_num else "forwards",
                limit=params.limit,
                highlight=params.highlight,
            )
            mode = "keyword"

        client = get_client("lts", settings)
        resp = client.list_logs(
            ListLogsRequest(
                log_group_id=params.log_group_id,
                log_stream_id=params.log_stream_id,
                body=body,
            )
        )

        logs_raw = list(getattr(resp, "logs", None) or [])
        logs = [log_entry(item) for item in logs_raw]

        result: dict = {
            "count": getattr(resp, "count", None),
            "total_returned": len(logs),
            "is_query_complete": getattr(resp, "is_query_complete", None),
            "query": {
                "from_ms": from_ms,
                "to_ms": to_ms,
                "mode": mode,
                "log_group_id": params.log_group_id,
                "log_stream_id": params.log_stream_id,
                "keywords": params.keywords,
                "query": params.query,
                "labels": labels_payload,
                "limit": params.limit,
                "is_desc": params.is_desc,
                "line_num": params.line_num,
            },
            "logs": logs,
        }

        analysis = getattr(resp, "analysis_logs", None)
        if analysis:
            # ``analysis_logs`` is a list of dicts (the SDK leaves them
            # plain), already JSON-serialisable.
            result["analysis_logs"] = analysis

        return result

    @wrap_tool
    def lts_get_log_context(
        log_group_id: str,
        log_stream_id: str,
        line_num: str,
        backwards: int = 10,
        forwards: int = 10,
        time_ms: Optional[int] = None,
    ) -> dict:
        """Fetch the N lines around a specific log entry.

        Use this after ``lts_search_logs`` flags an interesting line:
        feed its ``line_num`` (and optionally its timestamp) here to pull
        the causal chain — the request before, the response after, the
        cleanup that ran on failure, etc.

        ``backwards`` and ``forwards`` are independent (0..500). Setting
        both to 0 is allowed but pointless — at least one should be > 0.

        Args:
            log_group_id: Group containing the pivot log.
            log_stream_id: Stream containing the pivot log.
            line_num: ``line_num`` of the pivot from a previous response.
            backwards: How many lines BEFORE to fetch (0..500). Default 10.
            forwards: How many lines AFTER to fetch (0..500). Default 10.
            time_ms: Optional epoch-ms timestamp of the pivot for shard
                     disambiguation.

        Returns:
            {
              "pivot": {"line_num": ..., "time_ms": ...},
              "backwards": int,
              "forwards": int,
              "total_returned": int,
              "logs": [ {line_num, content, labels, ...}, ... ]
            }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GetLogContextInput(
            log_group_id=log_group_id,
            log_stream_id=log_stream_id,
            line_num=line_num,
            backwards=backwards,
            forwards=forwards,
            time_ms=time_ms,
        )

        if params.backwards == 0 and params.forwards == 0:
            raise ToolError(
                code="INVALID_PARAMS",
                message="at least one of backwards / forwards must be > 0",
            )

        body = ListLogContextRequestBody(
            line_num=params.line_num,
            time__=params.time_ms,
            backwards_size=params.backwards,
            forwards_size=params.forwards,
        )

        client = get_client("lts", settings)
        resp = client.list_log_context(
            ListLogContextRequest(
                log_group_id=params.log_group_id,
                log_stream_id=params.log_stream_id,
                body=body,
            )
        )

        logs_raw = list(getattr(resp, "logs", None) or [])
        logs = [log_entry(item) for item in logs_raw]
        return {
            "pivot": {"line_num": params.line_num, "time_ms": params.time_ms},
            "backwards": params.backwards,
            "forwards": params.forwards,
            "total_returned": len(logs),
            "logs": logs,
        }

    @wrap_tool
    def lts_query_histogram(
        log_group_id: str,
        log_stream_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        keyword: Optional[str] = None,
        step: str = "5m",
    ) -> dict:
        """Bucket log counts over time, optionally filtered by a keyword.

        Use this to spot error spikes / traffic anomalies — a histogram is
        much cheaper than a full ``lts_search_logs`` when you only need
        to know *when* things went wrong.

        Args:
            log_group_id / log_stream_id: Target stream.
            start_time / end_time: Window bounds. Default last 1h.
            keyword: Optional substring filter. Omit to count every line.
            step: Bucket width — one of 1m / 5m / 15m / 1h / 1d.

        Returns:
            {
              "count": int,                 # total in window
              "is_query_complete": bool,
              "step": str,
              "step_ms": int,
              "query": { "from_ms", "to_ms", "keyword", ... },
              "buckets": [ {ts_ms, count}, ... ]
            }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryHistogramInput(
            log_group_id=log_group_id,
            log_stream_id=log_stream_id,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            step=step,
        )

        from_ms, to_ms = _resolve_window(
            params.start_time, params.end_time, tz=settings.default_timezone
        )
        step_ms = _STEP_TO_MS[params.step]

        body = QueryLogKeyWordCountRequestBody(
            start_time=str(from_ms),
            end_time=str(to_ms),
            step_interval=step_ms,
            group_id=params.log_group_id,
            stream_id=params.log_stream_id,
            key_word=params.keyword,
            is_iterative=False,
        )

        client = get_client("lts", settings)
        resp = client.list_log_histogram(ListLogHistogramRequest(body=body))

        buckets = _parse_histogram_payload(getattr(resp, "histogram", None))
        return {
            "count": getattr(resp, "count", None),
            "is_query_complete": getattr(resp, "is_query_complete", None),
            "step": params.step,
            "step_ms": step_ms,
            "query": {
                "from_ms": from_ms,
                "to_ms": to_ms,
                "log_group_id": params.log_group_id,
                "log_stream_id": params.log_stream_id,
                "keyword": params.keyword,
            },
            "buckets": buckets,
        }

    return {
        "lts_search_logs": lts_search_logs,
        "lts_get_log_context": lts_get_log_context,
        "lts_query_histogram": lts_query_histogram,
    }
