"""Aggregate all CCE tools into a single dict."""
from __future__ import annotations

from ...config import Settings
from .tools.job import make_job_tools
from .tools.query import make_query_tools
from .tools.update import make_update_tools


def make_tools(settings: Settings) -> dict:
    """Build all CCE tool callables bound to *settings*."""
    tools: dict = {}
    tools.update(make_query_tools(settings))
    tools.update(make_update_tools(settings))
    tools.update(make_job_tools(settings))
    return tools
