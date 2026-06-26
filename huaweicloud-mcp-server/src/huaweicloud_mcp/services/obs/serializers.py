"""Compact JSON-serialisers for OBS SDK objects.

Two-tier strategy mirrors the RDS / VPC modules:
- ``*_summary`` — minimal fields for list views (token-efficient).
- ``*_detail`` — full operational info for single-resource fetches.

``_drop_nulls`` removes None/empty values so the LLM doesn't waste tokens
on absent fields.
"""
from __future__ import annotations

from typing import Any


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _drop_nulls(d: dict) -> dict:
    return {
        k: v
        for k, v in d.items()
        if v is not None and v != [] and v != {} and v != ""
    }


# ---------------------------------------------------------------------------
# Bucket (Bucket)
# ---------------------------------------------------------------------------
def bucket_summary(b: Any) -> dict:
    """List-view bucket — minimal fields for browsing."""
    return _drop_nulls({
        "name": _get(b, "name"),
        "creation_date": _get(b, "creation_date"),
        "location": _get(b, "location"),
    })


def bucket_detail(
    b: Any,
    metadata: Any = None,
    acl: Any = None,
    public_status: Any = None,
) -> dict:
    """Full bucket detail — all operational fields."""
    base = bucket_summary(b)

    # Enrich from GetBucketMetadataResponse
    if metadata is not None:
        base["storage_class"] = _get(metadata, "x_obs_storage_class")
        base["versioning"] = _get(metadata, "x_obs_version")
        base["location"] = _get(metadata, "x_obs_bucket_location") or base.get("location")
        base["epid"] = _get(metadata, "x_obs_epid")
        base["az_redundancy"] = _get(metadata, "x_obs_az_redundancy")
        base["fs_file_interface"] = _get(metadata, "x_obs_fs_file_interface")

    # Enrich from GetBucketPublicStatusResponse
    if public_status is not None:
        base["is_public"] = _get(public_status, "is_public")

    # Enrich from GetBucketAclResponse
    if acl is not None:
        grants = []
        owner = _get(acl, "owner")
        acl_list = _get(acl, "access_control_list")
        if acl_list:
            for grant_obj in (_get(acl_list, "grant") or []):
                grantee = _get(grant_obj, "grantee")
                grants.append(_drop_nulls({
                    "grantee_type": _get(grantee, "canned"),
                    "grantee_id": _get(grantee, "id"),
                    "permission": _get(grant_obj, "permission"),
                    "delivered": _get(grant_obj, "delivered"),
                }))
        base["acl_grants"] = grants
        if owner:
            base["owner_id"] = _get(owner, "id")

    return _drop_nulls(base)


# ---------------------------------------------------------------------------
# Object listing (Contents)
# ---------------------------------------------------------------------------
def object_summary(obj: Any) -> dict:
    """List-view object — minimal fields."""
    return _drop_nulls({
        "key": _get(obj, "key"),
        "size": _get(obj, "size"),
        "last_modified": _get(obj, "last_modified"),
        "etag": _get(obj, "e_tag"),
        "storage_class": _get(obj, "storage_class"),
        "type": _get(obj, "type"),
    })


def object_version_summary(v: Any) -> dict:
    """Version listing entry."""
    return _drop_nulls({
        "key": _get(v, "key"),
        "version_id": _get(v, "version_id"),
        "size": _get(v, "size"),
        "last_modified": _get(v, "last_modified"),
        "etag": _get(v, "e_tag"),
        "storage_class": _get(v, "storage_class"),
        "is_latest": _get(v, "is_latest"),
        "delete_marker": _get(v, "delete_marker"),
        "type": _get(v, "type"),
    })


# ---------------------------------------------------------------------------
# Object metadata (HeadObjectResponse)
# ---------------------------------------------------------------------------
def object_metadata(resp: Any, object_key: str) -> dict:
    """Object metadata from HEAD response."""
    return _drop_nulls({
        "key": object_key,
        "size": _get(resp, "content_length"),
        "etag": _get(resp, "e_tag"),
        "last_modified": _get(resp, "date"),
        "storage_class": _get(resp, "x_obs_storage_class"),
        "content_type": _get(resp, "content_type"),
        "server_side_encryption": _get(resp, "x_obs_server_side_encryption"),
        "kms_key_id": _get(resp, "x_obs_server_side_encryption_kms_key_id"),
        "object_type": _get(resp, "x_obs_object_type"),
        "version_id": _get(resp, "x_obs_version_id"),
        "status_code": _get(resp, "status_code"),
    })


# ---------------------------------------------------------------------------
# Object content (GetObjectResponse)
# ---------------------------------------------------------------------------
def object_content(resp: Any, object_key: str, content: str | None = None) -> dict:
    """Object metadata + text content from GET response."""
    meta = object_metadata(resp, object_key)
    if content is not None:
        meta["content"] = content
    return meta


# ---------------------------------------------------------------------------
# Bucket ACL (GetBucketAclResponse)
# ---------------------------------------------------------------------------
def bucket_acl_summary(resp: Any) -> dict:
    """Compact ACL representation."""
    owner = _get(resp, "owner")
    acl_list = _get(resp, "access_control_list")
    grants = []
    if acl_list:
        for g in (_get(acl_list, "grant") or []):
            grantee = _get(g, "grantee")
            grants.append(_drop_nulls({
                "grantee": _get(grantee, "canned") or _get(grantee, "id"),
                "permission": _get(g, "permission"),
                "delivered": _get(g, "delivered"),
            }))
    return _drop_nulls({
        "owner_id": _get(owner, "id"),
        "grants": grants,
    })
