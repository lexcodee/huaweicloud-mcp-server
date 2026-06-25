"""RDS management tools — create manual backup (two-phase commit).

create_manual_backup is DESTRUCTIVE-adjacent (creates a resource but should
be confirmed before high-risk changes). Uses two-phase commit:
  Phase 1: call → returns preview + approval_id (no execution)
  Phase 2: user approves → call rds_confirm_destructive(approval_id)
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkrds.v3 import (
    CreateManualBackupRequest,
    CreateManualBackupRequestBody,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, pending_actions, wrap_tool
from ..models import ConfirmDestructiveInput, CreateManualBackupInput
from ..serializers import backup_info_summary

log = logging.getLogger("huaweicloud_mcp.services.rds.tools.manage")


def make_manage_tools(settings: Settings) -> dict:
    """Build RDS management tools bound to *settings*."""
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # create_manual_backup (two-phase)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def rds_create_manual_backup(
        instance_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """⚠ Create a manual backup snapshot — TWO-PHASE operation.

        Returns a preview + approval_id. Use rds_confirm_destructive to
        execute after user approval.

        This is the recommended pre-change safety action: create a backup
        before any high-risk modification (parameter changes, version
        upgrade, schema migration).

        Args:
            instance_id: RDS instance UUID to back up.
            name: Backup name. Auto-generated if omitted.
            description: Backup description.

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = CreateManualBackupInput(
            instance_id=instance_id,
            name=name,
            description=description,
        )
        client = get_client("rds", settings)

        action_label = f"rds_create_manual_backup(instance_id={params.instance_id}, name={params.name})"

        def _execute() -> dict:
            body = CreateManualBackupRequestBody(
                instance_id=params.instance_id,
                name=params.name,
                description=params.description,
            )
            resp = client.create_manual_backup(
                CreateManualBackupRequest(body=body)
            )
            backup = getattr(resp, "backup", None)
            return backup_info_summary(backup) if backup else {"created": True}

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "create_manual_backup",
                "instance_id": params.instance_id,
                "name": params.name,
                "description": params.description,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "create_manual_backup",
            "instance_id": params.instance_id,
            "name": params.name,
            "message": (
                f"Manual backup is ready to submit. Present this preview to the "
                f"user and ask for explicit approval. If approved, call "
                f"rds_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    # ------------------------------------------------------------------ #
    # confirm_destructive
    # ------------------------------------------------------------------ #
    @wrap_tool
    def rds_confirm_destructive(approval_id: str) -> dict:
        """Execute a previously requested destructive RDS operation.

        Call this ONLY after the user has explicitly approved the operation.
        Approval IDs expire after 120 seconds.

        Args:
            approval_id: The approval_id from a pending destructive operation.

        Returns:
            The result of the executed operation.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        entry = pending_actions.pop(approval_id)
        log.info(
            "confirm_destructive approval_id=%s action=%s — executing",
            approval_id, entry["action"],
        )
        return entry["execute_fn"]()

    return {
        "rds_create_manual_backup": rds_create_manual_backup,
        "rds_confirm_destructive": rds_confirm_destructive,
    }
