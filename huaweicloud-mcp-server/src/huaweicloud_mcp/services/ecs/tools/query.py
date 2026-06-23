"""Read-only ECS query tools."""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkecs.v2 import (
    ListFlavorsRequest,
    ListServersDetailsRequest,
    ShowServerRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import (
    GetServerInput,
    ListFlavorsInput,
    ListServersInput,
)
from ..serializers import (
    flavor_summary,
    server_detail,
    server_status_only,
    server_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.ecs.tools.query")


def make_query_tools(settings: Settings) -> dict:
    """Build query tool callables bound to a Settings instance.

    Returns a dict {name: callable}. The callables are decorated with
    @wrap_tool so they always return {"ok":..., "data"|"error": ...}.
    """
    auth = create_auth_strategy()

    @wrap_tool
    def ecs_list_servers(
        name: Optional[str] = None,
        status: Optional[str] = None,
        flavor_id: Optional[str] = None,
        ip: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = 20,
        offset: int = 1,
    ) -> dict:
        """List ECS servers in the project, with optional filters and pagination.

        Token-optimized for LLM scanning: each server entry carries only the
        fields routinely populated by Huawei Cloud's list response, with all
        null/empty values dropped. Addresses are returned as a flat IP map
        ``{vpc_id: ["ip1", "ip2"]}`` rather than the SDK's nested NIC shape.

        For full operational info on a specific server (image_id,
        availability_zone, power_state, NIC type/MAC, security groups,
        volumes, metadata, ...), call ``ecs_get_server`` with the id
        (defaults to detail_level="full"). Pass detail_level="status" for
        a cheap status-only poll.

        Args:
            name: Substring of server name (Huawei Cloud does fuzzy match).
            status: One of ACTIVE / SHUTOFF / ERROR / BUILD / REBOOT / ...
            flavor_id: Restrict to a specific flavor.
            ip: Substring of private IPv4 address.
            tags: 'k=v' or 'k1=v1,k2=v2' — Huawei Cloud format.
            limit: 1..100, default 20.
            offset: 1-based page number, default 1.

        Returns:
            {"servers": [...], "count": N, "limit": L, "offset": O}.
            Each server item carries (when set):
            id, name, status, flavor_id, addresses, created, tags, task_state.
            Null fields are omitted entirely — absence implies the field
            wasn't returned by the API or wasn't applicable.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListServersInput(
            name=name,
            status=status,
            flavor_id=flavor_id,
            ip=ip,
            tags=tags,
            limit=limit,
            offset=offset,
        )
        client = get_client("ecs", settings)

        req = ListServersDetailsRequest(
            name=params.name,
            status=params.status,
            flavor=params.flavor_id,
            ip=params.ip,
            tags=params.tags,
            limit=params.limit,
            offset=params.offset,
        )
        resp = client.list_servers_details(req)
        servers = [server_summary(s) for s in (resp.servers or [])]
        return {
            "count": resp.count if resp.count is not None else len(servers),
            "limit": params.limit,
            "offset": params.offset,
            "servers": servers,
        }

    @wrap_tool
    def ecs_get_server(server_id: str, detail_level: str = "full") -> dict:
        """Inspect a single ECS server. Replaces the old detail/status pair.

        Two views are supported via ``detail_level``:

          * ``"full"`` (default) — complete server detail: flavor (vcpu/ram/disk),
            attached volumes, security groups, addresses (rich NIC form),
            metadata, key_name, host_id, image_id, AZ, etc. Backed by
            ListServersDetails. Use when you need depth.

          * ``"status"`` — lightweight power snapshot
            ``{server_id, name, status, task_state, power_state}``. Backed by
            the cheaper ShowServer call. Use when polling a power op
            (start/stop/reboot/resize) or just checking ACTIVE/SHUTOFF.

        Args:
            server_id: ECS server UUID.
            detail_level: "full" or "status". Defaults to "full".

        Returns:
            For detail_level="full": see serializers.server_detail.
            For detail_level="status": {server_id, name, status, task_state, power_state}.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = GetServerInput(server_id=server_id, detail_level=detail_level)
        client = get_client("ecs", settings)

        if params.detail_level == "status":
            req = ShowServerRequest(server_id=params.server_id)
            resp = client.show_server(req)
            if resp.server is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"server {params.server_id} not found",
                )
            return server_status_only(resp.server)

        # "full" — use ListServersDetails(server_id=...) to get the rich payload.
        req = ListServersDetailsRequest(server_id=params.server_id, limit=1)
        resp = client.list_servers_details(req)
        if not resp.servers:
            raise ToolError(
                code="NOT_FOUND",
                message=f"server {params.server_id} not found in project",
            )
        return server_detail(resp.servers[0])

    @wrap_tool
    def ecs_list_flavors(
        availability_zone: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """List available ECS flavors (instance types) in the region.

        Use before ecs_resize_server to pick a target_flavor_ref, or to
        suggest a flavor to the user. Note: not every flavor is available in
        every AZ — pass availability_zone to narrow it down.

        Args:
            availability_zone: Optional AZ id, e.g. 'af-south-1a'.
            limit: Max flavors to return, default 50, max 200.

        Returns:
            {"count": N, "flavors": [{id, name, vcpus, ram_mb, disk_gb,
                                       generation, performance_type}, ...]}.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListFlavorsInput(availability_zone=availability_zone, limit=limit)
        client = get_client("ecs", settings)
        req = ListFlavorsRequest(availability_zone=params.availability_zone)
        resp = client.list_flavors(req)
        flavors = [flavor_summary(f) for f in (resp.flavors or [])]
        # Apply client-side limit since ListFlavors doesn't support a server-side limit.
        flavors = flavors[: params.limit]
        return {"count": len(flavors), "flavors": flavors}

    return {
        "ecs_list_servers": ecs_list_servers,
        "ecs_get_server": ecs_get_server,
        "ecs_list_flavors": ecs_list_flavors,
    }