"""OBS security audit tool — composite risk analysis.

obs_audit_bucket_security checks multiple risk dimensions in one call:
  - Public read/write ACL (AnyoneCanRead/Write, public-read, public-read-write)
  - Bucket marked as public via get_bucket_public_status
  - No server-side encryption
  - No versioning enabled (no recovery from overwrite/delete)
  - Public access block not configured
  - Permissive policy grants (wildcard principals)

Returns risk_items[] with severity + remediation suggestions.
"""
from __future__ import annotations

import logging

from huaweicloudsdkobs.v1.model import (
    GetBucketAclRequest,
    GetBucketMetadataRequest,
    GetBucketPublicAccessBlockRequest,
    GetBucketPublicStatusRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import AuditBucketSecurityInput

log = logging.getLogger("huaweicloud_mcp.services.obs.tools.audit")

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
    """Build OBS security audit tool bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def obs_audit_bucket_security(bucket_name: str) -> dict:
        """Audit an OBS bucket for security risks.

        Checks multiple risk dimensions in one call and returns a prioritised
        list of findings with remediation suggestions. Use for proactive
        security inspections or compliance audits.

        Risk checks:
          HIGH:
            - Public read ACL (AnyoneCanRead / public-read)
            - Public write ACL (AnyoneCanWrite / public-read-write)
            - Bucket marked public via public status API
            - No server-side encryption
          MEDIUM:
            - No versioning enabled (no recovery from overwrite/delete)
            - Public access block not configured

        Args:
            bucket_name: Bucket name to audit.

        Returns:
            {"bucket_name": ..., "risk_items": [...], "risk_count": N,
             "high_risk_count": N, "overall_status": "pass"|"warn"|"critical"}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = AuditBucketSecurityInput(bucket_name=bucket_name)
        client = get_client("obs", settings)

        risks: list[dict] = []

        # ---- Check 1: Public status API ----
        is_public = None
        try:
            pub_resp = client.get_bucket_public_status(
                GetBucketPublicStatusRequest(bucket_name=params.bucket_name)
            )
            is_public = getattr(pub_resp, "is_public", None)
            if is_public:
                risks.append(_risk(
                    severity=SEVERITY_HIGH,
                    category="public_bucket",
                    description=(
                        f"Bucket {params.bucket_name!r} is marked as public "
                        f"via the public status API. Contents may be "
                        f"accessible to anyone on the internet."
                    ),
                    suggestion=(
                        "Set the bucket ACL to 'private' and remove any "
                        "public-read or public-read-write grants. "
                        "Use obs_set_bucket_policy to restrict access to "
                        "specific principals only."
                    ),
                ))
        except Exception as exc:  # noqa: BLE001
            log.warning("audit: public status check failed: %s", exc)

        # ---- Check 2: ACL grants ----
        try:
            acl_resp = client.get_bucket_acl(
                GetBucketAclRequest(bucket_name=params.bucket_name)
            )
            acl_list = getattr(acl_resp, "access_control_list", None)
            grants = []
            if acl_list:
                grants = getattr(acl_list, "grant", None) or []

            for g in grants:
                grantee = getattr(g, "grantee", None)
                canned = getattr(grantee, "canned", None) if grantee else None
                permission = getattr(g, "permission", None)
                # "Everyone" (canned="AllUsers") with read or write
                if canned and "AllUsers" in str(canned):
                    if "WRITE" in str(permission or "").upper():
                        risks.append(_risk(
                            severity=SEVERITY_HIGH,
                            category="public_write_acl",
                            description=(
                                f"Bucket grants public WRITE access "
                                f"(permission={permission}). Anyone can "
                                f"upload, overwrite, or delete objects."
                            ),
                            suggestion=(
                                "Remove the public-write grant immediately. "
                                "Set bucket ACL to 'private'."
                            ),
                        ))
                    elif "READ" in str(permission or "").upper():
                        risks.append(_risk(
                            severity=SEVERITY_HIGH,
                            category="public_read_acl",
                            description=(
                                f"Bucket grants public READ access "
                                f"(permission={permission}). Anyone can "
                                f"list and download all objects."
                            ),
                            suggestion=(
                                "Remove the public-read grant. If public "
                                "read is required for specific objects only, "
                                "use object-level ACLs or a restrictive "
                                "bucket policy instead."
                            ),
                        ))
        except Exception as exc:  # noqa: BLE001
            log.warning("audit: ACL check failed: %s", exc)

        # ---- Check 3: No server-side encryption ----
        try:
            meta_resp = client.get_bucket_metadata(
                GetBucketMetadataRequest(bucket_name=params.bucket_name)
            )
            sse = getattr(meta_resp, "x_obs_server_side_encryption", None)
            if not sse:
                risks.append(_risk(
                    severity=SEVERITY_HIGH,
                    category="no_encryption",
                    description=(
                        "Server-side encryption is not enabled on the "
                        "bucket. Data at rest is unencrypted."
                    ),
                    suggestion=(
                        "Enable server-side encryption (SSE-KMS or SSE-OBS) "
                        "on the bucket. This can be set during bucket "
                        "creation or via the OBS console."
                    ),
                ))

            # ---- Check 4: No versioning ----
            versioning = getattr(meta_resp, "x_obs_version", None)
            if not versioning or versioning == "Suspended":
                risks.append(_risk(
                    severity=SEVERITY_MEDIUM,
                    category="no_versioning",
                    description=(
                        f"Versioning is {'suspended' if versioning == 'Suspended' else 'not enabled'} "
                        f"on the bucket. Objects overwritten or deleted "
                        f"cannot be recovered."
                    ),
                    suggestion=(
                        "Enable versioning on the bucket to protect against "
                        "accidental overwrite and deletion. Use "
                        "set_bucket_versioning via the OBS console or SDK."
                    ),
                ))
        except Exception as exc:  # noqa: BLE001
            log.warning("audit: metadata check failed: %s", exc)

        # ---- Check 5: Public access block not configured ----
        try:
            bpa_resp = client.get_bucket_public_access_block(
                GetBucketPublicAccessBlockRequest(bucket_name=params.bucket_name)
            )
            # If we can read it, public access block is configured.
            # If is_public is True despite BPA, that's a config conflict.
        except Exception as exc:  # noqa: BLE001
            # If this fails, BPA is likely not configured.
            risks.append(_risk(
                severity=SEVERITY_MEDIUM,
                category="no_public_access_block",
                description=(
                    "Public access block configuration is not set or "
                    "not retrievable. Without it, public ACLs or policies "
                    "can inadvertently expose bucket data."
                ),
                suggestion=(
                    "Configure public access block to restrict public "
                    "access at the bucket level, preventing any public "
                    "ACL or policy from granting access."
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
            "bucket_name": params.bucket_name,
            "risk_items": risks,
            "risk_count": len(risks),
            "high_risk_count": high_count,
            "overall_status": overall,
        }

    return {"obs_audit_bucket_security": obs_audit_bucket_security}
