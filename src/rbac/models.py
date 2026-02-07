"""
RBAC Models
===========

Role-based access control models for fine-grained permissions.
Supports resource-level, team-level, and organization-level scoping.
"""

from datetime import datetime
from enum import StrEnum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ResourceType(StrEnum):
    """Types of resources that can be protected."""
    INCIDENT = "incident"
    POSTMORTEM = "postmortem"
    RUNBOOK = "runbook"
    SERVICE = "service"
    TEAM = "team"
    USER = "user"
    INTEGRATION = "integration"
    DASHBOARD = "dashboard"
    REPORT = "report"
    SLA_POLICY = "sla_policy"
    ESCALATION_POLICY = "escalation_policy"
    MAINTENANCE_WINDOW = "maintenance_window"
    WEBHOOK = "webhook"
    API_KEY = "api_key"
    SETTINGS = "settings"


class Action(StrEnum):
    """Actions that can be performed on resources."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    EXPORT = "export"
    EXECUTE = "execute"  # For runbooks, webhooks
    ASSIGN = "assign"    # For incidents, escalations
    RESOLVE = "resolve"  # For incidents
    ACKNOWLEDGE = "acknowledge"  # For incidents
    COMMENT = "comment"  # For incidents, postmortems
    MANAGE = "manage"    # Full control including settings


class ScopeType(StrEnum):
    """Scope levels for permissions."""
    GLOBAL = "global"           # All resources in org
    TEAM = "team"               # Resources owned by team
    SERVICE = "service"         # Resources related to service
    RESOURCE = "resource"       # Specific resource instance
    SELF = "self"               # Only own resources


class Permission(BaseModel):
    """
    A single permission granting an action on a resource type.
    
    Examples:
    - incident:read - Can read incidents
    - incident:* - Can perform any action on incidents
    - *:read - Can read any resource
    """
    id: UUID = Field(default_factory=uuid4)
    resource_type: ResourceType
    action: Action
    
    # Optional conditions
    conditions: Optional[dict] = Field(None, description="JSON conditions for the permission")
    
    @property
    def permission_string(self) -> str:
        """Return permission as 'resource:action' string."""
        return f"{self.resource_type.value}:{self.action.value}"
    
    @classmethod
    def from_string(cls, perm_str: str) -> "Permission":
        """Create permission from 'resource:action' string."""
        resource, action = perm_str.split(":", 1)
        return cls(
            resource_type=ResourceType(resource),
            action=Action(action),
        )


class ResourceScope(BaseModel):
    """
    Defines the scope of a permission.
    
    A scope determines which specific resources a permission applies to.
    """
    id: UUID = Field(default_factory=uuid4)
    scope_type: ScopeType
    
    # Scope identifiers (depending on scope_type)
    organization_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    service_id: Optional[UUID] = None
    resource_id: Optional[UUID] = None
    
    def matches(
        self,
        organization_id: Optional[UUID] = None,
        team_id: Optional[UUID] = None,
        service_id: Optional[UUID] = None,
        resource_id: Optional[UUID] = None,
        owner_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> bool:
        """Check if this scope matches the given context."""
        if self.scope_type == ScopeType.GLOBAL:
            return True
        
        if self.scope_type == ScopeType.TEAM:
            return self.team_id == team_id
        
        if self.scope_type == ScopeType.SERVICE:
            return self.service_id == service_id
        
        if self.scope_type == ScopeType.RESOURCE:
            return self.resource_id == resource_id
        
        if self.scope_type == ScopeType.SELF:
            return owner_id == user_id
        
        return False


class RolePermission(BaseModel):
    """A permission granted to a role with optional scope."""
    permission: Permission
    scope: ResourceScope = Field(
        default_factory=lambda: ResourceScope(scope_type=ScopeType.GLOBAL)
    )


class Role(BaseModel):
    """
    A role that bundles permissions together.
    
    Roles can be built-in (system-defined) or custom (org-defined).
    """
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Role name")
    description: str = Field("", description="Role description")
    
    # Organization (None for system roles)
    organization_id: Optional[UUID] = None
    
    # Permissions granted by this role
    permissions: list[RolePermission] = Field(default_factory=list)
    
    # Role hierarchy
    inherits_from: list[UUID] = Field(
        default_factory=list,
        description="Roles this role inherits from"
    )
    
    # Metadata
    is_system: bool = Field(default=False, description="System-defined role")
    is_default: bool = Field(default=False, description="Assigned to new users")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RoleAssignment(BaseModel):
    """
    Assignment of a role to a user.
    
    Supports scoped assignments (e.g., team lead for specific team).
    """
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    role_id: UUID
    
    # Optional scope limitation
    scope: Optional[ResourceScope] = None
    
    # Assignment metadata
    assigned_by: Optional[UUID] = None
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Status
    is_active: bool = Field(default=True)


class UserPermissions(BaseModel):
    """
    Aggregated permissions for a user.
    
    Combines all role assignments and their permissions.
    """
    user_id: UUID
    organization_id: UUID
    
    # Computed permissions
    roles: list[Role] = Field(default_factory=list)
    effective_permissions: list[RolePermission] = Field(default_factory=list)
    
    # Quick lookup maps
    can_create: set[ResourceType] = Field(default_factory=set)
    can_read: set[ResourceType] = Field(default_factory=set)
    can_update: set[ResourceType] = Field(default_factory=set)
    can_delete: set[ResourceType] = Field(default_factory=set)
    can_manage: set[ResourceType] = Field(default_factory=set)
    
    is_admin: bool = Field(default=False)
    is_super_admin: bool = Field(default=False)


class PermissionCheck(BaseModel):
    """Result of a permission check."""
    allowed: bool
    reason: str
    matched_permission: Optional[str] = None
    matched_role: Optional[str] = None


# Built-in system roles
SYSTEM_ROLES = {
    "super_admin": Role(
        name="Super Admin",
        description="Full access to all resources and settings",
        is_system=True,
        permissions=[
            RolePermission(
                permission=Permission(resource_type=rt, action=Action.MANAGE)
            )
            for rt in ResourceType
        ],
    ),
    "admin": Role(
        name="Admin",
        description="Organization administrator",
        is_system=True,
        permissions=[
            RolePermission(
                permission=Permission(resource_type=rt, action=a)
            )
            for rt in ResourceType
            for a in [Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE, Action.LIST]
        ],
    ),
    "responder": Role(
        name="Incident Responder",
        description="Can manage incidents and on-call duties",
        is_system=True,
        is_default=True,
        permissions=[
            # Incidents
            RolePermission(permission=Permission(resource_type=ResourceType.INCIDENT, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.INCIDENT, action=Action.LIST)),
            RolePermission(permission=Permission(resource_type=ResourceType.INCIDENT, action=Action.UPDATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.INCIDENT, action=Action.ACKNOWLEDGE)),
            RolePermission(permission=Permission(resource_type=ResourceType.INCIDENT, action=Action.RESOLVE)),
            RolePermission(permission=Permission(resource_type=ResourceType.INCIDENT, action=Action.COMMENT)),
            # Runbooks
            RolePermission(permission=Permission(resource_type=ResourceType.RUNBOOK, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.RUNBOOK, action=Action.LIST)),
            RolePermission(permission=Permission(resource_type=ResourceType.RUNBOOK, action=Action.EXECUTE)),
            # Postmortems
            RolePermission(permission=Permission(resource_type=ResourceType.POSTMORTEM, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.POSTMORTEM, action=Action.LIST)),
            RolePermission(permission=Permission(resource_type=ResourceType.POSTMORTEM, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.POSTMORTEM, action=Action.COMMENT)),
            # Services
            RolePermission(permission=Permission(resource_type=ResourceType.SERVICE, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.SERVICE, action=Action.LIST)),
            # Dashboards
            RolePermission(permission=Permission(resource_type=ResourceType.DASHBOARD, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.DASHBOARD, action=Action.LIST)),
        ],
    ),
    "viewer": Role(
        name="Viewer",
        description="Read-only access to incidents and reports",
        is_system=True,
        permissions=[
            RolePermission(permission=Permission(resource_type=rt, action=Action.READ))
            for rt in [ResourceType.INCIDENT, ResourceType.POSTMORTEM, ResourceType.RUNBOOK, 
                      ResourceType.SERVICE, ResourceType.DASHBOARD, ResourceType.REPORT]
        ] + [
            RolePermission(permission=Permission(resource_type=rt, action=Action.LIST))
            for rt in [ResourceType.INCIDENT, ResourceType.POSTMORTEM, ResourceType.RUNBOOK,
                      ResourceType.SERVICE, ResourceType.DASHBOARD, ResourceType.REPORT]
        ],
    ),
    "team_lead": Role(
        name="Team Lead",
        description="Manage team resources and members",
        is_system=True,
        inherits_from=[],  # Will inherit from responder
        permissions=[
            # Team management
            RolePermission(permission=Permission(resource_type=ResourceType.TEAM, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.TEAM, action=Action.UPDATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.USER, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.USER, action=Action.LIST)),
            # Escalation policies
            RolePermission(permission=Permission(resource_type=ResourceType.ESCALATION_POLICY, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.ESCALATION_POLICY, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.ESCALATION_POLICY, action=Action.UPDATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.ESCALATION_POLICY, action=Action.DELETE)),
            # Maintenance windows
            RolePermission(permission=Permission(resource_type=ResourceType.MAINTENANCE_WINDOW, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.MAINTENANCE_WINDOW, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.MAINTENANCE_WINDOW, action=Action.UPDATE)),
            # Reports
            RolePermission(permission=Permission(resource_type=ResourceType.REPORT, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.REPORT, action=Action.EXPORT)),
        ],
    ),
    "service_owner": Role(
        name="Service Owner",
        description="Manage service configuration and integrations",
        is_system=True,
        permissions=[
            # Service management
            RolePermission(permission=Permission(resource_type=ResourceType.SERVICE, action=Action.MANAGE)),
            # Integrations
            RolePermission(permission=Permission(resource_type=ResourceType.INTEGRATION, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.INTEGRATION, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.INTEGRATION, action=Action.UPDATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.INTEGRATION, action=Action.DELETE)),
            # Webhooks
            RolePermission(permission=Permission(resource_type=ResourceType.WEBHOOK, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.WEBHOOK, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.WEBHOOK, action=Action.UPDATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.WEBHOOK, action=Action.DELETE)),
            # SLA policies
            RolePermission(permission=Permission(resource_type=ResourceType.SLA_POLICY, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.SLA_POLICY, action=Action.READ)),
            RolePermission(permission=Permission(resource_type=ResourceType.SLA_POLICY, action=Action.UPDATE)),
            # Runbooks
            RolePermission(permission=Permission(resource_type=ResourceType.RUNBOOK, action=Action.CREATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.RUNBOOK, action=Action.UPDATE)),
            RolePermission(permission=Permission(resource_type=ResourceType.RUNBOOK, action=Action.DELETE)),
        ],
    ),
}
