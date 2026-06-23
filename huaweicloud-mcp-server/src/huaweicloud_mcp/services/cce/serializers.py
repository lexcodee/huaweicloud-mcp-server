"""Compact JSON-serialisers for CCE SDK objects.

Two-tier strategy mirrors the ECS module:
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
# Cluster
# ---------------------------------------------------------------------------
def cluster_summary(c: Any) -> dict:
    """List-view cluster fields. Drops nulls."""
    md = _get(c, "metadata")
    sp = _get(c, "spec")
    st = _get(c, "status")
    return _drop_nulls(
        {
            "id": _get(md, "uid"),
            "name": _get(md, "name"),
            "alias": _get(md, "alias"),
            "type": _get(sp, "type"),
            "flavor": _get(sp, "flavor"),
            "version": _get(sp, "version"),
            "category": _get(sp, "category"),
            "billing_mode": _get(sp, "billing_mode"),
            "phase": _get(st, "phase"),
            "created": _get(md, "creation_timestamp"),
            "updated": _get(md, "update_timestamp"),
        }
    )


def cluster_detail(c: Any) -> dict:
    """Full cluster detail including networking + endpoints."""
    md = _get(c, "metadata")
    sp = _get(c, "spec")
    st = _get(c, "status")

    base = cluster_summary(c)

    endpoints = _get(st, "endpoints") or []
    endpoints_out = []
    for ep in endpoints:
        endpoints_out.append(
            _drop_nulls(
                {
                    "url": _get(ep, "url"),
                    "type": _get(ep, "type"),
                }
            )
        )

    host_net = _get(sp, "host_network")
    container_net = _get(sp, "container_network")
    service_net = _get(sp, "service_network")
    extras = _drop_nulls(
        {
            "description": _get(sp, "description"),
            "platform_version": _get(sp, "platform_version"),
            "kubernetes_svc_ip_range": _get(sp, "kubernetes_svc_ip_range"),
            "kube_proxy_mode": _get(sp, "kube_proxy_mode"),
            "ipv6enable": _get(sp, "ipv6enable"),
            "host_network": _drop_nulls(
                {
                    "vpc": _get(host_net, "vpc"),
                    "subnet": _get(host_net, "subnet"),
                    "security_group": _get(host_net, "security_group"),
                }
            ) if host_net else None,
            "container_network": _drop_nulls(
                {
                    "mode": _get(container_net, "mode"),
                    "cidr": _get(container_net, "cidr"),
                }
            ) if container_net else None,
            "service_network": _drop_nulls(
                {
                    "ipv4_cidr": _get(service_net, "ipv4cidr") or _get(service_net, "ipv4_cidr"),
                }
            ) if service_net else None,
            "endpoints": endpoints_out,
            "job_id": _get(st, "job_id"),
            "reason": _get(st, "reason"),
            "message": _get(st, "message"),
            "labels": _get(md, "labels") or {},
            "annotations": _get(md, "annotations") or {},
            "timezone": _get(md, "timezone"),
        }
    )
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------
def node_summary(n: Any) -> dict:
    """List-view node fields."""
    md = _get(n, "metadata")
    sp = _get(n, "spec")
    st = _get(n, "status")
    return _drop_nulls(
        {
            "id": _get(md, "uid"),
            "name": _get(md, "name"),
            "phase": _get(st, "phase"),
            "flavor": _get(sp, "flavor"),
            "az": _get(sp, "az"),
            "os": _get(sp, "os"),
            "billing_mode": _get(sp, "billing_mode"),
            "private_ip": _get(st, "private_ip"),
            "public_ip": _get(st, "public_ip"),
            "server_id": _get(st, "server_id"),
            "created": _get(md, "creation_timestamp"),
        }
    )


def node_detail(n: Any) -> dict:
    """Full node detail — adds storage, NIC, k8s tags, login info."""
    md = _get(n, "metadata")
    sp = _get(n, "spec")
    st = _get(n, "status")

    base = node_summary(n)

    root = _get(sp, "root_volume")
    data_volumes = _get(sp, "data_volumes") or []
    nic = _get(sp, "node_nic_spec")
    login = _get(sp, "login")
    pub = _get(sp, "public_ip")

    extras = _drop_nulls(
        {
            "count": _get(sp, "count"),
            "dedicated_host_id": _get(sp, "dedicated_host_id"),
            "ecs_group_id": _get(sp, "ecs_group_id"),
            "server_enterprise_project_id": _get(sp, "server_enterprise_project_id"),
            "runtime": _drop_nulls(
                {
                    "name": _get(_get(sp, "runtime"), "name"),
                }
            ) if _get(sp, "runtime") else None,
            "root_volume": _drop_nulls(
                {
                    "volumetype": _get(root, "volumetype"),
                    "size": _get(root, "size"),
                }
            ) if root else None,
            "data_volumes": [
                _drop_nulls(
                    {
                        "volumetype": _get(v, "volumetype"),
                        "size": _get(v, "size"),
                    }
                )
                for v in data_volumes
            ],
            "k8s_tags": _get(sp, "k8s_tags") or {},
            "user_tags": _get(sp, "user_tags") or [],
            "taints": _get(sp, "taints") or [],
            "login_key_pair": _get(login, "ssh_key") if login else None,
            "node_nic_spec": _drop_nulls(
                {
                    "primary_nic_subnet": _get(
                        _get(nic, "primary_nic"), "subnet_id"
                    ) if _get(nic, "primary_nic") else None,
                }
            ) if nic else None,
            "public_ip_count": _get(pub, "count") if pub else None,
            "private_ipv6_ip": _get(st, "private_i_pv6_ip"),
            "last_probe_time": _get(st, "last_probe_time"),
            "job_id": _get(st, "job_id"),
            "delete_status": _get(st, "delete_status"),
            "configuration_up_to_date": _get(st, "configuration_up_to_date"),
            "labels": _get(md, "labels") or {},
            "annotations": _get(md, "annotations") or {},
        }
    )
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# NodePool
# ---------------------------------------------------------------------------
def nodepool_summary(p: Any) -> dict:
    """List-view node-pool fields."""
    md = _get(p, "metadata")
    sp = _get(p, "spec")
    st = _get(p, "status")
    tmpl = _get(sp, "node_template")

    autoscaling = _get(sp, "autoscaling")
    return _drop_nulls(
        {
            "id": _get(md, "uid"),
            "name": _get(md, "name"),
            "type": _get(sp, "type"),
            "phase": _get(st, "phase"),
            "initial_node_count": _get(sp, "initial_node_count"),
            "current_node": _get(st, "current_node"),
            "creating_node": _get(st, "creating_node"),
            "deleting_node": _get(st, "deleting_node"),
            "flavor": _get(tmpl, "flavor"),
            "az": _get(tmpl, "az"),
            "os": _get(tmpl, "os"),
            "autoscaling_enabled": _get(autoscaling, "enable"),
            "min_node_count": _get(autoscaling, "min_node_count"),
            "max_node_count": _get(autoscaling, "max_node_count"),
            "created": _get(md, "creation_timestamp"),
            "updated": _get(md, "update_timestamp"),
        }
    )


def nodepool_detail(p: Any) -> dict:
    """Full node-pool detail — adds template, scaling policy, job_id."""
    md = _get(p, "metadata")
    sp = _get(p, "spec")
    st = _get(p, "status")
    tmpl = _get(sp, "node_template")
    autoscaling = _get(sp, "autoscaling")

    base = nodepool_summary(p)

    root = _get(tmpl, "root_volume")
    data_volumes = _get(tmpl, "data_volumes") or []
    runtime = _get(tmpl, "runtime")

    extras = _drop_nulls(
        {
            "configuration_synced_node_count": _get(st, "configuration_synced_node_count"),
            "job_id": _get(st, "job_id"),
            "node_management": _drop_nulls(
                {
                    "server_group_reference": _get(
                        _get(sp, "node_management"), "server_group_reference"
                    ),
                }
            ) if _get(sp, "node_management") else None,
            "autoscaling": _drop_nulls(
                {
                    "enable": _get(autoscaling, "enable"),
                    "min_node_count": _get(autoscaling, "min_node_count"),
                    "max_node_count": _get(autoscaling, "max_node_count"),
                    "scale_down_cooldown_time": _get(
                        autoscaling, "scale_down_cooldown_time"
                    ),
                    "priority": _get(autoscaling, "priority"),
                }
            ) if autoscaling else None,
            "node_template": _drop_nulls(
                {
                    "flavor": _get(tmpl, "flavor"),
                    "az": _get(tmpl, "az"),
                    "os": _get(tmpl, "os"),
                    "billing_mode": _get(tmpl, "billing_mode"),
                    "count": _get(tmpl, "count"),
                    "k8s_tags": _get(tmpl, "k8s_tags") or {},
                    "user_tags": _get(tmpl, "user_tags") or [],
                    "taints": _get(tmpl, "taints") or [],
                    "runtime": _drop_nulls(
                        {"name": _get(runtime, "name")}
                    ) if runtime else None,
                    "root_volume": _drop_nulls(
                        {
                            "volumetype": _get(root, "volumetype"),
                            "size": _get(root, "size"),
                        }
                    ) if root else None,
                    "data_volumes": [
                        _drop_nulls(
                            {
                                "volumetype": _get(v, "volumetype"),
                                "size": _get(v, "size"),
                            }
                        )
                        for v in data_volumes
                    ],
                }
            ) if tmpl else None,
            "annotations": _get(md, "annotations") or {},
        }
    )
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------
def job_summary(j: Any) -> dict:
    """Summarise a ShowJob response."""
    md = _get(j, "metadata")
    sp = _get(j, "spec")
    st = _get(j, "status")

    sub_jobs = []
    for sj in (_get(sp, "sub_jobs") or []):
        sub_md = _get(sj, "metadata")
        sub_sp = _get(sj, "spec")
        sub_st = _get(sj, "status")
        sub_jobs.append(
            _drop_nulls(
                {
                    "job_id": _get(sub_md, "uid"),
                    "type": _get(sub_sp, "type"),
                    "resource_id": _get(sub_sp, "resource_id"),
                    "resource_name": _get(sub_sp, "resource_name"),
                    "phase": _get(sub_st, "phase"),
                    "reason": _get(sub_st, "reason"),
                    "created": _get(sub_md, "creation_timestamp"),
                    "updated": _get(sub_md, "update_timestamp"),
                }
            )
        )

    return _drop_nulls(
        {
            "job_id": _get(md, "uid"),
            "type": _get(sp, "type"),
            "cluster_id": _get(sp, "cluster_uid"),
            "resource_id": _get(sp, "resource_id"),
            "resource_name": _get(sp, "resource_name"),
            "phase": _get(st, "phase"),
            "reason": _get(st, "reason"),
            "created": _get(md, "creation_timestamp"),
            "updated": _get(md, "update_timestamp"),
            "sub_jobs_total": len(sub_jobs) if sub_jobs else None,
            "sub_jobs": sub_jobs,
        }
    )



