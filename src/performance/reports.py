"""Generate performance reports (weekly digest, exports)."""

import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

import structlog

from .calculator import PerformanceCalculator
from .leaderboard import LeaderboardGenerator
from .models import (
    BurnoutIndicator,
    OnCallStats,
    PerformanceReport,
    PerformanceSummary,
    TrendDirection,
)
from .trends import TrendAnalyzer

logger = structlog.get_logger()


class ReportFormat(str, Enum):
    """Report output formats."""

    JSON = "json"
    MARKDOWN = "markdown"
    SLACK = "slack"
    HTML = "html"


class ReportGenerator:
    """Generate comprehensive performance reports."""

    def __init__(
        self,
        calculator: PerformanceCalculator | None = None,
        trend_analyzer: TrendAnalyzer | None = None,
        leaderboard_generator: LeaderboardGenerator | None = None,
    ):
        """Initialize with optional components."""
        self.calculator = calculator or PerformanceCalculator()
        self.trend_analyzer = trend_analyzer or TrendAnalyzer(self.calculator)
        self.leaderboard_generator = leaderboard_generator or LeaderboardGenerator(
            self.calculator
        )

    async def generate_weekly_digest(
        self,
        incidents: list[dict],
        oncall_data: list[dict],
        reference_date: datetime | None = None,
        team_name: str | None = None,
        service_name: str | None = None,
        include_ai_summary: bool = True,
    ) -> PerformanceReport:
        """
        Generate a weekly performance digest.

        Args:
            incidents: All incidents
            oncall_data: On-call schedule/responder data
            reference_date: Reference date (defaults to now)
            team_name: Optional team filter
            service_name: Optional service filter
            include_ai_summary: Whether to include AI summary

        Returns:
            PerformanceReport with weekly metrics and insights
        """
        if reference_date is None:
            reference_date = datetime.utcnow()

        # Calculate week boundaries
        days_since_monday = reference_date.weekday()
        week_start = (reference_date - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=7)

        return await self.generate_report(
            incidents=incidents,
            oncall_data=oncall_data,
            period_start=week_start,
            period_end=week_end,
            team_name=team_name,
            service_name=service_name,
            include_ai_summary=include_ai_summary,
        )

    async def generate_report(
        self,
        incidents: list[dict],
        oncall_data: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        service_name: str | None = None,
        include_ai_summary: bool = True,
    ) -> PerformanceReport:
        """
        Generate a comprehensive performance report.

        Args:
            incidents: All incidents
            oncall_data: On-call schedule/responder data
            period_start: Start of report period
            period_end: End of report period
            team_name: Optional team filter
            service_name: Optional service filter
            include_ai_summary: Whether to include AI summary

        Returns:
            PerformanceReport with full metrics
        """
        report_id = f"pr-{uuid4().hex[:12]}"

        # Calculate team metrics
        team_metrics = self.calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Calculate on-call stats for each responder
        oncall_stats = self._build_oncall_stats(
            incidents=incidents,
            oncall_data=oncall_data,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
        )

        # Calculate trends
        trends = self.trend_analyzer.calculate_all_trends(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Calculate volume distribution
        incident_volume = self.calculator.calculate_incident_volume(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
        )

        # Time distribution
        time_distribution = self.calculator.calculate_time_distribution(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
        )

        # Workload distribution
        workload_distribution = self.calculator.calculate_workload_distribution(
            oncall_stats=oncall_stats,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
        )

        # SLA compliance
        sla_compliance = self.calculator.calculate_sla_compliance(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        # Burnout indicators
        burnout_indicators = [
            self.calculator.calculate_burnout_indicator(stat) for stat in oncall_stats
        ]
        high_risk_burnout = [b for b in burnout_indicators if b.risk_level in ("high", "critical")]

        # Top responders
        leaderboard = self.leaderboard_generator.generate_top_responders(
            oncall_stats=oncall_stats,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            limit=5,
        )
        top_responders = [
            self.leaderboard_generator.build_responder_stats(
                oncall_stat=next(
                    s for s in oncall_stats if s.responder_id == entry.responder_id
                ),
                incidents=incidents,
            )
            for entry in leaderboard.entries
            if any(s.responder_id == entry.responder_id for s in oncall_stats)
        ]

        # Build summary
        summary = self._build_summary(
            team_metrics=team_metrics,
            trends=trends,
            top_responders=[e.responder_name for e in leaderboard.entries[:3]],
            incident_volume=incident_volume,
            burnout_indicators=high_risk_burnout,
            workload_distribution=workload_distribution,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
        )

        logger.info(
            "performance_report_generated",
            report_id=report_id,
            team=team_name,
            service=service_name,
            total_incidents=team_metrics.total_incidents,
        )

        return PerformanceReport(
            report_id=report_id,
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
            summary=summary,
            team_metrics=team_metrics,
            oncall_stats=oncall_stats,
            trends=trends,
            incident_volume=incident_volume,
            time_distribution=time_distribution,
            workload_distribution=workload_distribution,
            sla_compliance=sla_compliance,
            burnout_indicators=burnout_indicators,
            top_responders=top_responders,
        )

    def export_report(
        self,
        report: PerformanceReport,
        format: ReportFormat = ReportFormat.MARKDOWN,
    ) -> str:
        """
        Export a report to the specified format.

        Args:
            report: PerformanceReport to export
            format: Output format

        Returns:
            Formatted report string
        """
        if format == ReportFormat.JSON:
            return self._export_json(report)
        elif format == ReportFormat.MARKDOWN:
            return self._export_markdown(report)
        elif format == ReportFormat.SLACK:
            return self._export_slack(report)
        elif format == ReportFormat.HTML:
            return self._export_html(report)
        else:
            return self._export_markdown(report)

    def _build_oncall_stats(
        self,
        incidents: list[dict],
        oncall_data: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
    ) -> list[OnCallStats]:
        """Build OnCallStats for each responder from incidents."""
        # Extract unique responders
        responders: dict[str, dict[str, Any]] = {}

        for data in oncall_data:
            responder_id = data.get("id") or data.get("user_id")
            if responder_id:
                responders[responder_id] = {
                    "id": responder_id,
                    "name": data.get("name", responder_id),
                    "email": data.get("email"),
                    "team": data.get("team_name") or data.get("team"),
                    "oncall_hours": data.get("oncall_hours"),
                }

        # Also extract from incidents
        for inc in incidents:
            for assigned in inc.get("assigned_to", []):
                if assigned and assigned not in responders:
                    responders[assigned] = {
                        "id": assigned,
                        "name": assigned,
                        "email": None,
                        "team": inc.get("team_name"),
                        "oncall_hours": None,
                    }

        # Filter by team
        if team_name:
            responders = {
                k: v for k, v in responders.items() if v.get("team") == team_name
            }

        # Build stats for each responder
        stats = []
        for responder_id, data in responders.items():
            stat = self.calculator.calculate_oncall_stats(
                incidents=incidents,
                responder_id=responder_id,
                responder_name=data["name"],
                period_start=period_start,
                period_end=period_end,
                responder_email=data.get("email"),
                team_name=data.get("team"),
                oncall_hours=data.get("oncall_hours"),
            )
            if stat.total_pages > 0:
                stats.append(stat)

        return stats

    def _build_summary(
        self,
        team_metrics,
        trends,
        top_responders,
        incident_volume,
        burnout_indicators,
        workload_distribution,
        period_start,
        period_end,
        team_name,
        service_name,
    ) -> PerformanceSummary:
        """Build the performance summary."""
        # Determine trend directions
        mttr_trend = None
        mtta_trend = None
        incident_trend = None

        for trend in trends:
            if trend.metric_name == "mttr":
                mttr_trend = trend.direction
            elif trend.metric_name == "mtta":
                mtta_trend = trend.direction
            elif trend.metric_name == "incident_count":
                incident_trend = trend.direction

        # Most affected services
        most_affected = sorted(
            incident_volume.by_service.items(), key=lambda x: x[1], reverse=True
        )[:3]
        most_affected_services = [s[0] for s in most_affected]

        # Busiest day
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        busiest_day = (
            day_names[incident_volume.peak_day]
            if incident_volume.peak_day is not None
            else None
        )

        # Generate insights
        key_insights = []
        recommendations = []

        # MTTR insight
        if mttr_trend == TrendDirection.IMPROVING:
            key_insights.append(
                f"MTTR improved to {team_metrics.mttr_minutes:.0f} minutes"
            )
        elif mttr_trend == TrendDirection.DECLINING:
            key_insights.append(
                f"MTTR increased to {team_metrics.mttr_minutes:.0f} minutes - investigate bottlenecks"
            )
            recommendations.append("Review incident response processes to reduce resolution time")

        # Incident volume insight
        if incident_trend == TrendDirection.DECLINING:
            key_insights.append("Incident volume decreased - great progress!")
        elif incident_trend == TrendDirection.IMPROVING:
            key_insights.append("Incident volume increased - may need additional investigation")

        # SLA insight
        if team_metrics.sla_compliance_percent:
            if team_metrics.sla_compliance_percent >= 95:
                key_insights.append(
                    f"SLA compliance at {team_metrics.sla_compliance_percent:.1f}% - excellent!"
                )
            elif team_metrics.sla_compliance_percent < 90:
                key_insights.append(
                    f"SLA compliance at {team_metrics.sla_compliance_percent:.1f}% - needs attention"
                )
                recommendations.append("Focus on critical and high severity incidents first")

        # Burnout insight
        if burnout_indicators:
            key_insights.append(
                f"{len(burnout_indicators)} responder(s) showing burnout risk indicators"
            )
            recommendations.append("Review on-call rotation to balance workload")

        # Workload imbalance
        workload_imbalance = False
        if workload_distribution.gini_coefficient and workload_distribution.gini_coefficient > 0.4:
            workload_imbalance = True
            recommendations.append("Workload is imbalanced - consider rotation adjustments")

        return PerformanceSummary(
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            service_name=service_name,
            mttr_minutes=team_metrics.mttr_minutes,
            mtta_minutes=team_metrics.mtta_minutes,
            total_incidents=team_metrics.total_incidents,
            sla_compliance_percent=team_metrics.sla_compliance_percent,
            mttr_trend=mttr_trend,
            mtta_trend=mtta_trend,
            incident_trend=incident_trend,
            top_responders=top_responders,
            most_affected_services=most_affected_services,
            busiest_day=busiest_day,
            burnout_risk_count=len(burnout_indicators),
            workload_imbalance=workload_imbalance,
            key_insights=key_insights,
            recommendations=recommendations,
        )

    def _export_json(self, report: PerformanceReport) -> str:
        """Export report as JSON."""
        return report.model_dump_json(indent=2)

    def _export_markdown(self, report: PerformanceReport) -> str:
        """Export report as Markdown."""
        lines = []

        # Header
        lines.append(f"# Performance Report")
        lines.append("")
        period_str = f"{report.period_start.strftime('%Y-%m-%d')} to {report.period_end.strftime('%Y-%m-%d')}"
        lines.append(f"**Period:** {period_str}")
        if report.team_name:
            lines.append(f"**Team:** {report.team_name}")
        if report.service_name:
            lines.append(f"**Service:** {report.service_name}")
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        summary = report.summary

        # Key metrics table
        lines.append("| Metric | Value | Trend |")
        lines.append("|--------|-------|-------|")

        mttr_trend_icon = self._trend_icon(summary.mttr_trend)
        mtta_trend_icon = self._trend_icon(summary.mtta_trend)
        incident_trend_icon = self._trend_icon(summary.incident_trend, invert=True)

        lines.append(
            f"| MTTR | {summary.mttr_minutes:.0f} min | {mttr_trend_icon} |"
            if summary.mttr_minutes
            else "| MTTR | N/A | - |"
        )
        lines.append(
            f"| MTTA | {summary.mtta_minutes:.0f} min | {mtta_trend_icon} |"
            if summary.mtta_minutes
            else "| MTTA | N/A | - |"
        )
        lines.append(f"| Total Incidents | {summary.total_incidents} | {incident_trend_icon} |")
        lines.append(
            f"| SLA Compliance | {summary.sla_compliance_percent:.1f}% | - |"
            if summary.sla_compliance_percent
            else "| SLA Compliance | N/A | - |"
        )
        lines.append("")

        # Key insights
        if summary.key_insights:
            lines.append("### Key Insights")
            lines.append("")
            for insight in summary.key_insights:
                lines.append(f"- {insight}")
            lines.append("")

        # Recommendations
        if summary.recommendations:
            lines.append("### Recommendations")
            lines.append("")
            for rec in summary.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        # Top Responders
        if report.top_responders:
            lines.append("## Top Responders")
            lines.append("")
            lines.append("| Rank | Name | Incidents | Avg Ack Time | Score |")
            lines.append("|------|------|-----------|--------------|-------|")
            for i, responder in enumerate(report.top_responders, 1):
                ack_time = (
                    f"{responder.avg_ack_time_minutes:.1f} min"
                    if responder.avg_ack_time_minutes
                    else "N/A"
                )
                lines.append(
                    f"| {i} | {responder.responder_name} | "
                    f"{responder.incidents_handled} | {ack_time} | {responder.total_score} |"
                )
            lines.append("")

        # Burnout Alerts
        high_risk = [
            b for b in report.burnout_indicators if b.risk_level in ("high", "critical")
        ]
        if high_risk:
            lines.append("## ⚠️ Burnout Alerts")
            lines.append("")
            for indicator in high_risk:
                lines.append(
                    f"- **{indicator.responder_name}** ({indicator.risk_level.upper()}): "
                    f"{indicator.total_pages} pages, {indicator.off_hours_pages} off-hours"
                )
            lines.append("")

        # Incident Distribution
        if report.incident_volume:
            lines.append("## Incident Distribution")
            lines.append("")
            lines.append("### By Severity")
            for sev, count in sorted(report.incident_volume.by_severity.items()):
                lines.append(f"- **{sev.capitalize()}:** {count}")
            lines.append("")

            lines.append("### Top Services")
            top_services = sorted(
                report.incident_volume.by_service.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:5]
            for service, count in top_services:
                lines.append(f"- **{service}:** {count}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Generated at {report.generated_at.isoformat()}*")

        return "\n".join(lines)

    def _export_slack(self, report: PerformanceReport) -> str:
        """Export report as Slack Block Kit JSON."""
        blocks = []
        summary = report.summary

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 Performance Report",
                "emoji": True,
            },
        })

        # Period info
        period_str = f"{report.period_start.strftime('%b %d')} - {report.period_end.strftime('%b %d, %Y')}"
        team_info = f"Team: {report.team_name}" if report.team_name else "All Teams"
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*{period_str}* | {team_info}"},
            ],
        })

        blocks.append({"type": "divider"})

        # Key metrics
        mttr_trend = self._trend_icon(summary.mttr_trend)
        incident_trend = self._trend_icon(summary.incident_trend, invert=True)

        metrics_text = []
        if summary.mttr_minutes:
            metrics_text.append(f"*MTTR:* {summary.mttr_minutes:.0f} min {mttr_trend}")
        if summary.mtta_minutes:
            metrics_text.append(f"*MTTA:* {summary.mtta_minutes:.0f} min")
        metrics_text.append(f"*Incidents:* {summary.total_incidents} {incident_trend}")
        if summary.sla_compliance_percent:
            sla_emoji = "✅" if summary.sla_compliance_percent >= 95 else "⚠️"
            metrics_text.append(f"*SLA:* {summary.sla_compliance_percent:.1f}% {sla_emoji}")

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": " | ".join(metrics_text),
            },
        })

        # Key insights
        if summary.key_insights:
            insights_text = "\n".join(f"• {i}" for i in summary.key_insights[:3])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Key Insights:*\n{insights_text}",
                },
            })

        # Top responders
        if report.top_responders:
            blocks.append({"type": "divider"})
            top_text = "*🏆 Top Responders:*\n"
            for i, r in enumerate(report.top_responders[:3], 1):
                medal = ["🥇", "🥈", "🥉"][i - 1]
                top_text += f"{medal} {r.responder_name} ({r.incidents_handled} incidents)\n"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": top_text},
            })

        # Burnout alerts
        high_risk = [
            b for b in report.burnout_indicators if b.risk_level in ("high", "critical")
        ]
        if high_risk:
            blocks.append({"type": "divider"})
            alert_text = "*⚠️ Burnout Alerts:*\n"
            for b in high_risk[:3]:
                alert_text += f"• {b.responder_name}: {b.total_pages} pages, {b.off_hours_pages} off-hours\n"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": alert_text},
            })

        return json.dumps({"blocks": blocks}, indent=2)

    def _export_html(self, report: PerformanceReport) -> str:
        """Export report as HTML."""
        summary = report.summary

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Performance Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
        .header {{ border-bottom: 2px solid #333; padding-bottom: 20px; }}
        .metrics {{ display: flex; gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #f5f5f5; padding: 15px; border-radius: 8px; min-width: 150px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; }}
        .metric-label {{ color: #666; font-size: 14px; }}
        .trend-up {{ color: green; }}
        .trend-down {{ color: red; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background: #f5f5f5; }}
        .alert {{ background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Performance Report</h1>
        <p><strong>Period:</strong> {report.period_start.strftime('%Y-%m-%d')} to {report.period_end.strftime('%Y-%m-%d')}</p>
        {"<p><strong>Team:</strong> " + report.team_name + "</p>" if report.team_name else ""}
    </div>

    <h2>Key Metrics</h2>
    <div class="metrics">
        <div class="metric-card">
            <div class="metric-value">{summary.mttr_minutes:.0f if summary.mttr_minutes else 'N/A'}</div>
            <div class="metric-label">MTTR (min)</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary.mtta_minutes:.0f if summary.mtta_minutes else 'N/A'}</div>
            <div class="metric-label">MTTA (min)</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary.total_incidents}</div>
            <div class="metric-label">Total Incidents</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary.sla_compliance_percent:.1f if summary.sla_compliance_percent else 'N/A'}%</div>
            <div class="metric-label">SLA Compliance</div>
        </div>
    </div>

    <h2>Key Insights</h2>
    <ul>
        {"".join(f"<li>{insight}</li>" for insight in summary.key_insights) if summary.key_insights else "<li>No insights available</li>"}
    </ul>

    <h2>Top Responders</h2>
    <table>
        <tr><th>Rank</th><th>Name</th><th>Incidents</th><th>Avg Ack Time</th><th>Score</th></tr>
        {"".join(
            f"<tr><td>{i}</td><td>{r.responder_name}</td><td>{r.incidents_handled}</td>"
            f"<td>{r.avg_ack_time_minutes:.1f if r.avg_ack_time_minutes else 'N/A'} min</td><td>{r.total_score}</td></tr>"
            for i, r in enumerate(report.top_responders, 1)
        )}
    </table>

    <p><em>Generated at {report.generated_at.isoformat()}</em></p>
</body>
</html>
"""
        return html

    def _trend_icon(
        self, direction: TrendDirection | None, invert: bool = False
    ) -> str:
        """Get trend icon for a direction."""
        if direction is None:
            return "➡️"
        if direction == TrendDirection.IMPROVING:
            return "⬇️" if not invert else "⬆️"
        elif direction == TrendDirection.DECLINING:
            return "⬆️" if not invert else "⬇️"
        return "➡️"
