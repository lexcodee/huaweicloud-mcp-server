"""Re-export AuthStrategy hierarchy from :mod:`mcp_auth_common`."""
from mcp_auth_common.strategy import (
    DEFAULT_ROLE_HIERARCHY,
    AutoAuth,
    AuthStrategy,
    create_auth_strategy,
    require_role,
)

__all__ = [
    "AuthMode",  # removed — kept as alias for migration
    "AutoAuth",
    "AuthStrategy",
    "DEFAULT_ROLE_HIERARCHY",
    "create_auth_strategy",
    "require_role",
]
