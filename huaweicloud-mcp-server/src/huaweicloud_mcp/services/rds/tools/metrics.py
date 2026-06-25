"""RDS metrics tool — cross-calls CES (Cloud Eye Service).

rds_get_instance_metrics queries RDS monitoring metrics via the CES v1 SDK.
The RDS namespace is 'SYS.RDS' and the primary dimension is
'instance_id,<rds_instance_id>'.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkces.v1 import ShowMetricDataRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ...ces._time import resolve_time_window
from ..models import GetInstanceMetricsInput

log = logging.getLogger("huaweicloud_mcp.services.rds.tools.metrics")

# Common RDS metric names and their human-readable descriptions.
RDS_METRIC_NAMES = {
    "rds001_cpu_util": "CPU utilization (%)",
    "rds002_mem_util": "Memory utilization (%)",
    "rds003_iops": "IOPS (input/output operations per second)",
    "rds004_connections": "Active database connections",
    "rds005_disk_util": "Disk space utilization (%)",
    "rds006_inbound_traffic": "Inbound network traffic (bytes/s)",
    "rds007_outbound_traffic": "Outbound network traffic (bytes/s)",
    "rds008_read_io_req": "Read I/O requests per second",
    "rds009_write_io_req": "Write I/O requests per second",
    "rds010_used_rds_size": "Used storage space (GB)",
}


def make_metrics_tools(settings: Settings) -> dict:
    """Build RDS metrics tool bound to *settings*."""
    auth = create_auth_strategy()

    @wrap_tool
    def rds_get_instance_metrics(
        instance_id: str,
        metrics: Optional[list[str]] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        period: Optional[int] = None,
        filter: str = "average",
    ) -> dict:
        """Query RDS instance monitoring metrics via CES.

        Wraps the CES ShowMetricData API for the SYS.RDS namespace,
        querying one or more metrics for a specific RDS instance.

        Common metrics:
          rds001_cpu_util      — CPU utilization (%)
          rds002_mem_util      — Memory utilization (%)
          rds003_iops          — IOPS
          rds004_connections   — Active connections
          rds005_disk_util     — Disk utilization (%)

        Use this alongside rds_get_db_logs(log_type='slow') to correlate
        slow queries with resource pressure (CPU/IOPS spikes).

        Args:
            instance_id: RDS instance UUID.
            metrics: List of metric names. Default: 5 core metrics.
            from_time: Window start. Default '-30m'.
            to_time: Window end. Default 'now'.
            period: Aggregation period in seconds (1/300/1200/3600). Default 300.
            filter: Aggregation function (average/max/min/sum/variance).

        Returns:
            {"results": [...], "total_returned": N}
            Each result: {metric_name, description, data_points: [{timestamp, value, unit}]}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        default_metrics = [
            "rds001_cpu_util",
            "rds002_mem_util",
            "rds003_iops",
            "rds004_connections",
            "rds005_disk_util",
        ]
        params = GetInstanceMetricsInput(
            instance_id=instance_id,
            metrics=metrics or default_metrics,
            from_time=from_time,
            to_time=to_time,
            period=period,
            filter=filter,  # type: ignore[arg-type]
        )

        from_ms, to_ms = resolve_time_window(
            params.from_time, params.to_time,
            default_from="-30m",
            settings=settings,
        )

        # Use CES v1 client for ShowMetricData.
        client = get_client("ces_v1", settings)
        namespace = "SYS.RDS"
        dim_0 = f"instance_id,{params.instance_id}"

        results: list[dict] = []
        for metric_name in params.metrics:
            req = ShowMetricDataRequest(
                namespace=namespace,
                metric_name=metric_name,
                filter=params.filter,
                period=params.period or 300,
                _from=from_ms,
                to=to_ms,
                dim_0=dim_0,
            )
            resp = client.show_metric_data(req)
            dps = list(getattr(resp, "datapoints", None) or [])
            dps_out = [
                {
                    "timestamp": getattr(dp, "timestamp", None),
                    "value": getattr(dp, params.filter, None),
                    "unit": getattr(dp, "unit", None),
                }
                for dp in dps
            ]
            results.append({
                "metric_name": metric_name,
                "description": RDS_METRIC_NAMES.get(metric_name, ""),
                "data_points": dps_out,
            })

        return {"results": results, "total_returned": len(results)}

    return {"rds_get_instance_metrics": rds_get_instance_metrics}
