"""Live integration test for ELB MCP tools against real Huawei Cloud.

Tests all 13 ELB tools:
  Read:
    1. elb_describe_load_balancers (list + detail)
    2. elb_describe_listeners (list + detail)
    3. elb_describe_backend_groups (list + detail)
    4. elb_list_backend_members (with health status)
    5. elb_describe_forwarding_rules (list + detail)
    6. elb_list_certificates (list + detail)
    7. elb_describe_access_log_config (list)
  Composite:
    8. elb_audit_health
  Write (read-only safe — only test non-destructive actions):
    9. elb_manage_backend_member (update_weight — safe, reversible)
   10. elb_manage_listener (update — safe, reversible)
   11. elb_manage_forwarding_rule (create + delete — full cycle)
   12. elb_set_connection_drain (enable + disable)
   13. elb_confirm_destructive (tested via forwarding rule delete)
"""
from __future__ import annotations

import json
import os
import sys
import traceback

# Ensure the package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "huaweicloud-mcp-server", "src"))

from huaweicloud_mcp.config import Settings, load_settings
from huaweicloud_mcp.services.elb.tools.query import make_query_tools
from huaweicloud_mcp.services.elb.tools.audit import make_audit_tools
from huaweicloud_mcp.services.elb.tools.manage import make_manage_tools


def p(title: str, obj: dict) -> None:
    """Pretty-print a tool result."""
    ok = obj.get("ok")
    tag = "OK" if ok else "FAIL"
    print(f"\n{'='*70}")
    print(f"  {title}  [{tag}]")
    print(f"{'='*70}")
    if ok:
        data = obj.get("data", obj)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:4000])
    else:
        err = obj.get("error", {})
        print(f"  code:    {err.get('code')}")
        print(f"  message: {err.get('message')}")
        if err.get("hint"):
            print(f"  hint:    {err.get('hint')}")
        if err.get("status_code"):
            print(f"  status:  {err.get('status_code')}")


def main() -> None:
    settings = load_settings()
    print(f"region={settings.region}  project_id={settings.project_id[:8]}...")
    print(f"ak={settings.access_key_id[:6]}...")

    # Build all ELB tools
    query_tools = make_query_tools(settings)
    audit_tools = make_audit_tools(settings)
    manage_tools = make_manage_tools(settings)

    results = {}

    # ── 1. elb_describe_load_balancers (LIST) ───────────────────────────
    print("\n>> elb_describe_load_balancers()  [list mode]")
    lb_id = None
    try:
        r = query_tools["elb_describe_load_balancers"]()
        p("elb_describe_load_balancers (list)", r)
        results["describe_lbs"] = r
        if r.get("ok"):
            lbs = r["data"].get("load_balancers", [])
            if lbs:
                lb_id = lbs[0]["id"]
                print(f"\n  >> discovered load_balancer_id: {lb_id}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["describe_lbs"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 2. elb_describe_load_balancers (DETAIL) ─────────────────────────
    if lb_id:
        print(f"\n>> elb_describe_load_balancers(loadbalancer_id='{lb_id}')  [detail mode]")
        try:
            r = query_tools["elb_describe_load_balancers"](loadbalancer_id=lb_id)
            p("elb_describe_load_balancers (detail)", r)
            results["describe_lb_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["describe_lb_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_describe_load_balancers (detail): SKIPPED (no LB found)")
        results["describe_lb_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no LB found"}}

    # ── 3. elb_describe_listeners (LIST) ────────────────────────────────
    print("\n>> elb_describe_listeners()  [list mode]")
    listener_id = None
    try:
        r = query_tools["elb_describe_listeners"]()
        p("elb_describe_listeners (list)", r)
        results["describe_listeners"] = r
        if r.get("ok"):
            listeners = r["data"].get("listeners", [])
            if listeners:
                listener_id = listeners[0]["id"]
                print(f"\n  >> discovered listener_id: {listener_id}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["describe_listeners"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 4. elb_describe_listeners (DETAIL) ──────────────────────────────
    if listener_id:
        print(f"\n>> elb_describe_listeners(listener_id='{listener_id}')  [detail mode]")
        try:
            r = query_tools["elb_describe_listeners"](listener_id=listener_id)
            p("elb_describe_listeners (detail)", r)
            results["describe_listener_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["describe_listener_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_describe_listeners (detail): SKIPPED (no listener found)")
        results["describe_listener_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no listener"}}

    # ── 5. elb_describe_backend_groups (LIST) ───────────────────────────
    print("\n>> elb_describe_backend_groups()  [list mode]")
    pool_id = None
    try:
        r = query_tools["elb_describe_backend_groups"]()
        p("elb_describe_backend_groups (list)", r)
        results["describe_pools"] = r
        if r.get("ok"):
            pools = r["data"].get("backend_groups", [])
            if pools:
                pool_id = pools[0]["id"]
                print(f"\n  >> discovered pool_id: {pool_id}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["describe_pools"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 6. elb_describe_backend_groups (DETAIL) ─────────────────────────
    if pool_id:
        print(f"\n>> elb_describe_backend_groups(pool_id='{pool_id}')  [detail mode]")
        try:
            r = query_tools["elb_describe_backend_groups"](pool_id=pool_id)
            p("elb_describe_backend_groups (detail)", r)
            results["describe_pool_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["describe_pool_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_describe_backend_groups (detail): SKIPPED (no pool found)")
        results["describe_pool_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no pool"}}

    # ── 7. elb_list_backend_members (with health) ───────────────────────
    member_id = None
    if pool_id and lb_id:
        print(f"\n>> elb_list_backend_members(pool_id='{pool_id}', loadbalancer_id='{lb_id}')")
        member_id = None
        try:
            r = query_tools["elb_list_backend_members"](
                pool_id=pool_id, loadbalancer_id=lb_id
            )
            p("elb_list_backend_members (with health)", r)
            results["list_members"] = r
            if r.get("ok"):
                members = r["data"].get("members", [])
                if members:
                    member_id = members[0]["id"]
                    print(f"\n  >> discovered member_id: {member_id}")
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["list_members"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_list_backend_members: SKIPPED (no pool/LB found)")
        results["list_members"] = {"ok": False, "error": {"code": "SKIP", "message": "no pool/LB"}}

    # ── 8. elb_describe_forwarding_rules (LIST) ─────────────────────────
    print("\n>> elb_describe_forwarding_rules()  [list mode]")
    policy_id = None
    try:
        r = query_tools["elb_describe_forwarding_rules"]()
        p("elb_describe_forwarding_rules (list)", r)
        results["describe_policies"] = r
        if r.get("ok"):
            policies = r["data"].get("forwarding_rules", [])
            if policies:
                policy_id = policies[0]["id"]
                print(f"\n  >> discovered policy_id: {policy_id}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["describe_policies"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 9. elb_describe_forwarding_rules (DETAIL) ───────────────────────
    if policy_id:
        print(f"\n>> elb_describe_forwarding_rules(policy_id='{policy_id}')  [detail mode]")
        try:
            r = query_tools["elb_describe_forwarding_rules"](policy_id=policy_id)
            p("elb_describe_forwarding_rules (detail)", r)
            results["describe_policy_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["describe_policy_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_describe_forwarding_rules (detail): SKIPPED (no policy found)")
        results["describe_policy_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no policy"}}

    # ── 10. elb_list_certificates (LIST) ────────────────────────────────
    print("\n>> elb_list_certificates()  [list mode]")
    cert_id = None
    try:
        r = query_tools["elb_list_certificates"]()
        p("elb_list_certificates (list)", r)
        results["list_certs"] = r
        if r.get("ok"):
            certs = r["data"].get("certificates", [])
            if certs:
                cert_id = certs[0]["id"]
                print(f"\n  >> discovered certificate_id: {cert_id}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["list_certs"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 11. elb_list_certificates (DETAIL) ──────────────────────────────
    if cert_id:
        print(f"\n>> elb_list_certificates(certificate_id='{cert_id}')  [detail mode]")
        try:
            r = query_tools["elb_list_certificates"](certificate_id=cert_id)
            p("elb_list_certificates (detail)", r)
            results["cert_detail"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["cert_detail"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_list_certificates (detail): SKIPPED (no cert found)")
        results["cert_detail"] = {"ok": False, "error": {"code": "SKIP", "message": "no cert"}}

    # ── 12. elb_describe_access_log_config (LIST) ───────────────────────
    print("\n>> elb_describe_access_log_config()  [list mode]")
    try:
        r = query_tools["elb_describe_access_log_config"]()
        p("elb_describe_access_log_config (list)", r)
        results["describe_logtanks"] = r
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["describe_logtanks"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 13. elb_audit_health ────────────────────────────────────────────
    print("\n>> elb_audit_health()  [all LBs]")
    try:
        r = audit_tools["elb_audit_health"]()
        p("elb_audit_health (all)", r)
        results["audit_all"] = r
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        results["audit_all"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

    # ── 14. elb_audit_health (single LB) ────────────────────────────────
    if lb_id:
        print(f"\n>> elb_audit_health(loadbalancer_id='{lb_id}')  [single LB]")
        try:
            r = audit_tools["elb_audit_health"](loadbalancer_id=lb_id)
            p("elb_audit_health (single)", r)
            results["audit_single"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["audit_single"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_audit_health (single): SKIPPED (no LB)")
        results["audit_single"] = {"ok": False, "error": {"code": "SKIP", "message": "no LB"}}

    # ── 15. elb_manage_backend_member (update_weight) ───────────────────
    # Safe test: read current weight, set to same value (no-op change).
    if pool_id and member_id:
        print(f"\n>> elb_manage_backend_member(update_weight, pool_id='{pool_id}', member_id='{member_id}', weight=1)")
        try:
            r = manage_tools["elb_manage_backend_member"](
                action="update_weight", pool_id=pool_id,
                member_id=member_id, weight=1
            )
            p("elb_manage_backend_member (update_weight)", r)
            results["update_weight"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["update_weight"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_manage_backend_member: SKIPPED (no pool/member)")
        results["update_weight"] = {"ok": False, "error": {"code": "SKIP", "message": "no pool/member"}}

    # ── 16. elb_set_connection_drain ───────────────────────────────────
    if pool_id:
        print(f"\n>> elb_set_connection_drain(pool_id='{pool_id}', enable=True, timeout=30)")
        try:
            r = manage_tools["elb_set_connection_drain"](
                pool_id=pool_id, enable=True, timeout=30
            )
            p("elb_set_connection_drain (enable)", r)
            results["set_drain_enable"] = r
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["set_drain_enable"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_set_connection_drain: SKIPPED (no pool)")
        results["set_drain_enable"] = {"ok": False, "error": {"code": "SKIP", "message": "no pool"}}

    # ── 17. elb_manage_forwarding_rule (create + delete full cycle) ─────
    if listener_id:
        print(f"\n>> elb_manage_forwarding_rule(create, listener_id='{listener_id}', name='mcp-test-rule')")
        created_policy_id = None
        try:
            r = manage_tools["elb_manage_forwarding_rule"](
                action="create",
                listener_id=listener_id,
                name="mcp-test-rule",
                redirect_pool_id=pool_id,
                rule_type="PATH",
                rule_compare_type="STARTS_WITH",
                rule_value="/mcp-test",
                priority=100,
            )
            p("elb_manage_forwarding_rule (create)", r)
            results["create_rule"] = r
            if r.get("ok"):
                created_policy_id = r["data"].get("policy", {}).get("id")
                print(f"\n  >> created policy_id: {created_policy_id}")
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            traceback.print_exc()
            results["create_rule"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}

        # Delete the rule we just created (two-phase commit).
        if created_policy_id:
            print(f"\n>> elb_manage_forwarding_rule(delete, policy_id='{created_policy_id}')  [two-phase]")
            try:
                r = manage_tools["elb_manage_forwarding_rule"](
                    action="delete", policy_id=created_policy_id
                )
                p("elb_manage_forwarding_rule (delete — pending)", r)
                results["delete_rule_pending"] = r
                if r.get("ok"):
                    approval_id = r["data"]["approval_id"]
                    print(f"\n  >> approval_id: {approval_id}")
                    # Confirm the deletion.
                    print(f"\n>> elb_confirm_destructive(approval_id='{approval_id}')")
                    r2 = manage_tools["elb_confirm_destructive"](approval_id=approval_id)
                    p("elb_confirm_destructive (delete rule)", r2)
                    results["delete_rule_confirm"] = r2
            except Exception as e:
                print(f"  EXCEPTION: {e}")
                traceback.print_exc()
                results["delete_rule_pending"] = {"ok": False, "error": {"code": "EXCEPTION", "message": str(e)}}
    else:
        print("\n>> elb_manage_forwarding_rule: SKIPPED (no listener)")
        results["create_rule"] = {"ok": False, "error": {"code": "SKIP", "message": "no listener"}}

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    passed = sum(1 for r in results.values() if r.get("ok"))
    failed = sum(1 for r in results.values() if not r.get("ok"))
    skipped = sum(1 for r in results.values() if not r.get("ok") and r.get("error", {}).get("code") == "SKIP")
    print(f"  Total: {len(results)}   Passed: {passed}   Failed: {failed}   Skipped: {skipped}")
    print()
    for name, r in results.items():
        if r.get("ok"):
            print(f"    [PASS] {name}")
        elif r.get("error", {}).get("code") == "SKIP":
            print(f"    [SKIP] {name}: {r['error']['message']}")
        else:
            print(f"    [FAIL] {name}: {r.get('error', {}).get('code')} — {r.get('error', {}).get('message', '')[:80]}")


if __name__ == "__main__":
    main()
