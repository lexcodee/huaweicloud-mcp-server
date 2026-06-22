"""Cached CodeArts Pipeline SDK client builder.

We use the SDK's BasicCredentials + Region; the SDK auto-resolves the
endpoint from the region id (do NOT hand-craft endpoint URLs).
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.http.http_config import HttpConfig
from huaweicloudsdkcodeartspipeline.v2.codeartspipeline_client import (
    CodeArtsPipelineClient,
)
from huaweicloudsdkcodeartspipeline.v2.region.codeartspipeline_region import (
    CodeArtsPipelineRegion,
)

from .config import Settings
from .errors import ToolError

log = logging.getLogger("pipeline_mcp_server.client")


def _build_http_config(settings: Settings) -> HttpConfig:
    cfg = HttpConfig.get_default_config()
    cfg.timeout = settings.http_timeout
    # Don't enable proxy by default; rely on env (HTTPS_PROXY) if user set it.
    cfg.ignore_ssl_verification = False
    return cfg


def _build_client(settings: Settings) -> CodeArtsPipelineClient:
    try:
        region = CodeArtsPipelineRegion.value_of(settings.region)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(
            code="UNSUPPORTED_REGION",
            message=(
                f"region '{settings.region}' is not recognised by the "
                "CodeArts Pipeline SDK. Check HUAWEICLOUD_REGION."
            ),
            hint=(
                "Common values: af-south-1, cn-north-1, cn-north-4, "
                "cn-east-3, ap-southeast-3."
            ),
        ) from exc

    creds = BasicCredentials(settings.access_key_id, settings.secret_access_key)

    builder = (
        CodeArtsPipelineClient.new_builder()
        .with_credentials(creds)
        .with_region(region)
        .with_http_config(_build_http_config(settings))
    )
    log.info(
        "codearts client built region=%s timeout=%ss retries=%s",
        settings.region, settings.http_timeout, settings.network_retries,
    )
    return builder.build()


# settings is hashable because it's a frozen dataclass.
@lru_cache(maxsize=4)
def get_client(settings: Settings) -> CodeArtsPipelineClient:
    """Return a cached CodeArtsPipelineClient for the given Settings."""
    return _build_client(settings)


# ---------------------------------------------------------------------------
# Low-level helper: enable / disable use the SDK's underlying HTTP plumbing
# because the *current* huaweicloudsdkcodeartspipeline release does not ship
# typed wrappers for the documented EnablePipeline / DisablePipeline APIs:
#   PUT /v5/{project_id}/api/pipelines/{pipeline_id}/unban
#   PUT /v5/{project_id}/api/pipelines/{pipeline_id}/ban
# The SDK still does AK/SK signing, retry, region routing for us — we just
# pass the resource_path through to ``Client.do_http_request``.
# ---------------------------------------------------------------------------

def call_raw_put(
    client: CodeArtsPipelineClient,
    *,
    resource_path: str,
    path_params: dict,
) -> dict:
    """Call a documented PUT endpoint that has no SDK-typed wrapper.

    Returns whatever the SDK's response handler decoded — for the
    ban/unban endpoints this is typically ``True`` (no response body).
    """
    # The SDK's do_http_request with response_type=None crashes because
    # sync_response_handler tries to set .raw_content on the deserialized
    # object (which may be a dict).  We work around this by providing a
    # minimal SdkResponse subclass that accepts the attribute.
    from huaweicloudsdkcore.sdk_response import SdkResponse

    class _RawPutResponse(SdkResponse):
        openapi_types = {}
        attribute_map = {}

        def __init__(self):
            super().__init__()

    response = client.do_http_request(
        method="PUT",
        resource_path=resource_path,
        path_params=path_params,
        query_params=[],
        header_params={"Content-Type": "application/json"},
        body=None,
        post_params=[],
        cname=None,
        response_type=_RawPutResponse,
        response_headers=[],
        collection_formats={},
        request_type="RawPut",
    )
    # response is an SdkResponse subclass; .status_code is the HTTP status.
    # Huawei Cloud quirk: some APIs return HTTP 200 with an error body
    # (e.g. {"error_code": "DEVPIPE.00011301", "error_msg": "..."}).
    # The SDK may deserialize error_code/error_msg as top-level attrs, OR
    # leave them in raw_content as a JSON body.  Check both paths.
    if hasattr(response, "status_code"):
        error_code = getattr(response, "error_code", None)
        error_msg = getattr(response, "error_msg", None)
        # If not set as attributes, try parsing raw_content JSON body
        if not error_code:
            import json as _json
            raw = getattr(response, "raw_content", None)
            if raw:
                try:
                    body = _json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
                    if isinstance(body, dict):
                        error_code = body.get("error_code")
                        error_msg = body.get("error_msg")
                except (ValueError, UnicodeDecodeError, AttributeError):
                    pass
        if error_code:
            return {
                "ok": False,
                "status_code": response.status_code,
                "error_code": error_code,
                "error_msg": error_msg,
            }
        if 200 <= response.status_code < 300:
            return {"ok": True, "status_code": response.status_code}
        body = getattr(response, "body", None) or getattr(response, "content", None)
        return {"ok": False, "status_code": response.status_code, "body": body}
    # Fallback: if it's already a dict (some SDK versions)
    if isinstance(response, dict):
        return response
    return {"ok": True}
