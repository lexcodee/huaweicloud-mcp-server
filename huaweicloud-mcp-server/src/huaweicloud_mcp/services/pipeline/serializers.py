"""Compact serializers — convert verbose SDK responses to LLM-friendly dicts.

Two-tier pattern:
  * `pipeline_summary` for list views (the response is a page of many)
  * `pipeline_detail`  for single-record views (more fields, parsed definition)
"""
from __future__ import annotations

from typing import Any, Optional

from .definition_utils import parse_definition


def _drop_nulls(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _to_dict(obj: Any) -> Any:
    """Best-effort to_dict for SDK objects, dicts, or lists."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        try:
            return obj.to_dict()
        except Exception:  # noqa: BLE001
            pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return obj


# ---------------------------------------------------------------------------
# List-view serializer (pipeline_list)
# ---------------------------------------------------------------------------

def stage_status_summary(stage: Any) -> dict:
    s = _to_dict(stage) or {}
    return _drop_nulls({
        "name": s.get("name"),
        "status": s.get("status"),
        "category": s.get("category"),
        "start_time": s.get("start_time"),
        "end_time": s.get("end_time"),
    })


def latest_run_summary(latest_run: Any) -> Optional[dict]:
    if latest_run is None:
        return None
    lr = _to_dict(latest_run) or {}
    bp = _to_dict(lr.get("build_params")) or {}
    return _drop_nulls({
        "pipeline_run_id": lr.get("pipeline_run_id"),
        "status": lr.get("status"),
        "trigger_type": lr.get("trigger_type"),
        "executor_name": lr.get("executor_name"),
        "run_number": lr.get("run_number"),
        "start_time": lr.get("start_time"),
        "end_time": lr.get("end_time"),
        "target_branch": bp.get("target_branch"),
        "commit_id": bp.get("commit_id"),
        "stage_status_list": [
            stage_status_summary(s) for s in (lr.get("stage_status_list") or [])
        ] or None,
        "detail_url": lr.get("detail_url"),
    })


def pipeline_summary(p: Any) -> dict:
    d = _to_dict(p) or {}
    return _drop_nulls({
        "pipeline_id": d.get("pipeline_id") or d.get("id"),
        "name": d.get("name"),
        "is_publish": d.get("is_publish"),
        "is_collect": d.get("is_collect"),
        "manifest_version": d.get("manifest_version"),
        "create_time": d.get("create_time"),
        "latest_run": latest_run_summary(d.get("latest_run")),
    })


def pipeline_list_response(resp: Any) -> dict:
    r = _to_dict(resp) or {}
    return {
        "offset": r.get("offset"),
        "limit": r.get("limit"),
        "total": r.get("total"),
        "pipelines": [pipeline_summary(p) for p in (r.get("pipelines") or [])],
    }


# ---------------------------------------------------------------------------
# Detail-view serializer (pipeline_get_detail)
# ---------------------------------------------------------------------------

def code_source_summary(src: Any) -> dict:
    s = _to_dict(src) or {}
    params = _to_dict(s.get("params")) or {}
    return _drop_nulls({
        "type": s.get("type"),
        "params": _drop_nulls({
            "git_type": params.get("git_type"),
            "alias": params.get("alias"),
            "default_branch": params.get("default_branch"),
            "git_url": params.get("git_url"),
            "ssh_git_url": params.get("ssh_git_url"),
            "web_url": params.get("web_url"),
            "repo_name": params.get("repo_name"),
            "codehub_id": params.get("codehub_id"),
            "endpoint_id": params.get("endpoint_id"),
        }),
    })


def variable_summary(v: Any) -> dict:
    d = _to_dict(v) or {}
    return _drop_nulls({
        "name": d.get("name"),
        "type": d.get("type"),
        "value": d.get("value"),
        "is_secret": d.get("is_secret"),
        "is_runtime": d.get("is_runtime"),
        "description": d.get("description"),
    })


def schedule_summary(s: Any) -> dict:
    d = _to_dict(s) or {}
    return _drop_nulls({
        "uuid": d.get("uuid"),
        "name": d.get("name"),
        "type": d.get("type"),
        "enable": d.get("enable"),
        "days_of_week": d.get("days_of_week"),
        "time_zone": d.get("time_zone"),
        "execution_time": d.get("execution_time"),
    })


def trigger_summary(t: Any) -> dict:
    d = _to_dict(t) or {}
    return _drop_nulls({
        "git_type": d.get("git_type"),
        "git_url": d.get("git_url"),
        "events": d.get("events"),
        "is_auto_commit": d.get("is_auto_commit"),
        "endpoint_id": d.get("endpoint_id"),
        "callback_url": d.get("callback_url"),
        "hook_id": d.get("hook_id"),
    })


def pipeline_detail(resp: Any) -> dict:
    """Return a compact detail dict and parse `definition` to an object."""
    r = _to_dict(resp) or {}
    raw_def = r.get("definition")

    parsed_def: Any = None
    parse_error: Optional[str] = None
    try:
        parsed_def = parse_definition(raw_def)
    except Exception as exc:  # noqa: BLE001
        parse_error = str(exc)

    out = {
        "id": r.get("id"),
        "name": r.get("name"),
        "description": r.get("description"),
        "is_publish": r.get("is_publish"),
        "manifest_version": r.get("manifest_version"),
        "create_time": r.get("create_time"),
        "update_time": r.get("update_time"),
        "creator_id": r.get("creator_id"),
        "creator_name": r.get("creator_name"),
        "group_id": r.get("group_id"),
        "project_id": r.get("project_id"),
        "component_id": r.get("component_id"),
        "sources": [code_source_summary(s) for s in (r.get("sources") or [])] or None,
        "variables": [variable_summary(v) for v in (r.get("variables") or [])] or None,
        "schedules": [schedule_summary(s) for s in (r.get("schedules") or [])] or None,
        "triggers": [trigger_summary(t) for t in (r.get("triggers") or [])] or None,
        # The decoded definition object — note: raw string is intentionally
        # not echoed back, the LLM would only choke on the escaping.
        "definition": parsed_def,
    }
    if parse_error:
        out["definition_parse_error"] = parse_error

    return _drop_nulls(out)