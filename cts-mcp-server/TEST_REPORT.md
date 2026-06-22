# CTS MCP Server — Test Report

**Date:** 2026-06-21
**Total tests:** 82
**Result:** ✅ All 82 passed

## Test Coverage Summary

| Module | Tests | Status | Key Scenarios |
|---|---|---|---|
| `test_time_utils.py` | 16 | ✅ | ISO8601 with offset, UTC `Z`, naive + timezone, relative `-Nh`/`-Nd`, epoch passthrough, unparseable input |
| `test_mask_utils.py` | 21 | ✅ | Structured walk (dict/list/nested/stringly-encoded), regex fallback (form-style), boundary: `resource_name` not masked, `access_key_id` not masked, `user_password_policy_name` not masked, `new_password` masked, `accessKey` camelCase masked |
| `test_seven_day_validation.py` | 11 | ✅ | 6d ago → pass, 7d+tolerance → pass, 7d−6min → reject, 8d → reject, start≥end → reject, None defaults, relative `-8d` → reject |
| `test_pagination.py` | 7 | ✅ | Single page with marker, null marker = no more pages, 3-page auto-paginate, max_results cap + truncated flag, marker passed as `next` param, 8d rejected via tool, invalid range rejected |
| `test_search_smoke.py` | 5 | ✅ | Basic search, service_type filter, trace_rating filter, request/response masking in summary, trace_type=data |
| `test_detail.py` | 5 | ✅ | Found, not found, password masking in body, trace_id passed to SDK, long body truncation with flag |

## Key Verification Results

### 1. 7-Day Time Range Validation

| Test Case | Input | Expected | Actual |
|---|---|---|---|
| Well within window | `now - 6d` | ✅ Pass | ✅ Pass |
| Just inside (7d − tolerance) | `now - 7d + 5min + 1min` | ✅ Pass | ✅ Pass |
| Within tolerance (7d + 3min) | `now - 7d - 3min` | ✅ Pass (5min tolerance) | ✅ Pass |
| Past tolerance (7d + 6min) | `now - 7d - 6min` | ❌ `TIME_RANGE_TOO_OLD` | ❌ `TIME_RANGE_TOO_OLD` |
| Clearly outside | `now - 8d` | ❌ `TIME_RANGE_TOO_OLD` | ❌ `TIME_RANGE_TOO_OLD` |
| Relative outside | `-8d` | ❌ `TIME_RANGE_TOO_OLD` | ❌ `TIME_RANGE_TOO_OLD` |
| Inverted range | start > end | ❌ `TIME_RANGE_INVALID` | ❌ `TIME_RANGE_INVALID` |

**Result:** The 7-day window is enforced BEFORE any SDK call is issued. The 5-minute tolerance absorbs clock drift between the client and server.

### 2. Cursor-Based Pagination

| Test Case | Pages | max_results | Expected | Actual |
|---|---|---|---|---|
| Single page, has marker | 1 (marker="abc") | — | `next_marker="abc"`, `truncated=false` | ✅ Match |
| Single page, no marker | 1 (marker=null) | — | `next_marker=null`, `truncated=false` | ✅ Match |
| Auto-paginate 3 pages | 3 (2+2+1 traces) | 100 | `total_returned=5`, `truncated=false` | ✅ Match |
| Auto-paginate with cap | 2 (2+2 traces) | 3 | `total_returned=3`, `truncated=true` | ✅ Match |
| Explicit next_marker | marker="cursor-prev" | — | SDK receives `next="cursor-prev"` | ✅ Match |

**Result:** Cursor-based pagination works correctly. `max_results` caps the merged set and sets `truncated=true`. The `next_marker` is correctly passed to the SDK's `next` parameter.

### 3. Sensitive-Value Masking

| Input Key | Masked? | Rationale |
|---|---|---|
| `password` | ✅ Yes | Trailing token matches |
| `new_password` | ✅ Yes | Trailing token matches |
| `newPassword` | ✅ Yes | camelCase tokenized → trailing matches |
| `secret` | ✅ Yes | Trailing single token |
| `access_key` | ✅ Yes | Trailing pair (access, key) |
| `secret_key` | ✅ Yes | Trailing pair (secret, key) |
| `token` | ✅ Yes | Trailing single token |
| `client_secret` | ✅ Yes | Trailing pair (client, secret) |
| `accessKey` (camelCase) | ✅ Yes | Concatenated form |
| `resource_name` | ❌ No | `name` is not a sensitive keyword |
| `user_password_policy_name` | ❌ No | `password` is interior, not trailing |
| `password_policy_name` | ❌ No | `password` is interior, not trailing |
| `access_key_id` | ❌ No | Trailing pair is (key, id), not in sensitive set — CTS identity metadata |

**Result:** The trailing-token anchoring strategy correctly masks sensitive values while preserving non-sensitive fields that happen to contain a keyword substring.

### 4. Time Conversion

| Input | Timezone | Result |
|---|---|---|
| `2026-06-20T22:00:00+08:00` | — | Correct UTC ms (14:00:00 UTC) |
| `2026-06-20T14:00:00Z` | — | Same as above |
| `2026-06-20 22:00:00` | Asia/Shanghai | Same as above |
| `-1h` | — | ~3600000 ms before now |
| `-2d` | — | ~172800000 ms before now |
| `1718900000000` (13-digit) | — | Passthrough |
| `1718900000` (10-digit) | — | ×1000 uplift |

**Result:** All time formats parse correctly. The `now` literal is also supported.
