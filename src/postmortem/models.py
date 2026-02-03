"""Data models for postmortem generation."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PostmortemFormat(str, Enum):
    """Output formats for postmortems."""

    MARKDOWN = "markdown"
    JSON = "json"
    CONFLUENCE = "confluence"
    SLACK = "slack"


class PostmortemStatus(str, Enum):
    """Status of a postmortem."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"


class TimelineEventType(str, Enum):
    """Types of timeline events."""

    ALERT_TRIGGERED = "alert_triggered"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    INVESTIGATION_STARTED = "investigation_started"
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"
    MITIGATION_STARTED = "mitigation_started"
    MITIGATION_COMPLETED = "mitigation_completed"
    INCIDENT_RESOLVED = "incident_resolved"
    DEPLOYMENT = "deployment"
    CONFIGURATION_CHANGE = "configuration_change"
    ESCALATION = "escalation"
    COMMUNICATION = "communication"
    OTHER = "other"


class TimelineEvent(BaseModel):
    """A single event in the incident timeline."""

    timestamp: datetime
    event_type: TimelineEventType = TimelineEventType.OTHER
    title: str
    description: str | None = None
    actor: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RootCauseAnalysis(BaseModel):
    """Root cause analysis section of the postmortem."""

    primary_cause: str
    contributing_factors: list[str] = Field(default_factory=list)
    trigger: str | None = None
    detection_method: str | None = None
    why_not_prevented: str | None = None
    confidence_level: str = "medium"


class ImpactAssessment(BaseModel):
    """Impact assessment section of the postmortem."""

    severity: str
    duration_minutes: int | None = None
    users_affected: int | None = None
    users_affected_description: str | None = None
    revenue_impact: str | None = None
    data_loss: bool = False
    data_loss_description: str | None = None
    sla_breach: bool = False
    sla_breach_description: str | None = None
    regions_affected: list[str] = Field(default_factory=list)
    services_affected: list[str] = Field(default_factory=list)
    summary: str | None = None


class ActionItemPriority(str, Enum):
    """Priority levels for action items."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionItemStatus(str, Enum):
    """Status of action items."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    WONT_DO = "wont_do"


class ActionItem(BaseModel):
    """A follow-up action item from the postmortem."""

    id: str
    title: str
    description: str | None = None
    priority: ActionItemPriority = ActionItemPriority.MEDIUM
    status: ActionItemStatus = ActionItemStatus.TODO
    owner: str | None = None
    due_date: datetime | None = None
    category: str | None = None
    ticket_url: str | None = None


class ResolutionStep(BaseModel):
    """A step taken to resolve the incident."""

    order: int
    description: str
    actor: str | None = None
    timestamp: datetime | None = None
    successful: bool = True


class Postmortem(BaseModel):
    """Complete postmortem document."""

    id: str
    incident_id: str
    title: str
    status: PostmortemStatus = PostmortemStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    approved_by: str | None = None
    version: int = 1
    incident_started_at: datetime | None = None
    incident_resolved_at: datetime | None = None
    incident_duration_minutes: int | None = None
    service_name: str
    severity: str
    executive_summary: str
    timeline: list[TimelineEvent] = Field(default_factory=list)
    root_cause: RootCauseAnalysis | None = None
    impact: ImpactAssessment | None = None
    resolution_steps: list[ResolutionStep] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    lessons_learned: list[str] = Field(default_factory=list)
    what_went_well: list[str] = Field(default_factory=list)
    what_went_poorly: list[str] = Field(default_factory=list)
    lucky_factors: list[str] = Field(default_factory=list)
    alert_url: str | None = None
    dashboard_url: str | None = None
    runbook_url: str | None = None
    related_incidents: list[str] = Field(default_factory=list)
    ai_generated: bool = True
    ai_model: str | None = None
    ai_confidence: float | None = None


class PostmortemGenerateRequest(BaseModel):
    """Request to generate a postmortem."""

    incident_id: str
    format: PostmortemFormat = PostmortemFormat.MARKDOWN
    include_ai_analysis: bool = True
    custom_context: str | None = None


class PostmortemUpdateRequest(BaseModel):
    """Request to update a postmortem."""

    title: str | None = None
    executive_summary: str | None = None
    status: PostmortemStatus | None = None
    root_cause: RootCauseAnalysis | None = None
    impact: ImpactAssessment | None = None
    action_items: list[ActionItem] | None = None
    lessons_learned: list[str] | None = None
    what_went_well: list[str] | None = None
    what_went_poorly: list[str] | None = None
