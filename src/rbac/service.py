"""
RBAC Service
============

Core service for role-based access control.
Handles permission checks, role assignments, and access decisions.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from .models import (
    SYSTEM_ROLES,
    Action,
    Permission,
    PermissionCheck,
    ResourceScope,
    ResourceType,
    Role,
    RoleAssignment,
    RolePermission,
    ScopeType,
    UserPermissions,
)


class RBACService:
    """
    Role-Based Access Control service.

    Manages roles, permissions, and access checks.
    """

    def __init__(self):
        # In-memory stores (replace with database in production)
        self._roles: dict[UUID, Role] = {}
        self._assignments: dict[UUID, list[RoleAssignment]] = (
            {}
        )  # user_id -> assignments
        self._cached_permissions: dict[UUID, UserPermissions] = (
            {}
        )  # user_id -> permissions

        # Initialize system roles
        self._init_system_roles()

    def _init_system_roles(self) -> None:
        """Initialize built-in system roles."""
        for role in SYSTEM_ROLES.values():
            self._roles[role.id] = role

    # ==================== Role Management ====================

    async def create_role(
        self,
        name: str,
        description: str,
        organization_id: UUID,
        permissions: list[RolePermission],
        inherits_from: Optional[list[UUID]] = None,
    ) -> Role:
        """Create a custom role for an organization."""
        role = Role(
            name=name,
            description=description,
            organization_id=organization_id,
            permissions=permissions,
            inherits_from=inherits_from or [],
            is_system=False,
        )
        self._roles[role.id] = role
        return role

    async def get_role(self, role_id: UUID) -> Optional[Role]:
        """Get role by ID."""
        return self._roles.get(role_id)

    async def get_role_by_name(
        self,
        name: str,
        organization_id: Optional[UUID] = None,
    ) -> Optional[Role]:
        """Get role by name (optionally scoped to organization)."""
        for role in self._roles.values():
            if role.name.lower() == name.lower():
                if organization_id is None or role.organization_id == organization_id:
                    return role
        return None

    async def list_roles(
        self,
        organization_id: Optional[UUID] = None,
        include_system: bool = True,
    ) -> list[Role]:
        """List available roles."""
        roles = []
        for role in self._roles.values():
            if role.is_system and not include_system:
                continue
            if (
                organization_id
                and role.organization_id
                and role.organization_id != organization_id
            ):
                continue
            roles.append(role)
        return roles

    async def update_role(
        self,
        role_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        permissions: Optional[list[RolePermission]] = None,
    ) -> Optional[Role]:
        """Update a custom role."""
        role = self._roles.get(role_id)
        if not role or role.is_system:
            return None

        if name:
            role.name = name
        if description:
            role.description = description
        if permissions is not None:
            role.permissions = permissions

        role.updated_at = datetime.utcnow()
        self._invalidate_cache_for_role(role_id)

        return role

    async def delete_role(self, role_id: UUID) -> bool:
        """Delete a custom role."""
        role = self._roles.get(role_id)
        if not role or role.is_system:
            return False

        # Remove assignments
        for user_id, assignments in self._assignments.items():
            self._assignments[user_id] = [
                a for a in assignments if a.role_id != role_id
            ]

        del self._roles[role_id]
        return True

    # ==================== Role Assignments ====================

    async def assign_role(
        self,
        user_id: UUID,
        role_id: UUID,
        scope: Optional[ResourceScope] = None,
        assigned_by: Optional[UUID] = None,
        expires_at: Optional[datetime] = None,
    ) -> RoleAssignment:
        """Assign a role to a user."""
        assignment = RoleAssignment(
            user_id=user_id,
            role_id=role_id,
            scope=scope,
            assigned_by=assigned_by,
            expires_at=expires_at,
        )

        if user_id not in self._assignments:
            self._assignments[user_id] = []
        self._assignments[user_id].append(assignment)

        # Invalidate cache
        self._cached_permissions.pop(user_id, None)

        return assignment

    async def revoke_role(
        self,
        user_id: UUID,
        role_id: UUID,
        scope: Optional[ResourceScope] = None,
    ) -> bool:
        """Revoke a role from a user."""
        if user_id not in self._assignments:
            return False

        original_count = len(self._assignments[user_id])
        self._assignments[user_id] = [
            a
            for a in self._assignments[user_id]
            if not (a.role_id == role_id and (scope is None or a.scope == scope))
        ]

        if len(self._assignments[user_id]) < original_count:
            self._cached_permissions.pop(user_id, None)
            return True
        return False

    async def get_user_roles(self, user_id: UUID) -> list[RoleAssignment]:
        """Get all role assignments for a user."""
        assignments = self._assignments.get(user_id, [])

        # Filter out expired assignments
        now = datetime.utcnow()
        active = [
            a
            for a in assignments
            if a.is_active and (a.expires_at is None or a.expires_at > now)
        ]

        return active

    async def get_users_with_role(self, role_id: UUID) -> list[UUID]:
        """Get all users with a specific role."""
        users = []
        now = datetime.utcnow()

        for user_id, assignments in self._assignments.items():
            for assignment in assignments:
                if (
                    assignment.role_id == role_id
                    and assignment.is_active
                    and (assignment.expires_at is None or assignment.expires_at > now)
                ):
                    users.append(user_id)
                    break

        return users

    # ==================== Permission Checks ====================

    async def check_permission(
        self,
        user_id: UUID,
        resource_type: ResourceType,
        action: Action,
        organization_id: Optional[UUID] = None,
        team_id: Optional[UUID] = None,
        service_id: Optional[UUID] = None,
        resource_id: Optional[UUID] = None,
        owner_id: Optional[UUID] = None,
    ) -> PermissionCheck:
        """
        Check if a user has permission to perform an action.

        Returns a PermissionCheck with the result and reason.
        """
        # Get user's effective permissions
        user_perms = await self.get_user_permissions(user_id, organization_id)

        # Super admin bypass
        if user_perms.is_super_admin:
            return PermissionCheck(
                allowed=True,
                reason="Super admin access",
                matched_role="Super Admin",
            )

        # Admin bypass for non-manage actions
        if user_perms.is_admin and action != Action.MANAGE:
            return PermissionCheck(
                allowed=True,
                reason="Admin access",
                matched_role="Admin",
            )

        # Check effective permissions
        for role_perm in user_perms.effective_permissions:
            perm = role_perm.permission
            scope = role_perm.scope

            # Check resource type match
            if perm.resource_type != resource_type:
                continue

            # Check action match (MANAGE grants all actions)
            if perm.action != action and perm.action != Action.MANAGE:
                continue

            # Check scope match
            if scope.matches(
                organization_id=organization_id,
                team_id=team_id,
                service_id=service_id,
                resource_id=resource_id,
                owner_id=owner_id,
                user_id=user_id,
            ):
                return PermissionCheck(
                    allowed=True,
                    reason="Permission granted",
                    matched_permission=perm.permission_string,
                )

        return PermissionCheck(
            allowed=False,
            reason=f"No permission for {action.value} on {resource_type.value}",
        )

    async def can(
        self,
        user_id: UUID,
        resource_type: ResourceType,
        action: Action,
        **context,
    ) -> bool:
        """Quick boolean permission check."""
        result = await self.check_permission(
            user_id=user_id,
            resource_type=resource_type,
            action=action,
            **context,
        )
        return result.allowed

    async def get_user_permissions(
        self,
        user_id: UUID,
        organization_id: Optional[UUID] = None,
    ) -> UserPermissions:
        """
        Get aggregated permissions for a user.

        Combines all roles and resolves inheritance.
        """
        # Check cache
        cache_key = user_id
        if cache_key in self._cached_permissions:
            return self._cached_permissions[cache_key]

        # Get role assignments
        assignments = await self.get_user_roles(user_id)

        # Collect roles (including inherited)
        roles = []
        role_ids_seen = set()

        for assignment in assignments:
            await self._collect_roles_recursive(
                assignment.role_id,
                roles,
                role_ids_seen,
            )

        # Aggregate permissions
        effective_permissions = []
        for role in roles:
            for role_perm in role.permissions:
                effective_permissions.append(role_perm)

        # Build quick lookup sets
        can_create = set()
        can_read = set()
        can_update = set()
        can_delete = set()
        can_manage = set()
        is_admin = False
        is_super_admin = False

        for role_perm in effective_permissions:
            perm = role_perm.permission
            resource = perm.resource_type
            action = perm.action

            if action == Action.CREATE:
                can_create.add(resource)
            elif action == Action.READ:
                can_read.add(resource)
            elif action == Action.UPDATE:
                can_update.add(resource)
            elif action == Action.DELETE:
                can_delete.add(resource)
            elif action == Action.MANAGE:
                can_manage.add(resource)
                # MANAGE implies all actions
                can_create.add(resource)
                can_read.add(resource)
                can_update.add(resource)
                can_delete.add(resource)

        # Check for admin roles
        for role in roles:
            if role.name == "Super Admin":
                is_super_admin = True
                is_admin = True
            elif role.name == "Admin":
                is_admin = True

        user_perms = UserPermissions(
            user_id=user_id,
            organization_id=organization_id or UUID(int=0),
            roles=roles,
            effective_permissions=effective_permissions,
            can_create=can_create,
            can_read=can_read,
            can_update=can_update,
            can_delete=can_delete,
            can_manage=can_manage,
            is_admin=is_admin,
            is_super_admin=is_super_admin,
        )

        # Cache
        self._cached_permissions[cache_key] = user_perms

        return user_perms

    async def _collect_roles_recursive(
        self,
        role_id: UUID,
        roles: list[Role],
        seen: set[UUID],
    ) -> None:
        """Recursively collect roles including inherited ones."""
        if role_id in seen:
            return

        role = self._roles.get(role_id)
        if not role:
            return

        seen.add(role_id)
        roles.append(role)

        # Collect inherited roles
        for parent_id in role.inherits_from:
            await self._collect_roles_recursive(parent_id, roles, seen)

    def _invalidate_cache_for_role(self, role_id: UUID) -> None:
        """Invalidate permission cache for users with a specific role."""
        for user_id, assignments in self._assignments.items():
            for assignment in assignments:
                if assignment.role_id == role_id:
                    self._cached_permissions.pop(user_id, None)
                    break

    # ==================== Permission Helpers ====================

    async def get_allowed_resources(
        self,
        user_id: UUID,
        action: Action,
    ) -> list[ResourceType]:
        """Get list of resource types the user can perform an action on."""
        user_perms = await self.get_user_permissions(user_id)

        if action == Action.CREATE:
            return list(user_perms.can_create)
        elif action == Action.READ:
            return list(user_perms.can_read)
        elif action == Action.UPDATE:
            return list(user_perms.can_update)
        elif action == Action.DELETE:
            return list(user_perms.can_delete)
        elif action == Action.MANAGE:
            return list(user_perms.can_manage)

        # For other actions, check each resource type
        allowed = []
        for rt in ResourceType:
            if await self.can(user_id, rt, action):
                allowed.append(rt)
        return allowed

    async def get_allowed_actions(
        self,
        user_id: UUID,
        resource_type: ResourceType,
    ) -> list[Action]:
        """Get list of actions the user can perform on a resource type."""
        user_perms = await self.get_user_permissions(user_id)

        allowed = []
        for role_perm in user_perms.effective_permissions:
            if role_perm.permission.resource_type == resource_type:
                allowed.append(role_perm.permission.action)

        # Add implied actions from MANAGE
        if Action.MANAGE in allowed:
            for action in [Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE]:
                if action not in allowed:
                    allowed.append(action)

        return list(set(allowed))


# Singleton instance
rbac_service = RBACService()
