"""Status Page Integration Module.

Provides integration with major status page providers for automated
incident communication and component status management.

Supported providers: Atlassian Statuspage, Status.io, Cachet (self-hosted)

Example:
    from statuspage import StatusPageService, StatusPageConfig, StatusPageProvider, StatusPageCredentials

    config = StatusPageConfig(
        id="prod", name="Production", provider=StatusPageProvider.ATLASSIAN,
        credentials=StatusPageCredentials(api_key="key", page_id="page"),
        component_mapping={"api": "comp-1"},
    )
    service = get_statuspage_service()
    await service.add_config(config)
"""

from .automation import StatusPageAutomation, get_statuspage_automation
from .models import (Component, ComponentStatus, ConfigCreateRequest, IncidentCreateRequest,
    IncidentImpact, IncidentStatus, MaintenanceWindow, SEVERITY_TO_COMPONENT_STATUS,
    SEVERITY_TO_IMPACT, StatusPageConfig, StatusPageCredentials, StatusPageIncident,
    StatusPageMetrics, StatusPageProvider, StatusUpdate, SyncResult)
from .routes import router
from .service import StatusPageService, get_statuspage_service

__all__ = ["StatusPageService", "get_statuspage_service", "StatusPageAutomation", "get_statuspage_automation",
    "StatusPageConfig", "StatusPageCredentials", "StatusPageProvider", "StatusPageIncident", "StatusUpdate",
    "Component", "ComponentStatus", "IncidentStatus", "IncidentImpact", "MaintenanceWindow", "StatusPageMetrics",
    "SyncResult", "ConfigCreateRequest", "IncidentCreateRequest", "SEVERITY_TO_IMPACT", "SEVERITY_TO_COMPONENT_STATUS", "router"]
