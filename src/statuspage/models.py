"""Status Page Integration - Data Models."""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class StatusPageProvider(str, Enum):
    ATLASSIAN = "atlassian"
    STATUSIO = "statusio"
    CACHET = "cachet"


class ComponentStatus(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded_performance"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    MAINTENANCE = "under_maintenance"


class IncidentStatus(str, Enum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class IncidentImpact(str, Enum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class StatusPageCredentials(BaseModel):
    api_key: str
    page_id: str | None = None
    api_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class StatusPageConfig(BaseModel):
    id: str
    name: str
    provider: StatusPageProvider
    credentials: StatusPageCredentials
    enabled: bool = True
    auto_sync: bool = True
    component_mapping: dict[str, str] = Field(default_factory=dict)
    default_impact: IncidentImpact = IncidentImpact.MINOR
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Component(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: ComponentStatus = ComponentStatus.OPERATIONAL
    group_id: str | None = None
    position: int = 0


class StatusUpdate(BaseModel):
    id: str | None = None
    incident_id: str
    status: IncidentStatus
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StatusPageIncident(BaseModel):
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
    external_id: str | None = None


class MaintenanceWindow(BaseModel):
    id: str
    name: str
    description: str
    scheduled_start: datetime
    scheduled_end: datetime
    component_ids: list[str] = Field(default_factory=list)
    notify_subscribers: bool = True


class StatusPageMetrics(BaseModel):
    config_id: str
    total_components: int = 0
    operational_components: int = 0
    degraded_components: int = 0
    outage_components: int = 0
    active_incidents: int = 0
    last_sync: datetime | None = None


class ConfigCreateRequest(BaseModel):
    name: str
    provider: StatusPageProvider
    credentials: StatusPageCredentials
    auto_sync: bool = True
    component_mapping: dict[str, str] = Field(default_factory=dict)


class IncidentCreateRequest(BaseModel):
    name: str
    message: str
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    impact: IncidentImpact = IncidentImpact.MINOR
    component_ids: list[str] = Field(default_factory=list)
    component_status: ComponentStatus = ComponentStatus.PARTIAL_OUTAGE


class SyncResult(BaseModel):
    success: bool
    synced_components: int = 0
    errors: list[str] = Field(default_factory=list)


SEVERITY_TO_IMPACT = {"critical": IncidentImpact.CRITICAL, "high": IncidentImpact.MAJOR, "medium": IncidentImpact.MINOR, "low": IncidentImpact.NONE}
SEVERITY_TO_COMPONENT_STATUS = {"critical": ComponentStatus.MAJOR_OUTAGE, "high": ComponentStatus.PARTIAL_OUTAGE, "medium": ComponentStatus.DEGRADED, "low": ComponentStatus.OPERATIONAL}
