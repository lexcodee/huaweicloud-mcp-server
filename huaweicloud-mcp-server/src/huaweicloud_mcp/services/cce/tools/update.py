"""CCE node-pool update tool — `initialNodeCount` only.

Why so narrow? Editing the full NodePoolSpecUpdate (taints, k8s tags,
node template, etc.) is a major operation that should go through the
console / IaC. This tool exists for the single hot use case: an LLM
operator scaling a pool up or down on demand. Other fields are
intentionally rejected by the input model — broaden it deliberately,
not by accident.

Destructive path (scale-down) uses the project's standard two-phase
commit pattern: phase 1 returns preview + approval_id, phase 2 executes
via the shared ``cce_confirm_destructive`` tool.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkcce.v3 import (
    NodePoolSpecUpdate,
    NodePoolUpdate,
    UpdateNodePoolRequest,
    ShowNodePoolRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, pending_actions, wrap_tool
from ..models import _DEFAULT_POOL_ID, UpdateNodePoolInput
from ..serializers import nodepool_summary

log = logging.getLogger("huaweicloud_mcp.services.cce.tools.update")


def _fetch_current(client, cluster_id: str, nodepool_id: str):
    """Read the pool's current state. Used to render the diff preview."""
    req = ShowNodePoolRequest(cluster_id=cluster_id, nodepool_id=nodepool_id)
    resp = client.show_node_pool(req)
    if resp is None or (resp.metadata is None and resp.spec is None):
        raise ToolError(
            code="NOT_FOUND",
            message=f"node pool {nodepool_id} not found in cluster {cluster_id}",
        )
    return resp


def make_update_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def cce_update_nodepool(
        cluster_id: str,
        nodepool_id: str,
        initial_node_count: int,
    ) -> dict:
        """Resize a CCE node pool by setting its desired ``initialNodeCount``.

        CCE reconciles toward this number — scale up adds nodes, scale
        down terminates nodes. Behavior summary:

          * Scale UP (new > current)  → non-destructive (new ECS nodes
            join the cluster). Executes immediately, returns ``job_id``.
          * Scale DOWN (new < current) → ⚠ DESTRUCTIVE. Existing nodes
            are removed; workloads on them are evicted/lost. Returns a
            preview + approval_id; the actual API call only happens
            after ``cce_confirm_destructive(approval_id)``.
          * No-op (new == current)    → returns ``{"status":"noop"}``.

        Only ``initialNodeCount`` is sent in the update body — every
        other field on the pool is preserved by Huawei Cloud's
        PATCH-style behavior on this endpoint. Use the console / Terraform
        for richer edits (taints, labels, scaling policy, etc.).

        Args:
            cluster_id: Cluster id that owns the pool.
            nodepool_id: Node-pool id to resize.
            initial_node_count: Target desired node count (0..2000).

        Returns:
            Scale up:   {"job_id": ..., "action": "scale_up",
                         "from": int, "to": int}
            Scale down: {"status": "pending_approval", "approval_id": ...,
                         "action": "scale_down", "from": int, "to": int,
                         "message": ...}
            No-op:      {"status": "noop", "current": int, "requested": int}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = UpdateNodePoolInput(
            cluster_id=cluster_id,
            nodepool_id=nodepool_id,
            initial_node_count=initial_node_count,
        )

        if params.nodepool_id == _DEFAULT_POOL_ID:
            raise ToolError(
                code="NOT_SUPPORTED",
                message=(
                    "DefaultPool does not support scaling. "
                    "Please create a custom node pool and scale that instead."
                ),
            )

        client = get_client("cce", settings)

        current = _fetch_current(client, params.cluster_id, params.nodepool_id)
        cur_spec = current.spec
        current_count = getattr(cur_spec, "initial_node_count", None)
        if current_count is None:
            # Pool may not expose initial_node_count (managed pools); fall
            # back to the running count.
            current_count = getattr(current.status, "current_node", None) or 0

        target = params.initial_node_count

        if target == current_count:
            return {
                "status": "noop",
                "current": current_count,
                "requested": target,
            }

        def _execute() -> dict:
            body = NodePoolUpdate(
                spec=NodePoolSpecUpdate(initial_node_count=target),
            )
            resp = client.update_node_pool(
                UpdateNodePoolRequest(
                    cluster_id=params.cluster_id,
                    nodepool_id=params.nodepool_id,
                    body=body,
                )
            )
            job_id = getattr(getattr(resp, "status", None), "job_id", None)
            return {
                "job_id": job_id,
                "action": "scale_up" if target > current_count else "scale_down",
                "from": current_count,
                "to": target,
                "nodepool": nodepool_summary(resp),
            }

        if target > current_count:
            # Scale up — execute immediately.
            return _execute()

        # Scale down — two-phase commit.
        action_label = (
            f"cce_update_nodepool(cluster={params.cluster_id}, "
            f"pool={params.nodepool_id}, count {current_count} → {target})"
        )
        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "scale_down",
                "cluster_id": params.cluster_id,
                "nodepool_id": params.nodepool_id,
                "from": current_count,
                "to": target,
                "delta": target - current_count,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "scale_down",
            "cluster_id": params.cluster_id,
            "nodepool_id": params.nodepool_id,
            "from": current_count,
            "to": target,
            "message": (
                f"⚠ Scaling DOWN from {current_count} → {target} will remove "
                f"{current_count - target} node(s) and disrupt workloads "
                "scheduled on them. Present this preview to the user and "
                "ask for explicit approval. If approved, call "
                f"cce_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    @wrap_tool
    def cce_confirm_destructive(approval_id: str) -> dict:
        """Execute a previously requested destructive CCE operation.

        Call this ONLY after the user has explicitly approved the
        operation. The ``approval_id`` comes from the original tool call
        (currently only ``cce_update_nodepool`` for scale-down). Approval
        IDs expire after 120 seconds — re-issue if expired.

        Args:
            approval_id: From a pending destructive operation.

        Returns:
            The result of the executed operation (e.g. {"job_id": ..., ...}).
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        entry = pending_actions.pop(approval_id)
        log.info(
            "cce.confirm_destructive approval_id=%s action=%s — executing",
            approval_id,
            entry["action"],
        )
        return entry["execute_fn"]()

    return {
        "cce_update_nodepool": cce_update_nodepool,
        "cce_confirm_destructive": cce_confirm_destructive,
    }
