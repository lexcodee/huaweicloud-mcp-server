"""Unified configuration for the Huawei Cloud MCP server.

Merges credentials and settings for ECS, CodeArts Pipeline, and CTS into
a single Settings dataclass. All three services share the same AK/SK/region;
service-specific fields (timezone, http_timeout, etc.) are included here.

Env vars (all read at startup via load_settings):
  HUAWEICLOUD_ACCESS_KEY_ID       (required)
  HUAWEICLOUD_SECRET_ACCESS_KEY   (required)
  HUAWEICLOUD_REGION              (required)
  HUAWEICLOUD_PROJECT_ID          (required for ECS/CTS)
  CODEARTS_DEFAULT_PROJECT_ID     (required for Pipeline; NOT a fallback for
                                   HUAWEICLOUD_PROJECT_ID — Pipeline uses its
                                   own CodeArts project id, which differs from
                                   the IaaS project id)
  CTS_DEFAULT_TIMEZONE            (optional, default Asia/Shanghai)
  HUAWEICLOUD_MCP_LOG_LEVEL       (optional, default INFO)
  HUAWEICLOUD_MCP_LOG_FILE        (optional)
  HUAWEICLOUD_MCP_HTTP_TIMEOUT    (optional, default 30)
  HUAWEICLOUD_MCP_NETWORK_RETRIES (optional, default 2)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()  # local dev convenience; no-op if no .env present
except ImportError:  # pragma: no cover
    pass


REQUIRED_VARS = (
    "HUAWEICLOUD_ACCESS_KEY_ID",
    "HUAWEICLOUD_SECRET_ACCESS_KEY",
    "HUAWEICLOUD_REGION",
)

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_PROJECT_ID = "15f2d47addb14784b82eb910447250a9"
DEFAULT_REGION = "af-south-1"


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration for all Huawei Cloud services."""

    access_key_id: str
    secret_access_key: str
    region: str
    project_id: str = ""
    default_project_id: str = ""
    default_timezone: str = DEFAULT_TIMEZONE
    log_level: str = "INFO"
    log_file: Optional[str] = None
    http_timeout: int = 30
    network_retries: int = 2

    def masked(self) -> dict:
        return {
            "access_key_id": _mask(self.access_key_id),
            "secret_access_key": _mask(self.secret_access_key),
            "region": self.region,
            "project_id": self.project_id,
            "default_project_id": self.default_project_id,
            "default_timezone": self.default_timezone,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "http_timeout": self.http_timeout,
            "network_retries": self.network_retries,
        }


def mask_secret(value: Optional[str]) -> str:
    """Mask a secret value, keeping first 4 and last 4 chars only."""
    return _mask(value or "")


def load_settings() -> Settings:
    """Load settings from env. Exit(2) if required vars missing."""
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        sys.stderr.write(
            "ERROR: huaweicloud-mcp-server: missing required env vars: "
            f"{', '.join(missing)}\n"
            "See .env.example for the full list.\n"
        )
        sys.exit(2)

    try:
        timeout = int(os.environ.get("HUAWEICLOUD_MCP_HTTP_TIMEOUT", "30"))
        retries = int(os.environ.get("HUAWEICLOUD_MCP_NETWORK_RETRIES", "2"))
    except ValueError:
        sys.stderr.write(
            "ERROR: HUAWEICLOUD_MCP_HTTP_TIMEOUT / HUAWEICLOUD_MCP_NETWORK_RETRIES "
            "must be integers.\n"
        )
        sys.exit(2)

    project_id = (os.environ.get("HUAWEICLOUD_PROJECT_ID") or "").strip()
    default_project_id = (os.environ.get("CODEARTS_DEFAULT_PROJECT_ID") or "").strip()

    # NOTE: CODEARTS_DEFAULT_PROJECT_ID and HUAWEICLOUD_PROJECT_ID are different
    # things. CodeArts uses its own project id, which is NOT the IaaS project id.
    # Do NOT fall back from one to the other — if Pipeline needs a project id and
    # CODEARTS_DEFAULT_PROJECT_ID is unset, resolve_project_id() raises explicitly.

    return Settings(
        access_key_id=os.environ["HUAWEICLOUD_ACCESS_KEY_ID"].strip(),
        secret_access_key=os.environ["HUAWEICLOUD_SECRET_ACCESS_KEY"].strip(),
        region=os.environ["HUAWEICLOUD_REGION"].strip(),
        project_id=project_id,
        default_project_id=default_project_id,
        default_timezone=os.environ.get("CTS_DEFAULT_TIMEZONE", DEFAULT_TIMEZONE).strip(),
        log_level=os.environ.get("HUAWEICLOUD_MCP_LOG_LEVEL", "INFO").upper(),
        log_file=os.environ.get("HUAWEICLOUD_MCP_LOG_FILE") or None,
        http_timeout=timeout,
        network_retries=retries,
    )


def resolve_project_id(settings: Settings, supplied: Optional[str]) -> str:
    """Return supplied if truthy, else the configured CodeArts default; raise if both empty.

    Used by Pipeline tools. CodeArts uses its OWN project id
    (CODEARTS_DEFAULT_PROJECT_ID), which is distinct from the IaaS
    HUAWEICLOUD_PROJECT_ID. We do NOT fall back to HUAWEICLOUD_PROJECT_ID —
    using the wrong project id silently routes Pipeline calls to the wrong
    CodeArts project, which is worse than a clean error.
    """
    pid = (
        (supplied or "").strip()
        or (settings.default_project_id or "").strip()
    )
    if not pid:
        from .errors import ToolError

        raise ToolError(
            code="MISSING_PROJECT_ID",
            message=(
                "project_id was not provided and CODEARTS_DEFAULT_PROJECT_ID is not set. "
                "Pipeline requires a CodeArts project id, which is different from "
                "HUAWEICLOUD_PROJECT_ID. Pass project_id explicitly or set "
                "CODEARTS_DEFAULT_PROJECT_ID."
            ),
            hint="Set CODEARTS_DEFAULT_PROJECT_ID (NOT HUAWEICLOUD_PROJECT_ID) in the server env, or pass project_id.",
        )
    return pid
