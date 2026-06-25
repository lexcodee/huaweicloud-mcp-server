"""Pydantic input models for VPC MCP tools (security groups + network)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# Query (merged: list + describe)
# ============================================================
class QuerySecurityGroupsInput(BaseModel):
    security_group_id: Optional[str] = Field(
        default=None,
        description=(
            "Security group UUID. Set to get detail for one group (includes "
            "full rule list). Omit/empty to list all groups in the project."
        ),
    )
    name: Optional[str] = Field(
        default=None,
        description="List filter — security group name (exact match, case-sensitive).",
    )
    vpc_id: Optional[str] = Field(
        default=None, description="List filter — VPC id."
    )
    enterprise_project_id: Optional[str] = Field(
        default=None,
        description="List filter — enterprise project id ('0' = default).",
    )
    limit: int = Field(
        default=100, ge=1, le=2000,
        description="List page size, default 100.",
    )
    marker: Optional[str] = Field(
        default=None, description="List pagination cursor from a previous response."
    )


class ListSgAssociatedInstancesInput(BaseModel):
    security_group_id: str = Field(..., description="Security group UUID.")


class CheckPortReachabilityInput(BaseModel):
    security_group_id: str = Field(..., description="Security group UUID.")
    protocol: Literal["tcp", "udp", "icmp", "any"] = Field(
        ..., description="Protocol to check."
    )
    port: int = Field(
        ..., ge=0, le=65535,
        description="Port number to check (ignored for icmp).",
    )
    direction: Literal["ingress", "egress"] = Field(
        default="ingress",
        description="Direction to check: ingress (inbound) or egress (outbound).",
    )
    source_ip: Optional[str] = Field(
        default=None,
        description=(
            "Source IP/CIDR to check (e.g. '10.0.0.0/24'). "
            "If omitted, checks whether ANY rule allows the port."
        ),
    )


# ============================================================
# Rules
# ============================================================
class AddSecurityGroupRuleInput(BaseModel):
    security_group_id: str = Field(..., description="Security group UUID.")
    direction: Literal["ingress", "egress"] = Field(
        ..., description="Rule direction."
    )
    protocol: Literal["tcp", "udp", "icmp", "any"] = Field(
        ..., description="Protocol."
    )
    port_range_min: Optional[int] = Field(
        default=None, ge=0, le=65535,
        description="Minimum port (inclusive). Required for tcp/udp unless port_range_max is also set.",
    )
    port_range_max: Optional[int] = Field(
        default=None, ge=0, le=65535,
        description="Maximum port (inclusive). Required for tcp/udp unless port_range_min is also set.",
    )
    remote_ip_prefix: Optional[str] = Field(
        default=None,
        description=(
            "Source/destination IP CIDR (e.g. '0.0.0.0/0' for anywhere, "
            "'10.0.0.0/24' for a subnet). "
            "Mutually exclusive with remote_group_id."
        ),
    )
    remote_group_id: Optional[str] = Field(
        default=None,
        description="Source/destination security group id. Mutually exclusive with remote_ip_prefix.",
    )
    description: Optional[str] = Field(
        default=None, max_length=255,
        description="Human-readable rule description.",
    )


class RemoveSecurityGroupRuleInput(BaseModel):
    security_group_rule_id: str = Field(
        ..., description="Security group rule UUID to delete."
    )


# ============================================================
# Manage (merged: create + clone)
# ============================================================
class CreateSecurityGroupInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Security group name.")
    source_security_group_id: Optional[str] = Field(
        default=None,
        description=(
            "If set, clone all rules from this source SG into the new SG. "
            "If omitted, create a plain SG with default rules only."
        ),
    )
    vpc_id: Optional[str] = Field(
        default=None,
        description=(
            "VPC id for the new SG. If omitted, uses the default VPC (or the "
            "source SG's VPC when cloning)."
        ),
    )
    enterprise_project_id: Optional[str] = Field(
        default=None, description="Enterprise project id for the new SG."
    )


# ============================================================
# Audit
# ============================================================
class AuditSecurityGroupInput(BaseModel):
    security_group_id: str = Field(..., description="Security group UUID to audit.")


# ============================================================
# Approval
# ============================================================
class ConfirmDestructiveInput(BaseModel):
    approval_id: str = Field(
        ...,
        description="The approval_id from a pending destructive operation.",
    )


# ============================================================
# VPC / Subnet / Peering / FlowLog query (merged: list + describe)
# ============================================================
class DescribeVpcsInput(BaseModel):
    vpc_id: Optional[str] = Field(
        default=None,
        description="VPC UUID. Set to get detail for one VPC. Omit/empty to list all.",
    )
    enterprise_project_id: Optional[str] = Field(
        default=None, description="List filter — enterprise project id."
    )
    limit: int = Field(default=100, ge=1, le=2000, description="List page size.")
    marker: Optional[str] = Field(
        default=None, description="Pagination cursor from a previous response."
    )


class DescribeSubnetsInput(BaseModel):
    subnet_id: Optional[str] = Field(
        default=None,
        description="Subnet UUID. Set to get detail for one subnet. Omit/empty to list all.",
    )
    vpc_id: Optional[str] = Field(
        default=None, description="List filter — VPC id."
    )
    limit: int = Field(default=100, ge=1, le=2000, description="List page size.")
    marker: Optional[str] = Field(
        default=None, description="Pagination cursor from a previous response."
    )


class DescribeVpcPeeringsInput(BaseModel):
    peering_id: Optional[str] = Field(
        default=None,
        description="Peering UUID. Set to get detail. Omit/empty to list all.",
    )
    vpc_id: Optional[str] = Field(
        default=None, description="List filter — VPC id (either request or accept side)."
    )
    status: Optional[str] = Field(
        default=None,
        description="List filter — peering status (PENDING_ACCEPTANCE / ACTIVE / REJECTED / DELETED).",
    )
    name: Optional[str] = Field(
        default=None, description="List filter — peering name."
    )
    limit: int = Field(default=100, ge=1, le=2000, description="List page size.")
    marker: Optional[str] = Field(
        default=None, description="Pagination cursor from a previous response."
    )


class ListFlowLogsInput(BaseModel):
    flow_log_id: Optional[str] = Field(
        default=None,
        description="Flow log UUID. Set to get detail. Omit/empty to list all.",
    )
    resource_type: Optional[str] = Field(
        default=None,
        description="List filter — resource type (port / vpc / subnet).",
    )
    resource_id: Optional[str] = Field(
        default=None, description="List filter — resource id (NIC / VPC / subnet)."
    )
    status: Optional[str] = Field(
        default=None, description="List filter — flow log status (ACTIVE / DOWN / ERROR)."
    )
    limit: int = Field(default=100, ge=1, le=2000, description="List page size.")
    marker: Optional[str] = Field(
        default=None, description="Pagination cursor from a previous response."
    )


# ============================================================
# EIP query + manage
# ============================================================
class DescribeEipsInput(BaseModel):
    eip_id: Optional[str] = Field(
        default=None,
        description="EIP UUID. Set to get detail for one EIP. Omit/empty to list all.",
    )
    public_ip_address: Optional[str] = Field(
        default=None, description="List filter — public IP address."
    )
    private_ip_address: Optional[str] = Field(
        default=None, description="List filter — bound private IP address."
    )
    enterprise_project_id: Optional[str] = Field(
        default=None, description="List filter — enterprise project id."
    )
    limit: int = Field(default=100, ge=1, le=2000, description="List page size.")
    marker: Optional[str] = Field(
        default=None, description="Pagination cursor from a previous response."
    )


class AssociateEipInput(BaseModel):
    publicip_id: str = Field(..., description="EIP UUID to bind.")
    port_id: str = Field(
        ...,
        description=(
            "Port UUID of the target resource (ECS NIC, NAT gateway, ELB, etc.). "
            "For an ECS server, this is the port_id of its primary NIC — "
            "find it via ecs_list_servers → server detail → addresses."
        ),
    )


class DisassociateEipInput(BaseModel):
    publicip_id: str = Field(..., description="EIP UUID to unbind.")
    confirm: bool = Field(
        default=False,
        description=(
            "Must be True to execute. Disassociating an EIP immediately "
            "cuts public network access for the bound resource."
        ),
    )


# ============================================================
# Route table query + route manage
# ============================================================
class DescribeRouteTablesInput(BaseModel):
    routetable_id: Optional[str] = Field(
        default=None,
        description="Route table UUID. Set to get detail (includes full route list). Omit/empty to list all.",
    )
    vpc_id: Optional[str] = Field(
        default=None, description="List filter — VPC id."
    )
    subnet_id: Optional[str] = Field(
        default=None, description="List filter — subnet id."
    )
    limit: int = Field(default=100, ge=1, le=2000, description="List page size.")
    marker: Optional[str] = Field(
        default=None, description="Pagination cursor from a previous response."
    )


class AddRouteInput(BaseModel):
    routetable_id: str = Field(..., description="Route table UUID.")
    destination: str = Field(
        ...,
        description="Destination CIDR (e.g. '10.1.0.0/16' for a peered VPC subnet).",
    )
    nexthop: str = Field(
        ...,
        description=(
            "Next hop resource id — a VPC peering id, a VPN gateway id, "
            "a NAT gateway id, or an ECS NIC id."
        ),
    )
    type: str = Field(
        ...,
        description=(
            "Route type. Common values: 'peering' (VPC peering), "
            "'vpn' (VPN gateway), 'nat' (NAT gateway), 'ecs' (ECS NIC)."
        ),
    )
    description: Optional[str] = Field(
        default=None, max_length=255, description="Route description."
    )


class DeleteRouteInput(BaseModel):
    routetable_id: str = Field(..., description="Route table UUID.")
    destination: str = Field(..., description="Destination CIDR of the route to delete.")
    nexthop: str = Field(..., description="Next hop id of the route to delete.")
    type: str = Field(..., description="Route type of the route to delete.")


# ============================================================
# Flow log data query
# ============================================================
class QueryFlowLogDataInput(BaseModel):
    flow_log_id: str = Field(..., description="Flow log UUID (from list_flow_logs).")
    start_time: str = Field(
        default="-1h",
        description="Window start. Relative ('-1h', '-30m', '-2d') or ISO8601.",
    )
    end_time: str = Field(default="now", description="Window end.")
    src_ip: Optional[str] = Field(
        default=None, description="Filter by source IP address."
    )
    dst_ip: Optional[str] = Field(
        default=None, description="Filter by destination IP address."
    )
    dst_port: Optional[int] = Field(
        default=None, ge=0, le=65535, description="Filter by destination port."
    )
    action: Optional[Literal["accept", "reject"]] = Field(
        default=None,
        description="Filter by action: 'accept' (allowed) or 'reject' (denied).",
    )
    limit: int = Field(default=100, ge=1, le=500, description="Max records to return.")
