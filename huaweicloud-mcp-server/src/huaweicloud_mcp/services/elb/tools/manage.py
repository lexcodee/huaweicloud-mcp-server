"""ELB management tools — write operations with two-phase commit.

Merged tools (action dispatch):
  * elb_manage_backend_member  — add / remove / update_weight
  * elb_manage_listener        — create / update / replace_certificate
  * elb_manage_forwarding_rule — create / delete

Standalone:
  * elb_set_connection_drain   — enable/disable graceful member removal on a pool
  * elb_confirm_destructive    — two-phase commit for all destructive ops

Destructive operations (remove member, create listener, delete forwarding rule)
use two-phase commit:
  Phase 1: call → returns preview + approval_id (no execution)
  Phase 2: user approves → call elb_confirm_destructive(approval_id)
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkelb.v3 import (
    ConnectionDrain,
    CreateL7PolicyOption,
    CreateL7PolicyRequest,
    CreateL7PolicyRequestBody,
    CreateListenerOption,
    CreateListenerRequest,
    CreateListenerRequestBody,
    CreateMemberOption,
    CreateMemberRequest,
    CreateMemberRequestBody,
    CreateRuleOption,
    CreateL7RuleRequest,
    CreateL7RuleRequestBody,
    DeleteL7PolicyRequest,
    DeleteMemberRequest,
    UpdateListenerOption,
    UpdateListenerRequest,
    UpdateListenerRequestBody,
    UpdateMemberOption,
    UpdateMemberRequest,
    UpdateMemberRequestBody,
    UpdatePoolOption,
    UpdatePoolRequest,
    UpdatePoolRequestBody,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, pending_actions, wrap_tool
from ..models import (
    ConfirmDestructiveInput,
    ManageBackendMemberInput,
    ManageForwardingRuleInput,
    ManageListenerInput,
    SetConnectionDrainInput,
)
from ..serializers import l7_policy_summary, listener_summary, member_summary

log = logging.getLogger("huaweicloud_mcp.services.elb.tools.manage")


def make_manage_tools(settings: Settings) -> dict:
    """Build ELB management tools bound to *settings*."""
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # manage_backend_member (merged: add / remove / update_weight)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_manage_backend_member(
        action: str,
        pool_id: str,
        member_id: Optional[str] = None,
        address: Optional[str] = None,
        protocol_port: Optional[int] = None,
        weight: Optional[int] = None,
        subnet_cidr_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict:
        """Manage backend server members in a pool.

        Dispatches based on action:
          * 'add'           → add a new backend server (address, port, weight).
          * 'remove'        → delete a member (DESTRUCTIVE — two-phase commit).
          * 'update_weight' → change a member's traffic weight (0 = drain, 100 = full).

        Args:
            action: 'add', 'remove', or 'update_weight'.
            pool_id: Backend server group (pool) id.
            member_id: Member id. Required for 'remove' and 'update_weight'.
            address: Backend server IP. Required for 'add'.
            protocol_port: Backend server port. Required for 'add'.
            weight: Traffic weight (0..100). For 'add' (default 100) and 'update_weight'.
            subnet_cidr_id: Subnet id. Optional for 'add'.
            name: Member name. Optional for 'add'.

        Returns:
            add:           {"member": {...}}
            update_weight: {"member": {...}}
            remove:        {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = ManageBackendMemberInput(
            action=action,
            pool_id=pool_id,
            member_id=member_id,
            address=address,
            protocol_port=protocol_port,
            weight=weight,
            subnet_cidr_id=subnet_cidr_id,
            name=name,
        )
        client = get_client("elb", settings)

        # ---- add ----
        if params.action == "add":
            if not params.address or params.protocol_port is None:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'add' requires address and protocol_port.",
                )
            opt = CreateMemberOption(
                address=params.address,
                protocol_port=params.protocol_port,
                weight=params.weight if params.weight is not None else 100,
                subnet_cidr_id=params.subnet_cidr_id,
                name=params.name,
            )
            resp = client.create_member(
                CreateMemberRequest(
                    pool_id=params.pool_id,
                    body=CreateMemberRequestBody(member=opt),
                )
            )
            return {"member": member_summary(getattr(resp, "member", None))}

        # ---- update_weight ----
        if params.action == "update_weight":
            if not params.member_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'update_weight' requires member_id.",
                )
            if params.weight is None:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'update_weight' requires weight.",
                )
            opt = UpdateMemberOption(weight=params.weight)
            resp = client.update_member(
                UpdateMemberRequest(
                    pool_id=params.pool_id,
                    member_id=params.member_id,
                    body=UpdateMemberRequestBody(member=opt),
                )
            )
            return {"member": member_summary(getattr(resp, "member", None))}

        # ---- remove (DESTRUCTIVE — two-phase) ----
        if params.action == "remove":
            if not params.member_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'remove' requires member_id.",
                )
            action_label = (
                f"elb_manage_backend_member(remove, pool_id={params.pool_id}, "
                f"member_id={params.member_id})"
            )

            def _execute() -> dict:
                client.delete_member(
                    DeleteMemberRequest(
                        pool_id=params.pool_id,
                        member_id=params.member_id,
                    )
                )
                return {"deleted": True, "pool_id": params.pool_id, "member_id": params.member_id}

            approval_id = pending_actions.put(
                action_label=action_label,
                preview={
                    "action": "remove_backend_member",
                    "pool_id": params.pool_id,
                    "member_id": params.member_id,
                },
                execute_fn=_execute,
            )
            return {
                "status": "pending_approval",
                "approval_id": approval_id,
                "action": "remove_backend_member",
                "pool_id": params.pool_id,
                "member_id": params.member_id,
                "message": (
                    f"⚠ Member removal is irreversible. Present this preview to "
                    f"the user and ask for explicit approval. If approved, call "
                    f"elb_confirm_destructive(approval_id='{approval_id}')."
                ),
            }

        raise ToolError(
            code="INVALID_ACTION",
            message=f"Unknown action {params.action!r}. Use 'add', 'remove', or 'update_weight'.",
        )

    # ------------------------------------------------------------------ #
    # manage_listener (merged: create / update / replace_certificate)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_manage_listener(
        action: str,
        listener_id: Optional[str] = None,
        loadbalancer_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        protocol: Optional[str] = None,
        protocol_port: Optional[int] = None,
        default_pool_id: Optional[str] = None,
        certificate_id: Optional[str] = None,
        http2_enable: Optional[bool] = None,
        keepalive_timeout: Optional[int] = None,
        client_timeout: Optional[int] = None,
        member_timeout: Optional[int] = None,
        tls_ciphers_policy: Optional[str] = None,
        admin_state_up: Optional[bool] = None,
    ) -> dict:
        """Manage ELB listeners.

        Dispatches based on action:
          * 'create'             → create a new listener (DESTRUCTIVE — two-phase).
          * 'update'             → modify listener config (timeouts, HTTP2, TLS, etc.).
          * 'replace_certificate' → swap the SSL certificate bound to the listener.

        Args:
            action: 'create', 'update', or 'replace_certificate'.
            listener_id: Listener id. Required for 'update' and 'replace_certificate'.
            loadbalancer_id: LB id. Required for 'create'.
            name: Listener name.
            description: Listener description.
            protocol: Protocol (TCP, UDP, HTTP, HTTPS, TERMINATED_HTTPS). Required for 'create'.
            protocol_port: Listening port. Required for 'create'.
            default_pool_id: Default backend server group id.
            certificate_id: SSL certificate id. For 'create' sets default cert;
                for 'replace_certificate' is the new cert to bind.
            http2_enable: Enable HTTP/2 (HTTPS only).
            keepalive_timeout: Keep-alive timeout (seconds).
            client_timeout: Client timeout (seconds).
            member_timeout: Backend timeout (seconds).
            tls_ciphers_policy: TLS ciphers policy name.
            admin_state_up: Administrative state (enabled/disabled).

        Returns:
            update:             {"listener": {...}}
            replace_certificate: {"listener": {...}}
            create:             {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = ManageListenerInput(
            action=action,
            listener_id=listener_id,
            loadbalancer_id=loadbalancer_id,
            name=name,
            description=description,
            protocol=protocol,
            protocol_port=protocol_port,
            default_pool_id=default_pool_id,
            certificate_id=certificate_id,
            http2_enable=http2_enable,
            keepalive_timeout=keepalive_timeout,
            client_timeout=client_timeout,
            member_timeout=member_timeout,
            tls_ciphers_policy=tls_ciphers_policy,
            admin_state_up=admin_state_up,
        )
        client = get_client("elb", settings)

        # ---- create (DESTRUCTIVE — two-phase) ----
        if params.action == "create":
            if not params.loadbalancer_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'create' requires loadbalancer_id.",
                )
            if not params.protocol or params.protocol_port is None:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'create' requires protocol and protocol_port.",
                )
            action_label = (
                f"elb_manage_listener(create, loadbalancer_id={params.loadbalancer_id}, "
                f"protocol={params.protocol}, port={params.protocol_port}, name={params.name})"
            )

            def _execute() -> dict:
                opt = CreateListenerOption(
                    loadbalancer_id=params.loadbalancer_id,
                    protocol=params.protocol,
                    protocol_port=params.protocol_port,
                    name=params.name,
                    description=params.description,
                    default_pool_id=params.default_pool_id,
                    default_tls_container_ref=params.certificate_id,
                    http2_enable=params.http2_enable,
                    keepalive_timeout=params.keepalive_timeout,
                    client_timeout=params.client_timeout,
                    member_timeout=params.member_timeout,
                    tls_ciphers_policy=params.tls_ciphers_policy,
                    admin_state_up=params.admin_state_up if params.admin_state_up is not None else True,
                )
                resp = client.create_listener(
                    CreateListenerRequest(
                        body=CreateListenerRequestBody(listener=opt)
                    )
                )
                return {"listener": listener_summary(getattr(resp, "listener", None))}

            approval_id = pending_actions.put(
                action_label=action_label,
                preview={
                    "action": "create_listener",
                    "loadbalancer_id": params.loadbalancer_id,
                    "protocol": params.protocol,
                    "protocol_port": params.protocol_port,
                    "name": params.name,
                    "default_pool_id": params.default_pool_id,
                    "certificate_id": params.certificate_id,
                },
                execute_fn=_execute,
            )
            return {
                "status": "pending_approval",
                "approval_id": approval_id,
                "action": "create_listener",
                "loadbalancer_id": params.loadbalancer_id,
                "protocol": params.protocol,
                "protocol_port": params.protocol_port,
                "name": params.name,
                "message": (
                    f"⚠ Listener creation is a significant change. Present this "
                    f"preview to the user and ask for explicit approval. If "
                    f"approved, call "
                    f"elb_confirm_destructive(approval_id='{approval_id}')."
                ),
            }

        # ---- update ----
        if params.action == "update":
            if not params.listener_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'update' requires listener_id.",
                )
            opt = UpdateListenerOption(
                name=params.name,
                description=params.description,
                default_pool_id=params.default_pool_id,
                http2_enable=params.http2_enable,
                keepalive_timeout=params.keepalive_timeout,
                client_timeout=params.client_timeout,
                member_timeout=params.member_timeout,
                tls_ciphers_policy=params.tls_ciphers_policy,
                admin_state_up=params.admin_state_up,
            )
            resp = client.update_listener(
                UpdateListenerRequest(
                    listener_id=params.listener_id,
                    body=UpdateListenerRequestBody(listener=opt),
                )
            )
            return {"listener": listener_summary(getattr(resp, "listener", None))}

        # ---- replace_certificate ----
        if params.action == "replace_certificate":
            if not params.listener_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'replace_certificate' requires listener_id.",
                )
            if not params.certificate_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'replace_certificate' requires certificate_id.",
                )
            opt = UpdateListenerOption(
                default_tls_container_ref=params.certificate_id,
            )
            resp = client.update_listener(
                UpdateListenerRequest(
                    listener_id=params.listener_id,
                    body=UpdateListenerRequestBody(listener=opt),
                )
            )
            return {
                "listener": listener_summary(getattr(resp, "listener", None)),
                "certificate_replaced": True,
                "new_certificate_id": params.certificate_id,
            }

        raise ToolError(
            code="INVALID_ACTION",
            message=f"Unknown action {params.action!r}. Use 'create', 'update', or 'replace_certificate'.",
        )

    # ------------------------------------------------------------------ #
    # manage_forwarding_rule (merged: create / delete)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_manage_forwarding_rule(
        action: str,
        policy_id: Optional[str] = None,
        listener_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        redirect_pool_id: Optional[str] = None,
        redirect_listener_id: Optional[str] = None,
        redirect_url: Optional[str] = None,
        rule_type: Optional[str] = None,
        rule_compare_type: Optional[str] = None,
        rule_value: Optional[str] = None,
        rule_key: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> dict:
        """Manage ELB L7 forwarding rules (policies).

        Dispatches based on action:
          * 'create' → create an L7 policy with an optional L7 rule
                       (URL path, Host, Header, QueryString routing).
          * 'delete' → delete an L7 policy (DESTRUCTIVE — two-phase commit).

        Args:
            action: 'create' or 'delete'.
            policy_id: L7 policy id. Required for 'delete'.
            listener_id: Listener id. Required for 'create'.
            name: Policy name.
            description: Policy description.
            redirect_pool_id: Target backend group for REDIRECT_TO_POOL.
            redirect_listener_id: Target listener for REDIRECT_TO_LISTENER.
            redirect_url: Target URL for REDIRECT_TO_URL.
            rule_type: Rule match type (HOST_NAME, PATH, HEADER, QUERY_STRING).
            rule_compare_type: Comparison type (EQUAL_TO, STARTS_WITH, ENDS_WITH, CONTAINS, REGEX).
            rule_value: Match value (e.g. '/api', 'example.com').
            rule_key: Header name (for HEADER) or query param name.
            priority: Policy priority (lower = higher priority).

        Returns:
            create: {"policy": {...}}
            delete: {"status": "pending_approval", "approval_id": "...", ...}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = ManageForwardingRuleInput(
            action=action,
            policy_id=policy_id,
            listener_id=listener_id,
            name=name,
            description=description,
            redirect_pool_id=redirect_pool_id,
            redirect_listener_id=redirect_listener_id,
            redirect_url=redirect_url,
            rule_type=rule_type,
            rule_compare_type=rule_compare_type,
            rule_value=rule_value,
            rule_key=rule_key,
            priority=priority,
        )
        client = get_client("elb", settings)

        # ---- create ----
        if params.action == "create":
            if not params.listener_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'create' requires listener_id.",
                )
            # Determine action type from redirect targets.
            if params.redirect_pool_id:
                policy_action = "REDIRECT_TO_POOL"
            elif params.redirect_listener_id:
                policy_action = "REDIRECT_TO_LISTENER"
            elif params.redirect_url:
                policy_action = "REDIRECT_TO_URL"
            else:
                policy_action = "FIXED_RESPONSE"

            opt = CreateL7PolicyOption(
                listener_id=params.listener_id,
                name=params.name,
                description=params.description,
                action=policy_action,
                redirect_pool_id=params.redirect_pool_id,
                redirect_listener_id=params.redirect_listener_id,
                redirect_url=params.redirect_url,
                priority=params.priority,
            )
            resp = client.create_l7_policy(
                CreateL7PolicyRequest(
                    body=CreateL7PolicyRequestBody(l7policy=opt)
                )
            )
            policy = getattr(resp, "l7policy", None)
            policy_id_created = getattr(policy, "id", None)

            # Create the L7 rule if conditions are provided.
            rule_created = None
            if (
                policy_id_created
                and params.rule_type
                and params.rule_compare_type
                and params.rule_value
            ):
                try:
                    rule_opt = CreateRuleOption(
                        type=params.rule_type,
                        compare_type=params.rule_compare_type,
                        value=params.rule_value,
                        key=params.rule_key,
                    )
                    rule_resp = client.create_l7_rule(
                        CreateL7RuleRequest(
                            l7policy_id=policy_id_created,
                            body=CreateL7RuleRequestBody(rule=rule_opt),
                        )
                    )
                    rule_created = getattr(rule_resp, "rule", None)
                except Exception as exc:  # noqa: BLE001
                    log.warning("manage_forwarding_rule: create rule failed: %s", exc)

            result = {"policy": l7_policy_summary(policy)}
            if rule_created:
                from ..serializers import l7_rule_summary
                result["rule"] = l7_rule_summary(rule_created)
            return result

        # ---- delete (DESTRUCTIVE — two-phase) ----
        if params.action == "delete":
            if not params.policy_id:
                raise ToolError(
                    code="MISSING_PARAMS",
                    message="'delete' requires policy_id.",
                )
            action_label = (
                f"elb_manage_forwarding_rule(delete, policy_id={params.policy_id})"
            )

            def _execute() -> dict:
                client.delete_l7_policy(
                    DeleteL7PolicyRequest(l7policy_id=params.policy_id)
                )
                return {"deleted": True, "policy_id": params.policy_id}

            approval_id = pending_actions.put(
                action_label=action_label,
                preview={
                    "action": "delete_forwarding_rule",
                    "policy_id": params.policy_id,
                },
                execute_fn=_execute,
            )
            return {
                "status": "pending_approval",
                "approval_id": approval_id,
                "action": "delete_forwarding_rule",
                "policy_id": params.policy_id,
                "message": (
                    f"⚠ Forwarding rule deletion is irreversible. Present this "
                    f"preview to the user and ask for explicit approval. If "
                    f"approved, call "
                    f"elb_confirm_destructive(approval_id='{approval_id}')."
                ),
            }

        raise ToolError(
            code="INVALID_ACTION",
            message=f"Unknown action {params.action!r}. Use 'create' or 'delete'.",
        )

    # ------------------------------------------------------------------ #
    # set_connection_drain
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_set_connection_drain(
        pool_id: str,
        enable: bool = True,
        timeout: int = 60,
    ) -> dict:
        """Enable or disable connection drain (graceful shutdown) on a backend pool.

        When enabled, existing connections to a member being removed are allowed
        to complete within the timeout period before the member is fully removed.
        Use for rolling deployments to avoid request interruption.

        Args:
            pool_id: Backend server group (pool) id.
            enable: True to enable, False to disable.
            timeout: Drain timeout in seconds (1..3600). Default 60.

        Returns:
            {"pool_id": ..., "connection_drain": {"enable": ..., "timeout": ...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "operator")

        params = SetConnectionDrainInput(
            pool_id=pool_id,
            enable=enable,
            timeout=timeout,
        )
        client = get_client("elb", settings)

        cd = ConnectionDrain(
            enable=params.enable,
            timeout=params.timeout if params.enable else 0,
        )
        opt = UpdatePoolOption(connection_drain=cd)
        resp = client.update_pool(
            UpdatePoolRequest(
                pool_id=params.pool_id,
                body=UpdatePoolRequestBody(pool=opt),
            )
        )
        pool = getattr(resp, "pool", None)
        from ..serializers import _connection_drain_summary
        return {
            "pool_id": params.pool_id,
            "connection_drain": _connection_drain_summary(
                getattr(pool, "connection_drain", None)
            ),
        }

    # ------------------------------------------------------------------ #
    # confirm_destructive
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_confirm_destructive(approval_id: str) -> dict:
        """Execute a previously requested destructive ELB operation.

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
        "elb_manage_backend_member": elb_manage_backend_member,
        "elb_manage_listener": elb_manage_listener,
        "elb_manage_forwarding_rule": elb_manage_forwarding_rule,
        "elb_set_connection_drain": elb_set_connection_drain,
        "elb_confirm_destructive": elb_confirm_destructive,
    }
