"""Compact JSON-serialisers for ELB SDK objects.

Two-tier strategy mirrors the RDS / VPC / OBS modules:
- ``*_summary`` — minimal fields for list views (token-efficient).
- ``*_detail`` — full operational info for single-resource fetches.

``_drop_nulls`` removes None/empty values so the LLM doesn't waste tokens
on absent fields.
"""
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


# ---------------------------------------------------------------------------
# Load Balancer (LoadBalancer)
# ---------------------------------------------------------------------------
def _eip_summary(eip: Any) -> dict:
    return _drop_nulls({
        "eip_id": _get(eip, "eip_id"),
        "eip_address": _get(eip, "eip_address"),
        "ip_version": _get(eip, "ip_version"),
    })


def load_balancer_summary(lb: Any) -> dict:
    """List-view load balancer — minimal fields for browsing."""
    eips = _get(lb, "eips") or []
    publicips = _get(lb, "publicips") or []
    return _drop_nulls({
        "id": _get(lb, "id"),
        "name": _get(lb, "name"),
        "operating_status": _get(lb, "operating_status"),
        "provisioning_status": _get(lb, "provisioning_status"),
        "admin_state_up": _get(lb, "admin_state_up"),
        "vip_address": _get(lb, "vip_address"),
        "vpc_id": _get(lb, "vpc_id"),
        "availability_zone_list": _get(lb, "availability_zone_list"),
        "provider": _get(lb, "provider"),
        "eips": [_eip_summary(e) for e in eips] if eips else None,
        "publicips": [_eip_summary(p) for p in publicips] if publicips else None,
    })


def load_balancer_detail(lb: Any) -> dict:
    """Full load balancer detail — all operational fields."""
    base = load_balancer_summary(lb)
    extras = _drop_nulls({
        "description": _get(lb, "description"),
        "vip_subnet_cidr_id": _get(lb, "vip_subnet_cidr_id"),
        "vip_port_id": _get(lb, "vip_port_id"),
        "ipv6_vip_address": _get(lb, "ipv6_vip_address"),
        "guaranteed": _get(lb, "guaranteed"),
        "l4_flavor_id": _get(lb, "l4_flavor_id"),
        "l7_flavor_id": _get(lb, "l7_flavor_id"),
        "billing_info": _get(lb, "billing_info"),
        "created_at": _get(lb, "created_at"),
        "updated_at": _get(lb, "updated_at"),
        "enterprise_project_id": _get(lb, "enterprise_project_id"),
        "deletion_protection_enable": _get(lb, "deletion_protection_enable"),
        "frozen_scene": _get(lb, "frozen_scene"),
        "tags": _get(lb, "tags"),
        "log_group_id": _get(lb, "log_group_id"),
        "log_topic_id": _get(lb, "log_topic_id"),
    })
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Listener (Listener)
# ---------------------------------------------------------------------------
def listener_summary(lis: Any) -> dict:
    """List-view listener — minimal fields."""
    return _drop_nulls({
        "id": _get(lis, "id"),
        "name": _get(lis, "name"),
        "protocol": _get(lis, "protocol"),
        "protocol_port": _get(lis, "protocol_port"),
        "operating_status": _get(lis, "operating_status"),
        "provisioning_status": _get(lis, "provisioning_status"),
        "admin_state_up": _get(lis, "admin_state_up"),
        "loadbalancer_id": _get(_get(lis, "loadbalancers", [None])[0] if _get(lis, "loadbalancers") else None, "id") if _get(lis, "loadbalancers") else None,
        "default_pool_id": _get(lis, "default_pool_id"),
        "default_tls_container_ref": _get(lis, "default_tls_container_ref"),
    })


def listener_detail(lis: Any) -> dict:
    """Full listener detail."""
    base = listener_summary(lis)
    extras = _drop_nulls({
        "description": _get(lis, "description"),
        "connection_limit": _get(lis, "connection_limit"),
        "http2_enable": _get(lis, "http2_enable"),
        "tls_ciphers_policy": _get(lis, "tls_ciphers_policy"),
        "security_policy_id": _get(lis, "security_policy_id"),
        "sni_container_refs": _get(lis, "sni_container_refs"),
        "sni_match_algo": _get(lis, "sni_match_algo"),
        "keepalive_timeout": _get(lis, "keepalive_timeout"),
        "client_timeout": _get(lis, "client_timeout"),
        "member_timeout": _get(lis, "member_timeout"),
        "enable_member_retry": _get(lis, "enable_member_retry"),
        "transparent_client_ip_enable": _get(lis, "transparent_client_ip_enable"),
        "proxy_protocol_enable": _get(lis, "proxy_protocol_enable"),
        "enhance_l7policy_enable": _get(lis, "enhance_l7policy_enable"),
        "gzip_enable": _get(lis, "gzip_enable"),
        "created_at": _get(lis, "created_at"),
        "updated_at": _get(lis, "updated_at"),
        "tags": _get(lis, "tags"),
        "protection_status": _get(lis, "protection_status"),
    })
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Backend Group / Pool (Pool)
# ---------------------------------------------------------------------------
def _session_persistence_summary(sp: Any) -> dict:
    return _drop_nulls({
        "type": _get(sp, "type"),
        "cookie_name": _get(sp, "cookie_name"),
        "persistence_timeout": _get(sp, "persistence_timeout"),
    })


def _connection_drain_summary(cd: Any) -> dict:
    return _drop_nulls({
        "enable": _get(cd, "enable"),
        "timeout": _get(cd, "timeout"),
    })


def _slow_start_summary(ss: Any) -> dict:
    return _drop_nulls({
        "enable": _get(ss, "enable"),
        "duration": _get(ss, "duration"),
    })


def pool_summary(pool: Any) -> dict:
    """List-view pool — minimal fields."""
    return _drop_nulls({
        "id": _get(pool, "id"),
        "name": _get(pool, "name"),
        "protocol": _get(pool, "protocol"),
        "lb_algorithm": _get(pool, "lb_algorithm"),
        "admin_state_up": _get(pool, "admin_state_up"),
        "healthmonitor_id": _get(pool, "healthmonitor_id"),
        "description": _get(pool, "description"),
    })


def pool_detail(pool: Any) -> dict:
    """Full pool detail with session persistence, connection drain, etc."""
    base = pool_summary(pool)
    extras = _drop_nulls({
        "ip_version": _get(pool, "ip_version"),
        "vpc_id": _get(pool, "vpc_id"),
        "type": _get(pool, "type"),
        "member_deletion_protection_enable": _get(pool, "member_deletion_protection_enable"),
        "any_port_enable": _get(pool, "any_port_enable"),
        "created_at": _get(pool, "created_at"),
        "updated_at": _get(pool, "updated_at"),
        "session_persistence": _session_persistence_summary(_get(pool, "session_persistence")),
        "connection_drain": _connection_drain_summary(_get(pool, "connection_drain")),
        "slow_start": _slow_start_summary(_get(pool, "slow_start")),
        "protection_status": _get(pool, "protection_status"),
    })
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Member (Member)
# ---------------------------------------------------------------------------
def member_summary(m: Any) -> dict:
    return _drop_nulls({
        "id": _get(m, "id"),
        "name": _get(m, "name"),
        "address": _get(m, "address"),
        "protocol_port": _get(m, "protocol_port"),
        "weight": _get(m, "weight"),
        "admin_state_up": _get(m, "admin_state_up"),
        "operating_status": _get(m, "operating_status"),
        "status": _get(m, "status"),
        "subnet_cidr_id": _get(m, "subnet_cidr_id"),
        "availability_zone": _get(m, "availability_zone"),
        "member_type": _get(m, "member_type"),
        "instance_id": _get(m, "instance_id"),
        "reason": _get(m, "reason"),
    })


# ---------------------------------------------------------------------------
# Health status from ShowLoadBalancerStatus
# ---------------------------------------------------------------------------
def health_member_summary(m: Any) -> dict:
    """Member health status from LoadBalancerStatusMember."""
    return _drop_nulls({
        "id": _get(m, "id"),
        "address": _get(m, "address"),
        "protocol_port": _get(m, "protocol_port"),
        "operating_status": _get(m, "operating_status"),
        "provisioning_status": _get(m, "provisioning_status"),
    })


def health_pool_summary(p: Any) -> dict:
    """Pool health from LoadBalancerStatusPool — includes member health."""
    members = _get(p, "members") or []
    hm = _get(p, "healthmonitor")
    return _drop_nulls({
        "id": _get(p, "id"),
        "name": _get(p, "name"),
        "operating_status": _get(p, "operating_status"),
        "provisioning_status": _get(p, "provisioning_status"),
        "healthmonitor": _drop_nulls({
            "type": _get(hm, "type"),
            "id": _get(hm, "id"),
            "name": _get(hm, "name"),
            "provisioning_status": _get(hm, "provisioning_status"),
        }) if hm else None,
        "members": [health_member_summary(m) for m in members] if members else None,
    })


def health_listener_summary(lis: Any) -> dict:
    """Listener health from LoadBalancerStatusListener."""
    pools = _get(lis, "pools") or []
    return _drop_nulls({
        "id": _get(lis, "id"),
        "name": _get(lis, "name"),
        "operating_status": _get(lis, "operating_status"),
        "provisioning_status": _get(lis, "provisioning_status"),
        "pools": [health_pool_summary(p) for p in pools] if pools else None,
    })


def load_balancer_status_summary(status: Any) -> dict:
    """Top-level LB status from ShowLoadBalancerStatusResponse."""
    lb = _get(status, "loadbalancer")
    if lb is None:
        return {}
    listeners = _get(lb, "listeners") or []
    pools = _get(lb, "pools") or []
    return _drop_nulls({
        "loadbalancer_id": _get(lb, "id"),
        "loadbalancer_name": _get(lb, "name"),
        "operating_status": _get(lb, "operating_status"),
        "provisioning_status": _get(lb, "provisioning_status"),
        "listeners": [health_listener_summary(l) for l in listeners] if listeners else None,
        "pools": [health_pool_summary(p) for p in pools] if pools else None,
    })


# ---------------------------------------------------------------------------
# L7 Policy + Rules (L7Policy, L7Rule)
# ---------------------------------------------------------------------------
def l7_rule_summary(rule: Any) -> dict:
    return _drop_nulls({
        "id": _get(rule, "id"),
        "type": _get(rule, "type"),
        "compare_type": _get(rule, "compare_type"),
        "value": _get(rule, "value"),
        "key": _get(rule, "key"),
        "invert": _get(rule, "invert"),
        "admin_state_up": _get(rule, "admin_state_up"),
        "provisioning_status": _get(rule, "provisioning_status"),
    })


def l7_policy_summary(policy: Any) -> dict:
    """List-view L7 policy."""
    return _drop_nulls({
        "id": _get(policy, "id"),
        "name": _get(policy, "name"),
        "action": _get(policy, "action"),
        "position": _get(policy, "position"),
        "priority": _get(policy, "priority"),
        "listener_id": _get(policy, "listener_id"),
        "redirect_pool_id": _get(policy, "redirect_pool_id"),
        "redirect_listener_id": _get(policy, "redirect_listener_id"),
        "redirect_url": _get(policy, "redirect_url"),
        "provisioning_status": _get(policy, "provisioning_status"),
        "admin_state_up": _get(policy, "admin_state_up"),
    })


def l7_policy_detail(policy: Any, rules: list | None = None) -> dict:
    """Full L7 policy detail with rules."""
    base = l7_policy_summary(policy)
    base["description"] = _get(policy, "description")
    base["created_at"] = _get(policy, "created_at")
    base["updated_at"] = _get(policy, "updated_at")
    if rules is not None:
        base["rules"] = [l7_rule_summary(r) for r in rules]
    else:
        inner_rules = _get(policy, "rules") or []
        base["rules"] = [l7_rule_summary(r) for r in inner_rules]
    return _drop_nulls(base)


# ---------------------------------------------------------------------------
# Certificate (CertificateInfo)
# ---------------------------------------------------------------------------
def certificate_summary(cert: Any) -> dict:
    return _drop_nulls({
        "id": _get(cert, "id"),
        "name": _get(cert, "name"),
        "domain": _get(cert, "domain"),
        "type": _get(cert, "type"),
        "admin_state_up": _get(cert, "admin_state_up"),
        "expire_time": _get(cert, "expire_time"),
        "common_name": _get(cert, "common_name"),
        "source": _get(cert, "source"),
    })


def certificate_detail(cert: Any) -> dict:
    base = certificate_summary(cert)
    extras = _drop_nulls({
        "description": _get(cert, "description"),
        "scm_certificate_id": _get(cert, "scm_certificate_id"),
        "fingerprint": _get(cert, "fingerprint"),
        "subject_alternative_names": _get(cert, "subject_alternative_names"),
        "created_at": _get(cert, "created_at"),
        "updated_at": _get(cert, "updated_at"),
        "protection_status": _get(cert, "protection_status"),
        "enterprise_project_id": _get(cert, "enterprise_project_id"),
    })
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Logtank (access log config)
# ---------------------------------------------------------------------------
def logtank_summary(lt: Any) -> dict:
    return _drop_nulls({
        "id": _get(lt, "id"),
        "loadbalancer_id": _get(lt, "loadbalancer_id"),
        "log_group_id": _get(lt, "log_group_id"),
        "log_topic_id": _get(lt, "log_topic_id"),
    })


# ---------------------------------------------------------------------------
# Health Monitor (HealthMonitor)
# ---------------------------------------------------------------------------
def health_monitor_summary(hm: Any) -> dict:
    return _drop_nulls({
        "id": _get(hm, "id"),
        "name": _get(hm, "name"),
        "type": _get(hm, "type"),
        "delay": _get(hm, "delay"),
        "timeout": _get(hm, "timeout"),
        "max_retries": _get(hm, "max_retries"),
        "max_retries_down": _get(hm, "max_retries_down"),
        "url_path": _get(hm, "url_path"),
        "http_method": _get(hm, "http_method"),
        "expected_codes": _get(hm, "expected_codes"),
        "monitor_port": _get(hm, "monitor_port"),
        "domain_name": _get(hm, "domain_name"),
        "admin_state_up": _get(hm, "admin_state_up"),
    })
