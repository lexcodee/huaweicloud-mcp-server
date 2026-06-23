"""Tests for mcp-gateway token subcommands: keygen, create, verify."""
from __future__ import annotations

import json
import os
import stat
import time
from argparse import Namespace
from pathlib import Path

import jwt
import pytest

from mcp_gateway.token import cmd_create, cmd_keygen, cmd_verify


def _keygen_args(tmp_path: Path, bits: int = 2048) -> Namespace:
    return Namespace(
        private_key=str(tmp_path / "jwt-private.pem"),
        public_key=str(tmp_path / "jwt-public.pem"),
        bits=bits,
    )


def _create_args(
    priv_path: str,
    *,
    sub: str = "alice",
    roles: str = "admin",
    issuer: str = "mcp-gateway",
    audience: str | None = None,
    tenant: str = "",
    ttl: int = 3600,
    fmt: str = "token",
) -> Namespace:
    return Namespace(
        sub=sub,
        roles=roles,
        private_key=priv_path,
        issuer=issuer,
        audience=audience,
        tenant=tenant,
        ttl=ttl,
        format=fmt,
    )


def _verify_args(
    pub_path: str,
    token: str,
    *,
    issuer: str = "mcp-gateway",
    audience: str | None = None,
    leeway: int = 30,
) -> Namespace:
    return Namespace(
        token=token,
        public_key=pub_path,
        issuer=issuer,
        audience=audience,
        leeway=leeway,
    )


class TestKeygen:
    def test_generates_key_pair(self, tmp_path: Path):
        args = _keygen_args(tmp_path)
        rc = cmd_keygen(args)
        assert rc == 0

        priv = Path(args.private_key)
        pub = Path(args.public_key)
        assert priv.is_file()
        assert pub.is_file()

        # Private key should be mode 0600
        mode = stat.S_IMODE(os.stat(priv).st_mode)
        assert mode == 0o600

        # Keys should be valid PEM
        priv_text = priv.read_text()
        pub_text = pub.read_text()
        assert "BEGIN RSA PRIVATE KEY" in priv_text
        assert "BEGIN PUBLIC KEY" in pub_text

        # The generated key pair should work for sign/verify
        token = jwt.encode({"sub": "test", "roles": ["admin"]}, priv_text, algorithm="RS256")
        payload = jwt.decode(token, pub_text, algorithms=["RS256"])
        assert payload["sub"] == "test"

    def test_4096_bits(self, tmp_path: Path):
        args = _keygen_args(tmp_path, bits=4096)
        rc = cmd_keygen(args)
        assert rc == 0

        priv_text = Path(args.private_key).read_text()
        pub_text = Path(args.public_key).read_text()
        token = jwt.encode({"sub": "x"}, priv_text, algorithm="RS256")
        jwt.decode(token, pub_text, algorithms=["RS256"])


class TestCreate:
    @pytest.fixture()
    def key_pair(self, tmp_path: Path):
        args = _keygen_args(tmp_path)
        cmd_keygen(args)
        return Path(args.private_key), Path(args.public_key)

    def test_create_default_format(self, key_pair, capsys):
        priv, pub = key_pair
        rc = cmd_create(_create_args(str(priv)))
        assert rc == 0

        token = capsys.readouterr().out.strip()
        assert token.count(".") == 2  # JWT = 3 dot-separated parts

        pub_text = pub.read_text()
        payload = jwt.decode(token, pub_text, algorithms=["RS256"])
        assert payload["sub"] == "alice"
        assert payload["roles"] == ["admin"]
        assert payload["iss"] == "mcp-gateway"
        assert "iat" in payload
        assert "exp" in payload

    def test_create_json_format(self, key_pair, capsys):
        priv, pub = key_pair
        rc = cmd_create(_create_args(str(priv), roles="readonly", tenant="proj-123", ttl=7200, fmt="json"))
        assert rc == 0

        output = json.loads(capsys.readouterr().out)
        assert "token" in output
        assert output["sub"] == "alice"
        assert output["roles"] == ["readonly"]
        assert output["iss"] == "mcp-gateway"
        assert output["tenant"] == "proj-123"
        assert output["exp"] - output["iat"] == 7200
        assert "expires_at" in output

        # Verify the embedded token
        pub_text = pub.read_text()
        payload = jwt.decode(output["token"], pub_text, algorithms=["RS256"])
        assert payload["sub"] == "alice"

    def test_create_with_audience(self, key_pair, capsys):
        priv, pub = key_pair
        rc = cmd_create(_create_args(str(priv), roles="operator", audience="mcp-api"))
        assert rc == 0

        token = capsys.readouterr().out.strip()
        pub_text = pub.read_text()
        payload = jwt.decode(token, pub_text, algorithms=["RS256"], audience="mcp-api")
        assert payload["aud"] == "mcp-api"

    def test_create_multiple_roles(self, key_pair, capsys):
        priv, pub = key_pair
        rc = cmd_create(_create_args(str(priv), roles="admin,operator"))
        assert rc == 0

        token = capsys.readouterr().out.strip()
        pub_text = pub.read_text()
        payload = jwt.decode(token, pub_text, algorithms=["RS256"])
        assert payload["roles"] == ["admin", "operator"]

    def test_create_missing_private_key(self, tmp_path, capsys):
        rc = cmd_create(_create_args(str(tmp_path / "nonexistent.pem")))
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_create_empty_roles(self, key_pair, capsys):
        priv, _ = key_pair
        rc = cmd_create(_create_args(str(priv), roles="  "))
        assert rc == 1
        assert "must not be empty" in capsys.readouterr().err

    def test_create_custom_role_warning(self, key_pair, capsys):
        priv, _ = key_pair
        rc = cmd_create(_create_args(str(priv), roles="admin,superuser"))
        assert rc == 0
        assert "unknown roles" in capsys.readouterr().err.lower()

    def test_create_permanent_token_no_exp(self, key_pair, capsys):
        """--ttl=0 omits exp claim → permanent token."""
        priv, pub = key_pair
        rc = cmd_create(_create_args(str(priv), ttl=0))
        assert rc == 0

        token = capsys.readouterr().out.strip()
        pub_text = pub.read_text()
        payload = jwt.decode(token, pub_text, algorithms=["RS256"], options={"verify_exp": False})
        assert payload["sub"] == "alice"
        assert "exp" not in payload

    def test_create_permanent_token_json_format(self, key_pair, capsys):
        """--ttl=0 with --format=json shows exp=null, expires_at='permanent'."""
        priv, pub = key_pair
        rc = cmd_create(_create_args(str(priv), ttl=0, fmt="json"))
        assert rc == 0

        output = json.loads(capsys.readouterr().out)
        assert output["exp"] is None
        assert output["expires_at"] == "permanent"

        # Embedded token should have no exp claim
        pub_text = pub.read_text()
        payload = jwt.decode(output["token"], pub_text, algorithms=["RS256"], options={"verify_exp": False})
        assert "exp" not in payload


class TestVerify:
    def test_verify_valid_token(self, tmp_path: Path, capsys):
        # keygen
        kg = _keygen_args(tmp_path)
        cmd_keygen(kg)
        capsys.readouterr()  # clear keygen output
        priv_text = Path(kg.private_key).read_text()
        pub_path = kg.public_key

        # sign a token directly
        token = jwt.encode(
            {"sub": "alice", "roles": ["admin"], "iss": "mcp-gateway", "tenant": "proj-abc",
             "iat": int(time.time()), "exp": int(time.time()) + 3600},
            priv_text, algorithm="RS256",
        )

        rc = cmd_verify(_verify_args(pub_path, token))
        assert rc == 0

        output = json.loads(capsys.readouterr().out)
        assert output["sub"] == "alice"
        assert output["roles"] == ["admin"]
        assert output["tenant"] == "proj-abc"
        assert "_expires_at" in output

    def test_verify_expired_token(self, tmp_path: Path, capsys):
        kg = _keygen_args(tmp_path)
        cmd_keygen(kg)
        priv_text = Path(kg.private_key).read_text()

        token = jwt.encode(
            {"sub": "expired", "roles": ["readonly"], "iss": "mcp-gateway", "exp": int(time.time()) - 10},
            priv_text, algorithm="RS256",
        )

        rc = cmd_verify(_verify_args(kg.public_key, token, leeway=0))
        assert rc == 1
        assert "expired" in capsys.readouterr().err.lower()

    def test_verify_wrong_issuer(self, tmp_path: Path, capsys):
        kg = _keygen_args(tmp_path)
        cmd_keygen(kg)
        priv_text = Path(kg.private_key).read_text()

        token = jwt.encode(
            {"sub": "x", "roles": ["readonly"], "iss": "wrong-issuer", "exp": int(time.time()) + 3600},
            priv_text, algorithm="RS256",
        )

        rc = cmd_verify(_verify_args(kg.public_key, token))
        assert rc == 1
        assert "issuer" in capsys.readouterr().err.lower()

    def test_verify_missing_public_key(self, tmp_path, capsys):
        rc = cmd_verify(_verify_args(str(tmp_path / "nonexistent.pem"), "some.token.here"))
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_verify_permanent_token(self, tmp_path: Path, capsys):
        """Verify should accept a token with no exp claim."""
        kg = _keygen_args(tmp_path)
        cmd_keygen(kg)
        capsys.readouterr()
        priv_text = Path(kg.private_key).read_text()

        token = jwt.encode(
            {"sub": "permanent-bot", "roles": ["admin"], "iss": "mcp-gateway", "iat": int(time.time())},
            priv_text, algorithm="RS256",
        )

        rc = cmd_verify(_verify_args(kg.public_key, token))
        assert rc == 0

        output = json.loads(capsys.readouterr().out)
        assert output["sub"] == "permanent-bot"
        assert "exp" not in output or output.get("exp") is None


class TestEndToEnd:
    def test_round_trip(self, tmp_path: Path, capsys):
        priv = tmp_path / "jwt-private.pem"
        pub = tmp_path / "jwt-public.pem"

        # Step 1: keygen
        assert cmd_keygen(_keygen_args(tmp_path)) == 0
        capsys.readouterr()  # clear keygen output

        # Step 2: create (json format)
        assert cmd_create(_create_args(str(priv), sub="devops-bot", roles="operator,readonly", tenant="proj-xyz", ttl=1800, fmt="json")) == 0
        create_output = json.loads(capsys.readouterr().out)
        token = create_output["token"]
        assert create_output["sub"] == "devops-bot"

        # Step 3: verify
        assert cmd_verify(_verify_args(str(pub), token)) == 0
        verify_output = json.loads(capsys.readouterr().out)
        assert verify_output["sub"] == "devops-bot"
        assert verify_output["roles"] == ["operator", "readonly"]
        assert verify_output["tenant"] == "proj-xyz"

    def test_round_trip_permanent(self, tmp_path: Path, capsys):
        """keygen → create --ttl=0 → verify: permanent token round-trip."""
        priv = tmp_path / "jwt-private.pem"
        pub = tmp_path / "jwt-public.pem"

        assert cmd_keygen(_keygen_args(tmp_path)) == 0
        capsys.readouterr()

        assert cmd_create(_create_args(str(priv), sub="permanent-bot", roles="admin", ttl=0, fmt="json")) == 0
        create_output = json.loads(capsys.readouterr().out)
        token = create_output["token"]
        assert create_output["exp"] is None
        assert create_output["expires_at"] == "permanent"

        assert cmd_verify(_verify_args(str(pub), token)) == 0
        verify_output = json.loads(capsys.readouterr().out)
        assert verify_output["sub"] == "permanent-bot"
        assert "exp" not in verify_output
