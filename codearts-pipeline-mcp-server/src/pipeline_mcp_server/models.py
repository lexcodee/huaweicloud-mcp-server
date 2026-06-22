"""Pydantic input models for every tool — re-validated inside tool bodies."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class _ProjectScopedInput(BaseModel):
    project_id: Optional[str] = Field(
        default=None,
        description=(
            "CodeArts project UUID. If omitted, the server's "
            "CODEARTS_DEFAULT_PROJECT_ID is used. Pass explicitly to operate "
            "on a different project."
        ),
    )


class _PipelineScopedInput(_ProjectScopedInput):
    pipeline_id: str = Field(..., description="Pipeline UUID.", min_length=1)


# ---------------------------------------------------------------------------
# pipeline_run
# ---------------------------------------------------------------------------

class RunVariable(BaseModel):
    name: str
    value: str


class RunSourceParams(BaseModel):
    git_type: Optional[str] = None
    default_branch: Optional[str] = Field(
        default=None,
        description="Branch to run on this invocation. Empty = use pipeline default.",
    )
    alias: Optional[str] = None
    codehub_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    git_url: Optional[str] = None
    # build_params (target_branch / commit_id / tag) supported as opaque dict
    build_params: Optional[dict] = None


class RunSource(BaseModel):
    type: Optional[str] = None
    params: Optional[RunSourceParams] = None


class PipelineRunInput(_PipelineScopedInput):
    sources: Optional[List[RunSource]] = Field(
        default=None,
        description=(
            "Optional code-source overrides. Most callers should leave this "
            "empty so the pipeline runs with its configured default branch."
        ),
    )
    variables: Optional[List[RunVariable]] = Field(
        default=None,
        description="Custom run variables [{name, value}, ...].",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional human-readable description for this run.",
        max_length=512,
    )
    choose_jobs: Optional[List[str]] = Field(
        default=None,
        description="Restrict the run to specific job ids.",
    )
    choose_stages: Optional[List[str]] = Field(
        default=None,
        description="Restrict the run to specific stage ids.",
    )


# ---------------------------------------------------------------------------
# pipeline_list
# ---------------------------------------------------------------------------

_ALLOWED_STATUS = {
    "COMPLETED", "RUNNING", "FAILED", "CANCELED",
    "PAUSED", "SUSPEND", "IGNORED",
}
_ALLOWED_SORT_KEY = {"name", "create_time", "update_time"}


class PipelineListInput(_ProjectScopedInput):
    name: Optional[str] = Field(default=None, description="Fuzzy match on pipeline name.")
    status: Optional[List[str]] = Field(
        default=None,
        description=(
            "Filter by latest_run.status. Allowed values: "
            "COMPLETED / RUNNING / FAILED / CANCELED / PAUSED / SUSPEND / IGNORED."
        ),
    )
    component_id: Optional[str] = None
    creator_id: Optional[str] = None
    creator_ids: Optional[List[str]] = None
    executor_ids: Optional[List[str]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)
    sort_key: Optional[str] = None
    sort_dir: Optional[Literal["asc", "desc"]] = None
    is_banned: Optional[bool] = Field(
        default=None,
        description="If true, include disabled pipelines in the result.",
    )

    @field_validator("status")
    @classmethod
    def _check_status(cls, v):
        if v is None:
            return v
        bad = [s for s in v if s not in _ALLOWED_STATUS]
        if bad:
            raise ValueError(
                f"unknown status values: {bad}. Allowed: {sorted(_ALLOWED_STATUS)}"
            )
        return v

    @field_validator("sort_key")
    @classmethod
    def _check_sort_key(cls, v):
        if v is None:
            return v
        if v not in _ALLOWED_SORT_KEY:
            raise ValueError(
                f"sort_key must be one of {sorted(_ALLOWED_SORT_KEY)}, got {v!r}"
            )
        return v


# ---------------------------------------------------------------------------
# pipeline_get_detail
# ---------------------------------------------------------------------------

class PipelineGetDetailInput(_PipelineScopedInput):
    pass


# ---------------------------------------------------------------------------
# pipeline_update_info
# ---------------------------------------------------------------------------

class PipelineUpdateInfoInput(_PipelineScopedInput):
    new_default_branch: Optional[str] = Field(
        default=None,
        description=(
            "New value for sources[].params.default_branch. Targets a single "
            "code source — selected via source_alias if there are multiple "
            "sources, otherwise sources[0]."
        ),
        min_length=1,
    )
    source_alias: Optional[str] = Field(
        default=None,
        description=(
            "Alias of the code source to update. Optional when the pipeline "
            "has exactly one source; required for multi-source pipelines."
        ),
    )
    new_pre_task: Optional[str] = Field(
        default=None,
        description=(
            "New value for definition.stages[0].pre[].task. Allowed values: "
            "'official_devcloud_manualTrigger' (manual first-stage trigger) "
            "or 'official_devcloud_autoTrigger' (auto first-stage trigger)."
        ),
    )
    pre_sequence: Optional[int] = Field(
        default=None,
        description=(
            "When the first stage has multiple pre-steps, restrict the change "
            "to the entry with this `sequence` value. Defaults to all entries."
        ),
        ge=0,
    )


# ---------------------------------------------------------------------------
# pipeline_set_status (replaces pipeline_enable / pipeline_disable)
# ---------------------------------------------------------------------------

class PipelineSetStatusInput(_PipelineScopedInput):
    status: Literal["enabled", "disabled"] = Field(
        ...,
        description=(
            "Target ban state. "
            "'enabled'  -> hit /unban (resumes code-event triggers and schedules; "
            "non-destructive, executes immediately). "
            "'disabled' -> hit /ban   (DESTRUCTIVE: stops automatic triggers; "
            "two-phase approval required)."
        ),
    )
