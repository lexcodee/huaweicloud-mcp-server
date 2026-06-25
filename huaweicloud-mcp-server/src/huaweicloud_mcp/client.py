"""Unified Huawei Cloud SDK client factory.

Builds cached SDK clients for ECS, CodeArts Pipeline, and CTS from a
single Settings instance. Each service has its own Region class and
Client class, but they share the same BasicCredentials and HttpConfig.
"""
from __future__ import annotations

import functools
import logging
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.http.http_config import HttpConfig

from .config import Settings
from .errors import ToolError

log = logging.getLogger("huaweicloud_mcp.client")


# -----------------------------------------------------------------------
# Per-service config: (ClientClass, RegionClass, pass_project_id_to_creds)
# -----------------------------------------------------------------------
# ECS and CTS require project_id in BasicCredentials; Pipeline does not
# (project_id is passed per-request via the request object).

_SERVICE_REGISTRY: dict[str, dict] = {}


def _ensure_registry() -> None:
    """Lazily populate the service registry (defer SDK imports)."""
    if _SERVICE_REGISTRY:
        return

    # ECS
    from huaweicloudsdkecs.v2 import EcsClient
    from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion

    _SERVICE_REGISTRY["ecs"] = {
        "client_cls": EcsClient,
        "region_cls": EcsRegion,
        "project_id_in_creds": True,
    }

    # CodeArts Pipeline
    from huaweicloudsdkcodeartspipeline.v2.codeartspipeline_client import (
        CodeArtsPipelineClient,
    )
    from huaweicloudsdkcodeartspipeline.v2.region.codeartspipeline_region import (
        CodeArtsPipelineRegion,
    )

    _SERVICE_REGISTRY["pipeline"] = {
        "client_cls": CodeArtsPipelineClient,
        "region_cls": CodeArtsPipelineRegion,
        "project_id_in_creds": False,
    }

    # CTS
    from huaweicloudsdkcts.v3.cts_client import CtsClient
    from huaweicloudsdkcts.v3.region.cts_region import CtsRegion

    _SERVICE_REGISTRY["cts"] = {
        "client_cls": CtsClient,
        "region_cls": CtsRegion,
        "project_id_in_creds": True,
    }

    # CCE
    from huaweicloudsdkcce.v3.cce_client import CceClient
    from huaweicloudsdkcce.v3.region.cce_region import CceRegion

    _SERVICE_REGISTRY["cce"] = {
        "client_cls": CceClient,
        "region_cls": CceRegion,
        "project_id_in_creds": True,
    }

    # LTS — same auth shape as ECS/CTS (project-scoped).
    from huaweicloudsdklts.v2.lts_client import LtsClient
    from huaweicloudsdklts.v2.region.lts_region import LtsRegion

    _SERVICE_REGISTRY["lts"] = {
        "client_cls": LtsClient,
        "region_cls": LtsRegion,
        "project_id_in_creds": True,
    }

    # CES v2 — Cloud Eye Service (project-scoped).
    from huaweicloudsdkces.v2.ces_client import CesClient
    from huaweicloudsdkces.v2.region.ces_region import CesRegion

    _SERVICE_REGISTRY["ces"] = {
        "client_cls": CesClient,
        "region_cls": CesRegion,
        "project_id_in_creds": True,
    }

    # CES v1 — needed for list_metrics, show_metric_data, list_events.
    from huaweicloudsdkces.v1.ces_client import CesClient as CesV1Client
    from huaweicloudsdkces.v1.region.ces_region import CesRegion as CesV1Region

    _SERVICE_REGISTRY["ces_v1"] = {
        "client_cls": CesV1Client,
        "region_cls": CesV1Region,
        "project_id_in_creds": True,
    }

    # VPC — Virtual Private Cloud (vpcs, subnets, route tables, peerings,
    # flow logs, security groups, rules). Project-scoped.
    from huaweicloudsdkvpc.v2.vpc_client import VpcClient
    from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion

    _SERVICE_REGISTRY["vpc"] = {
        "client_cls": VpcClient,
        "region_cls": VpcRegion,
        "project_id_in_creds": True,
    }

    # EIP — Elastic Public IP (v2). Project-scoped.
    from huaweicloudsdkeip.v2.eip_client import EipClient
    from huaweicloudsdkeip.v2.region.eip_region import EipRegion

    _SERVICE_REGISTRY["eip"] = {
        "client_cls": EipClient,
        "region_cls": EipRegion,
        "project_id_in_creds": True,
    }


def _build_http_config(settings: Settings) -> HttpConfig:
    cfg = HttpConfig.get_default_config()
    cfg.timeout = settings.http_timeout
    cfg.ignore_ssl_verification = False
    return cfg


def _build_client(service: str, settings: Settings) -> Any:
    """Build a raw SDK client for *service* from *settings*."""
    _ensure_registry()
    entry = _SERVICE_REGISTRY.get(service)
    if entry is None:
        raise ToolError(
            code="UNKNOWN_SERVICE",
            message=f"Unknown service {service!r}. Known: {sorted(_SERVICE_REGISTRY)}",
        )

    region_cls = entry["region_cls"]
    client_cls = entry["client_cls"]

    try:
        region_obj = region_cls.value_of(settings.region)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(
            code="UNSUPPORTED_REGION",
            message=(
                f"region {settings.region!r} is not recognized by the "
                f"{service} SDK."
            ),
            hint="Common values: af-south-1, cn-north-1, cn-north-4, cn-east-3.",
        ) from exc

    if entry["project_id_in_creds"]:
        creds = BasicCredentials(
            ak=settings.access_key_id,
            sk=settings.secret_access_key,
            project_id=settings.project_id,
        )
    else:
        creds = BasicCredentials(
            ak=settings.access_key_id,
            sk=settings.secret_access_key,
        )

    client = (
        client_cls.new_builder()
        .with_credentials(creds)
        .with_region(region_obj)
        .with_http_config(_build_http_config(settings))
        .build()
    )
    log.info(
        "%s client built region=%s project_id=%s endpoint=%s timeout=%ss",
        service,
        settings.region,
        settings.project_id if entry["project_id_in_creds"] else "(per-request)",
        getattr(region_obj, "endpoint", "?"),
        settings.http_timeout,
    )
    return client


# Cache keyed on (service, ak, sk, region, project_id) so tests that
# change credentials get fresh clients.  Settings is frozen so it's
# hashable, but we build the key manually for clarity.
@functools.lru_cache(maxsize=16)
def _cached_build(
    service: str,
    ak: str,
    sk: str,
    region: str,
    project_id: str,
    timeout: int,
) -> Any:
    """Cached builder — actual Settings fields are the cache key."""
    # Reconstruct a minimal Settings for _build_client.
    from .config import Settings

    settings = Settings(
        access_key_id=ak,
        secret_access_key=sk,
        region=region,
        project_id=project_id,
        http_timeout=timeout,
    )
    return _build_client(service, settings)


def get_client(service: str, settings: Settings) -> Any:
    """Return a cached SDK client for *service*.

    Args:
        service: One of "ecs", "pipeline", "cts".
        settings: The unified Settings instance.
    """
    return _cached_build(
        service,
        settings.access_key_id,
        settings.secret_access_key,
        settings.region,
        settings.project_id,
        settings.http_timeout,
    )


def reset_client_cache() -> None:
    """Clear the client cache — for tests."""
    _cached_build.cache_clear()
