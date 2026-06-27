"""Pydantic input models for ELB MCP tools.

ELB uses the v3 SDK exclusively. Tools follow the project's list/detail
dispatch pattern where applicable (describe_load_balancers, describe_listeners,
describe_backend_groups, describe_forwarding_rules, list_certificates,
describe_access_log_config).

Merged tools (action dispatch):
  * manage_backend_member — add / remove / update_weight
  * manage_listener        — create / update / replace_certificate
  * manage_forwarding_rule — create / delete
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# elb_describe_load_balancers — ListLoadBalancersRequest / ShowLoadBalancerRequest
# ---------------------------------------------------------------------------
class DescribeLoadBalancersInput(BaseModel):
    loadbalancer_id: Optional[str] = Field(
        default=None,
        description=(
            "Load balancer id. If None/empty, returns the LIST of LBs. "
            "If set, returns DETAIL for that single LB."
        ),
    )
    name: Optional[str] = Field(default=None, description="List-mode filter: LB name.")
    vpc_id: Optional[str] = Field(default=None, description="List-mode filter: VPC id.")
    vip_address: Optional[str] = Field(
        default=None, description="List-mode filter: VIP address."
    )
    operating_status: Optional[str] = Field(
        default=None,
        description="List-mode filter: operating status (ACTIVE, DELETED, ERROR, etc.).",
    )
    provisioning_status: Optional[str] = Field(
        default=None,
        description="List-mode filter: provisioning status.",
    )
    limit: Optional[int] = Field(
        default=None, ge=1, le=200, description="Page size (1..200)."
    )
    marker: Optional[str] = Field(
        default=None, description="Pagination marker (id of last item from previous page)."
    )


# ---------------------------------------------------------------------------
# elb_describe_listeners — ListListenersRequest / ShowListenerRequest
# ---------------------------------------------------------------------------
class DescribeListenersInput(BaseModel):
    listener_id: Optional[str] = Field(
        default=None,
        description=(
            "Listener id. If None/empty, returns the LIST of listeners. "
            "If set, returns DETAIL for that single listener."
        ),
    )
    loadbalancer_id: Optional[str] = Field(
        default=None, description="List-mode filter: load balancer id."
    )
    protocol: Optional[str] = Field(
        default=None, description="List-mode filter: protocol (TCP, UDP, HTTP, HTTPS, QUIC)."
    )
    protocol_port: Optional[int] = Field(
        default=None, description="List-mode filter: listening port."
    )
    name: Optional[str] = Field(default=None, description="List-mode filter: listener name.")
    limit: Optional[int] = Field(
        default=None, ge=1, le=200, description="Page size (1..200)."
    )
    marker: Optional[str] = Field(default=None, description="Pagination marker.")


# ---------------------------------------------------------------------------
# elb_describe_backend_groups — ListPoolsRequest / ShowPoolRequest
# ---------------------------------------------------------------------------
class DescribeBackendGroupsInput(BaseModel):
    pool_id: Optional[str] = Field(
        default=None,
        description=(
            "Backend server group (pool) id. If None/empty, returns the LIST. "
            "If set, returns DETAIL for that single pool."
        ),
    )
    loadbalancer_id: Optional[str] = Field(
        default=None, description="List-mode filter: load balancer id."
    )
    listener_id: Optional[str] = Field(
        default=None, description="List-mode filter: listener id."
    )
    protocol: Optional[str] = Field(
        default=None, description="List-mode filter: pool protocol (TCP, UDP, HTTP, HTTPS)."
    )
    lb_algorithm: Optional[str] = Field(
        default=None,
        description="List-mode filter: load balancing algorithm (ROUND_ROBIN, LEAST_CONNECTIONS, SOURCE_IP).",
    )
    name: Optional[str] = Field(default=None, description="List-mode filter: pool name.")
    limit: Optional[int] = Field(
        default=None, ge=1, le=200, description="Page size (1..200)."
    )
    marker: Optional[str] = Field(default=None, description="Pagination marker.")


# ---------------------------------------------------------------------------
# elb_list_backend_members — ListMembersRequest + ShowLoadBalancerStatus
# (merged: list_backend_servers + get_health_check_status)
# ---------------------------------------------------------------------------
class ListBackendMembersInput(BaseModel):
    pool_id: str = Field(..., description="Backend server group (pool) id.")
    loadbalancer_id: Optional[str] = Field(
        default=None,
        description=(
            "Load balancer id. Required to fetch real-time health status. "
            "If omitted, members are returned without health info."
        ),
    )
    name: Optional[str] = Field(default=None, description="Filter: member name.")
    address: Optional[str] = Field(default=None, description="Filter: member IP address.")
    protocol_port: Optional[int] = Field(default=None, description="Filter: member port.")
    limit: Optional[int] = Field(
        default=None, ge=1, le=200, description="Page size (1..200)."
    )
    marker: Optional[str] = Field(default=None, description="Pagination marker.")


# ---------------------------------------------------------------------------
# elb_describe_forwarding_rules — ListL7PoliciesRequest / ShowL7PolicyRequest
# (includes L7 rules under each policy)
# ---------------------------------------------------------------------------
class DescribeForwardingRulesInput(BaseModel):
    policy_id: Optional[str] = Field(
        default=None,
        description=(
            "L7 policy id. If None/empty, returns the LIST of policies. "
            "If set, returns DETAIL for that single policy (with its rules)."
        ),
    )
    listener_id: Optional[str] = Field(
        default=None, description="List-mode filter: listener id."
    )
    name: Optional[str] = Field(default=None, description="List-mode filter: policy name.")
    action: Optional[str] = Field(
        default=None,
        description="List-mode filter: action (REDIRECT_TO_POOL, REDIRECT_TO_LISTENER, REDIRECT_TO_URL, FIXED_RESPONSE).",
    )
    limit: Optional[int] = Field(
        default=None, ge=1, le=200, description="Page size (1..200)."
    )
    marker: Optional[str] = Field(default=None, description="Pagination marker.")


# ---------------------------------------------------------------------------
# elb_list_certificates — ListCertificatesRequest / ShowCertificateRequest
# ---------------------------------------------------------------------------
class ListCertificatesInput(BaseModel):
    certificate_id: Optional[str] = Field(
        default=None,
        description=(
            "Certificate id. If None/empty, returns the LIST. "
            "If set, returns DETAIL for that single certificate."
        ),
    )
    name: Optional[str] = Field(default=None, description="List-mode filter: certificate name.")
    domain: Optional[str] = Field(
        default=None, description="List-mode filter: domain name."
    )
    type: Optional[str] = Field(
        default=None, description="List-mode filter: certificate type (server, client)."
    )
    limit: Optional[int] = Field(
        default=None, ge=1, le=200, description="Page size (1..200)."
    )
    marker: Optional[str] = Field(default=None, description="Pagination marker.")


# ---------------------------------------------------------------------------
# elb_describe_access_log_config — ListLogtanksRequest / ShowLogtankRequest
# ---------------------------------------------------------------------------
class DescribeAccessLogConfigInput(BaseModel):
    logtank_id: Optional[str] = Field(
        default=None,
        description=(
            "Logtank (access log config) id. If None/empty, returns the LIST. "
            "If set, returns DETAIL for that single logtank."
        ),
    )
    loadbalancer_id: Optional[str] = Field(
        default=None, description="List-mode filter: load balancer id."
    )
    limit: Optional[int] = Field(
        default=None, ge=1, le=200, description="Page size (1..200)."
    )
    marker: Optional[str] = Field(default=None, description="Pagination marker.")


# ---------------------------------------------------------------------------
# elb_audit_health — composite health audit
# ---------------------------------------------------------------------------
class AuditHealthInput(BaseModel):
    loadbalancer_id: Optional[str] = Field(
        default=None,
        description=(
            "Audit a single load balancer. If None/empty, audits ALL load "
            "balancers (may be slow with many LBs)."
        ),
    )
    cert_expiry_days: int = Field(
        default=30,
        ge=1,
        description="Warn when certificates expire within this many days. Default 30.",
    )


# ---------------------------------------------------------------------------
# elb_manage_backend_member — merged: add / remove / update_weight
# ---------------------------------------------------------------------------
class ManageBackendMemberInput(BaseModel):
    action: Literal["add", "remove", "update_weight"] = Field(
        ...,
        description=(
            "Member action: 'add' to add a new backend server, 'remove' to "
            "delete a member (DESTRUCTIVE — two-phase commit), 'update_weight' "
            "to change a member's traffic weight (0 = drain, 100 = full)."
        ),
    )
    pool_id: str = Field(..., description="Backend server group (pool) id.")
    member_id: Optional[str] = Field(
        default=None,
        description="Member id. Required for 'remove' and 'update_weight'.",
    )
    address: Optional[str] = Field(
        default=None,
        description="Backend server IP address. Required for 'add'.",
    )
    protocol_port: Optional[int] = Field(
        default=None,
        ge=1, le=65535,
        description="Backend server port. Required for 'add'.",
    )
    weight: Optional[int] = Field(
        default=None,
        ge=0, le=100,
        description=(
            "Traffic weight (0..100). Used for 'add' (default 100) and "
            "'update_weight'. 0 = drain, 100 = full traffic."
        ),
    )
    subnet_cidr_id: Optional[str] = Field(
        default=None,
        description="Subnet id for the member. Optional for 'add'.",
    )
    name: Optional[str] = Field(default=None, description="Member name. Optional for 'add'.")


# ---------------------------------------------------------------------------
# elb_manage_listener — merged: create / update / replace_certificate
# ---------------------------------------------------------------------------
class ManageListenerInput(BaseModel):
    action: Literal["create", "update", "replace_certificate"] = Field(
        ...,
        description=(
            "Listener action: 'create' to create a new listener (DESTRUCTIVE — "
            "two-phase commit), 'update' to modify listener config, "
            "'replace_certificate' to swap the SSL certificate."
        ),
    )
    listener_id: Optional[str] = Field(
        default=None,
        description="Listener id. Required for 'update' and 'replace_certificate'.",
    )
    loadbalancer_id: Optional[str] = Field(
        default=None,
        description="Load balancer id. Required for 'create'.",
    )
    name: Optional[str] = Field(default=None, description="Listener name.")
    description: Optional[str] = Field(default=None, description="Listener description.")
    protocol: Optional[str] = Field(
        default=None,
        description="Protocol (TCP, UDP, HTTP, HTTPS, TERMINATED_HTTPS). Required for 'create'.",
    )
    protocol_port: Optional[int] = Field(
        default=None, ge=1, le=65535,
        description="Listening port. Required for 'create'.",
    )
    default_pool_id: Optional[str] = Field(
        default=None, description="Default backend server group id."
    )
    certificate_id: Optional[str] = Field(
        default=None,
        description=(
            "SSL certificate id. For 'create' sets the default cert; "
            "for 'replace_certificate' is the new cert to bind."
        ),
    )
    http2_enable: Optional[bool] = Field(default=None, description="Enable HTTP/2 (HTTPS only).")
    keepalive_timeout: Optional[int] = Field(
        default=None, ge=0, description="Keep-alive timeout in seconds."
    )
    client_timeout: Optional[int] = Field(
        default=None, ge=0, description="Client timeout in seconds."
    )
    member_timeout: Optional[int] = Field(
        default=None, ge=0, description="Member (backend) timeout in seconds."
    )
    tls_ciphers_policy: Optional[str] = Field(
        default=None, description="TLS ciphers policy name."
    )
    admin_state_up: Optional[bool] = Field(
        default=None, description="Administrative state (enabled/disabled)."
    )


# ---------------------------------------------------------------------------
# elb_manage_forwarding_rule — merged: create / delete
# ---------------------------------------------------------------------------
class ManageForwardingRuleInput(BaseModel):
    action: Literal["create", "delete"] = Field(
        ...,
        description=(
            "Forwarding rule action: 'create' to add an L7 policy + rule, "
            "'delete' to remove an L7 policy (DESTRUCTIVE — two-phase commit)."
        ),
    )
    policy_id: Optional[str] = Field(
        default=None,
        description="L7 policy id. Required for 'delete'.",
    )
    listener_id: Optional[str] = Field(
        default=None,
        description="Listener id. Required for 'create'.",
    )
    name: Optional[str] = Field(
        default=None, description="Policy name. Used for 'create'."
    )
    description: Optional[str] = Field(
        default=None, description="Policy description. Used for 'create'."
    )
    redirect_pool_id: Optional[str] = Field(
        default=None,
        description="Target backend group id for REDIRECT_TO_POOL action. Used for 'create'.",
    )
    redirect_listener_id: Optional[str] = Field(
        default=None,
        description="Target listener id for REDIRECT_TO_LISTENER action. Used for 'create'.",
    )
    redirect_url: Optional[str] = Field(
        default=None,
        description="Target URL for REDIRECT_TO_URL action. Used for 'create'.",
    )
    # L7 rule conditions
    rule_type: Optional[str] = Field(
        default=None,
        description=(
            "Rule match type for 'create': 'HOST_NAME', 'PATH', 'HEADER', 'QUERY_STRING'. "
            "Required when creating a policy with a rule."
        ),
    )
    rule_compare_type: Optional[str] = Field(
        default=None,
        description=(
            "Rule comparison type: 'EQUAL_TO', 'STARTS_WITH', 'ENDS_WITH', "
            "'CONTAINS', 'REGEX'. Required when rule_type is set."
        ),
    )
    rule_value: Optional[str] = Field(
        default=None,
        description="Rule match value (e.g. '/api' for PATH, 'example.com' for HOST_NAME).",
    )
    rule_key: Optional[str] = Field(
        default=None,
        description="Header name (for rule_type='HEADER') or query param name.",
    )
    priority: Optional[int] = Field(
        default=None,
        description="Policy priority (lower = higher priority). Used for 'create'.",
    )


# ---------------------------------------------------------------------------
# elb_set_connection_drain — UpdatePool with connection_drain
# ---------------------------------------------------------------------------
class SetConnectionDrainInput(BaseModel):
    pool_id: str = Field(..., description="Backend server group (pool) id.")
    enable: bool = Field(
        default=True,
        description="True to enable connection drain, False to disable.",
    )
    timeout: int = Field(
        default=60,
        ge=1, le=3600,
        description=(
            "Drain timeout in seconds (1..3600). Existing connections will be "
            "allowed to complete within this period before the member is removed. "
            "Default 60."
        ),
    )


# ---------------------------------------------------------------------------
# elb_confirm_destructive — two-phase commit
# ---------------------------------------------------------------------------
class ConfirmDestructiveInput(BaseModel):
    approval_id: str = Field(..., description="Approval id from a pending operation.")
