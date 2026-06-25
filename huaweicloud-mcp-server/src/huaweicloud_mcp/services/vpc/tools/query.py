"""Read-only VPC security-group query and audit tools."""
from __future__ import annotations

import ipaddress
import logging
from typing import Optional

from huaweicloudsdkecs.v2 import ListServersDetailsRequest
from huaweicloudsdkvpc.v2 import (
    ListSecurityGroupsRequest,
    ShowSecurityGroupRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import (
    AuditSecurityGroupInput,
    CheckPortReachabilityInput,
    ListSgAssociatedInstancesInput,
    QuerySecurityGroupsInput,
)
from ..serializers import (
    rule_summary,
    security_group_detail,
    security_group_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.vpc.tools.query")

# Ports considered sensitive for audit — open to 0.0.0.0/0 = high risk.
SENSITIVE_PORTS = {
    22: "SSH",
    3389: "RDP",
    3306: "MySQL",
    6379: "Redis",
    27017: "MongoDB",
    9200: "Elasticsearch",
    5432: "PostgreSQL",
    1433: "SQL Server",
    11211: "Memcached",
    2375: "Docker daemon (unencrypted)",
}


def make_query_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # query_security_groups  (merged: list + describe)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_query_security_groups(
        security_group_id: Optional[str] = None,
        name: Optional[str] = None,
        vpc_id: Optional[str] = None,
        enterprise_project_id: Optional[str] = None,
        limit: int = 100,
        marker: Optional[str] = None,
    ) -> dict:
        """List security groups, or fetch one group's detail.

        Dispatches based on ``security_group_id``:

          * ``security_group_id`` is None/empty → LIST mode. Returns a compact
            list of security groups in the project, each with its full rule
            list. Optional filters: name, vpc_id, enterprise_project_id.
          * ``security_group_id`` is set → DETAIL mode. Returns full info for
            one group (id, name, vpc_id, description, security_group_rules).
            Filters are ignored.

        Args:
            security_group_id: Group UUID; omit/empty to list.
            name: List filter — group name (exact match, case-sensitive).
            vpc_id: List filter — VPC id.
            enterprise_project_id: List filter — enterprise project id.
            limit: List page size, default 100.
            marker: List pagination cursor from a previous response.

        Returns:
            LIST mode:   {"security_groups": [...], "count": N}
            DETAIL mode: {id, name, vpc_id, description, security_group_rules: [...]}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QuerySecurityGroupsInput(
            security_group_id=security_group_id,
            name=name, vpc_id=vpc_id,
            enterprise_project_id=enterprise_project_id,
            limit=limit, marker=marker,
        )
        client = get_client("vpc", settings)

        # ---- DETAIL mode ----
        if params.security_group_id:
            resp = client.show_security_group(
                ShowSecurityGroupRequest(security_group_id=params.security_group_id)
            )
            if resp.security_group is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"security group {params.security_group_id} not found",
                )
            return security_group_detail(resp.security_group)

        # ---- LIST mode ----
        req = ListSecurityGroupsRequest(
            limit=params.limit,
            marker=params.marker,
            vpc_id=params.vpc_id,
            enterprise_project_id=params.enterprise_project_id,
        )
        resp = client.list_security_groups(req)
        groups = [security_group_summary(sg) for sg in (resp.security_groups or [])]

        # Client-side name filter (v2 API has no name param).
        if params.name:
            groups = [g for g in groups if g.get("name") == params.name]

        return {"security_groups": groups, "count": len(groups)}

    # ------------------------------------------------------------------ #
    # list_sg_associated_instances
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_list_sg_associated_instances(security_group_id: str) -> dict:
        """List ECS servers associated with a security group.

        Scans all ECS servers in the project and returns those whose
        security-group set includes the given id. Useful for assessing
        blast radius before deleting or modifying a rule.

        Args:
            security_group_id: Security group UUID.

        Returns:
            {"instances": [{id, name, status, ...}], "count": N}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListSgAssociatedInstancesInput(security_group_id=security_group_id)
        ecs_client = get_client("ecs", settings)

        matched: list[dict] = []
        offset = 1
        page_size = 100
        while True:
            resp = ecs_client.list_servers_details(
                ListServersDetailsRequest(limit=page_size, offset=offset)
            )
            for s in (resp.servers or []):
                sg_list = getattr(s, "security_groups", None) or []
                sg_ids = {
                    getattr(g, "id", None) or (g.get("id") if isinstance(g, dict) else None)
                    for g in sg_list
                }
                if params.security_group_id in sg_ids:
                    matched.append({
                        "id": getattr(s, "id", None),
                        "name": getattr(s, "name", None),
                        "status": getattr(s, "status", None),
                    })
            total = resp.count if resp.count is not None else len(resp.servers or [])
            if offset * page_size >= total or not resp.servers:
                break
            offset += 1

        return {"instances": matched, "count": len(matched)}

    # ------------------------------------------------------------------ #
    # check_port_reachability
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_check_port_reachability(
        security_group_id: str,
        protocol: str,
        port: int,
        direction: str = "ingress",
        source_ip: Optional[str] = None,
    ) -> dict:
        """Check whether traffic on a given protocol/port is allowed by a SG.

        Returns the matching rule(s) if allowed, or a denial result if not.

        Args:
            security_group_id: Security group UUID.
            protocol: 'tcp', 'udp', 'icmp', or 'any'.
            port: Port number (0-65535, ignored for icmp).
            direction: 'ingress' (inbound) or 'egress' (outbound).
            source_ip: Source IP/CIDR to check. If omitted, checks whether
                       ANY rule allows the port regardless of source.

        Returns:
            {"allowed": bool, "matched_rules": [...]}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = CheckPortReachabilityInput(
            security_group_id=security_group_id,
            protocol=protocol,
            port=port,
            direction=direction,
            source_ip=source_ip,
        )
        client = get_client("vpc", settings)

        resp = client.show_security_group(
            ShowSecurityGroupRequest(security_group_id=params.security_group_id)
        )
        if resp.security_group is None:
            raise ToolError(
                code="NOT_FOUND",
                message=f"security group {params.security_group_id} not found",
            )

        rules = getattr(resp.security_group, "security_group_rules", None) or []
        matched = []

        for rule in rules:
            r_dir = getattr(rule, "direction", None)
            r_proto = (getattr(rule, "protocol", None) or "").lower()
            r_min = getattr(rule, "port_range_min", None)
            r_max = getattr(rule, "port_range_max", None)
            r_cidr = getattr(rule, "remote_ip_prefix", None)

            if r_dir != params.direction:
                continue

            # Protocol match: 'any' rule matches everything; exact match otherwise.
            proto_ok = (
                r_proto in ("", "any", params.protocol)
                or params.protocol == "any"
            )
            if not proto_ok:
                continue

            # Port match (skip for icmp).
            if params.protocol != "icmp" and r_min is not None and r_max is not None:
                if not (r_min <= params.port <= r_max):
                    continue

            # Source IP match.
            if params.source_ip and r_cidr:
                if not _cidr_contains(r_cidr, params.source_ip):
                    continue

            matched.append(rule_summary(rule))

        return {"allowed": len(matched) > 0, "matched_rules": matched}

    # ------------------------------------------------------------------ #
    # audit_security_group
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_audit_security_group(security_group_id: str) -> dict:
        """Audit a security group for high-risk rules.

        Flags rules that expose sensitive ports (SSH, RDP, MySQL, Redis, etc.)
        to 0.0.0.0/0 (the entire internet).

        Args:
            security_group_id: Security group UUID.

        Returns:
            {"risk_level": "high"|"medium"|"none", "findings": [...]}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = AuditSecurityGroupInput(security_group_id=security_group_id)
        client = get_client("vpc", settings)

        resp = client.show_security_group(
            ShowSecurityGroupRequest(security_group_id=params.security_group_id)
        )
        if resp.security_group is None:
            raise ToolError(
                code="NOT_FOUND",
                message=f"security group {params.security_group_id} not found",
            )

        sg_name = getattr(resp.security_group, "name", None)
        rules = getattr(resp.security_group, "security_group_rules", None) or []
        findings: list[dict] = []

        for rule in rules:
            r_dir = getattr(rule, "direction", None)
            r_cidr = getattr(rule, "remote_ip_prefix", None)
            r_min = getattr(rule, "port_range_min", None)
            r_max = getattr(rule, "port_range_max", None)
            r_proto = (getattr(rule, "protocol", None) or "").lower()

            # Only ingress rules from 0.0.0.0/0 are high-risk.
            if r_dir != "ingress" or r_cidr != "0.0.0.0/0":
                continue

            # Check each port in the rule's range against sensitive ports.
            if r_min is not None and r_max is not None:
                for port in range(r_min, r_max + 1):
                    if port in SENSITIVE_PORTS:
                        findings.append({
                            "rule_id": getattr(rule, "id", None),
                            "protocol": r_proto or "any",
                            "port": port,
                            "service": SENSITIVE_PORTS[port],
                            "direction": "ingress",
                            "source": "0.0.0.0/0",
                            "severity": "high",
                            "message": (
                                f"{SENSITIVE_PORTS[port]} (port {port}) is open "
                                f"to the entire internet (0.0.0.0/0)"
                            ),
                        })
            # ICMP open to the world — medium risk.
            if r_proto == "icmp":
                findings.append({
                    "rule_id": getattr(rule, "id", None),
                    "protocol": "icmp",
                    "port": None,
                    "service": "ICMP",
                    "direction": "ingress",
                    "source": "0.0.0.0/0",
                    "severity": "medium",
                    "message": "ICMP is open to the entire internet (0.0.0.0/0)",
                })

        risk_level = "none"
        if any(f["severity"] == "high" for f in findings):
            risk_level = "high"
        elif any(f["severity"] == "medium" for f in findings):
            risk_level = "medium"

        return {
            "security_group_id": params.security_group_id,
            "security_group_name": sg_name,
            "risk_level": risk_level,
            "findings": findings,
            "rules_total": len(rules),
        }

    return {
        "vpc_query_security_groups": vpc_query_security_groups,
        "vpc_list_sg_associated_instances": vpc_list_sg_associated_instances,
        "vpc_check_port_reachability": vpc_check_port_reachability,
        "vpc_audit_security_group": vpc_audit_security_group,
    }


def _cidr_contains(cidr: str, ip: str) -> bool:
    """Check whether *ip* falls within *cidr*.

    Returns True if either value is not a valid address/CIDR (fail-open
    to avoid false negatives in reachability checks).
    """
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        addr = ipaddress.ip_address(ip)
        return addr in network
    except (ValueError, TypeError):
        return True
