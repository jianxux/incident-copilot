"""Incident cost calculator.

This module provides the core cost calculation logic for incidents,
including engineer time, revenue impact, SLA penalties, and ROI analysis.
"""

from datetime import datetime
from decimal import Decimal

import structlog

from .factors import CostFactorConfig, get_cost_config
from .models import (
    CalculateCostRequest,
    CostBreakdown,
    CostCategory,
    IncidentCost,
    ResponderCost,
    ROIAnalysis,
    SLAPenalty,
)

logger = structlog.get_logger()


class CostCalculator:
    """Calculator for incident costs."""

    def __init__(self, config: CostFactorConfig | None = None):
        """Initialize the cost calculator.

        Args:
            config: Cost factor configuration. Uses default if not provided.
        """
        self.config = config or get_cost_config()

    async def calculate_incident_cost(
        self,
        request: CalculateCostRequest,
    ) -> IncidentCost:
        """Calculate the total cost of an incident.

        Args:
            request: Cost calculation request with incident details.

        Returns:
            Complete incident cost record with all breakdowns.
        """
        logger.info(
            "calculating_incident_cost",
            incident_id=request.incident_id,
            service=request.service_name,
            severity=request.severity,
        )

        # Calculate duration
        resolved_at = request.incident_resolved_at or datetime.utcnow()
        duration_minutes = int(
            (resolved_at - request.incident_started_at).total_seconds() / 60
        )

        # Create the incident cost record
        incident_cost = IncidentCost(
            incident_id=request.incident_id,
            service_name=request.service_name,
            severity=request.severity,
            incident_started_at=request.incident_started_at,
            incident_resolved_at=request.incident_resolved_at,
            duration_minutes=duration_minutes,
            affected_users=request.affected_users,
            affected_transactions=request.affected_transactions,
        )

        # Calculate responder costs
        incident_cost.responder_costs = await self._calculate_responder_costs(
            responders=request.responders,
            severity=request.severity,
            incident_started_at=request.incident_started_at,
        )

        # Calculate revenue impact
        revenue_impact = await self._calculate_revenue_impact(
            service_name=request.service_name,
            duration_minutes=duration_minutes,
            severity=request.severity,
            affected_users=request.affected_users,
            affected_transactions=request.affected_transactions,
        )
        if revenue_impact > 0:
            incident_cost.cost_breakdown.append(
                CostBreakdown(
                    category=CostCategory.REVENUE_IMPACT,
                    amount=revenue_impact,
                    description=f"Revenue impact from {duration_minutes}min outage",
                )
            )

        # Add custom costs from request
        for custom in request.custom_costs:
            category = CostCategory(custom.get("category", "other"))
            incident_cost.cost_breakdown.append(
                CostBreakdown(
                    category=category,
                    amount=Decimal(str(custom.get("amount", 0))),
                    description=custom.get("description"),
                )
            )

        # Calculate ROI savings (estimated)
        incident_cost = await self._calculate_roi_savings(incident_cost)

        # Calculate totals
        incident_cost.calculate_totals()

        logger.info(
            "incident_cost_calculated",
            incident_id=request.incident_id,
            total_cost=str(incident_cost.total_cost),
            engineer_cost=str(incident_cost.total_engineer_cost),
            revenue_impact=str(incident_cost.total_revenue_impact),
            duration_minutes=duration_minutes,
        )

        return incident_cost

    async def _calculate_responder_costs(
        self,
        responders: list[dict],
        severity: str,
        incident_started_at: datetime,
    ) -> list[ResponderCost]:
        """Calculate costs for each responder.

        Args:
            responders: List of responder info dicts.
            severity: Incident severity level.
            incident_started_at: When the incident started.

        Returns:
            List of responder cost records.
        """
        costs = []
        rates = self.config.hourly_rates

        # Check if incident started during off-hours
        is_weekend = incident_started_at.weekday() >= 5
        hour = incident_started_at.hour
        is_overtime = hour < 9 or hour >= 18  # Outside 9-6

        for responder in responders:
            role = responder.get("role")
            team = responder.get("team")
            time_minutes = responder.get("time_minutes", 0)

            # Get hourly rate for this responder
            hourly_rate = rates.get_rate(
                role=role,
                team=team,
                is_overtime=is_overtime,
                is_weekend=is_weekend,
            )

            # Apply severity multiplier
            severity_multipliers = {
                "critical": Decimal("1.5"),
                "high": Decimal("1.25"),
                "medium": Decimal("1.0"),
                "low": Decimal("0.75"),
            }
            multiplier = severity_multipliers.get(severity.lower(), Decimal("1.0"))
            adjusted_rate = hourly_rate * multiplier

            # Calculate total cost for this responder
            hours = Decimal(time_minutes) / Decimal("60")
            total_cost = (adjusted_rate * hours).quantize(Decimal("0.01"))

            costs.append(
                ResponderCost(
                    responder_id=responder.get("id", "unknown"),
                    responder_name=responder.get("name", "Unknown"),
                    team=team,
                    role=role,
                    hourly_rate=adjusted_rate,
                    time_spent_minutes=time_minutes,
                    total_cost=total_cost,
                    is_overtime=is_overtime or is_weekend,
                    overtime_multiplier=rates.overtime_multiplier if is_overtime else rates.weekend_multiplier if is_weekend else Decimal("1.0"),
                )
            )

        return costs

    async def _calculate_revenue_impact(
        self,
        service_name: str,
        duration_minutes: int,
        severity: str,
        affected_users: int = 0,
        affected_transactions: int = 0,
    ) -> Decimal:
        """Calculate revenue impact of an incident.

        Args:
            service_name: Name of the affected service.
            duration_minutes: Duration of the incident in minutes.
            severity: Incident severity level.
            affected_users: Number of affected users.
            affected_transactions: Number of affected transactions.

        Returns:
            Estimated revenue impact in dollars.
        """
        revenue_factors = self.config.revenue_factors

        return revenue_factors.get_revenue_impact(
            service_name=service_name,
            duration_minutes=duration_minutes,
            severity=severity,
            affected_users=affected_users,
            affected_transactions=affected_transactions,
        )

    async def add_sla_penalty(
        self,
        incident_cost: IncidentCost,
        sla_id: str,
        sla_name: str,
        breach_type: str,
        target_value: str,
        actual_value: str,
        customer_id: str | None = None,
        customer_name: str | None = None,
        customer_tier: str = "professional",
    ) -> IncidentCost:
        """Add an SLA penalty to an incident cost record.

        Args:
            incident_cost: The incident cost record to update.
            sla_id: Unique identifier for the SLA.
            sla_name: Name of the SLA.
            breach_type: Type of breach (uptime, response_time, resolution_time).
            target_value: The SLA target value.
            actual_value: The actual value achieved.
            customer_id: Optional customer ID.
            customer_name: Optional customer name.
            customer_tier: Customer tier for penalty calculation.

        Returns:
            Updated incident cost record with SLA penalty.
        """
        sla_factors = self.config.sla_factors

        # Calculate penalty based on breach type
        if breach_type == "uptime":
            penalty_amount = sla_factors.calculate_uptime_penalty(
                actual_uptime_percent=Decimal(actual_value.replace("%", "")),
                customer_tier=customer_tier,
            )
        elif breach_type == "resolution_time":
            # Parse actual value as hours
            actual_hours = float(actual_value.replace(" hours", "").replace("h", ""))
            penalty_amount = sla_factors.calculate_resolution_penalty(
                severity=incident_cost.severity,
                resolution_time_hours=actual_hours,
                customer_tier=customer_tier,
            )
        else:
            # Default penalty for other breach types
            penalty_amount = sla_factors.response_time_penalty

        penalty = SLAPenalty(
            sla_id=sla_id,
            sla_name=sla_name,
            customer_id=customer_id,
            customer_name=customer_name,
            breach_type=breach_type,
            target_value=target_value,
            actual_value=actual_value,
            penalty_amount=penalty_amount,
        )

        incident_cost.sla_penalties.append(penalty)
        incident_cost.calculate_totals()

        logger.info(
            "sla_penalty_added",
            incident_id=incident_cost.incident_id,
            sla_name=sla_name,
            breach_type=breach_type,
            penalty_amount=str(penalty_amount),
        )

        return incident_cost

    async def _calculate_roi_savings(
        self,
        incident_cost: IncidentCost,
    ) -> IncidentCost:
        """Calculate estimated ROI savings from faster resolution.

        Compares actual MTTR against baseline to estimate savings.

        Args:
            incident_cost: The incident cost record to update.

        Returns:
            Updated incident cost with ROI savings calculated.
        """
        baseline_mttr = self.config.baseline_mttr_minutes
        actual_mttr = incident_cost.duration_minutes

        if actual_mttr >= baseline_mttr:
            # No savings if we took longer than baseline
            return incident_cost

        # Time saved
        minutes_saved = baseline_mttr - actual_mttr

        # Calculate cost saved from engineer time
        engineer_hourly_rate = self.config.hourly_rates.default_rate
        hours_saved = Decimal(minutes_saved) / Decimal("60")
        engineer_savings = engineer_hourly_rate * hours_saved

        # Calculate revenue protected (additional downtime would cost more revenue)
        revenue_factors = self.config.revenue_factors
        revenue_protected = revenue_factors.get_revenue_impact(
            service_name=incident_cost.service_name,
            duration_minutes=minutes_saved,
            severity=incident_cost.severity,
        )

        incident_cost.baseline_mttr_minutes = baseline_mttr
        incident_cost.actual_mttr_minutes = actual_mttr
        incident_cost.estimated_savings = (engineer_savings + revenue_protected).quantize(
            Decimal("0.01")
        )

        logger.debug(
            "roi_savings_calculated",
            incident_id=incident_cost.incident_id,
            baseline_mttr=baseline_mttr,
            actual_mttr=actual_mttr,
            minutes_saved=minutes_saved,
            estimated_savings=str(incident_cost.estimated_savings),
        )

        return incident_cost

    async def calculate_roi_analysis(
        self,
        incidents: list[IncidentCost],
        period_start: datetime,
        period_end: datetime,
        investment_cost: Decimal | None = None,
    ) -> ROIAnalysis:
        """Calculate ROI analysis for a period.

        Args:
            incidents: List of incident costs for the period.
            period_start: Start of the analysis period.
            period_end: End of the analysis period.
            investment_cost: Cost of tooling/investment (uses default if not provided).

        Returns:
            Complete ROI analysis.
        """
        if not incidents:
            return ROIAnalysis(
                analysis_id=f"ROI-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                period_start=period_start,
                period_end=period_end,
            )

        # Calculate averages
        total_incidents = len(incidents)
        baseline_mttr = self.config.baseline_mttr_minutes
        actual_mttrs = [
            i.duration_minutes for i in incidents if i.duration_minutes > 0
        ]
        avg_actual_mttr = sum(actual_mttrs) / len(actual_mttrs) if actual_mttrs else 0

        # MTTR reduction
        mttr_reduction = 0.0
        if baseline_mttr > 0 and avg_actual_mttr < baseline_mttr:
            mttr_reduction = ((baseline_mttr - avg_actual_mttr) / baseline_mttr) * 100

        # Cost analysis
        total_cost = sum(i.total_cost for i in incidents)
        avg_cost = total_cost / total_incidents

        total_savings = sum(i.estimated_savings for i in incidents)
        total_revenue_protected = sum(
            i.estimated_savings - sum(r.total_cost for r in i.responder_costs)
            for i in incidents
            if i.estimated_savings > 0
        )

        # Engineer hours saved
        hours_saved = sum(
            (baseline_mttr - i.duration_minutes) / 60
            for i in incidents
            if i.duration_minutes < baseline_mttr
        )

        # Investment cost
        investment = investment_cost or self.config.tooling_monthly_cost
        months = max(
            1,
            (period_end - period_start).days / 30,
        )
        total_investment = investment * Decimal(str(months))

        # ROI calculation
        roi_percent = 0.0
        if total_investment > 0:
            roi_percent = float(
                ((total_savings - total_investment) / total_investment) * 100
            )

        # Payback period
        payback_months = None
        if total_savings > 0:
            monthly_savings = total_savings / Decimal(str(months))
            if monthly_savings > 0:
                payback_months = float(investment / monthly_savings)

        # Savings by service
        savings_by_service: dict[str, Decimal] = {}
        for incident in incidents:
            service = incident.service_name
            savings_by_service[service] = (
                savings_by_service.get(service, Decimal("0"))
                + incident.estimated_savings
            )

        analysis = ROIAnalysis(
            analysis_id=f"ROI-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            period_start=period_start,
            period_end=period_end,
            total_incidents=total_incidents,
            baseline_mttr_minutes=float(baseline_mttr),
            actual_mttr_minutes=avg_actual_mttr,
            mttr_reduction_percent=mttr_reduction,
            baseline_cost_per_incident=avg_cost,
            actual_cost_per_incident=avg_cost,
            total_savings=total_savings,
            revenue_protected=total_revenue_protected,
            investment_cost=total_investment,
            roi_percentage=roi_percent,
            payback_period_months=payback_months,
            savings_by_service=savings_by_service,
            engineer_hours_saved=hours_saved,
        )

        logger.info(
            "roi_analysis_calculated",
            analysis_id=analysis.analysis_id,
            total_incidents=total_incidents,
            total_savings=str(total_savings),
            roi_percent=roi_percent,
        )

        return analysis

    async def finalize_cost(
        self,
        incident_cost: IncidentCost,
        finalized_by: str,
    ) -> IncidentCost:
        """Finalize an incident cost record.

        Once finalized, the cost record is considered locked for audit purposes.

        Args:
            incident_cost: The incident cost record to finalize.
            finalized_by: User who finalized the record.

        Returns:
            Finalized incident cost record.
        """
        incident_cost.calculate_totals()
        incident_cost.is_finalized = True
        incident_cost.finalized_at = datetime.utcnow()
        incident_cost.finalized_by = finalized_by

        logger.info(
            "incident_cost_finalized",
            cost_id=incident_cost.cost_id,
            incident_id=incident_cost.incident_id,
            total_cost=str(incident_cost.total_cost),
            finalized_by=finalized_by,
        )

        return incident_cost
