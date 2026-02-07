"""Tests for export system (PDF, CSV, JSON)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.export.models import (
    DEFAULT_INCIDENT_COLUMNS,
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
    ExportTemplate,
    ExportType,
    JSONOptions,
    MarkdownOptions,
    PDFOptions,
    RelatedDataConfig,
    ScheduledExport,
)
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_export_request() -> ExportRequest:
    """Create a sample export request."""
    return ExportRequest(
        export_type=ExportType.INCIDENTS,
        format=ExportFormat.CSV,
        filters=ExportFilter(
            date_range=DateRangeFilter(
                start_date=datetime.utcnow() - timedelta(days=30),
                end_date=datetime.utcnow(),
            ),
            severities=["P1", "P2"],
        ),
        columns=DEFAULT_INCIDENT_COLUMNS.copy(),
        async_processing=True,
    )


class TestDateRangeFilter:
    """Tests for DateRangeFilter model."""

    def test_filter_creation(self):
        """Test creating a date range filter."""
        now = datetime.utcnow()
        start = now - timedelta(days=7)
        dr = DateRangeFilter(start_date=start, end_date=now)
        assert dr.start_date == start
        assert dr.end_date == now

    def test_contains_within_range(self):
        """Test date within range detection."""
        now = datetime.utcnow()
        dr = DateRangeFilter(
            start_date=now - timedelta(days=7),
            end_date=now,
        )
        # Date within range
        assert dr.contains(now - timedelta(days=3))
        # Date at boundaries
        assert dr.contains(dr.start_date)
        assert dr.contains(dr.end_date)

    def test_contains_outside_range(self):
        """Test date outside range detection."""
        now = datetime.utcnow()
        dr = DateRangeFilter(
            start_date=now - timedelta(days=7),
            end_date=now,
        )
        assert not dr.contains(now - timedelta(days=10))
        assert not dr.contains(now + timedelta(days=1))


class TestExportFilter:
    """Tests for ExportFilter model."""

    def test_default_filter(self):
        """Test default export filter."""
        f = ExportFilter()
        assert f.include_resolved
        assert f.include_active
        assert len(f.services) == 0

    def test_filter_with_values(self):
        """Test export filter with values."""
        f = ExportFilter(
            services=["api", "web"],
            severities=["P1", "P2"],
            statuses=["resolved"],
            include_active=False,
        )
        assert len(f.services) == 2
        assert len(f.severities) == 2
        assert not f.include_active


class TestColumnConfig:
    """Tests for ColumnConfig model."""

    def test_column_creation(self):
        """Test creating a column config."""
        col = ColumnConfig(
            field="incident_id",
            header="Incident ID",
            format="string",
        )
        assert col.field == "incident_id"
        assert col.include

    def test_column_excluded(self):
        """Test excluding a column."""
        col = ColumnConfig(
            field="internal_notes",
            include=False,
        )
        assert not col.include


class TestRelatedDataConfig:
    """Tests for RelatedDataConfig model."""

    def test_default_config(self):
        """Test default related data config."""
        config = RelatedDataConfig()
        assert config.include_timeline
        assert config.include_comments
        assert config.include_action_items
        assert not config.include_attachments  # Attachments off by default

    def test_custom_limits(self):
        """Test custom limits for related data."""
        config = RelatedDataConfig(
            max_timeline_events=50,
            max_comments=20,
        )
        assert config.max_timeline_events == 50
        assert config.max_comments == 20


class TestPDFOptions:
    """Tests for PDF export options."""

    def test_default_pdf_options(self):
        """Test default PDF options."""
        opts = PDFOptions()
        assert opts.page_size == "A4"
        assert opts.orientation == "portrait"
        assert opts.include_cover_page
        assert opts.include_toc

    def test_custom_pdf_options(self):
        """Test custom PDF options."""
        opts = PDFOptions(
            page_size="Letter",
            orientation="landscape",
            include_cover_page=False,
            logo_url="https://example.com/logo.png",
        )
        assert opts.page_size == "Letter"
        assert opts.orientation == "landscape"
        assert opts.logo_url == "https://example.com/logo.png"


class TestCSVOptions:
    """Tests for CSV export options."""

    def test_default_csv_options(self):
        """Test default CSV options."""
        opts = CSVOptions()
        assert opts.delimiter == ","
        assert opts.include_header
        assert opts.encoding == "utf-8"
        assert opts.escape_formulas

    def test_custom_delimiter(self):
        """Test custom CSV delimiter."""
        opts = CSVOptions(delimiter="\t")
        assert opts.delimiter == "\t"


class TestJSONOptions:
    """Tests for JSON export options."""

    def test_default_json_options(self):
        """Test default JSON options."""
        opts = JSONOptions()
        assert opts.indent == 2
        assert opts.date_format == "iso"
        assert not opts.flatten

    def test_flat_json_options(self):
        """Test flattened JSON options."""
        opts = JSONOptions(flatten=True, indent=None)
        assert opts.flatten
        assert opts.indent is None


class TestExportRequest:
    """Tests for ExportRequest model."""

    def test_request_creation(self, sample_export_request):
        """Test creating an export request."""
        assert sample_export_request.export_type == ExportType.INCIDENTS
        assert sample_export_request.format == ExportFormat.CSV
        assert sample_export_request.async_processing

    def test_request_with_pdf_options(self):
        """Test request with PDF-specific options."""
        request = ExportRequest(
            export_type=ExportType.POSTMORTEMS,
            format=ExportFormat.PDF,
            pdf_options=PDFOptions(include_cover_page=True),
        )
        assert request.pdf_options is not None
        assert request.pdf_options.include_cover_page


class TestExportJob:
    """Tests for ExportJob model."""

    def test_job_creation(self, sample_export_request):
        """Test creating an export job."""
        job = ExportJob(
            id="job-123",
            request=sample_export_request,
            created_by="user-123",
        )
        assert job.status == ExportJobStatus.PENDING
        assert job.progress_percent == 0
        assert job.retry_count == 0

    def test_job_progress(self, sample_export_request):
        """Test job progress tracking."""
        job = ExportJob(
            id="job-123",
            request=sample_export_request,
            status=ExportJobStatus.PROCESSING,
            progress_percent=50,
            records_processed=100,
            total_records=200,
            current_step="Processing incidents",
        )
        assert job.progress_percent == 50
        assert job.current_step == "Processing incidents"

    def test_completed_job(self, sample_export_request):
        """Test completed export job."""
        job = ExportJob(
            id="job-123",
            request=sample_export_request,
            status=ExportJobStatus.COMPLETED,
            progress_percent=100,
            file_path="/exports/job-123.csv",
            file_size_bytes=1024,
            download_url="https://storage.example.com/exports/job-123.csv",
        )
        assert job.status == ExportJobStatus.COMPLETED
        assert job.file_size_bytes == 1024


class TestExportResult:
    """Tests for ExportResult model."""

    def test_result_creation(self):
        """Test creating an export result."""
        result = ExportResult(
            job_id="job-123",
            status=ExportJobStatus.COMPLETED,
            format=ExportFormat.CSV,
            export_type=ExportType.INCIDENTS,
            file_name="incidents-export.csv",
            file_size_bytes=2048,
            download_url="https://storage.example.com/exports/incidents.csv",
            records_exported=150,
            created_at=datetime.utcnow() - timedelta(minutes=5),
            completed_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        assert result.records_exported == 150
        assert result.file_size_bytes == 2048


class TestExportTemplate:
    """Tests for ExportTemplate model."""

    def test_template_creation(self):
        """Test creating an export template."""
        template = ExportTemplate(
            id="template-1",
            name="Weekly Incident Report",
            export_type=ExportType.INCIDENTS,
            format=ExportFormat.PDF,
            columns=DEFAULT_INCIDENT_COLUMNS,
            pdf_options=PDFOptions(include_toc=True),
            is_default=True,
        )
        assert template.is_default
        assert template.format == ExportFormat.PDF


class TestScheduledExport:
    """Tests for ScheduledExport model."""

    def test_scheduled_export_creation(self, sample_export_request):
        """Test creating a scheduled export."""
        scheduled = ScheduledExport(
            id="sched-1",
            name="Daily Incidents Report",
            frequency=ExportScheduleFrequency.DAILY,
            request=sample_export_request,
            delivery_email=["team@example.com"],
            timezone="America/New_York",
        )
        assert scheduled.enabled
        assert scheduled.frequency == ExportScheduleFrequency.DAILY
        assert len(scheduled.delivery_email) == 1

    def test_scheduled_export_with_cron(self, sample_export_request):
        """Test scheduled export with custom cron expression."""
        scheduled = ScheduledExport(
            id="sched-2",
            name="Custom Schedule",
            frequency=ExportScheduleFrequency.CUSTOM,
            cron_expression="0 9 * * 1",  # Every Monday at 9 AM
            request=sample_export_request,
        )
        assert scheduled.cron_expression == "0 9 * * 1"


class TestExportAPI:
    """Tests for Export API endpoints."""

    def test_create_export_job(self, client):
        """Test POST /api/exports endpoint."""
        response = client.post(
            "/api/exports",
            json={
                "export_type": "incidents",
                "format": "csv",
                "filters": {
                    "severities": ["P1", "P2"],
                },
            },
        )
        assert response.status_code in (200, 201, 202)

    def test_get_export_job(self, client):
        """Test GET /api/exports/{job_id} endpoint."""
        response = client.get("/api/exports/job-123")
        assert response.status_code in (200, 404)

    def test_list_export_jobs(self, client):
        """Test GET /api/exports endpoint."""
        response = client.get("/api/exports")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_download_export(self, client):
        """Test GET /api/exports/{job_id}/download endpoint."""
        response = client.get("/api/exports/job-123/download")
        assert response.status_code in (200, 404)

    def test_create_template(self, client):
        """Test POST /api/exports/templates endpoint."""
        response = client.post(
            "/api/exports/templates",
            json={
                "id": "template-1",
                "name": "My Template",
                "export_type": "incidents",
                "format": "pdf",
            },
        )
        assert response.status_code in (200, 201)

    def test_list_templates(self, client):
        """Test GET /api/exports/templates endpoint."""
        response = client.get("/api/exports/templates")
        assert response.status_code == 200

    def test_create_scheduled_export(self, client):
        """Test POST /api/exports/scheduled endpoint."""
        response = client.post(
            "/api/exports/scheduled",
            json={
                "id": "sched-1",
                "name": "Weekly Report",
                "frequency": "weekly",
                "request": {
                    "export_type": "incidents",
                    "format": "pdf",
                },
                "delivery_email": ["team@example.com"],
            },
        )
        assert response.status_code in (200, 201)

    def test_export_incidents_csv(self, client):
        """Test quick export to CSV."""
        response = client.post(
            "/api/exports/quick",
            json={
                "export_type": "incidents",
                "format": "csv",
            },
        )
        assert response.status_code in (200, 202)

    def test_export_postmortems_pdf(self, client):
        """Test quick export postmortems to PDF."""
        response = client.post(
            "/api/exports/quick",
            json={
                "export_type": "postmortems",
                "format": "pdf",
                "pdf_options": {"include_cover_page": True},
            },
        )
        assert response.status_code in (200, 202)
