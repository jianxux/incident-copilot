"""Configurable cost factors for incident cost calculation.

This module provides default cost factors and configuration for calculating
incident costs including hourly rates, revenue impact, and SLA penalties.
"""

from datetime import datetime
from decimal import Decimal

import structlog
from pydantic import BaseModel, Field

from .models import CostCategory, CostFactor

logger = structlog.get_logger()


class HourlyRates(BaseModel):
    """Hourly rates by role and team."""

    # Default rates by role
    default_rate: Decimal = Field(default=Decimal("150"))

    # Role-specific rates
    role_rates: dict[str, Decimal] = Field(
        default_factory=lambda: {
            "sre": Decimal("175"),
            "senior_sre": Decimal("200"),
            "staff_sre": Decimal("250"),
            "principal_sre": Decimal("300"),
            "software_engineer": Decimal("150"),
            "senior_engineer": Decimal("185"),
            "staff_engineer": Decimal("225"),
            "principal_engineer": Decimal("275"),
            "engineering_manager": Decimal("220"),
            "director": Decimal("275"),
            "vp": Decimal("350"),
            "dba": Decimal("180"),
            "security_engineer": Decimal("190"),
            "support_engineer": Decimal("120"),
        }
    )

    # Team-specific adjustments (multipliers)
    team_multipliers: dict[str, Decimal] = Field(
        default_factory=lambda: {
            "platform": Decimal("1.1"),
            "infrastructure": Decimal("1.1"),
            "security": Decimal("1.15"),
            "data": Decimal("1.05"),
            "payments": Decimal("1.2"),  # Higher stakes = premium
        }
    )

    # Overtime multipliers
    overtime_multiplier: Decimal = Field(default=Decimal("1.5"))
    weekend_multiplier: Decimal = Field(default=Decimal("2.0"))
    holiday_multiplier: Decimal = Field(default=Decimal("2.5"))

    def get_rate(
        self,
        role: str | None = None,
        team: str | None = None,
        is_overtime: bool = False,
        is_weekend: bool = False,
        is_holiday: bool = False,
    ) -> Decimal:
        """Get the hourly rate for a given role and team."""
        # Base rate from role or default
        base_rate = self.role_rates.get(
            role.lower() if role else "",
            self.default_rate,
        )

        # Apply team multiplier
        if team:
            team_key = team.lower().replace("-", "_").replace(" ", "_")
            multiplier = self.team_multipliers.get(team_key, Decimal("1.0"))
            base_rate = base_rate * multiplier

        # Apply time-based multipliers (highest one wins)
        if is_holiday:
            base_rate = base_rate * self.holiday_multiplier
        elif is_weekend:
            base_rate = base_rate * self.weekend_multiplier
        elif is_overtime:
            base_rate = base_rate * self.overtime_multiplier

        return base_rate.quantize(Decimal("0.01"))


class RevenueFactors(BaseModel):
    """Revenue impact factors for cost calculation."""

    # Revenue per user per hour (for user-facing services)
    default_revenue_per_user_hour: Decimal = Field(default=Decimal("0.10"))

    # Service-specific revenue factors
    service_revenue: dict[str, Decimal] = Field(
        default_factory=lambda: {
            # Revenue per minute of downtime
            "payments-api": Decimal("500"),
            "checkout-service": Decimal("400"),
            "api-gateway": Decimal("300"),
            "auth-service": Decimal("250"),
            "user-service": Decimal("150"),
            "search-service": Decimal("100"),
            "notification-service": Decimal("50"),
            "analytics-service": Decimal("25"),
        }
    )

    # Transaction value for transactional services
    average_transaction_value: Decimal = Field(default=Decimal("50"))

    # Severity multipliers for revenue impact
    severity_multipliers: dict[str, Decimal] = Field(
        default_factory=lambda: {
            "critical": Decimal("1.0"),  # Full impact
            "high": Decimal("0.75"),  # 75% impact
            "medium": Decimal("0.50"),  # 50% impact
            "low": Decimal("0.25"),  # 25% impact
            "info": Decimal("0.0"),  # No revenue impact
        }
    )

    def get_revenue_impact(
        self,
        service_name: str,
        duration_minutes: int,
        severity: str,
        affected_users: int = 0,
        affected_transactions: int = 0,
    ) -> Decimal:
        """Calculate revenue impact for an incident."""
        # Get base revenue rate for service
        service_key = service_name.lower().replace("_", "-")
        revenue_per_minute = self.service_revenue.get(
            service_key,
            Decimal("10"),  # Default $10/minute
        )

        # Calculate base impact from downtime
        base_impact = revenue_per_minute * Decimal(duration_minutes)

        # Add user-based impact
        if affected_users > 0:
            hours = Decimal(duration_minutes) / Decimal("60")
            user_impact = (
                Decimal(affected_users)
                * hours
                * self.default_revenue_per_user_hour
            )
            base_impact += user_impact

        # Add transaction-based impact
        if affected_transactions > 0:
            transaction_impact = (
                Decimal(affected_transactions) * self.average_transaction_value
            )
            base_impact += transaction_impact

        # Apply severity multiplier
        multiplier = self.severity_multipliers.get(
            severity.lower(),
            Decimal("0.5"),
        )
        total_impact = base_impact * multiplier

        return total_impact.quantize(Decimal("0.01"))


class SLAFactors(BaseModel):
    """SLA penalty factors."""

    # Default SLA targets
    uptime_target_percent: Decimal = Field(default=Decimal("99.9"))
    response_time_minutes: int = Field(default=15)
    resolution_time_hours: dict[str, int] = Field(
        default_factory=lambda: {
            "critical": 4,
            "high": 8,
            "medium": 24,
            "low": 72,
        }
    )

    # Penalty structures
    uptime_penalty_per_percent: Decimal = Field(default=Decimal("1000"))
    response_time_penalty: Decimal = Field(default=Decimal("500"))
    resolution_time_penalty_per_hour: Decimal = Field(default=Decimal("200"))

    # Customer tier multipliers
    customer_tier_multipliers: dict[str, Decimal] = Field(
        default_factory=lambda: {
            "enterprise": Decimal("2.0"),
            "business": Decimal("1.5"),
            "professional": Decimal("1.0"),
            "starter": Decimal("0.5"),
            "free": Decimal("0.0"),
        }
    )

    def calculate_uptime_penalty(
        self,
        actual_uptime_percent: Decimal,
        customer_tier: str = "professional",
    ) -> Decimal:
        """Calculate penalty for uptime SLA breach."""
        if actual_uptime_percent >= self.uptime_target_percent:
            return Decimal("0")

        breach_percent = self.uptime_target_percent - actual_uptime_percent
        base_penalty = breach_percent * self.uptime_penalty_per_percent

        tier_multiplier = self.customer_tier_multipliers.get(
            customer_tier.lower(),
            Decimal("1.0"),
        )

        return (base_penalty * tier_multiplier).quantize(Decimal("0.01"))

    def calculate_resolution_penalty(
        self,
        severity: str,
        resolution_time_hours: float,
        customer_tier: str = "professional",
    ) -> Decimal:
        """Calculate penalty for resolution time SLA breach."""
        target_hours = self.resolution_time_hours.get(severity.lower(), 24)

        if resolution_time_hours <= target_hours:
            return Decimal("0")

        breach_hours = Decimal(str(resolution_time_hours - target_hours))
        base_penalty = breach_hours * self.resolution_time_penalty_per_hour

        tier_multiplier = self.customer_tier_multipliers.get(
            customer_tier.lower(),
            Decimal("1.0"),
        )

        return (base_penalty * tier_multiplier).quantize(Decimal("0.01"))


class CostFactorConfig(BaseModel):
    """Complete cost factor configuration."""

    config_id: str = "default"
    name: str = "Default Cost Configuration"
    description: str | None = None
    is_active: bool = True
    effective_from: datetime = Field(default_factory=datetime.utcnow)
    effective_until: datetime | None = None

    # Component configurations
    hourly_rates: HourlyRates = Field(default_factory=HourlyRates)
    revenue_factors: RevenueFactors = Field(default_factory=RevenueFactors)
    sla_factors: SLAFactors = Field(default_factory=SLAFactors)

    # Custom cost factors
    custom_factors: list[CostFactor] = Field(default_factory=list)

    # Currency
    currency: str = "USD"

    # ROI calculation defaults
    baseline_mttr_minutes: int = Field(default=60)  # Industry average
    copilot_mttr_reduction_percent: Decimal = Field(default=Decimal("30"))
    tooling_monthly_cost: Decimal = Field(default=Decimal("5000"))

    def get_factor(self, factor_id: str) -> CostFactor | None:
        """Get a custom cost factor by ID."""
        for factor in self.custom_factors:
            if factor.factor_id == factor_id:
                return factor
        return None


class DefaultCostFactors:
    """Factory for default cost factors."""

    @staticmethod
    def get_engineer_time_factor() -> CostFactor:
        """Default engineer time cost factor."""
        return CostFactor(
            factor_id="engineer_time_default",
            name="Engineer Time",
            description="Default hourly rate for engineer time during incidents",
            category=CostCategory.ENGINEER_TIME,
            value=Decimal("150"),
            unit="per_hour",
            applies_to=["*"],
            severity_multipliers={
                "critical": Decimal("1.5"),  # 50% premium for critical
                "high": Decimal("1.25"),
                "medium": Decimal("1.0"),
                "low": Decimal("0.75"),
            },
        )

    @staticmethod
    def get_revenue_impact_factor(service_name: str) -> CostFactor:
        """Revenue impact cost factor for a service."""
        # Default values, should be configured per service
        defaults = {
            "payments": Decimal("500"),
            "checkout": Decimal("400"),
            "api-gateway": Decimal("300"),
        }

        value = defaults.get(service_name.lower(), Decimal("100"))

        return CostFactor(
            factor_id=f"revenue_impact_{service_name}",
            name=f"Revenue Impact - {service_name}",
            description=f"Revenue impact per minute of downtime for {service_name}",
            category=CostCategory.REVENUE_IMPACT,
            value=value,
            unit="per_minute",
            applies_to=[service_name],
        )

    @staticmethod
    def get_sla_penalty_factor() -> CostFactor:
        """Default SLA penalty cost factor."""
        return CostFactor(
            factor_id="sla_penalty_default",
            name="SLA Penalty",
            description="Penalty per hour of SLA breach",
            category=CostCategory.SLA_PENALTY,
            value=Decimal("200"),
            unit="per_hour",
            applies_to=["*"],
            severity_multipliers={
                "critical": Decimal("2.0"),
                "high": Decimal("1.5"),
                "medium": Decimal("1.0"),
                "low": Decimal("0.5"),
            },
        )

    @staticmethod
    def get_infrastructure_factor() -> CostFactor:
        """Infrastructure cost factor (e.g., emergency scaling)."""
        return CostFactor(
            factor_id="infrastructure_default",
            name="Infrastructure",
            description="Additional infrastructure costs during incident response",
            category=CostCategory.INFRASTRUCTURE,
            value=Decimal("50"),
            unit="per_hour",
            applies_to=["*"],
        )

    @staticmethod
    def get_default_config() -> CostFactorConfig:
        """Get the default cost factor configuration."""
        config = CostFactorConfig(
            config_id="default",
            name="Default Cost Configuration",
            description="Standard cost factors for incident cost calculation",
            custom_factors=[
                DefaultCostFactors.get_engineer_time_factor(),
                DefaultCostFactors.get_sla_penalty_factor(),
                DefaultCostFactors.get_infrastructure_factor(),
            ],
        )

        logger.info(
            "default_cost_config_created",
            config_id=config.config_id,
            factor_count=len(config.custom_factors),
        )

        return config


# Global default configuration
_default_config: CostFactorConfig | None = None


def get_cost_config() -> CostFactorConfig:
    """Get the current cost factor configuration."""
    global _default_config
    if _default_config is None:
        _default_config = DefaultCostFactors.get_default_config()
    return _default_config


def set_cost_config(config: CostFactorConfig) -> None:
    """Set the cost factor configuration."""
    global _default_config
    _default_config = config
    logger.info(
        "cost_config_updated",
        config_id=config.config_id,
        name=config.name,
    )
