"""Pydantic input models for CCE MCP tools.

CCE resource ids are 32-hex-char strings (with or without hyphens). We
keep validation lenient — Huawei Cloud's API will reject malformed ids
with a precise error code that we surface back to the caller.

Tools in this service follow a single-tool list/detail pattern: pass
``cluster_id=None`` for a list, pass a value to fetch a single detail.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# CCE ids are usually 32 hex (no hyphens), but some endpoints return them
# with hyphens. Accept both shapes.
_ID_RE = re.compile(r"^[0-9a-fA-F\-]{16,64}$")


def _check_id(v: str, field: str) -> str:
    if not _ID_RE.match(v):
        raise ValueError(f"{field} must be a 16..64 char hex/uuid string, got {v!r}")
    return v


# CCE uses the literal string "DefaultPool" as the id for the auto-created
# default node pool.  Allow it alongside normal UUID ids.
_DEFAULT_POOL_ID = "DefaultPool"


def _check_nodepool_id(v: str, field: str = "nodepool_id") -> str:
    if v == _DEFAULT_POOL_ID:
        return v
    return _check_id(v, field)


# ---------------------------------------------------------------------------
# cce_query_clusters
# ---------------------------------------------------------------------------
class QueryClustersInput(BaseModel):
    cluster_id: Optional[str] = Field(
        default=None,
        description=(
            "Cluster id. If None/empty, returns the cluster LIST. "
            "If set, returns DETAIL for that single cluster."
        ),
    )
    type: Optional[Literal["VirtualMachine", "ARM64"]] = Field(
        default=None,
        description="List-mode filter: cluster type. Ignored when cluster_id is set.",
    )
    status: Optional[
        Literal[
            "Available", "Unavailable", "ScalingUp", "ScalingDown",
            "Creating", "Deleting", "Upgrading", "Resizing", "RollingBack",
            "RollbackFailed", "Empty", "Error",
        ]
    ] = Field(
        default=None,
        description="List-mode filter: cluster phase/status. Ignored when cluster_id is set.",
    )
    version: Optional[str] = Field(
        default=None,
        description="List-mode filter: Kubernetes version (e.g. 'v1.27'). Ignored when cluster_id is set.",
    )
    detail: bool = Field(
        default=False,
        description=(
            "Detail-mode flag (forwarded to Huawei Cloud as the `detail` query "
            "param). For LIST mode, set true to include extra fields per cluster."
        ),
    )

    @field_validator("cluster_id")
    @classmethod
    def _v_cluster_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _check_id(v, "cluster_id")


# ---------------------------------------------------------------------------
# cce_query_nodes
# ---------------------------------------------------------------------------
class QueryNodesInput(BaseModel):
    cluster_id: str = Field(..., description="Cluster id that owns the node(s).")
    node_id: Optional[str] = Field(
        default=None,
        description=(
            "Node id. If None/empty, returns the LIST of nodes in the cluster. "
            "If set, returns DETAIL for that single node."
        ),
    )

    @field_validator("cluster_id")
    @classmethod
    def _v_cid(cls, v: str) -> str:
        return _check_id(v, "cluster_id")

    @field_validator("node_id")
    @classmethod
    def _v_nid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _check_id(v, "node_id")


# ---------------------------------------------------------------------------
# cce_query_nodepools
# ---------------------------------------------------------------------------
class QueryNodePoolsInput(BaseModel):
    cluster_id: str = Field(..., description="Cluster id that owns the node pool(s).")
    nodepool_id: Optional[str] = Field(
        default=None,
        description=(
            "Node pool id. If None/empty, returns the LIST of node pools in "
            "the cluster. If set, returns DETAIL for that single pool."
        ),
    )
    show_default_node_pool: bool = Field(
        default=False,
        description=(
            "List-mode flag: include the auto-created `DefaultPool` virtual "
            "node pool in the list. Ignored when nodepool_id is set."
        ),
    )

    @field_validator("cluster_id")
    @classmethod
    def _v_cid(cls, v: str) -> str:
        return _check_id(v, "cluster_id")

    @field_validator("nodepool_id")
    @classmethod
    def _v_pid(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return _check_nodepool_id(v)


# ---------------------------------------------------------------------------
# cce_update_nodepool — initialNodeCount only (whole-record PUT semantics,
# but the SDK accepts a partial NodePoolSpecUpdate body).
# ---------------------------------------------------------------------------
class UpdateNodePoolInput(BaseModel):
    cluster_id: str = Field(..., description="Cluster id that owns the node pool.")
    nodepool_id: str = Field(..., description="Node pool id to update.")
    initial_node_count: int = Field(
        ...,
        ge=0,
        le=2000,
        description=(
            "Target desired node count for the pool. CCE will scale toward "
            "this number (up or down). 0..2000. ⚠ Scaling DOWN destroys "
            "existing nodes and the workloads they run."
        ),
    )

    @field_validator("cluster_id")
    @classmethod
    def _v_cid(cls, v: str) -> str:
        return _check_id(v, "cluster_id")

    @field_validator("nodepool_id")
    @classmethod
    def _v_pid(cls, v: str) -> str:
        return _check_nodepool_id(v)


# ---------------------------------------------------------------------------
# cce_get_job
# ---------------------------------------------------------------------------
class GetJobInput(BaseModel):
    job_id: str = Field(..., description="Job id returned by a CCE async operation.")

    @field_validator("job_id")
    @classmethod
    def _v(cls, v: str) -> str:
        return _check_id(v, "job_id")


# ---------------------------------------------------------------------------
# Approval — shared with the gateway-level confirm tool pattern.
# ---------------------------------------------------------------------------
class ConfirmDestructiveInput(BaseModel):
    approval_id: str = Field(
        ...,
        description=(
            "The approval_id from a pending destructive operation. "
            "Obtain it from the original tool call's response."
        ),
    )
