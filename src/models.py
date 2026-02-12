"""Data models for Incident Copilot."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Incident severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertSource(StrEnum):
    """Alert source systems."""

    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    MANUAL = "manual"


# --- On-Call Models ---


class OnCallPerson(BaseModel):
    """A person currently on-call."""

    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    slack_user_id: str | None = None
    provider: str = "unknown"
    raw_data: dict = Field(default_factory=dict)

    @property
    def slack_mention(self) -> str:
        """Return Slack mention format if Slack ID is available."""
        if self.slack_user_id:
            return f"<@{self.slack_user_id}>"
        return self.name

    @property
    def teams_mention(self) -> str:
        """Return Teams mention format (requires email)."""
        if self.email:
            return f"<at>{self.email}</at>"
        return self.name


class OnCallRoster(BaseModel):
    """On-call roster from PagerDuty or Opsgenie."""

    schedule_id: str
    schedule_name: str
    provider: str  # "pagerduty" or "opsgenie"
    oncall_persons: list[OnCallPerson] = Field(default_factory=list)
    fetched_at: datetime
    schedule_url: str | None = None

    @property
    def primary_oncall(self) -> OnCallPerson | None:
        """Return the primary (first) on-call person."""
        return self.oncall_persons[0] if self.oncall_persons else None

    @property
    def oncall_names(self) -> list[str]:
        """Return list of on-call person names."""
        return [p.name for p in self.oncall_persons]

    @property
    def has_oncall(self) -> bool:
        """Check if anyone is currently on-call."""
        return len(self.oncall_persons) > 0


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


class OpsgenieAlert(BaseModel):
    """Parsed Opsgenie alert from webhook."""

    alert_id: str
    tiny_id: str | None = None
    title: str
    description: str | None = None
    severity: Severity = Severity.MEDIUM
    service_name: str
    source: str | None = None
    triggered_at: datetime
    url: str | None = None
    tags: list[str] = Field(default_factory=list)


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


# --- GitLab Models ---


class MergeRequest(BaseModel):
    """A merge request from GitLab."""

    iid: int
    title: str
    author: str
    merged_at: datetime
    url: str | None = None
    labels: list[str] = Field(default_factory=list)


class Pipeline(BaseModel):
    """A CI/CD pipeline from GitLab."""

    id: int
    status: str  # success, failed, running, pending, canceled
    ref: str  # branch name
    sha: str
    created_at: datetime
    url: str | None = None


class GitLabContext(BaseModel):
    """GitLab context for a service."""

    project: str
    recent_deploys: list[Deployment] = Field(default_factory=list)
    merge_requests: list[MergeRequest] = Field(default_factory=list)
    pipelines: list[Pipeline] = Field(default_factory=list)
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


# --- Topology Models ---


class TopologyContext(BaseModel):
    """Service topology context showing dependencies and blast radius."""

    service_id: str
    service_name: str
    criticality: str = "unknown"
    team: str | None = None

    # What this service depends on (if these fail, we're affected)
    upstream_services: list[str] = Field(default_factory=list)

    # What depends on this service (blast radius - what breaks if we fail)
    downstream_services: list[str] = Field(default_factory=list)

    # Blast radius details
    blast_radius_count: int = 0
    critical_services_affected: list[str] = Field(default_factory=list)
    risk_score: float = 0.0

    # Critical dependency paths
    critical_paths: list[list[str]] = Field(default_factory=list)


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

    # GitLab context
    gitlab: GitLabContext | None = None

    # Datadog context
    datadog: DatadogContext | None = None

    # Service topology (dependencies and blast radius)
    topology: TopologyContext | None = None

    # AI summary
    ai_summary: AILogSummary | None = None

    # AI Verdict — opinionated root cause assessment (Any to avoid circular import)
    verdict: Any = None

    # Similar past incidents
    similar_incidents: list[PastIncident] = Field(default_factory=list)

    # Linked runbooks
    runbooks: list[RunbookLink] = Field(default_factory=list)

    # On-call roster
    oncall: OnCallRoster | None = None

    # Service info
    owners: list[str] = Field(default_factory=list)
    runbook_url: str | None = None  # Deprecated: use runbooks list
    dashboard_url: str | None = None

    # Metadata
    assembled_at: datetime = Field(default_factory=datetime.utcnow)
    assembly_time_ms: int | None = None
    latency_report: Any = None
    errors: list[str] = Field(default_factory=list)
