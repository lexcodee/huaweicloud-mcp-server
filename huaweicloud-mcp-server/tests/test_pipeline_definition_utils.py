"""Unit tests for definition_utils — JSON-string safe parse / mutate / dump."""
from __future__ import annotations

import json

import pytest

from huaweicloud_mcp.services.pipeline.definition_utils import (
    ALLOWED_PRE_TASK_VALUES,
    dump_definition,
    parse_definition,
    summarise_definition,
    update_first_stage_pre_tasks,
)


def test_parse_string_round_trip():
    obj = {"stages": [{"name": "s1", "pre": [{"task": "x", "sequence": 0}]}]}
    s = json.dumps(obj)
    parsed = parse_definition(s)
    assert parsed == obj
    # Mutation must not affect the source string
    parsed["stages"][0]["pre"][0]["task"] = "y"
    assert json.loads(s)["stages"][0]["pre"][0]["task"] == "x"


def test_parse_dict_returns_deep_copy():
    obj = {"stages": [{"pre": [{"task": "x", "sequence": 0}]}]}
    parsed = parse_definition(obj)
    parsed["stages"][0]["pre"][0]["task"] = "y"
    assert obj["stages"][0]["pre"][0]["task"] == "x"


def test_parse_empty_returns_empty_dict():
    assert parse_definition(None) == {}
    assert parse_definition("") == {}


def test_parse_bad_json_raises():
    with pytest.raises(ValueError):
        parse_definition("{not json}")


def test_dump_definition_is_json_loadable():
    obj = {"stages": [{"name": "s", "pre": [{"task": "t", "sequence": 0}]}]}
    s = dump_definition(obj)
    assert json.loads(s) == obj


def test_update_first_stage_pre_tasks_all_entries():
    obj = {"stages": [{"pre": [
        {"task": "official_devcloud_autoTrigger", "sequence": 0},
        {"task": "official_devcloud_autoTrigger", "sequence": 1},
    ]}]}
    obj, diffs = update_first_stage_pre_tasks(
        obj, "official_devcloud_manualTrigger",
    )
    assert all(p["task"] == "official_devcloud_manualTrigger"
               for p in obj["stages"][0]["pre"])
    assert len(diffs) == 2


def test_update_first_stage_pre_tasks_specific_sequence():
    obj = {"stages": [{"pre": [
        {"task": "official_devcloud_autoTrigger", "sequence": 0},
        {"task": "official_devcloud_autoTrigger", "sequence": 1},
    ]}]}
    obj, diffs = update_first_stage_pre_tasks(
        obj, "official_devcloud_manualTrigger", sequence=1,
    )
    assert obj["stages"][0]["pre"][0]["task"] == "official_devcloud_autoTrigger"
    assert obj["stages"][0]["pre"][1]["task"] == "official_devcloud_manualTrigger"
    assert len(diffs) == 1
    assert diffs[0]["sequence"] == 1


def test_update_pre_task_unknown_value():
    obj = {"stages": [{"pre": [{"task": "x", "sequence": 0}]}]}
    with pytest.raises(ValueError):
        update_first_stage_pre_tasks(obj, "not_allowed")


def test_update_pre_task_missing_stages():
    with pytest.raises(ValueError):
        update_first_stage_pre_tasks({}, "official_devcloud_manualTrigger")


def test_update_pre_task_missing_pre():
    with pytest.raises(ValueError):
        update_first_stage_pre_tasks(
            {"stages": [{"name": "s"}]}, "official_devcloud_manualTrigger",
        )


def test_update_pre_task_unknown_sequence():
    obj = {"stages": [{"pre": [{"task": "x", "sequence": 0}]}]}
    with pytest.raises(ValueError):
        update_first_stage_pre_tasks(
            obj, "official_devcloud_manualTrigger", sequence=999,
        )


def test_update_pre_task_no_op_when_already_set_returns_empty_diff():
    obj = {"stages": [{"pre": [
        {"task": "official_devcloud_manualTrigger", "sequence": 0},
    ]}]}
    obj, diffs = update_first_stage_pre_tasks(
        obj, "official_devcloud_manualTrigger",
    )
    assert diffs == []


def test_summarise_definition_shape():
    obj = {"stages": [
        {"name": "s1", "pre": [{"task": "official_devcloud_autoTrigger"}],
         "jobs": [{"id": "j1"}, {"id": "j2"}]},
        {"name": "s2", "pre": [], "jobs": []},
    ]}
    summary = summarise_definition(obj)
    assert summary["stage_count"] == 2
    assert summary["stages"][0]["job_count"] == 2
    assert summary["stages"][0]["pre_tasks"] == ["official_devcloud_autoTrigger"]


def test_allowed_values_are_documented():
    assert ALLOWED_PRE_TASK_VALUES == {
        "official_devcloud_manualTrigger",
        "official_devcloud_autoTrigger",
    }