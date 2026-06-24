"""LTS alarm-rule and alarm-history tools.

Two tools:
  * ``lts_query_alarm_rules`` — list keyword + sql alarm rules, or fetch
    one rule's detail. Mirrors the CCE list/detail dispatch pattern.
  * ``lts_list_alarm_history`` — recently triggered alarm events
    (covers the original ``list_notifications`` use case — what fired
    when, with what payload).
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdklts.v2 import (
    ListActiveOrHistoryAlarmsRequest,
    ListActiveOrHistoryAlarmsRequestBody,
    ListKeywordsAlarmRulesRequest,
    ListSqlAlarmRulesRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ...cts.time_utils import human_to_epoch_ms, now_ms
from ..models import ListAlarmHistoryInput, QueryAlarmRulesInput
from ..serializers import (
    alarm_event_summary,
    keyword_alarm_rule_detail,
    keyword_alarm_rule_summary,
    sql_alarm_rule_detail,
    sql_alarm_rule_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.lts.tools.alarm")

_SEVERITY_TO_ID = {
    "Critical": 1,
    "Major": 2,
    "Minor": 3,
    "Info": 4,
}


def make_alarm_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def lts_query_alarm_rules(
        rule_id: Optional[str] = None,
        rule_type: str = "all",
    ) -> dict:
        """List LTS alarm rules, or return detail for one rule.

        Two output shapes, dispatched by ``rule_id``:

          * ``rule_id`` is None/empty → LIST mode. Returns BOTH keyword
            and SQL rules by default (``rule_type='all'``). Each item
            carries a ``rule_type`` field so the LLM can tell them apart.
            Pass ``rule_type='keyword'`` or ``'sql'`` to narrow the list.

          * ``rule_id`` is set → DETAIL mode. ``rule_type`` MUST be
            ``'keyword'`` or ``'sql'`` (we can't probe both safely — wrong
            type yields a 404 from LTS). Returns the full rule body
            including ``frequency``, ``condition_expression``, and the
            list of ``keywords_requests`` / ``sql_requests`` that wire
            the rule to specific log groups/streams.

        Args:
            rule_id: Rule id; omit/empty to list.
            rule_type: 'all' (list only) / 'keyword' / 'sql'.

        Returns:
            LIST mode:
              {"mode":"list", "rule_type": str, "count": N,
               "rules": [ {rule_id, rule_type, name, level, ...}, ... ]}
            DETAIL mode:
              {"mode":"detail", "rule_type": "keyword"|"sql",
               "rule": {...full body...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryAlarmRulesInput(rule_id=rule_id, rule_type=rule_type)
        client = get_client("lts", settings)

        # ---- LIST mode ---------------------------------------------------
        if params.rule_id is None:
            rules: list[dict] = []
            if params.rule_type in ("all", "keyword"):
                resp = client.list_keywords_alarm_rules(
                    ListKeywordsAlarmRulesRequest()
                )
                for r in getattr(resp, "keywords_alarm_rules", None) or []:
                    rules.append(keyword_alarm_rule_summary(r))
            if params.rule_type in ("all", "sql"):
                resp = client.list_sql_alarm_rules(ListSqlAlarmRulesRequest())
                for r in getattr(resp, "sql_alarm_rules", None) or []:
                    rules.append(sql_alarm_rule_summary(r))
            return {
                "mode": "list",
                "rule_type": params.rule_type,
                "count": len(rules),
                "rules": rules,
            }

        # ---- DETAIL mode -------------------------------------------------
        if params.rule_type == "all":
            raise ToolError(
                code="INVALID_PARAMS",
                message=(
                    "rule_type must be 'keyword' or 'sql' when rule_id is set "
                    "(LTS detail endpoints are typed)."
                ),
                hint=(
                    "Call lts_query_alarm_rules() first to discover the "
                    "rule_type of each rule_id, then pass it here."
                ),
            )

        # LTS' SDK has no "get one rule by id" endpoint — we fetch the list
        # for the matching family and filter client-side. This is the same
        # pattern Huawei's own console uses.
        if params.rule_type == "keyword":
            resp = client.list_keywords_alarm_rules(ListKeywordsAlarmRulesRequest())
            items = getattr(resp, "keywords_alarm_rules", None) or []
            id_attr = "keywords_alarm_rule_id"
            serializer = keyword_alarm_rule_detail
        else:  # sql
            resp = client.list_sql_alarm_rules(ListSqlAlarmRulesRequest())
            items = getattr(resp, "sql_alarm_rules", None) or []
            id_attr = "sql_alarm_rule_id"
            serializer = sql_alarm_rule_detail

        match = next(
            (r for r in items if getattr(r, id_attr, None) == params.rule_id),
            None,
        )
        if match is None:
            raise ToolError(
                code="NOT_FOUND",
                message=(
                    f"{params.rule_type} alarm rule {params.rule_id!r} not "
                    f"found in this project."
                ),
                hint=(
                    "Verify the rule_type — keyword rules and SQL rules "
                    "live in separate namespaces."
                ),
            )
        return {
            "mode": "detail",
            "rule_type": params.rule_type,
            "rule": serializer(match),
        }

    @wrap_tool
    def lts_list_alarm_history(
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        state: str = "active",
        alarm_level: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        marker: Optional[str] = None,
    ) -> dict:
        """List recently triggered alarm events (active or historical).

        This is the data source for "what alarms are firing right now /
        fired in the last hour" workflows — feed Slack bots, on-call
        triage, etc.

          * ``state='active'`` — events currently firing.
          * ``state='history'`` — events that have ended / been cleared.

        Time fields take the same humane forms as ``lts_search_logs``.
        Default window: last 1 day.

        Args:
            start_time / end_time: Window bounds. Default last 1d.
            state: 'active' (firing now) or 'history' (past events).
            alarm_level: Optional filter — Critical / Major / Minor / Info.
            search: Free-text search across alarm name / rule id /
                    resource. Forwarded to LTS ``search``.
            limit: Page size, 1..200.
            marker: Cursor from a previous response.

        Returns:
            {
              "state": "active"|"history",
              "total_returned": int,
              "next_marker": str | null,
              "query": { "from_ms", "to_ms", ... },
              "events": [ {event_id, starts_at, event_name,
                            event_severity, log_group_name,
                            log_stream_name, message, ...}, ... ]
            }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListAlarmHistoryInput(
            start_time=start_time,
            end_time=end_time,
            state=state,
            alarm_level=alarm_level,
            search=search,
            limit=limit,
            marker=marker,
        )

        # Resolve window — keep raw ms (LTS expects 13-digit ms here too).
        try:
            to_ms = (
                human_to_epoch_ms(params.end_time, settings.default_timezone)
                if params.end_time
                else now_ms()
            )
            from_ms = (
                human_to_epoch_ms(params.start_time, settings.default_timezone)
                if params.start_time
                else to_ms - 24 * 60 * 60 * 1000
            )
        except ValueError as e:
            raise ToolError(code="TIME_RANGE_INVALID", message=str(e)) from e
        if from_ms >= to_ms:
            raise ToolError(
                code="TIME_RANGE_INVALID",
                message=f"start_time ({from_ms}) must be < end_time ({to_ms})",
            )

        body_kwargs: dict = {
            "start_time": str(from_ms),
            "end_time": str(to_ms),
            "whether_custom_field": True,
        }
        if params.search:
            body_kwargs["search"] = params.search
        if params.alarm_level:
            body_kwargs["alarm_level_ids"] = [
                _SEVERITY_TO_ID[params.alarm_level]
            ]
        body = ListActiveOrHistoryAlarmsRequestBody(**body_kwargs)

        client = get_client("lts", settings)
        resp = client.list_active_or_history_alarms(
            ListActiveOrHistoryAlarmsRequest(
                type=params.state,
                marker=params.marker,
                limit=params.limit,
                body=body,
            )
        )

        events_raw = list(getattr(resp, "events", None) or [])
        events = [alarm_event_summary(e) for e in events_raw]
        page_info = getattr(resp, "page_info", None)
        next_marker = getattr(page_info, "next_marker", None) if page_info else None

        return {
            "state": params.state,
            "total_returned": len(events),
            "next_marker": next_marker,
            "query": {
                "from_ms": from_ms,
                "to_ms": to_ms,
                "alarm_level": params.alarm_level,
                "search": params.search,
                "limit": params.limit,
            },
            "events": events,
        }

    return {
        "lts_query_alarm_rules": lts_query_alarm_rules,
        "lts_list_alarm_history": lts_list_alarm_history,
    }
