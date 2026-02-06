"""Data models for Status Page integration.

Defines models for status page components, incidents, and updates
following Atlassian Statuspage API conventions.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ComponentStatus(str, Enum):
    """Status states for a status page component."""

    OPERATIONAL = "operational"
    DEGRADED_PERFORMANCE = "degraded_performance"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    UNDER_MAINTENANCE = "under_maintenance"


class ComponentImpact(str, Enum):
    """Impact level for a component during an incident."""

    NONE = "none"
    MINOR = "minor"  # Degraded performance
    MAJOR = "major"  # Partial outage
    CRITICAL = "critical"  # Full outage


class IncidentStatus(str, Enum):
    """Status states for a status page incident."""

    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    SCHEDULED = "scheduled"  # For maintenance
    IN_PROGRESS = "in_progress"  # For maintenance
    VERIFYING = "verifying"  # For maintenance
    COMPLETED = "completed"  # For maintenance


class IncidentImpact(str, Enum):
    """Overall impact level for an incident."""

    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class StatusComponent(BaseModel):
    """A status page component representing a service or feature."""

    id: str
    page_id: str
    name: str
    description: str | None = None
    status: ComponentStatus = ComponentStatus.OPERATIONAL
    position: int = 0
    showcase: bool = True
    only_show_if_degraded: bool = False
    group_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    automation_email: str | None = None

    # Internal mapping fields
    internal_service: str | None = Field(
        None, description="Mapped internal service name"
    )

    model_config = ConfigDict(use_enum_values=True)


class StatusUpdate(BaseModel):
    """An update posted to a status page incident."""

    id: str | None = None
    incident_id: str
    status: IncidentStatus
    body: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    affected_components: list[str] = Field(default_factory=list)
    deliver_notifications: bool = True
    custom_tweet: str | None = None

    # Internal tracking
    internal_user: str | None = Field(None, description="User who posted the update")
    auto_generated: bool = Field(
        False, description="Whether this was auto-generated"
    )

    model_config = ConfigDict(use_enum_values=True)


class StatusIncident(BaseModel):
    """A status page incident."""

    id: str | None = None
    page_id: str
    name: str
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    impact: IncidentImpact = IncidentImpact.NONE
    shortlink: str | None = None
    scheduled_for: datetime | None = None
    scheduled_until: datetime | None = None
    scheduled_remind_prior: bool = False
    scheduled_auto_in_progress: bool = False
    scheduled_auto_completed: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    monitoring_at: datetime | None = None

    # Component impacts
    component_ids: list[str] = Field(default_factory=list)
    components: dict[str, ComponentStatus] = Field(
        default_factory=dict,
        description="Component ID to status mapping",
    )

    # Updates
    incident_updates: list[StatusUpdate] = Field(default_factory=list)

    # Internal tracking
    internal_incident_id: str | None = Field(
        None, description="Mapped internal incident ID"
    )
    auto_created: bool = Field(
        False, description="Whether this was auto-created from internal incident"
    )
    manual_override: bool = Field(
        False, description="Whether manual messaging override is enabled"
    )

    model_config = ConfigDict(use_enum_values=True)


class StatusPage(BaseModel):
    """A status page configuration."""

    id: str
    name: str
    subdomain: str
    domain: str | None = None
    url: str | None = None
    time_zone: str = "UTC"
    allow_email_subscribers: bool = True
    allow_page_subscribers: bool = True
    allow_sms_subscribers: bool = False
    allow_webhook_subscribers: bool = False

    # Page type
    is_internal: bool = Field(
        False, description="Internal status page (employee-facing)"
    )
    is_customer_facing: bool = Field(
        True, description="Customer-facing status page"
    )

    # Components on this page
    components: list[StatusComponent] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class ComponentMapping(BaseModel):
    """Mapping between internal services and status page components."""

    internal_service: str = Field(..., description="Internal service name")
    component_id: str = Field(..., description="Status page component ID")
    page_id: str = Field(..., description="Status page ID")
    severity_threshold: str = Field(
        "high",
        description="Minimum severity to trigger status update (critical, high, medium, low)",
    )
    auto_update: bool = Field(
        True, description="Automatically update component status"
    )
    impact_mapping: dict[str, ComponentImpact] = Field(
        default_factory=lambda: {
            "critical": ComponentImpact.CRITICAL,
            "high": ComponentImpact.MAJOR,
            "medium": ComponentImpact.MINOR,
            "low": ComponentImpact.NONE,
        },
        description="Internal severity to component impact mapping",
    )


class UptimeMetrics(BaseModel):
    """Uptime metrics for a component."""

    component_id: str
    component_name: str
    uptime_percentage: float = Field(..., ge=0.0, le=100.0)
    downtime_minutes: float = 0.0
    total_incidents: int = 0
    avg_resolution_minutes: float | None = None
    period_start: datetime
    period_end: datetime


class StatusPageConfig(BaseModel):
    """Configuration for status page integration."""

    pages: list[StatusPage] = Field(default_factory=list)
    component_mappings: list[ComponentMapping] = Field(default_factory=list)
    default_page_id: str | None = None
    auto_create_incidents: bool = Field(
        True, description="Auto-create status incidents for P1/P2"
    )
    auto_update_incidents: bool = Field(
        True, description="Auto-update status incidents on internal changes"
    )
    auto_resolve_incidents: bool = Field(
        True, description="Auto-resolve status incidents when internal resolves"
    )
    notification_delay_seconds: int = Field(
        60, description="Delay before sending notifications (for grouping)"
    )
