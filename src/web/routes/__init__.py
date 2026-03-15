"""Web routes package compatibility exports."""

from ..store import incident_store
from .common import (
    DashboardAuthRedirect,
    _get_tenant_id_from_request,
    _map_status,
    landing_router,
    require_dashboard_auth,
    router,
    status_color,
)

# Backward-compatible alias used by src.main
DashboardAuthRedirectError = DashboardAuthRedirect
# Import route modules for side-effect registration on shared routers.
from . import api as _api  # noqa: E402, F401
from . import config as _config  # noqa: E402, F401
from . import demo as _demo  # noqa: E402, F401
from . import onboarding as _onboarding  # noqa: E402, F401
from . import pagerduty as _pagerduty  # noqa: E402, F401
from . import pages as _pages  # noqa: E402, F401
from .pages import incident_chat, incident_detail, incident_timeline  # noqa: E402

__all__ = [
    "router",
    "landing_router",
    "incident_store",
    "DashboardAuthRedirect",
    "DashboardAuthRedirectError",
    "require_dashboard_auth",
    "_get_tenant_id_from_request",
    "_map_status",
    "status_color",
    "incident_detail",
    "incident_chat",
    "incident_timeline",
]
