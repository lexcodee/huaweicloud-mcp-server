"""Test: tool-level RBAC — require_role + role hierarchy.

These tests mock Identity objects and verify that require_role correctly
enforces the admin ⊃ operator ⊃ readonly hierarchy.
"""
from __future__ import annotations

import pytest

from mcp_auth_common import Identity, require_role
from mcp_auth_common.errors import AuthError


class TestRequireRole:
    def test_admin_satisfies_readonly(self):
        identity = Identity(sub="alice", roles=["admin"])
        require_role(identity, "readonly")  # no exception

    def test_admin_satisfies_operator(self):
        identity = Identity(sub="alice", roles=["admin"])
        require_role(identity, "operator")

    def test_operator_satisfies_readonly(self):
        identity = Identity(sub="bob", roles=["operator"])
        require_role(identity, "readonly")

    def test_readonly_fails_operator(self):
        identity = Identity(sub="carol", roles=["readonly"])
        with pytest.raises(AuthError) as exc_info:
            require_role(identity, "operator")
        assert exc_info.value.status == 403

    def test_readonly_fails_admin(self):
        identity = Identity(sub="carol", roles=["readonly"])
        with pytest.raises(AuthError) as exc_info:
            require_role(identity, "admin")
        assert exc_info.value.status == 403

    def test_operator_fails_admin(self):
        identity = Identity(sub="bob", roles=["operator"])
        with pytest.raises(AuthError) as exc_info:
            require_role(identity, "admin")
        assert exc_info.value.status == 403

    def test_no_roles_fails_everything(self):
        identity = Identity(sub="anon", roles=[])
        with pytest.raises(AuthError) as exc_info:
            require_role(identity, "readonly")
        assert exc_info.value.status == 403

    def test_custom_hierarchy(self):
        """A custom hierarchy can be passed to override the default."""
        custom = {"superuser": {"superuser", "viewer"}, "viewer": {"viewer"}}
        identity = Identity(sub="dave", roles=["superuser"])
        require_role(identity, "viewer", hierarchy=custom)
        # But a viewer cannot satisfy superuser.
        identity2 = Identity(sub="eve", roles=["viewer"])
        with pytest.raises(AuthError):
            require_role(identity2, "superuser", hierarchy=custom)


class TestEcsToolMatrix:
    """Verify the ECS tool authorization matrix."""

    def test_readonly_can_list(self):
        identity = Identity(sub="r", roles=["readonly"])
        require_role(identity, "readonly")  # ecs_list_servers, ecs_get_server

    def test_readonly_cannot_start(self):
        identity = Identity(sub="r", roles=["readonly"])
        with pytest.raises(AuthError):
            require_role(identity, "operator")  # ecs_power_action(start)

    def test_operator_can_start(self):
        identity = Identity(sub="o", roles=["operator"])
        require_role(identity, "operator")  # ecs_power_action(start)

    def test_operator_cannot_delete(self):
        identity = Identity(sub="o", roles=["operator"])
        with pytest.raises(AuthError):
            require_role(identity, "admin")  # ecs_delete_server

    def test_admin_can_delete(self):
        identity = Identity(sub="a", roles=["admin"])
        require_role(identity, "admin")  # ecs_delete_server, ecs_resize_server


class TestPipelineToolMatrix:
    def test_readonly_can_list(self):
        identity = Identity(sub="r", roles=["readonly"])
        require_role(identity, "readonly")  # pipeline_list, pipeline_get_detail

    def test_operator_can_run(self):
        identity = Identity(sub="o", roles=["operator"])
        require_role(identity, "operator")  # pipeline_run

    def test_readonly_cannot_run(self):
        identity = Identity(sub="r", roles=["readonly"])
        with pytest.raises(AuthError):
            require_role(identity, "operator")  # pipeline_run

    def test_admin_can_update(self):
        identity = Identity(sub="a", roles=["admin"])
        require_role(identity, "admin")  # pipeline_update_info, pipeline_set_status

    def test_operator_cannot_update(self):
        identity = Identity(sub="o", roles=["operator"])
        with pytest.raises(AuthError):
            require_role(identity, "admin")


class TestCtsToolMatrix:
    def test_readonly_can_search(self):
        identity = Identity(sub="r", roles=["readonly"])
        require_role(identity, "readonly")  # cts_search_traces, cts_get_trace_detail
