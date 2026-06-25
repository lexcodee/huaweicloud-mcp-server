"""Pydantic input models for RDS MCP tools.

RDS uses the v3 SDK exclusively. Tools follow the project's list/detail
dispatch pattern where applicable (describe_instances, list_backups,
describe_parameter_group).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# rds_describe_instances — ListInstancesRequest
# ---------------------------------------------------------------------------
class DescribeInstancesInput(BaseModel):
    instance_id: Optional[str] = Field(
        default=None,
        description=(
            "Instance id. If None/empty, returns the LIST of instances. "
            "If set, returns DETAIL for that single instance."
        ),
    )
    name: Optional[str] = Field(
        default=None,
        description="List-mode filter: instance name (fuzzy match).",
    )
    datastore_type: Optional[str] = Field(
        default=None,
        description="List-mode filter: engine type (MySQL, PostgreSQL, SQLServer).",
    )
    status: Optional[str] = Field(
        default=None,
        description="List-mode filter: instance status (BUILD, ACTIVE, FAILED, etc.).",
    )
    vpc_id: Optional[str] = Field(
        default=None,
        description="List-mode filter: VPC id.",
    )
    subnet_id: Optional[str] = Field(
        default=None,
        description="List-mode filter: subnet id.",
    )
    offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Page offset.",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (1..100).",
    )


# ---------------------------------------------------------------------------
# rds_get_db_logs — merged error + slow query logs
# ---------------------------------------------------------------------------
class GetDbLogsInput(BaseModel):
    instance_id: str = Field(
        ..., description="RDS instance id."
    )
    log_type: Literal["error", "slow"] = Field(
        default="error",
        description=(
            "Log type: 'error' for database error logs, 'slow' for slow query logs. "
            "When 'slow', uses the statistics API for aggregated SQL-pattern analysis."
        ),
    )
    start_time: Optional[str] = Field(
        default=None,
        description=(
            "Inclusive start. Accepts '-1h', '-30m', ISO8601, "
            "'YYYY-MM-DD HH:MM:SS', or 13-digit epoch ms. Default '-1h'."
        ),
    )
    end_time: Optional[str] = Field(
        default=None,
        description="Exclusive end. Default 'now'.",
    )
    level: Optional[Literal["all", "warning", "error"]] = Field(
        default=None,
        description="Error-log mode: filter by severity level.",
    )
    database: Optional[str] = Field(
        default=None,
        description="Slow-log mode: filter by database name.",
    )
    min_duration_ms: int = Field(
        default=1000,
        ge=0,
        description=(
            "Slow-log mode: minimum execution duration in milliseconds. "
            "Only slow queries with avg duration >= this value are returned. "
            "Default 1000 (1 second)."
        ),
    )
    sort_by: Literal["duration", "count"] = Field(
        default="duration",
        description=(
            "Slow-log mode: sort order. 'duration' sorts by avg execution time "
            "(slowest first). 'count' sorts by execution frequency "
            "(most frequent first) — best for finding high-impact SQL patterns."
        ),
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Max records to return (1..100). Default 50.",
    )


# ---------------------------------------------------------------------------
# rds_list_db_resources — merged databases + accounts
# ---------------------------------------------------------------------------
class ListDbResourcesInput(BaseModel):
    instance_id: str = Field(
        ..., description="RDS instance id."
    )
    resource_type: Literal["databases", "accounts"] = Field(
        ...,
        description=(
            "Resource type: 'databases' to list all databases (name, charset, "
            "comment), 'accounts' to list all DB accounts and their privileges "
            "(name, databases, hosts, comment)."
        ),
    )
    page: Optional[int] = Field(
        default=None,
        ge=1,
        description="Page number (1-based).",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (1..100).",
    )


# ---------------------------------------------------------------------------
# rds_list_backups — ListBackupsRequest
# ---------------------------------------------------------------------------
class ListBackupsInput(BaseModel):
    instance_id: Optional[str] = Field(
        default=None,
        description="Filter by instance id.",
    )
    backup_id: Optional[str] = Field(
        default=None,
        description="Get a specific backup by id.",
    )
    backup_type: Optional[Literal["auto", "manual"]] = Field(
        default=None,
        description="Filter by backup type: 'auto' or 'manual'.",
    )
    status: Optional[str] = Field(
        default=None,
        description="Filter by status (BUILDING, COMPLETED, FAILED, etc.).",
    )
    begin_time: Optional[str] = Field(
        default=None,
        description="Filter: backups started after this time.",
    )
    end_time: Optional[str] = Field(
        default=None,
        description="Filter: backups started before this time.",
    )
    offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Page offset.",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Page size (1..100).",
    )


# ---------------------------------------------------------------------------
# rds_get_instance_metrics — cross-call CES
# ---------------------------------------------------------------------------
class GetInstanceMetricsInput(BaseModel):
    instance_id: str = Field(
        ..., description="RDS instance id."
    )
    metrics: list[str] = Field(
        default_factory=lambda: [
            "rds001_cpu_util",
            "rds002_mem_util",
            "rds003_iops",
            "rds004_connections",
            "rds005_disk_util",
        ],
        min_length=1,
        max_length=20,
        description=(
            "Metric names to query. Common RDS metrics: "
            "rds001_cpu_util (CPU%), rds002_mem_util (memory%), "
            "rds003_iops (IOPS), rds004_connections (active connections), "
            "rds005_disk_util (disk usage%). "
            "Default: all five core metrics."
        ),
    )
    from_time: Optional[str] = Field(
        default=None,
        description="Window start. Default '-30m'.",
    )
    to_time: Optional[str] = Field(
        default=None,
        description="Window end. Default 'now'.",
    )
    period: Optional[int] = Field(
        default=None,
        description=(
            "Aggregation period in seconds. "
            "1=original, 300=5min, 1200=20min, 3600=1h. Default 300."
        ),
    )
    filter: Literal["average", "max", "min", "sum", "variance"] = Field(
        default="average",
        description="Aggregation function.",
    )


# ---------------------------------------------------------------------------
# rds_describe_parameter_group — list/show configurations
# ---------------------------------------------------------------------------
class DescribeParameterGroupInput(BaseModel):
    config_id: Optional[str] = Field(
        default=None,
        description=(
            "Parameter group (configuration) id. If None/empty, lists all "
            "parameter groups. If set, shows that group's parameters."
        ),
    )
    instance_id: Optional[str] = Field(
        default=None,
        description=(
            "If set (and config_id is None), shows the parameter configuration "
            "currently applied to this specific instance. This takes precedence "
            "over listing all groups."
        ),
    )


# ---------------------------------------------------------------------------
# rds_list_replicas — replicas + replication status
# ---------------------------------------------------------------------------
class ListReplicasInput(BaseModel):
    instance_id: str = Field(
        ...,
        description=(
            "Primary instance id. Returns its read-only replicas and "
            "replication delay status."
        ),
    )


# ---------------------------------------------------------------------------
# rds_create_manual_backup — CreateManualBackupRequest (two-phase)
# ---------------------------------------------------------------------------
class CreateManualBackupInput(BaseModel):
    instance_id: str = Field(..., description="RDS instance id to back up.")
    name: Optional[str] = Field(
        default=None,
        description="Backup name. Auto-generated if omitted.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Backup description.",
    )


# ---------------------------------------------------------------------------
# rds_confirm_destructive — two-phase commit
# ---------------------------------------------------------------------------
class ConfirmDestructiveInput(BaseModel):
    approval_id: str = Field(..., description="Approval id from a pending operation.")


# ---------------------------------------------------------------------------
# rds_audit_instance_security — composite security audit
# ---------------------------------------------------------------------------
class AuditInstanceSecurityInput(BaseModel):
    instance_id: str = Field(..., description="RDS instance id to audit.")
