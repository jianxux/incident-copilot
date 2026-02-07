"""Export system for Incident Copilot.

Provides functionality to export incidents, postmortems, reports, and analytics
in multiple formats (PDF, CSV, JSON, Markdown).

Features:
- Async export jobs for large datasets
- Configurable columns and fields
- Date range and other filters
- Related data inclusion (timeline, comments, action items)
- Export templates for reusable configurations
- Scheduled exports (daily, weekly, monthly)
- Multiple output formats with format-specific options

Usage:
    from src.export import ExportService, ExportRequest, ExportFormat, ExportType

    # Create export service
    service = ExportService()

    # Create an export request
    request = ExportRequest(
        export_type=ExportType.INCIDENTS,
        format=ExportFormat.CSV,
    )

    # Create and process export
    job = await service.create_export(request)

    # Download when complete
    content, filename, content_type = await service.download(job.id)

API Routes:
    Include the router in your FastAPI app:

    from src.export import router as export_router
    app.include_router(export_router, prefix="/api/v1")

    Endpoints:
    - POST /export - Create export job
    - GET /export/{job_id} - Get job status
    - GET /export/{job_id}/download - Download file
    - GET /export/{job_id}/result - Get result details
    - POST /export/{job_id}/cancel - Cancel job
    - DELETE /export/{job_id} - Delete job
    - GET /export - List jobs
    - POST /export/quick/incidents - Quick incident export
    - POST /export/quick/postmortems - Quick postmortem export
    - POST /export/quick/analytics - Quick analytics export
    - POST /export/templates - Create template
    - GET /export/templates - List templates
    - POST /export/templates/{id}/export - Export from template
    - POST /export/schedules - Create schedule
    - GET /export/schedules - List schedules
    - POST /export/schedules/{id}/run - Run schedule now
    - GET /export/stats - Get statistics
"""

from .formatters import CSVFormatter, JSONFormatter, MarkdownFormatter, PDFFormatter
from .models import (
    DEFAULT_ANALYTICS_COLUMNS,
    DEFAULT_INCIDENT_COLUMNS,
    DEFAULT_POSTMORTEM_COLUMNS,
    ColumnConfig,
    CSVOptions,
    DateRangeFilter,
    ExportFilter,
    ExportFormat,
    ExportJob,
    ExportJobStatus,
    ExportRequest,
    ExportResult,
    ExportScheduleFrequency,
    ExportStats,
    ExportTemplate,
    ExportType,
    JSONOptions,
    MarkdownOptions,
    PDFOptions,
    RelatedDataConfig,
    ScheduledExport,
)
from .routes import router
from .service import ExportService, get_export_service

__all__ = [
    # Service
    "ExportService",
    "get_export_service",
    # Routes
    "router",
    # Formatters
    "CSVFormatter",
    "JSONFormatter",
    "MarkdownFormatter",
    "PDFFormatter",
    # Models - Core
    "ExportFormat",
    "ExportType",
    "ExportJobStatus",
    "ExportScheduleFrequency",
    # Models - Request/Response
    "ExportRequest",
    "ExportJob",
    "ExportResult",
    "ExportStats",
    # Models - Configuration
    "ColumnConfig",
    "DateRangeFilter",
    "ExportFilter",
    "RelatedDataConfig",
    "ExportTemplate",
    "ScheduledExport",
    # Models - Format Options
    "PDFOptions",
    "CSVOptions",
    "JSONOptions",
    "MarkdownOptions",
    # Default columns
    "DEFAULT_INCIDENT_COLUMNS",
    "DEFAULT_POSTMORTEM_COLUMNS",
    "DEFAULT_ANALYTICS_COLUMNS",
]
