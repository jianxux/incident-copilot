"""Data models for Incident Templates."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TemplateCategory(StrEnum):
    """Categories for incident templates."""

    INFRASTRUCTURE = "infrastructure"
    DATABASE = "database"
    DEPLOYMENT = "deployment"
    SECURITY = "security"
    NETWORK = "network"
    APPLICATION = "application"
    THIRD_PARTY = "third_party"
    CUSTOM = "custom"


class FieldType(StrEnum):
    """Template field types."""

    TEXT = "text"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    USER = "user"
    SERVICE = "service"
    DATETIME = "datetime"
    URL = "url"
    NUMBER = "number"


class TemplateField(BaseModel):
    """A configurable field within a template."""

    name: str = Field(..., description="Field identifier")
    label: str = Field(..., description="Display label")
    field_type: FieldType = FieldType.TEXT
    required: bool = False
    default_value: Any = None
    options: list[str] = Field(
        default_factory=list, description="Options for select fields"
    )
    placeholder: str | None = None
    description: str | None = None


class InitialAction(BaseModel):
    """An initial action to take when using template."""

    order: int = Field(ge=1, description="Action order")
    title: str
    description: str | None = None
    assignee_role: str | None = None  # e.g., "incident_commander", "oncall"
    auto_create_task: bool = False
    estimated_minutes: int | None = None


class StakeholderRole(BaseModel):
    """Stakeholder to notify for this incident type."""

    role: str  # e.g., "engineering_lead", "security_team"
    notification_channel: str = "slack"  # slack, email, pagerduty
    required: bool = True
    escalation_delay_minutes: int | None = None


class MatchPattern(BaseModel):
    """Pattern for auto-matching templates to alerts."""

    field: str  # alert field to match: title, service, source, tags
    operator: str = "contains"  # contains, equals, regex, starts_with
    value: str
    weight: float = Field(default=1.0, ge=0.0, le=10.0)


class TemplateVersion(BaseModel):
    """Version history for a template."""

    version: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None
    changes: str | None = None
    template_snapshot: dict = Field(default_factory=dict)


class TemplateAnalytics(BaseModel):
    """Usage analytics for a template."""

    usage_count: int = 0
    last_used_at: datetime | None = None
    avg_resolution_time_minutes: float | None = None
    success_rate: float | None = None  # % of incidents resolved without escalation
    feedback_score: float | None = None  # 1-5 user rating


class IncidentTemplate(BaseModel):
    """Incident template with all configuration."""

    id: str = Field(..., description="Unique template ID")
    name: str = Field(..., description="Template name")
    description: str | None = None
    category: TemplateCategory = TemplateCategory.CUSTOM

    # Template content
    title_pattern: str = Field(..., description="Title pattern with {placeholders}")
    severity_default: str = "medium"

    # Runbooks and documentation
    runbook_urls: list[str] = Field(default_factory=list)
    documentation_urls: list[str] = Field(default_factory=list)

    # Actions and stakeholders
    initial_actions: list[InitialAction] = Field(default_factory=list)
    stakeholders: list[StakeholderRole] = Field(default_factory=list)

    # Custom fields
    fields: list[TemplateField] = Field(default_factory=list)

    # Auto-matching
    match_patterns: list[MatchPattern] = Field(default_factory=list)
    match_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    # Organization
    organization_id: str | None = None
    is_builtin: bool = False
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)

    # Versioning
    version: int = 1
    version_history: list[TemplateVersion] = Field(default_factory=list)

    # Analytics
    analytics: TemplateAnalytics = Field(default_factory=TemplateAnalytics)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None


class TemplateMatch(BaseModel):
    """Result of template matching against an alert."""

    template_id: str
    template_name: str
    score: float = Field(ge=0.0, le=1.0)
    matched_patterns: list[str] = Field(default_factory=list)
    category: TemplateCategory


class AppliedTemplate(BaseModel):
    """Result of applying a template to create incident fields."""

    template_id: str
    template_name: str
    generated_title: str
    severity: str
    runbook_urls: list[str] = Field(default_factory=list)
    initial_actions: list[InitialAction] = Field(default_factory=list)
    stakeholders: list[StakeholderRole] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TemplateExport(BaseModel):
    """Export format for templates."""

    version: str = "1.0"
    exported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    templates: list[IncidentTemplate] = Field(default_factory=list)


class TemplateCreateRequest(BaseModel):
    """Request to create a new template."""

    name: str
    description: str | None = None
    category: TemplateCategory = TemplateCategory.CUSTOM
    title_pattern: str
    severity_default: str = "medium"
    runbook_urls: list[str] = Field(default_factory=list)
    initial_actions: list[InitialAction] = Field(default_factory=list)
    stakeholders: list[StakeholderRole] = Field(default_factory=list)
    fields: list[TemplateField] = Field(default_factory=list)
    match_patterns: list[MatchPattern] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class TemplateUpdateRequest(BaseModel):
    """Request to update a template."""

    name: str | None = None
    description: str | None = None
    category: TemplateCategory | None = None
    title_pattern: str | None = None
    severity_default: str | None = None
    runbook_urls: list[str] | None = None
    initial_actions: list[InitialAction] | None = None
    stakeholders: list[StakeholderRole] | None = None
    fields: list[TemplateField] | None = None
    match_patterns: list[MatchPattern] | None = None
    is_active: bool | None = None
    tags: list[str] | None = None
