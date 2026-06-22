"""Backwards-compatible facade for the structure named in the original spec."""
from mcp_auth_common import (
    AuthError,
    AuthStrategy,
    AutoAuth,
    Identity,
    create_auth_strategy,
    require_role,
)

from .middleware import GatewayAuthMiddleware

__all__ = [
    "AuthError",
    "AuthStrategy",
    "AutoAuth",
    "GatewayAuthMiddleware",
    "Identity",
    "create_auth_strategy",
    "require_role",
]
