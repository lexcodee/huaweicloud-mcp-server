# mcp-auth-common

Shared authentication primitives used by all Huawei Cloud MCP servers and the
gateway:

- `Identity` — pydantic v2 model carrying `sub` / `roles` / `tenant` / `iat` / `exp`.
- `AuthStrategy` — abstract; resolves an `Identity` from an ASGI `scope`.
- `GatewayAuth` — reads `scope["mcp_identity"]` injected by the gateway.
- `StandaloneAuth` — verifies a `Authorization: Bearer ...` JWT with the
  configured RS256 public key.
- `create_auth_strategy()` — factory selecting between the two via
  `MCP_AUTH_MODE`; defaults to `standalone` so an MCP server launched
  outside the gateway still refuses unauthenticated requests.
- `require_role(identity, required, hierarchy=DEFAULT_ROLE_HIERARCHY)` —
  raises `AuthError(403)` when the identity does not satisfy the required role.
- `set_request_scope(scope)` / `current_scope()` — contextvar plumbing so a
  tool function can call `current_scope()` without the FastMCP signature
  needing a `ctx` parameter.

Why this package exists separately from the gateway:

1. Every MCP server must enforce auth even when launched standalone. Embedding
   the same code in every server via copy-paste would drift; a shared package
   keeps the JWT verification logic in one place.
2. The gateway itself uses the same `Identity` model when it parses incoming
   JWTs, so both sides agree on the shape that flows through `scope["mcp_identity"]`.

Token issuance
--------------
The gateway ships a CLI for signing JWTs without an external IdP:

```bash
mcp-gateway token keygen                              # generate RSA key pair
mcp-gateway token create --sub alice --roles admin    # sign a JWT
mcp-gateway token verify --token "eyJ..."             # decode + verify
```

See `mcp-gateway/README.md` for full documentation.
