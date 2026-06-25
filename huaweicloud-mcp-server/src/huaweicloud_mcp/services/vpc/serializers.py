"""Convert VPC SDK response objects to compact JSON-friendly dicts."""
from __future__ import annotations

from typing import Any


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _drop_nulls(d: dict) -> dict:
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != [] and v != {} and v != ""
    }


def rule_summary(r: Any) -> dict:
    """Compact security-group rule view."""
    return _drop_nulls(
        {
            "id": _get(r, "id"),
            "direction": _get(r, "direction"),
            "protocol": _get(r, "protocol"),
            "port_range_min": _get(r, "port_range_min"),
            "port_range_max": _get(r, "port_range_max"),
            "remote_ip_prefix": _get(r, "remote_ip_prefix"),
            "remote_group_id": _get(r, "remote_group_id"),
            "remote_address_group_id": _get(r, "remote_address_group_id"),
            "description": _get(r, "description"),
            "ethertype": _get(r, "ethertype"),
            "security_group_id": _get(r, "security_group_id"),
        }
    )


def security_group_summary(sg: Any) -> dict:
    """Compact security-group view for list responses.

    Includes the full rules list because Huawei Cloud's v2 ListSecurityGroups
    response embeds rules in each group — dropping them would force a second
    API call per group for no benefit.
    """
    return _drop_nulls(
        {
            "id": _get(sg, "id"),
            "name": _get(sg, "name"),
            "vpc_id": _get(sg, "vpc_id"),
            "enterprise_project_id": _get(sg, "enterprise_project_id"),
            "description": _get(sg, "description"),
            "security_group_rules": [
                rule_summary(r) for r in (_get(sg, "security_group_rules") or [])
            ],
        }
    )


def security_group_detail(sg: Any) -> dict:
    """Full security-group view for describe responses.

    Same as summary for v2 (the API already returns everything), but kept
    as a separate function for future v3 migration where detail may carry
    extra fields (tags, created_at, updated_at).
    """
    return security_group_summary(sg)


# ============================================================
# VPC / Subnet / Peering / FlowLog / RouteTable / EIP
# ============================================================
def vpc_summary(v: Any) -> dict:
    """Compact VPC view for list responses."""
    return _drop_nulls({
        "id": _get(v, "id"),
        "name": _get(v, "name"),
        "cidr": _get(v, "cidr"),
        "status": _get(v, "status"),
        "enterprise_project_id": _get(v, "enterprise_project_id"),
        "description": _get(v, "description"),
        "created_at": _get(v, "created_at"),
        "updated_at": _get(v, "updated_at"),
    })


def vpc_detail(v: Any) -> dict:
    """Full VPC view for describe responses (includes routes)."""
    d = vpc_summary(v)
    routes = _get(v, "routes")
    if routes:
        d["routes"] = [route_summary(r) for r in routes]
    return d


def route_summary(r: Any) -> dict:
    """Compact route entry view (used in VPC detail and route table detail)."""
    return _drop_nulls({
        "id": _get(r, "id"),
        "destination": _get(r, "destination"),
        "nexthop": _get(r, "nexthop"),
        "type": _get(r, "type"),
        "description": _get(r, "description"),
    })


def subnet_summary(s: Any) -> dict:
    """Compact subnet view for list responses."""
    return _drop_nulls({
        "id": _get(s, "id"),
        "name": _get(s, "name"),
        "cidr": _get(s, "cidr"),
        "gateway_ip": _get(s, "gateway_ip"),
        "vpc_id": _get(s, "vpc_id"),
        "availability_zone": _get(s, "availability_zone"),
        "status": _get(s, "status"),
        "available_ip_address_count": _get(s, "available_ip_address_count"),
        "ipv6_enable": _get(s, "ipv6_enable"),
        "cidr_v6": _get(s, "cidr_v6"),
        "dhcp_enable": _get(s, "dhcp_enable"),
        "primary_dns": _get(s, "primary_dns"),
        "secondary_dns": _get(s, "secondary_dns"),
        "description": _get(s, "description"),
        "created_at": _get(s, "created_at"),
    })


def subnet_detail(s: Any) -> dict:
    """Full subnet view (same as summary — SDK returns all fields)."""
    return subnet_summary(s)


def vpc_peering_summary(p: Any) -> dict:
    """Compact VPC peering view for list responses."""
    req_vpc = _get(p, "request_vpc_info")
    acc_vpc = _get(p, "accept_vpc_info")
    return _drop_nulls({
        "id": _get(p, "id"),
        "name": _get(p, "name"),
        "status": _get(p, "status"),
        "description": _get(p, "description"),
        "request_vpc_id": _get(req_vpc, "vpc_id"),
        "request_tenant_id": _get(req_vpc, "tenant_id"),
        "accept_vpc_id": _get(acc_vpc, "vpc_id"),
        "accept_tenant_id": _get(acc_vpc, "tenant_id"),
        "created_at": _get(p, "created_at"),
        "updated_at": _get(p, "updated_at"),
    })


def vpc_peering_detail(p: Any) -> dict:
    """Full VPC peering view (same as summary)."""
    return vpc_peering_summary(p)


def flow_log_summary(f: Any) -> dict:
    """Compact flow log config view for list responses."""
    return _drop_nulls({
        "id": _get(f, "id"),
        "name": _get(f, "name"),
        "resource_type": _get(f, "resource_type"),
        "resource_id": _get(f, "resource_id"),
        "traffic_type": _get(f, "traffic_type"),
        "log_group_id": _get(f, "log_group_id"),
        "log_topic_id": _get(f, "log_topic_id"),
        "log_store_type": _get(f, "log_store_type"),
        "status": _get(f, "status"),
        "admin_state": _get(f, "admin_state"),
        "description": _get(f, "description"),
        "created_at": _get(f, "created_at"),
        "updated_at": _get(f, "updated_at"),
    })


def flow_log_detail(f: Any) -> dict:
    """Full flow log config view (same as summary)."""
    return flow_log_summary(f)


def route_table_summary(rt: Any) -> dict:
    """Compact route table view for list responses (no route entries)."""
    return _drop_nulls({
        "id": _get(rt, "id"),
        "name": _get(rt, "name"),
        "vpc_id": _get(rt, "vpc_id"),
        "default": _get(rt, "default"),
        "subnets": _get(rt, "subnets"),
        "description": _get(rt, "description"),
        "created_at": _get(rt, "created_at"),
    })


def route_table_detail(rt: Any) -> dict:
    """Full route table view for describe responses (includes route entries)."""
    d = route_table_summary(rt)
    routes = _get(rt, "routes")
    if routes:
        d["routes"] = [route_summary(r) for r in routes]
    return d


def eip_summary(e: Any) -> dict:
    """Compact EIP view for list responses."""
    return _drop_nulls({
        "id": _get(e, "id"),
        "public_ip_address": _get(e, "public_ip_address"),
        "public_ipv6_address": _get(e, "public_ipv6_address"),
        "status": _get(e, "status"),
        "type": _get(e, "type"),
        "bandwidth_id": _get(e, "bandwidth_id"),
        "bandwidth_name": _get(e, "bandwidth_name"),
        "bandwidth_size": _get(e, "bandwidth_size"),
        "bandwidth_share_type": _get(e, "bandwidth_share_type"),
        "port_id": _get(e, "port_id"),
        "private_ip_address": _get(e, "private_ip_address"),
        "enterprise_project_id": _get(e, "enterprise_project_id"),
        "alias": _get(e, "alias"),
        "create_time": _get(e, "create_time"),
    })


def eip_detail(e: Any) -> dict:
    """Full EIP view (same as summary — SDK returns all fields)."""
    return eip_summary(e)
