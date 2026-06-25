"""RDS log tools — merged error + slow query logs.

rds_get_db_logs dispatches on log_type:
  * 'error' → ListErrorLogsNew (database error logs with level filter)
  * 'slow'  → ListSlowlogStatistics (aggregated slow-query stats sorted by
              duration or count — the AI core value point for SQL analysis)

Time inputs accept human-readable formats ('-1h', ISO8601, etc.) and are
converted to ISO8601 with timezone offset for the RDS v3 API
(e.g. "2024-06-26T00:00:00+0000").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from huaweicloudsdkrds.v3 import (
    ListErrorLogsNewRequest,
    ListSlowlogStatisticsRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ...cts.time_utils import human_to_epoch_ms, now_ms
from ..models import GetDbLogsInput
from ..serializers import error_log_summary, slow_log_statistics

log = logging.getLogger("huaweicloud_mcp.services.rds.tools.logs")


def _resolve_time_window(
    start_time: Optional[str],
    end_time: Optional[str],
    default_from: str,
    settings: Settings,
) -> tuple[str, str]:
    """Resolve (start_iso, end_iso) from human-readable inputs.

    Returns ISO8601 strings with UTC offset, e.g. "2024-06-26T00:00:00+0000".
    """
    tz = settings.default_timezone
    to_ms = human_to_epoch_ms(end_time, tz) if end_time else now_ms()
    from_ms = human_to_epoch_ms(start_time, tz) if start_time else human_to_epoch_ms(default_from, tz)
    if from_ms >= to_ms:
        raise ToolError(
            code="TIME_RANGE_INVALID",
            message=f"start_time ({from_ms}) must be < end_time ({to_ms})",
        )
    # Convert epoch ms to ISO8601 with UTC offset (format required by RDS API).
    start_iso = datetime.fromtimestamp(from_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
    end_iso = datetime.fromtimestamp(to_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return start_iso, end_iso


def make_log_tools(settings: Settings) -> dict:
    """Build RDS log tools bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def rds_get_db_logs(
        instance_id: str,
        log_type: str = "error",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        level: Optional[str] = None,
        database: Optional[str] = None,
        min_duration_ms: int = 1000,
        sort_by: str = "duration",
        limit: int = 50,
    ) -> dict:
        """Query RDS database logs — error logs or slow query logs.

        Dispatches based on log_type:

        **Error logs** (log_type='error'):
          Returns database error log entries with timestamp, severity level,
          and content. Use for fault diagnosis — cross-reference with LTS
          application logs for causal-chain analysis.

        **Slow query logs** (log_type='slow'):
          Returns aggregated slow-query statistics grouped by SQL pattern.
          Each entry includes sql_text, avg_duration_ms, execution_count,
          lock_time_ms, rows_examined — enabling direct AI analysis of SQL
          patterns for index optimization and query rewriting.

          Use sort_by='count' to find high-frequency slow SQL (highest
          impact). Use sort_by='duration' to find the slowest individual
          queries. Filter by database and min_duration_ms to narrow scope.

        Args:
            instance_id: RDS instance UUID.
            log_type: 'error' or 'slow'. Default 'error'.
            start_time: Inclusive start. Accepts '-1h', '-30m', ISO8601,
                        'YYYY-MM-DD HH:MM:SS', or epoch ms. Default '-1h'.
            end_time: Exclusive end. Default 'now'.
            level: Error-log only: filter by severity ('all', 'warning', 'error').
            database: Slow-log only: filter by database name.
            min_duration_ms: Slow-log only: minimum avg duration in ms. Default 1000.
            sort_by: Slow-log only: 'duration' or 'count'. Default 'duration'.
            limit: Max records (1..100). Default 50.

        Returns:
            error: {"error_logs": [...], "total_record": N}
                   Each: {time, level, content}
            slow:  {"slow_queries": [...], "total_record": N, "sort_by": ...}
                   Each: {database, sql_text, avg_duration_ms, execution_count,
                          lock_time_ms, rows_sent, rows_examined, users, client_ip, type}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GetDbLogsInput(
            instance_id=instance_id,
            log_type=log_type,  # type: ignore[arg-type]
            start_time=start_time,
            end_time=end_time,
            level=level,  # type: ignore[arg-type]
            database=database,
            min_duration_ms=min_duration_ms,
            sort_by=sort_by,  # type: ignore[arg-type]
            limit=limit,
        )
        client = get_client("rds", settings)

        # ---- Error logs ----
        if params.log_type == "error":
            start_iso, end_iso = _resolve_time_window(
                params.start_time, params.end_time, "-1h", settings,
            )
            req = ListErrorLogsNewRequest(
                instance_id=params.instance_id,
                start_date=start_iso,
                end_date=end_iso,
                level=params.level,
                limit=params.limit,
            )
            resp = client.list_error_logs_new(req)
            entries = list(getattr(resp, "error_log_list", None) or [])
            out = [error_log_summary(e) for e in entries]
            return {"error_logs": out, "total_record": getattr(resp, "total_record", len(out))}

        # ---- Slow query logs (statistics) ----
        start_iso, end_iso = _resolve_time_window(
            params.start_time, params.end_time, "-1h", settings,
        )

        # Map sort_by to SDK sort parameter.
        sdk_sort = "executeTime" if params.sort_by == "duration" else "count"

        req = ListSlowlogStatisticsRequest(
            instance_id=params.instance_id,
            start_date=start_iso,
            end_date=end_iso,
            type="ALL",  # query all statement types
            sort=sdk_sort,
            cur_page=1,
            per_page=params.limit,
        )
        resp = client.list_slowlog_statistics(req)
        stats = list(getattr(resp, "slow_log_list", None) or [])
        out = [slow_log_statistics(s) for s in stats]

        # Post-filter by min_duration_ms and database (SDK may not support
        # these filters directly for all engines).
        if params.min_duration_ms > 0:
            out = [
                e for e in out
                if (e.get("avg_duration_ms") or 0) >= params.min_duration_ms
            ]
        if params.database:
            out = [e for e in out if e.get("database") == params.database]

        return {
            "slow_queries": out,
            "total_record": len(out),
            "sort_by": params.sort_by,
            "min_duration_ms": params.min_duration_ms,
        }

    return {"rds_get_db_logs": rds_get_db_logs}
