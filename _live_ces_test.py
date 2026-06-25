"""Live integration test for CES MCP tools against real Huawei Cloud.

Tests all 6 CES tools:
  1. ces_list_metrics
  2. ces_get_metric_data
  3. ces_query_alarm_rules
  4. ces_list_alarm_histories
  5. ces_query_resource_groups
  6. ces_list_event_data
"""
from __future__ import annotations

import json
import os
import sys
import traceback

# Ensure the package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "huaweicloud-mcp-server", "src"))

from huaweicloud_mcp.config import Settings, load_settings
from huaweicloud_mcp.services.ces.tools.metric import make_metric_tools
from huaweicloud_mcp.services.ces.tools.alarm import make_alarm_tools
from huaweicloud_mcp.services.ces.tools.resource_group import make_resource_group_tools
from huaweicloud_mcp.services.ces.tools.event import make_event_tools


def p(title: str, obj: dict) -> None:
    """Pretty-print a tool result."""
    ok = obj.get("ok")
    tag = "OK" if ok else "FAIL"
    print(f"\n{'='*60}")
    print(f"  {title}  [{tag}]")
    print(f"{'='*60}")
    if ok:
        data = obj.get("data", obj)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:3000])
    else:
        err = obj.get("error", {})
        print(f"  code:    {err.get('code')}")
        print(f"  message: {err.get('message')}")


def main() -> None:
    settings = load_settings()
    print(f"region={settings.region}  project_id={settings.project_id[:8]}...")

    # Build all CES tools
    metric_tools = make_metric_tools(settings)
    alarm_tools = make_alarm_tools(settings)
    rg_tools = make_resource_group_tools(settings)
    event_tools = make_event_tools(settings)

    results = {}

    # ── 1. ces_list_metrics ──────────────────────────────────────────────
    print("\n>> ces_list_metrics(namespace='SYS.ECS')")
    try:
        r = metric_tools["ces_list_metrics"](namespace="SYS.ECS", limit=10)
        p("ces_list_metrics", r)
        results["list_metrics"] = r
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["list_metrics"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # Extract an instance_id for metric data query
    instance_id = None
    if results["list_metrics"].get("ok"):
        metrics = results["list_metrics"].get("data", {}).get("metrics", [])
        for m in metrics:
            for d in m.get("dimensions", []):
                if d.get("name") == "instance_id":
                    instance_id = d["value"]
                    break
            if instance_id:
                break
    print(f"  >> discovered instance_id: {instance_id}")

    # ── 2. ces_get_metric_data ───────────────────────────────────────────
    if instance_id:
        print(f"\n>> ces_get_metric_data(cpu_util for {instance_id})")
        try:
            r = metric_tools["ces_get_metric_data"](
                metrics=[{
                    "namespace": "SYS.ECS",
                    "metric_name": "cpu_util",
                    "dimensions": f"instance_id,{instance_id}",
                }],
                from_time="-30m",
                period=300,
                filter="average",
            )
            p("ces_get_metric_data", r)
            results["get_metric_data"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["get_metric_data"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> ces_get_metric_data: SKIPPED (no instance_id found)")
        results["get_metric_data"] = {"ok": False, "error": {"code": "SKIP", "message": "no instance_id"}}

    # ── 3. ces_query_alarm_rules (LIST) ──────────────────────────────────
    print("\n>> ces_query_alarm_rules()  [list mode]")
    alarm_id = None
    try:
        r = alarm_tools["ces_query_alarm_rules"]()
        p("ces_query_alarm_rules (list)", r)
        results["query_alarm_rules_list"] = r
        if r.get("ok"):
            alarms = r.get("data", {}).get("alarms", [])
            if alarms:
                alarm_id = alarms[0].get("alarm_id")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["query_alarm_rules_list"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 3b. ces_query_alarm_rules (DETAIL) ───────────────────────────────
    if alarm_id:
        print(f"\n>> ces_query_alarm_rules(alarm_id='{alarm_id}')  [detail mode]")
        try:
            r = alarm_tools["ces_query_alarm_rules"](alarm_id=alarm_id)
            p("ces_query_alarm_rules (detail)", r)
            results["query_alarm_rules_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["query_alarm_rules_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> ces_query_alarm_rules (detail): SKIPPED (no alarm_id)")
        results["query_alarm_rules_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no alarm_id"}}

    # ── 4. ces_list_alarm_histories ──────────────────────────────────────
    print("\n>> ces_list_alarm_histories(from_time='-7d')")
    try:
        r = alarm_tools["ces_list_alarm_histories"](from_time="-7d", limit=5)
        p("ces_list_alarm_histories", r)
        results["list_alarm_histories"] = r
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["list_alarm_histories"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 5. ces_query_resource_groups (LIST) ──────────────────────────────
    print("\n>> ces_query_resource_groups()  [list mode]")
    group_id = None
    try:
        r = rg_tools["ces_query_resource_groups"]()
        p("ces_query_resource_groups (list)", r)
        results["query_resource_groups_list"] = r
        if r.get("ok"):
            groups = r.get("data", {}).get("resource_groups", [])
            if groups:
                group_id = groups[0].get("group_id")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["query_resource_groups_list"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 5b. ces_query_resource_groups (DETAIL) ───────────────────────────
    if group_id:
        print(f"\n>> ces_query_resource_groups(group_id='{group_id}')  [detail mode]")
        try:
            r = rg_tools["ces_query_resource_groups"](group_id=group_id)
            p("ces_query_resource_groups (detail)", r)
            results["query_resource_groups_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["query_resource_groups_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> ces_query_resource_groups (detail): SKIPPED (no group_id)")
        results["query_resource_groups_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no group_id"}}

    # ── 6. ces_list_event_data (LIST) ────────────────────────────────────
    print("\n>> ces_list_event_data(event_type='EVENT.SYS', from_time='-1d')")
    event_name = None
    try:
        r = event_tools["ces_list_event_data"](event_type="EVENT.SYS", from_time="-1d", limit=10)
        p("ces_list_event_data (list)", r)
        results["list_event_data_list"] = r
        if r.get("ok"):
            events = r.get("data", {}).get("events", [])
            if events:
                event_name = events[0].get("event_name")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["list_event_data_list"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 6b. ces_list_event_data (DETAIL) ─────────────────────────────────
    if event_name:
        print(f"\n>> ces_list_event_data(event_name='{event_name}')  [detail mode]")
        try:
            r = event_tools["ces_list_event_data"](event_name=event_name, from_time="-1d")
            p("ces_list_event_data (detail)", r)
            results["list_event_data_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["list_event_data_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> ces_list_event_data (detail): SKIPPED (no event_name)")
        results["list_event_data_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no event_name"}}

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    ok_count = 0
    fail_count = 0
    skip_count = 0
    for name, r in results.items():
        if r.get("ok") is True:
            status = "PASS"
            ok_count += 1
        elif r.get("error", {}).get("code") == "SKIP":
            status = "SKIP"
            skip_count += 1
        else:
            status = "FAIL"
            fail_count += 1
        print(f"  {name:40s}  {status}")
    print(f"\n  PASS={ok_count}  FAIL={fail_count}  SKIP={skip_count}  TOTAL={len(results)}")


if __name__ == "__main__":
    main()
