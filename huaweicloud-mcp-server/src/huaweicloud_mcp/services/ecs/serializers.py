"""Convert Huawei Cloud SDK response objects to compact JSON-friendly dicts.

Goal: surface only fields useful to LLMs / users; drop SDK metadata, hrefs,
links, deeply nested noise.

Two-tier strategy:
- ``server_summary`` — minimal field set for list views. Drops null/empty
  fields automatically and uses a flat IP-string address shape. Optimized
  for token efficiency when an LLM is scanning many servers.
- ``server_detail`` — full operational info (flavor specs, volumes, security
  groups, metadata, NIC details). Used when the caller asks for one specific
  server.

Rule of thumb: anything routinely null in HuaweiCloud's list response
(task_state, power_state, image_id, availability_zone, NIC type/mac) lives
in ``server_detail`` only. Anything always present in list responses
(id, name, status, flavor, IPs, tags, created) lives in ``server_summary``.
"""
from __future__ import annotations

from typing import Any


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read attribute from SDK object or dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _drop_nulls(d: dict) -> dict:
    """Remove keys whose values are None, empty list, or empty dict.

    Keeps falsy-but-meaningful values (0, False, empty string '' is dropped
    intentionally — Huawei Cloud uses '' for "field not applicable").
    """
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != [] and v != {} and v != ""
    }


def _addresses_compact(addrs: Any) -> dict:
    """Flat IP list per network — list-view oriented.

    Output shape:  ``{vpc_id: ["192.168.1.10", "1.2.3.4"]}``

    Drops ``OS-EXT-IPS:type``, ``OS-EXT-IPS-MAC:mac_addr``, and ``version``.
    Those fields are almost always null in Huawei Cloud list responses; for
    full NIC info use ``ecs_get_server_detail`` (which calls
    ``_addresses_full``).
    """
    if not addrs or not isinstance(addrs, dict):
        return {}
    out: dict[str, list[str]] = {}
    for net, items in addrs.items():
        ips = [_get(it, "addr") for it in (items or []) if _get(it, "addr")]
        if ips:
            out[net] = ips
    return out


def _addresses_full(addrs: Any) -> dict:
    """Rich NIC info per network — detail-view oriented.

    Per-IP entry: ``{addr, type, version, mac}`` with null fields stripped.
    """
    if not addrs or not isinstance(addrs, dict):
        return {}
    out: dict[str, list[dict]] = {}
    for net, items in addrs.items():
        rows = []
        for it in items or []:
            row = _drop_nulls(
                {
                    "addr": _get(it, "addr"),
                    "type": _get(it, "OS-EXT-IPS:type")
                    or _get(it, "os_ext_ips_type"),
                    "version": _get(it, "version"),
                    "mac": _get(it, "OS-EXT-IPS-MAC:mac_addr")
                    or _get(it, "os_ext_ips_mac_mac_addr"),
                }
            )
            if row:
                rows.append(row)
        if rows:
            out[net] = rows
    return out


def server_summary(s: Any) -> dict:
    """Compact server view for list_servers / ecs_get_server_status callers.

    Token-optimized: omits null/empty fields and reduces address structure
    to flat IP strings. Use ``server_detail`` when the caller needs full
    NIC, volume, security-group, or metadata info.

    Always present (when set on the SDK object):
      id, name, status, flavor_id, addresses, created

    Optional (only included when truthy):
      tags, task_state, updated
    """
    flavor = _get(s, "flavor")
    task_state = _get(s, "OS-EXT-STS:task_state") or _get(
        s, "os_ext_sts_task_state"
    )
    return _drop_nulls(
        {
            "id": _get(s, "id"),
            "name": _get(s, "name"),
            "status": _get(s, "status"),
            "flavor_id": _get(flavor, "id"),
            "addresses": _addresses_compact(_get(s, "addresses")),
            "created": _get(s, "created"),
            "tags": _get(s, "tags") or [],
            "task_state": task_state,
            # 'updated' kept only when materially different from 'created' is
            # impossible to detect cheaply here, so we drop it from the
            # summary entirely; ``server_detail`` carries it.
        }
    )


def server_detail(s: Any) -> dict:
    """Detailed server view including disks, NICs, security groups, metadata.

    Extends ``server_summary`` with all fields a human/automation might need
    when operating on one specific server. Re-populates ``addresses`` with
    the rich NIC shape (the summary uses flat IP strings).
    """
    base = server_summary(s)
    flavor = _get(s, "flavor")
    image = _get(s, "image")

    # Override addresses with the rich shape for detail callers.
    rich_addrs = _addresses_full(_get(s, "addresses"))
    if rich_addrs:
        base["addresses"] = rich_addrs

    # Bring back fields that summary intentionally drops.
    extras = {
        "flavor": (
            {
                "id": _get(flavor, "id"),
                "name": _get(flavor, "name"),
                "vcpus": _get(flavor, "vcpus"),
                "ram": _get(flavor, "ram"),
                "disk": _get(flavor, "disk"),
            }
            if flavor
            else None
        ),
        "image_id": _get(image, "id"),
        "power_state": _get(s, "OS-EXT-STS:power_state")
        or _get(s, "os_ext_sts_power_state"),
        "availability_zone": _get(s, "OS-EXT-AZ:availability_zone")
        or _get(s, "os_ext_az_availability_zone"),
        "updated": _get(s, "updated"),
        "key_name": _get(s, "key_name"),
        "host_id": _get(s, "host_id"),
        "enterprise_project_id": _get(s, "enterprise_project_id"),
        "description": _get(s, "description"),
        "volumes_attached": [
            {
                "id": _get(v, "id"),
                "device": _get(v, "device"),
                "boot_index": _get(v, "boot_index"),
                "delete_on_termination": _get(v, "delete_on_termination"),
            }
            for v in (_get(s, "os_extended_volumes_volumes_attached") or [])
        ],
        "security_groups": [
            {"id": _get(g, "id"), "name": _get(g, "name")}
            for g in (_get(s, "security_groups") or [])
        ],
        "metadata": _get(s, "metadata") or {},
    }
    base.update(_drop_nulls(extras))
    return base


def server_status_only(s: Any) -> dict:
    """Minimal status view for ecs_get_server_status."""
    return _drop_nulls(
        {
            "server_id": _get(s, "id"),
            "name": _get(s, "name"),
            "status": _get(s, "status"),
            "task_state": _get(s, "OS-EXT-STS:task_state")
            or _get(s, "os_ext_sts_task_state"),
            "power_state": _get(s, "OS-EXT-STS:power_state")
            or _get(s, "os_ext_sts_power_state"),
        }
    )


def flavor_summary(f: Any) -> dict:
    return {
        "id": _get(f, "id"),
        "name": _get(f, "name"),
        "vcpus": _get(f, "vcpus"),
        "ram_mb": _get(f, "ram"),
        "disk_gb": _get(f, "disk"),
        "generation": _get(_get(f, "os_extra_specs"), "ecs:generation"),
        "performance_type": _get(_get(f, "os_extra_specs"), "ecs:performancetype"),
    }


def job_summary(j: Any) -> dict:
    """Summarize a ShowJob response."""
    entities = _get(j, "entities")
    sub_jobs = []
    if entities is not None:
        for sj in (_get(entities, "sub_jobs") or []):
            sub_jobs.append(
                {
                    "job_id": _get(sj, "job_id"),
                    "job_type": _get(sj, "job_type"),
                    "status": _get(sj, "status"),
                    "begin_time": _get(sj, "begin_time"),
                    "end_time": _get(sj, "end_time"),
                    "error_code": _get(sj, "error_code"),
                    "fail_reason": _get(sj, "fail_reason"),
                    "entities": _get(sj, "entities"),
                }
            )
    return {
        "job_id": _get(j, "job_id"),
        "job_type": _get(j, "job_type"),
        "status": _get(j, "status"),
        "begin_time": _get(j, "begin_time"),
        "end_time": _get(j, "end_time"),
        "error_code": _get(j, "error_code"),
        "fail_reason": _get(j, "fail_reason"),
        "message": _get(j, "message"),
        "code": _get(j, "code"),
        "sub_jobs_total": _get(entities, "sub_jobs_total") if entities else None,
        "sub_jobs": sub_jobs,
    }