# Role-Based Access Control (RBAC) Module
# Fine-grained permissions for incident management

from .decorators import require_permission, require_role
from .models import Permission, ResourceScope, Role, RoleAssignment
from .routes import router
from .service import RBACService

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
