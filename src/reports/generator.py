"""Report generator service."""

import hashlib
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from ..analytics.store import analytics_store
from ..config import Settings, get_settings
from .delivery import ReportDeliveryService
from .models import (
    IncidentSummary,
    MetricsSummary,
    ReportConfig,
    ReportContent,
    ReportOutput,
    ReportRunRequest,
    ReportRunStatus,
    ReportType,
)
from .store import report_store
from .templates import ReportTemplates

logger = structlog.get_logger()


class ReportGenerator:
    """
    Main service for generating scheduled reports.

    Orchestrates data collection, content generation, template rendering,
    and delivery of reports.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.templates = ReportTemplates()
        self.delivery_service = ReportDeliveryService(self.settings)
        self.store = report_store

    async def generate_report(
        self,
        config: ReportConfig,
        request: ReportRunRequest | None = None,
    ) -> ReportOutput:
        """
        Generate a report based on configuration.

        Args:
            config: Report configuration
            request: Optional run request with overrides

        Returns:
            ReportOutput with generation and delivery results
        """
        request = request or ReportRunRequest()

        # Create output record
        output = ReportOutput(
            id=self._generate_id(f"output_{config.id}_{datetime.now(UTC).isoformat()}"),
            report_config_id=config.id,
            run_status=ReportRunStatus.RUNNING,
            started_at=datetime.now(UTC),
            triggered_by="schedule" if not request else "manual",
        )
        await self.store.save_output(output)

        try:
            # Determine time range
            period_end = request.period_end or datetime.now(UTC)
            period_start = request.period_start or self._get_default_period_start(
                config.report_type, period_end
            )

            # Collect data
            incidents = await self._collect_incidents(
                period_start, period_end, config, request
            )

            # Calculate metrics
            metrics = self._calculate_metrics(incidents, period_start, period_end)

            # Generate AI insights if enabled
            ai_insights = []
            ai_recommendations = []
            if config.template.include_ai_insights:
                ai_insights, ai_recommendations = await self._generate_ai_analysis(
                    incidents, metrics, config
                )

            # Build content
            content = ReportContent(
                report_config_id=config.id,
                report_type=config.report_type,
                period_start=period_start,
                period_end=period_end,
                title=self._get_report_title(config, period_start, period_end),
                subtitle=config.description,
                executive_summary=self._generate_executive_summary(incidents, metrics),
                metrics=metrics,
                incidents=incidents,
                trends=self._calculate_trends(metrics),
                ai_insights=ai_insights,
                ai_recommendations=ai_recommendations,
            )

            # Render templates
            template_name = self._get_template_name(config.report_type)
            template_context = self._build_template_context(content, config)

            # Render HTML
            if config.template.format in ("html", "both"):
                content.html = self.templates.render_html(
                    template_name, template_context
                )

            # Render Markdown
            if config.template.format in ("markdown", "both"):
                content.markdown = self.templates.render_markdown(
                    template_name, template_context
                )

            # Always generate JSON data
            content.json_data = self._content_to_dict(content)

            # Update output with content
            output.content = content
            output.run_status = ReportRunStatus.COMPLETED
            output.completed_at = datetime.now(UTC)
            output.duration_seconds = (
                output.completed_at - output.started_at
            ).total_seconds()

            # Deliver if not skipped
            if not request.skip_delivery:
                delivery_configs = config.delivery_channels
                if request.delivery_channels:
                    # Filter to requested channels
                    delivery_configs = [
                        dc
                        for dc in delivery_configs
                        if dc.channel in request.delivery_channels
                    ]

                if delivery_configs:
                    delivery_results = await self.delivery_service.deliver(
                        content, delivery_configs
                    )
                    output.delivery_results = delivery_results

                    # Check if any delivery failed
                    all_success = all(
                        r.get("success") for r in delivery_results.values()
                    )
                    if not all_success:
                        output.run_status = ReportRunStatus.DELIVERY_FAILED

            await self.store.save_output(output)

            logger.info(
                "report_generated",
                config_id=config.id,
                output_id=output.id,
                incidents=len(incidents),
                duration_seconds=output.duration_seconds,
            )

            return output

        except Exception as e:
            output.run_status = ReportRunStatus.FAILED
            output.error_message = str(e)
            output.completed_at = datetime.now(UTC)
            await self.store.save_output(output)

            logger.error(
                "report_generation_failed",
                config_id=config.id,
                error=str(e),
            )
            raise

    def _get_default_period_start(
        self,
        report_type: ReportType,
        period_end: datetime,
    ) -> datetime:
        """Get default period start based on report type."""
        if report_type == ReportType.DAILY_SUMMARY:
            return period_end - timedelta(days=1)
        elif report_type == ReportType.WEEKLY_RELIABILITY:
            return period_end - timedelta(weeks=1)
        elif report_type == ReportType.MONTHLY_ANALYSIS:
            return period_end - timedelta(days=30)
        else:
            return period_end - timedelta(days=1)

    async def _collect_incidents(
        self,
        period_start: datetime,
        period_end: datetime,
        config: ReportConfig,
        request: ReportRunRequest,
    ) -> list[IncidentSummary]:
        """Collect incident data from analytics store."""
        # Get metrics from analytics store
        filters = request.filters or config.filters

        try:
            metrics = await analytics_store.get_metrics_for_period(
                start=period_start,
                end=period_end,
                service_name=filters.services[0] if filters.services else None,
            )
        except Exception as e:
            logger.warning("analytics_fetch_failed", error=str(e))
            metrics = []

        # Convert to IncidentSummary
        incidents = []
        for metric in metrics:
            # Apply filters
            if filters.services and metric.service not in filters.services:
                continue
            if filters.exclude_services and metric.service in filters.exclude_services:
                continue
            if filters.severities and metric.severity not in filters.severities:
                continue

            summary = IncidentSummary(
                incident_id=metric.incident_id,
                title=metric.title,
                service_name=metric.service,
                severity=metric.severity,
                triggered_at=metric.triggered_at,
                resolved_at=metric.resolved_at,
                duration_minutes=metric.duration_minutes,
                mttr_seconds=metric.mttr_seconds,
                root_cause=getattr(metric, "root_cause", None),
            )
            incidents.append(summary)

        # Sort by triggered_at descending
        incidents.sort(key=lambda x: x.triggered_at, reverse=True)

        return incidents

    def _calculate_metrics(
        self,
        incidents: list[IncidentSummary],
        period_start: datetime,
        period_end: datetime,
    ) -> MetricsSummary:
        """Calculate metrics summary from incidents."""
        # Count by severity
        severity_counts: dict[str, int] = {}
        service_counts: dict[str, int] = {}
        mttr_values = []

        for incident in incidents:
            # Severity counts
            sev = incident.severity
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            # Service counts
            svc = incident.service_name
            service_counts[svc] = service_counts.get(svc, 0) + 1

            # MTTR
            if incident.duration_minutes is not None:
                mttr_values.append(incident.duration_minutes)

        # Calculate MTTR statistics
        mean_mttr = statistics.mean(mttr_values) if mttr_values else None
        median_mttr = statistics.median(mttr_values) if mttr_values else None
        p90_mttr = (
            sorted(mttr_values)[int(len(mttr_values) * 0.9)]
            if len(mttr_values) >= 10
            else None
        )

        return MetricsSummary(
            period_start=period_start,
            period_end=period_end,
            total_incidents=len(incidents),
            incidents_by_severity=severity_counts,
            incidents_by_service=service_counts,
            mean_mttr_minutes=mean_mttr,
            median_mttr_minutes=median_mttr,
            p90_mttr_minutes=p90_mttr,
            trend="stable",  # Would be calculated from historical data
        )

    async def _generate_ai_analysis(
        self,
        incidents: list[IncidentSummary],
        metrics: MetricsSummary,
        config: ReportConfig,
    ) -> tuple[list[str], list[str]]:
        """Generate AI-powered insights and recommendations."""
        insights = []
        recommendations = []

        try:
            # Import Anthropic client
            from anthropic import AsyncAnthropic

            if not self.settings.anthropic_api_key:
                return insights, recommendations

            client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)

            # Build context
            context = self._build_ai_context(incidents, metrics)

            # Generate analysis
            model = config.template.ai_model or self.settings.ai_model
            response = await client.messages.create(
                model=model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": f"""Analyze the following incident data and provide:
1. 3-5 key insights about patterns, trends, or notable observations
2. 3-5 actionable recommendations for improving reliability

Data:
{context}

Format your response as:
INSIGHTS:
- [insight 1]
- [insight 2]
...

RECOMMENDATIONS:
- [recommendation 1]
- [recommendation 2]
...""",
                    }
                ],
            )

            # Parse response
            response_text = response.content[0].text
            parsing_insights = False
            parsing_recommendations = False

            for line in response_text.split("\n"):
                line = line.strip()
                if line.startswith("INSIGHTS"):
                    parsing_insights = True
                    parsing_recommendations = False
                elif line.startswith("RECOMMENDATIONS"):
                    parsing_insights = False
                    parsing_recommendations = True
                elif line.startswith("- "):
                    item = line[2:].strip()
                    if parsing_insights:
                        insights.append(item)
                    elif parsing_recommendations:
                        recommendations.append(item)

        except Exception as e:
            logger.warning("ai_analysis_failed", error=str(e))

        return insights, recommendations

    def _build_ai_context(
        self,
        incidents: list[IncidentSummary],
        metrics: MetricsSummary,
    ) -> str:
        """Build context string for AI analysis."""
        context_parts = [
            f"Report Period: {metrics.period_start.date()} to {metrics.period_end.date()}",
            f"Total Incidents: {metrics.total_incidents}",
            (
                f"Mean MTTR: {metrics.mean_mttr_minutes:.1f} minutes"
                if metrics.mean_mttr_minutes
                else ""
            ),
        ]

        if metrics.incidents_by_severity:
            context_parts.append("\nBy Severity:")
            for sev, count in sorted(metrics.incidents_by_severity.items()):
                context_parts.append(f"  - {sev}: {count}")

        if metrics.incidents_by_service:
            context_parts.append("\nBy Service:")
            for svc, count in sorted(
                metrics.incidents_by_service.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]:
                context_parts.append(f"  - {svc}: {count}")

        context_parts.append("\nRecent Incidents:")
        for inc in incidents[:10]:
            context_parts.append(
                f"  - [{inc.severity}] {inc.service_name}: {inc.title[:60]}"
            )

        return "\n".join(filter(None, context_parts))

    def _generate_executive_summary(
        self,
        incidents: list[IncidentSummary],
        metrics: MetricsSummary,
    ) -> str:
        """Generate executive summary text."""
        parts = []

        # Total incidents
        parts.append(f"This period saw {metrics.total_incidents} incident(s).")

        # Severity breakdown
        if metrics.incidents_by_severity:
            critical = metrics.incidents_by_severity.get("critical", 0)
            high = metrics.incidents_by_severity.get("high", 0)
            if critical or high:
                parts.append(
                    f"Of these, {critical} were critical and {high} were high severity."
                )

        # Top affected service
        if metrics.incidents_by_service:
            top_service = max(
                metrics.incidents_by_service.items(),
                key=lambda x: x[1],
            )
            parts.append(
                f"The most affected service was {top_service[0]} with {top_service[1]} incident(s)."
            )

        # MTTR
        if metrics.mean_mttr_minutes:
            parts.append(
                f"Mean time to resolution was {metrics.mean_mttr_minutes:.1f} minutes."
            )

        return " ".join(parts)

    def _calculate_trends(self, metrics: MetricsSummary) -> dict[str, Any]:
        """Calculate trend information."""
        # In a real implementation, this would compare to previous period
        return {
            "incident_volume": "stable",
            "mttr_trend": (
                "improving"
                if metrics.mean_mttr_minutes and metrics.mean_mttr_minutes < 30
                else "stable"
            ),
            "top_services_affected": (
                list(metrics.incidents_by_service.keys())[:5]
                if metrics.incidents_by_service
                else []
            ),
        }

    def _get_report_title(
        self,
        config: ReportConfig,
        period_start: datetime,
        period_end: datetime,
    ) -> str:
        """Generate report title."""
        type_titles = {
            ReportType.DAILY_SUMMARY: "Daily Incident Summary",
            ReportType.WEEKLY_RELIABILITY: "Weekly Reliability Report",
            ReportType.MONTHLY_ANALYSIS: "Monthly Reliability Analysis",
            ReportType.ON_DEMAND: "Incident Report",
        }

        base_title = type_titles.get(config.report_type, "Incident Report")
        date_str = period_end.strftime("%Y-%m-%d")

        return f"{base_title} - {date_str}"

    def _get_template_name(self, report_type: ReportType) -> str:
        """Map report type to template name."""
        mapping = {
            ReportType.DAILY_SUMMARY: "daily_summary",
            ReportType.WEEKLY_RELIABILITY: "weekly_reliability",
            ReportType.MONTHLY_ANALYSIS: "monthly_analysis",
            ReportType.ON_DEMAND: "incident_summary",
        }
        return mapping.get(report_type, "daily_summary")

    def _build_template_context(
        self,
        content: ReportContent,
        config: ReportConfig,
    ) -> dict[str, Any]:
        """Build template context from content and config."""
        context = {
            "title": content.title,
            "subtitle": content.subtitle,
            "period_start": content.period_start,
            "period_end": content.period_end,
            "generated_at": content.generated_at,
            "executive_summary": content.executive_summary,
            "metrics": content.metrics,
            "incidents": content.incidents,
            "trends": content.trends,
            "ai_insights": content.ai_insights,
            "ai_recommendations": content.ai_recommendations,
            "logo_url": config.template.logo_url,
            "header": config.template.header,
            "footer": config.template.footer,
            "style": self.templates.HTML_BASE_STYLE,
        }
        return context

    def _content_to_dict(self, content: ReportContent) -> dict[str, Any]:
        """Convert content to JSON-serializable dict."""
        return {
            "report_type": content.report_type.value,
            "title": content.title,
            "subtitle": content.subtitle,
            "period_start": content.period_start.isoformat(),
            "period_end": content.period_end.isoformat(),
            "generated_at": content.generated_at.isoformat(),
            "executive_summary": content.executive_summary,
            "metrics": content.metrics.model_dump() if content.metrics else None,
            "incidents": [i.model_dump() for i in content.incidents],
            "trends": content.trends,
            "ai_insights": content.ai_insights,
            "ai_recommendations": content.ai_recommendations,
        }

    def _generate_id(self, base: str) -> str:
        """Generate a deterministic ID."""
        return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()[:12]

    async def run_scheduled_report(self, config: ReportConfig) -> ReportOutput:
        """
        Run a scheduled report.

        This is the callback invoked by the scheduler.
        """
        return await self.generate_report(config)


# Global generator instance
report_generator = ReportGenerator()
