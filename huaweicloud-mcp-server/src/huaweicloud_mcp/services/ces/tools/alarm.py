"""CES alarm tools — alarm rules and alarm histories.

Two tools:
  * ``ces_query_alarm_rules`` — list alarm rules, or fetch one rule's detail
    (including policies and associated resources). Uses the v2 SDK.
    Mirrors the CCE list/detail dispatch pattern.
  * ``ces_list_alarm_histories`` — query alarm history records.
    Uses the v2 SDK.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkces.v2 import (
    ListAlarmHistoriesRequest,
    ListAlarmRulePoliciesRequest,
    ListAlarmRuleResourcesRequest,
    ListAlarmRulesRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from .._time import resolve_time_window
from ..models import ListAlarmHistoriesInput, QueryAlarmRulesInput
from ..serializers import alarm_history_summary, alarm_rule_detail, alarm_rule_summary

log = logging.getLogger("huaweicloud_mcp.services.ces.tools.alarm")


def make_alarm_tools(settings: Settings) -> dict:
    """Build CES alarm tools bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def ces_query_alarm_rules(
        alarm_id: Optional[str] = None,
        namespace: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> dict:
        """List CES alarm rules, or fetch one rule's detail.

        Dispatches based on ``alarm_id``:

          * ``alarm_id`` is None/empty  → LIST mode. Returns a compact
            list of alarm rules with optional filters (namespace/name/status).

          * ``alarm_id`` is set         → DETAIL mode. Returns full rule
            info including policies (threshold, period, comparison operator,
            aggregation) and associated resources (resource group, dimensions).

        Args:
            alarm_id: Alarm rule id; omit/empty to list.
            namespace: List filter — service namespace, e.g. 'SYS.ECS'.
            name: List filter — alarm name (fuzzy match).
            status: List filter — alarm status (ok/alarm/invalid).
            limit: Page size (1..100).
            offset: Page offset.

        Returns:
            LIST mode:   {"alarms": [...], "count": N}
            DETAIL mode: see serializers.alarm_rule_detail
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryAlarmRulesInput(
            alarm_id=alarm_id,
            namespace=namespace,
            name=name,
            status=status,
            limit=limit,
            offset=offset,
        )
        client = get_client("ces", settings)

        # ---- LIST mode ---------------------------------------------------
        if params.alarm_id is None or params.alarm_id == "":
            req = ListAlarmRulesRequest(
                namespace=params.namespace,
                name=params.name,
                limit=params.limit,
                offset=params.offset,
            )
            resp = client.list_alarm_rules(req)
            items = list(getattr(resp, "alarms", None) or [])
            alarms = [alarm_rule_summary(a) for a in items]
            return {"count": len(alarms), "alarms": alarms}

        # ---- DETAIL mode -------------------------------------------------
        # Fetch the alarm rule from the list (CES v2 has no show-alarm-by-id)
        req = ListAlarmRulesRequest(alarm_id=params.alarm_id)
        resp = client.list_alarm_rules(req)
        items = list(getattr(resp, "alarms", None) or [])
        match = next(
            (a for a in items if getattr(a, "alarm_id", None) == params.alarm_id),
            None,
        )
        if match is None:
            raise ToolError(
                code="NOT_FOUND",
                message=f"alarm rule {params.alarm_id!r} not found",
            )

        # Fetch policies for this alarm rule
        policies_raw: list = []
        try:
            pol_resp = client.list_alarm_rule_policies(
                ListAlarmRulePoliciesRequest(alarm_id=params.alarm_id)
            )
            policies_raw = list(getattr(pol_resp, "policies", None) or [])
        except Exception:
            log.debug("could not fetch policies for alarm %s", params.alarm_id, exc_info=True)

        # Fetch resources for this alarm rule
        resources_raw: list = []
        try:
            res_resp = client.list_alarm_rule_resources(
                ListAlarmRuleResourcesRequest(alarm_id=params.alarm_id)
            )
            resources_raw = list(getattr(res_resp, "resources", None) or [])
        except Exception:
            log.debug("could not fetch resources for alarm %s", params.alarm_id, exc_info=True)

        return alarm_rule_detail(match, policies=policies_raw, resources=resources_raw)

    @wrap_tool
    def ces_list_alarm_histories(
        alarm_id: Optional[str] = None,
        status: Optional[str] = None,
        level: Optional[int] = None,
        namespace: Optional[str] = None,
        name: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> dict:
        """Query CES alarm history records.

        This is the data source for incident post-mortems — "what alarms
        fired in the last N hours/days" workflows.

        Args:
            alarm_id: Filter by alarm rule id.
            status: Filter by status (ok/alarm/invalid/insufficient_data).
            level: Filter by severity (1=Critical, 2=Major, 3=Minor, 4=Info).
            namespace: Filter by namespace, e.g. 'SYS.ECS'.
            name: Filter by alarm name.
            from_time: Window start. Default '-7d'.
            to_time: Window end. Default 'now'.
            limit: Page size (1..100).
            offset: Page offset.

        Returns:
            {
              "alarm_histories": [...],
              "count": N,
              "query": {"from_ms": ..., "to_ms": ..., ...}
            }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListAlarmHistoriesInput(
            alarm_id=alarm_id,
            status=status,
            level=level,
            namespace=namespace,
            name=name,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
            offset=offset,
        )

        # Resolve time window
        from_ms, to_ms = resolve_time_window(
            params.from_time, params.to_time,
            default_from="-7d",
            settings=settings,
        )

        client = get_client("ces", settings)
        req = ListAlarmHistoriesRequest(
            alarm_id=params.alarm_id,
            status=params.status,
            level=params.level,
            namespace=params.namespace,
            name=params.name,
            limit=params.limit,
            offset=params.offset,
        )
        # CES v2 ListAlarmHistoriesRequest uses create_time_from/to for time filter
        req.create_time_from = from_ms
        req.create_time_to = to_ms

        resp = client.list_alarm_histories(req)
        items = list(getattr(resp, "alarm_histories", None) or [])
        histories = [alarm_history_summary(h) for h in items]

        return {
            "alarm_histories": histories,
            "count": len(histories),
            "query": {
                "from_ms": from_ms,
                "to_ms": to_ms,
                "alarm_id": params.alarm_id,
                "status": params.status,
                "level": params.level,
                "namespace": params.namespace,
            },
        }

    return {
        "ces_query_alarm_rules": ces_query_alarm_rules,
        "ces_list_alarm_histories": ces_list_alarm_histories,
    }
