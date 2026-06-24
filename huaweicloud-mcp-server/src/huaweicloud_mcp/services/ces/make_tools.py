"""Aggregate all CES tools into a single dict."""
from __future__ import annotations

from ...config import Settings
from .tools.alarm import make_alarm_tools
from .tools.event import make_event_tools
from .tools.metric import make_metric_tools
from .tools.resource_group import make_resource_group_tools


def make_tools(settings: Settings) -> dict:
    """Build all CES tool callables bound to *settings*."""
    tools: dict = {}
    tools.update(make_metric_tools(settings))
    tools.update(make_alarm_tools(settings))
    tools.update(make_resource_group_tools(settings))
    tools.update(make_event_tools(settings))
    return tools
