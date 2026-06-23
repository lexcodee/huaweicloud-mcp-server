"""Aggregate all CTS tools into a single dict."""
from __future__ import annotations

from ...config import Settings
from .tools.search import make_search_tools
from .tools.detail import make_detail_tools


def make_tools(settings: Settings) -> dict:
    """Build all CTS tool callables bound to *settings*."""
    tools: dict = {}
    tools.update(make_search_tools(settings))
    tools.update(make_detail_tools(settings))
    return tools
