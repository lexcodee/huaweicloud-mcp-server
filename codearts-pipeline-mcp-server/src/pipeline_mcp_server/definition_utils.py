"""Safe parse / inspect / modify utilities for the ``definition`` field.

Important: ``definition`` on the CodeArts Pipeline API is a JSON-encoded
**string**, NOT an object. Always:
  1. parse it with ``parse_definition``
  2. mutate the resulting dict
  3. serialise back with ``dump_definition`` before sending to the API
"""
from __future__ import annotations

import json
from typing import Any, List, Optional, Tuple

# task is the only field this MCP server is allowed to update on a pre-step.
ALLOWED_PRE_TASK_VALUES = {
    "official_devcloud_manualTrigger",
    "official_devcloud_autoTrigger",
}


# ---------------------------------------------------------------------------
# Parse / dump
# ---------------------------------------------------------------------------

def parse_definition(definition: Any) -> dict:
    """Return a fresh dict regardless of whether the input is str or dict.

    The wire format is a JSON string; the SDK exposes it as the same string.
    Be permissive on input — some test fixtures pass a dict directly — and
    always return a dict so the caller can index uniformly.
    """
    if definition is None or definition == "":
        return {}
    if isinstance(definition, dict):
        # Defensive deep copy via JSON round-trip so mutations don't leak.
        return json.loads(json.dumps(definition))
    if isinstance(definition, str):
        try:
            obj = json.loads(definition)
        except json.JSONDecodeError as exc:
            raise ValueError(f"definition is not valid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(
                f"parsed definition has type {type(obj).__name__}, expected object"
            )
        return obj
    raise TypeError(
        f"definition must be str or dict, got {type(definition).__name__}"
    )


def dump_definition(definition_obj: dict) -> str:
    """Serialise back to the wire format. ``ensure_ascii=False`` matches what
    the CodeArts UI emits."""
    return json.dumps(definition_obj, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Targeted mutators (used by pipeline_update_info)
# ---------------------------------------------------------------------------

def update_first_stage_pre_tasks(
    definition_obj: dict,
    new_task: str,
    *,
    sequence: Optional[int] = None,
) -> Tuple[dict, List[dict]]:
    """Replace the ``task`` field on entries of ``stages[0].pre``.

    If ``sequence`` is provided, only the entry with that ``sequence`` value
    is changed; otherwise every entry in ``stages[0].pre`` is updated. Returns
    the mutated definition (same object, mutated in place) plus a list of
    diffs ``[{sequence, before, after}, ...]`` for audit logging.

    Raises ``ValueError`` when:
      * stages[0] does not exist
      * stages[0].pre is missing/empty
      * the requested sequence is not present
      * the desired task is not in ``ALLOWED_PRE_TASK_VALUES``
    """
    if new_task not in ALLOWED_PRE_TASK_VALUES:
        raise ValueError(
            f"new_pre_task must be one of {sorted(ALLOWED_PRE_TASK_VALUES)}, "
            f"got {new_task!r}"
        )

    stages = definition_obj.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("definition.stages is missing or empty")

    first_stage = stages[0]
    if not isinstance(first_stage, dict):
        raise ValueError("definition.stages[0] is not an object")

    pre = first_stage.get("pre")
    if not isinstance(pre, list) or not pre:
        raise ValueError("definition.stages[0].pre is missing or empty")

    diffs: List[dict] = []
    found_sequence = False
    for entry in pre:
        if not isinstance(entry, dict):
            continue
        if sequence is not None and entry.get("sequence") != sequence:
            continue
        if sequence is not None:
            found_sequence = True
        before = entry.get("task")
        if before == new_task:
            continue
        entry["task"] = new_task
        diffs.append({
            "sequence": entry.get("sequence"),
            "before": before,
            "after": new_task,
        })

    if sequence is not None and not found_sequence:
        raise ValueError(
            f"no pre-step with sequence={sequence} in stages[0].pre"
        )

    return definition_obj, diffs


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def summarise_definition(definition_obj: dict) -> dict:
    """Compact summary suitable for diff-style logs."""
    stages = definition_obj.get("stages") or []
    summary = {
        "stage_count": len(stages),
        "stages": [
            {
                "name": s.get("name") if isinstance(s, dict) else None,
                "pre_tasks": [
                    p.get("task")
                    for p in (s.get("pre") or [])
                    if isinstance(p, dict)
                ] if isinstance(s, dict) else [],
                "job_count": len(s.get("jobs") or []) if isinstance(s, dict) else 0,
            }
            for s in stages
        ],
    }
    return summary
