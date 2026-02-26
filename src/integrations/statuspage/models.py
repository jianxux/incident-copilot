"""Data models for status page integrations."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StatusPageProvider(StrEnum):
    """Supported status page providers."""

    ATLASSIAN = "atlassian"  # Statuspage.io
    INSTATUS = "instatus"
    CACHET = "cachet"


class ComponentStatus(StrEnum):
    """Standard component status values."""

    OPERATIONAL = "operational"
    DEGRADED_PERFORMANCE = "degraded_performance"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    UNDER_MAINTENANCE = "under_maintenance"


class IncidentStatus(StrEnum):
    """Standard incident status values."""

    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    SCHEDULED = "scheduled"  # For maintenance
    IN_PROGRESS = "in_progress"  # For maintenance
    VERIFYING = "verifying"  # For maintenance
    COMPLETED = "completed"  # For maintenance


class IncidentImpact(StrEnum):
    """Incident impact levels."""

    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    MAINTENANCE = "maintenance"


class StatusPageConfig(BaseModel):
    """Configuration for a status page provider."""

    id: str = Field(description="Unique config ID")
    name: str = Field(description="Display name for this config")
    provider: StatusPageProvider
    enabled: bool = True

    # Connection details
    api_key: str = Field(description="API key/token for authentication")
    page_id: str = Field(description="Status page ID")
    base_url: str | None = Field(
        default=None,
        description="Base URL (required for self-hosted like Cachet)",
    )

    # Sync settings
    auto_create_incidents: bool = Field(
        default=True,
        description="Automatically create status page incidents",
    )
    auto_update_incidents: bool = Field(
        default=True,
        description="Automatically update status page incidents",
    )
    auto_update_components: bool = Field(
        default=True,
        description="Automatically update component status",
    )

    # Mapping settings
    severity_to_impact: dict[str, IncidentImpact] = Field(
        default_factory=lambda: {
            "critical": IncidentImpact.CRITICAL,
            "high": IncidentImpact.MAJOR,
            "medium": IncidentImpact.MINOR,
            "low": IncidentImpact.MINOR,
            "info": IncidentImpact.NONE,
        },
        description="Map internal severity to status page impact",
    )

    # Component mapping (service name -> component ID)
    component_map: dict[str, str] = Field(
        default_factory=dict,
        description="Map service names to status page component IDs",
    )

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)


class Component(BaseModel):
    """A component on a status page."""

    id: str = Field(description="Component ID from status page")
    name: str = Field(description="Component name")
    description: str | None = None
    status: ComponentStatus = ComponentStatus.OPERATIONAL
    position: int = 0
    group_id: str | None = Field(default=None, description="Parent group ID")
    group_name: str | None = Field(default=None, description="Parent group name")

    # Provider-specific
    provider: StatusPageProvider
    page_id: str
    showcase: bool = True  # Whether component is shown on status page

    # Metadata
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Raw response for debugging
    raw_data: dict = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


class StatusIncidentUpdate(BaseModel):
    """An update/message on a status page incident."""

    id: str | None = Field(default=None, description="Update ID from status page")
    status: IncidentStatus
    body: str = Field(description="Update message")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    display_at: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)


class StatusIncident(BaseModel):
    """A status page incident."""

    id: str | None = Field(default=None, description="Incident ID from status page")
    name: str = Field(description="Incident title")
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    impact: IncidentImpact = IncidentImpact.MINOR

    # Linked components
    component_ids: list[str] = Field(
        default_factory=list,
        description="Affected component IDs",
    )

    # Timeline
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    scheduled_for: datetime | None = Field(
        default=None, description="For scheduled maintenance"
    )
    scheduled_until: datetime | None = Field(
        default=None, description="For scheduled maintenance"
    )

    # Updates/messages
    updates: list[StatusIncidentUpdate] = Field(default_factory=list)

    # Link to internal incident
    internal_incident_id: str | None = Field(
        default=None,
        description="ID of the internal incident this syncs from",
    )

    # Provider info
    provider: StatusPageProvider | None = None
    page_id: str | None = None
    shortlink: str | None = Field(default=None, description="Public URL to incident")

    # Raw response
    raw_data: dict = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


class ComponentStatusUpdate(BaseModel):
    """Request to update a component's status."""

    component_id: str
    status: ComponentStatus

    model_config = ConfigDict(use_enum_values=True)


class CreateIncidentRequest(BaseModel):
    """Request to create a status page incident."""

    name: str = Field(description="Incident title")
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    impact: IncidentImpact = IncidentImpact.MINOR
    body: str = Field(description="Initial incident message")
    component_ids: list[str] = Field(
        default_factory=list,
        description="Affected component IDs",
    )
    component_status: ComponentStatus | None = Field(
        default=None,
        description="Status to set for affected components",
    )
    internal_incident_id: str | None = Field(
        default=None,
        description="Link to internal incident",
    )

    model_config = ConfigDict(use_enum_values=True)


class UpdateIncidentRequest(BaseModel):
    """Request to update a status page incident."""

    status: IncidentStatus | None = None
    impact: IncidentImpact | None = None
    body: str | None = Field(default=None, description="Update message")
    component_ids: list[str] | None = None
    component_status: ComponentStatus | None = None

    model_config = ConfigDict(use_enum_values=True)
