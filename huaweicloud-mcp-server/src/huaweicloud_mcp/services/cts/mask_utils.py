"""Sensitive-value masking for CTS request/response payloads.

CTS audit events record the raw API request and response bodies. For
operations like "modify IAM user password" or "create access key" these
bodies contain secrets the LLM (and the conversation log it lives in)
must never see.

Strategy
--------
We do NOT remove the *keys* — that would make the masked output unreadable
("password was changed for user ..."  with no clue *what field* held it).
Instead, when we recognise a sensitive key, we replace its *value* with
``"***MASKED***"``. The key name itself is preserved.

Two passes:

1. **Structured pass** — try to parse the input as JSON. If it parses, walk
   the structure and substitute any value whose key matches the sensitive
   rule (see ``_is_sensitive_key``).

2. **Regex fallback** — when JSON parse fails (CTS sometimes records form
   bodies, plain strings, or escaped JSON), apply a permissive regex over
   the raw text. The regex anchors on the *key name* so unrelated fields
   like ``resource_name`` or ``user_password_policy_name`` aren't touched
   — only the value of a key whose name itself matches a sensitive rule
   gets replaced.

Anchoring rule
--------------
A key is sensitive iff the sensitive keyword appears at the END of the key,
either as the trailing alpha-token (``password``, ``new_password``,
``newPassword``) or as a trailing concatenated form (``accesskey``,
``accessKey``, ``access_key``). Keys where the keyword is INTERIOR
(``user_password_policy_name``, ``access_key_id``) are not masked — the
former is a policy descriptor, the latter is identity metadata that CTS
routinely records and that operators legitimately need to see.

Edge cases the tests cover:

* ``{"password": "***"}``                              → value masked
* ``{"resource_name":"my-bucket-password-policy"}``      → NOT masked (interior, not key-name)
* ``{"user_password_policy_name":"x", "new_password":"y"}``
                                                          → only ``new_password`` masked
* ``{"access_key_id":"AKID..."}``                        → NOT masked (CTS user identity metadata)
* ``{"accessKey":"..."}`` / ``{"access_key":"..."}``     → masked
* nested objects / arrays
* singly-escaped JSON strings inside an outer JSON
"""
from __future__ import annotations

import json
import re
from typing import Any

MASK_PLACEHOLDER = "***MASKED***"

# Last-token rule: if the key's trailing token equals one of these, mask the value.
_TRAILING_SINGLE = {
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "credentials",
    "authorization",
}

# Trailing two-token rule: keys whose last two tokens match one of these pairs.
# (so "access_key", "client_secret", "session_key" all hit, but "access_key_id" doesn't)
_TRAILING_PAIR = {
    ("access", "key"),
    ("secret", "key"),
    ("private", "key"),
    ("api", "key"),
    ("auth", "token"),
    ("client", "secret"),
    ("session", "key"),
    ("refresh", "token"),
    ("bearer", "token"),
}

# Concatenated single-token forms (no separator) — match at end of key.
_CONCAT_TRAILERS = (
    "accesskey",
    "secretkey",
    "privatekey",
    "apikey",
    "authtoken",
    "clientsecret",
    "sessionkey",
    "refreshtoken",
    "bearertoken",
)


def _tokenize(key: str) -> list[str]:
    """Split a key into lowercase alpha tokens, treating camelCase / underscores
    / hyphens / dots as separators."""
    # camelCase -> snake_case-ish before tokenising
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", key)
    s = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", s)
    s = s.lower()
    return [t for t in re.split(r"[^a-z]+", s) if t]


def _is_sensitive_key(key: str) -> bool:
    if not key:
        return False
    toks = _tokenize(key)
    if not toks:
        return False

    if toks[-1] in _TRAILING_SINGLE:
        return True

    if len(toks) >= 2 and (toks[-2], toks[-1]) in _TRAILING_PAIR:
        return True

    # Single-token key with no separator, e.g. "accesskey", "privatekey".
    if len(toks) == 1:
        only = toks[0]
        if only in _CONCAT_TRAILERS:
            return True

    return False


def _walk_structured(node: Any) -> Any:
    """Walk a parsed JSON tree, masking values under sensitive keys."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if _is_sensitive_key(str(k)):
                out[k] = MASK_PLACEHOLDER
            else:
                out[k] = _walk_structured(v)
        return out
    if isinstance(node, list):
        return [_walk_structured(item) for item in node]
    if isinstance(node, str):
        # Recurse into stringly-encoded JSON ("body": "{\"password\":...}").
        s = node.strip()
        if s.startswith(("{", "[")) and s.endswith(("}", "]")):
            try:
                inner = json.loads(s)
            except (ValueError, TypeError):
                return node
            return json.dumps(_walk_structured(inner), ensure_ascii=False)
        return node
    return node


# Regex for non-JSON / partial inputs. Anchors on the END of the key:
# the keyword must be the suffix of the key name, terminated by quote /
# colon / equals / whitespace.
_KEYWORDS_TRAILING = "|".join(
    sorted(
        set(_TRAILING_SINGLE)
        | {f"{a}_?{b}" for a, b in _TRAILING_PAIR}
        | set(_CONCAT_TRAILERS),
        key=len,
        reverse=True,
    )
)

# Match ``"<...>keyword"  :  <value>`` style (JSON).
_QUOTED_KEY_RE = re.compile(
    r"""(["'][\w.\-]*(?:""" + _KEYWORDS_TRAILING + r""")["']\s*:\s*)"""
    r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,}\]]+)""",
    re.IGNORECASE,
)

# Match ``...keyword = value`` or ``...keyword: value`` (unquoted form-style).
# Left boundary + optional prefix + keyword (trailing) + separator.
_BARE_KEY_RE = re.compile(
    r"""((?:^|[\s,&;{(\[])[\w.\-]*(?:""" + _KEYWORDS_TRAILING + r""")\s*[:=]\s*)"""
    r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;&}\]]+)""",
    re.IGNORECASE,
)


def _regex_mask(text: str) -> str:
    def _repl_quoted(m: re.Match) -> str:
        return f'{m.group(1)}"{MASK_PLACEHOLDER}"'

    def _repl_bare(m: re.Match) -> str:
        return f"{m.group(1)}{MASK_PLACEHOLDER}"

    out = _QUOTED_KEY_RE.sub(_repl_quoted, text)
    out = _BARE_KEY_RE.sub(_repl_bare, out)
    return out


def mask_sensitive(payload: Any) -> str:
    """Return a masked string view of ``payload``.

    Accepts:
      * dict / list — JSON-encoded and walked structurally.
      * str         — parsed as JSON if possible; otherwise regex-masked.
      * None        — returns ``""``.
      * other       — coerced to str (mask doesn't apply to scalars).
    """
    if payload is None:
        return ""

    if isinstance(payload, (dict, list)):
        return json.dumps(_walk_structured(payload), ensure_ascii=False)

    if isinstance(payload, str):
        stripped = payload.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError):
                return _regex_mask(payload)
            return json.dumps(_walk_structured(parsed), ensure_ascii=False)
        return _regex_mask(payload)

    return str(payload)


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Truncate ``text`` to at most ``limit`` chars.

    Returns ``(maybe_truncated_text, truncated_flag)``.
    """
    if text is None:
        return "", False
    if len(text) <= limit:
        return text, False
    return text[:limit] + "...[TRUNCATED]", True


def mask_and_truncate(payload: Any, limit: int) -> tuple[str, bool]:
    """Mask first, THEN truncate. Returns ``(text, truncated)``."""
    masked = mask_sensitive(payload)
    return truncate(masked, limit)