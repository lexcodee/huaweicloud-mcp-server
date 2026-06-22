"""Configuration loading for the CodeArts Pipeline MCP server.

Fail-fast on missing required env vars (exit 2 = configuration error).
Never log raw AK/SK; the `masked()` helper provides safe representations
for diagnostics.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

REQUIRED_VARS = (
    "HUAWEICLOUD_ACCESS_KEY_ID",
    "HUAWEICLOUD_SECRET_ACCESS_KEY",
    "HUAWEICLOUD_REGION",
)


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


@dataclass(frozen=True)
class Settings:
    access_key_id: str
    secret_access_key: str
    region: str
    default_project_id: Optional[str] = None
    log_level: str = "INFO"
    log_file: Optional[str] = None
    http_timeout: int = 30
    network_retries: int = 2

    def masked(self) -> dict:
        return {
            "access_key_id": _mask(self.access_key_id),
            "secret_access_key": _mask(self.secret_access_key),
            "region": self.region,
            "default_project_id": self.default_project_id,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "http_timeout": self.http_timeout,
            "network_retries": self.network_retries,
        }


def load_settings() -> Settings:
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        sys.stderr.write(
            "ERROR: codearts-pipeline-mcp-server: missing required env vars: "
            f"{', '.join(missing)}\n"
            "See .env.example for the full list.\n"
        )
        sys.exit(2)

    try:
        timeout = int(os.environ.get("PIPELINE_MCP_HTTP_TIMEOUT", "30"))
        retries = int(os.environ.get("PIPELINE_MCP_NETWORK_RETRIES", "2"))
    except ValueError:
        sys.stderr.write(
            "ERROR: PIPELINE_MCP_HTTP_TIMEOUT / PIPELINE_MCP_NETWORK_RETRIES "
            "must be integers.\n"
        )
        sys.exit(2)

    return Settings(
        access_key_id=os.environ["HUAWEICLOUD_ACCESS_KEY_ID"].strip(),
        secret_access_key=os.environ["HUAWEICLOUD_SECRET_ACCESS_KEY"].strip(),
        region=os.environ["HUAWEICLOUD_REGION"].strip(),
        default_project_id=(os.environ.get("CODEARTS_DEFAULT_PROJECT_ID") or None),
        log_level=os.environ.get("PIPELINE_MCP_LOG_LEVEL", "INFO").upper(),
        log_file=os.environ.get("PIPELINE_MCP_LOG_FILE") or None,
        http_timeout=timeout,
        network_retries=retries,
    )


def resolve_project_id(settings: Settings, supplied: Optional[str]) -> str:
    """Return supplied if truthy, else the configured default; raise if both empty."""
    pid = (supplied or "").strip() or (settings.default_project_id or "").strip()
    if not pid:
        # Imported here to avoid circular import at module load time.
        from .errors import ToolError
        raise ToolError(
            code="MISSING_PROJECT_ID",
            message=(
                "project_id was not provided and CODEARTS_DEFAULT_PROJECT_ID "
                "is not set. Pass project_id explicitly or set the default."
            ),
            hint="Set CODEARTS_DEFAULT_PROJECT_ID in the server env, or pass project_id.",
        )
    return pid
