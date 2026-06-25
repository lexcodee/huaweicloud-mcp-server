"""Tests for RDS MCP tools.

Covers:
  - Server registration (rds in ALL_SERVICES, tools appear)
  - rds_describe_instances (list + detail dispatch)
  - rds_get_db_logs (error + slow query dispatch)
  - rds_list_db_resources (databases + accounts dispatch)
  - rds_list_backups
  - rds_describe_parameter_group (list + config + instance dispatch)
  - rds_list_replicas
  - rds_create_manual_backup (two-phase commit)
  - rds_audit_instance_security
  - rds_get_instance_metrics (cross-call CES)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.server import ALL_SERVICES, build_server
from huaweicloud_mcp.services.rds.tools.query import make_query_tools
from huaweicloud_mcp.services.rds.tools.logs import make_log_tools
from huaweicloud_mcp.services.rds.tools.manage import make_manage_tools
from huaweicloud_mcp.services.rds.tools.audit import make_audit_tools
from huaweicloud_mcp.services.rds.tools.metrics import make_metrics_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rds_settings() -> Settings:
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        default_timezone="Asia/Shanghai",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def mock_rds_client(monkeypatch):
    """Replace get_client('rds', ...) with a MagicMock in all RDS tool modules."""
    fake = MagicMock(name="RdsClient")
    for mod in (
        "huaweicloud_mcp.services.rds.tools.query",
        "huaweicloud_mcp.services.rds.tools.logs",
        "huaweicloud_mcp.services.rds.tools.manage",
        "huaweicloud_mcp.services.rds.tools.audit",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


@pytest.fixture
def mock_rds_and_ces_clients(monkeypatch):
    """Replace get_client with a dispatcher returning rds or ces_v1 mock."""
    rds_fake = MagicMock(name="RdsClient")
    ces_fake = MagicMock(name="CesV1Client")

    def _get_client(service, settings):
        if service == "ces_v1":
            return ces_fake
        return rds_fake

    for mod in (
        "huaweicloud_mcp.services.rds.tools.query",
        "huaweicloud_mcp.services.rds.tools.logs",
        "huaweicloud_mcp.services.rds.tools.manage",
        "huaweicloud_mcp.services.rds.tools.audit",
        "huaweicloud_mcp.services.rds.tools.metrics",
    ):
        monkeypatch.setattr(f"{mod}.get_client", _get_client)
    return rds_fake, ces_fake


@pytest.fixture
def env_credentials(monkeypatch):
    monkeypatch.setenv("HUAWEICLOUD_ACCESS_KEY_ID", "AKID" + "X" * 16)
    monkeypatch.setenv("HUAWEICLOUD_SECRET_ACCESS_KEY", "SK" + "Y" * 38)
    monkeypatch.setenv("HUAWEICLOUD_REGION", "af-south-1")
    monkeypatch.setenv("HUAWEICLOUD_PROJECT_ID", "15f2d47addb14784b82eb910447250a9")


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------

def test_rds_is_in_all_services():
    assert "rds" in ALL_SERVICES


def test_build_server_registers_rds_tools(env_credentials):
    mcp = build_server(enabled=["rds"])
    tm = getattr(mcp, "_tool_manager", None)
    assert tm is not None
    names = set(tm._tools.keys())
    expected = {
        "rds_describe_instances",
        "rds_get_db_logs",
        "rds_list_db_resources",
        "rds_list_backups",
        "rds_get_instance_metrics",
        "rds_describe_parameter_group",
        "rds_list_replicas",
        "rds_create_manual_backup",
        "rds_audit_instance_security",
        "rds_confirm_destructive",
    }
    assert expected.issubset(names), f"Missing: {expected - names}"


# ---------------------------------------------------------------------------
# rds_describe_instances
# ---------------------------------------------------------------------------

class TestDescribeInstances:
    def test_list_mode(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.list_instances.return_value = _ns(
            instances=[
                _ns(
                    id="rds-001", name="db-prod", status="ACTIVE",
                    type="Single", datastore=_ns(type="MySQL", version="8.0"),
                    flavor_ref="rds.mysql.x1.large.2", cpu="4", mem="8",
                    private_ips=["10.0.0.1"], public_ips=[],
                    port=3306, enable_ssl=True,
                ),
            ],
            total_count=1,
        )
        result = tools["rds_describe_instances"]()
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 1
        assert data["instances"][0]["id"] == "rds-001"
        assert data["instances"][0]["engine"] == "MySQL"

    def test_detail_mode(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.list_instances.return_value = _ns(
            instances=[
                _ns(
                    id="rds-001", name="db-prod", status="ACTIVE",
                    type="Single", datastore=_ns(type="MySQL", version="8.0"),
                    flavor_ref="rds.mysql.x1.large.2", cpu="4", mem="8",
                    private_ips=["10.0.0.1"], public_ips=[],
                    port=3306, enable_ssl=True,
                    volume=_ns(type="ULTRAHIGH", size=200),
                    nodes=[_ns(id="n1", name="node-1", role="master", status="ACTIVE")],
                    related_instance=[],
                    backup_strategy=_ns(start_time="00:00-01:00", keep_days=7),
                    vpc_id="vpc-1", subnet_id="sub-1",
                    security_group_id="sg-1", max_iops=2000,
                ),
            ],
            total_count=1,
        )
        result = tools["rds_describe_instances"](instance_id="rds-001")
        assert result["ok"] is True
        inst = result["data"]["instance"]
        assert inst["id"] == "rds-001"
        assert inst["volume"]["size_gb"] == 200
        assert len(inst["nodes"]) == 1

    def test_detail_not_found(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.list_instances.return_value = _ns(instances=[], total_count=0)
        result = tools["rds_describe_instances"](instance_id="nonexistent")
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# rds_get_db_logs
# ---------------------------------------------------------------------------

class TestGetDbLogs:
    def test_error_logs(self, rds_settings, mock_rds_client):
        tools = make_log_tools(rds_settings)
        mock_rds_client.list_error_logs_new.return_value = _ns(
            error_log_list=[
                _ns(time="2024-01-01T00:00:00", level="ERROR", content="Too many connections"),
            ],
            total_record=1,
        )
        result = tools["rds_get_db_logs"](
            instance_id="rds-001", log_type="error", start_time="-1h",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["total_record"] == 1
        assert data["error_logs"][0]["content"] == "Too many connections"

    def test_slow_query_logs(self, rds_settings, mock_rds_client):
        tools = make_log_tools(rds_settings)
        mock_rds_client.list_slowlog_statistics.return_value = _ns(
            slow_log_list=[
                _ns(
                    count="15", time="2500", lock_time="100",
                    rows_sent=100, rows_examined=50000,
                    database="mydb", users="root",
                    query_sample="SELECT * FROM orders WHERE status='pending'",
                    type="SELECT", client_ip="10.0.0.5",
                ),
            ],
            total_record=1,
            page_number=1, page_record=1,
            start_time=0, end_time=0,
        )
        result = tools["rds_get_db_logs"](
            instance_id="rds-001", log_type="slow",
            sort_by="count", min_duration_ms=1000,
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["sort_by"] == "count"
        assert len(data["slow_queries"]) == 1
        sq = data["slow_queries"][0]
        assert sq["avg_duration_ms"] == 2500.0
        assert sq["execution_count"] == 15
        assert "SELECT" in sq["sql_text"]

    def test_slow_query_min_duration_filter(self, rds_settings, mock_rds_client):
        tools = make_log_tools(rds_settings)
        mock_rds_client.list_slowlog_statistics.return_value = _ns(
            slow_log_list=[
                _ns(count="5", time="500", lock_time="0",
                    rows_sent=1, rows_examined=10, database="db1",
                    users="u1", query_sample="SELECT 1", type="SELECT", client_ip=""),
                _ns(count="10", time="3000", lock_time="50",
                    rows_sent=100, rows_examined=50000, database="db1",
                    users="u1", query_sample="SELECT * FROM big_table", type="SELECT", client_ip=""),
            ],
            total_record=2,
            page_number=1, page_record=2,
            start_time=0, end_time=0,
        )
        result = tools["rds_get_db_logs"](
            instance_id="rds-001", log_type="slow",
            min_duration_ms=1000,
        )
        assert result["ok"] is True
        data = result["data"]
        # Only the 3000ms query should pass the 1000ms filter
        assert len(data["slow_queries"]) == 1
        assert data["slow_queries"][0]["avg_duration_ms"] == 3000.0

    def test_slow_query_database_filter(self, rds_settings, mock_rds_client):
        tools = make_log_tools(rds_settings)
        mock_rds_client.list_slowlog_statistics.return_value = _ns(
            slow_log_list=[
                _ns(count="5", time="2000", lock_time="0",
                    rows_sent=1, rows_examined=10, database="db1",
                    users="u1", query_sample="SELECT 1", type="SELECT", client_ip=""),
                _ns(count="10", time="3000", lock_time="50",
                    rows_sent=100, rows_examined=50000, database="db2",
                    users="u1", query_sample="SELECT * FROM big_table", type="SELECT", client_ip=""),
            ],
            total_record=2,
            page_number=1, page_record=2,
            start_time=0, end_time=0,
        )
        result = tools["rds_get_db_logs"](
            instance_id="rds-001", log_type="slow",
            database="db2", min_duration_ms=0,
        )
        assert result["ok"] is True
        data = result["data"]
        assert len(data["slow_queries"]) == 1
        assert data["slow_queries"][0]["database"] == "db2"


# ---------------------------------------------------------------------------
# rds_list_db_resources
# ---------------------------------------------------------------------------

class TestListDbResources:
    def test_list_databases(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.list_databases.return_value = _ns(
            databases=[
                _ns(name="mydb", character_set="utf8mb4", comment="main db"),
            ],
            total_count=1,
        )
        result = tools["rds_list_db_resources"](
            instance_id="rds-001", resource_type="databases",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["databases"][0]["name"] == "mydb"
        assert data["databases"][0]["character_set"] == "utf8mb4"

    def test_list_accounts(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.list_db_users.return_value = _ns(
            users=[
                _ns(
                    name="root",
                    hosts=["%", "10.0.0.%"],
                    comment="admin",
                    databases=[_ns(name="mydb", readonly=False)],
                ),
            ],
            total_count=1,
        )
        result = tools["rds_list_db_resources"](
            instance_id="rds-001", resource_type="accounts",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["accounts"][0]["name"] == "root"
        assert "%" in data["accounts"][0]["hosts"]
        assert data["accounts"][0]["databases"][0]["name"] == "mydb"


# ---------------------------------------------------------------------------
# rds_list_backups
# ---------------------------------------------------------------------------

class TestListBackups:
    def test_list_backups(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.list_backups.return_value = _ns(
            backups=[
                _ns(
                    id="bk-001", instance_id="rds-001", name="manual-1",
                    type="manual", status="COMPLETED", size=102400,
                    begin_time="2024-01-01T00:00:00Z", end_time="2024-01-01T00:05:00Z",
                ),
            ],
            total_count=1,
        )
        result = tools["rds_list_backups"](instance_id="rds-001")
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 1
        assert data["backups"][0]["id"] == "bk-001"
        assert data["backups"][0]["type"] == "manual"


# ---------------------------------------------------------------------------
# rds_describe_parameter_group
# ---------------------------------------------------------------------------

class TestDescribeParameterGroup:
    def test_list_all(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.list_configurations.return_value = _ns(
            configurations=[
                _ns(
                    id="cfg-1", name="mysql-default",
                    description="default config",
                    datastore_name="mysql", datastore_version_name="8.0",
                    created="2024-01-01", updated="2024-01-01",
                ),
            ],
        )
        result = tools["rds_describe_parameter_group"]()
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 1
        assert data["configurations"][0]["id"] == "cfg-1"

    def test_show_config(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.show_configuration.return_value = _ns(
            id="cfg-1", name="mysql-default",
            description="default config",
            datastore_name="mysql", datastore_version_name="8.0",
            created="2024-01-01", updated="2024-01-01",
            configuration_parameters=[
                _ns(
                    name="innodb_buffer_pool_size", value="134217728",
                    value_range="524288-9223372036854775807",
                    restart_required=True, readonly=False,
                    type="integer", description="Buffer pool size",
                ),
            ],
        )
        result = tools["rds_describe_parameter_group"](config_id="cfg-1")
        assert result["ok"] is True
        cfg = result["data"]["configuration"]
        assert cfg["id"] == "cfg-1"
        assert len(cfg["parameters"]) == 1
        assert cfg["parameters"][0]["name"] == "innodb_buffer_pool_size"
        assert cfg["parameters"][0]["current_value"] == "134217728"

    def test_show_instance_config(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        mock_rds_client.show_instance_configuration.return_value = _ns(
            datastore_name="mysql", datastore_version_name="8.0",
            created="2024-01-01", updated="2024-01-01",
            configuration_parameters=[
                _ns(
                    name="max_connections", value="2000",
                    value_range="1-100000",
                    restart_required=False, readonly=False,
                    type="integer", description="Max connections",
                ),
            ],
        )
        result = tools["rds_describe_parameter_group"](instance_id="rds-001")
        assert result["ok"] is True
        data = result["data"]
        assert data["instance_id"] == "rds-001"
        assert data["parameters"][0]["name"] == "max_connections"


# ---------------------------------------------------------------------------
# rds_list_replicas
# ---------------------------------------------------------------------------

class TestListReplicas:
    def test_list_replicas(self, rds_settings, mock_rds_client):
        tools = make_query_tools(rds_settings)
        # Primary instance with a replica
        mock_rds_client.list_instances.side_effect = [
            _ns(instances=[_ns(
                id="rds-primary", name="db-primary", status="ACTIVE",
                type="Single", datastore=_ns(type="MySQL", version="8.0"),
                flavor_ref="rds.mysql.x1.large.2", cpu="4", mem="8",
                private_ips=["10.0.0.1"], public_ips=[], port=3306,
                enable_ssl=True,
                related_instance=[_ns(id="rds-replica-1", type="replica")],
            )], total_count=1),
            # Replica instance detail
            _ns(instances=[_ns(
                id="rds-replica-1", name="db-replica-1", status="ACTIVE",
                type="Single", datastore=_ns(type="MySQL", version="8.0"),
                flavor_ref="rds.mysql.x1.large.2", cpu="4", mem="8",
                private_ips=["10.0.0.2"], public_ips=[], port=3306,
                enable_ssl=True,
            )], total_count=1),
        ]
        mock_rds_client.show_replication_status.return_value = _ns(
            replication_status="NORMAL", abnormal_reason=None,
        )
        result = tools["rds_list_replicas"](instance_id="rds-primary")
        assert result["ok"] is True
        data = result["data"]
        assert data["primary_id"] == "rds-primary"
        assert data["replica_count"] == 1
        assert data["replicas"][0]["id"] == "rds-replica-1"
        assert data["replication_status"]["replication_status"] == "NORMAL"


# ---------------------------------------------------------------------------
# rds_create_manual_backup (two-phase)
# ---------------------------------------------------------------------------

class TestCreateManualBackup:
    def test_phase1_returns_pending(self, rds_settings, mock_rds_client):
        tools = make_manage_tools(rds_settings)
        result = tools["rds_create_manual_backup"](
            instance_id="rds-001", name="pre-change-backup",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "pending_approval"
        assert "approval_id" in data
        # Should NOT have called the SDK yet
        mock_rds_client.create_manual_backup.assert_not_called()

    def test_phase2_executes(self, rds_settings, mock_rds_client):
        tools = make_manage_tools(rds_settings)
        # Phase 1
        r1 = tools["rds_create_manual_backup"](
            instance_id="rds-001", name="pre-change-backup",
        )
        approval_id = r1["data"]["approval_id"]

        # Phase 2
        mock_rds_client.create_manual_backup.return_value = _ns(
            backup=_ns(
                id="bk-new", instance_id="rds-001", name="pre-change-backup",
                begin_time="2024-01-01T00:00:00Z", status="BUILDING", type="manual",
            ),
        )
        r2 = tools["rds_confirm_destructive"](approval_id=approval_id)
        assert r2["ok"] is True
        assert r2["data"]["id"] == "bk-new"
        mock_rds_client.create_manual_backup.assert_called_once()

    def test_phase2_expired(self, rds_settings, mock_rds_client):
        tools = make_manage_tools(rds_settings)
        result = tools["rds_confirm_destructive"](approval_id="nonexistent")
        assert result["ok"] is False
        assert result["error"]["code"] == "APPROVAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# rds_audit_instance_security
# ---------------------------------------------------------------------------

class TestAuditInstanceSecurity:
    def test_clean_instance(self, rds_settings, mock_rds_client):
        tools = make_audit_tools(rds_settings)
        mock_rds_client.list_instances.return_value = _ns(
            instances=[_ns(
                id="rds-001", name="db-prod", status="ACTIVE",
                type="Single", datastore=_ns(type="MySQL", version="8.0"),
                flavor_ref="rds.mysql.x1.large.2", cpu="4", mem="8",
                private_ips=["10.0.0.1"], public_ips=[],
                port=3306, enable_ssl=True,
                volume=_ns(type="ULTRAHIGH", size=200),
                storage_used_space=50.0,
                related_instance=[_ns(id="rds-replica", type="replica")],
            )],
            total_count=1,
        )
        # Recent backup
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        mock_rds_client.list_backups.return_value = _ns(
            backups=[_ns(id="bk-1", begin_time=recent)],
            total_count=1,
        )
        # No root with %
        mock_rds_client.list_db_users.return_value = _ns(
            users=[_ns(name="appuser", hosts=["10.0.0.%"], comment="", databases=[])],
            total_count=1,
        )
        result = tools["rds_audit_instance_security"](instance_id="rds-001")
        assert result["ok"] is True
        data = result["data"]
        assert data["overall_status"] == "pass"
        assert data["risk_count"] == 0

    def test_risky_instance(self, rds_settings, mock_rds_client):
        tools = make_audit_tools(rds_settings)
        mock_rds_client.list_instances.return_value = _ns(
            instances=[_ns(
                id="rds-002", name="db-risky", status="ACTIVE",
                type="Single", datastore=_ns(type="MySQL", version="8.0"),
                flavor_ref="rds.mysql.x1.large.2", cpu="4", mem="8",
                private_ips=["10.0.0.1"], public_ips=["1.2.3.4"],
                port=3306, enable_ssl=False,
                volume=_ns(type="ULTRAHIGH", size=100),
                storage_used_space=90.0,  # 90%
                related_instance=[],  # no replica
            )],
            total_count=1,
        )
        # No recent backups
        mock_rds_client.list_backups.return_value = _ns(backups=[], total_count=0)
        # root with %
        mock_rds_client.list_db_users.return_value = _ns(
            users=[_ns(
                name="root", hosts=["%"], comment="",
                databases=[_ns(name="mydb", readonly=False)],
            )],
            total_count=1,
        )
        result = tools["rds_audit_instance_security"](instance_id="rds-002")
        assert result["ok"] is True
        data = result["data"]
        assert data["overall_status"] == "critical"
        assert data["high_risk_count"] >= 4  # public_ip, ssl, storage, no_backup, root_remote
        categories = [r["category"] for r in data["risk_items"]]
        assert "public_exposure" in categories
        assert "ssl_disabled" in categories
        assert "storage_near_full" in categories
        assert "no_recent_backup" in categories
        assert "root_remote_access" in categories

    def test_not_found(self, rds_settings, mock_rds_client):
        tools = make_audit_tools(rds_settings)
        mock_rds_client.list_instances.return_value = _ns(instances=[], total_count=0)
        result = tools["rds_audit_instance_security"](instance_id="nonexistent")
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# rds_get_instance_metrics (cross-call CES)
# ---------------------------------------------------------------------------

class TestGetInstanceMetrics:
    def test_default_metrics(self, rds_settings, mock_rds_and_ces_clients):
        rds_fake, ces_fake = mock_rds_and_ces_clients
        tools = make_metrics_tools(rds_settings)
        ces_fake.show_metric_data.return_value = _ns(
            datapoints=[_ns(timestamp=1700000000000, average=45.2, unit="%")],
            metric_name="rds001_cpu_util",
        )
        result = tools["rds_get_instance_metrics"](
            instance_id="rds-001", from_time="-30m",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["total_returned"] == 5  # 5 default metrics
        assert data["results"][0]["metric_name"] == "rds001_cpu_util"
        assert data["results"][0]["data_points"][0]["value"] == 45.2

    def test_custom_metrics(self, rds_settings, mock_rds_and_ces_clients):
        rds_fake, ces_fake = mock_rds_and_ces_clients
        tools = make_metrics_tools(rds_settings)
        ces_fake.show_metric_data.return_value = _ns(
            datapoints=[_ns(timestamp=1700000000000, average=100, unit="count")],
        )
        result = tools["rds_get_instance_metrics"](
            instance_id="rds-001",
            metrics=["rds004_connections"],
            from_time="-5m",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["total_returned"] == 1
        assert data["results"][0]["metric_name"] == "rds004_connections"
