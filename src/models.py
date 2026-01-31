"""Data models for Incident Copilot."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Incident severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertSource(str, Enum):
    """Alert source systems."""

    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    MANUAL = "manual"


# --- PagerDuty Models ---


class PagerDutyIncident(BaseModel):
    """Parsed PagerDuty incident from webhook."""

    incident_id: str
    incident_number: int | None = None
    title: str
    description: str | None = None
    severity: Severity = Severity.MEDIUM
    service_name: str
    service_id: str | None = None
    triggered_at: datetime
    html_url: str | None = None
    assigned_to: list[str] = Field(default_factory=list)


# --- GitHub Models ---


class Deployment(BaseModel):
    """A deployment/commit from GitHub."""

    sha: str
    short_sha: str
    author: str
    message: str
    timestamp: datetime
    files_changed: list[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    url: str | None = None


class GitHubContext(BaseModel):
    """GitHub context for a service."""

    repo: str
    recent_deploys: list[Deployment] = Field(default_factory=list)
    codeowners: list[str] = Field(default_factory=list)


# --- Datadog Models ---


class LogEntry(BaseModel):
    """A log entry from Datadog."""

    timestamp: datetime
    level: str
    message: str
    service: str | None = None
    host: str | None = None
    attributes: dict = Field(default_factory=dict)


class LogSummary(BaseModel):
    """Summarized log patterns."""

    pattern: str
    count: int
    level: str
    sample_message: str
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class MetricSnapshot(BaseModel):
    """Metrics snapshot from Datadog."""

    error_rate: float | None = None
    error_rate_baseline: float | None = None
    latency_p99_ms: float | None = None
    request_count: int | None = None
    time_range_minutes: int = 5


class DatadogContext(BaseModel):
    """Datadog context for a service."""

    service: str
    logs: list[LogEntry] = Field(default_factory=list)
    log_summaries: list[LogSummary] = Field(default_factory=list)
    metrics: MetricSnapshot | None = None


# --- AI Models ---


class AILogSummary(BaseModel):
    """AI-generated log summary."""

    top_issues: list[str]
    explanation: str
    likely_cause: str | None = None
    suggested_actions: list[str] = Field(default_factory=list)


# --- Past Incidents ---


class PastIncident(BaseModel):
    """A past incident for similarity matching."""

    incident_id: str
    title: str
    service: str
    description: str | None = None
    root_cause: str | None = None
    resolution: str | None = None
    occurred_at: datetime
    resolved_at: datetime | None = None
    similarity_score: float | None = None


# --- Runbook Models ---


class RunbookLink(BaseModel):
    """A runbook linked to an incident."""

    title: str
    url: str
    source: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list)


# --- Context Card ---


class ContextCard(BaseModel):
    """The assembled context card delivered to engineers."""

    # Alert info
    incident_id: str
    title: str
    severity: Severity
    service_name: str
    triggered_at: datetime
    alert_url: str | None = None

    # GitHub context
    github: GitHubContext | None = None

    # Datadog context
    datadog: DatadogContext | None = None

    # AI summary
    ai_summary: AILogSummary | None = None

    # Similar past incidents
    similar_incidents: list[PastIncident] = Field(default_factory=list)

    # Linked runbooks
    runbooks: list[RunbookLink] = Field(default_factory=list)

    # Service info
    owners: list[str] = Field(default_factory=list)
    runbook_url: str | None = None  # Deprecated: use runbooks list
    dashboard_url: str | None = None

    # Metadata
    assembled_at: datetime = Field(default_factory=datetime.utcnow)
    assembly_time_ms: int | None = None
    errors: list[str] = Field(default_factory=list)
