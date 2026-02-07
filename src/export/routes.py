"""FastAPI routes for the export system."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .models import (
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
    RelatedDataConfig,
    ScheduledExport,
)
from .service import ExportService, get_export_service

router = APIRouter(prefix="/export", tags=["export"])


# Request/Response models
class CreateExportRequest(BaseModel):
    """Request body for creating an export."""

    export_type: ExportType
    format: ExportFormat
    filters: ExportFilter = Field(default_factory=ExportFilter)
    related_data: RelatedDataConfig = Field(default_factory=RelatedDataConfig)
    template_id: str | None = None
    async_processing: bool = True
    notify_on_completion: bool = False
    notification_email: str | None = None
    notification_webhook: str | None = None
    expiry_hours: int = 24


class CreateTemplateRequest(BaseModel):
    """Request body for creating an export template."""

    name: str
    description: str | None = None
    export_type: ExportType
    format: ExportFormat
    filters: ExportFilter = Field(default_factory=ExportFilter)
    related_data: RelatedDataConfig = Field(default_factory=RelatedDataConfig)
    is_default: bool = False


class CreateScheduleRequest(BaseModel):
    """Request body for creating a scheduled export."""

    name: str
    description: str | None = None
    frequency: ExportScheduleFrequency
    cron_expression: str | None = None
    timezone: str = "UTC"
    request: CreateExportRequest
    delivery_email: list[str] = Field(default_factory=list)
    delivery_webhook: str | None = None


class UpdateScheduleRequest(BaseModel):
    """Request body for updating a scheduled export."""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    frequency: ExportScheduleFrequency | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    delivery_email: list[str] | None = None
    delivery_webhook: str | None = None


class ExportJobResponse(BaseModel):
    """Response for export job status."""

    id: str
    status: ExportJobStatus
    progress_percent: int
    records_processed: int
    total_records: int | None
    current_step: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    download_url: str | None
    file_name: str | None
    file_size_bytes: int | None
    error_message: str | None

    @classmethod
    def from_job(cls, job: ExportJob) -> "ExportJobResponse":
        return cls(
            id=job.id,
            status=job.status,
            progress_percent=job.progress_percent,
            records_processed=job.records_processed,
            total_records=job.total_records,
            current_step=job.current_step,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            expires_at=job.expires_at,
            download_url=job.download_url,
            file_name=job.file_name,
            file_size_bytes=job.file_size_bytes,
            error_message=job.error_message,
        )


class ExportListResponse(BaseModel):
    """Response for listing exports."""

    jobs: list[ExportJobResponse]
    total: int
    limit: int
    offset: int


class TemplateListResponse(BaseModel):
    """Response for listing templates."""

    templates: list[ExportTemplate]
    total: int


class ScheduleListResponse(BaseModel):
    """Response for listing schedules."""

    schedules: list[ScheduledExport]
    total: int


# Dependency
def get_service() -> ExportService:
    """Dependency to get export service."""
    return get_export_service()


# Export job routes
@router.post("", response_model=ExportJobResponse)
async def create_export(
    request: CreateExportRequest,
    background_tasks: BackgroundTasks,
    service: Annotated[ExportService, Depends(get_service)],
) -> ExportJobResponse:
    """Create a new export job.

    If async_processing is True (default), the export will be processed in the background
    and you should poll the status endpoint to check for completion.
    """
    export_request = ExportRequest(
        export_type=request.export_type,
        format=request.format,
        filters=request.filters,
        related_data=request.related_data,
        template_id=request.template_id,
        async_processing=request.async_processing,
        notify_on_completion=request.notify_on_completion,
        notification_email=request.notification_email,
        notification_webhook=request.notification_webhook,
        expiry_hours=request.expiry_hours,
    )

    job = await service.create_export(export_request)
    return ExportJobResponse.from_job(job)


@router.get("/{job_id}", response_model=ExportJobResponse)
async def get_export_status(
    job_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> ExportJobResponse:
    """Get the status of an export job."""
    job = await service.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    return ExportJobResponse.from_job(job)


@router.get("/{job_id}/result", response_model=ExportResult)
async def get_export_result(
    job_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> ExportResult:
    """Get the result of a completed export job."""
    result = await service.get_result(job_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Export result not found or job not completed",
        )
    return result


@router.get("/{job_id}/download")
async def download_export(
    job_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> StreamingResponse:
    """Download the exported file."""
    result = await service.download(job_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Export file not found or job not completed",
        )

    content, filename, content_type = result

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )


@router.post("/{job_id}/cancel")
async def cancel_export(
    job_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> dict[str, bool]:
    """Cancel a pending or processing export job."""
    success = await service.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel job (not found or already completed)",
        )
    return {"cancelled": True}


@router.delete("/{job_id}")
async def delete_export(
    job_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> dict[str, bool]:
    """Delete an export job and its file."""
    success = await service.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Export job not found")
    return {"deleted": True}


@router.get("", response_model=ExportListResponse)
async def list_exports(
    service: Annotated[ExportService, Depends(get_service)],
    status: ExportJobStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ExportListResponse:
    """List export jobs."""
    jobs = await service.list_jobs(status=status, limit=limit, offset=offset)
    return ExportListResponse(
        jobs=[ExportJobResponse.from_job(j) for j in jobs],
        total=len(jobs),  # Would need count query in production
        limit=limit,
        offset=offset,
    )


# Quick export routes (synchronous, returns file directly)
@router.post("/quick/incidents")
async def quick_export_incidents(
    format: ExportFormat = Query(default=ExportFormat.CSV),
    service: Annotated[ExportService, Depends(get_service)] = None,
    services: list[str] | None = Query(default=None),
    severities: list[str] | None = Query(default=None),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> StreamingResponse:
    """Quick synchronous export of incidents."""
    from .models import DateRangeFilter

    filters = ExportFilter(
        services=services or [],
        severities=severities or [],
    )
    if start_date and end_date:
        filters.date_range = DateRangeFilter(start_date=start_date, end_date=end_date)

    request = ExportRequest(
        export_type=ExportType.INCIDENTS,
        format=format,
        filters=filters,
        async_processing=False,
    )

    job = await service.create_export(request)
    result = await service.download(job.id)

    if not result:
        raise HTTPException(status_code=500, detail="Export failed")

    content, filename, content_type = result

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/quick/postmortems")
async def quick_export_postmortems(
    format: ExportFormat = Query(default=ExportFormat.MARKDOWN),
    service: Annotated[ExportService, Depends(get_service)] = None,
    services: list[str] | None = Query(default=None),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> StreamingResponse:
    """Quick synchronous export of postmortems."""
    from .models import DateRangeFilter

    filters = ExportFilter(services=services or [])
    if start_date and end_date:
        filters.date_range = DateRangeFilter(start_date=start_date, end_date=end_date)

    request = ExportRequest(
        export_type=ExportType.POSTMORTEMS,
        format=format,
        filters=filters,
        async_processing=False,
    )

    job = await service.create_export(request)
    result = await service.download(job.id)

    if not result:
        raise HTTPException(status_code=500, detail="Export failed")

    content, filename, content_type = result

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/quick/analytics")
async def quick_export_analytics(
    format: ExportFormat = Query(default=ExportFormat.JSON),
    service: Annotated[ExportService, Depends(get_service)] = None,
) -> StreamingResponse:
    """Quick synchronous export of analytics."""
    request = ExportRequest(
        export_type=ExportType.ANALYTICS,
        format=format,
        async_processing=False,
    )

    job = await service.create_export(request)
    result = await service.download(job.id)

    if not result:
        raise HTTPException(status_code=500, detail="Export failed")

    content, filename, content_type = result

    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# Template routes
@router.post("/templates", response_model=ExportTemplate)
async def create_template(
    request: CreateTemplateRequest,
    service: Annotated[ExportService, Depends(get_service)],
) -> ExportTemplate:
    """Create a new export template."""
    template = ExportTemplate(
        id="",  # Will be set by service
        name=request.name,
        description=request.description,
        export_type=request.export_type,
        format=request.format,
        filters=request.filters,
        related_data=request.related_data,
        is_default=request.is_default,
    )
    return await service.create_template(template)


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    service: Annotated[ExportService, Depends(get_service)],
    export_type: ExportType | None = None,
) -> TemplateListResponse:
    """List export templates."""
    templates = await service.list_templates(export_type=export_type)
    return TemplateListResponse(
        templates=templates,
        total=len(templates),
    )


@router.get("/templates/{template_id}", response_model=ExportTemplate)
async def get_template(
    template_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> ExportTemplate:
    """Get an export template by ID."""
    template = await service.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> dict[str, bool]:
    """Delete an export template."""
    success = await service.delete_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"deleted": True}


@router.post("/templates/{template_id}/export", response_model=ExportJobResponse)
async def export_from_template(
    template_id: str,
    service: Annotated[ExportService, Depends(get_service)],
    async_processing: bool = True,
) -> ExportJobResponse:
    """Create an export using a template."""
    template = await service.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    request = ExportRequest(
        export_type=template.export_type,
        format=template.format,
        columns=template.columns,
        filters=template.filters,
        related_data=template.related_data,
        pdf_options=template.pdf_options,
        csv_options=template.csv_options,
        json_options=template.json_options,
        markdown_options=template.markdown_options,
        template_id=template_id,
        async_processing=async_processing,
    )

    job = await service.create_export(request)
    return ExportJobResponse.from_job(job)


# Schedule routes
@router.post("/schedules", response_model=ScheduledExport)
async def create_schedule(
    request: CreateScheduleRequest,
    service: Annotated[ExportService, Depends(get_service)],
) -> ScheduledExport:
    """Create a scheduled export."""
    export_request = ExportRequest(
        export_type=request.request.export_type,
        format=request.request.format,
        filters=request.request.filters,
        related_data=request.request.related_data,
        async_processing=True,  # Schedules always async
    )

    schedule = ScheduledExport(
        id="",  # Will be set by service
        name=request.name,
        description=request.description,
        frequency=request.frequency,
        cron_expression=request.cron_expression,
        timezone=request.timezone,
        request=export_request,
        delivery_email=request.delivery_email,
        delivery_webhook=request.delivery_webhook,
    )

    return await service.create_schedule(schedule)


@router.get("/schedules", response_model=ScheduleListResponse)
async def list_schedules(
    service: Annotated[ExportService, Depends(get_service)],
    enabled: bool | None = None,
) -> ScheduleListResponse:
    """List scheduled exports."""
    schedules = await service.list_schedules(enabled=enabled)
    return ScheduleListResponse(
        schedules=schedules,
        total=len(schedules),
    )


@router.get("/schedules/{schedule_id}", response_model=ScheduledExport)
async def get_schedule(
    schedule_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> ScheduledExport:
    """Get a scheduled export by ID."""
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.patch("/schedules/{schedule_id}", response_model=ScheduledExport)
async def update_schedule(
    schedule_id: str,
    request: UpdateScheduleRequest,
    service: Annotated[ExportService, Depends(get_service)],
) -> ScheduledExport:
    """Update a scheduled export."""
    updates = request.model_dump(exclude_unset=True)
    schedule = await service.update_schedule(schedule_id, updates)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> dict[str, bool]:
    """Delete a scheduled export."""
    success = await service.delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"deleted": True}


@router.post("/schedules/{schedule_id}/run", response_model=ExportJobResponse)
async def run_schedule_now(
    schedule_id: str,
    service: Annotated[ExportService, Depends(get_service)],
) -> ExportJobResponse:
    """Run a scheduled export immediately."""
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    job = await service.create_export(schedule.request)
    return ExportJobResponse.from_job(job)


# Statistics route
@router.get("/stats", response_model=ExportStats)
async def get_export_stats(
    service: Annotated[ExportService, Depends(get_service)],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> ExportStats:
    """Get export statistics."""
    return await service.get_stats(start_date=start_date, end_date=end_date)
