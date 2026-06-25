"""Aggregate all VPC tools into a single dict."""
from __future__ import annotations

from ...config import Settings
from .tools.query import make_query_tools
from .tools.manage import make_manage_tools
from .tools.network import make_network_tools
from .tools.eip import make_eip_tools
from .tools.route import make_route_tools
from .tools.flow_log import make_flow_log_tools


def make_tools(settings: Settings) -> dict:
    """Build all VPC tool callables bound to *settings*."""
    tools: dict = {}
    tools.update(make_query_tools(settings))
    tools.update(make_manage_tools(settings))
    tools.update(make_network_tools(settings))
    tools.update(make_eip_tools(settings))
    tools.update(make_route_tools(settings))
    tools.update(make_flow_log_tools(settings))
    return tools
