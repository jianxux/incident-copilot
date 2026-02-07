"""
RBAC API Routes
===============

FastAPI routes for role and permission management.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .decorators import RoleChecker
from .models import (
    Action,
    Permission,
    PermissionCheck,
    ResourceScope,
    ResourceType,
    RoleAssignment,
    RolePermission,
    ScopeType,
    UserPermissions,
)
from .service import rbac_service

router = APIRouter(prefix="/rbac", tags=["rbac"])


# ==================== Request/Response Models ====================


class CreateRoleRequest(BaseModel):
    """Request to create a custom role."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    permissions: list[dict] = Field(
        default_factory=list,
        description="List of permission objects with resource_type and action",
    )
    inherits_from: list[UUID] = Field(default_factory=list)


class UpdateRoleRequest(BaseModel):
    """Request to update a role."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    permissions: list[dict] | None = None


class AssignRoleRequest(BaseModel):
    """Request to assign a role to a user."""

    user_id: UUID
    role_id: UUID
    scope_type: ScopeType | None = None
    team_id: UUID | None = None
    service_id: UUID | None = None
    expires_at: datetime | None = None


class RevokeRoleRequest(BaseModel):
    """Request to revoke a role from a user."""

    user_id: UUID
    role_id: UUID


class CheckPermissionRequest(BaseModel):
    """Request to check a permission."""

    user_id: UUID
    resource_type: ResourceType
    action: Action
    organization_id: UUID | None = None
    team_id: UUID | None = None
    service_id: UUID | None = None
    resource_id: UUID | None = None
    owner_id: UUID | None = None


class RoleResponse(BaseModel):
    """Role response with permission details."""

    id: UUID
    name: str
    description: str
    organization_id: UUID | None
    is_system: bool
    is_default: bool
    permissions: list[dict]
    inherits_from: list[UUID]
    created_at: datetime
    updated_at: datetime


# ==================== Role Routes ====================


@router.get("/roles", response_model=list[RoleResponse])
async def list_roles(
    organization_id: UUID | None = None,
    include_system: bool = True,
    _: None = Depends(RoleChecker("Admin")),
) -> list[RoleResponse]:
    """
    List all available roles.

    Requires Admin role.
    """
    roles = await rbac_service.list_roles(
        organization_id=organization_id,
        include_system=include_system,
    )

    return [
        RoleResponse(
            id=r.id,
            name=r.name,
            description=r.description,
            organization_id=r.organization_id,
            is_system=r.is_system,
            is_default=r.is_default,
            permissions=[
                {
                    "resource_type": rp.permission.resource_type.value,
                    "action": rp.permission.action.value,
                    "scope_type": rp.scope.scope_type.value,
                }
                for rp in r.permissions
            ],
            inherits_from=r.inherits_from,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in roles
    ]


@router.get("/roles/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: UUID,
    _: None = Depends(RoleChecker("Admin")),
) -> RoleResponse:
    """
    Get role details by ID.

    Requires Admin role.
    """
    role = await rbac_service.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        organization_id=role.organization_id,
        is_system=role.is_system,
        is_default=role.is_default,
        permissions=[
            {
                "resource_type": rp.permission.resource_type.value,
                "action": rp.permission.action.value,
                "scope_type": rp.scope.scope_type.value,
            }
            for rp in role.permissions
        ],
        inherits_from=role.inherits_from,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.post("/roles", response_model=RoleResponse, status_code=201)
async def create_role(
    request: CreateRoleRequest,
    organization_id: UUID = Query(..., description="Organization ID"),
    _: None = Depends(RoleChecker("Admin")),
) -> RoleResponse:
    """
    Create a custom role.

    Requires Admin role.
    """
    # Parse permissions
    permissions = []
    for perm_dict in request.permissions:
        perm = Permission(
            resource_type=ResourceType(perm_dict["resource_type"]),
            action=Action(perm_dict["action"]),
        )
        scope_type = ScopeType(perm_dict.get("scope_type", "global"))
        scope = ResourceScope(scope_type=scope_type)
        permissions.append(RolePermission(permission=perm, scope=scope))

    role = await rbac_service.create_role(
        name=request.name,
        description=request.description,
        organization_id=organization_id,
        permissions=permissions,
        inherits_from=request.inherits_from,
    )

    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        organization_id=role.organization_id,
        is_system=role.is_system,
        is_default=role.is_default,
        permissions=[
            {
                "resource_type": rp.permission.resource_type.value,
                "action": rp.permission.action.value,
                "scope_type": rp.scope.scope_type.value,
            }
            for rp in role.permissions
        ],
        inherits_from=role.inherits_from,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.put("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: UUID,
    request: UpdateRoleRequest,
    _: None = Depends(RoleChecker("Admin")),
) -> RoleResponse:
    """
    Update a custom role.

    System roles cannot be modified.
    Requires Admin role.
    """
    # Parse permissions if provided
    permissions = None
    if request.permissions is not None:
        permissions = []
        for perm_dict in request.permissions:
            perm = Permission(
                resource_type=ResourceType(perm_dict["resource_type"]),
                action=Action(perm_dict["action"]),
            )
            scope_type = ScopeType(perm_dict.get("scope_type", "global"))
            scope = ResourceScope(scope_type=scope_type)
            permissions.append(RolePermission(permission=perm, scope=scope))

    role = await rbac_service.update_role(
        role_id=role_id,
        name=request.name,
        description=request.description,
        permissions=permissions,
    )

    if not role:
        raise HTTPException(
            status_code=400,
            detail="Role not found or cannot be modified (system role)",
        )

    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        organization_id=role.organization_id,
        is_system=role.is_system,
        is_default=role.is_default,
        permissions=[
            {
                "resource_type": rp.permission.resource_type.value,
                "action": rp.permission.action.value,
                "scope_type": rp.scope.scope_type.value,
            }
            for rp in role.permissions
        ],
        inherits_from=role.inherits_from,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: UUID,
    _: None = Depends(RoleChecker("Super Admin")),
):
    """
    Delete a custom role.

    System roles cannot be deleted.
    Requires Super Admin role.
    """
    success = await rbac_service.delete_role(role_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Role not found or cannot be deleted (system role)",
        )


# ==================== Assignment Routes ====================


@router.post("/assignments", response_model=RoleAssignment, status_code=201)
async def assign_role(
    request: AssignRoleRequest,
    assigned_by: UUID | None = None,
    _: None = Depends(RoleChecker("Admin")),
) -> RoleAssignment:
    """
    Assign a role to a user.

    Optionally scope the assignment to a team or service.
    Requires Admin role.
    """
    scope = None
    if request.scope_type:
        scope = ResourceScope(
            scope_type=request.scope_type,
            team_id=request.team_id,
            service_id=request.service_id,
        )

    return await rbac_service.assign_role(
        user_id=request.user_id,
        role_id=request.role_id,
        scope=scope,
        assigned_by=assigned_by,
        expires_at=request.expires_at,
    )


@router.delete("/assignments", status_code=204)
async def revoke_role(
    request: RevokeRoleRequest,
    _: None = Depends(RoleChecker("Admin")),
):
    """
    Revoke a role from a user.

    Requires Admin role.
    """
    success = await rbac_service.revoke_role(
        user_id=request.user_id,
        role_id=request.role_id,
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Role assignment not found",
        )


@router.get("/users/{user_id}/roles", response_model=list[RoleAssignment])
async def get_user_roles(
    user_id: UUID,
    _: None = Depends(RoleChecker("Admin")),
) -> list[RoleAssignment]:
    """
    Get all role assignments for a user.

    Requires Admin role.
    """
    return await rbac_service.get_user_roles(user_id)


@router.get("/roles/{role_id}/users", response_model=list[UUID])
async def get_role_users(
    role_id: UUID,
    _: None = Depends(RoleChecker("Admin")),
) -> list[UUID]:
    """
    Get all users with a specific role.

    Requires Admin role.
    """
    return await rbac_service.get_users_with_role(role_id)


# ==================== Permission Check Routes ====================


@router.post("/check", response_model=PermissionCheck)
async def check_permission(request: CheckPermissionRequest) -> PermissionCheck:
    """
    Check if a user has a specific permission.

    Returns detailed result including which permission/role matched.
    """
    return await rbac_service.check_permission(
        user_id=request.user_id,
        resource_type=request.resource_type,
        action=request.action,
        organization_id=request.organization_id,
        team_id=request.team_id,
        service_id=request.service_id,
        resource_id=request.resource_id,
        owner_id=request.owner_id,
    )


@router.get("/users/{user_id}/permissions", response_model=UserPermissions)
async def get_user_permissions(
    user_id: UUID,
    organization_id: UUID | None = None,
) -> UserPermissions:
    """
    Get aggregated permissions for a user.

    Returns all effective permissions from all assigned roles.
    """
    return await rbac_service.get_user_permissions(
        user_id=user_id,
        organization_id=organization_id,
    )


@router.get("/users/{user_id}/allowed-actions/{resource_type}")
async def get_allowed_actions(
    user_id: UUID,
    resource_type: ResourceType,
) -> dict:
    """
    Get list of actions a user can perform on a resource type.
    """
    actions = await rbac_service.get_allowed_actions(user_id, resource_type)
    return {
        "user_id": str(user_id),
        "resource_type": resource_type.value,
        "allowed_actions": [a.value for a in actions],
    }


@router.get("/users/{user_id}/allowed-resources/{action}")
async def get_allowed_resources(
    user_id: UUID,
    action: Action,
) -> dict:
    """
    Get list of resource types a user can perform an action on.
    """
    resources = await rbac_service.get_allowed_resources(user_id, action)
    return {
        "user_id": str(user_id),
        "action": action.value,
        "allowed_resources": [r.value for r in resources],
    }


# ==================== Reference Routes ====================


@router.get("/resource-types")
async def list_resource_types() -> list[dict]:
    """List all resource types."""
    return [
        {"type": rt.value, "name": rt.value.replace("_", " ").title()}
        for rt in ResourceType
    ]


@router.get("/actions")
async def list_actions() -> list[dict]:
    """List all actions."""
    return [{"action": a.value, "name": a.value.title()} for a in Action]


@router.get("/scope-types")
async def list_scope_types() -> list[dict]:
    """List all scope types."""
    return [
        {"scope": s.value, "name": s.value.replace("_", " ").title()} for s in ScopeType
    ]
