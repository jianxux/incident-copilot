"""Cost report generation for incident cost tracking.

This module provides report generation capabilities including
team summaries, service summaries, trends, and export functionality.
"""

import csv
import io
import json
from datetime import datetime, timedelta
from decimal import Decimal

import structlog

from .calculator import CostCalculator
from .factors import CostFactorConfig, get_cost_config
from .models import (
    CostCategory,
    CostReport,
    GenerateReportRequest,
    IncidentCost,
    ReportPeriod,
    ROIAnalysis,
    ServiceCostSummary,
    TeamCostSummary,
)

logger = structlog.get_logger()


class CostStore:
    """In-memory store for incident costs (replace with database in production)."""

    def __init__(self):
        self._costs: dict[str, IncidentCost] = {}

    async def save(self, cost: IncidentCost) -> IncidentCost:
        """Save an incident cost record."""
        self._costs[cost.incident_id] = cost
        return cost

    async def get(self, incident_id: str) -> IncidentCost | None:
        """Get an incident cost by incident ID."""
        return self._costs.get(incident_id)

    async def get_by_cost_id(self, cost_id: str) -> IncidentCost | None:
        """Get an incident cost by cost ID."""
        for cost in self._costs.values():
            if cost.cost_id == cost_id:
                return cost
        return None

    async def list(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        service_name: str | None = None,
        team: str | None = None,
        severity: str | None = None,
        is_finalized: bool | None = None,
        limit: int = 100,
    ) -> list[IncidentCost]:
        """List incident costs with filters."""
        results = []
        for cost in self._costs.values():
            # Date filter
            if start_date and cost.incident_started_at < start_date:
                continue
            if end_date and cost.incident_started_at > end_date:
                continue

            # Service filter
            if service_name and cost.service_name != service_name:
                continue

            # Team filter (check responders)
            if team:
                teams = {r.team for r in cost.responder_costs if r.team}
                if team not in teams:
                    continue

            # Severity filter
            if severity and cost.severity != severity:
                continue

            # Finalized filter
            if is_finalized is not None and cost.is_finalized != is_finalized:
                continue

            results.append(cost)

        # Sort by date descending and limit
        results.sort(key=lambda x: x.incident_started_at, reverse=True)
        return results[:limit]

    async def delete(self, incident_id: str) -> bool:
        """Delete an incident cost record."""
        if incident_id in self._costs:
            del self._costs[incident_id]
            return True
        return False

    async def clear(self):
        """Clear all costs (for testing)."""
        self._costs.clear()


# Global store instance
cost_store = CostStore()


class CostReportGenerator:
    """Generator for incident cost reports."""

    def __init__(
        self,
        store: CostStore | None = None,
        calculator: CostCalculator | None = None,
        config: CostFactorConfig | None = None,
    ):
        """Initialize the report generator.

        Args:
            store: Cost store instance.
            calculator: Cost calculator instance.
            config: Cost factor configuration.
        """
        self.store = store or cost_store
        self.config = config or get_cost_config()
        self.calculator = calculator or CostCalculator(self.config)

    async def generate_report(
        self,
        request: GenerateReportRequest,
    ) -> CostReport:
        """Generate a cost report for the specified period.

        Args:
            request: Report generation request with filters.

        Returns:
            Complete cost report.
        """
        # Determine period boundaries
        period_start, period_end = self._get_period_boundaries(
            request.period,
            request.period_start,
            request.period_end,
        )

        logger.info(
            "generating_cost_report",
            period=request.period.value,
            start=period_start.isoformat(),
            end=period_end.isoformat(),
        )

        # Fetch incidents for the period
        incidents = await self.store.list(
            start_date=period_start,
            end_date=period_end,
            limit=10000,  # Get all for report
        )

        # Filter by services/teams if specified
        if request.services:
            incidents = [
                i for i in incidents if i.service_name in request.services
            ]
        if request.teams:
            incidents = [
                i for i in incidents
                if any(r.team in request.teams for r in i.responder_costs if r.team)
            ]

        # Build the report
        report = CostReport(
            report_id=f"REPORT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            title=self._generate_report_title(request.period, period_start),
            period=request.period,
            period_start=period_start,
            period_end=period_end,
            total_incidents=len(incidents),
            currency=self.config.currency,
        )

        if incidents:
            # Calculate totals
            report.total_cost = sum(i.total_cost for i in incidents)
            report.average_cost_per_incident = (
                report.total_cost / report.total_incidents
            )

            # Cost by category
            report.cost_by_category = self._calculate_cost_by_category(incidents)

            # Cost by severity
            report.cost_by_severity, report.incidents_by_severity = (
                self._calculate_cost_by_severity(incidents)
            )

            # Team summaries
            report.team_summaries = self._calculate_team_summaries(incidents)

            # Service summaries
            report.service_summaries = self._calculate_service_summaries(incidents)

            # Top costly incidents
            sorted_by_cost = sorted(
                incidents,
                key=lambda x: x.total_cost,
                reverse=True,
            )
            report.top_incidents = sorted_by_cost[: request.top_incidents_limit]

            # SLA summary
            for incident in incidents:
                for penalty in incident.sla_penalties:
                    report.sla_breach_count += 1
                    if penalty.is_waived:
                        report.sla_penalties_waived += penalty.penalty_amount
                    else:
                        report.total_sla_penalties += penalty.penalty_amount

            # Cost trends
            report.cost_trend = self._calculate_cost_trend(
                incidents, period_start, period_end
            )
            report.mttr_trend = self._calculate_mttr_trend(
                incidents, period_start, period_end
            )

            # ROI analysis
            if request.include_roi:
                report.roi_analysis = await self.calculator.calculate_roi_analysis(
                    incidents=incidents,
                    period_start=period_start,
                    period_end=period_end,
                )

            # Compare with previous period
            if request.compare_previous:
                await self._add_period_comparison(report, request.period)

        logger.info(
            "cost_report_generated",
            report_id=report.report_id,
            total_incidents=report.total_incidents,
            total_cost=str(report.total_cost),
        )

        return report

    def _get_period_boundaries(
        self,
        period: ReportPeriod,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime, datetime]:
        """Get the start and end dates for a report period."""
        now = datetime.utcnow()

        if period == ReportPeriod.CUSTOM and start and end:
            return start, end

        if period == ReportPeriod.DAILY:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == ReportPeriod.WEEKLY:
            # Start from Monday
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7)
        elif period == ReportPeriod.MONTHLY:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # End at start of next month
            if now.month == 12:
                end = start.replace(year=now.year + 1, month=1)
            else:
                end = start.replace(month=now.month + 1)
        elif period == ReportPeriod.QUARTERLY:
            quarter = (now.month - 1) // 3
            start_month = quarter * 3 + 1
            start = now.replace(
                month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            end_month = start_month + 3
            if end_month > 12:
                end = start.replace(year=now.year + 1, month=end_month - 12)
            else:
                end = start.replace(month=end_month)
        elif period == ReportPeriod.YEARLY:
            start = now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            end = start.replace(year=now.year + 1)
        else:
            # Default to current month
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now

        return start, end

    def _generate_report_title(
        self,
        period: ReportPeriod,
        start: datetime,
    ) -> str:
        """Generate a report title based on period."""
        if period == ReportPeriod.DAILY:
            return f"Daily Cost Report - {start.strftime('%Y-%m-%d')}"
        elif period == ReportPeriod.WEEKLY:
            return f"Weekly Cost Report - Week of {start.strftime('%Y-%m-%d')}"
        elif period == ReportPeriod.MONTHLY:
            return f"Monthly Cost Report - {start.strftime('%B %Y')}"
        elif period == ReportPeriod.QUARTERLY:
            quarter = (start.month - 1) // 3 + 1
            return f"Q{quarter} {start.year} Cost Report"
        elif period == ReportPeriod.YEARLY:
            return f"Annual Cost Report - {start.year}"
        else:
            return f"Cost Report - {start.strftime('%Y-%m-%d')}"

    def _calculate_cost_by_category(
        self,
        incidents: list[IncidentCost],
    ) -> dict[str, Decimal]:
        """Calculate total cost by category."""
        totals: dict[str, Decimal] = {cat.value: Decimal("0") for cat in CostCategory}

        for incident in incidents:
            # Add engineer costs
            totals[CostCategory.ENGINEER_TIME.value] += incident.total_engineer_cost

            # Add breakdown costs
            for breakdown in incident.cost_breakdown:
                totals[breakdown.category.value] += breakdown.amount

            # Add SLA penalties
            totals[CostCategory.SLA_PENALTY.value] += incident.total_sla_penalties

        return totals

    def _calculate_cost_by_severity(
        self,
        incidents: list[IncidentCost],
    ) -> tuple[dict[str, Decimal], dict[str, int]]:
        """Calculate cost and count by severity."""
        cost_by_severity: dict[str, Decimal] = {}
        count_by_severity: dict[str, int] = {}

        for incident in incidents:
            severity = incident.severity
            cost_by_severity[severity] = (
                cost_by_severity.get(severity, Decimal("0")) + incident.total_cost
            )
            count_by_severity[severity] = count_by_severity.get(severity, 0) + 1

        return cost_by_severity, count_by_severity

    def _calculate_team_summaries(
        self,
        incidents: list[IncidentCost],
    ) -> list[TeamCostSummary]:
        """Calculate cost summaries by team."""
        team_data: dict[str, dict] = {}

        for incident in incidents:
            for responder in incident.responder_costs:
                team = responder.team or "Unknown"

                if team not in team_data:
                    team_data[team] = {
                        "incident_ids": set(),
                        "total_cost": Decimal("0"),
                        "total_time": 0,
                        "responders": {},
                    }

                team_data[team]["incident_ids"].add(incident.incident_id)
                team_data[team]["total_cost"] += responder.total_cost
                team_data[team]["total_time"] += responder.time_spent_minutes

                # Track responder stats
                responder_key = responder.responder_name
                if responder_key not in team_data[team]["responders"]:
                    team_data[team]["responders"][responder_key] = {
                        "cost": Decimal("0"),
                        "incident_count": 0,
                    }
                team_data[team]["responders"][responder_key]["cost"] += (
                    responder.total_cost
                )
                team_data[team]["responders"][responder_key]["incident_count"] += 1

        summaries = []
        for team_name, data in team_data.items():
            incident_count = len(data["incident_ids"])
            top_responders = sorted(
                [
                    {
                        "name": name,
                        "cost": float(stats["cost"]),
                        "incident_count": stats["incident_count"],
                    }
                    for name, stats in data["responders"].items()
                ],
                key=lambda x: x["cost"],
                reverse=True,
            )[:5]

            summaries.append(
                TeamCostSummary(
                    team_name=team_name,
                    incident_count=incident_count,
                    total_response_time_minutes=data["total_time"],
                    total_cost=data["total_cost"],
                    average_cost_per_incident=(
                        data["total_cost"] / incident_count if incident_count else Decimal("0")
                    ),
                    responder_count=len(data["responders"]),
                    top_responders=top_responders,
                )
            )

        return sorted(summaries, key=lambda x: x.total_cost, reverse=True)

    def _calculate_service_summaries(
        self,
        incidents: list[IncidentCost],
    ) -> list[ServiceCostSummary]:
        """Calculate cost summaries by service."""
        service_data: dict[str, dict] = {}

        for incident in incidents:
            service = incident.service_name

            if service not in service_data:
                service_data[service] = {
                    "incident_count": 0,
                    "total_cost": Decimal("0"),
                    "total_revenue_impact": Decimal("0"),
                    "total_sla_penalties": Decimal("0"),
                    "cost_by_severity": {},
                    "total_mttr": 0,
                }

            service_data[service]["incident_count"] += 1
            service_data[service]["total_cost"] += incident.total_cost
            service_data[service]["total_revenue_impact"] += incident.total_revenue_impact
            service_data[service]["total_sla_penalties"] += incident.total_sla_penalties
            service_data[service]["total_mttr"] += incident.duration_minutes

            severity = incident.severity
            service_data[service]["cost_by_severity"][severity] = (
                service_data[service]["cost_by_severity"].get(severity, Decimal("0"))
                + incident.total_cost
            )

        summaries = []
        for service_name, data in service_data.items():
            count = data["incident_count"]
            summaries.append(
                ServiceCostSummary(
                    service_name=service_name,
                    incident_count=count,
                    total_cost=data["total_cost"],
                    total_revenue_impact=data["total_revenue_impact"],
                    total_sla_penalties=data["total_sla_penalties"],
                    average_cost_per_incident=(
                        data["total_cost"] / count if count else Decimal("0")
                    ),
                    cost_by_severity=data["cost_by_severity"],
                    mttr_minutes=(data["total_mttr"] / count if count else 0),
                )
            )

        return sorted(summaries, key=lambda x: x.total_cost, reverse=True)

    def _calculate_cost_trend(
        self,
        incidents: list[IncidentCost],
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """Calculate daily cost trend."""
        daily_costs: dict[str, Decimal] = {}

        for incident in incidents:
            date_key = incident.incident_started_at.strftime("%Y-%m-%d")
            daily_costs[date_key] = (
                daily_costs.get(date_key, Decimal("0")) + incident.total_cost
            )

        # Fill in missing days with zero
        current = start
        trend = []
        while current < end:
            date_key = current.strftime("%Y-%m-%d")
            trend.append({
                "date": date_key,
                "cost": float(daily_costs.get(date_key, Decimal("0"))),
            })
            current += timedelta(days=1)

        return trend

    def _calculate_mttr_trend(
        self,
        incidents: list[IncidentCost],
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        """Calculate daily MTTR trend."""
        daily_mttr: dict[str, list[int]] = {}

        for incident in incidents:
            date_key = incident.incident_started_at.strftime("%Y-%m-%d")
            if date_key not in daily_mttr:
                daily_mttr[date_key] = []
            if incident.duration_minutes > 0:
                daily_mttr[date_key].append(incident.duration_minutes)

        trend = []
        current = start
        while current < end:
            date_key = current.strftime("%Y-%m-%d")
            mttrs = daily_mttr.get(date_key, [])
            avg_mttr = sum(mttrs) / len(mttrs) if mttrs else 0
            trend.append({
                "date": date_key,
                "mttr_minutes": avg_mttr,
            })
            current += timedelta(days=1)

        return trend

    async def _add_period_comparison(
        self,
        report: CostReport,
        period: ReportPeriod,
    ) -> None:
        """Add comparison with previous period."""
        # Calculate previous period boundaries
        duration = report.period_end - report.period_start
        prev_start = report.period_start - duration
        prev_end = report.period_start

        # Fetch previous period incidents
        prev_incidents = await self.store.list(
            start_date=prev_start,
            end_date=prev_end,
            limit=10000,
        )

        if prev_incidents:
            report.previous_period_cost = sum(i.total_cost for i in prev_incidents)
            if report.previous_period_cost > 0:
                report.cost_change_percent = float(
                    ((report.total_cost - report.previous_period_cost)
                     / report.previous_period_cost)
                    * 100
                )

    async def export_to_csv(self, report: CostReport) -> str:
        """Export a cost report to CSV format.

        Args:
            report: The cost report to export.

        Returns:
            CSV string of the report.
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Summary section
        writer.writerow(["Cost Report Summary"])
        writer.writerow(["Report ID", report.report_id])
        writer.writerow(["Period", f"{report.period_start} to {report.period_end}"])
        writer.writerow(["Total Incidents", report.total_incidents])
        writer.writerow(["Total Cost", f"{report.currency} {report.total_cost}"])
        writer.writerow(["Average Cost per Incident", f"{report.currency} {report.average_cost_per_incident}"])
        writer.writerow([])

        # Cost by category
        writer.writerow(["Cost by Category"])
        writer.writerow(["Category", "Amount"])
        for category, amount in report.cost_by_category.items():
            writer.writerow([category, f"{report.currency} {amount}"])
        writer.writerow([])

        # Cost by severity
        writer.writerow(["Cost by Severity"])
        writer.writerow(["Severity", "Incidents", "Total Cost"])
        for severity, cost in report.cost_by_severity.items():
            count = report.incidents_by_severity.get(severity, 0)
            writer.writerow([severity, count, f"{report.currency} {cost}"])
        writer.writerow([])

        # Service summaries
        writer.writerow(["Service Summary"])
        writer.writerow([
            "Service",
            "Incidents",
            "Total Cost",
            "Revenue Impact",
            "SLA Penalties",
            "Avg MTTR (min)",
        ])
        for service in report.service_summaries:
            writer.writerow([
                service.service_name,
                service.incident_count,
                f"{report.currency} {service.total_cost}",
                f"{report.currency} {service.total_revenue_impact}",
                f"{report.currency} {service.total_sla_penalties}",
                f"{service.mttr_minutes:.1f}",
            ])
        writer.writerow([])

        # Team summaries
        writer.writerow(["Team Summary"])
        writer.writerow([
            "Team",
            "Incidents",
            "Responders",
            "Total Time (min)",
            "Total Cost",
        ])
        for team in report.team_summaries:
            writer.writerow([
                team.team_name,
                team.incident_count,
                team.responder_count,
                team.total_response_time_minutes,
                f"{report.currency} {team.total_cost}",
            ])

        return output.getvalue()

    async def export_to_json(
        self,
        report: CostReport,
        include_details: bool = True,
    ) -> str:
        """Export a cost report to JSON format.

        Args:
            report: The cost report to export.
            include_details: Whether to include full incident details.

        Returns:
            JSON string of the report.
        """
        data = report.model_dump(mode="json")

        if not include_details:
            # Remove detailed incident data for summary export
            data.pop("top_incidents", None)
            data.pop("cost_trend", None)
            data.pop("mttr_trend", None)

        return json.dumps(data, indent=2, default=str)

    async def export_for_finance(
        self,
        report: CostReport,
    ) -> dict:
        """Export report data formatted for finance systems.

        Args:
            report: The cost report to export.

        Returns:
            Dict formatted for finance system integration.
        """
        return {
            "report_type": "incident_cost",
            "report_id": report.report_id,
            "period": {
                "start": report.period_start.isoformat(),
                "end": report.period_end.isoformat(),
                "type": report.period.value,
            },
            "currency": report.currency,
            "summary": {
                "total_incidents": report.total_incidents,
                "total_cost": float(report.total_cost),
                "average_cost": float(report.average_cost_per_incident),
            },
            "cost_breakdown": {
                cat: float(amount)
                for cat, amount in report.cost_by_category.items()
            },
            "department_allocation": [
                {
                    "department": team.team_name,
                    "cost": float(team.total_cost),
                    "incident_count": team.incident_count,
                    "labor_hours": team.total_response_time_minutes / 60,
                }
                for team in report.team_summaries
            ],
            "service_cost_centers": [
                {
                    "service": service.service_name,
                    "cost": float(service.total_cost),
                    "revenue_impact": float(service.total_revenue_impact),
                    "penalties": float(service.total_sla_penalties),
                }
                for service in report.service_summaries
            ],
            "sla_penalties": {
                "total": float(report.total_sla_penalties),
                "breach_count": report.sla_breach_count,
                "waived": float(report.sla_penalties_waived),
            },
            "roi": (
                {
                    "total_savings": float(report.roi_analysis.total_savings),
                    "roi_percentage": report.roi_analysis.roi_percentage,
                    "engineer_hours_saved": report.roi_analysis.engineer_hours_saved,
                }
                if report.roi_analysis
                else None
            ),
            "generated_at": report.generated_at.isoformat(),
        }
