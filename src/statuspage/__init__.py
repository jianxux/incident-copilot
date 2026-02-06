"""Status Page integration for Incident Copilot.

Provides integration with Atlassian Statuspage for public incident communication,
component status management, and automated status updates.
"""

from .automation import (
    StatusPageAutomation,
    auto_create_status_incident,
    auto_update_status_incident,
    get_status_automation,
)
from .client import StatuspageClient, get_statuspage_client
from .models import (
    ComponentImpact,
    ComponentStatus,
    IncidentStatus,
    StatusComponent,
    StatusIncident,
    StatusPage,
    StatusUpdate,
)
from .routes import router as statuspage_router
from .sync import StatusPageSync, get_status_sync
from .templates import StatusUpdateTemplates, get_templates

__all__ = [
    # Models
    "ComponentStatus",
    "ComponentImpact",
    "IncidentStatus",
    "StatusComponent",
    "StatusIncident",
    "StatusUpdate",
    "StatusPage",
    # Client
    "StatuspageClient",
    "get_statuspage_client",
    # Sync
    "StatusPageSync",
    "get_status_sync",
    # Templates
    "StatusUpdateTemplates",
    "get_templates",
    # Automation
    "StatusPageAutomation",
    "get_status_automation",
    "auto_create_status_incident",
    "auto_update_status_incident",
    # Router
    "statuspage_router",
]
