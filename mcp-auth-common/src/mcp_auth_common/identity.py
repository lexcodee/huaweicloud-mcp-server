"""Identity model carried end-to-end from JWT payload to tool RBAC.

Kept deliberately small: only the fields every layer needs. The same model
is produced by:

* :class:`StandaloneAuth` decoding an ``Authorization: Bearer ...`` JWT.
* The gateway middleware decoding the same JWT, then placing the instance
  into ``scope["mcp_identity"]`` for downstream MCP servers.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Identity(BaseModel):
    """Caller identity.

    ``sub`` is the subject claim — a user id or service account id.
    ``roles`` is a flat list of role names (lower-case kebab-case by convention)
    that the upstream issuer attests this subject holds. Role hierarchy
    (``admin`` ⊃ ``operator`` ⊃ ``readonly``) is *not* baked into the JWT —
    it is applied at check time by :func:`mcp_auth_common.require_role`.
    """

    sub: str
    roles: list[str] = Field(default_factory=list)
    tenant: str = ""
    iat: int | None = None
    exp: int | None = None

    model_config = {"frozen": True}
