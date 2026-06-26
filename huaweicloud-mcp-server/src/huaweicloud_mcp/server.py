"""Unified FastMCP server entrypoint.

build_server(enabled={"ecs", "pipeline", "cts", "cce"}) builds a single FastMCP
instance with tools from the selected Huawei Cloud services. Each service
module exposes a make_tools(settings) -> dict[str, callable] function.

Tool-level filtering: pass ``include`` / ``exclude`` (lists of fnmatch globs)
to register only a subset of tools. Useful for RBAC mounts (read-only token
gets a different mount that excludes ``*_set_status`` etc.) or for shrinking
the LLM tool list per use-case. Both also accept env overrides:

    MCP_INCLUDE_TOOLS="ecs_*,cts_*"
    MCP_EXCLUDE_TOOLS="*_set_status,*_confirm_destructive,*_scale_*"

Precedence: explicit kwargs > env vars. include filters first (kept only if
at least one pattern matches), then exclude removes from the result.

Transport is selected via MCP_TRANSPORT env var (stdio | sse | streamable-http),
same as the original per-service servers.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import sys
from typing import Iterable, Optional

from mcp.server.fastmcp import FastMCP

from .config import load_settings, Settings
from .logging_setup import setup_logging

VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")

SERVER_NAME = "huaweicloud-mcp-server"

ALL_SERVICES = ("ecs", "pipeline", "cts", "cce", "lts", "ces", "vpc", "rds", "obs")


def _split_csv(value: str | None) -> list[str]:
    """Parse a comma-separated env var into a list of trimmed non-empty parts."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _normalise_patterns(value: Iterable[str] | str | None) -> list[str]:
    """Accept None / str / iterable[str] from YAML or env, return a clean list."""
    if value is None:
        return []
    if isinstance(value, str):
        return _split_csv(value)
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _filter_tools(
    tools: dict,
    include: list[str],
    exclude: list[str],
    *,
    log: logging.Logger,
) -> dict:
    """Apply include then exclude glob filters to a tool-name dict.

    Patterns are matched case-sensitively with :func:`fnmatch.fnmatchcase`,
    consistent with tool names (which are all lowercase snake_case).
    """
    if not include and not exclude:
        return tools

    def _matches_any(name: str, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatchcase(name, pat) for pat in patterns)

    kept: dict = {}
    dropped_by_include: list[str] = []
    dropped_by_exclude: list[str] = []
    for name, fn in tools.items():
        if include and not _matches_any(name, include):
            dropped_by_include.append(name)
            continue
        if exclude and _matches_any(name, exclude):
            dropped_by_exclude.append(name)
            continue
        kept[name] = fn

    if include:
        unmatched = [pat for pat in include if not any(fnmatch.fnmatchcase(n, pat) for n in tools)]
        if unmatched:
            log.warning("include patterns matched no tools: %s", unmatched)
    if exclude:
        unmatched = [pat for pat in exclude if not any(fnmatch.fnmatchcase(n, pat) for n in tools)]
        if unmatched:
            log.warning("exclude patterns matched no tools: %s", unmatched)
    if dropped_by_include:
        log.info("tool filter: %d tools not in include set: %s",
                 len(dropped_by_include), sorted(dropped_by_include))
    if dropped_by_exclude:
        log.info("tool filter: %d tools excluded: %s",
                 len(dropped_by_exclude), sorted(dropped_by_exclude))
    return kept


def build_server(
    enabled: Optional[list[str] | set[str]] = None,
    *,
    include: Optional[list[str] | str] = None,
    exclude: Optional[list[str] | str] = None,
    settings: Optional[Settings] = None,
) -> FastMCP:
    """Build a fully wired FastMCP server.

    Args:
        enabled: Subset of ``ALL_SERVICES`` to register. Accepts a list (from
                 YAML manifest) or set. Defaults to all services. Env override:
                 ``MCP_ENABLED_SERVICES``.
        include: Optional fnmatch globs; only tools matching at least one
                 pattern are registered. Applied before ``exclude``. Env
                 override: ``MCP_INCLUDE_TOOLS`` (comma-separated).
        exclude: Optional fnmatch globs; matching tools are removed. Applied
                 after ``include``. Env override: ``MCP_EXCLUDE_TOOLS``.
        settings: Pre-loaded Settings. If None, loads from env.
    """
    if settings is None:
        settings = load_settings()

    log = setup_logging(
        level=settings.log_level,
        log_file=settings.log_file,
        known_secrets=[settings.access_key_id, settings.secret_access_key],
    )

    if enabled is None:
        env_services = os.environ.get("MCP_ENABLED_SERVICES", "")
        if env_services:
            enabled = [s.strip() for s in env_services.split(",") if s.strip()]
        else:
            enabled = list(ALL_SERVICES)

    # Normalise to set for internal use, regardless of caller type.
    enabled_set = set(enabled)
    unknown = enabled_set - set(ALL_SERVICES)
    if unknown:
        raise ValueError(
            f"Unknown services: {unknown}. Valid: {sorted(ALL_SERVICES)}"
        )

    log.info("starting %s services=%s config=%s", SERVER_NAME, sorted(enabled_set), settings.masked())

    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8000"))

    # Build instructions dynamically based on enabled services.
    instructions_parts: list[str] = []
    if "ecs" in enabled:
        instructions_parts.append(
            "ECS: list/inspect servers, power actions (start/stop/reboot), "
            "delete, resize, poll async jobs. Destructive ops use two-phase "
            "commit — first call returns preview + approval_id; call "
            "ecs_confirm_destructive(approval_id) only after explicit user approval."
        )
    if "pipeline" in enabled:
        instructions_parts.append(
            "CodeArts Pipeline: list/get pipelines, run, enable/disable, "
            "update config. Destructive ops (disable, update) use two-phase "
            "commit — call pipeline_confirm_destructive(approval_id) only "
            "after explicit user approval."
        )
    if "cts" in enabled:
        instructions_parts.append(
            "CTS: search audit traces and get trace detail. Read-only. "
            "Only the last 7 days are queryable. Sensitive values are masked."
        )
    if "cce" in enabled:
        instructions_parts.append(
            "CCE: query clusters / nodes / node pools (list when id is empty, "
            "detail when id is set), inspect async jobs, scale a node pool's "
            "initialNodeCount (scale-down uses two-phase commit), and download "
            "a cluster kubeconfig. Treat kubeconfig output as a secret."
        )
    if "lts" in enabled:
        instructions_parts.append(
            "LTS (Log Tank Service): search/inspect logs and triage alarms. "
            "Discovery flow — first call lts_query_log_resources(log_group_id=None) "
            "to enumerate log groups, then lts_query_log_resources(log_group_id=...) "
            "to list streams under a group, then lts_search_logs(...) with the "
            "(group_id, stream_id) pair. Use lts_get_log_context to fetch N lines "
            "around a specific line_num for causal-chain analysis, and "
            "lts_query_histogram for time-bucketed counts when triaging spikes. "
            "lts_query_alarm_rules dispatches list-vs-detail like the discovery "
            "tool; lts_list_alarm_history returns recent triggered alarm events. "
            "Read-only — no destructive ops exposed."
        )
    if "ces" in enabled:
        instructions_parts.append(
            "CES (Cloud Eye Service): monitor metrics, alarm rules, and events. "
            "Discovery flow — call ces_list_metrics(namespace='SYS.ECS') to find "
            "available metric names, then ces_get_metric_data(metrics=[...]) to "
            "query time-series data (accepts multiple metrics in one call). "
            "ces_query_alarm_rules dispatches list-vs-detail: omit alarm_id to "
            "list rules, set alarm_id to get detail (policies + resources). "
            "ces_list_alarm_histories returns alarm firing records. "
            "ces_query_resource_groups dispatches list-vs-detail: omit group_id "
            "to list groups, set group_id to get detail with resources. "
            "ces_list_event_data dispatches list-vs-detail: omit event_name to "
            "list events, set event_name to get detail. "
            "Read-only — no destructive ops exposed."
        )
    if "vpc" in enabled:
        instructions_parts.append(
            "VPC (Virtual Private Cloud): manage security groups, VPCs, subnets, "
            "EIPs, route tables, VPC peerings, and flow logs. "
            "vpc_query_security_groups dispatches list-vs-detail: omit "
            "security_group_id to list groups, set it to get one group's full "
            "rule list. vpc_add_security_group_rule opens a port; "
            "vpc_remove_security_group_rule is DESTRUCTIVE (two-phase commit — "
            "call vpc_confirm_destructive(approval_id) after user approval). "
            "vpc_check_port_reachability tests whether a protocol/port is allowed. "
            "vpc_audit_security_group flags high-risk rules (0.0.0.0/0 on SSH/RDP/etc). "
            "vpc_list_sg_associated_instances finds ECS servers using a SG. "
            "vpc_create_security_group creates a new SG, optionally cloning all "
            "rules from an existing one (pass source_security_group_id). "
            "vpc_describe_vpcs / vpc_describe_subnets / vpc_describe_vpc_peerings / "
            "vpc_describe_route_tables / vpc_describe_eips / vpc_list_flow_logs all "
            "dispatch list-vs-detail: omit the id param to list, set it to get detail. "
            "vpc_associate_eip binds an EIP to a port (ECS NIC / NAT / ELB). "
            "vpc_disassociate_eip is DESTRUCTIVE (two-phase, requires confirm=True). "
            "vpc_add_route adds a route entry to a route table. "
            "vpc_delete_route is DESTRUCTIVE (two-phase commit). "
            "vpc_query_flow_log_data queries actual flow log records from LTS — "
            "use action='reject' to find denied traffic."
        )
    if "rds" in enabled:
        instructions_parts.append(
            "RDS (Relational Database Service): inspect instances, query logs, "
            "audit security, and create backups. "
            "rds_describe_instances dispatches list-vs-detail: omit instance_id "
            "to list instances, set it to get full detail (nodes, volume, backup "
            "strategy, connection addresses, storage usage). "
            "rds_get_db_logs queries error logs (log_type='error') or slow query "
            "statistics (log_type='slow') — slow logs return aggregated SQL-pattern "
            "data (sql_text, avg_duration_ms, execution_count, lock_time_ms) for "
            "AI-driven index optimization. Use sort_by='count' for high-frequency "
            "slow SQL, sort_by='duration' for slowest queries. "
            "rds_list_db_resources lists databases (resource_type='databases') or "
            "DB accounts with privileges (resource_type='accounts'). "
            "rds_list_backups queries auto/manual backups. "
            "rds_get_instance_metrics queries CES monitoring metrics (CPU, memory, "
            "IOPS, connections, disk) — cross-correlate with slow logs to find "
            "performance bottlenecks. "
            "rds_describe_parameter_group lists parameter groups, shows one group's "
            "params (config_id), or shows params applied to a specific instance "
            "(instance_id). "
            "rds_list_replicas shows read-only replicas and replication delay. "
            "rds_create_manual_backup is a TWO-PHASE operation — call "
            "rds_confirm_destructive(approval_id) after user approval. "
            "rds_audit_instance_security checks for public IP exposure, root remote "
            "access, storage near-full, missing backups, SSL disabled, and no replica."
        )
    if "obs" in enabled:
        instructions_parts.append(
            "OBS (Object Storage Service): manage buckets and objects. "
            "obs_describe_buckets dispatches list-vs-detail: omit bucket_name "
            "to list all buckets, set it to get full detail (metadata, versioning, "
            "ACL, public status). obs_list_objects lists objects with optional "
            "prefix/delimiter/pagination; set include_versions=True to list all "
            "historical versions. obs_get_object dispatches metadata-vs-content: "
            "include_content=False (default) for HEAD metadata only, True to "
            "download text content (size-limited to 1 MB). "
            "obs_generate_presigned_url creates time-limited download/upload "
            "URLs — the safest way to share files without exposing credentials. "
            "obs_upload_object writes text/small files (configs, JSON reports). "
            "obs_delete_object is DESTRUCTIVE (two-phase commit — call "
            "obs_confirm_destructive(approval_id) after user approval). "
            "obs_create_bucket creates a new bucket (defaults to private ACL). "
            "obs_describe_bucket_policy returns ACL grants and public status. "
            "obs_describe_bucket_lifecycle queries lifecycle rules (may use "
            "raw HTTP if SDK lacks lifecycle API). "
            "obs_set_bucket_policy is DESTRUCTIVE (two-phase commit). "
            "obs_audit_bucket_security checks for public ACL, no encryption, "
            "no versioning, and missing public access block — use for batch "
            "security audits across all buckets."
        )

    mcp = FastMCP(
        SERVER_NAME,
        instructions="\n\n".join(instructions_parts),
        host=host,
        port=port,
    )

    tools: dict = {}

    if "ecs" in enabled:
        from .services.ecs.make_tools import make_tools as _ecs_tools
        tools.update(_ecs_tools(settings))

    if "pipeline" in enabled:
        from .services.pipeline.make_tools import make_tools as _pipeline_tools
        tools.update(_pipeline_tools(settings))

    if "cts" in enabled:
        from .services.cts.make_tools import make_tools as _cts_tools
        tools.update(_cts_tools(settings))

    if "cce" in enabled:
        from .services.cce.make_tools import make_tools as _cce_tools
        tools.update(_cce_tools(settings))

    if "lts" in enabled:
        from .services.lts.make_tools import make_tools as _lts_tools
        tools.update(_lts_tools(settings))

    if "ces" in enabled:
        from .services.ces.make_tools import make_tools as _ces_tools
        tools.update(_ces_tools(settings))

    if "vpc" in enabled:
        from .services.vpc.make_tools import make_tools as _vpc_tools
        tools.update(_vpc_tools(settings))

    if "rds" in enabled:
        from .services.rds.make_tools import make_tools as _rds_tools
        tools.update(_rds_tools(settings))

    if "obs" in enabled:
        from .services.obs.make_tools import make_tools as _obs_tools
        tools.update(_obs_tools(settings))

    # Resolve include/exclude: explicit kwargs win, otherwise fall back to env.
    include_patterns = _normalise_patterns(include)
    if not include_patterns:
        include_patterns = _split_csv(os.environ.get("MCP_INCLUDE_TOOLS"))
    exclude_patterns = _normalise_patterns(exclude)
    if not exclude_patterns:
        exclude_patterns = _split_csv(os.environ.get("MCP_EXCLUDE_TOOLS"))

    tools = _filter_tools(tools, include_patterns, exclude_patterns, log=log)

    for name, fn in tools.items():
        mcp.add_tool(fn, name=name)

    log.info("registered %d tools: %s", len(tools), sorted(tools.keys()))
    return mcp


def main() -> None:
    """CLI entrypoint. Selects transport from MCP_TRANSPORT env var."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport not in VALID_TRANSPORTS:
        sys.stderr.write(
            f"ERROR: invalid MCP_TRANSPORT={transport!r}. "
            f"Valid: {', '.join(VALID_TRANSPORTS)}\n"
        )
        sys.exit(2)

    try:
        server = build_server()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        logging.exception("fatal error during server startup")
        sys.exit(1)

    server.run(transport=transport)


if __name__ == "__main__":
    main()
