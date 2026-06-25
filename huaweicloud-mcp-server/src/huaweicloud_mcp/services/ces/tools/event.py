"""CES event data tool — list events and event details.

Single tool:
  * ``ces_list_event_data`` — list event monitoring data, or fetch one
    event's detail. Uses the v1 SDK (ListEvents / ListEventDetail).
    Mirrors the CCE list/detail dispatch pattern.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkces.v1 import ListEventDetailRequest, ListEventsRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from .._time import resolve_time_window
from ..models import ListEventDataInput
from ..serializers import event_detail, event_summary

log = logging.getLogger("huaweicloud_mcp.services.ces.tools.event")


def make_event_tools(settings: Settings) -> dict:
    """Build CES event data tool bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def ces_list_event_data(
        event_name: Optional[str] = None,
        event_type: Optional[str] = None,
        sub_event_type: Optional[str] = None,
        event_source: Optional[str] = None,
        event_level: Optional[str] = None,
        event_state: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        limit: Optional[int] = None,
        start: Optional[str] = None,
    ) -> dict:
        """List CES event monitoring data, or fetch one event's detail.

        Dispatches based on ``event_name``:

          * ``event_name`` is None/empty → LIST mode. Returns a compact
            list of events (system or custom) in the time window.

          * ``event_name`` is set        → DETAIL mode. Returns full
            event info including event sources, users, and counts.

        Events capture OTC operations, service exceptions, and custom
        events. Cross-reference with metric anomalies to identify
        change-impact causality.

        Args:
            event_name: Event name; omit/empty to list.
            event_type: 'EVENT.SYS' (default) or 'EVENT.CUSTOM'.
            sub_event_type: Sub-type filter
                            (SUB_EVENT.OPS / SUB_EVENT.PLAN / SUB_EVENT.CUSTOM).
            event_source: Detail filter — event source (namespace).
            event_level: Detail filter — Critical/Major/Minor/Info.
            event_state: Detail filter — normal/warning/incident.
            from_time: Window start. Default '-1d'.
            to_time: Window end. Default 'now'.
            limit: Page size (1..100).
            start: Pagination cursor.

        Returns:
            LIST mode:
              {"events": [...], "count": N, "query": {...}}
            DETAIL mode:
              see serializers.event_detail
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListEventDataInput(
            event_name=event_name,
            event_type=event_type,
            sub_event_type=sub_event_type,
            event_source=event_source,
            event_level=event_level,
            event_state=event_state,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            start=start,
        )

        # Resolve time window
        from_ms, to_ms = resolve_time_window(
            params.from_time, params.to_time,
            default_from="-1d",
            settings=settings,
        )

        # v1 client for events
        client = get_client("ces_v1", settings)

        # ---- LIST mode ---------------------------------------------------
        if params.event_name is None or params.event_name == "":
            req = ListEventsRequest(
                event_type=params.event_type,
                sub_event_type=params.sub_event_type,
                event_name=None,
                _from=from_ms,
                to=to_ms,
                start=params.start,
                limit=params.limit,
            )
            resp = client.list_events(req)
            items = list(getattr(resp, "events", None) or [])
            events = [event_summary(e) for e in items]
            return {
                "events": events,
                "count": len(events),
                "query": {
                    "from_ms": from_ms,
                    "to_ms": to_ms,
                    "event_type": params.event_type,
                },
            }

        # ---- DETAIL mode -------------------------------------------------
        # CES v1 ListEventDetail API requires event_type; default to EVENT.SYS.
        detail_event_type = params.event_type or "EVENT.SYS"
        req = ListEventDetailRequest(
            event_name=params.event_name,
            event_type=detail_event_type,
            sub_event_type=params.sub_event_type,
            event_source=params.event_source,
            event_level=params.event_level,
            event_user=None,
            event_state=params.event_state,
            _from=from_ms,
            to=to_ms,
            start=params.start,
            limit=params.limit,
        )
        resp = client.list_event_detail(req)
        return event_detail(resp)

    return {"ces_list_event_data": ces_list_event_data}
