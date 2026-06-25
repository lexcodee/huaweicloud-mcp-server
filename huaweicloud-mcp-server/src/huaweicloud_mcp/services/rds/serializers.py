"""Compact JSON-serialisers for RDS SDK objects.

Two-tier strategy mirrors the CES / VPC modules:
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
# Instance (InstanceResponse)
# ---------------------------------------------------------------------------
def _datastore_summary(ds: Any) -> dict:
    return _drop_nulls({
        "type": _get(ds, "type"),
        "version": _get(ds, "version"),
    })


def _volume_summary(vol: Any) -> dict:
    return _drop_nulls({
        "type": _get(vol, "type"),
        "size_gb": _get(vol, "size"),
    })


def _node_summary(n: Any) -> dict:
    return _drop_nulls({
        "id": _get(n, "id"),
        "name": _get(n, "name"),
        "role": _get(n, "role"),
        "status": _get(n, "status"),
        "availability_zone": _get(n, "availability_zone"),
    })


def _backup_strategy_summary(bs: Any) -> dict:
    return _drop_nulls({
        "start_time": _get(bs, "start_time"),
        "keep_days": _get(bs, "keep_days"),
    })


def _related_instance_summary(ri: Any) -> dict:
    return _drop_nulls({
        "id": _get(ri, "id"),
        "type": _get(ri, "type"),
    })


def instance_summary(inst: Any) -> dict:
    """List-view instance — minimal fields for browsing."""
    return _drop_nulls({
        "id": _get(inst, "id"),
        "name": _get(inst, "name"),
        "status": _get(inst, "status"),
        "type": _get(inst, "type"),
        "engine": _get(_get(inst, "datastore"), "type"),
        "engine_version": _get(_get(inst, "datastore"), "version"),
        "flavor_ref": _get(inst, "flavor_ref"),
        "cpu": _get(inst, "cpu"),
        "mem": _get(inst, "mem"),
        "private_ips": _get(inst, "private_ips"),
        "public_ips": _get(inst, "public_ips"),
        "port": _get(inst, "port"),
        "enable_ssl": _get(inst, "enable_ssl"),
    })


def instance_detail(inst: Any) -> dict:
    """Full instance detail — all operational fields."""
    base = instance_summary(inst)
    extras = _drop_nulls({
        "private_dns_names": _get(inst, "private_dns_names"),
        "public_dns_names": _get(inst, "public_dns_names"),
        "created": _get(inst, "created"),
        "updated": _get(inst, "updated"),
        "db_user_name": _get(inst, "db_user_name"),
        "maintenance_window": _get(inst, "maintenance_window"),
        "time_zone": _get(inst, "time_zone"),
        "region": _get(inst, "region"),
        "vpc_id": _get(inst, "vpc_id"),
        "subnet_id": _get(inst, "subnet_id"),
        "security_group_id": _get(inst, "security_group_id"),
        "enterprise_project_id": _get(inst, "enterprise_project_id"),
        "disk_encryption_id": _get(inst, "disk_encryption_id"),
        "max_iops": _get(inst, "max_iops"),
        "backup_used_space": _get(inst, "backup_used_space"),
        "storage_used_space": _get(inst, "storage_used_space"),
        "alias": _get(inst, "alias"),
        "datastore": _datastore_summary(_get(inst, "datastore")),
        "volume": _volume_summary(_get(inst, "volume")),
        "ha": _drop_nulls({
            "replication_mode": _get(_get(inst, "ha"), "replication_mode"),
        }),
        "backup_strategy": _backup_strategy_summary(_get(inst, "backup_strategy")),
        "charge_info": _drop_nulls({
            "charge_mode": _get(_get(inst, "charge_info"), "charge_mode"),
        }),
        "nodes": [_node_summary(n) for n in (_get(inst, "nodes") or [])],
        "related_instance": [
            _related_instance_summary(ri)
            for ri in (_get(inst, "related_instance") or [])
        ],
    })
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Error log (ErrorLog)
# ---------------------------------------------------------------------------
def error_log_summary(e: Any) -> dict:
    return _drop_nulls({
        "time": _get(e, "time"),
        "level": _get(e, "level"),
        "content": _get(e, "content"),
    })


# ---------------------------------------------------------------------------
# Slow log — individual entry (SlowLog)
# ---------------------------------------------------------------------------
def slow_log_entry(s: Any) -> dict:
    return _drop_nulls({
        "start_time": _get(s, "start_time"),
        "database": _get(s, "database"),
        "sql_text": _get(s, "query_sample"),
        "duration_ms": _safe_float(_get(s, "time")),
        "lock_time_ms": _safe_float(_get(s, "lock_time")),
        "rows_sent": _safe_int(_get(s, "rows_sent")),
        "rows_examined": _safe_int(_get(s, "rows_examined")),
        "execution_count": _safe_int(_get(s, "count")),
        "users": _get(s, "users"),
        "client_ip": _get(s, "client_ip"),
        "type": _get(s, "type"),
    })


# ---------------------------------------------------------------------------
# Slow log statistics — aggregated by SQL pattern (SlowLogStatistics)
# ---------------------------------------------------------------------------
def slow_log_statistics(s: Any) -> dict:
    return _drop_nulls({
        "database": _get(s, "database"),
        "sql_text": _get(s, "query_sample"),
        "avg_duration_ms": _safe_float(_get(s, "time")),
        "lock_time_ms": _safe_float(_get(s, "lock_time")),
        "execution_count": _safe_int(_get(s, "count")),
        "rows_sent": _get(s, "rows_sent"),
        "rows_examined": _get(s, "rows_examined"),
        "users": _get(s, "users"),
        "client_ip": _get(s, "client_ip"),
        "type": _get(s, "type"),
    })


# ---------------------------------------------------------------------------
# Database (DatabaseForCreation)
# ---------------------------------------------------------------------------
def database_summary(d: Any) -> dict:
    return _drop_nulls({
        "name": _get(d, "name"),
        "character_set": _get(d, "character_set"),
        "comment": _get(d, "comment"),
    })


# ---------------------------------------------------------------------------
# DB user / account (UserForList)
# ---------------------------------------------------------------------------
def db_user_summary(u: Any) -> dict:
    dbs = _get(u, "databases") or []
    db_privs = [
        _drop_nulls({
            "name": _get(d, "name"),
            "readonly": _get(d, "readonly"),
        })
        for d in dbs
    ]
    return _drop_nulls({
        "name": _get(u, "name"),
        "hosts": _get(u, "hosts"),
        "comment": _get(u, "comment"),
        "databases": db_privs,
    })


# ---------------------------------------------------------------------------
# Backup (BackupForList)
# ---------------------------------------------------------------------------
def backup_summary(b: Any) -> dict:
    return _drop_nulls({
        "id": _get(b, "id"),
        "instance_id": _get(b, "instance_id"),
        "name": _get(b, "name"),
        "type": _get(b, "type"),
        "status": _get(b, "status"),
        "size_kb": _get(b, "size"),
        "begin_time": _get(b, "begin_time"),
        "end_time": _get(b, "end_time"),
    })


# ---------------------------------------------------------------------------
# Configuration parameter (ConfigurationParameter)
# ---------------------------------------------------------------------------
def configuration_parameter_summary(p: Any) -> dict:
    return _drop_nulls({
        "name": _get(p, "name"),
        "current_value": _get(p, "value"),
        "value_range": _get(p, "value_range"),
        "restart_required": _get(p, "restart_required"),
        "readonly": _get(p, "readonly"),
        "type": _get(p, "type"),
        "description": _get(p, "description"),
    })


def configuration_summary(c: Any) -> dict:
    """List-view parameter group."""
    return _drop_nulls({
        "id": _get(c, "id"),
        "name": _get(c, "name"),
        "description": _get(c, "description"),
        "datastore_name": _get(c, "datastore_name"),
        "datastore_version_name": _get(c, "datastore_version_name"),
        "created": _get(c, "created"),
        "updated": _get(c, "updated"),
    })


def configuration_detail(c: Any) -> dict:
    """Full parameter group detail with all parameters."""
    base = configuration_summary(c)
    params = _get(c, "configuration_parameters") or []
    base["parameters"] = [configuration_parameter_summary(p) for p in params]
    return base


# ---------------------------------------------------------------------------
# Backup info (BackupInfo — from CreateManualBackupResponse)
# ---------------------------------------------------------------------------
def backup_info_summary(b: Any) -> dict:
    return _drop_nulls({
        "id": _get(b, "id"),
        "instance_id": _get(b, "instance_id"),
        "name": _get(b, "name"),
        "description": _get(b, "description"),
        "begin_time": _get(b, "begin_time"),
        "status": _get(b, "status"),
        "type": _get(b, "type"),
    })


# ---------------------------------------------------------------------------
# Replication status (ShowReplicationStatusResponse)
# ---------------------------------------------------------------------------
def replication_status_summary(r: Any) -> dict:
    return _drop_nulls({
        "replication_status": _get(r, "replication_status"),
        "abnormal_reason": _get(r, "abnormal_reason"),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
