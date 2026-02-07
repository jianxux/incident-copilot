"""
RBAC Decorators
===============

FastAPI dependency decorators for permission enforcement.
"""

from functools import wraps
from typing import Callable, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from .models import Action, ResourceType
from .service import rbac_service


class PermissionDenied(HTTPException):
    """Exception raised when permission is denied."""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


async def get_current_user_id(request: Request) -> UUID:
    """
    Extract current user ID from request.

    Override this function in your application to integrate with your auth system.
    """
    # Default implementation - override in your app
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return UUID(user_id) if isinstance(user_id, str) else user_id


def require_permission(
    resource_type: ResourceType,
    action: Action,
    resource_id_param: Optional[str] = None,
    team_id_param: Optional[str] = None,
    service_id_param: Optional[str] = None,
):
    """
    Decorator to require a specific permission for an endpoint.

    Usage:
        @router.get("/incidents/{incident_id}")
        @require_permission(ResourceType.INCIDENT, Action.READ, resource_id_param="incident_id")
        async def get_incident(incident_id: UUID, ...):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if not request:
                # Try to find request in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found",
                )

            user_id = await get_current_user_id(request)

            # Extract context from parameters
            context = {}
            if resource_id_param and resource_id_param in kwargs:
                context["resource_id"] = kwargs[resource_id_param]
            if team_id_param and team_id_param in kwargs:
                context["team_id"] = kwargs[team_id_param]
            if service_id_param and service_id_param in kwargs:
                context["service_id"] = kwargs[service_id_param]

            # Check permission
            result = await rbac_service.check_permission(
                user_id=user_id,
                resource_type=resource_type,
                action=action,
                **context,
            )

            if not result.allowed:
                raise PermissionDenied(result.reason)

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_role(role_name: str):
    """
    Decorator to require a specific role for an endpoint.

    Usage:
        @router.post("/admin/settings")
        @require_role("Admin")
        async def update_settings(...):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if not request:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found",
                )

            user_id = await get_current_user_id(request)

            # Get user's roles
            assignments = await rbac_service.get_user_roles(user_id)

            has_role = False
            for assignment in assignments:
                role = await rbac_service.get_role(assignment.role_id)
                if role and role.name.lower() == role_name.lower():
                    has_role = True
                    break

            if not has_role:
                raise PermissionDenied(f"Requires role: {role_name}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_admin():
    """Decorator to require admin access."""
    return require_role("Admin")


def require_super_admin():
    """Decorator to require super admin access."""
    return require_role("Super Admin")


class PermissionChecker:
    """
    FastAPI dependency for permission checking.

    Usage:
        @router.get("/incidents/{incident_id}")
        async def get_incident(
            incident_id: UUID,
            _: None = Depends(PermissionChecker(ResourceType.INCIDENT, Action.READ)),
        ):
            ...
    """

    def __init__(
        self,
        resource_type: ResourceType,
        action: Action,
        resource_id_param: Optional[str] = None,
    ):
        self.resource_type = resource_type
        self.action = action
        self.resource_id_param = resource_id_param

    async def __call__(
        self,
        request: Request,
        user_id: UUID = Depends(get_current_user_id),
    ) -> None:
        context = {}

        # Extract resource ID from path parameters
        if self.resource_id_param:
            resource_id = request.path_params.get(self.resource_id_param)
            if resource_id:
                context["resource_id"] = (
                    UUID(resource_id) if isinstance(resource_id, str) else resource_id
                )

        result = await rbac_service.check_permission(
            user_id=user_id,
            resource_type=self.resource_type,
            action=self.action,
            **context,
        )

        if not result.allowed:
            raise PermissionDenied(result.reason)


class RoleChecker:
    """
    FastAPI dependency for role checking.

    Usage:
        @router.post("/admin/settings")
        async def update_settings(
            _: None = Depends(RoleChecker("Admin")),
        ):
            ...
    """

    def __init__(self, role_name: str):
        self.role_name = role_name

    async def __call__(
        self,
        user_id: UUID = Depends(get_current_user_id),
    ) -> None:
        assignments = await rbac_service.get_user_roles(user_id)

        for assignment in assignments:
            role = await rbac_service.get_role(assignment.role_id)
            if role and role.name.lower() == self.role_name.lower():
                return

        raise PermissionDenied(f"Requires role: {self.role_name}")
