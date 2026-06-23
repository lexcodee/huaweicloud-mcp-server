"""Pydantic input models for MCP tools.

These models are used with FastMCP's tool registration so that FastMCP
emits a JSON Schema for each tool to clients (Hermes / Claude Desktop).

Destructive operations no longer have a `confirm` parameter — they use
a two-phase commit pattern instead. See lifecycle.py for details.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

def _check_uuid(v: str) -> str:
    if not UUID_RE.match(v):
        raise ValueError(f"not a valid UUID: {v!r}")
    return v

# ============================================================
# Query
# ============================================================
class ListServersInput(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="Filter by server name (substring match by Huawei Cloud).",
    )
    status: Optional[
        Literal[
            "ACTIVE", "SHUTOFF", "ERROR", "BUILD", "REBOOT", "HARD_REBOOT",
            "REBUILD", "MIGRATING", "RESIZE", "VERIFY_RESIZE", "REVERT_RESIZE",
            "DELETED", "PAUSED", "SUSPENDED", "SHELVED", "SHELVED_OFFLOADED",
        ]
    ] = Field(default=None, description="Filter by server power/lifecycle status.")
    flavor_id: Optional[str] = Field(default=None, description="Filter by flavor id.")
    ip: Optional[str] = Field(default=None, description="Filter by private IPv4 substring.")
    tags: Optional[str] = Field(
        default=None,
        description="Filter by tags. Format: 'key=value' or 'key1=v1,key2=v2'.",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Page size, default 20, max 100.")
    offset: int = Field(default=1, ge=1, description="Page number (1-based), default 1.")

class GetServerInput(BaseModel):
    server_id: str = Field(..., description="ECS server UUID.")
    detail_level: Literal["status", "full"] = Field(
        default="full",
        description=(
            "'status' = lightweight {server_id,name,status,task_state,power_state} "
            "via ShowServer (fast, ideal for polling). "
            "'full' (default) = complete server detail with flavor, volumes, "
            "security groups, addresses, metadata via ListServersDetails."
        ),
    )

    @field_validator("server_id")
    @classmethod
    def _v(cls, v: str) -> str:
        return _check_uuid(v)

class ListFlavorsInput(BaseModel):
    availability_zone: Optional[str] = Field(
        default=None, description="Restrict to a specific AZ, e.g. 'af-south-1a'."
    )
    limit: int = Field(default=50, ge=1, le=200, description="Max flavors to return.")

# ============================================================
# Lifecycle
# ============================================================
class ServerIdsInput(BaseModel):
    server_ids: list[str] = Field(
        ..., min_length=1, max_length=1000, description="One or more ECS server UUIDs."
    )

    @field_validator("server_ids")
    @classmethod
    def _check_uuids(cls, v: list[str]) -> list[str]:
        for sid in v:
            _check_uuid(sid)
        return v

class StartServersInput(ServerIdsInput):
    pass

class PowerActionInput(ServerIdsInput):
    action: Literal["start", "stop", "reboot"] = Field(
        ...,
        description=(
            "Power action to apply to all server_ids: "
            "'start' (power on, non-destructive, executes immediately), "
            "'stop' (graceful shutdown, two-phase approval), "
            "'reboot' (restart, two-phase approval)."
        ),
    )
    type: Literal["SOFT", "HARD"] = Field(
        default="SOFT",
        description=(
            "Only honored for stop/reboot. "
            "SOFT = graceful via guest OS; HARD = force power-cycle (may lose data). "
            "Ignored when action='start'."
        ),
    )


class DeleteServersInput(ServerIdsInput):
    delete_publicip: bool = Field(
        default=False, description="If true, also release attached EIPs."
    )
    delete_volume: bool = Field(
        default=False,
        description="If true, also delete attached EVS data disks. DATA LOSS RISK.",
    )


class ResizeServerInput(BaseModel):
    server_id: str = Field(..., description="ECS server UUID to resize.")
    target_flavor_ref: str = Field(
        ..., description="Target flavor id (use ecs_list_flavors to discover)."
    )
    dedicated_host_id: Optional[str] = Field(
        default=None, description="Optional DeH id (only for prepaid/dedicated hosts)."
    )
    mode: Optional[Literal["withStopServer"]] = Field(
        default=None,
        description="If 'withStopServer', allow resize even when the server is running.",
    )

    @field_validator("server_id")
    @classmethod
    def _v(cls, v: str) -> str:
        return _check_uuid(v)

# ============================================================
# Job
# ============================================================
class GetJobInput(BaseModel):
    job_id: str = Field(..., description="Job id returned by an asynchronous ECS operation.")

# ============================================================
# Approval
# ============================================================
class ConfirmDestructiveInput(BaseModel):
    approval_id: str = Field(
        ...,
        description=(
            "The approval_id from a pending destructive operation. "
            "Obtain it from the original tool call's response."
        ),
    )