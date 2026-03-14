"""Export service for creating and managing export jobs."""

import asyncio
import hashlib
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .formatters import CSVFormatter, JSONFormatter, MarkdownFormatter, PDFFormatter
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
    ScheduledExport,
)


class ExportService:
    """Service for creating and managing exports."""

    def __init__(
        self,
        export_dir: str | None = None,
        base_url: str = "http://localhost:8000",
    ):
        if export_dir is None:
            export_dir = os.path.join(tempfile.gettempdir(), "exports")
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url

        # In-memory storage (replace with database in production)
        self._jobs: dict[str, ExportJob] = {}
        self._templates: dict[str, ExportTemplate] = {}
        self._schedules: dict[str, ScheduledExport] = {}
        self._stats: dict[str, ExportStats] = {}

    async def create_export(
        self,
        request: ExportRequest,
        user_id: str | None = None,
        organization_id: str | None = None,
    ) -> ExportJob:
        """Create a new export job."""
        job_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=request.expiry_hours)

        job = ExportJob(
            id=job_id,
            request=request,
            status=ExportJobStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            created_by=user_id,
            organization_id=organization_id,
        )

        self._jobs[job_id] = job

        if request.async_processing:
            # Start background processing
            asyncio.create_task(self._process_export(job_id))
        else:
            # Process synchronously
            await self._process_export(job_id)

        return job

    async def get_status(self, job_id: str) -> ExportJob | None:
        """Get the status of an export job."""
        job = self._jobs.get(job_id)
        if job and job.expires_at and datetime.now(UTC) > job.expires_at:
            job.status = ExportJobStatus.EXPIRED
        return job

    async def get_result(self, job_id: str) -> ExportResult | None:
        """Get the result of a completed export job."""
        job = await self.get_status(job_id)
        if not job or job.status != ExportJobStatus.COMPLETED:
            return None

        return ExportResult(
            job_id=job.id,
            status=job.status,
            format=job.request.format,
            export_type=job.request.export_type,
            file_name=job.file_name or "",
            file_size_bytes=job.file_size_bytes or 0,
            download_url=job.download_url,
            file_path=job.file_path,
            records_exported=job.records_processed,
            created_at=job.created_at,
            completed_at=job.completed_at or datetime.now(UTC),
            expires_at=job.expires_at or datetime.now(UTC),
            checksum=self._calculate_checksum(job.file_path) if job.file_path else None,
        )

    async def download(self, job_id: str) -> tuple[bytes, str, str] | None:
        """Download the exported file. Returns (content, filename, content_type)."""
        job = await self.get_status(job_id)
        if not job or job.status != ExportJobStatus.COMPLETED:
            return None

        if not job.file_path or not os.path.exists(job.file_path):
            return None

        with open(job.file_path, "rb") as f:
            content = f.read()

        content_type = self._get_content_type(job.request.format)
        filename = job.file_name or f"export_{job_id}.{job.request.format.value}"

        return content, filename, content_type

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or processing export job."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status in [ExportJobStatus.PENDING, ExportJobStatus.PROCESSING]:
            job.status = ExportJobStatus.FAILED
            job.error_message = "Cancelled by user"
            return True

        return False

    async def delete_job(self, job_id: str) -> bool:
        """Delete an export job and its file."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        # Delete file if exists
        if job.file_path and os.path.exists(job.file_path):
            os.remove(job.file_path)

        del self._jobs[job_id]
        return True

    async def list_jobs(
        self,
        user_id: str | None = None,
        organization_id: str | None = None,
        status: ExportJobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExportJob]:
        """List export jobs with optional filtering."""
        jobs = list(self._jobs.values())

        if user_id:
            jobs = [j for j in jobs if j.created_by == user_id]
        if organization_id:
            jobs = [j for j in jobs if j.organization_id == organization_id]
        if status:
            jobs = [j for j in jobs if j.status == status]

        # Sort by created_at desc
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return jobs[offset : offset + limit]

    # Template management
    async def create_template(
        self,
        template: ExportTemplate,
        user_id: str | None = None,
    ) -> ExportTemplate:
        """Create a new export template."""
        template.id = str(uuid.uuid4())
        template.created_at = datetime.now(UTC)
        template.created_by = user_id
        self._templates[template.id] = template
        return template

    async def get_template(self, template_id: str) -> ExportTemplate | None:
        """Get an export template by ID."""
        return self._templates.get(template_id)

    async def list_templates(
        self,
        organization_id: str | None = None,
        export_type: ExportType | None = None,
    ) -> list[ExportTemplate]:
        """List export templates."""
        templates = list(self._templates.values())

        if organization_id:
            templates = [
                t
                for t in templates
                if t.organization_id == organization_id or t.is_default
            ]
        if export_type:
            templates = [t for t in templates if t.export_type == export_type]

        return templates

    async def delete_template(self, template_id: str) -> bool:
        """Delete an export template."""
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

    # Scheduled exports
    async def create_schedule(
        self,
        schedule: ScheduledExport,
        user_id: str | None = None,
    ) -> ScheduledExport:
        """Create a scheduled export."""
        schedule.id = str(uuid.uuid4())
        schedule.created_at = datetime.now(UTC)
        schedule.updated_at = datetime.now(UTC)
        schedule.created_by = user_id
        schedule.next_run_at = self._calculate_next_run(schedule)
        self._schedules[schedule.id] = schedule
        return schedule

    async def get_schedule(self, schedule_id: str) -> ScheduledExport | None:
        """Get a scheduled export by ID."""
        return self._schedules.get(schedule_id)

    async def update_schedule(
        self,
        schedule_id: str,
        updates: dict[str, Any],
    ) -> ScheduledExport | None:
        """Update a scheduled export."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            return None

        for key, value in updates.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)

        schedule.updated_at = datetime.now(UTC)
        schedule.next_run_at = self._calculate_next_run(schedule)
        return schedule

    async def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a scheduled export."""
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]
            return True
        return False

    async def list_schedules(
        self,
        organization_id: str | None = None,
        enabled: bool | None = None,
    ) -> list[ScheduledExport]:
        """List scheduled exports."""
        schedules = list(self._schedules.values())

        if organization_id:
            schedules = [s for s in schedules if s.organization_id == organization_id]
        if enabled is not None:
            schedules = [s for s in schedules if s.enabled == enabled]

        return schedules

    async def run_scheduled_exports(self) -> list[str]:
        """Run all due scheduled exports. Returns list of created job IDs."""
        now = datetime.now(UTC)
        job_ids = []

        for schedule in self._schedules.values():
            if not schedule.enabled:
                continue
            if not schedule.next_run_at or schedule.next_run_at > now:
                continue

            # Create export job
            job = await self.create_export(
                request=schedule.request,
                organization_id=schedule.organization_id,
            )
            job_ids.append(job.id)

            # Update schedule
            schedule.last_run_at = now
            schedule.last_job_id = job.id
            schedule.next_run_at = self._calculate_next_run(schedule)

        return job_ids

    # Statistics
    async def get_stats(
        self,
        organization_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ExportStats:
        """Get export statistics."""
        jobs = list(self._jobs.values())

        if organization_id:
            jobs = [j for j in jobs if j.organization_id == organization_id]
        if start_date:
            jobs = [j for j in jobs if j.created_at >= start_date]
        if end_date:
            jobs = [j for j in jobs if j.created_at <= end_date]

        completed_jobs = [j for j in jobs if j.status == ExportJobStatus.COMPLETED]

        # Calculate statistics
        exports_by_format: dict[str, int] = {}
        exports_by_type: dict[str, int] = {}
        total_records = 0
        total_size = 0
        total_time = 0.0
        time_count = 0

        for job in completed_jobs:
            fmt = job.request.format.value
            exports_by_format[fmt] = exports_by_format.get(fmt, 0) + 1

            exp_type = job.request.export_type.value
            exports_by_type[exp_type] = exports_by_type.get(exp_type, 0) + 1

            total_records += job.records_processed
            total_size += job.file_size_bytes or 0

            if job.started_at and job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                total_time += duration
                time_count += 1

        avg_time = total_time / time_count if time_count > 0 else None

        return ExportStats(
            total_exports=len(completed_jobs),
            exports_by_format=exports_by_format,
            exports_by_type=exports_by_type,
            average_processing_time_seconds=avg_time,
            total_records_exported=total_records,
            total_file_size_bytes=total_size,
            period_start=start_date,
            period_end=end_date,
        )

    # Internal methods
    async def _process_export(self, job_id: str) -> None:
        """Process an export job."""
        job = self._jobs.get(job_id)
        if not job:
            return

        try:
            job.status = ExportJobStatus.PROCESSING
            job.started_at = datetime.now(UTC)
            job.current_step = "Fetching data"

            # Fetch data based on export type
            data = await self._fetch_data(job.request)
            job.total_records = len(data) if isinstance(data, list) else 1
            job.current_step = "Formatting data"
            job.progress_percent = 30

            # Format data
            content = await self._format_data(job.request, data)
            job.current_step = "Writing file"
            job.progress_percent = 70

            # Write file
            file_ext = self._get_file_extension(job.request.format)
            file_name = (
                f"export_{job.request.export_type.value}_{job.id[:8]}.{file_ext}"
            )
            file_path = self.export_dir / file_name

            with open(file_path, "wb") as f:
                f.write(content)

            # Update job
            job.file_path = str(file_path)
            job.file_name = file_name
            job.file_size_bytes = len(content)
            job.download_url = f"{self.base_url}/api/v1/export/{job.id}/download"
            job.records_processed = job.total_records or 0
            job.progress_percent = 100
            job.status = ExportJobStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            job.current_step = None

            # Send notification if requested
            if job.request.notify_on_completion:
                await self._send_notification(job)

        except Exception as e:
            job.status = ExportJobStatus.FAILED
            job.error_message = str(e)
            job.error_details = {"type": type(e).__name__}
            job.completed_at = datetime.now(UTC)

            # Retry if applicable
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = ExportJobStatus.PENDING
                await asyncio.sleep(5 * job.retry_count)  # Exponential backoff
                await self._process_export(job_id)

    async def _fetch_data(self, request: ExportRequest) -> list[dict[str, Any]] | dict:
        """Fetch data based on export type and filters."""
        # This would integrate with actual data services
        # For now, return mock data
        filters = request.filters

        if request.export_type == ExportType.INCIDENTS:
            return await self._fetch_incidents(filters)
        elif request.export_type == ExportType.POSTMORTEMS:
            return await self._fetch_postmortems(filters)
        elif request.export_type == ExportType.ANALYTICS:
            return await self._fetch_analytics(filters)
        elif request.export_type == ExportType.REPORTS:
            return await self._fetch_reports(filters)
        elif request.export_type == ExportType.ACTION_ITEMS:
            return await self._fetch_action_items(filters)
        else:
            return []

    async def _fetch_incidents(self, filters: ExportFilter) -> list[dict[str, Any]]:
        """Fetch incidents from the data store."""
        # Mock implementation - integrate with actual incident service
        return [
            {
                "incident_id": "INC-001",
                "title": "Database connection timeout",
                "severity": "high",
                "service_name": "api-gateway",
                "status": "resolved",
                "triggered_at": datetime.now(UTC) - timedelta(days=1),
                "resolved_at": datetime.now(UTC) - timedelta(hours=23),
                "timeline": [
                    {
                        "timestamp": datetime.now(UTC) - timedelta(days=1),
                        "event_type": "alert_triggered",
                        "title": "Alert triggered",
                    },
                ],
                "action_items": [],
            }
        ]

    async def _fetch_postmortems(self, filters: ExportFilter) -> list[dict[str, Any]]:
        """Fetch postmortems from the data store."""
        return [
            {
                "id": "PM-001",
                "incident_id": "INC-001",
                "title": "Database Connection Timeout Postmortem",
                "service_name": "api-gateway",
                "severity": "high",
                "status": "published",
                "executive_summary": "Database connection pool exhausted.",
                "incident_duration_minutes": 60,
                "created_at": datetime.now(UTC),
                "root_cause": {
                    "primary_cause": "Connection pool configuration",
                    "contributing_factors": ["High traffic", "Missing monitoring"],
                },
                "impact": {
                    "severity": "high",
                    "users_affected": 1000,
                    "sla_breach": False,
                },
                "action_items": [],
                "lessons_learned": ["Add connection pool monitoring"],
            }
        ]

    async def _fetch_analytics(self, filters: ExportFilter) -> dict[str, Any]:
        """Fetch analytics data."""
        return {
            "mttr_stats": {
                "period": "7d",
                "mean_mttr_minutes": 45.5,
                "median_mttr_minutes": 30.0,
                "p90_mttr_minutes": 120.0,
                "incidents_count": 12,
                "resolved_count": 10,
            },
            "severity_breakdown": {
                "critical": 2,
                "high": 5,
                "medium": 3,
                "low": 2,
            },
            "service_breakdown": {
                "api-gateway": 4,
                "database": 3,
                "auth-service": 2,
                "frontend": 3,
            },
        }

    async def _fetch_reports(self, filters: ExportFilter) -> list[dict[str, Any]]:
        """Fetch reports from the data store."""
        return []

    async def _fetch_action_items(self, filters: ExportFilter) -> list[dict[str, Any]]:
        """Fetch action items from the data store."""
        return []

    async def _format_data(
        self, request: ExportRequest, data: list[dict[str, Any]] | dict
    ) -> bytes:
        """Format data according to the requested format."""
        if request.format == ExportFormat.PDF:
            formatter = PDFFormatter(
                export_type=request.export_type,
                columns=request.columns,
                options=request.pdf_options,
                related_data=request.related_data,
            )
        elif request.format == ExportFormat.CSV:
            formatter = CSVFormatter(
                export_type=request.export_type,
                columns=request.columns,
                options=request.csv_options,
                related_data=request.related_data,
            )
        elif request.format == ExportFormat.JSON:
            formatter = JSONFormatter(
                export_type=request.export_type,
                columns=request.columns,
                options=request.json_options,
                related_data=request.related_data,
            )
        elif request.format == ExportFormat.MARKDOWN:
            formatter = MarkdownFormatter(
                export_type=request.export_type,
                columns=request.columns,
                options=request.markdown_options,
                related_data=request.related_data,
            )
        else:
            raise ValueError(f"Unsupported format: {request.format}")

        return formatter.format_bytes(data)

    async def _send_notification(self, job: ExportJob) -> None:
        """Send completion notification."""
        # Email notification
        if job.request.notification_email:
            # Integrate with email service
            pass

        # Webhook notification
        if job.request.notification_webhook:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                try:
                    await session.post(
                        job.request.notification_webhook,
                        json={
                            "job_id": job.id,
                            "status": job.status.value,
                            "download_url": job.download_url,
                            "records_exported": job.records_processed,
                        },
                    )
                except Exception:
                    pass  # Log but don't fail

    def _calculate_next_run(self, schedule: ScheduledExport) -> datetime:
        """Calculate the next run time for a scheduled export."""
        now = datetime.now(UTC)

        if schedule.frequency == ExportScheduleFrequency.DAILY:
            return now + timedelta(days=1)
        elif schedule.frequency == ExportScheduleFrequency.WEEKLY:
            return now + timedelta(weeks=1)
        elif schedule.frequency == ExportScheduleFrequency.MONTHLY:
            return now + timedelta(days=30)
        elif schedule.frequency == ExportScheduleFrequency.CUSTOM:
            # Parse cron expression (simplified)
            if schedule.cron_expression:
                # Would use croniter in production
                return now + timedelta(hours=1)
            return now + timedelta(days=1)

        return now + timedelta(days=1)

    def _get_file_extension(self, format: ExportFormat) -> str:
        """Get file extension for format."""
        extensions = {
            ExportFormat.PDF: "pdf",
            ExportFormat.CSV: "csv",
            ExportFormat.JSON: "json",
            ExportFormat.MARKDOWN: "md",
        }
        return extensions.get(format, "txt")

    def _get_content_type(self, format: ExportFormat) -> str:
        """Get content type for format."""
        content_types = {
            ExportFormat.PDF: "application/pdf",
            ExportFormat.CSV: "text/csv",
            ExportFormat.JSON: "application/json",
            ExportFormat.MARKDOWN: "text/markdown",
        }
        return content_types.get(format, "application/octet-stream")

    def _calculate_checksum(self, file_path: str | None) -> str | None:
        """Calculate SHA256 checksum of file."""
        if not file_path or not os.path.exists(file_path):
            return None

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()


# Global service instance
_export_service: ExportService | None = None


def get_export_service() -> ExportService:
    """Get or create the global export service instance."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service
