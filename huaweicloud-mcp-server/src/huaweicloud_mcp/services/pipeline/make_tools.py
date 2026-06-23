"""Aggregate all CodeArts Pipeline tools into a single dict."""
from __future__ import annotations

from ...config import Settings
from .tools.query import make_query_tools
from .tools.execution import make_execution_tools
from .tools.lifecycle import make_lifecycle_tools
from .tools.update import make_update_tools


def make_tools(settings: Settings) -> dict:
    """Build all Pipeline tool callables bound to *settings*."""
    tools: dict = {}
    tools.update(make_query_tools(settings))
    tools.update(make_execution_tools(settings))
    tools.update(make_lifecycle_tools(settings))
    tools.update(make_update_tools(settings))
    return tools
