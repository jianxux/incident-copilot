"""Cost calculators for different incident cost categories."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from .models import (
    CostCategory,
    CostEntry,
    Currency,
    EngineerRate,
    ServiceCriticality,
    ServiceRevenueConfig,
    SLAConfig,
)


class CostCalculator(Protocol):
    """Protocol for cost calculators."""

    async def calculate(self, **kwargs) -> CostEntry: ...


class EngineerTimeCostCalculator:
    """Calculator for engineer time costs."""

    # Default rates by level if no specific rate configured
    DEFAULT_RATES: dict[str, Decimal] = {
        "junior": Decimal("75"),
        "mid": Decimal("100"),
        "senior": Decimal("150"),
        "staff": Decimal("200"),
        "principal": Decimal("250"),
        "default": Decimal("125"),
    }

    def __init__(self, rates: dict[str, EngineerRate] | None = None):
        """Initialize with optional engineer rate configurations."""
        self.rates = rates or {}

    def get_rate(
        self,
        engineer_id: str | None = None,
        team: str | None = None,
        level: str | None = None,
    ) -> Decimal:
        """Get hourly rate for an engineer."""
        # Check for specific engineer rate
        if engineer_id and engineer_id in self.rates:
            return self.rates[engineer_id].hourly_rate

        # Check for team default rate
        if team:
            team_rates = [
                r for r in self.rates.values() if r.team == team and r.is_default
            ]
            if team_rates:
                return team_rates[0].hourly_rate

        # Fall back to level-based rate
        level_key = (level or "default").lower()
        return self.DEFAULT_RATES.get(level_key, self.DEFAULT_RATES["default"])

    async def calculate(
        self,
        incident_id: str,
        hours: float,
        engineer_id: str | None = None,
        engineer_name: str | None = None,
        team: str | None = None,
        department: str | None = None,
        level: str | None = None,
        description: str | None = None,
    ) -> CostEntry:
        """Calculate cost for engineer time spent on incident."""
        hourly_rate = self.get_rate(engineer_id, team, level)
        amount = hourly_rate * Decimal(str(hours))

        return CostEntry(
            incident_id=incident_id,
            category=CostCategory.ENGINEER_TIME,
            amount=amount,
            currency=Currency.USD,
            description=description or f"Engineer time: {hours}h @ ${hourly_rate}/h",
            team=team,
            department=department,
            engineer_id=engineer_id,
            engineer_name=engineer_name,
            hours_spent=hours,
            hourly_rate=hourly_rate,
            source="calculated",
        )

    async def calculate_team_response(
        self,
        incident_id: str,
        responders: list[dict],
        duration_hours: float,
    ) -> list[CostEntry]:
        """Calculate costs for entire team response."""
        entries = []
        for responder in responders:
            entry = await self.calculate(
                incident_id=incident_id,
                hours=responder.get("hours", duration_hours),
                engineer_id=responder.get("id"),
                engineer_name=responder.get("name"),
                team=responder.get("team"),
                department=responder.get("department"),
                level=responder.get("level"),
            )
            entries.append(entry)
        return entries


class RevenueImpactCalculator:
    """Calculator for lost revenue impact."""

    # Default hourly impact by criticality
    DEFAULT_HOURLY_IMPACT: dict[ServiceCriticality, Decimal] = {
        ServiceCriticality.CRITICAL: Decimal("50000"),
        ServiceCriticality.HIGH: Decimal("10000"),
        ServiceCriticality.MEDIUM: Decimal("2000"),
        ServiceCriticality.LOW: Decimal("500"),
    }

    def __init__(self, service_configs: dict[str, ServiceRevenueConfig] | None = None):
        """Initialize with optional service revenue configurations."""
        self.service_configs = service_configs or {}

    def get_hourly_impact(
        self, service_name: str, criticality: ServiceCriticality | None = None
    ) -> Decimal:
        """Get hourly revenue impact for a service."""
        if service_name in self.service_configs:
            return self.service_configs[service_name].hourly_revenue_impact

        crit = criticality or ServiceCriticality.MEDIUM
        return self.DEFAULT_HOURLY_IMPACT.get(
            crit, self.DEFAULT_HOURLY_IMPACT[ServiceCriticality.MEDIUM]
        )

    async def calculate(
        self,
        incident_id: str,
        service_name: str,
        duration_hours: float,
        criticality: ServiceCriticality | None = None,
        partial_outage_pct: float = 100.0,  # % of service affected
        description: str | None = None,
    ) -> CostEntry:
        """Calculate revenue impact for a service outage."""
        hourly_impact = self.get_hourly_impact(service_name, criticality)
        # Adjust for partial outage
        adjusted_impact = hourly_impact * Decimal(str(partial_outage_pct / 100))
        amount = adjusted_impact * Decimal(str(duration_hours))

        return CostEntry(
            incident_id=incident_id,
            category=CostCategory.LOST_REVENUE,
            amount=amount,
            currency=Currency.USD,
            description=description
            or f"Revenue impact: {service_name} ({partial_outage_pct}% affected for {duration_hours}h)",
            source="calculated",
            metadata={
                "service_name": service_name,
                "duration_hours": duration_hours,
                "partial_outage_pct": partial_outage_pct,
                "hourly_impact": str(hourly_impact),
            },
        )


class CloudCostCalculator:
    """Calculator for cloud resource costs during incidents."""

    # Default hourly costs for common resource types
    DEFAULT_RESOURCE_COSTS: dict[str, Decimal] = {
        "compute_extra": Decimal("50"),  # Extra compute for scaling
        "database_recovery": Decimal("100"),  # DB recovery operations
        "bandwidth_spike": Decimal("25"),  # Extra bandwidth
        "storage_snapshot": Decimal("10"),  # Emergency snapshots
        "failover": Decimal("200"),  # Failover to DR
    }

    async def calculate(
        self,
        incident_id: str,
        resource_type: str,
        quantity: float = 1.0,
        hours: float = 1.0,
        unit_cost: Decimal | None = None,
        description: str | None = None,
    ) -> CostEntry:
        """Calculate cloud resource costs."""
        if unit_cost is None:
            unit_cost = self.DEFAULT_RESOURCE_COSTS.get(resource_type, Decimal("50"))

        amount = unit_cost * Decimal(str(quantity)) * Decimal(str(hours))

        return CostEntry(
            incident_id=incident_id,
            category=CostCategory.CLOUD_RESOURCES,
            amount=amount,
            currency=Currency.USD,
            description=description
            or f"Cloud: {resource_type} ({quantity} x {hours}h)",
            source="calculated",
            metadata={
                "resource_type": resource_type,
                "quantity": quantity,
                "hours": hours,
                "unit_cost": str(unit_cost),
            },
        )

    async def calculate_scaling_cost(
        self,
        incident_id: str,
        original_capacity: int,
        scaled_capacity: int,
        duration_hours: float,
        cost_per_unit_hour: Decimal,
    ) -> CostEntry:
        """Calculate cost of emergency scaling."""
        extra_units = max(0, scaled_capacity - original_capacity)
        amount = (
            cost_per_unit_hour
            * Decimal(str(extra_units))
            * Decimal(str(duration_hours))
        )

        return CostEntry(
            incident_id=incident_id,
            category=CostCategory.CLOUD_RESOURCES,
            amount=amount,
            currency=Currency.USD,
            description=f"Emergency scaling: {original_capacity} → {scaled_capacity} for {duration_hours}h",
            source="calculated",
            metadata={
                "original_capacity": original_capacity,
                "scaled_capacity": scaled_capacity,
                "extra_units": extra_units,
            },
        )


class SLAPenaltyCalculator:
    """Calculator for SLA penalty costs."""

    def __init__(self, sla_configs: dict[str, SLAConfig] | None = None):
        """Initialize with SLA configurations."""
        self.sla_configs = sla_configs or {}

    def calculate_downtime_pct(
        self,
        downtime_minutes: float,
        period_days: int = 30,
    ) -> float:
        """Calculate downtime percentage for a period."""
        total_minutes = period_days * 24 * 60
        return (downtime_minutes / total_minutes) * 100

    def calculate_uptime(self, downtime_pct: float) -> float:
        """Calculate uptime percentage from downtime."""
        return 100.0 - downtime_pct

    async def calculate(
        self,
        incident_id: str,
        customer_id: str,
        downtime_minutes: float,
        period_days: int = 30,
        description: str | None = None,
    ) -> CostEntry | None:
        """Calculate SLA penalty for a customer."""
        if customer_id not in self.sla_configs:
            return None

        config = self.sla_configs[customer_id]
        downtime_pct = self.calculate_downtime_pct(downtime_minutes, period_days)
        uptime = self.calculate_uptime(downtime_pct)

        # Check if SLA is breached
        if uptime >= config.uptime_target:
            return None  # No breach, no penalty

        # Calculate breach severity
        breach_pct = config.uptime_target - uptime
        penalty_pct = min(
            breach_pct * config.penalty_per_violation_pct,
            config.max_penalty_pct,
        )
        amount = config.monthly_fee * penalty_pct / Decimal("100")

        return CostEntry(
            incident_id=incident_id,
            category=CostCategory.SLA_PENALTY,
            amount=amount,
            currency=config.currency,
            description=description
            or f"SLA penalty for {config.customer_name}: {uptime:.3f}% uptime (target: {config.uptime_target}%)",
            source="calculated",
            metadata={
                "customer_id": customer_id,
                "customer_name": config.customer_name,
                "downtime_minutes": downtime_minutes,
                "uptime_pct": uptime,
                "target_uptime": config.uptime_target,
                "penalty_pct": float(penalty_pct),
            },
        )


class CustomerImpactCalculator:
    """Calculator for customer impact costs."""

    # Cost estimates per customer impact type
    IMPACT_COSTS: dict[str, Decimal] = {
        "support_ticket": Decimal("50"),
        "escalation": Decimal("200"),
        "churn_risk": Decimal("5000"),
        "refund": Decimal("100"),
        "goodwill_credit": Decimal("250"),
    }

    async def calculate(
        self,
        incident_id: str,
        impact_type: str,
        count: int = 1,
        custom_cost: Decimal | None = None,
        description: str | None = None,
    ) -> CostEntry:
        """Calculate customer impact cost."""
        unit_cost = custom_cost or self.IMPACT_COSTS.get(impact_type, Decimal("100"))
        amount = unit_cost * Decimal(str(count))

        return CostEntry(
            incident_id=incident_id,
            category=CostCategory.CUSTOMER_IMPACT,
            amount=amount,
            currency=Currency.USD,
            description=description or f"Customer impact: {count}x {impact_type}",
            source="calculated",
            metadata={
                "impact_type": impact_type,
                "count": count,
                "unit_cost": str(unit_cost),
            },
        )

    async def calculate_from_tickets(
        self,
        incident_id: str,
        tickets: int,
        escalations: int = 0,
        refunds: int = 0,
    ) -> list[CostEntry]:
        """Calculate costs from support metrics."""
        entries = []

        if tickets > 0:
            entries.append(await self.calculate(incident_id, "support_ticket", tickets))
        if escalations > 0:
            entries.append(await self.calculate(incident_id, "escalation", escalations))
        if refunds > 0:
            entries.append(await self.calculate(incident_id, "refund", refunds))

        return entries


class CostCalculatorFactory:
    """Factory for creating and configuring cost calculators."""

    def __init__(self):
        self._engineer_rates: dict[str, EngineerRate] = {}
        self._service_configs: dict[str, ServiceRevenueConfig] = {}
        self._sla_configs: dict[str, SLAConfig] = {}

    def register_engineer_rate(self, rate: EngineerRate) -> None:
        """Register an engineer rate configuration."""
        self._engineer_rates[rate.id] = rate

    def register_service_config(self, config: ServiceRevenueConfig) -> None:
        """Register a service revenue configuration."""
        self._service_configs[config.service_name] = config

    def register_sla_config(self, config: SLAConfig) -> None:
        """Register an SLA configuration."""
        self._sla_configs[config.customer_id] = config

    def engineer_time(self) -> EngineerTimeCostCalculator:
        """Get engineer time calculator."""
        return EngineerTimeCostCalculator(self._engineer_rates)

    def revenue_impact(self) -> RevenueImpactCalculator:
        """Get revenue impact calculator."""
        return RevenueImpactCalculator(self._service_configs)

    def cloud_cost(self) -> CloudCostCalculator:
        """Get cloud cost calculator."""
        return CloudCostCalculator()

    def sla_penalty(self) -> SLAPenaltyCalculator:
        """Get SLA penalty calculator."""
        return SLAPenaltyCalculator(self._sla_configs)

    def customer_impact(self) -> CustomerImpactCalculator:
        """Get customer impact calculator."""
        return CustomerImpactCalculator()
