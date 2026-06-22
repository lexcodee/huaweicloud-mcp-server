"""``cts_search_traces`` — combined-condition CTS audit-event search."""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkcts.v3 import ListTracesRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ..client import get_cts_client
from ..config import Settings
from ..errors import ToolError, wrap_tool
from ..models import SearchTracesInput, resolve_time_range
from ..serializers import trace_summary

log = logging.getLogger("cts_mcp_server.tools.search")

# Defensive hard ceiling for the auto-paginate loop so a runaway response
# with a never-empty marker can't hold the request loop indefinitely.
_AUTO_PAGINATE_MAX_PAGES = 50


def make_search_tools(settings: Settings) -> dict:
    """Build the search tool, bound to a Settings instance."""
    auth = create_auth_strategy()

    @wrap_tool
    def cts_search_traces(
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        service_type: Optional[str] = None,
        user: Optional[str] = None,
        trace_rating: Optional[str] = None,
        trace_type: str = "system",
        trace_name: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_name: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 10,
        next_marker: Optional[str] = None,
        auto_paginate: bool = False,
        max_results: int = 100,
    ) -> dict:
        """Search Huawei Cloud CTS audit events by time + filters.

        IMPORTANT — CTS limitations (read before using):

          * Only the **last 7 days** of trace data is queryable via this API.
            Earlier history lives in the OBS bucket configured on the CTS
            tracker (CTS console → Tracker → Object Storage). This tool
            REJECTS start_time values that fall outside the 7-day window
            before issuing any SDK call.
          * Pagination is **cursor-based**, NOT offset-based. Use the
            ``next_marker`` from a previous response, not a computed offset.
            Set ``auto_paginate=true`` to have the tool walk the cursor
            internally up to ``max_results`` rows.
          * Time is converted to 13-digit UTC ms internally — humans may
            write ``-1h``, ``-2d``, ``"2026-06-20T22:00:00+08:00"``, or
            ``"2026-06-20 22:00:00"`` (naive strings interpreted in
            CTS_DEFAULT_TIMEZONE, default Asia/Shanghai). The CTS interval
            is half-open ``[from, to)``.
          * Most filters (``service_type``, ``user``, ``resource_*``) only
            apply when ``trace_type="system"`` (management plane). For
            data-plane events pass ``trace_type="data"``.
          * Sensitive values in request/response bodies (``password``,
            ``secret``, ``token``, ``access_key``, etc.) are replaced with
            ``"***MASKED***"`` before being returned. Body summaries are
            truncated to 500 chars; use ``cts_get_trace_detail`` for the
            (still masked, larger) full body.

        Args:
            start_time: Inclusive start of search window. Defaults to '-1h'.
            end_time:   Exclusive end of search window. Defaults to now.
            service_type: Service abbreviation in UPPERCASE (ECS / OBS / VPC /
                IAM / EVS / ELB / CCE / RDS / ...). System events only.
            user: Sub-user name (matches user.user_name). System events only.
            trace_rating: One of 'normal' / 'warning' / 'incident'.
            trace_type: 'system' (default, management plane) or 'data'.
            trace_name: Exact event name like 'deleteEip'.
            resource_type / resource_name / resource_id: Resource filters
                (system events only).
            limit: Page size (1..200, CTS default 10).
            next_marker: Cursor from a previous response — opaque string.
            auto_paginate: If true, internally walks marker pages until
                exhausted or ``max_results`` reached.
            max_results: Cap on merged result count when auto_paginate is
                on (1..2000, default 100).

        Returns:
            On success::

                {
                  "total_returned": int,
                  "next_marker": str | null,   # null = no more pages
                  "truncated": bool,           # true = stopped at max_results
                  "query": { "from_ms": ..., "to_ms": ..., "filters": {...} },
                  "traces": [ ... trimmed trace summaries ... ]
                }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = SearchTracesInput(
            start_time=start_time,
            end_time=end_time,
            service_type=service_type,
            user=user,
            trace_rating=trace_rating,
            trace_type=trace_type,
            trace_name=trace_name,
            resource_type=resource_type,
            resource_name=resource_name,
            resource_id=resource_id,
            limit=limit,
            next_marker=next_marker,
            auto_paginate=auto_paginate,
            max_results=max_results,
        )

        try:
            from_ms, to_ms = resolve_time_range(
                params.start_time, params.end_time, settings.default_timezone
            )
        except ValueError as e:
            msg = str(e)
            if "last 7 days" in msg:
                raise ToolError(code="TIME_RANGE_TOO_OLD", message=msg)
            raise ToolError(code="TIME_RANGE_INVALID", message=msg)

        # Soft warning when user/resource_* filters are set on a non-system
        # query — these are silently dropped by the CTS API, easy to miss.
        if params.trace_type != "system" and any(
            [params.user, params.resource_type, params.resource_name, params.resource_id]
        ):
            log.info(
                "trace_type=%s — user/resource_* filters will be ignored by CTS "
                "(they only apply when trace_type='system')",
                params.trace_type,
            )

        client = get_cts_client(settings)

        def _build_req(marker: Optional[str]) -> ListTracesRequest:
            # The SDK uses `_from` (because `from` is a Python keyword).
            return ListTracesRequest(
                trace_type=params.trace_type,
                limit=params.limit,
                _from=from_ms,
                to=to_ms,
                next=marker,
                service_type=params.service_type,
                user=params.user,
                resource_id=params.resource_id,
                resource_name=params.resource_name,
                resource_type=params.resource_type,
                trace_name=params.trace_name,
                trace_rating=params.trace_rating,
            )

        all_traces: list = []
        cursor: Optional[str] = params.next_marker
        truncated = False
        pages = 0

        while True:
            pages += 1
            req = _build_req(cursor)
            log.debug(
                "list_traces request: from=%d to=%d limit=%d marker=%r trace_type=%s",
                from_ms, to_ms, params.limit, cursor, params.trace_type,
            )
            resp = client.list_traces(req)
            traces = resp.traces or []
            meta = getattr(resp, "meta_data", None)
            cursor = getattr(meta, "marker", None) if meta else None

            # Respect max_results when auto-paginating
            if params.auto_paginate:
                remaining = params.max_results - len(all_traces)
                if remaining <= 0:
                    truncated = True
                    break
                if len(traces) > remaining:
                    all_traces.extend(traces[:remaining])
                    truncated = True
                    cursor = None  # we stopped early; caller can resume w/ resp marker if exposed
                    break
                all_traces.extend(traces)
            else:
                all_traces.extend(traces)
                break  # single page mode

            if not cursor:
                break  # no more data
            if pages >= _AUTO_PAGINATE_MAX_PAGES:
                log.warning(
                    "auto_paginate hit the safety cap of %d pages; stopping",
                    _AUTO_PAGINATE_MAX_PAGES,
                )
                truncated = True
                break

        serialized = [
            trace_summary(t, tz=settings.default_timezone, summary_limit=500)
            for t in all_traces
        ]

        return {
            "total_returned": len(serialized),
            "next_marker": cursor or None,
            "truncated": truncated,
            "query": {
                "from_ms": from_ms,
                "to_ms": to_ms,
                "filters": {
                    "service_type": params.service_type,
                    "user": params.user,
                    "trace_rating": params.trace_rating,
                    "trace_type": params.trace_type,
                    "trace_name": params.trace_name,
                    "resource_type": params.resource_type,
                    "resource_name": params.resource_name,
                    "resource_id": params.resource_id,
                    "limit": params.limit,
                    "auto_paginate": params.auto_paginate,
                    "max_results": params.max_results if params.auto_paginate else None,
                },
            },
            "traces": serialized,
        }

    return {"cts_search_traces": cts_search_traces}
