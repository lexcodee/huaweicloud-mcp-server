"""Huawei Cloud CTS client singleton.

CTS is a PROJECT-SCOPED service — the BasicCredentials constructor MUST
receive ``project_id``, otherwise the SDK will fail to sign requests with
a misleading ``IAM.0011`` / signature error. This is the single biggest
foot-gun for CTS integration; the constructor enforces it explicitly.
"""
from __future__ import annotations

import functools
import logging

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions as hwc_exc
from huaweicloudsdkcore.http.http_config import HttpConfig
from huaweicloudsdkcts.v3 import CtsClient
from huaweicloudsdkcts.v3.region.cts_region import CtsRegion

from .config import Settings

log = logging.getLogger("cts_mcp_server.client")

REQUEST_TIMEOUT_SECONDS = 30
RETRY_TIMES = 3


class UnknownRegionError(Exception):
    pass


@functools.lru_cache(maxsize=1)
def _build_client(
    access_key_id: str,
    secret_access_key: str,
    project_id: str,
    region: str,
) -> CtsClient:
    """Build a single CtsClient. Cached on the credential tuple."""
    if not project_id:
        # Defensive: load_settings already guarantees this, but if a caller
        # ever bypasses it the error should be loud and obvious.
        raise ValueError(
            "project_id is required for CTS — it is a project-scoped service "
            "and BasicCredentials cannot sign requests without it."
        )

    try:
        region_obj = CtsRegion.value_of(region)
    except hwc_exc.SdkException as e:
        raise UnknownRegionError(
            f"region '{region}' is not recognized by huaweicloudsdkcts"
        ) from e

    creds = BasicCredentials(
        ak=access_key_id,
        sk=secret_access_key,
        project_id=project_id,
    )

    http_config = HttpConfig.get_default_config()
    http_config.timeout = REQUEST_TIMEOUT_SECONDS
    # retry on 5xx / connection errors only; SDK does not retry on 4xx by default
    http_config.retry_times = RETRY_TIMES

    client = (
        CtsClient.new_builder()
        .with_credentials(creds)
        .with_region(region_obj)
        .with_http_config(http_config)
        .build()
    )
    log.info(
        "cts client built region=%s project_id=%s endpoint=%s",
        region,
        project_id,
        region_obj.endpoint,
    )
    return client


def get_cts_client(settings: Settings) -> CtsClient:
    """Get (or build) the CTS client for the given settings."""
    return _build_client(
        settings.access_key_id,
        settings.secret_access_key,
        settings.project_id,
        settings.region,
    )


def reset_client_cache() -> None:
    """Reset the singleton — for tests."""
    _build_client.cache_clear()
