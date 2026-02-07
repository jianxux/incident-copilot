# Role-Based Access Control (RBAC) Module
# Fine-grained permissions for incident management

from .models import Role, Permission, RoleAssignment, ResourceScope
from .service import RBACService
from .routes import router
from .decorators import require_permission, require_role

__all__ = [
    "Role",
    "Permission",
    "RoleAssignment",
    "ResourceScope",
    "RBACService",
    "router",
    "require_permission",
    "require_role",
]
