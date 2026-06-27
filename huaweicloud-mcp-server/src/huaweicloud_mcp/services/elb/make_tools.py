"""Aggregate all ELB tools into a single dict."""
from __future__ import annotations

from ...config import Settings
from .tools.audit import make_audit_tools
from .tools.manage import make_manage_tools
from .tools.query import make_query_tools


def make_tools(settings: Settings) -> dict:
    """Build all ELB tool callables bound to *settings*."""
    tools: dict = {}
    tools.update(make_query_tools(settings))
    tools.update(make_audit_tools(settings))
    tools.update(make_manage_tools(settings))
    return tools
