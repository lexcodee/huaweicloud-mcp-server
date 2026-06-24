"""Aggregate all LTS tools into a single dict."""
from __future__ import annotations

from ...config import Settings
from .tools.alarm import make_alarm_tools
from .tools.discovery import make_discovery_tools
from .tools.search import make_search_tools


def make_tools(settings: Settings) -> dict:
    """Build all LTS tool callables bound to *settings*."""
    tools: dict = {}
    tools.update(make_discovery_tools(settings))
    tools.update(make_search_tools(settings))
    tools.update(make_alarm_tools(settings))
    return tools
