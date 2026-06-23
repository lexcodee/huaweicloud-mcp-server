"""Low-level HTTP helper for Pipeline endpoints without SDK typed wrappers.

Extracted from the original pipeline_mcp_server.client module. The
CodeArts Pipeline SDK does not ship typed wrappers for EnablePipeline /
DisablePipeline (PUT /ban, PUT /unban), so we route through
Client.do_http_request which still does AK/SK signing + region routing.
"""
from __future__ import annotations

import json as _json
from typing import Any


def call_raw_put(
    client: Any,
    *,
    resource_path: str,
    path_params: dict,
) -> dict:
    """Call a documented PUT endpoint that has no SDK-typed wrapper.

    Returns whatever the SDK's response handler decoded — for the
    ban/unban endpoints this is typically ``True`` (no response body).
    """
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
    if hasattr(response, "status_code"):
        error_code = getattr(response, "error_code", None)
        error_msg = getattr(response, "error_msg", None)
        if not error_code:
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
    if isinstance(response, dict):
        return response
    return {"ok": True}
