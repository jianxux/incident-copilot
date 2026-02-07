"""Cost calculation and analysis service."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from .calculator import CostCalculatorFactory
from .models import (
    CostCategory,
    CostEntry,
    CostReport,
    CostTrend,
    Currency,
    EngineerRate,
    IncidentCost,
    ROIAnalysis,
    ServiceCriticality,
    ServiceRevenueConfig,
    SLAConfig,
    TeamCostAllocation,
)
from .store import CostStore, InMemoryCostStore


class CostService:
    """Service for calculating and managing incident costs."""

    def __init__(self, store: CostStore | None = None):
        self.store: CostStore = store or InMemoryCostStore()
        self.factory = CostCalculatorFactory()

    # Configuration management
    async def configure_engineer_rate(self, rate: EngineerRate) -> str:
        """Register an engineer rate configuration."""
        self.factory.register_engineer_rate(rate)
        return await self.store.save_engineer_rate(rate)

    async def configure_service(self, config: ServiceRevenueConfig) -> str:
        """Register a service revenue configuration."""
        self.factory.register_service_config(config)
        return await self.store.save_service_config(config)

    async def configure_sla(self, config: SLAConfig) -> str:
        """Register an SLA configuration."""
        self.factory.register_sla_config(config)
        return await self.store.save_sla_config(config)

    # Cost entry operations
    async def add_cost_entry(self, entry: CostEntry) -> str:
        """Add a manual cost entry."""
        return await self.store.save_entry(entry)

    async def get_cost_entry(self, entry_id: str) -> CostEntry | None:
        """Get a cost entry by ID."""
        return await self.store.get_entry(entry_id)

    async def delete_cost_entry(self, entry_id: str) -> bool:
        """Delete a cost entry."""
        return await self.store.delete_entry(entry_id)

    # Calculators
    async def calculate_engineer_time(
        self,
        incident_id: str,
        hours: float,
        engineer_id: str | None = None,
        engineer_name: str | None = None,
        team: str | None = None,
        department: str | None = None,
        level: str | None = None,
        save: bool = True,
    ) -> CostEntry:
        """Calculate and optionally save engineer time cost."""
        calc = self.factory.engineer_time()
        entry = await calc.calculate(
            incident_id=incident_id,
            hours=hours,
            engineer_id=engineer_id,
            engineer_name=engineer_name,
            team=team,
            department=department,
            level=level,
        )
        if save:
            await self.store.save_entry(entry)
        return entry

    async def calculate_revenue_impact(
        self,
        incident_id: str,
        service_name: str,
        duration_hours: float,
        criticality: ServiceCriticality | None = None,
        partial_outage_pct: float = 100.0,
        save: bool = True,
    ) -> CostEntry:
        """Calculate and optionally save revenue impact."""
        calc = self.factory.revenue_impact()
        entry = await calc.calculate(
            incident_id=incident_id,
            service_name=service_name,
            duration_hours=duration_hours,
            criticality=criticality,
            partial_outage_pct=partial_outage_pct,
        )
        if save:
            await self.store.save_entry(entry)
        return entry

    async def calculate_cloud_cost(
        self,
        incident_id: str,
        resource_type: str,
        quantity: float = 1.0,
        hours: float = 1.0,
        unit_cost: Decimal | None = None,
        save: bool = True,
    ) -> CostEntry:
        """Calculate and optionally save cloud resource cost."""
        calc = self.factory.cloud_cost()
        entry = await calc.calculate(
            incident_id=incident_id,
            resource_type=resource_type,
            quantity=quantity,
            hours=hours,
            unit_cost=unit_cost,
        )
        if save:
            await self.store.save_entry(entry)
        return entry

    async def calculate_sla_penalty(
        self,
        incident_id: str,
        customer_id: str,
        downtime_minutes: float,
        period_days: int = 30,
        save: bool = True,
    ) -> CostEntry | None:
        """Calculate and optionally save SLA penalty."""
        calc = self.factory.sla_penalty()
        entry = await calc.calculate(
            incident_id=incident_id,
            customer_id=customer_id,
            downtime_minutes=downtime_minutes,
            period_days=period_days,
        )
        if entry and save:
            await self.store.save_entry(entry)
        return entry

    async def calculate_customer_impact(
        self,
        incident_id: str,
        impact_type: str,
        count: int = 1,
        custom_cost: Decimal | None = None,
        save: bool = True,
    ) -> CostEntry:
        """Calculate and optionally save customer impact cost."""
        calc = self.factory.customer_impact()
        entry = await calc.calculate(
            incident_id=incident_id,
            impact_type=impact_type,
            count=count,
            custom_cost=custom_cost,
        )
        if save:
            await self.store.save_entry(entry)
        return entry

    # Incident cost aggregation
    async def get_incident_cost(self, incident_id: str) -> IncidentCost | None:
        """Get aggregated cost for an incident."""
        # Try cached version first
        cached = await self.store.get_incident_cost(incident_id)
        if cached:
            return cached

        # Calculate from entries
        entries = await self.store.get_entries_for_incident(incident_id)
        if not entries:
            return None

        return await self._aggregate_incident_cost(incident_id, entries)

    async def calculate_incident_cost(
        self,
        incident_id: str,
        incident_title: str | None = None,
        service_name: str | None = None,
        severity: str | None = None,
        started_at: datetime | None = None,
        resolved_at: datetime | None = None,
    ) -> IncidentCost:
        """Calculate total cost for an incident from stored entries."""
        entries = await self.store.get_entries_for_incident(incident_id)

        cost = IncidentCost(
            incident_id=incident_id,
            incident_title=incident_title,
            service_name=service_name,
            severity=severity,
            started_at=started_at,
            resolved_at=resolved_at,
        )

        for entry in entries:
            cost.add_entry(entry)

        await self.store.save_incident_cost(cost)
        return cost

    async def _aggregate_incident_cost(
        self,
        incident_id: str,
        entries: list[CostEntry],
    ) -> IncidentCost:
        """Aggregate entries into incident cost."""
        cost = IncidentCost(incident_id=incident_id)
        for entry in entries:
            cost.add_entry(entry)
        return cost

    # Trend analysis
    async def get_cost_trend(
        self,
        period: str = "30d",
        end_date: datetime | None = None,
    ) -> CostTrend:
        """Get cost trend for a period."""
        end = end_date or datetime.utcnow()
        days = int(period.rstrip("d"))
        start = end - timedelta(days=days)
        prev_start = start - timedelta(days=days)

        # Current period
        current_entries = await self.store.get_entries_by_date_range(start, end)
        current_costs = await self.store.get_all_incident_costs(start, end)

        # Previous period
        prev_entries = await self.store.get_entries_by_date_range(prev_start, start)

        # Calculate totals
        current_total = sum(e.amount_usd for e in current_entries)
        prev_total = sum(e.amount_usd for e in prev_entries)

        # By category
        by_category: dict[CostCategory, Decimal] = {}
        for entry in current_entries:
            by_category[entry.category] = (
                by_category.get(entry.category, Decimal("0")) + entry.amount_usd
            )

        # By team
        by_team: dict[str, Decimal] = {}
        for entry in current_entries:
            if entry.team:
                by_team[entry.team] = by_team.get(entry.team, Decimal("0")) + entry.amount_usd

        # By department
        by_department: dict[str, Decimal] = {}
        for entry in current_entries:
            if entry.department:
                by_department[entry.department] = (
                    by_department.get(entry.department, Decimal("0")) + entry.amount_usd
                )

        # Calculate change
        change_pct = None
        trend = "stable"
        if prev_total > 0:
            change_pct = float((current_total - prev_total) / prev_total * 100)
            if change_pct > 10:
                trend = "degrading"
            elif change_pct < -10:
                trend = "improving"

        incident_count = (
            len(current_costs)
            if current_costs
            else len(set(e.incident_id for e in current_entries))
        )
        avg_cost = current_total / Decimal(str(max(1, incident_count)))

        return CostTrend(
            period=period,
            start_date=start,
            end_date=end,
            total_cost=current_total,
            incident_count=incident_count,
            average_cost_per_incident=avg_cost,
            by_category=by_category,
            by_team=by_team,
            by_department=by_department,
            previous_total=prev_total if prev_total else None,
            change_pct=change_pct,
            trend=trend,
        )

    # Report generation
    async def generate_report(
        self,
        period: str = "30d",
        title: str | None = None,
        end_date: datetime | None = None,
    ) -> CostReport:
        """Generate a comprehensive cost report."""
        end = end_date or datetime.utcnow()
        days = int(period.rstrip("d"))
        start = end - timedelta(days=days)

        entries = await self.store.get_entries_by_date_range(start, end)
        incident_costs = await self.store.get_all_incident_costs(start, end)

        # Calculate totals
        total_cost = sum(e.amount_usd for e in entries)
        incident_count = (
            len(incident_costs) if incident_costs else len(set(e.incident_id for e in entries))
        )
        avg_cost = total_cost / Decimal(str(max(1, incident_count)))

        # By category
        by_category: dict[CostCategory, Decimal] = {}
        for entry in entries:
            by_category[entry.category] = (
                by_category.get(entry.category, Decimal("0")) + entry.amount_usd
            )

        # By severity (from incident costs)
        by_severity: dict[str, Decimal] = {}
        for cost in incident_costs:
            if cost.severity:
                by_severity[cost.severity] = (
                    by_severity.get(cost.severity, Decimal("0")) + cost.total_cost
                )

        # By service
        by_service: dict[str, Decimal] = {}
        for cost in incident_costs:
            if cost.service_name:
                by_service[cost.service_name] = (
                    by_service.get(cost.service_name, Decimal("0")) + cost.total_cost
                )

        # By team
        by_team: dict[str, Decimal] = {}
        for entry in entries:
            if entry.team:
                by_team[entry.team] = by_team.get(entry.team, Decimal("0")) + entry.amount_usd

        # By department
        by_department: dict[str, Decimal] = {}
        for entry in entries:
            if entry.department:
                by_department[entry.department] = (
                    by_department.get(entry.department, Decimal("0")) + entry.amount_usd
                )

        # Top incidents
        sorted_costs = sorted(incident_costs, key=lambda c: c.total_cost, reverse=True)
        top_incidents = sorted_costs[:10]
        max_cost_incident = sorted_costs[0] if sorted_costs else None

        # Get trend
        trend = await self.get_cost_trend(period, end)

        # Daily costs
        daily_costs: list[tuple[str, Decimal]] = []
        for day_offset in range(days):
            day = start + timedelta(days=day_offset)
            day_end = day + timedelta(days=1)
            day_entries = [e for e in entries if day <= e.created_at < day_end]
            day_total = sum(e.amount_usd for e in day_entries)
            daily_costs.append((day.strftime("%Y-%m-%d"), day_total))

        report = CostReport(
            report_id=str(uuid.uuid4()),
            title=title or f"Cost Report: {period}",
            period=period,
            start_date=start,
            end_date=end,
            total_cost=total_cost,
            incident_count=incident_count,
            avg_cost_per_incident=avg_cost,
            max_cost_incident=max_cost_incident,
            by_category=by_category,
            by_severity=by_severity,
            by_service=by_service,
            by_team=by_team,
            by_department=by_department,
            trend=trend,
            daily_costs=daily_costs,
            top_incidents=top_incidents,
        )

        await self.store.save_report(report)
        return report

    # ROI Analysis
    async def calculate_roi(
        self,
        title: str,
        period: str,
        prevention_investment: Decimal,
        projected_incidents_prevented: int,
        investment_items: list[dict[str, Any]] | None = None,
        notes: str | None = None,
        end_date: datetime | None = None,
    ) -> ROIAnalysis:
        """Calculate ROI for prevention investment."""
        end = end_date or datetime.utcnow()
        days = int(period.rstrip("d"))
        start = end - timedelta(days=days)

        # Get incident costs for the period
        incident_costs = await self.store.get_all_incident_costs(start, end)
        total_incident_cost = sum(c.total_cost for c in incident_costs)
        incident_count = len(incident_costs)

        # Calculate average cost per incident
        avg_cost = (
            total_incident_cost / Decimal(str(max(1, incident_count)))
            if incident_count > 0
            else Decimal("0")
        )

        # Projected savings
        projected_savings = avg_cost * Decimal(str(projected_incidents_prevented))

        # ROI calculation
        net_benefit = projected_savings - prevention_investment
        roi_pct = None
        payback_months = None

        if prevention_investment > 0:
            roi_pct = float(
                (projected_savings - prevention_investment) / prevention_investment * 100
            )
            if projected_savings > 0:
                payback_months = float(
                    prevention_investment / (projected_savings / Decimal(str(days / 30)))
                )

        analysis = ROIAnalysis(
            analysis_id=str(uuid.uuid4()),
            title=title,
            period=period,
            start_date=start,
            end_date=end,
            total_incident_cost=total_incident_cost,
            incident_count=incident_count,
            prevention_investment=prevention_investment,
            investment_items=investment_items or [],
            projected_incidents_prevented=projected_incidents_prevented,
            projected_savings=projected_savings,
            roi_pct=roi_pct,
            payback_period_months=payback_months,
            net_benefit=net_benefit,
            notes=notes,
        )

        await self.store.save_roi_analysis(analysis)
        return analysis

    # Team allocation
    async def calculate_team_allocation(
        self,
        team: str,
        period: str,
        end_date: datetime | None = None,
    ) -> TeamCostAllocation:
        """Calculate cost allocation for a team."""
        end = end_date or datetime.utcnow()
        days = int(period.rstrip("d"))
        start = end - timedelta(days=days)
        prev_start = start - timedelta(days=days)

        # Get entries for this team
        entries = await self.store.get_entries_by_team(team, start, end)
        prev_entries = await self.store.get_entries_by_team(team, prev_start, start)

        # Separate direct vs support costs
        direct_costs = Decimal("0")
        support_costs = Decimal("0")
        by_category: dict[CostCategory, Decimal] = {}
        incidents: list[str] = []

        for entry in entries:
            if entry.incident_id not in incidents:
                incidents.append(entry.incident_id)

            # If the incident is for this team's service, it's direct cost
            # Otherwise it's support cost (helping another team)
            # This is simplified; in practice you'd check service ownership
            if entry.team == team:
                direct_costs += entry.amount_usd
            else:
                support_costs += entry.amount_usd

            by_category[entry.category] = (
                by_category.get(entry.category, Decimal("0")) + entry.amount_usd
            )

        total_costs = direct_costs + support_costs
        prev_total = sum(e.amount_usd for e in prev_entries)

        change_pct = None
        if prev_total > 0:
            change_pct = float((total_costs - prev_total) / prev_total * 100)

        # Get department from first entry
        department = entries[0].department if entries else None

        allocation = TeamCostAllocation(
            team=team,
            department=department,
            period=period,
            start_date=start,
            end_date=end,
            direct_costs=direct_costs,
            support_costs=support_costs,
            total_costs=total_costs,
            by_category=by_category,
            incidents=incidents,
            previous_period_cost=prev_total if prev_total else None,
            change_pct=change_pct,
        )

        await self.store.save_team_allocation(allocation)
        return allocation

    # Comparison
    async def compare_periods(
        self,
        period1: str,
        period2: str,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Compare costs between two periods."""
        trend1 = await self.get_cost_trend(period1, end_date)

        # Calculate end date for period2
        days1 = int(period1.rstrip("d"))
        end2 = (end_date or datetime.utcnow()) - timedelta(days=days1)
        trend2 = await self.get_cost_trend(period2, end2)

        return {
            "period1": {
                "period": period1,
                "total_cost": trend1.total_cost,
                "incident_count": trend1.incident_count,
                "avg_cost": trend1.average_cost_per_incident,
            },
            "period2": {
                "period": period2,
                "total_cost": trend2.total_cost,
                "incident_count": trend2.incident_count,
                "avg_cost": trend2.average_cost_per_incident,
            },
            "comparison": {
                "cost_change": trend1.total_cost - trend2.total_cost,
                "cost_change_pct": float(
                    (trend1.total_cost - trend2.total_cost) / trend2.total_cost * 100
                )
                if trend2.total_cost
                else None,
                "incident_count_change": trend1.incident_count - trend2.incident_count,
            },
        }
