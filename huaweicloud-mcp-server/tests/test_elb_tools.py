"""Tests for ELB MCP tools.

Covers:
  - Server registration (elb in ALL_SERVICES, tools appear)
  - elb_describe_load_balancers (list + detail dispatch)
  - elb_describe_listeners (list + detail dispatch)
  - elb_describe_backend_groups (list + detail dispatch)
  - elb_list_backend_members (members + health status merge)
  - elb_describe_forwarding_rules (list + detail with rules)
  - elb_list_certificates (list + detail dispatch)
  - elb_describe_access_log_config (list + detail dispatch)
  - elb_audit_health (composite audit)
  - elb_manage_backend_member (add / update_weight / remove two-phase)
  - elb_manage_listener (create two-phase / update / replace_certificate)
  - elb_manage_forwarding_rule (create / delete two-phase)
  - elb_set_connection_drain
  - elb_confirm_destructive
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.server import ALL_SERVICES, build_server
from huaweicloud_mcp.services.elb.tools.query import make_query_tools
from huaweicloud_mcp.services.elb.tools.audit import make_audit_tools
from huaweicloud_mcp.services.elb.tools.manage import make_manage_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def elb_settings() -> Settings:
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def mock_elb_client(monkeypatch):
    """Replace get_client('elb', ...) with a MagicMock in all ELB tool modules."""
    fake = MagicMock(name="ElbClient")
    for mod in (
        "huaweicloud_mcp.services.elb.tools.query",
        "huaweicloud_mcp.services.elb.tools.audit",
        "huaweicloud_mcp.services.elb.tools.manage",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------

class TestServerRegistration:
    def test_elb_in_all_services(self):
        assert "elb" in ALL_SERVICES

    def test_build_server_registers_elb_tools(self, elb_settings, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED_SERVICES", "elb")
        server = build_server(settings=elb_settings)
        tool_names = set(server._tool_manager._tools.keys())
        elb_tools = {n for n in tool_names if n.startswith("elb_")}
        expected = {
            "elb_describe_load_balancers",
            "elb_describe_listeners",
            "elb_describe_backend_groups",
            "elb_list_backend_members",
            "elb_describe_forwarding_rules",
            "elb_list_certificates",
            "elb_describe_access_log_config",
            "elb_audit_health",
            "elb_manage_backend_member",
            "elb_manage_listener",
            "elb_manage_forwarding_rule",
            "elb_set_connection_drain",
            "elb_confirm_destructive",
        }
        assert expected <= elb_tools, f"Missing: {expected - elb_tools}"


# ---------------------------------------------------------------------------
# elb_describe_load_balancers
# ---------------------------------------------------------------------------

class TestDescribeLoadBalancers:
    def test_list_all(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        lb1 = _ns(id="lb-1", name="web-lb", operating_status="ACTIVE",
                  provisioning_status="ACTIVE", admin_state_up=True,
                  vip_address="10.0.0.1", vpc_id="vpc-1",
                  availability_zone_list=["af-south-1a"], provider="vlb",
                  eips=[], publicips=[])
        lb2 = _ns(id="lb-2", name="api-lb", operating_status="ACTIVE",
                  provisioning_status="ACTIVE", admin_state_up=True,
                  vip_address="10.0.0.2", vpc_id="vpc-1",
                  availability_zone_list=["af-south-1b"], provider="vlb",
                  eips=[], publicips=[])
        mock_elb_client.list_load_balancers.return_value = _ns(
            loadbalancers=[lb1, lb2]
        )

        result = tools["elb_describe_load_balancers"]()
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 2
        assert data["load_balancers"][0]["id"] == "lb-1"
        assert data["load_balancers"][0]["name"] == "web-lb"

    def test_detail(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        lb = _ns(
            id="lb-1", name="web-lb", operating_status="ACTIVE",
            provisioning_status="ACTIVE", admin_state_up=True,
            vip_address="10.0.0.1", vpc_id="vpc-1",
            availability_zone_list=["af-south-1a"], provider="vlb",
            eips=[], publicips=[], description="web load balancer",
            vip_subnet_cidr_id="subnet-1", vip_port_id="port-1",
            guaranteed=True, l4_flavor_id="flavor-1", l7_flavor_id=None,
            billing_info=None, created_at="2024-01-01T00:00:00Z",
            updated_at="2024-06-01T00:00:00Z", enterprise_project_id=None,
            deletion_protection_enable=True, frozen_scene=None,
            tags={"env": "prod"}, log_group_id=None, log_topic_id=None,
            ipv6_vip_address=None,
        )
        mock_elb_client.show_load_balancer.return_value = _ns(loadbalancer=lb)

        result = tools["elb_describe_load_balancers"](loadbalancer_id="lb-1")
        assert result["ok"] is True
        data = result["data"]
        assert data["load_balancer"]["id"] == "lb-1"
        assert data["load_balancer"]["description"] == "web load balancer"
        assert data["load_balancer"]["deletion_protection_enable"] is True

    def test_not_found(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        mock_elb_client.show_load_balancer.return_value = _ns(loadbalancer=None)
        result = tools["elb_describe_load_balancers"](loadbalancer_id="nope")
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# elb_describe_listeners
# ---------------------------------------------------------------------------

class TestDescribeListeners:
    def test_list(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        lis = _ns(id="lis-1", name="http-80", protocol="HTTP", protocol_port=80,
                  operating_status="ACTIVE", provisioning_status="ACTIVE",
                  admin_state_up=True, loadbalancers=[_ns(id="lb-1")],
                  default_pool_id="pool-1", default_tls_container_ref=None)
        mock_elb_client.list_listeners.return_value = _ns(listeners=[lis])
        result = tools["elb_describe_listeners"]()
        assert result["ok"] is True
        assert result["data"]["total_count"] == 1
        assert result["data"]["listeners"][0]["protocol"] == "HTTP"

    def test_detail(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        lis = _ns(id="lis-1", name="https-443", protocol="HTTPS", protocol_port=443,
                  operating_status="ACTIVE", provisioning_status="ACTIVE",
                  admin_state_up=True, loadbalancers=[_ns(id="lb-1")],
                  default_pool_id="pool-1", default_tls_container_ref="cert-1",
                  description="HTTPS listener", connection_limit=1000,
                  http2_enable=True, tls_ciphers_policy="tls-1-2",
                  security_policy_id=None, sni_container_refs=[],
                  sni_match_algo=None, keepalive_timeout=60,
                  client_timeout=60, member_timeout=60,
                  enable_member_retry=True, transparent_client_ip_enable=None,
                  proxy_protocol_enable=None, enhance_l7policy_enable=None,
                  gzip_enable=None, created_at="2024-01-01T00:00:00Z",
                  updated_at="2024-06-01T00:00:00Z", tags={}, protection_status=None)
        mock_elb_client.show_listener.return_value = _ns(listener=lis)
        result = tools["elb_describe_listeners"](listener_id="lis-1")
        assert result["ok"] is True
        assert result["data"]["listener"]["http2_enable"] is True
        assert result["data"]["listener"]["tls_ciphers_policy"] == "tls-1-2"


# ---------------------------------------------------------------------------
# elb_describe_backend_groups
# ---------------------------------------------------------------------------

class TestDescribeBackendGroups:
    def test_list(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        pool = _ns(id="pool-1", name="web-pool", protocol="HTTP",
                   lb_algorithm="ROUND_ROBIN", admin_state_up=True,
                   healthmonitor_id="hm-1", description="web backend pool")
        mock_elb_client.list_pools.return_value = _ns(pools=[pool])
        result = tools["elb_describe_backend_groups"]()
        assert result["ok"] is True
        assert result["data"]["backend_groups"][0]["lb_algorithm"] == "ROUND_ROBIN"

    def test_detail(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        pool = _ns(id="pool-1", name="web-pool", protocol="HTTP",
                   lb_algorithm="ROUND_ROBIN", admin_state_up=True,
                   healthmonitor_id="hm-1", description="web backend pool",
                   ip_version=4, vpc_id="vpc-1", type=None,
                   member_deletion_protection_enable=False, any_port_enable=False,
                   created_at="2024-01-01T00:00:00Z",
                   updated_at="2024-06-01T00:00:00Z",
                   session_persistence=_ns(type="HTTP_COOKIE", cookie_name=None,
                                           persistence_timeout=60),
                   connection_drain=_ns(enable=True, timeout=30),
                   slow_start=_ns(enable=False, duration=0),
                   protection_status=None)
        mock_elb_client.show_pool.return_value = _ns(pool=pool)
        result = tools["elb_describe_backend_groups"](pool_id="pool-1")
        assert result["ok"] is True
        detail = result["data"]["backend_group"]
        assert detail["connection_drain"]["enable"] is True
        assert detail["session_persistence"]["type"] == "HTTP_COOKIE"


# ---------------------------------------------------------------------------
# elb_list_backend_members (merged: members + health)
# ---------------------------------------------------------------------------

class TestListBackendMembers:
    def test_list_without_health(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        m1 = _ns(id="m-1", name="backend-1", address="10.0.1.1",
                 protocol_port=8080, weight=100, admin_state_up=True,
                 operating_status="ONLINE", status=None, subnet_cidr_id="subnet-1",
                 availability_zone="af-south-1a", member_type="ECS",
                 instance_id="ecs-1", reason=None)
        m2 = _ns(id="m-2", name="backend-2", address="10.0.1.2",
                 protocol_port=8080, weight=100, admin_state_up=True,
                 operating_status="ONLINE", status=None, subnet_cidr_id="subnet-1",
                 availability_zone="af-south-1a", member_type="ECS",
                 instance_id="ecs-2", reason=None)
        mock_elb_client.list_members.return_value = _ns(members=[m1, m2])
        result = tools["elb_list_backend_members"](pool_id="pool-1")
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 2
        assert data["health_status_available"] is False
        assert "health_status" not in data["members"][0]

    def test_list_with_health(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        m1 = _ns(id="m-1", name="backend-1", address="10.0.1.1",
                 protocol_port=8080, weight=100, admin_state_up=True,
                 operating_status=None, status=None, subnet_cidr_id="subnet-1",
                 availability_zone="af-south-1a", member_type=None,
                 instance_id=None, reason=None)
        mock_elb_client.list_members.return_value = _ns(members=[m1])

        # Health status response.
        health_member = _ns(id="m-1", address="10.0.1.1", protocol_port=8080,
                           operating_status="ONLINE", provisioning_status="ACTIVE")
        health_pool = _ns(id="pool-1", name="web-pool", operating_status="ACTIVE",
                         provisioning_status="ACTIVE", healthmonitor=None,
                         members=[health_member])
        status_lb = _ns(id="lb-1", name="web-lb", operating_status="ACTIVE",
                       provisioning_status="ACTIVE", listeners=[],
                       pools=[health_pool])
        mock_elb_client.show_load_balancer_status.return_value = _ns(
            statuses=_ns(loadbalancer=status_lb)
        )

        result = tools["elb_list_backend_members"](
            pool_id="pool-1", loadbalancer_id="lb-1"
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["health_status_available"] is True
        assert data["members"][0]["health_status"] == "ONLINE"


# ---------------------------------------------------------------------------
# elb_describe_forwarding_rules
# ---------------------------------------------------------------------------

class TestDescribeForwardingRules:
    def test_list(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        policy = _ns(id="pol-1", name="api-routing", action="REDIRECT_TO_POOL",
                     position=10, priority=None, listener_id="lis-1",
                     redirect_pool_id="pool-2", redirect_listener_id=None,
                     redirect_url=None, provisioning_status="ACTIVE",
                     admin_state_up=True, description="route /api to pool-2",
                     created_at="2024-01-01T00:00:00Z",
                     updated_at="2024-06-01T00:00:00Z", rules=[])
        mock_elb_client.list_l7_policies.return_value = _ns(l7policies=[policy])
        result = tools["elb_describe_forwarding_rules"]()
        assert result["ok"] is True
        assert result["data"]["forwarding_rules"][0]["action"] == "REDIRECT_TO_POOL"

    def test_detail_with_rules(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        policy = _ns(id="pol-1", name="api-routing", action="REDIRECT_TO_POOL",
                     position=10, priority=None, listener_id="lis-1",
                     redirect_pool_id="pool-2", redirect_listener_id=None,
                     redirect_url=None, provisioning_status="ACTIVE",
                     admin_state_up=True, description="route /api to pool-2",
                     created_at="2024-01-01T00:00:00Z",
                     updated_at="2024-06-01T00:00:00Z", rules=[])
        rule = _ns(id="rule-1", type="PATH", compare_type="STARTS_WITH",
                   value="/api", key=None, invert=False, admin_state_up=True,
                   provisioning_status="ACTIVE")
        mock_elb_client.show_l7_policy.return_value = _ns(l7policy=policy)
        mock_elb_client.list_l7_rules.return_value = _ns(rules=[rule])
        result = tools["elb_describe_forwarding_rules"](policy_id="pol-1")
        assert result["ok"] is True
        detail = result["data"]["forwarding_rule"]
        assert detail["rules"][0]["type"] == "PATH"
        assert detail["rules"][0]["value"] == "/api"


# ---------------------------------------------------------------------------
# elb_list_certificates
# ---------------------------------------------------------------------------

class TestListCertificates:
    def test_list(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        cert = _ns(id="cert-1", name="wildcard", domain="*.example.com",
                   type="server", admin_state_up=True,
                   expire_time="2025-12-31T23:59:59Z", common_name="*.example.com",
                   source="scm")
        mock_elb_client.list_certificates.return_value = _ns(certificates=[cert])
        result = tools["elb_list_certificates"]()
        assert result["ok"] is True
        assert result["data"]["certificates"][0]["domain"] == "*.example.com"

    def test_detail(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        cert = _ns(id="cert-1", name="wildcard", domain="*.example.com",
                   type="server", admin_state_up=True,
                   expire_time="2025-12-31T23:59:59Z", common_name="*.example.com",
                   source="scm", description="wildcard cert",
                   scm_certificate_id="scm-1", fingerprint="ab:cd:ef",
                   subject_alternative_names=["example.com", "app.example.com"],
                   created_at="2024-01-01T00:00:00Z",
                   updated_at="2024-06-01T00:00:00Z", protection_status=None,
                   enterprise_project_id=None)
        mock_elb_client.show_certificate.return_value = _ns(certificate=cert)
        result = tools["elb_list_certificates"](certificate_id="cert-1")
        assert result["ok"] is True
        assert result["data"]["certificate"]["fingerprint"] == "ab:cd:ef"


# ---------------------------------------------------------------------------
# elb_describe_access_log_config
# ---------------------------------------------------------------------------

class TestDescribeAccessLogConfig:
    def test_list(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        lt = _ns(id="lt-1", loadbalancer_id="lb-1",
                 log_group_id="lg-1", log_topic_id="lt-1")
        mock_elb_client.list_logtanks.return_value = _ns(logtanks=[lt])
        result = tools["elb_describe_access_log_config"]()
        assert result["ok"] is True
        assert result["data"]["access_log_configs"][0]["log_group_id"] == "lg-1"

    def test_detail(self, elb_settings, mock_elb_client):
        tools = make_query_tools(elb_settings)
        lt = _ns(id="lt-1", loadbalancer_id="lb-1",
                 log_group_id="lg-1", log_topic_id="lt-1")
        mock_elb_client.show_logtank.return_value = _ns(logtank=lt)
        result = tools["elb_describe_access_log_config"](logtank_id="lt-1")
        assert result["ok"] is True
        assert result["data"]["access_log_config"]["log_topic_id"] == "lt-1"


# ---------------------------------------------------------------------------
# elb_audit_health
# ---------------------------------------------------------------------------

class TestAuditHealth:
    def test_audit_pass(self, elb_settings, mock_elb_client):
        tools = make_audit_tools(elb_settings)
        lb = _ns(id="lb-1", name="web-lb",
                 availability_zone_list=["af-south-1a"])
        mock_elb_client.show_load_balancer.return_value = _ns(loadbalancer=lb)
        mock_elb_client.list_certificates.return_value = _ns(certificates=[])
        mock_elb_client.list_listeners.return_value = _ns(
            listeners=[_ns(id="lis-1", name="http", default_pool_id="pool-1")]
        )
        mock_elb_client.list_pools.return_value = _ns(
            pools=[_ns(id="pool-1", name="web-pool", healthmonitor_id="hm-1")]
        )
        mock_elb_client.list_members.return_value = _ns(members=[])
        mock_elb_client.show_load_balancer_status.return_value = _ns(
            statuses=_ns(loadbalancer=_ns(id="lb-1", pools=[], listeners=[]))
        )
        result = tools["elb_audit_health"](loadbalancer_id="lb-1")
        assert result["ok"] is True
        assert result["data"]["overall_status"] == "pass"

    def test_audit_cert_expiring(self, elb_settings, mock_elb_client):
        tools = make_audit_tools(elb_settings)
        lb = _ns(id="lb-1", name="web-lb", availability_zone_list=["af-south-1a"])
        mock_elb_client.show_load_balancer.return_value = _ns(loadbalancer=lb)
        # Certificate expiring in 10 days.
        from datetime import datetime, timedelta, timezone
        expiry = (datetime.now(timezone.utc) + timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        cert = _ns(id="cert-1", name="expiring", expire_time=expiry)
        mock_elb_client.list_certificates.return_value = _ns(certificates=[cert])
        mock_elb_client.list_listeners.return_value = _ns(listeners=[])
        mock_elb_client.list_pools.return_value = _ns(pools=[])
        result = tools["elb_audit_health"](
            loadbalancer_id="lb-1", cert_expiry_days=30
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["overall_status"] == "critical"
        assert any(r["category"] == "cert_expiring" for r in data["risk_items"])

    def test_audit_listener_no_pool(self, elb_settings, mock_elb_client):
        tools = make_audit_tools(elb_settings)
        lb = _ns(id="lb-1", name="web-lb", availability_zone_list=["af-south-1a"])
        mock_elb_client.show_load_balancer.return_value = _ns(loadbalancer=lb)
        mock_elb_client.list_certificates.return_value = _ns(certificates=[])
        mock_elb_client.list_listeners.return_value = _ns(
            listeners=[_ns(id="lis-1", name="http", default_pool_id=None)]
        )
        mock_elb_client.list_pools.return_value = _ns(pools=[])
        mock_elb_client.list_members.return_value = _ns(members=[])
        mock_elb_client.show_load_balancer_status.return_value = _ns(
            statuses=_ns(loadbalancer=_ns(id="lb-1", pools=[], listeners=[]))
        )
        result = tools["elb_audit_health"](loadbalancer_id="lb-1")
        assert result["ok"] is True
        data = result["data"]
        assert any(r["category"] == "listener_no_pool" for r in data["risk_items"])


# ---------------------------------------------------------------------------
# elb_manage_backend_member
# ---------------------------------------------------------------------------

class TestManageBackendMember:
    def test_add(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        member = _ns(id="m-1", name="backend-1", address="10.0.1.1",
                     protocol_port=8080, weight=100, admin_state_up=True,
                     operating_status="ONLINE", status=None,
                     subnet_cidr_id="subnet-1", availability_zone="af-south-1a",
                     member_type=None, instance_id=None, reason=None)
        mock_elb_client.create_member.return_value = _ns(member=member)
        result = tools["elb_manage_backend_member"](
            action="add", pool_id="pool-1", address="10.0.1.1", protocol_port=8080
        )
        assert result["ok"] is True
        assert result["data"]["member"]["address"] == "10.0.1.1"
        mock_elb_client.create_member.assert_called_once()

    def test_update_weight(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        member = _ns(id="m-1", name="backend-1", address="10.0.1.1",
                     protocol_port=8080, weight=0, admin_state_up=True,
                     operating_status="ONLINE", status=None,
                     subnet_cidr_id="subnet-1", availability_zone="af-south-1a",
                     member_type=None, instance_id=None, reason=None)
        mock_elb_client.update_member.return_value = _ns(member=member)
        result = tools["elb_manage_backend_member"](
            action="update_weight", pool_id="pool-1", member_id="m-1", weight=0
        )
        assert result["ok"] is True
        assert result["data"]["member"]["weight"] == 0

    def test_remove_two_phase(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        result = tools["elb_manage_backend_member"](
            action="remove", pool_id="pool-1", member_id="m-1"
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "pending_approval"
        assert "approval_id" in data
        # Member not deleted yet.
        mock_elb_client.delete_member.assert_not_called()

        # Confirm.
        confirm = tools["elb_confirm_destructive"]
        confirm_result = confirm(approval_id=data["approval_id"])
        assert confirm_result["ok"] is True
        assert confirm_result["data"]["deleted"] is True
        mock_elb_client.delete_member.assert_called_once()

    def test_add_missing_params(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        result = tools["elb_manage_backend_member"](
            action="add", pool_id="pool-1", address="10.0.1.1"
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "MISSING_PARAMS"


# ---------------------------------------------------------------------------
# elb_manage_listener
# ---------------------------------------------------------------------------

class TestManageListener:
    def test_create_two_phase(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        result = tools["elb_manage_listener"](
            action="create", loadbalancer_id="lb-1",
            protocol="HTTP", protocol_port=8080, name="new-listener"
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "pending_approval"
        mock_elb_client.create_listener.assert_not_called()

        # Set up mock for the actual create.
        lis = _ns(id="lis-new", name="new-listener", protocol="HTTP",
                  protocol_port=8080, operating_status="ACTIVE",
                  provisioning_status="ACTIVE", admin_state_up=True,
                  loadbalancers=[_ns(id="lb-1")], default_pool_id=None,
                  default_tls_container_ref=None)
        mock_elb_client.create_listener.return_value = _ns(listener=lis)

        confirm = tools["elb_confirm_destructive"]
        confirm_result = confirm(approval_id=data["approval_id"])
        assert confirm_result["ok"] is True
        assert confirm_result["data"]["listener"]["id"] == "lis-new"
        mock_elb_client.create_listener.assert_called_once()

    def test_update(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        lis = _ns(id="lis-1", name="http-80", protocol="HTTP", protocol_port=80,
                  operating_status="ACTIVE", provisioning_status="ACTIVE",
                  admin_state_up=True, loadbalancers=[_ns(id="lb-1")],
                  default_pool_id="pool-1", default_tls_container_ref=None)
        mock_elb_client.update_listener.return_value = _ns(listener=lis)
        result = tools["elb_manage_listener"](
            action="update", listener_id="lis-1", keepalive_timeout=120
        )
        assert result["ok"] is True
        assert result["data"]["listener"]["id"] == "lis-1"

    def test_replace_certificate(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        lis = _ns(id="lis-1", name="https-443", protocol="HTTPS",
                  protocol_port=443, operating_status="ACTIVE",
                  provisioning_status="ACTIVE", admin_state_up=True,
                  loadbalancers=[_ns(id="lb-1")], default_pool_id="pool-1",
                  default_tls_container_ref="cert-new")
        mock_elb_client.update_listener.return_value = _ns(listener=lis)
        result = tools["elb_manage_listener"](
            action="replace_certificate", listener_id="lis-1",
            certificate_id="cert-new"
        )
        assert result["ok"] is True
        assert result["data"]["certificate_replaced"] is True
        assert result["data"]["new_certificate_id"] == "cert-new"


# ---------------------------------------------------------------------------
# elb_manage_forwarding_rule
# ---------------------------------------------------------------------------

class TestManageForwardingRule:
    def test_create(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        policy = _ns(id="pol-1", name="api-route", action="REDIRECT_TO_POOL",
                     position=10, priority=None, listener_id="lis-1",
                     redirect_pool_id="pool-2", redirect_listener_id=None,
                     redirect_url=None, provisioning_status="ACTIVE",
                     admin_state_up=True)
        mock_elb_client.create_l7_policy.return_value = _ns(l7policy=policy)
        result = tools["elb_manage_forwarding_rule"](
            action="create", listener_id="lis-1", name="api-route",
            redirect_pool_id="pool-2", rule_type="PATH",
            rule_compare_type="STARTS_WITH", rule_value="/api"
        )
        assert result["ok"] is True
        assert result["data"]["policy"]["action"] == "REDIRECT_TO_POOL"
        mock_elb_client.create_l7_policy.assert_called_once()
        # Rule creation should also have been called.
        mock_elb_client.create_l7_rule.assert_called_once()

    def test_create_without_rule(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        policy = _ns(id="pol-1", name="host-route", action="REDIRECT_TO_POOL",
                     position=10, priority=None, listener_id="lis-1",
                     redirect_pool_id="pool-2", redirect_listener_id=None,
                     redirect_url=None, provisioning_status="ACTIVE",
                     admin_state_up=True)
        mock_elb_client.create_l7_policy.return_value = _ns(l7policy=policy)
        result = tools["elb_manage_forwarding_rule"](
            action="create", listener_id="lis-1", name="host-route",
            redirect_pool_id="pool-2"
        )
        assert result["ok"] is True
        mock_elb_client.create_l7_rule.assert_not_called()

    def test_delete_two_phase(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        result = tools["elb_manage_forwarding_rule"](
            action="delete", policy_id="pol-1"
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "pending_approval"
        mock_elb_client.delete_l7_policy.assert_not_called()

        confirm = tools["elb_confirm_destructive"]
        confirm_result = confirm(approval_id=data["approval_id"])
        assert confirm_result["ok"] is True
        assert confirm_result["data"]["deleted"] is True
        mock_elb_client.delete_l7_policy.assert_called_once()


# ---------------------------------------------------------------------------
# elb_set_connection_drain
# ---------------------------------------------------------------------------

class TestSetConnectionDrain:
    def test_enable(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        pool = _ns(id="pool-1", connection_drain=_ns(enable=True, timeout=60))
        mock_elb_client.update_pool.return_value = _ns(pool=pool)
        result = tools["elb_set_connection_drain"](
            pool_id="pool-1", enable=True, timeout=60
        )
        assert result["ok"] is True
        assert result["data"]["connection_drain"]["enable"] is True
        assert result["data"]["connection_drain"]["timeout"] == 60
        mock_elb_client.update_pool.assert_called_once()

    def test_disable(self, elb_settings, mock_elb_client):
        tools = make_manage_tools(elb_settings)
        pool = _ns(id="pool-1", connection_drain=_ns(enable=False, timeout=0))
        mock_elb_client.update_pool.return_value = _ns(pool=pool)
        result = tools["elb_set_connection_drain"](
            pool_id="pool-1", enable=False
        )
        assert result["ok"] is True
        assert result["data"]["connection_drain"]["enable"] is False
