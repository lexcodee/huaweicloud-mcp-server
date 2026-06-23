"""Lifecycle operation tools (start, stop, reboot, delete, resize).

Destructive ops use a TWO-PHASE COMMIT pattern to prevent LLM bypass:

  Phase 1: Call the destructive tool → returns preview + approval_id
           (NO execution happens)
  Phase 2: LLM presents preview to user, asks for explicit approval
           User approves → LLM calls ecs_confirm_destructive(approval_id)
           → action executes

This prevents the LLM from auto-filling confirm=true without user consent.

Tool-level RBAC:
  - ecs_power_action(action="start")  → operator
  - ecs_power_action(action="stop"/"reboot") → admin (two-phase)
  - ecs_delete_server  → admin (two-phase)
  - ecs_resize_server  → admin (two-phase)
  - ecs_confirm_destructive → operator (the approval already happened)
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkecs.v2 import (
    BatchRebootServersRequest,
    BatchRebootServersRequestBody,
    BatchRebootSeversOption,
    BatchStartServersOption,
    BatchStartServersRequest,
    BatchStartServersRequestBody,
    BatchStopServersOption,
    BatchStopServersRequest,
    BatchStopServersRequestBody,
    DeleteServersRequest,
    DeleteServersRequestBody,
    ResizePostPaidServerOption,
    ResizePrePaidServerOption,
    ResizeServerRequest,
    ResizeServerRequestBody,
    ServerId,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import pending_actions, wrap_tool
from ..models import (
    DeleteServersInput,
    PowerActionInput,
    ResizeServerInput,
)

log = logging.getLogger("huaweicloud_mcp.services.ecs.tools.lifecycle")


def _as_server_ids(ids: list[str]) -> list[ServerId]:
    return [ServerId(id=i) for i in ids]


def make_lifecycle_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def ecs_power_action(
        server_ids: list[str],
        action: str,
        type: str = "SOFT",
    ) -> dict:
        """Apply a batch power action to one or more ECS servers.

        Replaces the old trio ecs_start_server / ecs_stop_server /
        ecs_reboot_server. One tool, dispatched by ``action``.

        Actions:
          * ``"start"`` — power on stopped servers. Non-destructive,
            executes immediately.
          * ``"stop"``  — ⚠ DESTRUCTIVE. Graceful (SOFT) or forced (HARD)
            shutdown. Returns a preview + approval_id. Use
            ecs_confirm_destructive to execute after user approval.
          * ``"reboot"`` — ⚠ DESTRUCTIVE. SOFT = guest-level reboot;
            HARD = power-cycle (may lose unflushed writes). Returns a
            preview + approval_id. Use ecs_confirm_destructive to execute
            after user approval.

        Args:
            server_ids: 1..1000 ECS server UUIDs (all receive the same action).
            action: One of "start" | "stop" | "reboot".
            type: "SOFT" (default) or "HARD". Only honored for stop/reboot.

        Returns:
          For action="start": {"job_id": "...", "action": "start"}
          For destructive actions: {"status": "pending_approval",
              "approval_id": "...", "action": "...", "server_ids": [...],
              "type": "...", "message": "..."}
        """
        identity = auth.resolve(current_scope())
        # Role depends on action: start → operator, stop/reboot → admin.
        if action == "start":
            require_role(identity, "operator")
        else:
            require_role(identity, "admin")

        params = PowerActionInput(
            server_ids=server_ids,
            action=action,
            type=type,
        )
        client = get_client("ecs", settings)
        servers = _as_server_ids(params.server_ids)

        if params.action == "start":
            body = BatchStartServersRequestBody(
                os_start=BatchStartServersOption(servers=servers)
            )
            resp = client.batch_start_servers(BatchStartServersRequest(body=body))
            return {"job_id": resp.job_id, "action": "start"}

        # Destructive — two-phase commit
        # Phase 1: store the execution lambda, return preview + approval_id
        if params.action == "stop":
            action_label = f"ecs_power_action(action='stop', type={params.type!r}, servers={params.server_ids})"

            def _execute() -> dict:
                body = BatchStopServersRequestBody(
                    os_stop=BatchStopServersOption(servers=servers, type=params.type)
                )
                resp = client.batch_stop_servers(BatchStopServersRequest(body=body))
                return {"job_id": resp.job_id, "action": "stop"}

        else:  # reboot
            action_label = f"ecs_power_action(action='reboot', type={params.type!r}, servers={params.server_ids})"

            def _execute() -> dict:
                body = BatchRebootServersRequestBody(
                    reboot=BatchRebootSeversOption(servers=servers, type=params.type)
                )
                resp = client.batch_reboot_servers(BatchRebootServersRequest(body=body))
                return {"job_id": resp.job_id, "action": "reboot"}

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": params.action,
                "server_ids": params.server_ids,
                "type": params.type,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": params.action,
            "server_ids": params.server_ids,
            "type": params.type,
            "message": (
                f"⚠ {params.action} is destructive. Present this preview to the user "
                f"and ask for explicit approval. If approved, call "
                f"ecs_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    @wrap_tool
    def ecs_delete_server(
        server_ids: list[str],
        delete_publicip: bool = False,
        delete_volume: bool = False,
    ) -> dict:
        """⚠⚠ HIGHLY DESTRUCTIVE: permanently delete ECS servers.

        Deletion is irreversible. Optionally also releases EIPs and deletes
        attached EVS data disks (with delete_volume=true the data IS LOST).

        This is a TWO-PHASE operation: returns a preview + approval_id.
        Use ecs_confirm_destructive to execute after user approval.

        Args:
            server_ids: 1..1000 UUIDs.
            delete_publicip: If true, release attached EIPs.
            delete_volume: If true, also delete attached data disks (DATA LOSS).

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = DeleteServersInput(
            server_ids=server_ids,
            delete_publicip=delete_publicip,
            delete_volume=delete_volume,
        )
        client = get_client("ecs", settings)

        action_label = (
            f"ecs_delete_server(servers={params.server_ids}, "
            f"delete_publicip={params.delete_publicip}, "
            f"delete_volume={params.delete_volume})"
        )

        def _execute() -> dict:
            body = DeleteServersRequestBody(
                servers=_as_server_ids(params.server_ids),
                delete_publicip=params.delete_publicip,
                delete_volume=params.delete_volume,
            )
            resp = client.delete_servers(DeleteServersRequest(body=body))
            return {"job_id": resp.job_id}

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "delete",
                "server_ids": params.server_ids,
                "delete_publicip": params.delete_publicip,
                "delete_volume": params.delete_volume,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "delete",
            "server_ids": params.server_ids,
            "delete_publicip": params.delete_publicip,
            "delete_volume": params.delete_volume,
            "message": (
                f"⚠⚠ DELETE is irreversible. Present this preview to the user "
                f"and ask for explicit approval. If approved, call "
                f"ecs_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    @wrap_tool
    def ecs_resize_server(
        server_id: str,
        target_flavor_ref: str,
        dedicated_host_id: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> dict:
        """⚠ DESTRUCTIVE: change a server's flavor (vCPU/RAM).

        Resize requires the server to be stopped (or pass mode='withStopServer'
        to allow the API to stop it). After API success the server enters
        VERIFY_RESIZE state — the user (or another tool) must confirm via
        the Huawei Cloud console / API for the change to become permanent.

        This is a TWO-PHASE operation: returns a preview + approval_id.
        Use ecs_confirm_destructive to execute after user approval.

        Args:
            server_id: Source server UUID.
            target_flavor_ref: Target flavor id (e.g. 's6.large.2').
            dedicated_host_id: Optional DeH id (only for prepaid hosts).
            mode: 'withStopServer' to permit resize while server is running.

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = ResizeServerInput(
            server_id=server_id,
            target_flavor_ref=target_flavor_ref,
            dedicated_host_id=dedicated_host_id,
            mode=mode,
        )
        client = get_client("ecs", settings)

        action_label = (
            f"ecs_resize_server(server={params.server_id}, "
            f"flavor={params.target_flavor_ref}, mode={params.mode!r})"
        )

        def _execute() -> dict:
            if params.dedicated_host_id:
                opt = ResizePrePaidServerOption(
                    flavor_ref=params.target_flavor_ref,
                    dedicated_host_id=params.dedicated_host_id,
                    mode=params.mode,
                )
            else:
                opt = ResizePostPaidServerOption(
                    flavor_ref=params.target_flavor_ref,
                    mode=params.mode,
                )
            body = ResizeServerRequestBody(resize=opt)
            resp = client.resize_server(
                ResizeServerRequest(server_id=params.server_id, body=body)
            )
            return {"job_id": resp.job_id}

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "resize",
                "server_id": params.server_id,
                "target_flavor_ref": params.target_flavor_ref,
                "dedicated_host_id": params.dedicated_host_id,
                "mode": params.mode,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "resize",
            "server_id": params.server_id,
            "target_flavor_ref": params.target_flavor_ref,
            "mode": params.mode,
            "message": (
                f"⚠ Resize is destructive. Present this preview to the user "
                f"and ask for explicit approval. If approved, call "
                f"ecs_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    @wrap_tool
    def ecs_confirm_destructive(approval_id: str) -> dict:
        """Execute a previously requested destructive operation after user approval.

        Call this ONLY after the user has explicitly approved the operation.
        The approval_id comes from the original destructive tool call
        (ecs_power_action, ecs_delete_server, or ecs_resize_server).

        Approval IDs expire after 120 seconds. If expired, re-issue the
        original operation to get a new approval_id.

        Args:
            approval_id: The approval_id from a pending destructive operation.

        Returns:
            The result of the executed operation (typically {"job_id": "..."}).
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        entry = pending_actions.pop(approval_id)
        log.info(
            "confirm_destructive approval_id=%s action=%s — executing",
            approval_id,
            entry["action"],
        )
        return entry["execute_fn"]()

    return {
        "ecs_power_action": ecs_power_action,
        "ecs_delete_server": ecs_delete_server,
        "ecs_resize_server": ecs_resize_server,
        "ecs_confirm_destructive": ecs_confirm_destructive,
    }