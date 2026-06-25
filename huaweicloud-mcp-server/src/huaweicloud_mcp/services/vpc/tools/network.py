"""Read-only VPC network query tools: VPCs, subnets, peerings, flow logs.

Each tool merges list + describe into a single entrypoint dispatched by an
optional id parameter — same pattern as vpc_query_security_groups.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkvpc.v2 import (
    ListFlowLogsRequest,
    ListSubnetsRequest,
    ListVpcPeeringsRequest,
    ListVpcsRequest,
    ShowFlowLogRequest,
    ShowSubnetRequest,
    ShowVpcPeeringRequest,
    ShowVpcRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import (
    DescribeSubnetsInput,
    DescribeVpcPeeringsInput,
    DescribeVpcsInput,
    ListFlowLogsInput,
)
from ..serializers import (
    flow_log_detail,
    flow_log_summary,
    subnet_detail,
    subnet_summary,
    vpc_detail,
    vpc_peering_detail,
    vpc_peering_summary,
    vpc_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.vpc.tools.network")


def make_network_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # describe_vpcs  (merged: list + describe)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_describe_vpcs(
        vpc_id: Optional[str] = None,
        enterprise_project_id: Optional[str] = None,
        limit: int = 100,
        marker: Optional[str] = None,
    ) -> dict:
        """List VPCs, or fetch one VPC's detail.

        Dispatches based on ``vpc_id``:

          * ``vpc_id`` is None/empty → LIST mode. Returns a compact list of
            VPCs in the project (id, name, cidr, status, enterprise_project_id).
          * ``vpc_id`` is set → DETAIL mode. Returns full info for one VPC
            including its route entries.

        Args:
            vpc_id: VPC UUID; omit/empty to list.
            enterprise_project_id: List filter — enterprise project id.
            limit: List page size, default 100.
            marker: Pagination cursor from a previous response.

        Returns:
            LIST mode:   {"vpcs": [...], "count": N}
            DETAIL mode: {id, name, cidr, status, routes: [...], ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeVpcsInput(
            vpc_id=vpc_id,
            enterprise_project_id=enterprise_project_id,
            limit=limit,
            marker=marker,
        )
        client = get_client("vpc", settings)

        if params.vpc_id:
            resp = client.show_vpc(ShowVpcRequest(vpc_id=params.vpc_id))
            if resp.vpc is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"VPC {params.vpc_id} not found",
                )
            return vpc_detail(resp.vpc)

        req = ListVpcsRequest(
            limit=params.limit,
            marker=params.marker,
            enterprise_project_id=params.enterprise_project_id,
        )
        resp = client.list_vpcs(req)
        vpcs = [vpc_summary(v) for v in (resp.vpcs or [])]
        return {"vpcs": vpcs, "count": len(vpcs)}

    # ------------------------------------------------------------------ #
    # describe_subnets  (merged: list + describe)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_describe_subnets(
        subnet_id: Optional[str] = None,
        vpc_id: Optional[str] = None,
        limit: int = 100,
        marker: Optional[str] = None,
    ) -> dict:
        """List subnets, or fetch one subnet's detail.

        Dispatches based on ``subnet_id``:

          * ``subnet_id`` is None/empty → LIST mode. Returns subnets with
            cidr, AZ, available_ip_address_count, gateway_ip, vpc_id.
          * ``subnet_id`` is set → DETAIL mode. Returns full info for one
            subnet.

        Args:
            subnet_id: Subnet UUID; omit/empty to list.
            vpc_id: List filter — VPC id.
            limit: List page size, default 100.
            marker: Pagination cursor.

        Returns:
            LIST mode:   {"subnets": [...], "count": N}
            DETAIL mode: {id, name, cidr, available_ip_address_count, ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeSubnetsInput(
            subnet_id=subnet_id, vpc_id=vpc_id, limit=limit, marker=marker,
        )
        client = get_client("vpc", settings)

        if params.subnet_id:
            resp = client.show_subnet(ShowSubnetRequest(subnet_id=params.subnet_id))
            if resp.subnet is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"subnet {params.subnet_id} not found",
                )
            return subnet_detail(resp.subnet)

        req = ListSubnetsRequest(
            limit=params.limit, marker=params.marker, vpc_id=params.vpc_id,
        )
        resp = client.list_subnets(req)
        subnets = [subnet_summary(s) for s in (resp.subnets or [])]
        return {"subnets": subnets, "count": len(subnets)}

    # ------------------------------------------------------------------ #
    # describe_vpc_peerings  (merged: list + describe)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_describe_vpc_peerings(
        peering_id: Optional[str] = None,
        vpc_id: Optional[str] = None,
        status: Optional[str] = None,
        name: Optional[str] = None,
        limit: int = 100,
        marker: Optional[str] = None,
    ) -> dict:
        """List VPC peerings, or fetch one peering's detail.

        Dispatches based on ``peering_id``:

          * ``peering_id`` is None/empty → LIST mode. Returns peerings with
            id, name, status, request_vpc_id, accept_vpc_id.
          * ``peering_id`` is set → DETAIL mode. Returns full info for one
            peering connection.

        Peering status values: PENDING_ACCEPTANCE, ACTIVE, REJECTED, DELETED.

        Args:
            peering_id: Peering UUID; omit/empty to list.
            vpc_id: List filter — VPC id (either request or accept side).
            status: List filter — peering status.
            name: List filter — peering name.
            limit: List page size, default 100.
            marker: Pagination cursor.

        Returns:
            LIST mode:   {"peerings": [...], "count": N}
            DETAIL mode: {id, name, status, request_vpc_id, accept_vpc_id, ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeVpcPeeringsInput(
            peering_id=peering_id, vpc_id=vpc_id, status=status,
            name=name, limit=limit, marker=marker,
        )
        client = get_client("vpc", settings)

        if params.peering_id:
            resp = client.show_vpc_peering(
                ShowVpcPeeringRequest(peering_id=params.peering_id)
            )
            if resp.peering is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"VPC peering {params.peering_id} not found",
                )
            return vpc_peering_detail(resp.peering)

        req = ListVpcPeeringsRequest(
            limit=params.limit, marker=params.marker,
            vpc_id=params.vpc_id, status=params.status, name=params.name,
        )
        resp = client.list_vpc_peerings(req)
        peerings = [vpc_peering_summary(p) for p in (resp.peerings or [])]
        return {"peerings": peerings, "count": len(peerings)}

    # ------------------------------------------------------------------ #
    # list_flow_logs  (merged: list + describe)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_list_flow_logs(
        flow_log_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        marker: Optional[str] = None,
    ) -> dict:
        """List VPC flow log configurations, or fetch one flow log's detail.

        Dispatches based on ``flow_log_id``:

          * ``flow_log_id`` is None/empty → LIST mode. Returns flow log
            configs with id, name, resource_type, resource_id,
            log_group_id, log_topic_id, status.
          * ``flow_log_id`` is set → DETAIL mode. Returns full info for
            one flow log config.

        Use vpc_query_flow_log_data to query the actual log records.

        Args:
            flow_log_id: Flow log UUID; omit/empty to list.
            resource_type: List filter — 'port', 'vpc', or 'subnet'.
            resource_id: List filter — resource id (NIC / VPC / subnet).
            status: List filter — flow log status (ACTIVE / DOWN / ERROR).
            limit: List page size, default 100.
            marker: Pagination cursor.

        Returns:
            LIST mode:   {"flow_logs": [...], "count": N}
            DETAIL mode: {id, name, resource_type, resource_id, ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListFlowLogsInput(
            flow_log_id=flow_log_id, resource_type=resource_type,
            resource_id=resource_id, status=status,
            limit=limit, marker=marker,
        )
        client = get_client("vpc", settings)

        if params.flow_log_id:
            resp = client.show_flow_log(
                ShowFlowLogRequest(flowlog_id=params.flow_log_id)
            )
            if resp.flow_log is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"flow log {params.flow_log_id} not found",
                )
            return flow_log_detail(resp.flow_log)

        req = ListFlowLogsRequest(
            limit=params.limit, marker=params.marker,
            resource_type=params.resource_type,
            resource_id=params.resource_id,
            status=params.status,
        )
        resp = client.list_flow_logs(req)
        flow_logs = [flow_log_summary(f) for f in (resp.flow_logs or [])]
        return {"flow_logs": flow_logs, "count": len(flow_logs)}

    return {
        "vpc_describe_vpcs": vpc_describe_vpcs,
        "vpc_describe_subnets": vpc_describe_subnets,
        "vpc_describe_vpc_peerings": vpc_describe_vpc_peerings,
        "vpc_list_flow_logs": vpc_list_flow_logs,
    }
