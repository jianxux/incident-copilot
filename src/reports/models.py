"""Data models for scheduled reports."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReportType(StrEnum):
    """Types of scheduled reports."""

    DAILY_SUMMARY = "daily_summary"
    WEEKLY_RELIABILITY = "weekly_reliability"
    MONTHLY_ANALYSIS = "monthly_analysis"
    ON_DEMAND = "on_demand"


class ReportStatus(StrEnum):
    """Status of a report schedule."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ReportRunStatus(StrEnum):
    """Status of a report run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"


class DeliveryChannel(StrEnum):
    """Delivery channels for reports."""

    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    S3 = "s3"


class DeliveryConfig(BaseModel):
    """Configuration for a delivery channel."""

    channel: DeliveryChannel
    enabled: bool = True

    # Email-specific
    recipients: list[str] = Field(default_factory=list)
    subject_template: str | None = None

    # Slack-specific
    slack_channel: str | None = None
    slack_webhook_url: str | None = None
    thread_ts: str | None = None

    # Webhook-specific
    webhook_url: str | None = None
    webhook_headers: dict[str, str] = Field(default_factory=dict)
    webhook_method: str = "POST"

    # S3-specific
    s3_bucket: str | None = None
    s3_key_prefix: str | None = None


class ReportSchedule(BaseModel):
    """Schedule configuration for a report."""

    # Cron expression (e.g., "0 9 * * 1" for every Monday at 9am)
    cron_expression: str

    # Timezone for the schedule
    timezone: str = "UTC"

    # Next scheduled run time
    next_run_at: datetime | None = None

    # Last successful run time
    last_run_at: datetime | None = None

    # Whether to skip on holidays
    skip_holidays: bool = False

    # Holiday calendar (e.g., "US", "UK")
    holiday_calendar: str | None = None


class ReportFilter(BaseModel):
    """Filters to apply when generating reports."""

    # Service filters
    services: list[str] = Field(default_factory=list)
    exclude_services: list[str] = Field(default_factory=list)

    # Severity filters
    severities: list[str] = Field(default_factory=list)
    min_severity: str | None = None

    # Team filters
    teams: list[str] = Field(default_factory=list)

    # Time range override (in days, relative to report run time)
    time_range_days: int | None = None


class ReportTemplate(BaseModel):
    """Custom template configuration."""

    # Template format (markdown, html, json)
    format: str = "markdown"

    # Custom header/footer
    header: str | None = None
    footer: str | None = None

    # Logo URL for HTML reports
    logo_url: str | None = None

    # Include sections
    include_summary: bool = True
    include_metrics: bool = True
    include_trends: bool = True
    include_incidents: bool = True
    include_recommendations: bool = True

    # AI analysis options
    include_ai_insights: bool = True
    ai_model: str | None = None


class ReportConfig(BaseModel):
    """Configuration for a scheduled report."""

    id: str
    name: str
    description: str | None = None
    report_type: ReportType
    status: ReportStatus = ReportStatus.ACTIVE

    # Created/updated metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None

    # Schedule
    schedule: ReportSchedule

    # Delivery channels
    delivery_channels: list[DeliveryConfig] = Field(default_factory=list)

    # Filters
    filters: ReportFilter = Field(default_factory=ReportFilter)

    # Template customization
    template: ReportTemplate = Field(default_factory=ReportTemplate)

    # Tags for organization
    tags: list[str] = Field(default_factory=list)


class IncidentSummary(BaseModel):
    """Summary of an incident for reporting."""

    incident_id: str
    title: str
    service_name: str
    severity: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    duration_minutes: int | None = None
    mttr_seconds: float | None = None
    root_cause: str | None = None


class MetricsSummary(BaseModel):
    """Summary of metrics for a report period."""

    period_start: datetime
    period_end: datetime
    total_incidents: int = 0
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    incidents_by_service: dict[str, int] = Field(default_factory=dict)

    # MTTR metrics
    mean_mttr_minutes: float | None = None
    median_mttr_minutes: float | None = None
    p90_mttr_minutes: float | None = None

    # Time to acknowledge
    mean_tta_minutes: float | None = None

    # Comparison to previous period
    incident_count_change_percent: float | None = None
    mttr_change_percent: float | None = None
    trend: str = "stable"  # improving, degrading, stable


class ReportContent(BaseModel):
    """Content of a generated report."""

    # Report metadata
    report_config_id: str
    report_type: ReportType
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period_start: datetime
    period_end: datetime

    # Report title/subtitle
    title: str
    subtitle: str | None = None

    # Executive summary
    executive_summary: str | None = None

    # Metrics summary
    metrics: MetricsSummary | None = None

    # Incident list
    incidents: list[IncidentSummary] = Field(default_factory=list)

    # Trend analysis
    trends: dict[str, Any] = Field(default_factory=dict)

    # AI-generated insights
    ai_insights: list[str] = Field(default_factory=list)
    ai_recommendations: list[str] = Field(default_factory=list)

    # Rendered content in various formats
    markdown: str | None = None
    html: str | None = None
    json_data: dict[str, Any] | None = None


class ReportOutput(BaseModel):
    """Output of a report generation run."""

    id: str
    report_config_id: str
    run_status: ReportRunStatus = ReportRunStatus.PENDING

    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None

    # Trigger info
    triggered_by: str | None = None  # "schedule", "manual", "api"
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Content
    content: ReportContent | None = None

    # Delivery status per channel
    delivery_results: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Error info
    error_message: str | None = None
    error_details: dict[str, Any] | None = None


class ReportRunRequest(BaseModel):
    """Request to run a report manually."""

    # Override time range
    period_start: datetime | None = None
    period_end: datetime | None = None

    # Override filters
    filters: ReportFilter | None = None

    # Skip delivery (just generate)
    skip_delivery: bool = False

    # Specific channels to deliver to
    delivery_channels: list[DeliveryChannel] | None = None


class ReportCreateRequest(BaseModel):
    """Request to create a new report configuration."""

    name: str
    description: str | None = None
    report_type: ReportType
    cron_expression: str
    timezone: str = "UTC"
    delivery_channels: list[DeliveryConfig] = Field(default_factory=list)
    filters: ReportFilter | None = None
    template: ReportTemplate | None = None
    tags: list[str] = Field(default_factory=list)


class ReportUpdateRequest(BaseModel):
    """Request to update a report configuration."""

    name: str | None = None
    description: str | None = None
    status: ReportStatus | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    delivery_channels: list[DeliveryConfig] | None = None
    filters: ReportFilter | None = None
    template: ReportTemplate | None = None
    tags: list[str] | None = None
