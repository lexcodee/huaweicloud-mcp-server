"""OBS management tools — upload, delete, create bucket, set policy.

delete_object and set_bucket_policy are DESTRUCTIVE and use two-phase commit:
  Phase 1: call → returns preview + approval_id (no execution)
  Phase 2: user approves → call obs_confirm_destructive(approval_id)
"""
from __future__ import annotations

import io
import logging
from typing import Optional

from huaweicloudsdkobs.v1.model import (
    CreateBucketRequest,
    CreateBucketRequestBody,
    DeleteObjectRequest,
    PutObjectRequest,
    SetBucketPolicyRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, pending_actions, wrap_tool
from ..models import (
    ConfirmDestructiveInput,
    CreateBucketInput,
    DeleteObjectInput,
    SetBucketPolicyInput,
    UploadObjectInput,
)

log = logging.getLogger("huaweicloud_mcp.services.obs.tools.manage")


class _BinaryStream(io.BytesIO):
    """BytesIO with mode attribute — required by OBS SDK's ensure_file_in_rb_mode."""

    @property
    def mode(self) -> str:
        return "rb"


def make_manage_tools(settings: Settings) -> dict:
    """Build OBS management tools bound to *settings*."""
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # upload_object
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_upload_object(
        bucket_name: str,
        object_key: str,
        content: str,
        content_type: Optional[str] = None,
        storage_class: Optional[str] = None,
    ) -> dict:
        """Upload text/small file content to an OBS bucket.

        Suitable for configuration files, JSON reports, CI artifacts.
        For large or binary files, use obs_generate_presigned_url(method='PUT')
        to get an upload URL instead.

        Args:
            bucket_name: Bucket name.
            object_key: Destination object key (path).
            content: Text content to upload (UTF-8).
            content_type: Content-Type header (e.g. 'application/json').
            storage_class: 'STANDARD', 'WARM', or 'COLD'.

        Returns:
            {"bucket": ..., "key": ..., "etag": "...", "size": N}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = UploadObjectInput(
            bucket_name=bucket_name,
            object_key=object_key,
            content=content,
            content_type=content_type,
            storage_class=storage_class,
        )
        client = get_client("obs", settings)

        stream = _BinaryStream(params.content.encode("utf-8"))
        req = PutObjectRequest(
            bucket_name=params.bucket_name,
            object_key=params.object_key,
            stream=stream,
            x_obs_storage_class=params.storage_class,
        )

        resp = client.put_object(req)
        return {
            "bucket": params.bucket_name,
            "key": params.object_key,
            "etag": getattr(resp, "e_tag", None),
            "size": len(params.content.encode("utf-8")),
            "version_id": getattr(resp, "x_obs_version_id", None),
        }

    # ------------------------------------------------------------------ #
    # delete_object (two-phase)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_delete_object(
        bucket_name: str,
        object_key: str,
        version_id: Optional[str] = None,
    ) -> dict:
        """⚠ Delete an OBS object — TWO-PHASE operation.

        Returns a preview + approval_id. Use obs_confirm_destructive to
        execute after user approval. Deletion is irreversible (unless
        versioning is enabled and a specific version_id is provided).

        Args:
            bucket_name: Bucket name.
            object_key: Object key to delete.
            version_id: Specific version to delete (versioning enabled).

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = DeleteObjectInput(
            bucket_name=bucket_name,
            object_key=object_key,
            version_id=version_id,
        )
        client = get_client("obs", settings)

        action_label = (
            f"obs_delete_object(bucket_name={params.bucket_name}, "
            f"object_key={params.object_key}, version_id={params.version_id})"
        )

        def _execute() -> dict:
            req = DeleteObjectRequest(
                bucket_name=params.bucket_name,
                object_key=params.object_key,
                version_id=params.version_id,
            )
            resp = client.delete_object(req)
            return {
                "deleted": True,
                "bucket": params.bucket_name,
                "key": params.object_key,
                "version_id": getattr(resp, "x_obs_version_id", None),
                "delete_marker": getattr(resp, "x_obs_delete_marker", None),
            }

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "delete_object",
                "bucket_name": params.bucket_name,
                "object_key": params.object_key,
                "version_id": params.version_id,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "delete_object",
            "bucket_name": params.bucket_name,
            "object_key": params.object_key,
            "version_id": params.version_id,
            "message": (
                f"Object deletion is ready to submit. Present this preview to "
                f"the user and ask for explicit approval. If approved, call "
                f"obs_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    # ------------------------------------------------------------------ #
    # create_bucket
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_create_bucket(
        bucket_name: str,
        location: Optional[str] = None,
        storage_class: Optional[str] = None,
        acl: str = "private",
    ) -> dict:
        """Create a new OBS bucket.

        Defaults to private ACL (no public access). The bucket name must
        be globally unique across all of Huawei Cloud OBS.

        Args:
            bucket_name: Globally unique bucket name (3..63 chars).
            location: Region for the bucket. Defaults to server region.
            storage_class: Default storage class ('STANDARD', 'WARM', 'COLD').
            acl: Bucket ACL — 'private' (default), 'public-read',
                 'public-read-write'. Non-private is a security risk.

        Returns:
            {"created": True, "bucket": ..., "location": ..., "acl": ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = CreateBucketInput(
            bucket_name=bucket_name,
            location=location,
            storage_class=storage_class,
            acl=acl,
        )
        client = get_client("obs", settings)

        if params.acl != "private":
            log.warning(
                "create_bucket with non-private ACL: %s — security risk",
                params.acl,
            )

        req = CreateBucketRequest(
            bucket_name=params.bucket_name,
            x_obs_acl=params.acl,
            x_obs_storage_class=params.storage_class,
            body=CreateBucketRequestBody(
                location=params.location or settings.region,
            ),
        )
        client.create_bucket(req)
        return {
            "created": True,
            "bucket": params.bucket_name,
            "location": params.location or settings.region,
            "acl": params.acl,
            "storage_class": params.storage_class or "STANDARD",
        }

    # ------------------------------------------------------------------ #
    # set_bucket_policy (two-phase)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_set_bucket_policy(
        bucket_name: str,
        policy: str,
    ) -> dict:
        """⚠ Set/update bucket policy — TWO-PHASE operation.

        Returns a preview + approval_id. Use obs_confirm_destructive to
        execute after user approval. Bucket policies control cross-account
        and public access — incorrect policies can expose data.

        Args:
            bucket_name: Bucket name.
            policy: Bucket policy JSON string (OBS policy format).

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = SetBucketPolicyInput(
            bucket_name=bucket_name,
            policy=policy,
        )
        client = get_client("obs", settings)

        action_label = f"obs_set_bucket_policy(bucket_name={params.bucket_name})"

        def _execute() -> dict:
            # Use do_http_request with raw JSON body.
            # The SDK's SetBucketPolicyRequestBody wraps the policy in XML,
            # but OBS expects raw JSON. Use cname for virtual-hosted-style.
            client.do_http_request(
                method="PUT",
                resource_path="/",
                cname=params.bucket_name,
                query_params=[("policy", "")],
                header_params={"Content-Type": "application/json"},
                body=params.policy,
                response_type="SetBucketPolicyResponse",
            )
            return {
                "updated": True,
                "bucket": params.bucket_name,
                "policy": params.policy,
            }

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "set_bucket_policy",
                "bucket_name": params.bucket_name,
                "policy": params.policy,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "set_bucket_policy",
            "bucket_name": params.bucket_name,
            "message": (
                f"Bucket policy update is ready to submit. Present this "
                f"preview to the user and ask for explicit approval. "
                f"If approved, call "
                f"obs_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    # ------------------------------------------------------------------ #
    # confirm_destructive
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_confirm_destructive(approval_id: str) -> dict:
        """Execute a previously requested destructive OBS operation.

        Call this ONLY after the user has explicitly approved the operation.
        Approval IDs expire after 120 seconds.

        Args:
            approval_id: The approval_id from a pending destructive operation.

        Returns:
            The result of the executed operation.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        entry = pending_actions.pop(approval_id)
        log.info(
            "confirm_destructive approval_id=%s action=%s — executing",
            approval_id, entry["action"],
        )
        return entry["execute_fn"]()

    return {
        "obs_upload_object": obs_upload_object,
        "obs_delete_object": obs_delete_object,
        "obs_create_bucket": obs_create_bucket,
        "obs_set_bucket_policy": obs_set_bucket_policy,
        "obs_confirm_destructive": obs_confirm_destructive,
    }
