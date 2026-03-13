"""Tests for RBAC module."""

import pytest

from src.rbac.models import (
    SYSTEM_ROLES,
    Action,
    Permission,
    ResourceType,
    Role,
    RoleAssignment,
)
from src.rbac.service import RBACService


class TestRBACModels:
    def test_role_creation(self):
        role = Role(name="Admin", description="Full access", tenant_id="t-1")
        assert role.name == "Admin"

    def test_role_assignment(self):
        import uuid

        uid, rid = uuid.uuid4(), uuid.uuid4()
        assignment = RoleAssignment(user_id=uid, role_id=rid)
        assert assignment.user_id == uid

    def test_permission(self):
        perm = Permission(resource_type=ResourceType.INCIDENT, action=Action.READ)
        assert perm.resource_type == ResourceType.INCIDENT

    def test_system_roles_exist(self):
        assert isinstance(SYSTEM_ROLES, (list, dict))
        assert len(SYSTEM_ROLES) > 0

    def test_resource_types(self):
        assert ResourceType.INCIDENT
        assert ResourceType.SERVICE

    def test_actions(self):
        assert Action.READ
        assert Action.CREATE
        assert Action.UPDATE
        assert Action.DELETE


class TestRBACService:
    @pytest.fixture
    def service(self):
        return RBACService()

    def test_service_instantiation(self, service):
        assert service is not None

    @pytest.mark.asyncio
    async def test_list_roles(self, service):
        roles = await service.list_roles("tenant-1")
        assert isinstance(roles, list)
