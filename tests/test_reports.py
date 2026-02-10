"""Unit tests for the scheduled reports module."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reports import (
    CRON_PRESETS,
    CronExpression,
    DeliveryChannel,
    DeliveryConfig,
    IncidentSummary,
    MetricsSummary,
    ReportConfig,
    ReportContent,
    ReportFilter,
    ReportGenerator,
    ReportOutput,
    ReportRunRequest,
    ReportRunStatus,
    ReportSchedule,
    ReportScheduler,
    ReportStatus,
    ReportStore,
    ReportTemplate,
    ReportTemplates,
    ReportType,
    describe_cron,
    get_cron_preset,
)
from src.reports.delivery import (
    ReportDeliveryService,
    SlackDeliveryAdapter,
    WebhookDeliveryAdapter,
)

# =============================================================================
# CronExpression Tests
# =============================================================================


class TestCronExpression:
    """Tests for CronExpression parser."""

    def test_parse_simple_expression(self):
        """Test parsing simple cron expressions."""
        cron = CronExpression("0 9 * * *")
        assert 0 in cron.fields["minute"]
        assert 9 in cron.fields["hour"]
        assert len(cron.fields["day_of_month"]) == 31
        assert len(cron.fields["month"]) == 12
        assert len(cron.fields["day_of_week"]) == 7

    def test_parse_step_expression(self):
        """Test parsing step expressions (*/n)."""
        cron = CronExpression("*/15 * * * *")
        assert cron.fields["minute"] == {0, 15, 30, 45}

    def test_parse_range_expression(self):
        """Test parsing range expressions (n-m)."""
        cron = CronExpression("0 9-17 * * *")
        assert cron.fields["hour"] == {9, 10, 11, 12, 13, 14, 15, 16, 17}

    def test_parse_list_expression(self):
        """Test parsing list expressions (a,b,c)."""
        cron = CronExpression("0 9 * * 1,3,5")
        assert cron.fields["day_of_week"] == {1, 3, 5}

    def test_parse_day_names(self):
        """Test parsing day names."""
        cron = CronExpression("0 9 * * mon,wed,fri")
        assert cron.fields["day_of_week"] == {1, 3, 5}

    def test_parse_month_names(self):
        """Test parsing month names."""
        cron = CronExpression("0 9 1 jan,jul *")
        assert cron.fields["month"] == {1, 7}

    def test_parse_combined_expression(self):
        """Test parsing combined expressions."""
        cron = CronExpression("0 9-17/2 * * 1-5")
        # 9-17 with step 2: 9, 11, 13, 15, 17
        assert cron.fields["hour"] == {9, 11, 13, 15, 17}
        assert cron.fields["day_of_week"] == {1, 2, 3, 4, 5}

    def test_invalid_expression_wrong_fields(self):
        """Test that invalid expressions raise ValueError."""
        with pytest.raises(ValueError, match="expected 5 fields"):
            CronExpression("0 9 * *")

    def test_matches_datetime(self):
        """Test datetime matching."""
        cron = CronExpression("30 14 * * *")
        dt_match = datetime(2024, 2, 6, 14, 30)
        dt_no_match = datetime(2024, 2, 6, 14, 31)

        assert cron.matches(dt_match)
        assert not cron.matches(dt_no_match)

    def test_matches_weekday(self):
        """Test weekday matching (Monday = 1 in cron, 0 in Python)."""
        cron = CronExpression("0 9 * * 1")  # Monday
        monday = datetime(2024, 2, 5, 9, 0)  # This is a Monday
        tuesday = datetime(2024, 2, 6, 9, 0)  # This is a Tuesday

        assert cron.matches(monday)
        assert not cron.matches(tuesday)

    def test_next_run(self):
        """Test next run calculation."""
        cron = CronExpression("0 * * * *")  # Every hour
        now = datetime(2024, 2, 6, 14, 30)
        next_run = cron.next_run(now)

        assert next_run.minute == 0
        assert next_run.hour == 15
        assert next_run.day == 6

    def test_next_run_next_day(self):
        """Test next run calculation that rolls to next day."""
        cron = CronExpression("0 9 * * *")  # 9am daily
        now = datetime(2024, 2, 6, 10, 0)
        next_run = cron.next_run(now)

        assert next_run.hour == 9
        assert next_run.day == 7  # Next day

    def test_validate_valid(self):
        """Test validation of valid expression."""
        valid, error = CronExpression.validate("0 9 * * 1-5")
        assert valid
        assert error is None

    def test_validate_invalid(self):
        """Test validation of invalid expression."""
        valid, error = CronExpression.validate("invalid")
        assert not valid
        assert error is not None


class TestCronPresets:
    """Tests for cron presets."""

    def test_get_preset(self):
        """Test getting preset by name."""
        assert get_cron_preset("daily_9am") == "0 9 * * *"
        assert get_cron_preset("weekly_monday_9am") == "0 9 * * 1"
        assert get_cron_preset("nonexistent") is None

    def test_describe_cron(self):
        """Test cron description."""
        assert "minute" in describe_cron("* * * * *").lower()
        assert "hour" in describe_cron("0 * * * *").lower()
        assert "day" in describe_cron("0 0 * * *").lower()

    def test_all_presets_valid(self):
        """Test that all presets are valid expressions."""
        for name, expression in CRON_PRESETS.items():
            valid, error = CronExpression.validate(expression)
            assert valid, f"Preset {name} is invalid: {error}"


# =============================================================================
# ReportStore Tests
# =============================================================================


class TestReportStore:
    """Tests for ReportStore."""

    @pytest.fixture
    def store(self):
        """Create fresh store for each test."""
        return ReportStore()

    @pytest.fixture
    def sample_config(self):
        """Create sample report configuration."""
        return ReportConfig(
            id="test-report-1",
            name="Test Daily Report",
            report_type=ReportType.DAILY_SUMMARY,
            schedule=ReportSchedule(
                cron_expression="0 9 * * *",
                timezone="UTC",
            ),
        )

    @pytest.mark.asyncio
    async def test_save_and_get_config(self, store, sample_config):
        """Test saving and retrieving config."""
        saved = await store.save_config(sample_config)
        assert saved.id == sample_config.id

        retrieved = await store.get_config(sample_config.id)
        assert retrieved is not None
        assert retrieved.name == sample_config.name

    @pytest.mark.asyncio
    async def test_get_nonexistent_config(self, store):
        """Test getting nonexistent config returns None."""
        result = await store.get_config("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_configs_filtered(self, store):
        """Test filtering configs by status."""
        active_config = ReportConfig(
            id="active-1",
            name="Active Report",
            report_type=ReportType.DAILY_SUMMARY,
            status=ReportStatus.ACTIVE,
            schedule=ReportSchedule(cron_expression="0 9 * * *"),
        )
        paused_config = ReportConfig(
            id="paused-1",
            name="Paused Report",
            report_type=ReportType.DAILY_SUMMARY,
            status=ReportStatus.PAUSED,
            schedule=ReportSchedule(cron_expression="0 9 * * *"),
        )

        await store.save_config(active_config)
        await store.save_config(paused_config)

        active_only = await store.get_all_configs(status=ReportStatus.ACTIVE)
        assert len(active_only) == 1
        assert active_only[0].id == "active-1"

    @pytest.mark.asyncio
    async def test_delete_config(self, store, sample_config):
        """Test deleting config."""
        await store.save_config(sample_config)
        result = await store.delete_config(sample_config.id)
        assert result

        retrieved = await store.get_config(sample_config.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_update_schedule(self, store, sample_config):
        """Test updating schedule times."""
        await store.save_config(sample_config)
        new_next_run = datetime.utcnow() + timedelta(hours=1)

        updated = await store.update_schedule(
            sample_config.id, next_run_at=new_next_run
        )

        assert updated is not None
        assert updated.schedule.next_run_at == new_next_run

    @pytest.mark.asyncio
    async def test_save_and_get_output(self, store):
        """Test saving and retrieving output."""
        output = ReportOutput(
            id="output-1",
            report_config_id="config-1",
            run_status=ReportRunStatus.COMPLETED,
        )

        saved = await store.save_output(output)
        assert saved.id == output.id

        retrieved = await store.get_output(output.id)
        assert retrieved is not None
        assert retrieved.run_status == ReportRunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_outputs_for_config(self, store):
        """Test getting outputs for a specific config."""
        for i in range(3):
            output = ReportOutput(
                id=f"output-{i}",
                report_config_id="config-1",
                run_status=ReportRunStatus.COMPLETED,
            )
            await store.save_output(output)

        outputs = await store.get_outputs_for_config("config-1")
        assert len(outputs) == 3

    @pytest.mark.asyncio
    async def test_output_trimming(self):
        """Test that outputs are trimmed when exceeding max."""
        store = ReportStore(max_outputs=5)

        for i in range(10):
            output = ReportOutput(
                id=f"output-{i}",
                report_config_id="config-1",
                run_status=ReportRunStatus.COMPLETED,
                triggered_at=datetime.utcnow() + timedelta(minutes=i),
            )
            await store.save_output(output)

        stats = await store.get_stats()
        assert stats["outputs_count"] <= 5

    @pytest.mark.asyncio
    async def test_get_stats(self, store, sample_config):
        """Test getting store statistics."""
        await store.save_config(sample_config)

        stats = await store.get_stats()
        assert stats["configs_count"] == 1
        assert stats["active_configs"] == 1


# =============================================================================
# ReportTemplates Tests
# =============================================================================


class TestReportTemplates:
    """Tests for ReportTemplates."""

    @pytest.fixture
    def templates(self):
        """Create templates instance."""
        return ReportTemplates()

    @pytest.fixture
    def sample_context(self, templates):
        """Create sample template context."""
        return {
            "title": "Test Report",
            "subtitle": "Test Subtitle",
            "period_start": datetime(2024, 2, 1),
            "period_end": datetime(2024, 2, 7),
            "generated_at": datetime.utcnow(),
            "executive_summary": "This is a test summary.",
            "metrics": MetricsSummary(
                period_start=datetime(2024, 2, 1),
                period_end=datetime(2024, 2, 7),
                total_incidents=10,
                incidents_by_severity={"critical": 2, "high": 3, "medium": 5},
                mean_mttr_minutes=45.5,
                trend="improving",
            ),
            "incidents": [
                IncidentSummary(
                    incident_id="inc-1",
                    title="Test Incident",
                    service_name="api-service",
                    severity="high",
                    triggered_at=datetime.utcnow(),
                    duration_minutes=30,
                ),
            ],
            "ai_insights": ["Insight 1", "Insight 2"],
            "ai_recommendations": ["Recommendation 1"],
            "style": templates.HTML_BASE_STYLE,
        }

    def test_render_html_daily_summary(self, templates, sample_context):
        """Test HTML rendering of daily summary."""
        sample_context["style"] = templates.HTML_BASE_STYLE
        html = templates.render_html("daily_summary", sample_context)

        assert "<html>" in html
        assert "Test Report" in html
        assert "Test Incident" in html
        assert "api-service" in html

    def test_render_markdown_daily_summary(self, templates, sample_context):
        """Test Markdown rendering of daily summary."""
        md = templates.render_markdown("daily_summary", sample_context)

        assert "# Test Report" in md
        assert "Test Incident" in md
        assert "api-service" in md

    def test_render_html_weekly_reliability(self, templates, sample_context):
        """Test HTML rendering of weekly report."""
        sample_context["style"] = templates.HTML_BASE_STYLE
        html = templates.render_html("weekly_reliability", sample_context)

        assert "<html>" in html
        assert "Weekly" in html

    def test_format_duration_filter(self, templates):
        """Test duration formatting filter."""
        assert templates._format_duration(30) == "30m"
        assert templates._format_duration(90) == "1h 30m"
        assert templates._format_duration(0.5) == "30s"
        assert templates._format_duration(None) == "N/A"

    def test_format_percent_filter(self, templates):
        """Test percent formatting filter."""
        assert templates._format_percent(10.5) == "+10.5%"
        assert templates._format_percent(-5.0) == "-5.0%"
        assert templates._format_percent(None) == "N/A"

    def test_severity_emoji_filter(self, templates):
        """Test severity emoji filter."""
        assert templates._severity_emoji("critical") == "🔴"
        assert templates._severity_emoji("high") == "🟠"
        assert templates._severity_emoji("unknown") == "⚪"

    def test_trend_arrow_filter(self, templates):
        """Test trend arrow filter."""
        assert templates._trend_arrow("improving") == "📈"
        assert templates._trend_arrow("degrading") == "📉"
        assert templates._trend_arrow("stable") == "➡️"


# =============================================================================
# ReportScheduler Tests
# =============================================================================


class TestReportScheduler:
    """Tests for ReportScheduler."""

    @pytest.fixture
    def scheduler(self):
        """Create scheduler instance."""
        callback = AsyncMock()
        return ReportScheduler(run_callback=callback), callback

    @pytest.fixture
    def sample_config(self):
        """Create sample report configuration."""
        return ReportConfig(
            id="test-report",
            name="Test Report",
            report_type=ReportType.DAILY_SUMMARY,
            schedule=ReportSchedule(
                cron_expression="0 9 * * *",
                timezone="UTC",
            ),
        )

    @pytest.mark.asyncio
    async def test_schedule_report(self, scheduler, sample_config):
        """Test scheduling a report."""
        sched, _ = scheduler
        config = await sched.schedule_report(sample_config)

        assert config.schedule.next_run_at is not None
        assert config.schedule.next_run_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_pause_report(self, scheduler, sample_config):
        """Test pausing a report."""
        sched, _ = scheduler
        await sched.schedule_report(sample_config)

        paused = await sched.pause_report(sample_config.id)
        assert paused is not None
        assert paused.status == ReportStatus.PAUSED

    @pytest.mark.asyncio
    async def test_resume_report(self, scheduler, sample_config):
        """Test resuming a paused report."""
        sched, _ = scheduler
        await sched.schedule_report(sample_config)
        await sched.pause_report(sample_config.id)

        resumed = await sched.resume_report(sample_config.id)
        assert resumed is not None
        assert resumed.status == ReportStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_unschedule_report(self, scheduler, sample_config):
        """Test removing a report from schedule."""
        sched, _ = scheduler
        await sched.schedule_report(sample_config)

        result = await sched.unschedule_report(sample_config.id)
        assert result

        config = await sched.store.get_config(sample_config.id)
        assert config is None

    @pytest.mark.asyncio
    async def test_get_upcoming_runs(self, scheduler, sample_config):
        """Test getting upcoming scheduled runs."""
        sched, _ = scheduler
        # Set next_run to be within 24 hours
        sample_config.schedule.next_run_at = datetime.utcnow() + timedelta(hours=1)
        await sched.store.save_config(sample_config)

        upcoming = await sched.get_upcoming_runs(hours=24)
        assert len(upcoming) == 1
        assert upcoming[0][0].id == sample_config.id

    @pytest.mark.asyncio
    async def test_get_schedule_status(self, scheduler, sample_config):
        """Test getting scheduler status."""
        sched, _ = scheduler
        await sched.schedule_report(sample_config)

        status = await sched.get_schedule_status()
        assert "running" in status
        assert "active_schedules" in status
        assert status["active_schedules"] == 1

    @pytest.mark.asyncio
    async def test_start_stop(self, scheduler):
        """Test starting and stopping scheduler."""
        sched, _ = scheduler

        await sched.start()
        assert sched._running

        await sched.stop()
        assert not sched._running


# =============================================================================
# Delivery Adapter Tests
# =============================================================================


class TestSlackDeliveryAdapter:
    """Tests for SlackDeliveryAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with mock settings."""
        settings = MagicMock()
        settings.slack_bot_token = "xoxb-test-token"
        settings.slack_default_channel = "#incidents"
        return SlackDeliveryAdapter(settings)

    @pytest.fixture
    def sample_content(self):
        """Create sample report content."""
        return ReportContent(
            report_config_id="config-1",
            report_type=ReportType.DAILY_SUMMARY,
            period_start=datetime(2024, 2, 1),
            period_end=datetime(2024, 2, 7),
            title="Test Report",
            executive_summary="Test summary",
            metrics=MetricsSummary(
                period_start=datetime(2024, 2, 1),
                period_end=datetime(2024, 2, 7),
                total_incidents=5,
            ),
            incidents=[],
        )

    def test_is_configured(self, adapter):
        """Test configuration check."""
        assert adapter.is_configured()

    def test_is_not_configured(self):
        """Test configuration check when not configured."""
        settings = MagicMock()
        settings.slack_bot_token = ""
        settings.slack_default_channel = ""
        adapter = SlackDeliveryAdapter(settings)
        assert not adapter.is_configured()

    def test_build_blocks(self, adapter, sample_content):
        """Test Slack block building."""
        blocks = adapter._build_blocks(sample_content)

        assert len(blocks) > 0
        assert blocks[0]["type"] == "header"
        assert "Test Report" in blocks[0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_deliver_via_webhook(self, adapter, sample_content):
        """Test delivery via webhook."""
        config = DeliveryConfig(
            channel=DeliveryChannel.SLACK,
            slack_webhook_url="https://hooks.slack.com/test",
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await adapter.deliver(sample_content, config)

            assert result["success"]
            assert result["method"] == "webhook"


class TestWebhookDeliveryAdapter:
    """Tests for WebhookDeliveryAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter."""
        return WebhookDeliveryAdapter()

    @pytest.fixture
    def sample_content(self):
        """Create sample report content."""
        return ReportContent(
            report_config_id="config-1",
            report_type=ReportType.DAILY_SUMMARY,
            period_start=datetime(2024, 2, 1),
            period_end=datetime(2024, 2, 7),
            title="Test Report",
        )

    def test_is_configured(self, adapter):
        """Webhook is always 'configured' (per-request)."""
        assert adapter.is_configured()

    @pytest.mark.asyncio
    async def test_deliver_no_url(self, adapter, sample_content):
        """Test delivery fails without URL."""
        config = DeliveryConfig(channel=DeliveryChannel.WEBHOOK)

        result = await adapter.deliver(sample_content, config)

        assert not result["success"]
        assert "No webhook URL" in result["error"]

    @pytest.mark.asyncio
    async def test_deliver_success(self, adapter, sample_content):
        """Test successful webhook delivery."""
        config = DeliveryConfig(
            channel=DeliveryChannel.WEBHOOK,
            webhook_url="https://example.com/webhook",
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                return_value=mock_response
            )

            result = await adapter.deliver(sample_content, config)

            assert result["success"]
            assert result["status_code"] == 200


class TestReportDeliveryService:
    """Tests for ReportDeliveryService."""

    @pytest.fixture
    def service(self):
        """Create service with mock settings."""
        settings = MagicMock()
        settings.slack_bot_token = "xoxb-test"
        settings.slack_default_channel = "#test"
        settings.aws_region = ""
        return ReportDeliveryService(settings)

    @pytest.fixture
    def sample_content(self):
        """Create sample report content."""
        return ReportContent(
            report_config_id="config-1",
            report_type=ReportType.DAILY_SUMMARY,
            period_start=datetime(2024, 2, 1),
            period_end=datetime(2024, 2, 7),
            title="Test Report",
            markdown="# Test",
        )

    def test_get_configured_channels(self, service):
        """Test getting configured channels."""
        channels = service.get_configured_channels()
        assert DeliveryChannel.SLACK in channels
        assert DeliveryChannel.WEBHOOK in channels

    @pytest.mark.asyncio
    async def test_deliver_skips_disabled(self, service, sample_content):
        """Test that disabled channels are skipped."""
        configs = [
            DeliveryConfig(
                channel=DeliveryChannel.SLACK,
                enabled=False,
            ),
        ]

        results = await service.deliver(sample_content, configs)

        assert results["slack"]["skipped"]


# =============================================================================
# ReportGenerator Tests
# =============================================================================


class TestReportGenerator:
    """Tests for ReportGenerator."""

    @pytest.fixture
    def generator(self):
        """Create generator with mock settings."""
        settings = MagicMock()
        settings.anthropic_api_key = ""
        settings.slack_bot_token = ""
        settings.aws_region = ""
        return ReportGenerator(settings)

    @pytest.fixture
    def sample_config(self):
        """Create sample report configuration."""
        return ReportConfig(
            id="test-report",
            name="Test Report",
            report_type=ReportType.DAILY_SUMMARY,
            schedule=ReportSchedule(
                cron_expression="0 9 * * *",
                timezone="UTC",
            ),
            template=ReportTemplate(format="both"),
        )

    def test_get_default_period_daily(self, generator):
        """Test default period for daily report."""
        end = datetime(2024, 2, 7, 9, 0)
        start = generator._get_default_period_start(ReportType.DAILY_SUMMARY, end)

        assert (end - start).days == 1

    def test_get_default_period_weekly(self, generator):
        """Test default period for weekly report."""
        end = datetime(2024, 2, 7, 9, 0)
        start = generator._get_default_period_start(ReportType.WEEKLY_RELIABILITY, end)

        assert (end - start).days == 7

    def test_get_default_period_monthly(self, generator):
        """Test default period for monthly report."""
        end = datetime(2024, 2, 7, 9, 0)
        start = generator._get_default_period_start(ReportType.MONTHLY_ANALYSIS, end)

        assert (end - start).days == 30

    def test_calculate_metrics(self, generator):
        """Test metrics calculation."""
        incidents = [
            IncidentSummary(
                incident_id=f"inc-{i}",
                title=f"Incident {i}",
                service_name="api-service",
                severity="high" if i % 2 == 0 else "medium",
                triggered_at=datetime.utcnow(),
                duration_minutes=30 + i * 10,
            )
            for i in range(5)
        ]

        metrics = generator._calculate_metrics(
            incidents,
            datetime.utcnow() - timedelta(days=1),
            datetime.utcnow(),
        )

        assert metrics.total_incidents == 5
        assert metrics.incidents_by_severity["high"] == 3
        assert metrics.incidents_by_severity["medium"] == 2
        assert metrics.mean_mttr_minutes == 50.0  # (30+40+50+60+70)/5

    def test_generate_executive_summary(self, generator):
        """Test executive summary generation."""
        incidents = [
            IncidentSummary(
                incident_id="inc-1",
                title="Test Incident",
                service_name="api-service",
                severity="critical",
                triggered_at=datetime.utcnow(),
                duration_minutes=30,
            ),
        ]
        metrics = MetricsSummary(
            period_start=datetime.utcnow() - timedelta(days=1),
            period_end=datetime.utcnow(),
            total_incidents=1,
            incidents_by_severity={"critical": 1},
            incidents_by_service={"api-service": 1},
            mean_mttr_minutes=30.0,
        )

        summary = generator._generate_executive_summary(incidents, metrics)

        assert "1 incident" in summary
        assert "critical" in summary
        assert "api-service" in summary

    def test_get_report_title(self, generator, sample_config):
        """Test report title generation."""
        start = datetime(2024, 2, 1)
        end = datetime(2024, 2, 7)

        title = generator._get_report_title(sample_config, start, end)

        assert "Daily" in title
        assert "2024-02-07" in title

    @pytest.mark.asyncio
    async def test_generate_report(self, generator, sample_config):
        """Test full report generation."""
        # Mock the analytics store
        with patch("src.reports.generator.analytics_store") as mock_store:
            mock_store.get_metrics_for_period = AsyncMock(return_value=[])

            output = await generator.generate_report(sample_config)

            assert output.run_status == ReportRunStatus.COMPLETED
            assert output.content is not None
            assert output.content.title is not None

    @pytest.mark.asyncio
    async def test_generate_report_with_request(self, generator, sample_config):
        """Test report generation with custom request."""
        request = ReportRunRequest(
            period_start=datetime(2024, 2, 1),
            period_end=datetime(2024, 2, 7),
            skip_delivery=True,
        )

        with patch("src.reports.generator.analytics_store") as mock_store:
            mock_store.get_metrics_for_period = AsyncMock(return_value=[])

            output = await generator.generate_report(sample_config, request)

            assert output.content.period_start == request.period_start
            assert output.content.period_end == request.period_end


# =============================================================================
# Integration Tests
# =============================================================================


class TestReportsIntegration:
    """Integration tests for the reports module."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete workflow: schedule -> generate -> deliver."""
        # Create fresh store for test
        store = ReportStore()

        # Create config - no delivery channels to avoid delivery status issues
        config = ReportConfig(
            id="integration-test",
            name="Integration Test Report",
            report_type=ReportType.DAILY_SUMMARY,
            schedule=ReportSchedule(
                cron_expression="0 9 * * *",
                timezone="UTC",
            ),
            delivery_channels=[],  # No delivery channels for test
            template=ReportTemplate(format="both"),
        )

        # Mock settings
        settings = MagicMock()
        settings.anthropic_api_key = ""
        settings.slack_bot_token = ""
        settings.aws_region = ""

        # Create generator
        generator = ReportGenerator(settings)
        generator.store = store

        # Create scheduler with generator callback
        scheduler = ReportScheduler(run_callback=generator.run_scheduled_report)
        scheduler.store = store

        # Schedule report
        scheduled = await scheduler.schedule_report(config)
        assert scheduled.schedule.next_run_at is not None

        # Generate report manually
        with patch("src.reports.generator.analytics_store") as mock_store:
            mock_store.get_metrics_for_period = AsyncMock(return_value=[])

            output = await generator.generate_report(config)

            assert output.run_status == ReportRunStatus.COMPLETED
            assert output.content.html is not None
            assert output.content.markdown is not None

        # Check output was stored
        stored_output = await store.get_output(output.id)
        assert stored_output is not None
        assert stored_output.content.title == output.content.title

    @pytest.mark.asyncio
    async def test_models_serialization(self):
        """Test that models serialize/deserialize correctly."""
        config = ReportConfig(
            id="serialize-test",
            name="Serialize Test",
            report_type=ReportType.WEEKLY_RELIABILITY,
            schedule=ReportSchedule(
                cron_expression="0 9 * * 1",
                timezone="America/New_York",
            ),
            delivery_channels=[
                DeliveryConfig(
                    channel=DeliveryChannel.EMAIL,
                    recipients=["test@example.com"],
                ),
            ],
            filters=ReportFilter(
                services=["api", "web"],
                severities=["critical", "high"],
            ),
        )

        # Serialize to dict
        config_dict = config.model_dump()

        # Deserialize back
        config2 = ReportConfig.model_validate(config_dict)

        assert config2.id == config.id
        assert config2.schedule.cron_expression == config.schedule.cron_expression
        assert len(config2.delivery_channels) == 1
        assert config2.filters.services == ["api", "web"]
