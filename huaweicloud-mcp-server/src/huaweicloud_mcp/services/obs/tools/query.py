"""OBS query tools — read-only operations.

Tools:
- obs_describe_buckets: list all buckets or get one bucket's detail
- obs_list_objects: list objects (optionally with versions)
- obs_get_object: get object metadata or content
- obs_generate_presigned_url: generate time-limited download/upload URL
- obs_describe_bucket_policy: get bucket policy + ACL
- obs_describe_bucket_lifecycle: get lifecycle rules
"""
from __future__ import annotations

import io
import logging
import time
import urllib.parse
from typing import Optional

from huaweicloudsdkobs.v1.model import (
    GetBucketAclRequest,
    GetBucketMetadataRequest,
    GetBucketPublicStatusRequest,
    GetObjectRequest,
    HeadObjectRequest,
    ListBucketsRequest,
    ListObjectsRequest,
)
from huaweicloudsdkobs.v1.obs_signer import OBSSigner
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import (
    DescribeBucketLifecycleInput,
    DescribeBucketPolicyInput,
    DescribeBucketsInput,
    GeneratePresignedUrlInput,
    GetObjectInput,
    ListObjectsInput,
)
from ..serializers import (
    bucket_acl_summary,
    bucket_detail,
    bucket_summary,
    object_content,
    object_metadata,
    object_summary,
    object_version_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.obs.tools.query")


def _build_endpoint(region: str) -> str:
    """Build OBS endpoint from region."""
    return f"https://obs.{region}.myhuaweicloud.com"


def _generate_presigned_url(
    ak: str,
    sk: str,
    region: str,
    bucket_name: str,
    object_key: str,
    method: str,
    expires_seconds: int,
) -> str:
    """Generate a presigned URL using OBSSigner (V2 HMAC-SHA1).

    Uses virtual-hosted-style addressing:
      https://<bucket>.obs.<region>.myhuaweicloud.com/<key>
    """
    from huaweicloudsdkobs.v1.obs_credentials import ObsCredentials
    creds = ObsCredentials(ak=ak, sk=sk)
    expires = str(int(time.time()) + expires_seconds)

    # Use the SDK's own signer for exact signature compatibility.
    result = OBSSigner.getSignature(
        credentials=creds,
        method=method,
        bucket=bucket_name,
        key=object_key,
        path_args=[],
        headers={},
        expires=expires,
    )
    signature = result["Signature"]

    endpoint = _build_endpoint(region)
    # Virtual-hosted-style: https://<bucket>.obs.<region>.myhuaweicloud.com/<key>
    # Preserve '/' in object key (OBS expects unencoded slashes in the path).
    host = endpoint.replace("https://", "")
    encoded_key = urllib.parse.quote(object_key, safe="/")
    url = (
        f"https://{bucket_name}.{host}"
        f"/{encoded_key}"
        f"?AccessKeyId={ak}"
        f"&Expires={expires}"
        f"&Signature={urllib.parse.quote(signature, safe='')}"
    )
    return url


def make_query_tools(settings: Settings) -> dict:
    """Build OBS query tools bound to *settings*."""
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # describe_buckets (list/detail dispatch)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_describe_buckets(bucket_name: Optional[str] = None) -> dict:
        """List all OBS buckets or get detail for a single bucket.

        Dispatches based on bucket_name:
          * None/empty → list all buckets (name, creation_date, location).
          * set → get full detail for that bucket (metadata, versioning,
            storage class, encryption, ACL grants, public status).

        Args:
            bucket_name: Bucket name. None/empty to list all.

        Returns:
            LIST: {"buckets": [...], "owner": {...}}
            DETAIL: {"bucket": {name, creation_date, location, storage_class,
                     versioning, is_public, acl_grants, ...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeBucketsInput(bucket_name=bucket_name)
        client = get_client("obs", settings)

        if not params.bucket_name:
            resp = client.list_buckets(ListBucketsRequest())
            raw_buckets = getattr(resp, "buckets", None)
            # OBS SDK wraps the list in a Buckets object with .buckets attr
            if raw_buckets is not None and hasattr(raw_buckets, "buckets"):
                buckets = list(getattr(raw_buckets, "buckets", None) or [])
            elif isinstance(raw_buckets, (list, tuple)):
                buckets = list(raw_buckets)
            else:
                buckets = []
            out = [bucket_summary(b) for b in buckets]
            owner = getattr(resp, "owner", None)
            return {
                "buckets": out,
                "total_count": len(out),
                "owner_id": getattr(owner, "id", None) if owner else None,
            }

        # Detail mode: get bucket metadata + ACL + public status
        meta_resp = client.get_bucket_metadata(
            GetBucketMetadataRequest(bucket_name=params.bucket_name)
        )
        acl_resp = client.get_bucket_acl(
            GetBucketAclRequest(bucket_name=params.bucket_name)
        )
        try:
            pub_resp = client.get_bucket_public_status(
                GetBucketPublicStatusRequest(bucket_name=params.bucket_name)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("get_bucket_public_status failed: %s", exc)
            pub_resp = None

        # Build a synthetic bucket object from metadata
        from types import SimpleNamespace
        synth_bucket = SimpleNamespace(
            name=params.bucket_name,
            creation_date=None,
            location=getattr(meta_resp, "x_obs_bucket_location", None),
        )
        detail = bucket_detail(synth_bucket, meta_resp, acl_resp, pub_resp)
        return {"bucket": detail}

    # ------------------------------------------------------------------ #
    # list_objects (merged with list_object_versions)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_list_objects(
        bucket_name: str,
        prefix: Optional[str] = None,
        delimiter: Optional[str] = None,
        marker: Optional[str] = None,
        max_keys: Optional[int] = 100,
        include_versions: bool = False,
    ) -> dict:
        """List objects in an OBS bucket, optionally including all versions.

        When include_versions=False, returns current objects only.
        When include_versions=True, returns all versions of each object
        (version_id, is_latest, delete_marker). Requires versioning enabled.

        Args:
            bucket_name: Bucket name.
            prefix: Only return objects starting with this prefix.
            delimiter: Group objects by this delimiter (e.g. '/' for dirs).
            marker: Pagination marker.
            max_keys: Max objects per page (1..1000). Default 100.
            include_versions: Include all historical versions.

        Returns:
            {"objects": [...], "common_prefixes": [...], "is_truncated": bool,
             "next_marker": "...", "total_count": N}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListObjectsInput(
            bucket_name=bucket_name,
            prefix=prefix,
            delimiter=delimiter,
            marker=marker,
            max_keys=max_keys,
            include_versions=include_versions,
        )
        client = get_client("obs", settings)

        req = ListObjectsRequest(
            bucket_name=params.bucket_name,
            prefix=params.prefix,
            delimiter=params.delimiter,
            marker=params.marker,
            max_keys=params.max_keys,
            versions=params.include_versions,
        )
        resp = client.list_objects(req)

        if params.include_versions:
            # Version listing — response has versions and delete_markers
            versions = list(getattr(resp, "versions", None) or [])
            delete_markers = list(getattr(resp, "delete_markers", None) or [])
            out = [object_version_summary(v) for v in versions]
            out.extend([
                object_version_summary(dm) for dm in delete_markers
            ])
        else:
            contents = list(getattr(resp, "contents", None) or [])
            out = [object_summary(o) for o in contents]

        common_prefixes = list(getattr(resp, "common_prefixes", None) or [])
        cp_list = []
        for cp in common_prefixes:
            prefix_val = getattr(cp, "prefix", None)
            if prefix_val:
                cp_list.append(prefix_val)

        return {
            "objects": out,
            "common_prefixes": cp_list,
            "is_truncated": getattr(resp, "is_truncated", False),
            "next_marker": getattr(resp, "next_marker", None),
            "total_count": len(out),
        }

    # ------------------------------------------------------------------ #
    # get_object (merged metadata + content)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_get_object(
        bucket_name: str,
        object_key: str,
        include_content: bool = False,
        version_id: Optional[str] = None,
        max_content_bytes: int = 1048576,
    ) -> dict:
        """Get OBS object metadata, optionally with text content.

        When include_content=False, uses HEAD request — returns only
        metadata (size, etag, storage_class, content_type, encryption).
        When include_content=True, downloads the object body (size-limited
        to max_content_bytes, only suitable for text/small files).

        Args:
            bucket_name: Bucket name.
            object_key: Object key (path).
            include_content: Download and return text content.
            version_id: Specific version id.
            max_content_bytes: Max bytes to read (default 1 MB).

        Returns:
            {"key": ..., "size": N, "etag": "...", "storage_class": "...",
             "content": "..."}  (content only if include_content=True)
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GetObjectInput(
            bucket_name=bucket_name,
            object_key=object_key,
            include_content=include_content,
            version_id=version_id,
            max_content_bytes=max_content_bytes,
        )
        client = get_client("obs", settings)

        if not params.include_content:
            # Metadata only — HEAD request
            req = HeadObjectRequest(
                bucket_name=params.bucket_name,
                object_key=params.object_key,
                version_id=params.version_id,
            )
            resp = client.head_object(req)
            return object_metadata(resp, params.object_key)

        # Full content — GET request
        req = GetObjectRequest(
            bucket_name=params.bucket_name,
            object_key=params.object_key,
            version_id=params.version_id,
        )
        resp = client.get_object(req)

        # Read the body — OBS SDK returns SdkStreamResponse with _stream
        content = None
        stream = getattr(resp, "_stream", None)
        if stream is not None:
            # SdkStreamResponse wraps a requests.Response
            raw_bytes = getattr(stream, "content", None)
            if raw_bytes is None and hasattr(stream, "raw"):
                raw_bytes = stream.raw.read(params.max_content_bytes)
            if raw_bytes is not None:
                raw_bytes = raw_bytes[:params.max_content_bytes]
        else:
            # Fallback: raw_content attribute
            raw_content = getattr(resp, "raw_content", None)
            if raw_content is not None:
                if hasattr(raw_content, "read"):
                    raw_bytes = raw_content.read(params.max_content_bytes)
                elif isinstance(raw_content, (bytes, bytearray)):
                    raw_bytes = bytes(raw_content[:params.max_content_bytes])
                else:
                    raw_bytes = str(raw_content).encode("utf-8")[:params.max_content_bytes]
            else:
                raw_bytes = b""

        if raw_bytes:
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raise ToolError(
                    code="BINARY_CONTENT",
                    message=(
                        f"Object {params.object_key!r} contains binary data "
                        f"that cannot be decoded as UTF-8 text. "
                        f"Use obs_generate_presigned_url to download it directly."
                    ),
                    hint="For binary files (images, archives, etc.), use presigned URLs.",
                )

        return object_content(resp, params.object_key, content)

    # ------------------------------------------------------------------ #
    # generate_presigned_url
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_generate_presigned_url(
        bucket_name: str,
        object_key: str,
        method: str = "GET",
        expires: int = 3600,
    ) -> dict:
        """Generate a time-limited presigned URL for object download or upload.

        The URL contains a signature and expires after the specified duration.
        No AK/SK is needed to use the URL — it's self-contained.

        For GET: anyone with the URL can download the object.
        For PUT: anyone with the URL can upload to the object key.

        Args:
            bucket_name: Bucket name.
            object_key: Object key (path).
            method: 'GET' for download URL, 'PUT' for upload URL.
            expires: URL validity in seconds (60..86400). Default 3600.

        Returns:
            {"url": "https://...", "method": "GET|PUT", "expires_in": N,
             "expires_at": "ISO timestamp"}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GeneratePresignedUrlInput(
            bucket_name=bucket_name,
            object_key=object_key,
            method=method,
            expires=expires,
        )

        endpoint = _build_endpoint(settings.region)
        url = _generate_presigned_url(
            ak=settings.access_key_id,
            sk=settings.secret_access_key,
            region=settings.region,
            bucket_name=params.bucket_name,
            object_key=params.object_key,
            method=params.method,
            expires_seconds=params.expires,
        )

        from datetime import datetime, timezone
        expires_at = datetime.fromtimestamp(
            int(time.time()) + params.expires, tz=timezone.utc
        ).isoformat()

        return {
            "url": url,
            "method": params.method,
            "expires_in": params.expires,
            "expires_at": expires_at,
        }

    # ------------------------------------------------------------------ #
    # describe_bucket_policy (policy + ACL)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_describe_bucket_policy(bucket_name: str) -> dict:
        """Get bucket policy and ACL for permission auditing.

        Returns the bucket's ACL grants (owner, grantees, permissions)
        and public access status. Use together with
        obs_audit_bucket_security for comprehensive risk analysis.

        Args:
            bucket_name: Bucket name.

        Returns:
            {"bucket_name": ..., "acl": {...}, "is_public": bool}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeBucketPolicyInput(bucket_name=bucket_name)
        client = get_client("obs", settings)

        acl_resp = client.get_bucket_acl(
            GetBucketAclRequest(bucket_name=params.bucket_name)
        )
        acl = bucket_acl_summary(acl_resp)

        try:
            pub_resp = client.get_bucket_public_status(
                GetBucketPublicStatusRequest(bucket_name=params.bucket_name)
            )
            is_public = getattr(pub_resp, "is_public", None)
        except Exception as exc:  # noqa: BLE001
            log.warning("get_bucket_public_status failed: %s", exc)
            is_public = None

        return {
            "bucket_name": params.bucket_name,
            "acl": acl,
            "is_public": is_public,
        }

    # ------------------------------------------------------------------ #
    # describe_bucket_lifecycle
    # ------------------------------------------------------------------ #
    @wrap_tool
    def obs_describe_bucket_lifecycle(bucket_name: str) -> dict:
        """Get lifecycle rules for an OBS bucket.

        Lifecycle rules define automatic storage class transitions
        (e.g. STANDARD → WARM → COLD) and expiration deletion.
        Useful for troubleshooting unexpected file disappearance
        and cost optimization analysis.

        Note: The OBS SDK may not expose lifecycle APIs directly.
        If unavailable, returns a clear error suggesting the OBS console.

        Args:
            bucket_name: Bucket name.

        Returns:
            {"bucket_name": ..., "rules": [...]} or error dict.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeBucketLifecycleInput(bucket_name=bucket_name)
        client = get_client("obs", settings)

        # Try raw HTTP request for lifecycle configuration.
        # OBS REST API: GET /<bucket>?lifecycle
        # Use cname for virtual-hosted-style addressing (required by OBS).
        try:
            resp = client.do_http_request(
                method="GET",
                resource_path="/",
                cname=params.bucket_name,
                query_params=[("lifecycle", "")],
                response_type=None,
            )
            # Parse raw XML response
            raw_body = None
            if hasattr(resp, "raw_content"):
                raw = resp.raw_content
                if hasattr(raw, "read"):
                    raw_body = raw.read()
                elif isinstance(raw, (bytes, bytearray)):
                    raw_body = bytes(raw)
            if raw_body:
                text = raw_body.decode("utf-8", errors="replace")
                return {
                    "bucket_name": params.bucket_name,
                    "lifecycle_xml": text,
                    "note": "Raw XML response — parse for rule details.",
                }
            return {
                "bucket_name": params.bucket_name,
                "rules": [],
                "note": "No lifecycle configuration found.",
            }
        except Exception as exc:  # noqa: BLE001
            # 404 NoSuchLifecycleConfiguration is a valid response —
            # the bucket simply has no lifecycle rules.
            err_msg = str(exc)
            if "NoSuchLifecycleConfiguration" in err_msg or "404" in err_msg:
                return {
                    "bucket_name": params.bucket_name,
                    "rules": [],
                    "note": "No lifecycle configuration set on this bucket.",
                }
            log.warning("lifecycle query failed: %s", exc)
            raise ToolError(
                code="LIFECYCLE_QUERY_FAILED",
                message=(
                    f"Failed to query lifecycle for bucket "
                    f"{params.bucket_name!r}: {exc}"
                ),
                hint=(
                    "The OBS SDK may not support lifecycle APIs directly. "
                    "Check lifecycle rules in the OBS console or use the "
                    "OBS REST API: GET /<bucket>?lifecycle"
                ),
            )

    return {
        "obs_describe_buckets": obs_describe_buckets,
        "obs_list_objects": obs_list_objects,
        "obs_get_object": obs_get_object,
        "obs_generate_presigned_url": obs_generate_presigned_url,
        "obs_describe_bucket_policy": obs_describe_bucket_policy,
        "obs_describe_bucket_lifecycle": obs_describe_bucket_lifecycle,
    }
