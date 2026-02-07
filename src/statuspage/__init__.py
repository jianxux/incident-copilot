"""Status Page Integration Module.

Provides integration with major status page providers for
automated incident communication and component status management.

Supported providers:
- Atlassian Statuspage
- Status.io
- Cachet (self-hosted)

Example usage:
    from statuspage import (
        StatusPageService,
        StatusPageConfig,
        StatusPageProvider,
        StatusPageCredentials,
        get_statuspage_service,
    )

    # Configure a status page
    config = StatusPageConfig(
        id="prod-statuspage",
        name="Production Status Page",
        provider=StatusPageProvider.ATLASSIAN,
        credentials=StatusPageCredentials(
            api_key="your-api-key",
            page_id="your-page-id",
        ),
        component_mapping={
            "api-service": "component-id-1",
            "web-app": "component-id-2",
        },
    )

    # Add to service
    service = get_statuspage_service()
    await service.add_config(config)

    # Create incident
    from statuspage import StatusPageIncident, IncidentStatus
    incident = StatusPageIncident(
        name="API Degradation",
        message="We are investigating reports of slow API responses.",
        status=IncidentStatus.INVESTIGATING,
        component_ids=["api-service"],
    )
    await service.create_incident_all(incident, "internal-incident-123")
"""

from .automation import StatusPageAutomation, get_statuspage_automation
from .models import (
    Component,
    ComponentStatus,
    ComponentUpdateRequest,
    ConfigCreateRequest,
    ConfigUpdateRequest,
    IncidentCreateRequest,
    IncidentImpact,
    IncidentStatus,
    IncidentUpdateRequest,
    MaintenanceWindow,
    SEVERITY_TO_COMPONENT_STATUS,
    SEVERITY_TO_IMPACT,
    StatusPageConfig,
    StatusPageCredentials,
    StatusPageIncident,
    StatusPageMetrics,
    StatusPageProvider,
    StatusUpdate,
    SyncResult,
)
from .routes import router
from .service import StatusPageService, get_statuspage_service

__all__ = [
    # Service
    "StatusPageService",
    "get_statuspage_service",
    # Automation
    "StatusPageAutomation",
    "get_statuspage_automation",
    # Models
    "StatusPageConfig",
    "StatusPageCredentials",
    "StatusPageProvider",
    "StatusPageIncident",
    "StatusUpdate",
    "Component",
    "ComponentStatus",
    "IncidentStatus",
    "IncidentImpact",
    "MaintenanceWindow",
    "StatusPageMetrics",
    "SyncResult",
    # Request models
    "ConfigCreateRequest",
    "ConfigUpdateRequest",
    "IncidentCreateRequest",
    "IncidentUpdateRequest",
    "ComponentUpdateRequest",
    # Mappings
    "SEVERITY_TO_IMPACT",
    "SEVERITY_TO_COMPONENT_STATUS",
    # Router
    "router",
]
