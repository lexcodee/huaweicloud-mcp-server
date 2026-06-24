"""CES resource group tools — list/detail dispatch.

Single tool:
  * ``ces_query_resource_groups`` — list resource groups, or fetch one
    group's detail (including resources). Uses the v2 SDK.
    Mirrors the CCE list/detail dispatch pattern.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkces.v2 import (
    ListResourceGroupsRequest,
    ListResourceGroupsServicesResourcesRequest,
    ShowResourceGroupRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import QueryResourceGroupsInput
from ..serializers import resource_group_detail, resource_group_summary

log = logging.getLogger("huaweicloud_mcp.services.ces.tools.resource_group")


def make_resource_group_tools(settings: Settings) -> dict:
    """Build CES resource group tools bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def ces_query_resource_groups(
        group_id: Optional[str] = None,
        group_name: Optional[str] = None,
        status: Optional[str] = None,
        type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> dict:
        """List CES resource groups, or fetch one group's detail.

        Dispatches based on ``group_id``:

          * ``group_id`` is None/empty  → LIST mode. Returns a compact
            list of resource groups with optional filters.

          * ``group_id`` is set         → DETAIL mode. Returns full
            group info including the resources (instances) in the group.

        Args:
            group_id: Resource group id; omit/empty to list.
            group_name: List filter — group name.
            status: List filter — health status
                    (health/unhealthy/no_alarm_rule).
            type: List filter — group type (EPS/custom).
            limit: Page size (1..100).
            offset: Page offset.

        Returns:
            LIST mode:   {"resource_groups": [...], "count": N}
            DETAIL mode: see serializers.resource_group_detail
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryResourceGroupsInput(
            group_id=group_id,
            group_name=group_name,
            status=status,
            type=type,
            limit=limit,
            offset=offset,
        )
        client = get_client("ces", settings)

        # ---- LIST mode ---------------------------------------------------
        if params.group_id is None or params.group_id == "":
            req = ListResourceGroupsRequest(
                group_name=params.group_name,
                status=params.status,
                type=params.type,
                limit=params.limit,
                offset=params.offset,
            )
            resp = client.list_resource_groups(req)
            items = list(getattr(resp, "resource_groups", None) or [])
            groups = [resource_group_summary(g) for g in items]
            return {"count": len(groups), "resource_groups": groups}

        # ---- DETAIL mode -------------------------------------------------
        req = ShowResourceGroupRequest(group_id=params.group_id)
        resp = client.show_resource_group(req)

        # Fetch resources in this group
        resources_raw: list = []
        try:
            res_resp = client.list_resource_groups_services_resources(
                ListResourceGroupsServicesResourcesRequest(
                    group_id=params.group_id,
                )
            )
            resources_raw = list(getattr(res_resp, "resources", None) or [])
        except Exception:
            log.debug(
                "could not fetch resources for group %s",
                params.group_id, exc_info=True,
            )

        return resource_group_detail(resp, resources=resources_raw)

    return {"ces_query_resource_groups": ces_query_resource_groups}
