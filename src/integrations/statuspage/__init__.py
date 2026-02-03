"""Status page integrations for incident-copilot.

Supports multiple status page providers:
- Statuspage.io (Atlassian)
- Instatus
- Cachet (self-hosted)
"""

from .atlassian import AtlassianStatuspageClient
from .cachet import CachetClient
from .instatus import InstatusClient
from .models import (
    Component,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    StatusIncident,
    StatusIncidentUpdate,
    StatusPageConfig,
    StatusPageProvider,
)
from .service import StatusPageService
from .sync import StatusPageSync

__all__ = [
    # Models
    "StatusPageProvider",
    "ComponentStatus",
    "IncidentStatus",
    "IncidentImpact",
    "StatusPageConfig",
    "Component",
    "StatusIncident",
    "StatusIncidentUpdate",
    # Clients
    "AtlassianStatuspageClient",
    "InstatusClient",
    "CachetClient",
    # Service & Sync
    "StatusPageService",
    "StatusPageSync",
]
