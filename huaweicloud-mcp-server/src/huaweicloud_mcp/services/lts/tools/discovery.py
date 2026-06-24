"""LTS resource discovery — log groups and log streams under a group.

We deliberately collapse the original ``list_log_groups`` and
``list_log_streams`` into a single ``lts_query_log_resources`` tool that
dispatches on the presence of ``log_group_id``. This mirrors the CCE
list/detail pattern used elsewhere in the project: one fewer entry in the
LLM's tool list, no loss of expressive power.
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdklts.v2 import ListLogGroupsRequest, ListLogStreamRequest
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import wrap_tool
from ..models import QueryLogResourcesInput
from ..serializers import log_group_summary, log_stream_summary

log = logging.getLogger("huaweicloud_mcp.services.lts.tools.discovery")


def make_discovery_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    @wrap_tool
    def lts_query_log_resources(
        log_group_id: Optional[str] = None,
    ) -> dict:
        """List LTS log groups, or list log streams under one group.

        Dispatches based on ``log_group_id``:

          * ``log_group_id`` is None/empty → returns every log GROUP in
            the project. Each item: id, name, alias, ttl_in_days, created.

          * ``log_group_id`` is set        → returns every log STREAM
            inside that group. Each item: id, name, alias, log_group_id,
            ttl_in_days, hot_storage_days, filter_count, created.

        This is the prerequisite discovery step for every other LTS tool
        that needs a (group_id, stream_id) pair (``lts_search_logs``,
        ``lts_get_log_context``, ``lts_query_histogram``).

        Args:
            log_group_id: Log group id; omit/empty to list groups.

        Returns:
            Groups mode:  {"mode":"groups", "count": N, "log_groups": [...]}
            Streams mode: {"mode":"streams", "log_group_id": str,
                           "count": N, "log_streams": [...]}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = QueryLogResourcesInput(log_group_id=log_group_id)
        client = get_client("lts", settings)

        if params.log_group_id is None:
            resp = client.list_log_groups(ListLogGroupsRequest())
            items = list(getattr(resp, "log_groups", None) or [])
            groups = [log_group_summary(g) for g in items]
            return {
                "mode": "groups",
                "count": len(groups),
                "log_groups": groups,
            }

        # Stream listing — list_log_stream(singular) takes ``log_group_id``
        # and returns ``log_streams``.
        resp = client.list_log_stream(
            ListLogStreamRequest(log_group_id=params.log_group_id)
        )
        items = list(getattr(resp, "log_streams", None) or [])
        streams = []
        for s in items:
            entry = log_stream_summary(s)
            # The per-group endpoint doesn't echo log_group_id back; stamp it.
            entry.setdefault("log_group_id", params.log_group_id)
            streams.append(entry)
        return {
            "mode": "streams",
            "log_group_id": params.log_group_id,
            "count": len(streams),
            "log_streams": streams,
        }

    return {"lts_query_log_resources": lts_query_log_resources}
