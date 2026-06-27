"""ELB query tools — read-only operations.

Tools:
  * elb_describe_load_balancers  — list/get LBs (list-vs-detail dispatch)
  * elb_describe_listeners       — list/get listeners (list-vs-detail dispatch)
  * elb_describe_backend_groups  — list/get pools (list-vs-detail dispatch)
  * elb_list_backend_members     — list members + health status (merged)
  * elb_describe_forwarding_rules — list/get L7 policies + rules (list-vs-detail)
  * elb_list_certificates        — list/get certs (list-vs-detail dispatch)
  * elb_describe_access_log_config — list/get logtanks (list-vs-detail dispatch)
"""
from __future__ import annotations

import logging
from typing import Optional

from huaweicloudsdkelb.v3 import (
    ListCertificatesRequest,
    ListL7PoliciesRequest,
    ListL7RulesRequest,
    ListListenersRequest,
    ListLoadBalancersRequest,
    ListLogtanksRequest,
    ListMembersRequest,
    ListPoolsRequest,
    ShowCertificateRequest,
    ShowL7PolicyRequest,
    ShowListenerRequest,
    ShowLoadBalancerRequest,
    ShowLoadBalancerStatusRequest,
    ShowLogtankRequest,
    ShowPoolRequest,
)
from mcp_auth_common import create_auth_strategy, current_scope, require_role

from ....client import get_client
from ....config import Settings
from ....errors import ToolError, wrap_tool
from ..models import (
    DescribeAccessLogConfigInput,
    DescribeBackendGroupsInput,
    DescribeForwardingRulesInput,
    DescribeListenersInput,
    DescribeLoadBalancersInput,
    ListBackendMembersInput,
    ListCertificatesInput,
)
from ..serializers import (
    certificate_detail,
    certificate_summary,
    l7_policy_detail,
    l7_policy_summary,
    listener_detail,
    listener_summary,
    load_balancer_detail,
    load_balancer_status_summary,
    load_balancer_summary,
    logtank_summary,
    member_summary,
    pool_detail,
    pool_summary,
)

log = logging.getLogger("huaweicloud_mcp.services.elb.tools.query")


def make_query_tools(settings: Settings) -> dict:
    """Build ELB read-only query tools bound to *settings*."""
    auth = create_auth_strategy()

    # ------------------------------------------------------------------ #
    # describe_load_balancers
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_describe_load_balancers(
        loadbalancer_id: Optional[str] = None,
        name: Optional[str] = None,
        vpc_id: Optional[str] = None,
        vip_address: Optional[str] = None,
        operating_status: Optional[str] = None,
        provisioning_status: Optional[str] = None,
        limit: Optional[int] = None,
        marker: Optional[str] = None,
    ) -> dict:
        """List or get detail of ELB load balancers.

        Dispatches based on loadbalancer_id:
          * loadbalancer_id is None/empty → LIST mode.
          * loadbalancer_id is set → DETAIL mode (full info: VIP, AZs,
            flavors, EIPs, tags, protection settings).

        Args:
            loadbalancer_id: LB UUID. Omit to list, set to get detail.
            name: List-mode filter: LB name.
            vpc_id: List-mode filter: VPC id.
            vip_address: List-mode filter: VIP address.
            operating_status: List-mode filter (ACTIVE, DELETED, ERROR).
            provisioning_status: List-mode filter.
            limit: Page size (1..200).
            marker: Pagination marker.

        Returns:
            LIST:  {"load_balancers": [...], "total_count": N}
            DETAIL: {"load_balancer": {...full detail...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeLoadBalancersInput(
            loadbalancer_id=loadbalancer_id,
            name=name,
            vpc_id=vpc_id,
            vip_address=vip_address,
            operating_status=operating_status,
            provisioning_status=provisioning_status,
            limit=limit,
            marker=marker,
        )
        client = get_client("elb", settings)

        # Detail mode.
        if params.loadbalancer_id:
            resp = client.show_load_balancer(
                ShowLoadBalancerRequest(loadbalancer_id=params.loadbalancer_id)
            )
            lb = getattr(resp, "loadbalancer", None)
            if lb is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"Load balancer {params.loadbalancer_id!r} not found.",
                )
            return {"load_balancer": load_balancer_detail(lb)}

        # List mode.
        req = ListLoadBalancersRequest(
            name=params.name,
            vpc_id=params.vpc_id,
            vip_address=params.vip_address,
            operating_status=params.operating_status,
            provisioning_status=params.provisioning_status,
            limit=params.limit,
            marker=params.marker,
        )
        resp = client.list_load_balancers(req)
        lbs = list(getattr(resp, "loadbalancers", None) or [])
        out = [load_balancer_summary(lb) for lb in lbs]
        return {"load_balancers": out, "total_count": len(out)}

    # ------------------------------------------------------------------ #
    # describe_listeners
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_describe_listeners(
        listener_id: Optional[str] = None,
        loadbalancer_id: Optional[str] = None,
        protocol: Optional[str] = None,
        protocol_port: Optional[int] = None,
        name: Optional[str] = None,
        limit: Optional[int] = None,
        marker: Optional[str] = None,
    ) -> dict:
        """List or get detail of ELB listeners.

        Dispatches based on listener_id:
          * listener_id is None/empty → LIST mode.
          * listener_id is set → DETAIL mode (protocol, port, SSL cert,
            default pool, timeouts, HTTP2, TLS policy).

        Args:
            listener_id: Listener UUID. Omit to list, set to get detail.
            loadbalancer_id: List-mode filter: LB id.
            protocol: List-mode filter (TCP, UDP, HTTP, HTTPS, QUIC).
            protocol_port: List-mode filter: port.
            name: List-mode filter: listener name.
            limit: Page size (1..200).
            marker: Pagination marker.

        Returns:
            LIST:  {"listeners": [...], "total_count": N}
            DETAIL: {"listener": {...full detail...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeListenersInput(
            listener_id=listener_id,
            loadbalancer_id=loadbalancer_id,
            protocol=protocol,
            protocol_port=protocol_port,
            name=name,
            limit=limit,
            marker=marker,
        )
        client = get_client("elb", settings)

        if params.listener_id:
            resp = client.show_listener(
                ShowListenerRequest(listener_id=params.listener_id)
            )
            lis = getattr(resp, "listener", None)
            if lis is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"Listener {params.listener_id!r} not found.",
                )
            return {"listener": listener_detail(lis)}

        req = ListListenersRequest(
            loadbalancer_id=params.loadbalancer_id,
            protocol=params.protocol,
            protocol_port=params.protocol_port,
            name=params.name,
            limit=params.limit,
            marker=params.marker,
        )
        resp = client.list_listeners(req)
        listeners = list(getattr(resp, "listeners", None) or [])
        out = [listener_summary(lis) for lis in listeners]
        return {"listeners": out, "total_count": len(out)}

    # ------------------------------------------------------------------ #
    # describe_backend_groups
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_describe_backend_groups(
        pool_id: Optional[str] = None,
        loadbalancer_id: Optional[str] = None,
        listener_id: Optional[str] = None,
        protocol: Optional[str] = None,
        lb_algorithm: Optional[str] = None,
        name: Optional[str] = None,
        limit: Optional[int] = None,
        marker: Optional[str] = None,
    ) -> dict:
        """List or get detail of ELB backend server groups (pools).

        Dispatches based on pool_id:
          * pool_id is None/empty → LIST mode.
          * pool_id is set → DETAIL mode (load algorithm, session persistence,
            connection drain, slow start, health monitor id).

        Args:
            pool_id: Pool UUID. Omit to list, set to get detail.
            loadbalancer_id: List-mode filter: LB id.
            listener_id: List-mode filter: listener id.
            protocol: List-mode filter (TCP, UDP, HTTP, HTTPS).
            lb_algorithm: List-mode filter (ROUND_ROBIN, LEAST_CONNECTIONS, SOURCE_IP).
            name: List-mode filter: pool name.
            limit: Page size (1..200).
            marker: Pagination marker.

        Returns:
            LIST:  {"backend_groups": [...], "total_count": N}
            DETAIL: {"backend_group": {...full detail...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeBackendGroupsInput(
            pool_id=pool_id,
            loadbalancer_id=loadbalancer_id,
            listener_id=listener_id,
            protocol=protocol,
            lb_algorithm=lb_algorithm,
            name=name,
            limit=limit,
            marker=marker,
        )
        client = get_client("elb", settings)

        if params.pool_id:
            resp = client.show_pool(ShowPoolRequest(pool_id=params.pool_id))
            pool = getattr(resp, "pool", None)
            if pool is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"Backend group (pool) {params.pool_id!r} not found.",
                )
            return {"backend_group": pool_detail(pool)}

        req = ListPoolsRequest(
            loadbalancer_id=params.loadbalancer_id,
            listener_id=params.listener_id,
            protocol=params.protocol,
            lb_algorithm=params.lb_algorithm,
            name=params.name,
            limit=params.limit,
            marker=params.marker,
        )
        resp = client.list_pools(req)
        pools = list(getattr(resp, "pools", None) or [])
        out = [pool_summary(p) for p in pools]
        return {"backend_groups": out, "total_count": len(out)}

    # ------------------------------------------------------------------ #
    # list_backend_members (merged: list members + health check status)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_list_backend_members(
        pool_id: str,
        loadbalancer_id: Optional[str] = None,
        name: Optional[str] = None,
        address: Optional[str] = None,
        protocol_port: Optional[int] = None,
        limit: Optional[int] = None,
        marker: Optional[str] = None,
    ) -> dict:
        """List backend server members of a pool with real-time health status.

        Merged from list_backend_servers + get_health_check_status. Always
        lists pool members via list_members. When loadbalancer_id is provided,
        also fetches real-time health status (ONLINE/OFFLINE/NO_MONITOR) via
        show_load_balancer_status and merges operating_status into each member.

        Args:
            pool_id: Backend server group (pool) id.
            loadbalancer_id: LB id for health status cross-call. If omitted,
                members are returned without health info.
            name: Filter: member name.
            address: Filter: member IP address.
            protocol_port: Filter: member port.
            limit: Page size (1..200).
            marker: Pagination marker.

        Returns:
            {"pool_id": ..., "members": [...], "total_count": N,
             "health_status_available": bool}
            Each member includes: id, address, protocol_port, weight,
            operating_status, and health_status (when available).
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListBackendMembersInput(
            pool_id=pool_id,
            loadbalancer_id=loadbalancer_id,
            name=name,
            address=address,
            protocol_port=protocol_port,
            limit=limit,
            marker=marker,
        )
        client = get_client("elb", settings)

        # Fetch members.
        req = ListMembersRequest(
            pool_id=params.pool_id,
            name=params.name,
            address=params.address,
            protocol_port=params.protocol_port,
            limit=params.limit,
            marker=params.marker,
        )
        resp = client.list_members(req)
        members = list(getattr(resp, "members", None) or [])
        out = [member_summary(m) for m in members]

        # Cross-call show_load_balancer_status for health info.
        health_available = False
        if params.loadbalancer_id:
            try:
                status_resp = client.show_load_balancer_status(
                    ShowLoadBalancerStatusRequest(
                        loadbalancer_id=params.loadbalancer_id
                    )
                )
                status_data = load_balancer_status_summary(
                    getattr(status_resp, "statuses", None)
                )
                # Build member_id → health_status map.
                health_map: dict[str, str] = {}
                for pool_status in (status_data.get("pools") or []):
                    if pool_status.get("id") == params.pool_id:
                        for m_status in (pool_status.get("members") or []):
                            health_map[m_status.get("id")] = m_status.get(
                                "operating_status"
                            )
                # Merge health into member output.
                if health_map:
                    health_available = True
                    for m in out:
                        mid = m.get("id")
                        if mid in health_map:
                            m["health_status"] = health_map[mid]
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "list_backend_members: health status fetch failed: %s", exc
                )

        return {
            "pool_id": params.pool_id,
            "members": out,
            "total_count": len(out),
            "health_status_available": health_available,
        }

    # ------------------------------------------------------------------ #
    # describe_forwarding_rules (L7 policies + rules)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_describe_forwarding_rules(
        policy_id: Optional[str] = None,
        listener_id: Optional[str] = None,
        name: Optional[str] = None,
        action: Optional[str] = None,
        limit: Optional[int] = None,
        marker: Optional[str] = None,
    ) -> dict:
        """List or get detail of ELB L7 forwarding policies and their rules.

        Dispatches based on policy_id:
          * policy_id is None/empty → LIST mode (policies with inline rules).
          * policy_id is set → DETAIL mode (full policy + all its L7 rules).

        Args:
            policy_id: L7 policy UUID. Omit to list, set to get detail.
            listener_id: List-mode filter: listener id.
            name: List-mode filter: policy name.
            action: List-mode filter (REDIRECT_TO_POOL, REDIRECT_TO_LISTENER,
                    REDIRECT_TO_URL, FIXED_RESPONSE).
            limit: Page size (1..200).
            marker: Pagination marker.

        Returns:
            LIST:  {"forwarding_rules": [...], "total_count": N}
            DETAIL: {"forwarding_rule": {...full detail with rules...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeForwardingRulesInput(
            policy_id=policy_id,
            listener_id=listener_id,
            name=name,
            action=action,
            limit=limit,
            marker=marker,
        )
        client = get_client("elb", settings)

        if params.policy_id:
            resp = client.show_l7_policy(
                ShowL7PolicyRequest(l7policy_id=params.policy_id)
            )
            policy = getattr(resp, "l7policy", None)
            if policy is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"L7 policy {params.policy_id!r} not found.",
                )
            # Fetch rules for this policy.
            rules = []
            try:
                rules_resp = client.list_l7_rules(
                    ListL7RulesRequest(l7policy_id=params.policy_id)
                )
                rules = list(getattr(rules_resp, "rules", None) or [])
            except Exception as exc:  # noqa: BLE001
                log.warning("describe_forwarding_rules: list rules failed: %s", exc)
            return {"forwarding_rule": l7_policy_detail(policy, rules)}

        req = ListL7PoliciesRequest(
            listener_id=params.listener_id,
            name=params.name,
            action=params.action,
            limit=params.limit,
            marker=params.marker,
        )
        resp = client.list_l7_policies(req)
        policies = list(getattr(resp, "l7policies", None) or [])
        out = [l7_policy_detail(p) for p in policies]
        return {"forwarding_rules": out, "total_count": len(out)}

    # ------------------------------------------------------------------ #
    # list_certificates
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_list_certificates(
        certificate_id: Optional[str] = None,
        name: Optional[str] = None,
        domain: Optional[str] = None,
        type: Optional[str] = None,
        limit: Optional[int] = None,
        marker: Optional[str] = None,
    ) -> dict:
        """List or get detail of ELB SSL certificates.

        Dispatches based on certificate_id:
          * certificate_id is None/empty → LIST mode (id, name, domain,
            type, expire_time).
          * certificate_id is set → DETAIL mode (full cert info including
            fingerprint, SANs, SCM ref, protection status).

        Args:
            certificate_id: Certificate UUID. Omit to list, set to get detail.
            name: List-mode filter: certificate name.
            domain: List-mode filter: domain name.
            type: List-mode filter: 'server' or 'client'.
            limit: Page size (1..200).
            marker: Pagination marker.

        Returns:
            LIST:  {"certificates": [...], "total_count": N}
            DETAIL: {"certificate": {...full detail...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = ListCertificatesInput(
            certificate_id=certificate_id,
            name=name,
            domain=domain,
            type=type,
            limit=limit,
            marker=marker,
        )
        client = get_client("elb", settings)

        if params.certificate_id:
            resp = client.show_certificate(
                ShowCertificateRequest(certificate_id=params.certificate_id)
            )
            cert = getattr(resp, "certificate", None)
            if cert is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"Certificate {params.certificate_id!r} not found.",
                )
            return {"certificate": certificate_detail(cert)}

        req = ListCertificatesRequest(
            name=params.name,
            domain=params.domain,
            type=params.type,
            limit=params.limit,
            marker=params.marker,
        )
        resp = client.list_certificates(req)
        certs = list(getattr(resp, "certificates", None) or [])
        out = [certificate_summary(c) for c in certs]
        return {"certificates": out, "total_count": len(out)}

    # ------------------------------------------------------------------ #
    # describe_access_log_config (logtanks)
    # ------------------------------------------------------------------ #
    @wrap_tool
    def elb_describe_access_log_config(
        logtank_id: Optional[str] = None,
        loadbalancer_id: Optional[str] = None,
        limit: Optional[int] = None,
        marker: Optional[str] = None,
    ) -> dict:
        """List or get detail of ELB access log delivery configs (logtanks).

        A logtank configures access log delivery from a load balancer to LTS
        (Log Tank Service). Shows the LTS log_group_id and log_topic_id.

        Dispatches based on logtank_id:
          * logtank_id is None/empty → LIST mode.
          * logtank_id is set → DETAIL mode.

        Args:
            logtank_id: Logtank UUID. Omit to list, set to get detail.
            loadbalancer_id: List-mode filter: LB id.
            limit: Page size (1..200).
            marker: Pagination marker.

        Returns:
            LIST:  {"access_log_configs": [...], "total_count": N}
            DETAIL: {"access_log_config": {...}}
        """
        identity = auth.resolve(current_scope())
        require_role(identity, "readonly")

        params = DescribeAccessLogConfigInput(
            logtank_id=logtank_id,
            loadbalancer_id=loadbalancer_id,
            limit=limit,
            marker=marker,
        )
        client = get_client("elb", settings)

        if params.logtank_id:
            resp = client.show_logtank(
                ShowLogtankRequest(logtank_id=params.logtank_id)
            )
            lt = getattr(resp, "logtank", None)
            if lt is None:
                raise ToolError(
                    code="NOT_FOUND",
                    message=f"Logtank {params.logtank_id!r} not found.",
                )
            return {"access_log_config": logtank_summary(lt)}

        req = ListLogtanksRequest(
            loadbalancer_id=params.loadbalancer_id,
            limit=params.limit,
            marker=params.marker,
        )
        resp = client.list_logtanks(req)
        logtanks = list(getattr(resp, "logtanks", None) or [])
        out = [logtank_summary(lt) for lt in logtanks]
        return {"access_log_configs": out, "total_count": len(out)}

    return {
        "elb_describe_load_balancers": elb_describe_load_balancers,
        "elb_describe_listeners": elb_describe_listeners,
        "elb_describe_backend_groups": elb_describe_backend_groups,
        "elb_list_backend_members": elb_list_backend_members,
        "elb_describe_forwarding_rules": elb_describe_forwarding_rules,
        "elb_list_certificates": elb_list_certificates,
        "elb_describe_access_log_config": elb_describe_access_log_config,
    }
