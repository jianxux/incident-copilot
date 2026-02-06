"""Data models for incident templates."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TemplateCategory(str, Enum):
    """Categories for incident templates."""

    INFRASTRUCTURE = "infrastructure"
    APPLICATION = "application"
    SECURITY = "security"
    NETWORK = "network"
    DATABASE = "database"
    OBSERVABILITY = "observability"
    CLOUD = "cloud"
    GENERAL = "general"


class TemplateStepStatus(str, Enum):
    """Status of a template step during incident response."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class TemplateStep(BaseModel):
    """A single step in an incident response template."""

    id: str
    order: int
    title: str
    description: str | None = None
    
    # Suggested action can be a command, script, or instruction
    suggested_action: str | None = None
    
    # Time estimate in minutes
    time_estimate_minutes: int | None = None
    
    # Optional: link to runbook for this step
    runbook_url: str | None = None
    runbook_id: str | None = None
    
    # Optional: role best suited for this step
    recommended_role: str | None = None
    
    # Is this step critical/required?
    is_critical: bool = False
    
    # Conditions for when this step applies
    conditions: list[str] = Field(default_factory=list)
    
    # Tags for filtering/grouping steps
    tags: list[str] = Field(default_factory=list)
    
    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class RenderedStep(BaseModel):
    """A step rendered for a specific incident with status tracking."""

    step_id: str
    order: int
    title: str
    description: str | None = None
    suggested_action: str | None = None
    time_estimate_minutes: int | None = None
    runbook_url: str | None = None
    is_critical: bool = False
    
    # Runtime status
    status: TemplateStepStatus = TemplateStepStatus.PENDING
    completed_at: datetime | None = None
    completed_by: str | None = None
    notes: str | None = None
    
    # Checkbox state for UI
    checked: bool = False


class IncidentTemplate(BaseModel):
    """An incident response template."""

    id: str
    name: str
    description: str
    category: TemplateCategory
    
    # Template steps
    steps: list[TemplateStep] = Field(default_factory=list)
    
    # Matching criteria
    keywords: list[str] = Field(default_factory=list)
    service_tags: list[str] = Field(default_factory=list)
    severity_levels: list[str] = Field(default_factory=list)  # e.g., ["critical", "high"]
    
    # Multi-tenant support
    tenant_id: str | None = None  # None means built-in/global template
    is_builtin: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    version: int = 1
    
    # Linked runbooks at template level
    runbook_ids: list[str] = Field(default_factory=list)
    runbook_urls: list[str] = Field(default_factory=list)
    
    # Usage stats
    use_count: int = 0
    last_used_at: datetime | None = None
    
    # Whether this template is active
    enabled: bool = True
    
    # Tags for additional categorization
    tags: list[str] = Field(default_factory=list)
    
    # Total estimated time based on steps
    @property
    def total_time_estimate_minutes(self) -> int:
        """Calculate total estimated time from all steps."""
        return sum(
            step.time_estimate_minutes or 0 
            for step in self.steps
        )
    
    @property
    def critical_steps_count(self) -> int:
        """Count of critical steps."""
        return sum(1 for step in self.steps if step.is_critical)


class TemplateMatch(BaseModel):
    """A template matched to an incident."""

    template_id: str
    template_name: str
    category: TemplateCategory
    description: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)
    matched_services: list[str] = Field(default_factory=list)
    matched_severity: bool = False
    step_count: int = 0
    total_time_estimate_minutes: int = 0


class RenderedChecklist(BaseModel):
    """A rendered incident checklist from a template."""

    id: str
    incident_id: str
    template_id: str
    template_name: str
    category: TemplateCategory
    
    # Rendered steps with status
    steps: list[RenderedStep] = Field(default_factory=list)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Progress tracking
    @property
    def total_steps(self) -> int:
        return len(self.steps)
    
    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == TemplateStepStatus.COMPLETED)
    
    @property
    def progress_percent(self) -> float:
        if not self.steps:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100


class TemplateCreateRequest(BaseModel):
    """Request to create a new template."""

    name: str
    description: str
    category: TemplateCategory
    steps: list[TemplateStep] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    service_tags: list[str] = Field(default_factory=list)
    severity_levels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    runbook_ids: list[str] = Field(default_factory=list)
    runbook_urls: list[str] = Field(default_factory=list)
    tenant_id: str | None = None


class TemplateUpdateRequest(BaseModel):
    """Request to update an existing template."""

    name: str | None = None
    description: str | None = None
    category: TemplateCategory | None = None
    steps: list[TemplateStep] | None = None
    keywords: list[str] | None = None
    service_tags: list[str] | None = None
    severity_levels: list[str] | None = None
    tags: list[str] | None = None
    runbook_ids: list[str] | None = None
    runbook_urls: list[str] | None = None
    enabled: bool | None = None
