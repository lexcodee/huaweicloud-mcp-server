"""VPC flow log data query — fetches actual flow log records from LTS.

VPC flow logs are delivered to LTS (Log Tank Service). This tool:
  1. Looks up the flow log config (VPC SDK) to get log_group_id + log_topic_id.
  2. Searches LTS for actual log records in the time window.
  3. Parses the VPC flow log record format and applies filters.

VPC flow log record format (space-delimited):
  version project_id interface_id srcaddr dstaddr srcport dstport
  protocol packets bytes start end action log_status
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkvpc.v2 import ShowFlowLogRequest
from huaweicloudsdklts.v2 import ListLogsRequest, QueryLtsLogParams
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ...cts.time_utils import human_to_epoch_ms, now_ms
from ..models import QueryFlowLogDataInput

log = logging.getLogger("huaweicloud_mcp.services.vpc.tools.flow_log")


def _parse_flow_log_record(content: str) -> Optional[dict]:
    """Parse a single VPC flow log line into a structured dict.

    Returns None if the line doesn't match the expected format.
    """
    parts = content.strip().split()
    if len(parts) < 14:
        return None
    try:
        return {
            "version": parts[0],
            "project_id": parts[1],
            "interface_id": parts[2],
            "srcaddr": parts[3],
            "dstaddr": parts[4],
            "srcport": int(parts[5]),
            "dstport": int(parts[6]),
            "protocol": int(parts[7]),
            "packets": int(parts[8]),
            "bytes": int(parts[9]),
            "start": parts[10],
            "end": parts[11],
            "action": parts[12].lower(),
            "log_status": parts[13],
        }
    except (ValueError, IndexError):
        return None


# Protocol number → name mapping (common ones).
_PROTO_MAP = {1: "icmp", 6: "tcp", 17: "udp"}


def _enrich_record(rec: dict) -> dict:
    """Add human-readable protocol name."""
    proto = rec.get("protocol")
    rec["protocol_name"] = _PROTO_MAP.get(proto, str(proto)) if proto is not None else None
    return rec


def make_flow_log_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def vpc_query_flow_log_data(
        flow_log_id: str,
        start_time: str = "-1h",
        end_time: str = "now",
        src_ip: Optional[str] = None,
        dst_ip: Optional[str] = None,
        dst_port: Optional[int] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        """Query actual VPC flow log records (5-tuple + accept/reject).

        Looks up the flow log config to find the LTS log group/topic,
        then searches LTS for records in the time window. Results are
        parsed into structured dicts with srcaddr, dstaddr, srcport,
        dstport, protocol, action, packets, bytes.

        Use ``action='reject'`` to find denied traffic — combine with
        vpc_audit_security_group to confirm whether SG rules are the cause.

        Args:
            flow_log_id: Flow log UUID (from vpc_list_flow_logs).
            start_time: Window start. Relative ('-1h', '-30m', '-2d') or ISO8601.
            end_time: Window end. Default 'now'.
            src_ip: Filter by source IP address.
            dst_ip: Filter by destination IP address.
            dst_port: Filter by destination port.
            action: Filter by 'accept' or 'reject'.
            limit: Max records to return, default 100.

        Returns:
            {
              "flow_log_id": str,
              "total_returned": int,
              "records": [{srcaddr, dstaddr, srcport, dstport, protocol,
                           action, packets, bytes, ...}, ...]
            }
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryFlowLogDataInput(
            flow_log_id=flow_log_id, start_time=start_time, end_time=end_time,
            src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port,
            action=action, limit=limit,
        )

        # 1. Get flow log config to find LTS group/topic IDs.
        vpc_client = get_client("vpc", settings)
        fl_resp = vpc_client.show_flow_log(
            ShowFlowLogRequest(flowlog_id=params.flow_log_id)
        )
        if fl_resp.flow_log is None:
            raise ToolError(
                code="NOT_FOUND",
                message=f"flow log {params.flow_log_id} not found",
            )
        log_group_id = getattr(fl_resp.flow_log, "log_group_id", None)
        log_topic_id = getattr(fl_resp.flow_log, "log_topic_id", None)
        if not log_group_id or not log_topic_id:
            raise ToolError(
                code="INVALID_FLOW_LOG_CONFIG",
                message=(
                    f"flow log {params.flow_log_id} has no log_group_id or "
                    f"log_topic_id — it may not be properly configured to "
                    f"deliver logs to LTS."
                ),
            )

        # 2. Resolve time window.
        tz = settings.default_timezone
        try:
            to_ms = human_to_epoch_ms(params.end_time, tz) if params.end_time != "now" else now_ms()
            from_ms = (
                human_to_epoch_ms(params.start_time, tz)
                if params.start_time != "now"
                else now_ms()
            )
        except ValueError as e:
            raise ToolError(code="TIME_RANGE_INVALID", message=str(e)) from e

        if from_ms >= to_ms:
            raise ToolError(
                code="TIME_RANGE_INVALID",
                message=f"start_time ({from_ms}) must be < end_time ({to_ms})",
            )

        # 3. Build keyword filter for LTS search.
        #    VPC flow log records are space-delimited, so each filter value
        #    can be used as a keyword token (LTS ANDs them).
        keywords_parts = []
        if params.src_ip:
            keywords_parts.append(params.src_ip)
        if params.dst_ip:
            keywords_parts.append(params.dst_ip)
        if params.dst_port is not None:
            keywords_parts.append(str(params.dst_port))
        if params.action:
            keywords_parts.append(params.action)
        keywords = " ".join(keywords_parts) if keywords_parts else None

        # 4. Search LTS.
        lts_client = get_client("lts", settings)
        body = QueryLtsLogParams(
            start_time=str(from_ms),
            end_time=str(to_ms),
            is_count=True,
            keywords=keywords,
            is_desc=True,
            search_type="init",
            limit=params.limit,
        )
        resp = lts_client.list_logs(
            ListLogsRequest(
                log_group_id=log_group_id,
                log_stream_id=log_topic_id,
                body=body,
            )
        )

        # 5. Parse and filter records.
        records = []
        for item in (getattr(resp, "logs", None) or []):
            content = getattr(item, "content", None) or ""
            rec = _parse_flow_log_record(content)
            if rec is None:
                continue
            # Apply precise filters (keyword match is substring-level).
            if params.src_ip and rec["srcaddr"] != params.src_ip:
                continue
            if params.dst_ip and rec["dstaddr"] != params.dst_ip:
                continue
            if params.dst_port is not None and rec["dstport"] != params.dst_port:
                continue
            if params.action and rec["action"] != params.action:
                continue
            rec["line_num"] = getattr(item, "line_num", None)
            rec["timestamp"] = getattr(item, "collect_time", None)
            records.append(_enrich_record(rec))

        return {
            "flow_log_id": params.flow_log_id,
            "total_returned": len(records),
            "records": records,
        }

    return {
        "vpc_query_flow_log_data": vpc_query_flow_log_data,
    }
