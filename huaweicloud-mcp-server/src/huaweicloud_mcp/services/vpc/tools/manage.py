"""VPC security-group write tools: create/clone, add/remove rules.

remove_security_group_rule is DESTRUCTIVE and uses two-phase commit:
  Phase 1: call → returns preview + approval_id (no execution)
  Phase 2: user approves → call vpc_confirm_destructive(approval_id)
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkvpc.v2 import (
    CreateSecurityGroupOption,
    CreateSecurityGroupRequest,
    CreateSecurityGroupRequestBody,
    CreateSecurityGroupRuleOption,
    CreateSecurityGroupRuleRequest,
    CreateSecurityGroupRuleRequestBody,
    DeleteSecurityGroupRuleRequest,
    ShowSecurityGroupRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, pending_actions, wrap_tool
from ..models import (
    AddSecurityGroupRuleInput,
    ConfirmDestructiveInput,
    CreateSecurityGroupInput,
    RemoveSecurityGroupRuleInput,
)
from ..serializers import rule_summary, security_group_detail

log = logging.getLogger("huaweicloud_mcp.services.vpc.tools.manage")


def make_manage_tools(settings: Settings) -> dict:
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # create_security_group  (merged: create + clone)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_create_security_group(
        name: str,
        source_security_group_id: Optional[str] = None,
        vpc_id: Optional[str] = None,
        enterprise_project_id: Optional[str] = None,
    ) -> dict:
        """Create a new security group, optionally cloning rules from an existing one.

        Dispatches based on ``source_security_group_id``:

          * ``source_security_group_id`` is None/empty → PLAIN CREATE.
            Creates a new SG with default rules (allow-all egress).
          * ``source_security_group_id`` is set → CLONE mode.
            Reads the source SG's rules, creates a new SG, then copies each
            rule. ``vpc_id`` defaults to the source SG's VPC if not specified.

        Args:
            name: Name for the new security group.
            source_security_group_id: If set, clone all rules from this SG.
            vpc_id: VPC id. If omitted, uses default VPC (or source's VPC when cloning).
            enterprise_project_id: Enterprise project id for the new SG.

        Returns:
            PLAIN:  {id, name, vpc_id, security_group_rules: [...]}
            CLONE:  {id, name, vpc_id, cloned_rules_count, security_group_rules: [...]}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = CreateSecurityGroupInput(
            name=name,
            source_security_group_id=source_security_group_id,
            vpc_id=vpc_id,
            enterprise_project_id=enterprise_project_id,
        )
        client = get_client("vpc", settings)

        # ---- CLONE mode: read source first ----
        src_rules = []
        if params.source_security_group_id:
            src_resp = client.show_security_group(
                ShowSecurityGroupRequest(
                    security_group_id=params.source_security_group_id,
                )
            )
            if src_resp.security_group is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=(
                        f"source security group "
                        f"{params.source_security_group_id} not found"
                    ),
                )
            src_sg = src_resp.security_group
            src_rules = getattr(src_sg, "security_group_rules", None) or []
            # Inherit source VPC if not explicitly specified.
            if not params.vpc_id:
                params = params.model_copy(
                    update={"vpc_id": getattr(src_sg, "vpc_id", None)}
                )

        # ---- Create the new SG ----
        opt = CreateSecurityGroupOption(
            name=params.name,
            vpc_id=params.vpc_id,
            enterprise_project_id=params.enterprise_project_id,
        )
        create_resp = client.create_security_group(
            CreateSecurityGroupRequest(
                body=CreateSecurityGroupRequestBody(security_group=opt)
            )
        )
        new_sg = create_resp.security_group
        new_sg_id = getattr(new_sg, "id", None)

        # ---- CLONE mode: copy each rule ----
        cloned = 0
        if src_rules:
            for rule in src_rules:
                rule_opt = CreateSecurityGroupRuleOption(
                    security_group_id=new_sg_id,
                    direction=getattr(rule, "direction", None),
                    ethertype=getattr(rule, "ethertype", None) or "IPv4",
                    protocol=getattr(rule, "protocol", None),
                    port_range_min=getattr(rule, "port_range_min", None),
                    port_range_max=getattr(rule, "port_range_max", None),
                    remote_ip_prefix=getattr(rule, "remote_ip_prefix", None),
                    remote_group_id=getattr(rule, "remote_group_id", None),
                    remote_address_group_id=getattr(rule, "remote_address_group_id", None),
                    description=getattr(rule, "description", None),
                )
                try:
                    client.create_security_group_rule(
                        CreateSecurityGroupRuleRequest(
                            body=CreateSecurityGroupRuleRequestBody(
                                security_group_rule=rule_opt
                            )
                        )
                    )
                    cloned += 1
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "clone: failed to copy rule %s: %s",
                        getattr(rule, "id", "?"), exc,
                    )

        # ---- Re-fetch to get the final rule set ----
        final_resp = client.show_security_group(
            ShowSecurityGroupRequest(security_group_id=new_sg_id)
        )
        result = security_group_detail(final_resp.security_group)
        if src_rules:
            result["cloned_rules_count"] = cloned
        return result

    # ------------------------------------------------------------------ #
    # add_security_group_rule
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_add_security_group_rule(
        security_group_id: str,
        direction: str,
        protocol: str,
        port_range_min: Optional[int] = None,
        port_range_max: Optional[int] = None,
        remote_ip_prefix: Optional[str] = None,
        remote_group_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Add a single ingress or egress rule to a security group.

        For tcp/udp, set port_range_min and port_range_max (use the same
        value for a single port). For icmp, omit port ranges. Specify
        either remote_ip_prefix (CIDR) or remote_group_id (another SG),
        not both. If neither is set, defaults to 0.0.0.0/0.

        Args:
            security_group_id: Target security group UUID.
            direction: 'ingress' or 'egress'.
            protocol: 'tcp', 'udp', 'icmp', or 'any'.
            port_range_min: Minimum port (inclusive).
            port_range_max: Maximum port (inclusive).
            remote_ip_prefix: Source/destination CIDR (e.g. '0.0.0.0/0').
            remote_group_id: Source/destination SG id.
            description: Human-readable rule description.

        Returns:
            The created rule: {id, direction, protocol, port_range_min, ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = AddSecurityGroupRuleInput(
            security_group_id=security_group_id,
            direction=direction,
            protocol=protocol,
            port_range_min=port_range_min,
            port_range_max=port_range_max,
            remote_ip_prefix=remote_ip_prefix,
            remote_group_id=remote_group_id,
            description=description,
        )

        if params.remote_ip_prefix and params.remote_group_id:
            raise ToolError(
                code="CONFLICTING_PARAMS",
                message="remote_ip_prefix and remote_group_id are mutually exclusive.",
            )

        # Default to open-to-all if neither source is specified.
        if not params.remote_ip_prefix and not params.remote_group_id:
            params = params.model_copy(update={"remote_ip_prefix": "0.0.0.0/0"})

        # Normalise protocol: 'any' → None for the SDK.
        sdk_protocol = None if params.protocol == "any" else params.protocol

        client = get_client("vpc", settings)
        opt = CreateSecurityGroupRuleOption(
            security_group_id=params.security_group_id,
            direction=params.direction,
            ethertype="IPv4",
            protocol=sdk_protocol,
            port_range_min=params.port_range_min,
            port_range_max=params.port_range_max,
            remote_ip_prefix=params.remote_ip_prefix,
            remote_group_id=params.remote_group_id,
            description=params.description,
        )
        resp = client.create_security_group_rule(
            CreateSecurityGroupRuleRequest(
                body=CreateSecurityGroupRuleRequestBody(security_group_rule=opt)
            )
        )
        return rule_summary(resp.security_group_rule)

    # ------------------------------------------------------------------ #
    # remove_security_group_rule  (DESTRUCTIVE — two-phase)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_remove_security_group_rule(security_group_rule_id: str) -> dict:
        """⚠ DESTRUCTIVE: delete a security group rule.

        This is a TWO-PHASE operation: returns a preview + approval_id.
        Use vpc_confirm_destructive to execute after user approval.

        Args:
            security_group_rule_id: Rule UUID to delete.

        Returns:
            {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "admin")

        params = RemoveSecurityGroupRuleInput(
            security_group_rule_id=security_group_rule_id,
        )
        client = get_client("vpc", settings)

        action_label = f"vpc_remove_security_group_rule(rule_id={params.security_group_rule_id})"

        def _execute() -> dict:
            client.delete_security_group_rule(
                DeleteSecurityGroupRuleRequest(
                    security_group_rule_id=params.security_group_rule_id,
                )
            )
            return {"deleted": True, "rule_id": params.security_group_rule_id}

        approval_id = pending_actions.put(
            action_label=action_label,
            preview={
                "action": "remove_rule",
                "security_group_rule_id": params.security_group_rule_id,
            },
            execute_fn=_execute,
        )
        return {
            "status": "pending_approval",
            "approval_id": approval_id,
            "action": "remove_rule",
            "security_group_rule_id": params.security_group_rule_id,
            "message": (
                f"⚠ Rule deletion is irreversible. Present this preview to the user "
                f"and ask for explicit approval. If approved, call "
                f"vpc_confirm_destructive(approval_id='{approval_id}')."
            ),
        }

    # ------------------------------------------------------------------ #
    # confirm_destructive
    # ------------------------------------------------------------------ #
    @wrap_tool
    def vpc_confirm_destructive(approval_id: str) -> dict:
        """Execute a previously requested destructive VPC operation.

        Call this ONLY after the user has explicitly approved the operation.
        Approval IDs expire after 120 seconds.

        Args:
            approval_id: The approval_id from a pending destructive operation.

        Returns:
            The result of the executed operation.
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        entry = pending_actions.pop(approval_id)
        log.info(
            "confirm_destructive approval_id=%s action=%s — executing",
            approval_id, entry["action"],
        )
        return entry["execute_fn"]()

    return {
        "vpc_create_security_group": vpc_create_security_group,
        "vpc_add_security_group_rule": vpc_add_security_group_rule,
        "vpc_remove_security_group_rule": vpc_remove_security_group_rule,
        "vpc_confirm_destructive": vpc_confirm_destructive,
    }
