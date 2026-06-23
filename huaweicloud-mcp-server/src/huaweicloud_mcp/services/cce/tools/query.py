"""Read-only CCE query tools.

Pattern: each list-or-detail tool dispatches based on whether the id
parameter is set. This keeps the tool surface small while still giving
the LLM a clean way to drill from list -> detail without learning two
tools per resource.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkcce.v3 import (
    ListClustersRequest,
    ListNodePoolsRequest,
    ListNodesRequest,
    ShowClusterRequest,
    ShowNodePoolRequest,
    ShowNodeRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import (
    QueryClustersInput,
    QueryNodePoolsInput,
    QueryNodesInput,
)
from ..serializers import (
    cluster_detail,
    cluster_summary,
    node_detail,
    node_summary,
    nodepool_detail,
    nodepool_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.cce.tools.query")


def make_query_tools(settings: Settings) -> dict:
    """Build read-only CCE query tools bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def cce_query_clusters(
        cluster_id: Optional[str] = None,
        type: Optional[str] = None,
        status: Optional[str] = None,
        version: Optional[str] = None,
        detail: bool = False,
    ) -> dict:
        """List CCE clusters, or fetch one cluster's detail.

        Dispatches based on ``cluster_id``:

          * ``cluster_id`` is None/empty  → LIST mode. Returns a compact
            list of clusters in the project, with optional filters
            (type/status/version). Each item: id, name, type, flavor,
            version, phase, billing_mode, created.

          * ``cluster_id`` is set         → DETAIL mode. Returns full
            cluster info: networking (host/container/service CIDRs),
            endpoints, k8s svc IP range, labels/annotations, job_id if a
            background op is in progress, etc. Filters are ignored.

        Args:
            cluster_id: Cluster UUID; omit/empty to list.
            type: List filter — cluster type (e.g. 'VirtualMachine').
            status: List filter — cluster phase (Available/Creating/...).
            version: List filter — Kubernetes version (e.g. 'v1.27').
            detail: Forwarded to Huawei Cloud as the `detail` flag for
                    extra fields per cluster in LIST mode.

        Returns:
            LIST mode:   {"clusters": [...], "count": N}
            DETAIL mode: see serializers.cluster_detail
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryClustersInput(
            cluster_id=cluster_id,
            type=type,
            status=status,
            version=version,
            detail=detail,
        )
        client = get_client("cce", settings)

        if params.cluster_id is None:
            req = ListClustersRequest(
                detail=("true" if params.detail else None),
                status=params.status,
                type=params.type,
                version=params.version,
            )
            resp = client.list_clusters(req)
            items = list(resp.items or [])
            clusters = [cluster_summary(c) for c in items]
            return {"count": len(clusters), "clusters": clusters}

        req = ShowClusterRequest(
            cluster_id=params.cluster_id,
            detail=("true" if params.detail else None),
        )
        resp = client.show_cluster(req)
        if resp is None or (resp.metadata is None and resp.spec is None):
            raise ToolError(
                code="NOT_FOUND",
                message=f"cluster {params.cluster_id} not found",
            )
        return cluster_detail(resp)

    @wrap_tool
    def cce_query_nodes(
        cluster_id: str,
        node_id: Optional[str] = None,
    ) -> dict:
        """List nodes in a CCE cluster, or fetch one node's detail.

        Dispatches based on ``node_id``:

          * ``node_id`` is None/empty → LIST mode. Returns a compact list
            of nodes in the cluster. Each item: id, name, phase, flavor,
            az, os, billing_mode, private_ip, public_ip, server_id (the
            backing ECS UUID), created.

          * ``node_id`` is set        → DETAIL mode. Returns full node
            info: root/data volumes, k8s_tags, user_tags, taints, NIC
            spec, public-ip config, runtime, login key, last_probe_time,
            job_id of the most recent async op.

        Args:
            cluster_id: Cluster id that owns the node(s).
            node_id: Node UUID; omit/empty to list.

        Returns:
            LIST mode:   {"cluster_id": str, "nodes": [...], "count": N}
            DETAIL mode: see serializers.node_detail
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryNodesInput(cluster_id=cluster_id, node_id=node_id)
        client = get_client("cce", settings)

        if params.node_id is None:
            req = ListNodesRequest(cluster_id=params.cluster_id)
            resp = client.list_nodes(req)
            items = list(resp.items or [])
            nodes = [node_summary(n) for n in items]
            return {"cluster_id": params.cluster_id, "count": len(nodes), "nodes": nodes}

        req = ShowNodeRequest(cluster_id=params.cluster_id, node_id=params.node_id)
        resp = client.show_node(req)
        if resp is None or (resp.metadata is None and resp.spec is None):
            raise ToolError(
                code="NOT_FOUND",
                message=f"node {params.node_id} not found in cluster {params.cluster_id}",
            )
        return node_detail(resp)

    @wrap_tool
    def cce_query_nodepools(
        cluster_id: str,
        nodepool_id: Optional[str] = None,
        show_default_node_pool: bool = False,
    ) -> dict:
        """List node pools in a cluster, or fetch one pool's detail.

        Dispatches based on ``nodepool_id``:

          * ``nodepool_id`` is None/empty → LIST mode. Returns a compact
            list of node pools. Each item: id, name, type, phase,
            initial_node_count (desired), current_node, creating_node,
            deleting_node, flavor, az, os, autoscaling_enabled,
            min/max_node_count, created.

          * ``nodepool_id`` is set        → DETAIL mode. Returns full
            pool info: node_template (flavor, az, os, root/data volumes,
            k8s_tags, user_tags, taints, runtime), autoscaling policy
            (min/max/cooldown/priority), job_id if scaling.

        Args:
            cluster_id: Cluster id.
            nodepool_id: Node-pool UUID; omit/empty to list.
            show_default_node_pool: Include the auto-created `DefaultPool`
                                    in LIST mode. Ignored in DETAIL mode.

        Returns:
            LIST mode:   {"cluster_id": str, "nodepools": [...], "count": N}
            DETAIL mode: see serializers.nodepool_detail
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryNodePoolsInput(
            cluster_id=cluster_id,
            nodepool_id=nodepool_id,
            show_default_node_pool=show_default_node_pool,
        )
        client = get_client("cce", settings)

        if params.nodepool_id is None:
            req = ListNodePoolsRequest(
                cluster_id=params.cluster_id,
                show_default_node_pool=params.show_default_node_pool,
            )
            resp = client.list_node_pools(req)
            items = list(resp.items or [])
            pools = [nodepool_summary(p) for p in items]
            return {
                "cluster_id": params.cluster_id,
                "count": len(pools),
                "nodepools": pools,
            }

        req = ShowNodePoolRequest(
            cluster_id=params.cluster_id,
            nodepool_id=params.nodepool_id,
        )
        resp = client.show_node_pool(req)
        if resp is None or (resp.metadata is None and resp.spec is None):
            raise ToolError(
                code="NOT_FOUND",
                message=(
                    f"node pool {params.nodepool_id} not found "
                    f"in cluster {params.cluster_id}"
                ),
            )
        return nodepool_detail(resp)

    return {
        "cce_query_clusters": cce_query_clusters,
        "cce_query_nodes": cce_query_nodes,
        "cce_query_nodepools": cce_query_nodepools,
    }
