"""pipeline_set_status — toggle ban (enabled/disabled) state.

The CodeArts API exposes:
  PUT /v5/{project_id}/api/pipelines/{pipeline_id}/unban   (EnablePipeline)
  PUT /v5/{project_id}/api/pipelines/{pipeline_id}/ban     (DisablePipeline)

The current SDK release does not ship typed wrappers for these endpoints, so
we route through ``Client.do_http_request`` — the SDK still does AK/SK
signing, region routing, retry, and timeouts for us.

This module previously exposed two separate tools (``pipeline_enable`` /
``pipeline_disable``). They were merged into a single ``pipeline_set_status``
tool dispatched by ``status="enabled"|"disabled"`` to shrink the MCP startup
context.

Destructive ops (status="disabled") use two-phase commit:
  Phase 1: returns preview + approval_id (NO execution)
  Phase 2: user approves → LLM calls pipeline_confirm_destructive(approval_id)
"""
from __future__ import annotations

import logging
from typing import Optional

from ....client import get_client
from ..client_helpers import call_raw_put
from ....config import Settings, resolve_project_id
from ....errors import ToolError, pending_actions, wrap_tool
from mcp_auth_common import create_auth_strategy, current_scope, require_role
from ..models import PipelineSetStatusInput

log = logging.getLogger("huaweicloud_mcp.services.pipeline.tools.lifecycle")


def make_lifecycle_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def pipeline_set_status(
        pipeline_id: str,
        status: str,
        project_id: Optional[str] = None,
    ) -> dict:
        """Enable or disable a pipeline (toggle ban state).

        Replaces the old pair ``pipeline_enable`` / ``pipeline_disable``.

        Status semantics:
          * ``status="enabled"``  -> PUT .../unban. Non-destructive — resumes
            code-event triggers and scheduled runs. Executes immediately.
            Manual triggers continue to work in either state.
          * ``status="disabled"`` -> PUT .../ban.  ⚠ DESTRUCTIVE — stops
            automatic triggers (code-push / merge / scheduled runs are
            ignored until re-enabled). Manual runs may also be blocked
            depending on tenant policy. Returns a preview + approval_id.
            Use pipeline_confirm_destructive to execute after user approval.

        Args:
            pipeline_id: pipeline UUID.
            status: "enabled" or "disabled".
            project_id: CodeArts project UUID. Defaults to
                CODEARTS_DEFAULT_PROJECT_ID.

        Returns:
          For status="enabled": {"pipeline_id": "...", "status": "enabled", "enabled": true}
          For status="disabled": {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = PipelineSetStatusInput(
            pipeline_id=pipeline_id,
            status=status,
            project_id=project_id,
        )
        pid = resolve_project_id(settings, params.project_id)
        client = get_client("pipeline", settings)

        if params.status == "enabled":
            resource_path = "/v5/{project_id}/api/pipelines/{pipeline_id}/unban"
            result = call_raw_put(
                client,
                resource_path=resource_path,
                path_params={"project_id": pid, "pipeline_id": params.pipeline_id},
            )
            if not result.get("ok"):
                raise ToolError(
                    code=result.get("error_code", "UNBAN_FAILED"),
                    message=result.get("error_msg", "Pipeline unban API returned error"),
                )
            log.info(
                "pipeline.set_status pipeline_id=%s project_id=%s status=enabled",
                params.pipeline_id, pid,
            )
            return {
                "pipeline_id": params.pipeline_id,
                "status": "enabled",
                "enabled": True,
            }

        # status == "disabled" — destructive, two-phase commit
        action_label = f"pipeline_set_status(status='disabled', pipeline_id={params.pipeline_id!r})"

        def _execute() -> dict:
            resource_path = "/v5/{project_id}/api/pipelines/{pipeline_id}/ban"
            result = call_raw_put(
                client,
                resource_path=resource_path,
                path_params={"project_id": pid, "pipeline_id": params.pipeline_id},
            )
            if not result.get("ok"):
                raise ToolError(
                    code=result.get("error_code", "BAN_FAILED"),
                    message=result.get("error_msg", "Pipeline ban API returned error"),
                )
            log.info(
                "pipeline.set_status pipeline_id=%s project_id=%s status=disabled",
                params.pipeline_id, pid,
            )
            return {
                "pipeline_id": params.pipeline_id,
                "status": "disabled",
                "enabled": False,
            }

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "disable_pipeline",
                "pipeline_id": params.pipeline_id,
                "project_id": pid,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "disable_pipeline",
            "pipeline_id": params.pipeline_id,
            "message": (
                f"⚠ Disabling pipeline stops automatic triggers. Present this "
                f"preview to the user and ask for explicit approval. If approved, "
                f"call pipeline_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    @wrap_tool
    def pipeline_confirm_destructive(approval_id: str) -> dict:
        """Execute a previously requested destructive pipeline operation after user approval.

        Call this ONLY after the user has explicitly approved the operation.
        The approval_id comes from the original destructive tool call
        (pipeline_set_status with status="disabled", or pipeline_update_info).

        Approval IDs expire after 120 seconds. If expired, re-issue the
        original operation to get a new approval_id.

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
            approval_id,
            entry["action"],
        )
        return entry["execute_fn"]()

    return {
        "pipeline_set_status": pipeline_set_status,
        "pipeline_confirm_destructive": pipeline_confirm_destructive,
    }