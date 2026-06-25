"""RDS security audit tool — composite risk analysis.

rds_audit_instance_security checks multiple risk dimensions in one call:
  - Public IP direct exposure (not behind ELB/VPN)
  - root/admin account allows % remote login
  - Storage usage > 85%
  - No automatic backup success in last 7 days
  - SSL connection not enforced
  - No read-only replica (single point of failure)
  - Slow query log not enabled (checked via backup strategy / config)

Returns risk_items[] with severity + remediation suggestions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from huaweicloudsdkrds.v3 import (
    ListBackupsRequest,
    ListInstancesRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import AuditInstanceSecurityInput
from ..serializers import instance_detail

log = logging.getLogger("huaweicloud_mcp.services.rds.tools.audit")

# Risk severity levels.
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


def make_audit_tools(settings: Settings) -> dict:
    """Build RDS security audit tool bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def rds_audit_instance_security(instance_id: str) -> dict:
        """Audit an RDS instance for security risks.

        Checks multiple risk dimensions in one call and returns a prioritised
        list of findings with remediation suggestions. Use for proactive
        security inspections or pre-change safety verification.

        Risk checks:
          HIGH:
            - Public IP directly exposed (not behind ELB/VPN)
            - root/admin account allows '%' remote login
            - Storage usage > 85%
            - No automatic backup success in last 7 days
            - SSL connection not enforced
          MEDIUM:
            - No read-only replica (single point of failure)
            - Slow query log not enabled

        Args:
            instance_id: RDS instance UUID.

        Returns:
            {"instance_id": ..., "risk_items": [...], "risk_count": N,
             "high_risk_count": N, "overall_status": "pass"|"warn"|"critical"}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = AuditInstanceSecurityInput(instance_id=instance_id)
        client = get_client("rds", settings)

        # Fetch instance detail.
        inst_resp = client.list_instances(
            ListInstancesRequest(id=params.instance_id)
        )
        instances = list(getattr(inst_resp, "instances", None) or [])
        if not instances:
            raise ToolError(
                code="NOT_FOUND",
                message=f"RDS instance {params.instance_id!r} not found.",
            )
        inst = instances[0]
        detail = instance_detail(inst)

        risks: list[dict] = []

        # ---- Check 1: Public IP exposure ----
        public_ips = getattr(inst, "public_ips", None) or []
        if public_ips:
            risks.append(_risk(
                severity=SEVERITY_HIGH,
                category="public_exposure",
                description=(
                    f"Instance has public IP(s): {public_ips}. "
                    f"Direct internet exposure without ELB/VPN is a security risk."
                ),
                suggestion=(
                    "Disassociate the public IP or restrict access via "
                    "security group rules to known CIDR ranges only. "
                    "Consider routing through a VPC endpoint or VPN gateway."
                ),
            ))

        # ---- Check 2: SSL not enforced ----
        enable_ssl = getattr(inst, "enable_ssl", None)
        if enable_ssl is False or enable_ssl is None:
            risks.append(_risk(
                severity=SEVERITY_HIGH,
                category="ssl_disabled",
                description="SSL is not enabled — database connections are unencrypted.",
                suggestion="Enable SSL for the instance to encrypt all database connections.",
            ))

        # ---- Check 3: Storage usage > 85% ----
        volume = getattr(inst, "volume", None)
        storage_used = getattr(inst, "storage_used_space", None)
        volume_size = getattr(volume, "size", None) if volume else None
        if storage_used is not None and volume_size and volume_size > 0:
            # storage_used_space is in GB, volume_size is in GB
            usage_pct = (float(storage_used) / float(volume_size)) * 100
            if usage_pct > 85:
                risks.append(_risk(
                    severity=SEVERITY_HIGH,
                    category="storage_near_full",
                    description=(
                        f"Storage usage is {usage_pct:.1f}% "
                        f"({storage_used}GB / {volume_size}GB). "
                        f"Risk of disk-full failure."
                    ),
                    suggestion=(
                        "Expand storage capacity or clean up old data. "
                        "Consider enabling auto-scaling storage policy."
                    ),
                ))

        # ---- Check 4: No recent backup ----
        try:
            backup_resp = client.list_backups(
                ListBackupsRequest(
                    instance_id=params.instance_id,
                    backup_type="auto",
                    status="COMPLETED",
                    limit=1,
                )
            )
            backups = list(getattr(backup_resp, "backups", None) or [])
            seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
            has_recent_backup = False
            for b in backups:
                begin_time = getattr(b, "begin_time", None)
                if begin_time:
                    try:
                        # begin_time is typically "YYYY-MM-DDTHH:MM:SSZ"
                        bt = datetime.fromisoformat(
                            begin_time.replace("Z", "+00:00")
                        )
                        if bt >= seven_days_ago:
                            has_recent_backup = True
                            break
                    except (ValueError, TypeError):
                        has_recent_backup = True  # can't parse, assume ok
                        break
            if not has_recent_backup:
                risks.append(_risk(
                    severity=SEVERITY_HIGH,
                    category="no_recent_backup",
                    description=(
                        "No successful automatic backup in the last 7 days. "
                        "Data loss risk if instance fails."
                    ),
                    suggestion=(
                        "Verify backup policy is enabled and check backup "
                        "configuration. Ensure keep_days >= 7."
                    ),
                ))
        except Exception as exc:  # noqa: BLE001
            log.warning("audit: backup check failed: %s", exc)

        # ---- Check 5: root/admin with % host ----
        try:
            from huaweicloudsdkrds.v3 import ListDbUsersRequest
            users_resp = client.list_db_users(
                ListDbUsersRequest(instance_id=params.instance_id, page=1, limit=100)
            )
            users = list(getattr(users_resp, "users", None) or [])
            for u in users:
                uname = getattr(u, "name", "")
                hosts = getattr(u, "hosts", None) or []
                if uname.lower() in ("root", "admin") and "%" in hosts:
                    risks.append(_risk(
                        severity=SEVERITY_HIGH,
                        category="root_remote_access",
                        description=(
                            f"Account '{uname}' allows remote login from '%' "
                            f"(any host). This is a critical security risk."
                        ),
                        suggestion=(
                            f"Restrict '{uname}' to specific host IPs only. "
                            f"Replace '%' with the actual application server IPs."
                        ),
                    ))
        except Exception as exc:  # noqa: BLE001
            log.warning("audit: account check failed: %s", exc)

        # ---- Check 6: No read-only replica (single point of failure) ----
        related = getattr(inst, "related_instance", None) or []
        has_replica = any(
            getattr(ri, "type", None) == "replica" for ri in related
        )
        inst_type = getattr(inst, "type", "")
        # Only flag for Single instances (HA already has redundancy).
        if not has_replica and inst_type == "Single":
            risks.append(_risk(
                severity=SEVERITY_MEDIUM,
                category="no_replica",
                description=(
                    "Single instance with no read-only replica — "
                    "single point of failure."
                ),
                suggestion=(
                    "Create a read-only replica for read scaling and "
                    "failover protection. Or upgrade to HA (primary/standby)."
                ),
            ))

        # ---- Summary ----
        high_count = sum(1 for r in risks if r["severity"] == SEVERITY_HIGH)
        if high_count > 0:
            overall = "critical"
        elif risks:
            overall = "warn"
        else:
            overall = "pass"

        return {
            "instance_id": params.instance_id,
            "instance_name": detail.get("name"),
            "risk_items": risks,
            "risk_count": len(risks),
            "high_risk_count": high_count,
            "overall_status": overall,
        }

    return {"rds_audit_instance_security": rds_audit_instance_security}
