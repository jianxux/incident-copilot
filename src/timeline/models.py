"""Timeline models using Pydantic v2."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """Types of timeline events."""

    STATUS_CHANGE = "status_change"
    ASSIGNMENT = "assignment"
    COMMENT = "comment"
    DEPLOYMENT = "deployment"
    ALERT = "alert"
    ESCALATION = "escalation"
    NOTIFICATION = "notification"
    ACTION_TAKEN = "action_taken"
    METRIC_ANOMALY = "metric_anomaly"
    LOG_PATTERN = "log_pattern"
    ROLLBACK = "rollback"
    MITIGATION = "mitigation"
    RESOLUTION = "resolution"
    POSTMORTEM = "postmortem"
    MANUAL = "manual"


class EventSource(str, Enum):
    """Sources of timeline events."""

    PAGERDUTY = "pagerduty"
    SLACK = "slack"
    JIRA = "jira"
    GITHUB = "github"
    DATADOG = "datadog"
    PROMETHEUS = "prometheus"
    CLOUDWATCH = "cloudwatch"
    KUBERNETES = "kubernetes"
    MANUAL = "manual"
    SYSTEM = "system"


class EventSeverity(str, Enum):
    """Event severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TimelineEvent(BaseModel):
    """A single event in the incident timeline."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    incident_id: str
    timestamp: datetime
    event_type: EventType
    source: EventSource
    severity: EventSeverity = EventSeverity.INFO
    title: str
    description: str | None = None
    actor: str | None = None  # Who/what triggered the event
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)
    related_events: list[UUID] = Field(default_factory=list)
    raw_data: dict[str, Any] | None = None  # Original data from source
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TimelineGap(BaseModel):
    """Represents a gap in the timeline."""

    start_time: datetime
    end_time: datetime
    duration_seconds: float
    preceding_event_id: UUID | None = None
    following_event_id: UUID | None = None
    severity: str = "info"  # info, warning, critical based on duration


class TimelineEntry(BaseModel):
    """Timeline entry with computed properties for display."""

    model_config = ConfigDict(populate_by_name=True)

    event: TimelineEvent
    relative_time: str  # e.g., "+5m", "-2h"
    is_milestone: bool = False
    display_group: str | None = None  # For grouping related events
    icon: str | None = None
    color: str | None = None


class TimelineFilter(BaseModel):
    """Filters for querying timeline."""

    event_types: list[EventType] | None = None
    sources: list[EventSource] | None = None
    severities: list[EventSeverity] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    actors: list[str] | None = None
    tags: list[str] | None = None
    search_query: str | None = None


class TimelineSummary(BaseModel):
    """Summary statistics for a timeline."""

    incident_id: str
    total_events: int
    event_counts_by_type: dict[str, int]
    event_counts_by_source: dict[str, int]
    first_event: datetime | None
    last_event: datetime | None
    duration_seconds: float | None
    gaps: list[TimelineGap]
    key_milestones: list[UUID]


class TimelineExport(BaseModel):
    """Exported timeline for postmortems."""

    incident_id: str
    title: str
    exported_at: datetime = Field(default_factory=datetime.utcnow)
    summary: TimelineSummary
    entries: list[TimelineEntry]
    format_version: str = "1.0"
