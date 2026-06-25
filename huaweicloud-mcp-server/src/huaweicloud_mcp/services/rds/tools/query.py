"""RDS query tools — read-only operations.

Tools:
  * rds_describe_instances — list/get instances (list-vs-detail dispatch)
  * rds_list_db_resources — merged databases + accounts (resource_type dispatch)
  * rds_list_backups — backup list with filters
  * rds_describe_parameter_group — parameter group list/show/show-instance
  * rds_list_replicas — read-only replicas + replication delay
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkrds.v3 import (
    ListBackupsRequest,
    ListConfigurationsRequest,
    ListDatabasesRequest,
    ListDbUsersRequest,
    ListInstancesRequest,
    ShowConfigurationRequest,
    ShowInstanceConfigurationRequest,
    ShowReplicationStatusRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import (
    DescribeInstancesInput,
    DescribeParameterGroupInput,
    ListBackupsInput,
    ListDbResourcesInput,
    ListReplicasInput,
)
from ..serializers import (
    backup_summary,
    configuration_detail,
    configuration_summary,
    database_summary,
    db_user_summary,
    instance_detail,
    instance_summary,
    replication_status_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.rds.tools.query")


def make_query_tools(settings: Settings) -> dict:
    """Build RDS read-only query tools bound to *settings*."""
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # describe_instances
    # ------------------------------------------------------------------ #
    @wrap_tool
    def rds_describe_instances(
        instance_id: Optional[str] = None,
        name: Optional[str] = None,
        datastore_type: Optional[str] = None,
        status: Optional[str] = None,
        vpc_id: Optional[str] = None,
        subnet_id: Optional[str] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """List or get detail of RDS instances.

        Dispatches based on instance_id:
          * instance_id is None/empty → LIST mode (returns all instances
            matching the filters).
          * instance_id is set → DETAIL mode (returns full info for that
            single instance: nodes, volume, backup strategy, related
            instances, SSL, connection addresses, storage usage).

        Args:
            instance_id: Instance UUID. Omit to list, set to get detail.
            name: List-mode filter: instance name (fuzzy).
            datastore_type: List-mode filter: engine (MySQL/PostgreSQL/SQLServer).
            status: List-mode filter: instance status.
            vpc_id: List-mode filter: VPC id.
            subnet_id: List-mode filter: subnet id.
            offset: Page offset.
            limit: Page size (1..100).

        Returns:
            LIST:  {"instances": [...], "total_count": N}
            DETAIL: {"instance": {...full detail...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeInstancesInput(
            instance_id=instance_id,
            name=name,
            datastore_type=datastore_type,
            status=status,
            vpc_id=vpc_id,
            subnet_id=subnet_id,
            offset=offset,
            limit=limit,
        )
        client = get_client("rds", settings)

        req = ListInstancesRequest(
            id=params.instance_id or None,
            name=params.name,
            datastore_type=params.datastore_type,
            vpc_id=params.vpc_id,
            subnet_id=params.subnet_id,
            offset=params.offset,
            limit=params.limit,
        )
        resp = client.list_instances(req)
        instances = list(getattr(resp, "instances", None) or [])

        # Detail mode: return the first (should be only) instance fully.
        if params.instance_id:
            if not instances:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"RDS instance {params.instance_id!r} not found.",
                )
            return {"instance": instance_detail(instances[0])}

        # List mode: return summaries.
        out = [instance_summary(i) for i in instances]
        return {"instances": out, "total_count": getattr(resp, "total_count", len(out))}

    # ------------------------------------------------------------------ #
    # list_db_resources (merged: databases + accounts)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def rds_list_db_resources(
        instance_id: str,
        resource_type: str,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """List databases or DB accounts under an RDS instance.

        Dispatches based on resource_type:
          * 'databases' → list all databases (name, character_set, comment).
          * 'accounts'  → list all DB accounts and their privileges
                           (name, hosts, databases with readonly flag, comment).

        Args:
            instance_id: RDS instance UUID.
            resource_type: 'databases' or 'accounts'.
            page: Page number (1-based).
            limit: Page size (1..100).

        Returns:
            databases: {"databases": [...], "total_count": N}
            accounts:  {"accounts": [...], "total_count": N}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListDbResourcesInput(
            instance_id=instance_id,
            resource_type=resource_type,
            page=page,
            limit=limit,
        )
        client = get_client("rds", settings)

        if params.resource_type == "databases":
            req = ListDatabasesRequest(
                instance_id=params.instance_id,
                page=params.page or 1,
                limit=params.limit,
            )
            resp = client.list_databases(req)
            dbs = list(getattr(resp, "databases", None) or [])
            out = [database_summary(d) for d in dbs]
            return {"databases": out, "total_count": getattr(resp, "total_count", len(out))}

        # accounts
        req = ListDbUsersRequest(
            instance_id=params.instance_id,
            page=params.page or 1,
            limit=params.limit,
        )
        resp = client.list_db_users(req)
        users = list(getattr(resp, "users", None) or [])
        out = [db_user_summary(u) for u in users]
        return {"accounts": out, "total_count": getattr(resp, "total_count", len(out))}

    # ------------------------------------------------------------------ #
    # list_backups
    # ------------------------------------------------------------------ #
    @wrap_tool
    def rds_list_backups(
        instance_id: Optional[str] = None,
        backup_id: Optional[str] = None,
        backup_type: Optional[str] = None,
        status: Optional[str] = None,
        begin_time: Optional[str] = None,
        end_time: Optional[str] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """List RDS backups (auto + manual) with optional filters.

        Args:
            instance_id: Filter by instance id.
            backup_id: Get a specific backup by id.
            backup_type: 'auto' or 'manual'.
            status: Filter by status (BUILDING, COMPLETED, FAILED, etc.).
            begin_time: Backups started after this time.
            end_time: Backups started before this time.
            offset: Page offset.
            limit: Page size (1..100).

        Returns:
            {"backups": [...], "total_count": N}
            Each backup: {id, instance_id, name, type, status, size_kb, begin_time, end_time}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListBackupsInput(
            instance_id=instance_id,
            backup_id=backup_id,
            backup_type=backup_type,
            status=status,
            begin_time=begin_time,
            end_time=end_time,
            offset=offset,
            limit=limit,
        )
        client = get_client("rds", settings)

        req = ListBackupsRequest(
            instance_id=params.instance_id,
            backup_id=params.backup_id,
            backup_type=params.backup_type,
            status=params.status,
            begin_time=params.begin_time,
            end_time=params.end_time,
            offset=params.offset,
            limit=params.limit,
        )
        resp = client.list_backups(req)
        backups = list(getattr(resp, "backups", None) or [])
        out = [backup_summary(b) for b in backups]
        return {"backups": out, "total_count": getattr(resp, "total_count", len(out))}

    # ------------------------------------------------------------------ #
    # describe_parameter_group
    # ------------------------------------------------------------------ #
    @wrap_tool
    def rds_describe_parameter_group(
        config_id: Optional[str] = None,
        instance_id: Optional[str] = None,
    ) -> dict:
        """List parameter groups, show one group's params, or show an instance's applied params.

        Dispatches based on parameters:
          * instance_id is set → show the parameter configuration currently
            applied to that specific instance.
          * config_id is set → show that parameter group's full parameter list.
          * both are None/empty → list all parameter groups.

        Args:
            config_id: Parameter group (configuration) id.
            instance_id: RDS instance id — shows applied params for this instance.

        Returns:
            INSTANCE: {"instance_id": ..., "datastore": ..., "parameters": [...]}
            CONFIG:   {"configuration": {id, name, ..., "parameters": [...]}}
            LIST:     {"configurations": [...], "total_count": N}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeParameterGroupInput(
            config_id=config_id,
            instance_id=instance_id,
        )
        client = get_client("rds", settings)

        # Instance-specific configuration takes precedence.
        if params.instance_id:
            req = ShowInstanceConfigurationRequest(
                instance_id=params.instance_id,
            )
            resp = client.show_instance_configuration(req)
            param_list = list(getattr(resp, "configuration_parameters", None) or [])
            from ..serializers import configuration_parameter_summary
            return {
                "instance_id": params.instance_id,
                "datastore_name": getattr(resp, "datastore_name", None),
                "datastore_version_name": getattr(resp, "datastore_version_name", None),
                "updated": getattr(resp, "updated", None),
                "parameters": [configuration_parameter_summary(p) for p in param_list],
            }

        # Single config detail.
        if params.config_id:
            req = ShowConfigurationRequest(config_id=params.config_id)
            resp = client.show_configuration(req)
            return {"configuration": configuration_detail(resp)}

        # List all configs.
        resp = client.list_configurations(ListConfigurationsRequest())
        configs = list(getattr(resp, "configurations", None) or [])
        out = [configuration_summary(c) for c in configs]
        return {"configurations": out, "total_count": len(out)}

    # ------------------------------------------------------------------ #
    # list_replicas
    # ------------------------------------------------------------------ #
    @wrap_tool
    def rds_list_replicas(instance_id: str) -> dict:
        """List read-only replicas of a primary RDS instance and their replication delay.

        Combines instance detail (to find related replica instances) with
        replication status (to report delay/abnormalities).

        Args:
            instance_id: Primary instance UUID.

        Returns:
            {"primary_id": ..., "replicas": [...], "replication_status": {...}}
            Each replica: {id, name, status, role, ...}
            replication_status: {replication_status, abnormal_reason}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListReplicasInput(instance_id=instance_id)
        client = get_client("rds", settings)

        # Get instance detail to find related replicas.
        inst_resp = client.list_instances(
            ListInstancesRequest(id=params.instance_id)
        )
        instances = list(getattr(inst_resp, "instances", None) or [])
        if not instances:
            raise ToolError(
                code="NOT_FOUND",
                message=f"RDS instance {params.instance_id!r} not found.",
            )
        inst = instances[0]
        related = list(getattr(inst, "related_instance", None) or [])
        replicas = [
            {
                "id": getattr(ri, "id", None),
                "type": getattr(ri, "type", None),
            }
            for ri in related
            if getattr(ri, "type", None) == "replica"
        ]

        # Fetch each replica's detail.
        replica_details = []
        for r in replicas:
            r_resp = client.list_instances(ListInstancesRequest(id=r["id"]))
            r_insts = list(getattr(r_resp, "instances", None) or [])
            if r_insts:
                replica_details.append(instance_summary(r_insts[0]))

        # Replication status.
        repl_resp = client.show_replication_status(
            ShowReplicationStatusRequest(instance_id=params.instance_id)
        )
        repl_status = replication_status_summary(repl_resp)

        return {
            "primary_id": params.instance_id,
            "replicas": replica_details,
            "replica_count": len(replica_details),
            "replication_status": repl_status,
        }

    return {
        "rds_describe_instances": rds_describe_instances,
        "rds_list_db_resources": rds_list_db_resources,
        "rds_list_backups": rds_list_backups,
        "rds_describe_parameter_group": rds_describe_parameter_group,
        "rds_list_replicas": rds_list_replicas,
    }
