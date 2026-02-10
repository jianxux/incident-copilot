"""Scheduled reports module for Incident Copilot.

This module provides scheduled report generation and delivery for incident data.

Features:
- Cron-based scheduling with timezone support
- HTML and Markdown report templates
- Email delivery (SMTP and AWS SES)
- Slack delivery (webhook and API)
- Webhook and S3 delivery adapters
- AI-powered insights and recommendations

Usage:
    from src.reports import (
        ReportGenerator,
        ReportScheduler,
        ReportConfig,
        ReportSchedule,
        ReportType,
        DeliveryChannel,
        DeliveryConfig,
    )

    # Create a report configuration
    config = ReportConfig(
        id="weekly-reliability",
        name="Weekly Reliability Report",
        report_type=ReportType.WEEKLY_RELIABILITY,
        schedule=ReportSchedule(
            cron_expression="0 9 * * 1",  # Monday 9am
            timezone="America/Los_Angeles",
        ),
        delivery_channels=[
            DeliveryConfig(
                channel=DeliveryChannel.EMAIL,
                recipients=["team@example.com"],
            ),
            DeliveryConfig(
                channel=DeliveryChannel.SLACK,
                slack_channel="#incidents",
            ),
        ],
    )

    # Schedule and run
    scheduler = ReportScheduler(run_callback=generator.run_scheduled_report)
    await scheduler.schedule_report(config)
    await scheduler.start()
"""

from .delivery import (
    DeliveryAdapter,
    EmailDeliveryAdapter,
    ReportDeliveryService,
    S3DeliveryAdapter,
    SlackDeliveryAdapter,
    WebhookDeliveryAdapter,
)
from .generator import ReportGenerator, report_generator
from .models import (
    DeliveryChannel,
    DeliveryConfig,
    IncidentSummary,
    MetricsSummary,
    ReportConfig,
    ReportContent,
    ReportCreateRequest,
    ReportFilter,
    ReportOutput,
    ReportRunRequest,
    ReportRunStatus,
    ReportSchedule,
    ReportStatus,
    ReportTemplate,
    ReportType,
    ReportUpdateRequest,
)
from .scheduler import (
    CRON_PRESETS,
    CronExpression,
    ReportScheduler,
    describe_cron,
    get_cron_preset,
)
from .store import ReportStore, report_store
from .templates import ReportTemplates, report_templates

__all__ = [
    # Models
    "ReportType",
    "ReportStatus",
    "ReportRunStatus",
    "DeliveryChannel",
    "DeliveryConfig",
    "ReportSchedule",
    "ReportFilter",
    "ReportTemplate",
    "ReportConfig",
    "IncidentSummary",
    "MetricsSummary",
    "ReportContent",
    "ReportOutput",
    "ReportRunRequest",
    "ReportCreateRequest",
    "ReportUpdateRequest",
    # Scheduler
    "CronExpression",
    "ReportScheduler",
    "CRON_PRESETS",
    "get_cron_preset",
    "describe_cron",
    # Generator
    "ReportGenerator",
    "report_generator",
    # Delivery
    "DeliveryAdapter",
    "EmailDeliveryAdapter",
    "SlackDeliveryAdapter",
    "WebhookDeliveryAdapter",
    "S3DeliveryAdapter",
    "ReportDeliveryService",
    # Templates
    "ReportTemplates",
    "report_templates",
    # Store
    "ReportStore",
    "report_store",
]
