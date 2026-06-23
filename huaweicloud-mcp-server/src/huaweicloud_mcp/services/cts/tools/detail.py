"""``cts_get_trace_detail`` — retrieve a single trace's full body."""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkcts.v3 import ListTracesRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import GetTraceDetailInput
from ..serializers import trace_detail
from ..time_utils import SEVEN_DAY_TOLERANCE_MS, SEVEN_DAYS_MS, now_ms

log = logging.getLogger("huaweicloud_mcp.services.cts.tools.detail")


def make_detail_tools(settings: Settings) -> dict:
    """Build the detail tool, bound to a Settings instance."""
    auth = create_auth_strategy()

    @wrap_tool
    def cts_get_trace_detail(
        trace_id: str,
        trace_type: str = "system",
    ) -> dict:
        """Get the full request/response body of a single CTS audit event.

        This tool is used after ``cts_search_traces`` has identified a
        specific ``trace_id`` and you need to inspect the full (but
        sensitive-value-masked) request and response payloads.

        Under the hood this calls the same ``ListTraces`` API with
        ``trace_id`` set — when ``trace_id`` is present, CTS ignores all
        other filter parameters and returns only the matching trace.

        IMPORTANT — same 7-day window as search: if the trace is older than
        7 days it will not be found by this API.

        Sensitive values (password, secret, token, access_key, etc.) in
        the request/response bodies are replaced with ``"***MASKED***"``.
        Bodies are truncated at 5000 chars; if truncated, the response
        includes ``truncate_hint`` with instructions to view the full
        payload in the CTS console.

        Args:
            trace_id: The event ID from a cts_search_traces result.
            trace_type: 'system' (default) or 'data' — must match the
                trace_type used at search time.

        Returns:
            On success: a dict with full trace metadata plus masked
            request/response bodies. On not-found: ``{"ok": false,
            "error": {"code": "NOT_FOUND", ...}}``.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GetTraceDetailInput(trace_id=trace_id, trace_type=trace_type)
        client = get_client("cts", settings)

        # Use the full 7-day window; trace_id overrides all other filters.
        now = now_ms()
        from_ms = now - SEVEN_DAYS_MS - SEVEN_DAY_TOLERANCE_MS

        req = ListTracesRequest(
            trace_type=params.trace_type,
            trace_id=params.trace_id,
            _from=from_ms,
            to=now,
        )
        log.debug(
            "list_traces detail request: trace_id=%r trace_type=%s from=%d to=%d",
            params.trace_id, params.trace_type, from_ms, now,
        )
        resp = client.list_traces(req)
        traces = resp.traces or []

        if not traces:
            raise ToolError(
                code="NOT_FOUND",
                message=(
                    f"trace_id={params.trace_id!r} not found in the last 7-day "
                    f"window (trace_type={params.trace_type!r}). If the event is "
                    f"older, check the OBS bucket on the CTS tracker."
                ),
            )

        return trace_detail(traces[0], tz=settings.default_timezone, body_limit=5000)

    return {"cts_get_trace_detail": cts_get_trace_detail}