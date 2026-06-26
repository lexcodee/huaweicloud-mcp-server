"""Pydantic input models for OBS MCP tools.

OBS uses the v1 SDK (huaweicloudsdkobs.v1). Tools follow the project's
merge patterns:
- list_objects + list_object_versions → list_objects (include_versions flag)
- get_object_metadata + get_object_content → get_object (include_content flag)
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# obs_describe_buckets — list/detail dispatch
# ---------------------------------------------------------------------------
class DescribeBucketsInput(BaseModel):
    bucket_name: Optional[str] = Field(
        default=None,
        description=(
            "Bucket name. If None/empty, returns the LIST of all buckets. "
            "If set, returns DETAIL for that single bucket (metadata, "
            "versioning, storage class, encryption, ACL, public status)."
        ),
    )


# ---------------------------------------------------------------------------
# obs_list_objects — merged list_objects + list_object_versions
# ---------------------------------------------------------------------------
class ListObjectsInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")
    prefix: Optional[str] = Field(
        default=None,
        description="Only return objects starting with this prefix.",
    )
    delimiter: Optional[str] = Field(
        default=None,
        description=(
            "Delimiter for grouping objects (e.g. '/' to simulate "
            "directory structure). Objects between prefixes are grouped "
            "into common_prefixes."
        ),
    )
    marker: Optional[str] = Field(
        default=None,
        description="Pagination marker — start listing after this key.",
    )
    max_keys: Optional[int] = Field(
        default=100,
        ge=1,
        le=1000,
        description="Max objects to return per page (1..1000). Default 100.",
    )
    include_versions: bool = Field(
        default=False,
        description=(
            "If True, list all object versions (requires versioning "
            "enabled on the bucket). Returns version_id, is_latest, "
            "delete_marker for each version. If False, returns only "
            "the current version of each object."
        ),
    )


# ---------------------------------------------------------------------------
# obs_get_object — merged get_object_metadata + get_object_content
# ---------------------------------------------------------------------------
class GetObjectInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")
    object_key: str = Field(..., description="Object key (path).")
    include_content: bool = Field(
        default=False,
        description=(
            "If True, downloads and returns the object's text content "
            "(size-limited to 1 MB, only for text/small files). "
            "If False, returns only metadata (size, content-type, "
            "storage class, last-modified, etag) via HEAD request."
        ),
    )
    version_id: Optional[str] = Field(
        default=None,
        description="Specific version id (requires versioning enabled).",
    )
    max_content_bytes: int = Field(
        default=1048576,
        ge=1,
        le=10485760,
        description=(
            "Max bytes to read when include_content=True (1..10485760). "
            "Default 1 MB. Objects larger than this are truncated."
        ),
    )


# ---------------------------------------------------------------------------
# obs_generate_presigned_url
# ---------------------------------------------------------------------------
class GeneratePresignedUrlInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")
    object_key: str = Field(..., description="Object key (path).")
    method: Literal["GET", "PUT"] = Field(
        default="GET",
        description=(
            "HTTP method for the presigned URL: 'GET' for download, "
            "'PUT' for upload."
        ),
    )
    expires: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description=(
            "URL validity in seconds (60..86400). Default 3600 (1 hour). "
            "Max 86400 (24 hours)."
        ),
    )


# ---------------------------------------------------------------------------
# obs_upload_object
# ---------------------------------------------------------------------------
class UploadObjectInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")
    object_key: str = Field(..., description="Object key (destination path).")
    content: str = Field(
        ...,
        description="Text content to upload (UTF-8 encoded).",
    )
    content_type: Optional[str] = Field(
        default=None,
        description="Content-Type header (e.g. 'application/json', 'text/plain').",
    )
    storage_class: Optional[str] = Field(
        default=None,
        description=(
            "Storage class: 'STANDARD', 'WARM' (Infrequent Access), "
            "or 'COLD' (Archive). Default: bucket default."
        ),
    )


# ---------------------------------------------------------------------------
# obs_delete_object — two-phase commit
# ---------------------------------------------------------------------------
class DeleteObjectInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")
    object_key: str = Field(..., description="Object key to delete.")
    version_id: Optional[str] = Field(
        default=None,
        description="Specific version to delete (requires versioning enabled).",
    )


# ---------------------------------------------------------------------------
# obs_describe_bucket_policy — get policy + ACL
# ---------------------------------------------------------------------------
class DescribeBucketPolicyInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")


# ---------------------------------------------------------------------------
# obs_describe_bucket_lifecycle
# ---------------------------------------------------------------------------
class DescribeBucketLifecycleInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")


# ---------------------------------------------------------------------------
# obs_create_bucket
# ---------------------------------------------------------------------------
class CreateBucketInput(BaseModel):
    bucket_name: str = Field(
        ...,
        description=(
            "Bucket name. Must be globally unique, 3..63 chars, "
            "lowercase letters/digits/hyphens, start with letter/digit."
        ),
    )
    location: Optional[str] = Field(
        default=None,
        description=(
            "Region for the bucket (e.g. 'af-south-1'). "
            "Defaults to the server's configured region."
        ),
    )
    storage_class: Optional[str] = Field(
        default=None,
        description=(
            "Default storage class: 'STANDARD', 'WARM', or 'COLD'. "
            "Default: STANDARD."
        ),
    )
    acl: Optional[str] = Field(
        default="private",
        description=(
            "Bucket ACL: 'private' (default, no public access), "
            "'public-read', 'public-read-write'. "
            "WARNING: non-private ACLs expose bucket contents."
        ),
    )


# ---------------------------------------------------------------------------
# obs_set_bucket_policy — two-phase commit
# ---------------------------------------------------------------------------
class SetBucketPolicyInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name.")
    policy: str = Field(
        ...,
        description="Bucket policy JSON string (OBS policy format).",
    )


# ---------------------------------------------------------------------------
# obs_confirm_destructive — two-phase commit
# ---------------------------------------------------------------------------
class ConfirmDestructiveInput(BaseModel):
    approval_id: str = Field(..., description="Approval id from a pending operation.")


# ---------------------------------------------------------------------------
# obs_audit_bucket_security — composite security audit
# ---------------------------------------------------------------------------
class AuditBucketSecurityInput(BaseModel):
    bucket_name: str = Field(..., description="Bucket name to audit.")
