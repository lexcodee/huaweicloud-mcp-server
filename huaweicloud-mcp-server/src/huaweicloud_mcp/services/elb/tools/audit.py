"""ELB health audit tool — composite risk analysis.

elb_audit_health checks multiple risk dimensions across load balancers:
  - Certificate nearing expiry (within cert_expiry_days)
  - All backend members in a pool are OFFLINE/NO_MONITOR
  - Listener has no default backend group
  - Cross-AZ imbalance (all members in one AZ when LB spans multiple AZs)

Returns risk_items[] with severity + remediation suggestions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from huaweicloudsdkelb.v3 import (
    ListCertificatesRequest,
    ListListenersRequest,
    ListLoadBalancersRequest,
    ListMembersRequest,
    ListPoolsRequest,
    ShowLoadBalancerStatusRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import wrap_tool
from ..models import AuditHealthInput
from ..serializers import load_balancer_summary

log = logging.getLogger("huaweicloud_mcp.services.elb.tools.audit")

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


def _risk(severity: str, category: str, description: str, suggestion: str) -> dict:
    return {
        "severity": severity,
        "category": category,
        "description": description,
        "suggestion": suggestion,
    }


def _parse_expire_time(expire_time: str | None) -> datetime | None:
    """Parse certificate expire_time into a timezone-aware datetime."""
    if not expire_time:
        return None
    # Common formats: "2025-12-31T23:59:59Z" or "2025-12-31 23:59:59"
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            dt = datetime.strptime(expire_time, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try fromisoformat as fallback.
    try:
        return datetime.fromisoformat(expire_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def make_audit_tools(settings: Settings) -> dict:
    """Build ELB health audit tool bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def elb_audit_health(
        loadbalancer_id: Optional[str] = None,
        cert_expiry_days: int = 30,
    ) -> dict:
        """Audit ELB load balancers for health and configuration risks.

        Checks multiple risk dimensions in one call and returns a prioritised
        list of findings with remediation suggestions. Use for proactive
        health inspections or periodic AI-driven patrols.

        Risk checks:
          HIGH:
            - Certificate expiring within cert_expiry_days
            - All backend members OFFLINE/NO_MONITOR in a pool
            - Listener has no default backend group
          MEDIUM:
            - Cross-AZ imbalance (all members in single AZ)
            - Pool has no health monitor configured

        Args:
            loadbalancer_id: Audit a single LB. If None, audits ALL LBs.
            cert_expiry_days: Warn when certs expire within this many days.

        Returns:
            {"loadbalancers_audited": N, "risk_items": [...],
             "risk_count": N, "high_risk_count": N,
             "overall_status": "pass"|"warn"|"critical"}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = AuditHealthInput(
            loadbalancer_id=loadbalancer_id,
            cert_expiry_days=cert_expiry_days,
        )
        client = get_client("elb", settings)

        # Fetch load balancers.
        if params.loadbalancer_id:
            from huaweicloudsdkelb.v3 import ShowLoadBalancerRequest
            lb_resp = client.show_load_balancer(
                ShowLoadBalancerRequest(loadbalancer_id=params.loadbalancer_id)
            )
            lbs = [getattr(lb_resp, "loadbalancer", None)]
            lbs = [lb for lb in lbs if lb is not None]
        else:
            lb_resp = client.list_load_balancers(ListLoadBalancersRequest())
            lbs = list(getattr(lb_resp, "loadbalancers", None) or [])

        risks: list[dict] = []
        lb_ids = [getattr(lb, "id", None) for lb in lbs]

        # ---- Check 1: Certificate expiry ----
        try:
            cert_resp = client.list_certificates(ListCertificatesRequest())
            certs = list(getattr(cert_resp, "certificates", None) or [])
            now = datetime.now(timezone.utc)
            expiry_threshold = now + timedelta(days=params.cert_expiry_days)
            for cert in certs:
                expire_time = getattr(cert, "expire_time", None)
                expiry = _parse_expire_time(expire_time)
                if expiry is None:
                    continue
                if expiry <= now:
                    risks.append(_risk(
                        severity=SEVERITY_HIGH,
                        category="cert_expired",
                        description=(
                            f"Certificate '{getattr(cert, 'name', '?')}' "
                            f"(id={getattr(cert, 'id', '?')}) has EXPIRED "
                            f"on {expire_time}."
                        ),
                        suggestion=(
                            "Replace the expired certificate immediately and "
                            "update all listeners bound to it via "
                            "elb_manage_listener(action='replace_certificate')."
                        ),
                    ))
                elif expiry <= expiry_threshold:
                    days_left = (expiry - now).days
                    risks.append(_risk(
                        severity=SEVERITY_HIGH,
                        category="cert_expiring",
                        description=(
                            f"Certificate '{getattr(cert, 'name', '?')}' "
                            f"(id={getattr(cert, 'id', '?')}) expires in "
                            f"{days_left} days ({expire_time})."
                        ),
                        suggestion=(
                            f"Renew and replace this certificate before it expires. "
                            f"Use elb_manage_listener(action='replace_certificate') "
                            f"to update listeners bound to it."
                        ),
                    ))
        except Exception as exc:  # noqa: BLE001
            log.warning("audit: certificate check failed: %s", exc)

        # ---- Per-LB checks ----
        for lb in lbs:
            lb_id = getattr(lb, "id", None)
            lb_name = getattr(lb, "name", "?")
            lb_azs = getattr(lb, "availability_zone_list", None) or []

            # ---- Check 2: Listener without default pool ----
            try:
                lis_resp = client.list_listeners(
                    ListListenersRequest(loadbalancer_id=lb_id)
                )
                listeners = list(getattr(lis_resp, "listeners", None) or [])
                for lis in listeners:
                    default_pool_id = getattr(lis, "default_pool_id", None)
                    if not default_pool_id:
                        risks.append(_risk(
                            severity=SEVERITY_HIGH,
                            category="listener_no_pool",
                            description=(
                                f"Listener '{getattr(lis, 'name', '?')}' "
                                f"(id={getattr(lis, 'id', '?')}) on LB "
                                f"'{lb_name}' has no default backend group. "
                                f"Traffic will be dropped."
                            ),
                            suggestion=(
                                "Associate a backend server group with this "
                                "listener via elb_manage_listener(action='update', "
                                "default_pool_id=...)."
                            ),
                        ))
            except Exception as exc:  # noqa: BLE001
                log.warning("audit: listener check failed for LB %s: %s", lb_id, exc)

            # ---- Check 3 & 4: Pool health + member status ----
            try:
                pool_resp = client.list_pools(
                    ListPoolsRequest(loadbalancer_id=lb_id)
                )
                pools = list(getattr(pool_resp, "pools", None) or [])

                # Fetch LB status for member health.
                member_health: dict[str, str] = {}
                try:
                    status_resp = client.show_load_balancer_status(
                        ShowLoadBalancerStatusRequest(loadbalancer_id=lb_id)
                    )
                    statuses = getattr(status_resp, "statuses", None)
                    if statuses:
                        status_lb = getattr(statuses, "loadbalancer", None)
                        if status_lb:
                            for sp in (getattr(status_lb, "pools", None) or []):
                                for sm in (getattr(sp, "members", None) or []):
                                    mid = getattr(sm, "id", None)
                                    if mid:
                                        member_health[mid] = getattr(
                                            sm, "operating_status", None
                                        )
                except Exception as exc:  # noqa: BLE001
                    log.warning("audit: status fetch failed for LB %s: %s", lb_id, exc)

                for pool in pools:
                    pool_id = getattr(pool, "id", None)
                    pool_name = getattr(pool, "name", "?")
                    hm_id = getattr(pool, "healthmonitor_id", None)

                    # Check 4: No health monitor.
                    if not hm_id:
                        risks.append(_risk(
                            severity=SEVERITY_MEDIUM,
                            category="no_health_monitor",
                            description=(
                                f"Pool '{pool_name}' (id={pool_id}) on LB "
                                f"'{lb_name}' has no health monitor configured. "
                                f"Unhealthy backends will still receive traffic."
                            ),
                            suggestion=(
                                "Create a health monitor for this pool to enable "
                                "automatic health-based traffic routing."
                            ),
                        ))

                    # Fetch members for this pool.
                    members = []
                    try:
                        m_resp = client.list_members(
                            ListMembersRequest(pool_id=pool_id)
                        )
                        members = list(getattr(m_resp, "members", None) or [])
                    except Exception as exc:  # noqa: BLE001
                        log.warning("audit: member list failed for pool %s: %s", pool_id, exc)

                    if not members:
                        continue

                    # Check 3: All members offline.
                    all_down = True
                    member_azs: set[str] = set()
                    for m in members:
                        mid = getattr(m, "id", None)
                        health = member_health.get(mid) or getattr(m, "operating_status", None)
                        if health and health.upper() not in ("OFFLINE", "NO_MONITOR", "DELETED", "ERROR"):
                            all_down = False
                        az = getattr(m, "availability_zone", None)
                        if az:
                            member_azs.add(az)

                    if all_down:
                        risks.append(_risk(
                            severity=SEVERITY_HIGH,
                            category="all_backends_down",
                            description=(
                                f"All {len(members)} backend members in pool "
                                f"'{pool_name}' (id={pool_id}) on LB '{lb_name}' "
                                f"are OFFLINE/NO_MONITOR. This pool is not "
                                f"serving any traffic."
                            ),
                            suggestion=(
                                "Check backend server health, security group "
                                "rules, and network connectivity. Use "
                                "elb_list_backend_members for details."
                            ),
                        ))

                    # Check 5: Cross-AZ imbalance.
                    if (
                        len(lb_azs) > 1
                        and len(member_azs) == 1
                        and len(members) > 1
                    ):
                        risks.append(_risk(
                            severity=SEVERITY_MEDIUM,
                            category="cross_az_imbalance",
                            description=(
                                f"LB '{lb_name}' spans AZs {lb_azs} but all "
                                f"{len(members)} members in pool '{pool_name}' "
                                f"are in AZ {member_azs}. No cross-AZ "
                                f"redundancy for this pool."
                            ),
                            suggestion=(
                                "Distribute backend members across availability "
                                "zones for fault tolerance."
                            ),
                        ))
            except Exception as exc:  # noqa: BLE001
                log.warning("audit: pool check failed for LB %s: %s", lb_id, exc)

        # ---- Summary ----
        high_count = sum(1 for r in risks if r["severity"] == SEVERITY_HIGH)
        if high_count > 0:
            overall = "critical"
        elif risks:
            overall = "warn"
        else:
            overall = "pass"

        return {
            "loadbalancers_audited": len(lbs),
            "load_balancer_ids": lb_ids,
            "risk_items": risks,
            "risk_count": len(risks),
            "high_risk_count": high_count,
            "overall_status": overall,
        }

    return {"elb_audit_health": elb_audit_health}
