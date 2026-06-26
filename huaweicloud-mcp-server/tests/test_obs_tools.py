"""Tests for OBS MCP tools.

Covers:
  - Server registration (obs in ALL_SERVICES, tools appear)
  - obs_describe_buckets (list + detail dispatch)
  - obs_list_objects (current + versions dispatch)
  - obs_get_object (metadata + content dispatch)
  - obs_generate_presigned_url
  - obs_describe_bucket_policy
  - obs_describe_bucket_lifecycle
  - obs_upload_object
  - obs_delete_object (two-phase commit)
  - obs_create_bucket
  - obs_set_bucket_policy (two-phase commit)
  - obs_confirm_destructive
  - obs_audit_bucket_security
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from huaweicloud_mcp.config import Settings
from huaweicloud_mcp.server import ALL_SERVICES, build_server
from huaweicloud_mcp.services.obs.tools.query import make_query_tools
from huaweicloud_mcp.services.obs.tools.manage import make_manage_tools
from huaweicloud_mcp.services.obs.tools.audit import make_audit_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def obs_settings() -> Settings:
    return Settings(
        access_key_id="AKID" + "X" * 16,
        secret_access_key="SK" + "Y" * 38,
        project_id="15f2d47addb14784b82eb910447250a9",
        region="af-south-1",
        log_file=None,
        log_level="INFO",
    )


@pytest.fixture
def mock_obs_client(monkeypatch):
    """Replace get_client('obs', ...) with a MagicMock in all OBS tool modules."""
    fake = MagicMock(name="ObsClient")
    for mod in (
        "huaweicloud_mcp.services.obs.tools.query",
        "huaweicloud_mcp.services.obs.tools.manage",
        "huaweicloud_mcp.services.obs.tools.audit",
    ):
        monkeypatch.setattr(f"{mod}.get_client", lambda service, settings, _f=fake: _f)
    return fake


# ---------------------------------------------------------------------------
# Server registration
# ---------------------------------------------------------------------------

class TestServerRegistration:
    def test_obs_in_all_services(self):
        assert "obs" in ALL_SERVICES

    def test_build_server_registers_obs_tools(self, obs_settings, monkeypatch):
        monkeypatch.setenv("MCP_ENABLED_SERVICES", "obs")
        server = build_server(settings=obs_settings)
        tool_names = set(server._tool_manager._tools.keys())
        obs_tools = {n for n in tool_names if n.startswith("obs_")}
        expected = {
            "obs_describe_buckets",
            "obs_list_objects",
            "obs_get_object",
            "obs_generate_presigned_url",
            "obs_describe_bucket_policy",
            "obs_describe_bucket_lifecycle",
            "obs_upload_object",
            "obs_delete_object",
            "obs_create_bucket",
            "obs_set_bucket_policy",
            "obs_confirm_destructive",
            "obs_audit_bucket_security",
        }
        assert expected <= obs_tools, f"Missing: {expected - obs_tools}"


# ---------------------------------------------------------------------------
# obs_describe_buckets
# ---------------------------------------------------------------------------

class TestDescribeBuckets:
    def test_list_all_buckets(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        owner = _ns(id="owner-123")
        b1 = _ns(name="bucket-a", creation_date="2024-01-01T00:00:00Z", location="af-south-1")
        b2 = _ns(name="bucket-b", creation_date="2024-02-01T00:00:00Z", location="cn-north-4")
        buckets_obj = _ns(buckets=[b1, b2])
        mock_obs_client.list_buckets.return_value = _ns(
            owner=owner, buckets=buckets_obj,
        )

        result = tools["obs_describe_buckets"]()
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 2
        assert data["buckets"][0]["name"] == "bucket-a"
        assert data["owner_id"] == "owner-123"

    def test_bucket_detail(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        mock_obs_client.get_bucket_metadata.return_value = _ns(
            x_obs_storage_class="STANDARD",
            x_obs_version="Enabled",
            x_obs_bucket_location="af-south-1",
            x_obs_epid=None,
            x_obs_az_redundancy=None,
            x_obs_fs_file_interface=None,
        )
        mock_obs_client.get_bucket_acl.return_value = _ns(
            owner=_ns(id="owner-123"),
            access_control_list=_ns(grant=[
                _ns(grantee=_ns(canned="AllUsers", id=None), permission="READ", delivered=None),
            ]),
        )
        mock_obs_client.get_bucket_public_status.return_value = _ns(is_public=True)

        result = tools["obs_describe_buckets"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        bucket = data["bucket"]
        assert bucket["name"] == "my-bucket"
        assert bucket["storage_class"] == "STANDARD"
        assert bucket["versioning"] == "Enabled"
        assert bucket["is_public"] is True
        assert len(bucket["acl_grants"]) == 1


# ---------------------------------------------------------------------------
# obs_list_objects
# ---------------------------------------------------------------------------

class TestListObjects:
    def test_list_current_objects(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        o1 = _ns(key="file1.txt", size=1024, last_modified="2024-01-01", e_tag="etag1", storage_class="STANDARD", type=None)
        o2 = _ns(key="dir/file2.txt", size=2048, last_modified="2024-01-02", e_tag="etag2", storage_class="STANDARD", type=None)
        mock_obs_client.list_objects.return_value = _ns(
            contents=[o1, o2],
            common_prefixes=[],
            is_truncated=False,
            next_marker=None,
        )

        result = tools["obs_list_objects"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 2
        assert data["objects"][0]["key"] == "file1.txt"
        assert data["is_truncated"] is False

    def test_list_with_prefix_and_delimiter(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        mock_obs_client.list_objects.return_value = _ns(
            contents=[_ns(key="dir/a.txt", size=100, last_modified="2024-01-01", e_tag="e1", storage_class=None, type=None)],
            common_prefixes=[_ns(prefix="dir/sub/")],
            is_truncated=False,
            next_marker=None,
        )

        result = tools["obs_list_objects"](
            bucket_name="my-bucket", prefix="dir/", delimiter="/",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["common_prefixes"] == ["dir/sub/"]

    def test_list_with_versions(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        v1 = _ns(key="file.txt", version_id="v1", size=100, last_modified="2024-01-01", e_tag="e1", storage_class="STANDARD", is_latest=True, delete_marker=None, type=None)
        v2 = _ns(key="file.txt", version_id="v2", size=200, last_modified="2024-01-02", e_tag="e2", storage_class="STANDARD", is_latest=False, delete_marker=None, type=None)
        mock_obs_client.list_objects.return_value = _ns(
            versions=[v1, v2],
            delete_markers=[],
            contents=None,
            common_prefixes=[],
            is_truncated=False,
            next_marker=None,
        )

        result = tools["obs_list_objects"](
            bucket_name="my-bucket", include_versions=True,
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["total_count"] == 2
        assert data["objects"][0]["version_id"] == "v1"
        assert data["objects"][0]["is_latest"] is True


# ---------------------------------------------------------------------------
# obs_get_object
# ---------------------------------------------------------------------------

class TestGetObject:
    def test_metadata_only(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        mock_obs_client.head_object.return_value = _ns(
            content_length=1024,
            e_tag="etag123",
            date="2024-01-01T00:00:00Z",
            x_obs_storage_class="STANDARD",
            content_type="text/plain",
            x_obs_server_side_encryption=None,
            x_obs_server_side_encryption_kms_key_id=None,
            x_obs_object_type=None,
            x_obs_version_id=None,
            status_code=200,
        )

        result = tools["obs_get_object"](
            bucket_name="my-bucket", object_key="config.json",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["key"] == "config.json"
        assert data["size"] == 1024
        assert data["etag"] == "etag123"
        assert "content" not in data

    def test_with_content(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        import io
        mock_obs_client.get_object.return_value = _ns(
            raw_content=io.BytesIO(b'{"key": "value"}'),
            content_length=16,
            e_tag="etag456",
            date="2024-01-01",
            x_obs_storage_class="STANDARD",
            content_type="application/json",
            x_obs_server_side_encryption=None,
            x_obs_server_side_encryption_kms_key_id=None,
            x_obs_object_type=None,
            x_obs_version_id=None,
            status_code=200,
        )

        result = tools["obs_get_object"](
            bucket_name="my-bucket", object_key="config.json", include_content=True,
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["content"] == '{"key": "value"}'


# ---------------------------------------------------------------------------
# obs_generate_presigned_url
# ---------------------------------------------------------------------------

class TestGeneratePresignedUrl:
    def test_get_url(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        result = tools["obs_generate_presigned_url"](
            bucket_name="my-bucket", object_key="file.txt", method="GET", expires=3600,
        )
        assert result["ok"] is True
        data = result["data"]
        assert "url" in data
        assert "AccessKeyId" in data["url"]
        assert "Expires" in data["url"]
        assert "Signature" in data["url"]
        assert data["method"] == "GET"
        assert data["expires_in"] == 3600

    def test_put_url(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        result = tools["obs_generate_presigned_url"](
            bucket_name="my-bucket", object_key="upload.txt", method="PUT", expires=7200,
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["method"] == "PUT"
        assert data["expires_in"] == 7200


# ---------------------------------------------------------------------------
# obs_describe_bucket_policy
# ---------------------------------------------------------------------------

class TestDescribeBucketPolicy:
    def test_get_policy(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        mock_obs_client.get_bucket_acl.return_value = _ns(
            owner=_ns(id="owner-123"),
            access_control_list=_ns(grant=[
                _ns(grantee=_ns(canned="AllUsers", id=None), permission="READ", delivered=None),
            ]),
        )
        mock_obs_client.get_bucket_public_status.return_value = _ns(is_public=False)

        result = tools["obs_describe_bucket_policy"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["bucket_name"] == "my-bucket"
        assert data["is_public"] is False
        assert len(data["acl"]["grants"]) == 1


# ---------------------------------------------------------------------------
# obs_describe_bucket_lifecycle
# ---------------------------------------------------------------------------

class TestDescribeBucketLifecycle:
    def test_lifecycle_success(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        import io
        xml_body = b"<LifecycleConfiguration><Rule><ID>rule1</ID></Rule></LifecycleConfiguration>"
        mock_obs_client.do_http_request.return_value = _ns(
            raw_content=io.BytesIO(xml_body),
        )

        result = tools["obs_describe_bucket_lifecycle"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["bucket_name"] == "my-bucket"
        assert "rule1" in data["lifecycle_xml"]

    def test_lifecycle_not_supported(self, obs_settings, mock_obs_client):
        tools = make_query_tools(obs_settings)
        mock_obs_client.do_http_request.side_effect = Exception("500 Internal Server Error")

        result = tools["obs_describe_bucket_lifecycle"](bucket_name="my-bucket")
        assert result["ok"] is False
        assert result["error"]["code"] == "LIFECYCLE_QUERY_FAILED"

    def test_lifecycle_no_config(self, obs_settings, mock_obs_client):
        """404 NoSuchLifecycleConfiguration is a valid 'no rules' response."""
        tools = make_query_tools(obs_settings)
        mock_obs_client.do_http_request.side_effect = Exception("404 NoSuchLifecycleConfiguration")

        result = tools["obs_describe_bucket_lifecycle"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["rules"] == []


# ---------------------------------------------------------------------------
# obs_upload_object
# ---------------------------------------------------------------------------

class TestUploadObject:
    def test_upload_text(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        mock_obs_client.put_object.return_value = _ns(
            e_tag="etag789", x_obs_version_id=None,
        )

        result = tools["obs_upload_object"](
            bucket_name="my-bucket",
            object_key="report.json",
            content='{"status": "ok"}',
            content_type="application/json",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["bucket"] == "my-bucket"
        assert data["key"] == "report.json"
        assert data["etag"] == "etag789"
        assert data["size"] == 16


# ---------------------------------------------------------------------------
# obs_delete_object (two-phase)
# ---------------------------------------------------------------------------

class TestDeleteObject:
    def test_delete_returns_pending(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        result = tools["obs_delete_object"](
            bucket_name="my-bucket", object_key="temp.txt",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "pending_approval"
        assert "approval_id" in data
        assert data["action"] == "delete_object"

    def test_delete_confirm_executes(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        mock_obs_client.delete_object.return_value = _ns(
            x_obs_version_id=None, x_obs_delete_marker=None,
        )

        # Phase 1
        r1 = tools["obs_delete_object"](
            bucket_name="my-bucket", object_key="temp.txt",
        )
        approval_id = r1["data"]["approval_id"]

        # Phase 2
        r2 = tools["obs_confirm_destructive"](approval_id=approval_id)
        assert r2["ok"] is True
        assert r2["data"]["deleted"] is True
        assert r2["data"]["key"] == "temp.txt"


# ---------------------------------------------------------------------------
# obs_create_bucket
# ---------------------------------------------------------------------------

class TestCreateBucket:
    def test_create_private_bucket(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        mock_obs_client.create_bucket.return_value = _ns()

        result = tools["obs_create_bucket"](bucket_name="new-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["created"] is True
        assert data["bucket"] == "new-bucket"
        assert data["acl"] == "private"

    def test_create_with_location_and_storage(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        mock_obs_client.create_bucket.return_value = _ns()

        result = tools["obs_create_bucket"](
            bucket_name="new-bucket",
            location="cn-north-4",
            storage_class="WARM",
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["location"] == "cn-north-4"
        assert data["storage_class"] == "WARM"


# ---------------------------------------------------------------------------
# obs_set_bucket_policy (two-phase)
# ---------------------------------------------------------------------------

class TestSetBucketPolicy:
    def test_set_policy_returns_pending(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        policy = '{"Statement": [{"Effect": "Allow", "Principal": "*", "Action": "obs:GetObject", "Resource": "my-bucket/*"}]}'

        result = tools["obs_set_bucket_policy"](
            bucket_name="my-bucket", policy=policy,
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "pending_approval"
        assert data["action"] == "set_bucket_policy"

    def test_set_policy_confirm_executes(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        mock_obs_client.set_bucket_policy.return_value = _ns()
        policy = '{"Statement": []}'

        r1 = tools["obs_set_bucket_policy"](
            bucket_name="my-bucket", policy=policy,
        )
        approval_id = r1["data"]["approval_id"]

        r2 = tools["obs_confirm_destructive"](approval_id=approval_id)
        assert r2["ok"] is True
        assert r2["data"]["updated"] is True


# ---------------------------------------------------------------------------
# obs_confirm_destructive — error cases
# ---------------------------------------------------------------------------

class TestConfirmDestructive:
    def test_invalid_approval_id(self, obs_settings, mock_obs_client):
        tools = make_manage_tools(obs_settings)
        result = tools["obs_confirm_destructive"](approval_id="nonexistent")
        assert result["ok"] is False
        assert result["error"]["code"] == "APPROVAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# obs_audit_bucket_security
# ---------------------------------------------------------------------------

class TestAuditBucketSecurity:
    def test_clean_bucket(self, obs_settings, mock_obs_client):
        tools = make_audit_tools(obs_settings)
        mock_obs_client.get_bucket_public_status.return_value = _ns(is_public=False)
        mock_obs_client.get_bucket_acl.return_value = _ns(
            owner=_ns(id="owner-123"),
            access_control_list=_ns(grant=[
                _ns(grantee=_ns(canned="CanonicalUser", id="owner-123"), permission="FULL_CONTROL", delivered=None),
            ]),
        )
        mock_obs_client.get_bucket_metadata.return_value = _ns(
            x_obs_server_side_encryption="AES256",
            x_obs_version="Enabled",
            x_obs_storage_class="STANDARD",
            x_obs_bucket_location="af-south-1",
        )
        mock_obs_client.get_bucket_public_access_block.return_value = _ns(is_public=False)

        result = tools["obs_audit_bucket_security"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["overall_status"] == "pass"
        assert data["risk_count"] == 0

    def test_public_bucket(self, obs_settings, mock_obs_client):
        tools = make_audit_tools(obs_settings)
        mock_obs_client.get_bucket_public_status.return_value = _ns(is_public=True)
        mock_obs_client.get_bucket_acl.return_value = _ns(
            owner=_ns(id="owner-123"),
            access_control_list=_ns(grant=[
                _ns(grantee=_ns(canned="AllUsers", id=None), permission="READ", delivered=None),
                _ns(grantee=_ns(canned="AllUsers", id=None), permission="WRITE", delivered=None),
            ]),
        )
        mock_obs_client.get_bucket_metadata.return_value = _ns(
            x_obs_server_side_encryption=None,
            x_obs_version=None,
            x_obs_storage_class="STANDARD",
            x_obs_bucket_location="af-south-1",
        )
        mock_obs_client.get_bucket_public_access_block.return_value = _ns(is_public=True)

        result = tools["obs_audit_bucket_security"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["overall_status"] == "critical"
        assert data["high_risk_count"] >= 3  # public + read + write + no_encryption
        categories = {r["category"] for r in data["risk_items"]}
        assert "public_bucket" in categories
        assert "public_read_acl" in categories
        assert "public_write_acl" in categories
        assert "no_encryption" in categories

    def test_no_versioning(self, obs_settings, mock_obs_client):
        tools = make_audit_tools(obs_settings)
        mock_obs_client.get_bucket_public_status.return_value = _ns(is_public=False)
        mock_obs_client.get_bucket_acl.return_value = _ns(
            owner=_ns(id="owner-123"),
            access_control_list=_ns(grant=[
                _ns(grantee=_ns(canned="CanonicalUser", id="owner-123"), permission="FULL_CONTROL", delivered=None),
            ]),
        )
        mock_obs_client.get_bucket_metadata.return_value = _ns(
            x_obs_server_side_encryption="AES256",
            x_obs_version=None,
            x_obs_storage_class="STANDARD",
            x_obs_bucket_location="af-south-1",
        )
        mock_obs_client.get_bucket_public_access_block.return_value = _ns(is_public=False)

        result = tools["obs_audit_bucket_security"](bucket_name="my-bucket")
        assert result["ok"] is True
        data = result["data"]
        assert data["overall_status"] == "warn"
        categories = {r["category"] for r in data["risk_items"]}
        assert "no_versioning" in categories
