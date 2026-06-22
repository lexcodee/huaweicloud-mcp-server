"""pipeline_update_info — read-modify-write for limited fields.

⚠⚠ The CodeArts UpdatePipelineInfo API is a full PUT replacement, NOT a
PATCH. Any field omitted from the request body is reset on the server.
This tool MUST therefore:
  1. fetch the current pipeline detail
  2. mutate ONLY the fields the caller asked to change
  3. serialise the full PipelineDTO back

Currently supported mutations:
  * sources[].params.default_branch (selected by source_alias, or sources[0])
  * definition.stages[0].pre[].task   (with allow-list of values)

The caller MUST pass confirm=true to acknowledge the race-condition risk
inherent to whole-record PUT.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from huaweicloudsdkcodeartspipeline.v2.model import (
    CodeSource,
    CodeSourceParams,
    CustomVariable,
    PipelineDTO,
    PipelineSchedule,
    PipelineTrigger,
    ShowPipelineDetailRequest,
    UpdatePipelineInfoRequest,
)

from ..client import get_client
from ..config import Settings, resolve_project_id
from ..definition_utils import (
    ALLOWED_PRE_TASK_VALUES,
    dump_definition,
    parse_definition,
    summarise_definition,
    update_first_stage_pre_tasks,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ..errors import ToolError, pending_actions, wrap_tool
from ..models import PipelineUpdateInfoInput

log = logging.getLogger("pipeline_mcp_server.tools.update")


# ---------------------------------------------------------------------------
# Helpers — rebuild SDK objects from a detail response (which exposes
# PipelineSource / PipelineSourceParam / CustomVariable / PipelineSchedule /
# PipelineTrigger). We translate them to the types accepted by PipelineDTO
# (CodeSource / CodeSourceParams / CustomVariable / PipelineSchedule /
# PipelineTrigger). For variables/schedules/triggers the type is the same;
# for sources we have to re-pack into CodeSource(+CodeSourceParams).
# ---------------------------------------------------------------------------

def _copy_attrs(src, dst, names: list) -> None:
    for n in names:
        if hasattr(src, n):
            v = getattr(src, n)
            if v is not None:
                setattr(dst, n, v)


def _to_code_source(detail_source) -> CodeSource:
    cs = CodeSource()
    if getattr(detail_source, "type", None) is not None:
        cs.type = detail_source.type
    src_params = getattr(detail_source, "params", None)
    if src_params is not None:
        params = CodeSourceParams()
        # CodeSourceParams supports a subset of PipelineSourceParam — copy
        # only the fields it actually exposes.
        for n in (
            "git_type", "codehub_id", "endpoint_id", "default_branch",
            "git_url", "ssh_git_url", "web_url", "repo_name", "alias",
        ):
            if hasattr(src_params, n):
                v = getattr(src_params, n)
                if v is not None:
                    setattr(params, n, v)
        cs.params = params
    return cs


def _to_custom_variable(detail_var) -> CustomVariable:
    cv = CustomVariable()
    _copy_attrs(detail_var, cv, [
        "name", "sequence", "type", "value", "is_secret",
        "description", "is_runtime", "limits", "is_reset",
        "latest_value", "runtime_value",
    ])
    return cv


def _to_schedule(detail_sched) -> PipelineSchedule:
    s = PipelineSchedule()
    _copy_attrs(detail_sched, s, [
        "uuid", "type", "name", "enable", "days_of_week", "time_zone",
    ])
    return s


def _to_trigger(detail_trigger) -> PipelineTrigger:
    t = PipelineTrigger()
    _copy_attrs(detail_trigger, t, [
        "git_url", "git_type", "is_auto_commit", "events", "hook_id",
        "repo_id", "endpoint_id", "callback_url", "security_token",
    ])
    return t


# ---------------------------------------------------------------------------

def _short_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _select_source_index(detail, source_alias: Optional[str]) -> int:
    sources = getattr(detail, "sources", None) or []
    if not sources:
        raise ToolError(
            code="NO_SOURCE",
            message="pipeline has no sources; cannot update default_branch.",
        )
    if source_alias is None:
        if len(sources) == 1:
            return 0
        aliases = [
            getattr(getattr(s, "params", None), "alias", None) for s in sources
        ]
        raise ToolError(
            code="SOURCE_ALIAS_REQUIRED",
            message=(
                f"pipeline has {len(sources)} code sources; pass source_alias "
                f"to disambiguate. Available aliases: {aliases}"
            ),
        )
    for i, src in enumerate(sources):
        params = getattr(src, "params", None)
        if params is not None and getattr(params, "alias", None) == source_alias:
            return i
    raise ToolError(
        code="SOURCE_ALIAS_NOT_FOUND",
        message=f"no code source with alias={source_alias!r} on this pipeline.",
    )


# ---------------------------------------------------------------------------

def make_update_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def pipeline_update_info(
        pipeline_id: str,
        project_id: Optional[str] = None,
        new_default_branch: Optional[str] = None,
        source_alias: Optional[str] = None,
        new_pre_task: Optional[str] = None,
        pre_sequence: Optional[int] = None,
    ) -> dict:
        """⚠ DESTRUCTIVE: update pipeline configuration (default branch and/or
        first-stage pre-task).

        The CodeArts UpdatePipelineInfo API replaces the WHOLE pipeline record
        on every call. This tool reads the current detail, mutates only the
        fields you pass, and PUTs the merged record back. There is a small
        race window: if someone edits the pipeline in the console between
        our read and our write, their edit will be overwritten.

        This is a TWO-PHASE operation: returns a preview + approval_id.
        Use pipeline_confirm_destructive to execute after user approval.

        Required:
          pipeline_id : pipeline UUID.
        At least one of:
          new_default_branch : new branch for one code source. If the pipeline
                               has multiple sources, also pass source_alias.
          new_pre_task       : new value for definition.stages[0].pre[].task.
                               Allowed values:
                                 - "official_devcloud_manualTrigger"
                                   (require manual click to start stage 0)
                                 - "official_devcloud_autoTrigger"
                                   (start stage 0 automatically)
                               When the first stage has more than one pre-step,
                               pass pre_sequence to target a specific entry;
                               otherwise every entry is updated.

        Returns:
          {"status": "pending_approval", "approval_id": "...", "preview": {...}}

        Examples (only one of these per call):
          pipeline_update_info(pipeline_id="...", new_default_branch="release/2.0")
          pipeline_update_info(pipeline_id="...",
                               new_pre_task="official_devcloud_manualTrigger")
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = PipelineUpdateInfoInput(
            pipeline_id=pipeline_id,
            project_id=project_id,
            new_default_branch=new_default_branch,
            source_alias=source_alias,
            new_pre_task=new_pre_task,
            pre_sequence=pre_sequence,
        )

        if params.new_default_branch is None and params.new_pre_task is None:
            raise ToolError(
                code="NO_FIELDS_TO_UPDATE",
                message=(
                    "at least one of new_default_branch or new_pre_task must "
                    "be supplied — refusing to issue an empty PUT."
                ),
            )

        if (
            params.new_pre_task is not None
            and params.new_pre_task not in ALLOWED_PRE_TASK_VALUES
        ):
            raise ToolError(
                code="INVALID_PRE_TASK",
                message=(
                    f"new_pre_task must be one of {sorted(ALLOWED_PRE_TASK_VALUES)}, "
                    f"got {params.new_pre_task!r}"
                ),
            )

        pid = resolve_project_id(settings, params.project_id)
        client = get_client(settings)

        # --- Two-phase commit: compute the full diff, then store for approval ---
        # Step 1: read full current configuration.
        detail = client.show_pipeline_detail(
            ShowPipelineDetailRequest(project_id=pid, pipeline_id=params.pipeline_id)
        )

        original_definition_str = getattr(detail, "definition", None)
        original_definition_obj = parse_definition(original_definition_str)
        original_def_summary = summarise_definition(original_definition_obj)
        original_def_hash = _short_hash(original_definition_str or "")

        changes: dict = {}

        # ----- default_branch -------------------------------------------------
        chosen_index = None
        if params.new_default_branch is not None:
            chosen_index = _select_source_index(detail, params.source_alias)
            current_branch = getattr(
                getattr(detail.sources[chosen_index], "params", None),
                "default_branch", None,
            )
            changes["default_branch"] = {
                "source_index": chosen_index,
                "source_alias": getattr(
                    getattr(detail.sources[chosen_index], "params", None),
                    "alias", None,
                ),
                "before": current_branch,
                "after": params.new_default_branch,
            }

        # ----- definition.stages[0].pre[].task --------------------------------
        diffs = []
        new_definition_obj = original_definition_obj
        new_definition_str = original_definition_str
        if params.new_pre_task is not None:
            new_definition_obj = parse_definition(original_definition_str)  # fresh copy
            try:
                new_definition_obj, diffs = update_first_stage_pre_tasks(
                    new_definition_obj,
                    new_task=params.new_pre_task,
                    sequence=params.pre_sequence,
                )
            except ValueError as exc:
                raise ToolError(
                    code="DEFINITION_UPDATE_FAILED",
                    message=str(exc),
                ) from exc
            new_definition_str = dump_definition(new_definition_obj)
            changes["pre_task"] = {
                "diffs": diffs,
                "applied_to_count": len(diffs),
            }

        # ----- build the full PipelineDTO from the detail response ------------
        dto = PipelineDTO()
        # Mandatory full-record fields:
        dto.name = getattr(detail, "name", None)
        dto.is_publish = bool(getattr(detail, "is_publish", False))
        dto.manifest_version = getattr(detail, "manifest_version", None)
        dto.definition = new_definition_str

        # Optional descriptive fields the API allows on PipelineDTO:
        if getattr(detail, "description", None) is not None:
            dto.description = detail.description
        if getattr(detail, "group_id", None) is not None:
            dto.group_id = detail.group_id
        if getattr(detail, "id", None) is not None:
            dto.id = detail.id
        if getattr(detail, "security_level", None) is not None:
            dto.security_level = detail.security_level

        # Sources — full re-pack, mutate only chosen index when needed.
        new_sources = []
        for i, src in enumerate(getattr(detail, "sources", None) or []):
            cs = _to_code_source(src)
            if i == chosen_index and cs.params is not None:
                cs.params.default_branch = params.new_default_branch
            new_sources.append(cs)
        dto.sources = new_sources

        # Variables, schedules, triggers — preserve verbatim.
        if getattr(detail, "variables", None):
            dto.variables = [_to_custom_variable(v) for v in detail.variables]
        if getattr(detail, "schedules", None):
            dto.schedules = [_to_schedule(s) for s in detail.schedules]
        if getattr(detail, "triggers", None):
            dto.triggers = [_to_trigger(t) for t in detail.triggers]

        # ----- diff log (definition before/after) -----------------------------
        new_def_summary = summarise_definition(new_definition_obj)
        new_def_hash = _short_hash(new_definition_str or "")
        log.info(
            "pipeline_update_info pipeline_id=%s project_id=%s "
            "definition_hash %s -> %s; before_summary=%s after_summary=%s; "
            "changes=%s",
            params.pipeline_id, pid,
            original_def_hash, new_def_hash,
            original_def_summary, new_def_summary,
            changes,
        )

        # --- Phase 1: store the PUT for approval, return preview ---
        action_label = f"pipeline_update_info(pipeline_id={params.pipeline_id!r}, changes={changes})"

        def _execute() -> dict:
            request = UpdatePipelineInfoRequest(
                project_id=pid,
                pipeline_id=params.pipeline_id,
                body=dto,
            )
            response = client.update_pipeline_info(request)
            resp_d = response.to_dict() if hasattr(response, "to_dict") else {}
            return {
                "pipeline_id": params.pipeline_id,
                "changes": changes,
                "definition_hash_before": original_def_hash,
                "definition_hash_after": new_def_hash,
                "raw_response": resp_d,
            }

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "update_pipeline",
                "pipeline_id": params.pipeline_id,
                "changes": changes,
                "definition_hash_before": original_def_hash,
                "definition_hash_after": new_def_hash,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "update_pipeline",
            "pipeline_id": params.pipeline_id,
            "changes": changes,
            "definition_hash_before": original_def_hash,
            "definition_hash_after": new_def_hash,
            "message": (
                f"⚠ Pipeline update is destructive (full PUT). Present this "
                f"preview to the user and ask for explicit approval. If approved, "
                f"call pipeline_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    return {"pipeline_update_info": pipeline_update_info}
