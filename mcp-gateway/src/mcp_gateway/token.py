"""Token issuance and key-generation CLI.

Subcommands
-----------
``mcp-gateway token create``
    Sign a JWT with the configured private key.  The public key that the
    gateway uses for verification is referenced from ``manifest.yaml``
    (``jwt.public_key``); this command takes the *private* key path
    explicitly via ``--private-key`` so that the private key never lives
    in the manifest or environment variables.

``mcp-gateway token keygen``
    Generate an RSA-2048 (or 4096) key pair suitable for JWT RS256
    signing/verification.  Prints the paths of the generated files.

Role hierarchy
--------------
The three built-in roles are:

    admin ⊃ operator ⊃ readonly

You may pass any subset of these (or custom roles) via ``--roles``.
The hierarchy is enforced at check time by ``require_role()``, not in
the token itself — the token simply records which roles the bearer holds.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

import jwt


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ROLES = {"admin", "operator", "readonly"}
DEFAULT_ISSUER = "mcp-gateway"
DEFAULT_TTL = 3600  # seconds


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------

def cmd_keygen(args: argparse.Namespace) -> int:
    """Generate an RSA key pair for JWT RS256 signing."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    bits = args.bits
    private_path = Path(args.private_key)
    public_path = Path(args.public_key)

    # Generate key pair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=bits)

    # Write private key (PEM, no passphrase)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_path.write_bytes(private_pem)
    private_path.chmod(0o600)

    # Write public key (PEM)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_path.write_bytes(public_pem)

    print(f"Private key: {private_path}  (mode 0600)")
    print(f"Public key:  {public_path}")
    print(f"Key size:    {bits} bits")
    print()
    print("Update your .env / manifest.yaml:")
    print(f'  MCP_JWT_PUBLIC_KEY=file:{public_path}')
    return 0


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> int:
    """Sign a JWT with the private key."""
    private_key_path = Path(args.private_key)
    if not private_key_path.is_file():
        print(f"Error: private key not found: {private_key_path}", file=sys.stderr)
        return 1

    private_key_pem = private_key_path.read_text(encoding="utf-8")

    # Parse roles
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    if not roles:
        print("Error: --roles must not be empty", file=sys.stderr)
        return 1

    # Warn about unknown roles (not an error — custom hierarchies are valid)
    unknown = set(roles) - VALID_ROLES
    if unknown:
        print(f"Note: unknown roles (not in {VALID_ROLES}): {unknown}", file=sys.stderr)

    # Build payload
    now = time.time()
    iat = int(now)
    payload: dict = {
        "sub": args.sub,
        "roles": roles,
        "iss": args.issuer,
        "iat": iat,
    }
    # --ttl=0 means permanent: omit exp so the token never expires.
    permanent = args.ttl == 0
    if not permanent:
        payload["exp"] = iat + args.ttl
    if args.tenant:
        payload["tenant"] = args.tenant
    if args.audience:
        payload["aud"] = args.audience

    # Sign
    token = jwt.encode(payload, private_key_pem, algorithm="RS256")

    # Output
    if args.format == "json":
        output: dict = {
            "token": token,
            "sub": args.sub,
            "roles": roles,
            "iss": args.issuer,
            "iat": iat,
        }
        if permanent:
            output["exp"] = None
            output["expires_at"] = "permanent"
        else:
            exp = payload["exp"]
            output["exp"] = exp
            output["expires_at"] = datetime.datetime.fromtimestamp(
                exp, tz=datetime.timezone.utc
            ).isoformat()
        if args.tenant:
            output["tenant"] = args.tenant
        if args.audience:
            output["aud"] = args.audience
        print(json.dumps(output, indent=2))
    else:
        # Plain token — easy to pipe into Authorization header
        print(token)

    return 0


# ---------------------------------------------------------------------------
# verify (bonus: decode a token with the public key for inspection)
# ---------------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> int:
    """Decode and verify a JWT using the public key."""
    public_key_path = Path(args.public_key)
    if not public_key_path.is_file():
        print(f"Error: public key not found: {public_key_path}", file=sys.stderr)
        return 1

    public_key_pem = public_key_path.read_text(encoding="utf-8")

    # Read token from --token or stdin
    token = args.token
    if not token:
        token = sys.stdin.read().strip()
    if not token:
        print("Error: no token provided (use --token or pipe to stdin)", file=sys.stderr)
        return 1

    try:
        payload = jwt.decode(
            token,
            public_key_pem,
            algorithms=["RS256"],
            issuer=args.issuer,
            audience=args.audience or None,
            leeway=args.leeway,
            options={"verify_exp": False},
        )
        # Manual exp check: permanent tokens (no exp) are ok; expired ones are not.
        if "exp" in payload and payload["exp"] < time.time() - args.leeway:
            print("Error: token has expired", file=sys.stderr)
            return 1
    except jwt.InvalidIssuerError as exc:
        print(f"Error: invalid issuer — {exc}", file=sys.stderr)
        return 1
    except jwt.InvalidAudienceError as exc:
        print(f"Error: invalid audience — {exc}", file=sys.stderr)
        return 1
    except jwt.InvalidTokenError as exc:
        print(f"Error: invalid token — {exc}", file=sys.stderr)
        return 1

    # Pretty print
    exp = payload.get("exp")
    if exp:
        expires_at = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc).isoformat()
        payload["_expires_at"] = expires_at
    print(json.dumps(payload, indent=2))
    return 0


# ---------------------------------------------------------------------------
# Argument parsers
# ---------------------------------------------------------------------------

def add_token_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``token create``, ``token keygen``, ``token verify`` sub-commands."""
    token_parser = subparsers.add_parser("token", help="JWT token issuance and key management")
    token_sub = token_parser.add_subparsers(dest="token_command", required=True)

    # --- keygen ---
    keygen_p = token_sub.add_parser("keygen", help="Generate RSA key pair for JWT RS256")
    keygen_p.add_argument(
        "--private-key", default="jwt-private.pem",
        help="Output path for private key (default: jwt-private.pem)",
    )
    keygen_p.add_argument(
        "--public-key", default="jwt-public.pem",
        help="Output path for public key (default: jwt-public.pem)",
    )
    keygen_p.add_argument(
        "--bits", type=int, default=2048, choices=[2048, 4096],
        help="RSA key size (default: 2048)",
    )
    keygen_p.set_defaults(func=cmd_keygen)

    # --- create ---
    create_p = token_sub.add_parser("create", help="Sign a JWT with the private key")
    create_p.add_argument("--sub", required=True, help="Subject claim (user or service account id)")
    create_p.add_argument(
        "--roles", required=True,
        help="Comma-separated role list (e.g. admin,operator,readonly)",
    )
    create_p.add_argument(
        "--private-key", default="jwt-private.pem",
        help="Path to RSA private key PEM (default: jwt-private.pem)",
    )
    create_p.add_argument("--issuer", default=DEFAULT_ISSUER, help="JWT issuer (default: mcp-gateway)")
    create_p.add_argument("--audience", default=None, help="JWT audience (optional)")
    create_p.add_argument("--tenant", default="", help="Tenant/project id (optional)")
    create_p.add_argument(
        "--ttl", type=int, default=DEFAULT_TTL,
        help=f"Token lifetime in seconds (default: {DEFAULT_TTL}; 0 = permanent)",
    )
    create_p.add_argument(
        "--format", choices=["token", "json"], default="token",
        help="Output format: 'token' (raw JWT) or 'json' (with metadata). Default: token",
    )
    create_p.set_defaults(func=cmd_create)

    # --- verify ---
    verify_p = token_sub.add_parser("verify", help="Decode and verify a JWT with the public key")
    verify_p.add_argument("--token", default=None, help="JWT string (reads stdin if omitted)")
    verify_p.add_argument(
        "--public-key", default="jwt-public.pem",
        help="Path to RSA public key PEM (default: jwt-public.pem)",
    )
    verify_p.add_argument("--issuer", default=DEFAULT_ISSUER, help="Expected issuer")
    verify_p.add_argument("--audience", default=None, help="Expected audience (optional)")
    verify_p.add_argument("--leeway", type=int, default=30, help="Clock-skew tolerance in seconds")
    verify_p.set_defaults(func=cmd_verify)
