"""Data models for the export system."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ExportFormat(StrEnum):
    """Supported export formats."""

    PDF = "pdf"
    CSV = "csv"
    JSON = "json"
    MARKDOWN = "markdown"


class ExportType(StrEnum):
    """Types of data that can be exported."""

    INCIDENTS = "incidents"
    POSTMORTEMS = "postmortems"
    REPORTS = "reports"
    ANALYTICS = "analytics"
    TIMELINE = "timeline"
    ACTION_ITEMS = "action_items"


class ExportJobStatus(StrEnum):
    """Status of an export job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ExportScheduleFrequency(StrEnum):
    """Frequency for scheduled exports."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ColumnConfig(BaseModel):
    """Configuration for a single column in export."""

    field: str
    header: str | None = None
    include: bool = True
    format: str | None = None  # e.g., "datetime", "currency", "percentage"
    width: int | None = None  # For PDF/table exports


class DateRangeFilter(BaseModel):
    """Date range filter for exports."""

    start_date: datetime
    end_date: datetime

    def contains(self, dt: datetime) -> bool:
        """Check if a datetime falls within this range."""
        return self.start_date <= dt <= self.end_date


class ExportFilter(BaseModel):
    """Filters to apply when exporting data."""

    date_range: DateRangeFilter | None = None
    services: list[str] = Field(default_factory=list)
    severities: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_by: list[str] = Field(default_factory=list)
    include_resolved: bool = True
    include_active: bool = True


class RelatedDataConfig(BaseModel):
    """Configuration for including related data in exports."""

    include_timeline: bool = True
    include_comments: bool = True
    include_attachments: bool = False
    include_action_items: bool = True
    include_metrics: bool = True
    include_root_cause: bool = True
    include_impact: bool = True
    max_timeline_events: int | None = None
    max_comments: int | None = None


class PDFOptions(BaseModel):
    """PDF-specific export options."""

    page_size: str = "A4"  # A4, Letter, Legal
    orientation: str = "portrait"  # portrait, landscape
    include_cover_page: bool = True
    include_toc: bool = True
    include_header: bool = True
    include_footer: bool = True
    header_text: str | None = None
    footer_text: str | None = None
    logo_url: str | None = None
    font_size: int = 10
    margins: dict[str, float] = Field(
        default_factory=lambda: {"top": 72, "bottom": 72, "left": 72, "right": 72}
    )


class CSVOptions(BaseModel):
    """CSV-specific export options."""

    delimiter: str = ","
    quote_char: str = '"'
    include_header: bool = True
    encoding: str = "utf-8"
    line_ending: str = "\n"
    escape_formulas: bool = True  # Prevent CSV injection


class JSONOptions(BaseModel):
    """JSON-specific export options."""

    indent: int | None = 2
    include_schema: bool = False
    schema_version: str = "1.0"
    flatten: bool = False  # Flatten nested objects
    date_format: str = "iso"  # iso, timestamp, custom
    custom_date_format: str | None = None


class MarkdownOptions(BaseModel):
    """Markdown-specific export options."""

    include_toc: bool = True
    heading_style: str = "atx"  # atx (#), setext (underline)
    include_metadata: bool = True
    code_block_style: str = "fenced"  # fenced (```), indented
    table_alignment: str = "left"  # left, center, right


class ExportTemplate(BaseModel):
    """Reusable export configuration template."""

    id: str
    name: str
    description: str | None = None
    export_type: ExportType
    format: ExportFormat
    columns: list[ColumnConfig] = Field(default_factory=list)
    filters: ExportFilter = Field(default_factory=ExportFilter)
    related_data: RelatedDataConfig = Field(default_factory=RelatedDataConfig)
    pdf_options: PDFOptions | None = None
    csv_options: CSVOptions | None = None
    json_options: JSONOptions | None = None
    markdown_options: MarkdownOptions | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None
    is_default: bool = False
    organization_id: str | None = None


class ExportRequest(BaseModel):
    """Request to create an export job."""

    export_type: ExportType
    format: ExportFormat
    filters: ExportFilter = Field(default_factory=ExportFilter)
    columns: list[ColumnConfig] = Field(default_factory=list)
    related_data: RelatedDataConfig = Field(default_factory=RelatedDataConfig)
    template_id: str | None = None

    # Format-specific options
    pdf_options: PDFOptions | None = None
    csv_options: CSVOptions | None = None
    json_options: JSONOptions | None = None
    markdown_options: MarkdownOptions | None = None

    # Job options
    async_processing: bool = True
    notify_on_completion: bool = True
    notification_email: str | None = None
    notification_webhook: str | None = None
    expiry_hours: int = 24


class ExportJob(BaseModel):
    """An export job tracking entity."""

    id: str
    request: ExportRequest
    status: ExportJobStatus = ExportJobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    created_by: str | None = None
    organization_id: str | None = None

    # Progress tracking
    progress_percent: int = 0
    records_processed: int = 0
    total_records: int | None = None
    current_step: str | None = None

    # Result info
    file_path: str | None = None
    file_size_bytes: int | None = None
    file_name: str | None = None
    download_url: str | None = None

    # Error tracking
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    retry_count: int = 0
    max_retries: int = 3


class ExportResult(BaseModel):
    """Result of a completed export."""

    job_id: str
    status: ExportJobStatus
    format: ExportFormat
    export_type: ExportType
    file_name: str
    file_size_bytes: int
    download_url: str | None = None
    file_path: str | None = None
    records_exported: int
    created_at: datetime
    completed_at: datetime
    expires_at: datetime
    checksum: str | None = None  # SHA256 of file content


class ScheduledExport(BaseModel):
    """Configuration for a scheduled export."""

    id: str
    name: str
    description: str | None = None
    enabled: bool = True
    frequency: ExportScheduleFrequency
    cron_expression: str | None = None  # For custom frequency
    timezone: str = "UTC"
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_job_id: str | None = None

    # Export configuration
    request: ExportRequest

    # Delivery configuration
    delivery_email: list[str] = Field(default_factory=list)
    delivery_webhook: str | None = None
    delivery_s3_bucket: str | None = None
    delivery_s3_prefix: str | None = None

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None
    organization_id: str | None = None


class ExportStats(BaseModel):
    """Statistics about export usage."""

    total_exports: int = 0
    exports_by_format: dict[str, int] = Field(default_factory=dict)
    exports_by_type: dict[str, int] = Field(default_factory=dict)
    average_processing_time_seconds: float | None = None
    total_records_exported: int = 0
    total_file_size_bytes: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None


# Default column configurations for different export types
DEFAULT_INCIDENT_COLUMNS = [
    ColumnConfig(field="incident_id", header="Incident ID"),
    ColumnConfig(field="title", header="Title"),
    ColumnConfig(field="severity", header="Severity"),
    ColumnConfig(field="service_name", header="Service"),
    ColumnConfig(field="status", header="Status"),
    ColumnConfig(field="triggered_at", header="Triggered At", format="datetime"),
    ColumnConfig(field="resolved_at", header="Resolved At", format="datetime"),
    ColumnConfig(field="duration_minutes", header="Duration (min)"),
    ColumnConfig(field="assignee", header="Assignee"),
]

DEFAULT_POSTMORTEM_COLUMNS = [
    ColumnConfig(field="id", header="Postmortem ID"),
    ColumnConfig(field="incident_id", header="Incident ID"),
    ColumnConfig(field="title", header="Title"),
    ColumnConfig(field="service_name", header="Service"),
    ColumnConfig(field="severity", header="Severity"),
    ColumnConfig(field="status", header="Status"),
    ColumnConfig(field="incident_duration_minutes", header="Duration (min)"),
    ColumnConfig(field="created_at", header="Created At", format="datetime"),
    ColumnConfig(field="created_by", header="Author"),
]

DEFAULT_ANALYTICS_COLUMNS = [
    ColumnConfig(field="metric_name", header="Metric"),
    ColumnConfig(field="value", header="Value"),
    ColumnConfig(field="period", header="Period"),
    ColumnConfig(field="service_name", header="Service"),
    ColumnConfig(field="trend", header="Trend"),
]
