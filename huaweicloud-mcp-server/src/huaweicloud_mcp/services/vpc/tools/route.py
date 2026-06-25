"""VPC route table tools: list/describe, add route, delete route.

delete_route is DESTRUCTIVE and uses two-phase commit:
  Phase 1: call → returns preview + approval_id (no execution)
  Phase 2: user approves → call vpc_confirm_destructive(approval_id)
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkvpc.v2 import (
    ListRouteTablesRequest,
    ShowRouteTableRequest,
    UpdateRouteTableRequest,
)
from huaweicloudsdkvpc.v2.model import (
    AddRouteTableRoute,
    DelRouteTableRoute,
    RouteTableRouteAction,
    UpdateRouteTableReq,
    UpdateRoutetableReqBody,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, pending_actions, wrap_tool
from ..models import (
    AddRouteInput,
    DeleteRouteInput,
    DescribeRouteTablesInput,
)
from ..serializers import route_table_detail, route_table_summary

log = logging.getLogger("huaweicloud_mcp.services.vpc.tools.route")


def make_route_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # describe_route_tables  (merged: list + describe)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_describe_route_tables(
        routetable_id: Optional[str] = None,
        vpc_id: Optional[str] = None,
        subnet_id: Optional[str] = None,
        limit: int = 100,
        marker: Optional[str] = None,
    ) -> dict:
        """List route tables, or fetch one route table's detail.

        Dispatches based on ``routetable_id``:

          * ``routetable_id`` is None/empty → LIST mode. Returns route
            tables with id, name, vpc_id, default flag, associated subnets.
            Does NOT include route entries (use DETAIL mode for that).
          * ``routetable_id`` is set → DETAIL mode. Returns full info
            including all route entries (destination, nexthop, type).

        Args:
            routetable_id: Route table UUID; omit/empty to list.
            vpc_id: List filter — VPC id.
            subnet_id: List filter — subnet id.
            limit: List page size, default 100.
            marker: Pagination cursor.

        Returns:
            LIST mode:   {"route_tables": [...], "count": N}
            DETAIL mode: {id, name, vpc_id, subnets, routes: [...], ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeRouteTablesInput(
            routetable_id=routetable_id, vpc_id=vpc_id,
            subnet_id=subnet_id, limit=limit, marker=marker,
        )
        client = get_client("vpc", settings)

        if params.routetable_id:
            resp = client.show_route_table(
                ShowRouteTableRequest(routetable_id=params.routetable_id)
            )
            if resp.routetable is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"route table {params.routetable_id} not found",
                )
            return route_table_detail(resp.routetable)

        req = ListRouteTablesRequest(
            limit=params.limit, marker=params.marker,
            vpc_id=params.vpc_id, subnet_id=params.subnet_id,
        )
        resp = client.list_route_tables(req)
        tables = [route_table_summary(rt) for rt in (resp.routetables or [])]
        return {"route_tables": tables, "count": len(tables)}

    # ------------------------------------------------------------------ #
    # add_route
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_add_route(
        routetable_id: str,
        destination: str,
        nexthop: str,
        type: str,
        description: Optional[str] = None,
    ) -> dict:
        """Add a custom route entry to a route table.

        Executes immediately. Common use cases:
          - Add a route to a VPC peering connection (type='peering')
          - Add a route to a VPN gateway (type='vpn')
          - Add a route to a NAT gateway (type='nat')
          - Add a route to an ECS NIC (type='ecs')

        Args:
            routetable_id: Route table UUID.
            destination: Destination CIDR (e.g. '10.1.0.0/16').
            nexthop: Next hop resource id (peering id, VPN gateway id, etc.).
            type: Route type ('peering', 'vpn', 'nat', 'ecs').
            description: Optional route description.

        Returns:
            {id, name, vpc_id, routes: [...]} — the updated route table.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = AddRouteInput(
            routetable_id=routetable_id, destination=destination,
            nexthop=nexthop, type=type, description=description,
        )
        client = get_client("vpc", settings)

        add_entry = AddRouteTableRoute(
            type=params.type,
            destination=params.destination,
            nexthop=params.nexthop,
            description=params.description,
        )
        body = UpdateRoutetableReqBody(
            routetable=UpdateRouteTableReq(
                routes=RouteTableRouteAction(add=[add_entry])
            )
        )
        resp = client.update_route_table(
            UpdateRouteTableRequest(routetable_id=params.routetable_id, body=body)
        )
        return route_table_detail(resp.routetable)

    # ------------------------------------------------------------------ #
    # delete_route  (DESTRUCTIVE — two-phase)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_delete_route(
        routetable_id: str,
        destination: str,
        nexthop: str,
        type: str,
    ) -> dict:
        """⚠ DESTRUCTIVE: delete a route entry from a route table.

        Removing a route may break connectivity to the destination network.
        This is a TWO-PHASE operation: returns a preview + approval_id.
        Use vpc_confirm_destructive to execute after user approval.

        Args:
            routetable_id: Route table UUID.
            destination: Destination CIDR of the route to delete.
            nexthop: Next hop id of the route to delete.
            type: Route type of the route to delete.

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = DeleteRouteInput(
            routetable_id=routetable_id, destination=destination,
            nexthop=nexthop, type=type,
        )
        client = get_client("vpc", settings)

        action_label = (
            f"vpc_delete_route(routetable_id={params.routetable_id}, "
            f"destination={params.destination}, nexthop={params.nexthop})"
        )

        def _execute() -> dict:
            del_entry = DelRouteTableRoute(
                type=params.type,
                destination=params.destination,
                nexthop=params.nexthop,
            )
            body = UpdateRoutetableReqBody(
                routetable=UpdateRouteTableReq(
                    routes=RouteTableRouteAction(_del=[del_entry])
                )
            )
            client.update_route_table(
                UpdateRouteTableRequest(
                    routetable_id=params.routetable_id, body=body,
                )
            )
            return {
                "deleted": True,
                "routetable_id": params.routetable_id,
                "destination": params.destination,
                "nexthop": params.nexthop,
            }

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "delete_route",
                "routetable_id": params.routetable_id,
                "destination": params.destination,
                "nexthop": params.nexthop,
                "type": params.type,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "delete_route",
            "routetable_id": params.routetable_id,
            "destination": params.destination,
            "nexthop": params.nexthop,
            "type": params.type,
            "message": (
                f"⚠ Deleting this route may break connectivity to "
                f"{params.destination}. Present this preview to the user "
                f"and ask for explicit approval. If approved, call "
                f"vpc_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    return {
        "vpc_describe_route_tables": vpc_describe_route_tables,
        "vpc_add_route": vpc_add_route,
        "vpc_delete_route": vpc_delete_route,
    }
