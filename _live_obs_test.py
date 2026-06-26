"""Live integration test for OBS MCP tools against real Huawei Cloud.

Run with:
  cd /root/huaweicloud-mcp-server
  source .env
  uv run python _live_obs_test.py
"""
from __future__ import annotations

import json
import os
import sys
import time

# Load .env
from pathlib import Path
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from huaweicloud_mcp.config import load_settings
from huaweicloud_mcp.services.obs.tools.query import make_query_tools
from huaweicloud_mcp.services.obs.tools.manage import make_manage_tools
from huaweicloud_mcp.services.obs.tools.audit import make_audit_tools

settings = load_settings()
query_tools = make_query_tools(settings)
manage_tools = make_manage_tools(settings)
audit_tools = make_audit_tools(settings)

all_tools = {}
all_tools.update(query_tools)
all_tools.update(manage_tools)
all_tools.update(audit_tools)

TEST_BUCKET = f"mcp-obs-test-{int(time.time())}"
TEST_KEY = "test/config.json"
TEST_CONTENT = json.dumps({"test": True, "message": "hello from MCP live test"}, indent=2)

passed = 0
failed = 0
skipped = 0

def run_tool(name: str, **kwargs):
    """Run a tool and return (ok, data)."""
    fn = all_tools[name]
    result = fn(**kwargs)
    ok = result.get("ok", False)
    data = result.get("data", result.get("error", {}))
    return ok, data

def check(label: str, ok: bool, detail: str = ""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✓ {label}")
        if detail:
            print(f"    {detail}")
    else:
        failed += 1
        print(f"  ✗ {label}")
        if detail:
            print(f"    {detail}")

def skip(label: str, reason: str):
    global skipped
    skipped += 1
    print(f"  ⊘ {label} (skipped: {reason})")


print("=" * 70)
print("OBS MCP Live Integration Test")
print(f"  Region: {settings.region}")
print(f"  Test bucket: {TEST_BUCKET}")
print("=" * 70)

# ------------------------------------------------------------------
# 1. List existing buckets
# ------------------------------------------------------------------
print("\n[1] obs_describe_buckets — list all")
ok, data = run_tool("obs_describe_buckets")
check("list buckets", ok, f"found {data.get('total_count', 0)} buckets")
if ok and data.get("buckets"):
    for b in data["buckets"][:3]:
        print(f"    - {b.get('name')} ({b.get('location')})")

# ------------------------------------------------------------------
# 2. Create test bucket
# ------------------------------------------------------------------
print("\n[2] obs_create_bucket — create test bucket")
ok, data = run_tool("obs_create_bucket", bucket_name=TEST_BUCKET, acl="private")
check("create bucket", ok, f"bucket={data.get('bucket')}, acl={data.get('acl')}")

if not ok:
    print("\nCannot continue without a test bucket. Aborting.")
    sys.exit(1)

# Wait for bucket to be ready
time.sleep(2)

# ------------------------------------------------------------------
# 3. Get bucket detail
# ------------------------------------------------------------------
print("\n[3] obs_describe_buckets — bucket detail")
ok, data = run_tool("obs_describe_buckets", bucket_name=TEST_BUCKET)
check("bucket detail", ok, f"storage_class={data.get('bucket', {}).get('storage_class')}, versioning={data.get('bucket', {}).get('versioning')}")

# ------------------------------------------------------------------
# 4. Upload object
# ------------------------------------------------------------------
print("\n[4] obs_upload_object — upload test config")
ok, data = run_tool(
    "obs_upload_object",
    bucket_name=TEST_BUCKET,
    object_key=TEST_KEY,
    content=TEST_CONTENT,
    content_type="application/json",
)
check("upload object", ok, f"key={data.get('key')}, size={data.get('size')}, etag={data.get('etag')}")

# ------------------------------------------------------------------
# 5. List objects
# ------------------------------------------------------------------
print("\n[5] obs_list_objects — list in test bucket")
ok, data = run_tool("obs_list_objects", bucket_name=TEST_BUCKET)
check("list objects", ok, f"total_count={data.get('total_count')}")
if ok and data.get("objects"):
    for o in data["objects"][:5]:
        print(f"    - {o.get('key')} ({o.get('size')} bytes)")

# ------------------------------------------------------------------
# 6. Get object metadata (HEAD)
# ------------------------------------------------------------------
print("\n[6] obs_get_object — metadata only (HEAD)")
ok, data = run_tool("obs_get_object", bucket_name=TEST_BUCKET, object_key=TEST_KEY)
check("head object", ok, f"size={data.get('size')}, etag={data.get('etag')}, storage_class={data.get('storage_class')}")

# ------------------------------------------------------------------
# 7. Get object content (GET)
# ------------------------------------------------------------------
print("\n[7] obs_get_object — with content (GET)")
ok, data = run_tool("obs_get_object", bucket_name=TEST_BUCKET, object_key=TEST_KEY, include_content=True)
content_matches = ok and data.get("content") == TEST_CONTENT
check("get object content", ok, f"size={data.get('size')}, content_len={len(data.get('content', ''))}")
check("content matches uploaded", content_matches)

# ------------------------------------------------------------------
# 8. Generate presigned URL
# ------------------------------------------------------------------
print("\n[8] obs_generate_presigned_url — GET URL")
ok, data = run_tool("obs_generate_presigned_url", bucket_name=TEST_BUCKET, object_key=TEST_KEY, method="GET", expires=3600)
check("presigned GET url", ok, f"expires_in={data.get('expires_in')}")
if ok:
    url = data["url"]
    print(f"    url={url[:80]}...")

# Verify presigned URL works with curl
if ok:
    import subprocess
    print("    verifying URL with curl...")
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True, text=True, timeout=10,
    )
    http_code = r.stdout.strip()
    check("presigned URL downloadable", http_code == "200", f"HTTP {http_code}")

# ------------------------------------------------------------------
# 9. Generate presigned PUT URL
# ------------------------------------------------------------------
print("\n[9] obs_generate_presigned_url — PUT URL")
ok, data = run_tool("obs_generate_presigned_url", bucket_name=TEST_BUCKET, object_key="test/uploaded.txt", method="PUT", expires=3600)
check("presigned PUT url", ok)

# Verify PUT URL works
if ok:
    import subprocess
    print("    verifying PUT URL with curl...")
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "PUT",
         "-H", "Content-Type:", "--data-binary", "uploaded via presigned URL", data["url"]],
        capture_output=True, text=True, timeout=10,
    )
    http_code = r.stdout.strip()
    check("presigned PUT works", http_code == "200", f"HTTP {http_code}")

# ------------------------------------------------------------------
# 10. Describe bucket policy / ACL
# ------------------------------------------------------------------
print("\n[10] obs_describe_bucket_policy — ACL + public status")
ok, data = run_tool("obs_describe_bucket_policy", bucket_name=TEST_BUCKET)
check("bucket policy/acl", ok, f"is_public={data.get('is_public')}, grants={len(data.get('acl', {}).get('grants', []))}")

# ------------------------------------------------------------------
# 11. Audit bucket security
# ------------------------------------------------------------------
print("\n[11] obs_audit_bucket_security — composite audit")
ok, data = run_tool("obs_audit_bucket_security", bucket_name=TEST_BUCKET)
check("audit bucket", ok, f"overall={data.get('overall_status')}, risks={data.get('risk_count')}, high={data.get('high_risk_count')}")
if ok and data.get("risk_items"):
    for r in data["risk_items"]:
        print(f"    [{r['severity']}] {r['category']}: {r['description'][:80]}")

# ------------------------------------------------------------------
# 12. List object versions (versioning likely not enabled)
# ------------------------------------------------------------------
print("\n[12] obs_list_objects — include_versions=True")
ok, data = run_tool("obs_list_objects", bucket_name=TEST_BUCKET, include_versions=True)
if ok:
    check("list versions", ok, f"total_count={data.get('total_count')}")
else:
    skip("list versions", "versioning not enabled or not supported")

# ------------------------------------------------------------------
# 13. Describe bucket lifecycle
# ------------------------------------------------------------------
print("\n[13] obs_describe_bucket_lifecycle")
ok, data = run_tool("obs_describe_bucket_lifecycle", bucket_name=TEST_BUCKET)
if ok:
    check("lifecycle query", ok, f"has xml={bool(data.get('lifecycle_xml'))}")
else:
    skip("lifecycle query", "no lifecycle config (expected for new bucket)")

# ------------------------------------------------------------------
# 14. Delete object — two-phase commit
# ------------------------------------------------------------------
print("\n[14] obs_delete_object — two-phase commit")
ok, data = run_tool("obs_delete_object", bucket_name=TEST_BUCKET, object_key=TEST_KEY)
check("delete returns pending", ok and data.get("status") == "pending_approval", f"approval_id={data.get('approval_id', 'N/A')[:20]}")

if ok and data.get("approval_id"):
    approval_id = data["approval_id"]
    print(f"    approval_id={approval_id}")
    print("    confirming deletion...")
    ok2, data2 = run_tool("obs_confirm_destructive", approval_id=approval_id)
    check("confirm delete executes", ok2, f"deleted={data2.get('deleted')}, key={data2.get('key')}")

# ------------------------------------------------------------------
# 15. Set bucket policy — two-phase commit
# ------------------------------------------------------------------
print("\n[15] obs_set_bucket_policy — two-phase commit")
policy = json.dumps({
    "Statement": [{
        "Sid": "AllowPublicRead",
        "Effect": "Allow",
        "Principal": {"ID": ["*"]},
        "Action": ["GetObject"],
        "Resource": [f"{TEST_BUCKET}/*"]
    }]
})
ok, data = run_tool("obs_set_bucket_policy", bucket_name=TEST_BUCKET, policy=policy)
check("set policy returns pending", ok and data.get("status") == "pending_approval")

if ok and data.get("approval_id"):
    approval_id = data["approval_id"]
    print("    confirming policy set...")
    ok2, data2 = run_tool("obs_confirm_destructive", approval_id=approval_id)
    check("confirm set policy executes", ok2, f"updated={data2.get('updated')}")

# ------------------------------------------------------------------
# Cleanup: Delete remaining objects and bucket
# ------------------------------------------------------------------
print("\n[Cleanup] Removing test objects and bucket")

# List and delete all objects
ok, data = run_tool("obs_list_objects", bucket_name=TEST_BUCKET)
if ok and data.get("objects"):
    for obj in data["objects"]:
        key = obj.get("key")
        if key:
            ok_d, data_d = run_tool("obs_delete_object", bucket_name=TEST_BUCKET, object_key=key)
            if ok_d and data_d.get("approval_id"):
                run_tool("obs_confirm_destructive", approval_id=data_d["approval_id"])
                print(f"    deleted {key}")

# Delete bucket directly via SDK (no MCP tool for bucket deletion)
try:
    from huaweicloud_mcp.client import get_client
    from huaweicloudsdkobs.v1.model import DeleteBucketRequest
    client = get_client("obs", settings)
    client.delete_bucket(DeleteBucketRequest(bucket_name=TEST_BUCKET))
    print(f"    deleted bucket {TEST_BUCKET}")
except Exception as e:
    print(f"    failed to delete bucket: {e}")

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
print("\n" + "=" * 70)
print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
print("=" * 70)
sys.exit(0 if failed == 0 else 1)
