"""Huawei Cloud ECS client singleton with timeout and retry policy."""
from __future__ import annotations

import functools
import logging

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions as hwc_exc
from huaweicloudsdkcore.http.http_config import HttpConfig
from huaweicloudsdkecs.v2 import EcsClient
from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion

from .config import Settings

log = logging.getLogger("ecs_mcp_server.client")

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
) -> EcsClient:
    """Build a single EcsClient. Cached on the credential tuple."""
    try:
        region_obj = EcsRegion.value_of(region)
    except hwc_exc.SdkException as e:  # noqa: BLE001
        raise UnknownRegionError(
            f"region '{region}' is not recognized by huaweicloudsdkecs"
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
    # ignore SSL is OFF (default); we trust Huawei Cloud certs

    client = (
        EcsClient.new_builder()
        .with_credentials(creds)
        .with_region(region_obj)
        .with_http_config(http_config)
        .build()
    )
    log.info(
        "ecs client built region=%s project_id=%s endpoint=%s",
        region,
        project_id,
        region_obj.endpoint,
    )
    return client


def get_ecs_client(settings: Settings) -> EcsClient:
    """Get (or build) the ECS client for the given settings."""
    return _build_client(
        settings.access_key_id,
        settings.secret_access_key,
        settings.project_id,
        settings.region,
    )


def reset_client_cache() -> None:
    """Reset the singleton — for tests."""
    _build_client.cache_clear()
