"""Status Page Integration - Data Models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StatusPageProvider(str, Enum):
    """Supported status page providers."""

    ATLASSIAN = "atlassian"
    STATUSIO = "statusio"
    CACHET = "cachet"


class ComponentStatus(str, Enum):
    """Standard component status levels."""

    OPERATIONAL = "operational"
    DEGRADED = "degraded_performance"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    MAINTENANCE = "under_maintenance"


class IncidentStatus(str, Enum):
    """Status page incident status."""

    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class IncidentImpact(str, Enum):
    """Incident impact level."""

    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class StatusPageCredentials(BaseModel):
    """Provider-specific credentials."""

    api_key: str = Field(..., description="API key for authentication")
    page_id: str | None = Field(None, description="Page/site identifier")
    api_url: str | None = Field(None, description="Custom API URL (for self-hosted)")
    extra: dict[str, Any] = Field(
        default_factory=dict, description="Additional provider-specific fields"
    )


class StatusPageConfig(BaseModel):
    """Status page configuration."""

    id: str = Field(..., description="Unique configuration ID")
    name: str = Field(..., description="Display name")
    provider: StatusPageProvider
    credentials: StatusPageCredentials
    enabled: bool = Field(default=True, description="Whether this config is active")
    auto_sync: bool = Field(
        default=True, description="Auto-sync incident status changes"
    )
    component_mapping: dict[str, str] = Field(
        default_factory=dict, description="Service ID → Component ID"
    )
    default_impact: IncidentImpact = Field(default=IncidentImpact.MINOR)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Component(BaseModel):
    """Status page component."""

    id: str
    name: str
    description: str | None = None
    status: ComponentStatus = ComponentStatus.OPERATIONAL
    group_id: str | None = None
    position: int = 0
    showcase: bool = True


class StatusUpdate(BaseModel):
    """Status update for an incident."""

    id: str | None = None
    incident_id: str
    status: IncidentStatus
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    author: str | None = None


class StatusPageIncident(BaseModel):
    """Status page incident."""

    id: str | None = None
    name: str
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    impact: IncidentImpact = IncidentImpact.MINOR
    message: str
    component_ids: list[str] = Field(default_factory=list)
    component_status: ComponentStatus = ComponentStatus.PARTIAL_OUTAGE
    scheduled_for: datetime | None = None
    scheduled_until: datetime | None = None
    updates: list[StatusUpdate] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    external_id: str | None = Field(None, description="ID in external status page")


class MaintenanceWindow(BaseModel):
    """Scheduled maintenance window."""

    id: str
    name: str
    description: str
    scheduled_start: datetime
    scheduled_end: datetime
    component_ids: list[str] = Field(default_factory=list)
    auto_start: bool = True
    auto_complete: bool = True
    notify_subscribers: bool = True
    status: IncidentStatus = IncidentStatus.SCHEDULED


class StatusPageMetrics(BaseModel):
    """Status page metrics snapshot."""

    config_id: str
    total_components: int = 0
    operational_components: int = 0
    degraded_components: int = 0
    outage_components: int = 0
    maintenance_components: int = 0
    active_incidents: int = 0
    scheduled_maintenances: int = 0
    last_sync: datetime | None = None
    uptime_percentage: float | None = None


# Request/Response Models
class ConfigCreateRequest(BaseModel):
    """Request to create status page config."""

    name: str
    provider: StatusPageProvider
    credentials: StatusPageCredentials
    auto_sync: bool = True
    component_mapping: dict[str, str] = Field(default_factory=dict)


class ConfigUpdateRequest(BaseModel):
    """Request to update status page config."""

    name: str | None = None
    enabled: bool | None = None
    auto_sync: bool | None = None
    component_mapping: dict[str, str] | None = None
    default_impact: IncidentImpact | None = None


class IncidentCreateRequest(BaseModel):
    """Request to create incident on status page."""

    name: str
    message: str
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    impact: IncidentImpact = IncidentImpact.MINOR
    component_ids: list[str] = Field(default_factory=list)
    component_status: ComponentStatus = ComponentStatus.PARTIAL_OUTAGE
    notify_subscribers: bool = True


class IncidentUpdateRequest(BaseModel):
    """Request to update incident on status page."""

    status: IncidentStatus | None = None
    message: str | None = None
    component_status: ComponentStatus | None = None


class ComponentUpdateRequest(BaseModel):
    """Request to update component status."""

    component_id: str
    status: ComponentStatus


class SyncResult(BaseModel):
    """Result of sync operation."""

    success: bool
    synced_components: int = 0
    synced_incidents: int = 0
    errors: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Severity Mappings
SEVERITY_TO_IMPACT: dict[str, IncidentImpact] = {
    "critical": IncidentImpact.CRITICAL,
    "high": IncidentImpact.MAJOR,
    "medium": IncidentImpact.MINOR,
    "low": IncidentImpact.NONE,
    "sev1": IncidentImpact.CRITICAL,
    "sev2": IncidentImpact.MAJOR,
    "sev3": IncidentImpact.MINOR,
    "sev4": IncidentImpact.NONE,
}

SEVERITY_TO_COMPONENT_STATUS: dict[str, ComponentStatus] = {
    "critical": ComponentStatus.MAJOR_OUTAGE,
    "high": ComponentStatus.PARTIAL_OUTAGE,
    "medium": ComponentStatus.DEGRADED,
    "low": ComponentStatus.OPERATIONAL,
    "sev1": ComponentStatus.MAJOR_OUTAGE,
    "sev2": ComponentStatus.PARTIAL_OUTAGE,
    "sev3": ComponentStatus.DEGRADED,
    "sev4": ComponentStatus.OPERATIONAL,
}

# Status progression for auto-updates
INCIDENT_STATUS_ORDER = [
    IncidentStatus.INVESTIGATING,
    IncidentStatus.IDENTIFIED,
    IncidentStatus.MONITORING,
    IncidentStatus.RESOLVED,
]
