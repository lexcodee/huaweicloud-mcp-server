"""CES metric tools — list metrics (v1) and get metric data (v1).

Two tools:
  * ``ces_list_metrics`` — discover available metrics by namespace/dimension.
    Uses the v1 SDK (ListMetricsRequest).
  * ``ces_get_metric_data`` — query time-series data for one or more metrics.
    Uses the v1 SDK (ShowMetricDataRequest) which supports period, filter,
    and arbitrary time windows (unlike the v2 batch API which is limited
    to 5-minute windows and lacks period/filter).
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkces.v1 import ListMetricsRequest, ShowMetricDataRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from .._time import resolve_time_window
from ..models import GetMetricDataInput, ListMetricsInput, MetricSpec
from ..serializers import metric_data_point_v1, metric_summary

log = logging.getLogger("huaweicloud_mcp.services.ces.tools.metric")


def _parse_dimensions(dimensions: str) -> dict:
    """Parse a comma-separated dimensions string into {dim_0, dim_1, dim_2, dim_3}.

    Input:  "instance_id,abc123" or "instance_id,abc123,process_name,sshd"
    Output: {"dim_0": "instance_id,abc123", "dim_1": "process_name,sshd"}
    """
    if not dimensions:
        return {}
    parts = [p.strip() for p in dimensions.split(",") if p.strip()]
    if len(parts) % 2 != 0:
        raise ToolError(
            code="INVALID_PARAMS",
            message=(
                f"Dimensions must be comma-separated name,value pairs; "
                f"got odd number of parts: {dimensions!r}"
            ),
        )
    result = {}
    for i in range(0, len(parts), 2):
        key = parts[i]
        value = parts[i + 1]
        dim_idx = i // 2
        if dim_idx > 3:
            raise ToolError(
                code="INVALID_PARAMS",
                message=f"Too many dimension pairs (max 4): {dimensions!r}",
            )
        result[f"dim_{dim_idx}"] = f"{key},{value}"
    return result


def make_metric_tools(settings: Settings) -> dict:
    """Build CES metric tools bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def ces_list_metrics(
        namespace: Optional[str] = None,
        metric_name: Optional[str] = None,
        dim_0: Optional[str] = None,
        dim_1: Optional[str] = None,
        dim_2: Optional[str] = None,
        start: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """List available CES metrics, filtered by namespace/dimension.

        This is the prerequisite discovery step: call it to learn which
        metric_name values exist for a given namespace before querying
        time-series data with ``ces_get_metric_data``.

        Common namespaces:
          SYS.ECS  — cloud server CPU/memory/disk/network
          SYS.RDS  — relational database
          SYS.DCS  — Redis cache
          SYS.ELB  — load balancer
          SYS.CCE  — container cluster nodes
          SYS.FunctionGraph — function compute

        Args:
            namespace: Service namespace, e.g. 'SYS.ECS'.
            metric_name: Metric name filter, e.g. 'cpu_util'.
            dim_0: First dimension filter, format 'key,value'.
            dim_1: Second dimension filter.
            dim_2: Third dimension filter.
            start: Pagination cursor.
            limit: Page size (1..1000).

        Returns:
            {"metrics": [...], "count": N}
            Each metric: {namespace, metric_name, unit, dimensions: [{name, value}]}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListMetricsInput(
            namespace=namespace,
            metric_name=metric_name,
            dim_0=dim_0,
            dim_1=dim_1,
            dim_2=dim_2,
            start=start,
            limit=limit,
        )
        # v1 client for list_metrics
        client = get_client("ces_v1", settings)

        req = ListMetricsRequest(
            namespace=params.namespace,
            metric_name=params.metric_name,
            dim_0=params.dim_0,
            dim_1=params.dim_1,
            dim_2=params.dim_2,
            start=params.start,
            limit=params.limit,
        )
        resp = client.list_metrics(req)
        items = list(getattr(resp, "metrics", None) or [])
        metrics = [metric_summary(m) for m in items]
        return {"count": len(metrics), "metrics": metrics}

    @wrap_tool
    def ces_get_metric_data(
        metrics: list[dict],
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        period: Optional[int] = None,
        filter: str = "average",
    ) -> dict:
        """Query CES metric time-series data for one or more metrics.

        Each item in ``metrics`` is {namespace, metric_name, dimensions}:
          - namespace: e.g. "SYS.ECS"
          - metric_name: e.g. "cpu_util"
          - dimensions: comma-separated "name,value" pairs,
            e.g. "instance_id,abc123" or "instance_id,abc123,process_name,sshd"
            (leave empty for ALL_INSTANCE queries)

        The tool loops over each metric spec internally using the v1
        ShowMetricData API, which supports period/filter and arbitrary
        time windows (unlike the v2 batch API which is limited to 5 min).

        Args:
            metrics: List of {namespace, metric_name, dimensions} dicts.
                     Max 500 items.
            from_time: Window start. Default '-5m'.
            to_time: Window end. Default 'now'.
            period: Aggregation period in seconds
                    (1/60/300/1200/3600/14400/86400). Default 1.
            filter: Aggregation function: average/max/min/sum/variance.

        Returns:
            {"results": [...], "total_returned": N}
            Each result: {namespace, metric_name, dimensions, data_points: [...]}
            Each data_point: {timestamp, value, unit}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        # Validate and parse metrics list
        try:
            metric_specs = [MetricSpec(**m) for m in metrics]
        except Exception as e:
            raise ToolError(
                code="INVALID_PARAMS",
                message=f"Invalid metrics spec: {e}",
            ) from e

        params = GetMetricDataInput(
            metrics=metric_specs,
            from_time=from_time,
            to_time=to_time,
            period=period,
            filter=filter,  # type: ignore[arg-type]
        )

        # Resolve time window
        from_ms, to_ms = resolve_time_window(
            params.from_time, params.to_time,
            default_from="-5m",
            settings=settings,
        )

        # v1 client for show_metric_data
        client = get_client("ces_v1", settings)

        results: list[dict] = []
        for spec in params.metrics:
            # Parse dimensions string into dim_0..dim_3
            dims = _parse_dimensions(spec.dimensions)

            req = ShowMetricDataRequest(
                namespace=spec.namespace,
                metric_name=spec.metric_name,
                filter=params.filter,
                period=params.period,
                _from=from_ms,
                to=to_ms,
                **dims,
            )
            resp = client.show_metric_data(req)

            dps = list(getattr(resp, "datapoints", None) or [])
            dps_out = [metric_data_point_v1(dp, params.filter) for dp in dps]
            results.append(
                {
                    "namespace": spec.namespace,
                    "metric_name": getattr(resp, "metric_name", spec.metric_name),
                    "dimensions": spec.dimensions,
                    "data_points": dps_out,
                }
            )

        return {"results": results, "total_returned": len(results)}

    return {
        "ces_list_metrics": ces_list_metrics,
        "ces_get_metric_data": ces_get_metric_data,
    }
