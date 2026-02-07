"""Data models for incident cost tracking and analysis."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field


class Currency(str, Enum):
    """Supported currencies."""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CAD = "CAD"
    AUD = "AUD"


class CostCategory(str, Enum):
    """Categories of incident costs."""

    ENGINEER_TIME = "engineer_time"
    LOST_REVENUE = "lost_revenue"
    CLOUD_RESOURCES = "cloud_resources"
    CUSTOMER_IMPACT = "customer_impact"
    SLA_PENALTY = "sla_penalty"
    REMEDIATION = "remediation"
    THIRD_PARTY = "third_party"
    OPPORTUNITY = "opportunity"


class ServiceCriticality(str, Enum):
    """Service criticality levels for revenue impact."""

    CRITICAL = "critical"  # Core revenue-generating
    HIGH = "high"  # Major business impact
    MEDIUM = "medium"  # Moderate impact
    LOW = "low"  # Minimal direct impact


class CostEntry(BaseModel):
    """A single cost entry for an incident."""

    id: str = Field(default_factory=lambda: "")
    incident_id: str
    category: CostCategory
    amount: Decimal = Field(ge=0)
    currency: Currency = Currency.USD
    description: str | None = None

    # Attribution
    team: str | None = None
    department: str | None = None
    engineer_id: str | None = None
    engineer_name: str | None = None

    # Time tracking (for engineer time)
    hours_spent: float | None = None
    hourly_rate: Decimal | None = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    source: str = "manual"  # manual, calculated, imported
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def amount_usd(self) -> Decimal:
        """Approximate USD amount (simplified conversion)."""
        rates = {
            Currency.USD: Decimal("1.0"),
            Currency.EUR: Decimal("1.08"),
            Currency.GBP: Decimal("1.27"),
            Currency.JPY: Decimal("0.0067"),
            Currency.CAD: Decimal("0.74"),
            Currency.AUD: Decimal("0.65"),
        }
        return self.amount * rates.get(self.currency, Decimal("1.0"))


class EngineerRate(BaseModel):
    """Hourly rate configuration for an engineer or team."""

    id: str
    name: str
    hourly_rate: Decimal
    currency: Currency = Currency.USD
    team: str | None = None
    department: str | None = None
    level: str | None = None  # junior, mid, senior, staff, principal
    is_default: bool = False
    effective_from: datetime = Field(default_factory=datetime.utcnow)
    effective_to: datetime | None = None


class ServiceRevenueConfig(BaseModel):
    """Revenue impact configuration for a service."""

    service_name: str
    criticality: ServiceCriticality
    hourly_revenue_impact: Decimal  # Estimated revenue impact per hour of downtime
    currency: Currency = Currency.USD
    customer_count: int | None = None
    monthly_revenue: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SLAConfig(BaseModel):
    """SLA configuration for penalty calculations."""

    id: str
    customer_id: str
    customer_name: str
    service_level: str  # gold, silver, bronze
    uptime_target: float = 99.9  # Percentage
    penalty_per_violation_pct: Decimal = Field(
        default=Decimal("1.0")
    )  # % of monthly fee
    monthly_fee: Decimal
    currency: Currency = Currency.USD
    max_penalty_pct: Decimal = Field(
        default=Decimal("25.0")
    )  # Max penalty as % of monthly fee


class IncidentCost(BaseModel):
    """Aggregated costs for a single incident."""

    incident_id: str
    incident_title: str | None = None
    service_name: str | None = None
    severity: str | None = None

    # Time range
    started_at: datetime | None = None
    resolved_at: datetime | None = None

    # Cost breakdown
    entries: list[CostEntry] = Field(default_factory=list)

    # Aggregated totals by category
    totals_by_category: dict[CostCategory, Decimal] = Field(default_factory=dict)

    # Summary
    total_cost: Decimal = Field(default=Decimal("0"))
    currency: Currency = Currency.USD
    calculated_at: datetime = Field(default_factory=datetime.utcnow)

    @computed_field
    @property
    def duration_hours(self) -> float | None:
        """Duration of incident in hours."""
        if self.started_at and self.resolved_at:
            return (self.resolved_at - self.started_at).total_seconds() / 3600
        return None

    @computed_field
    @property
    def cost_per_hour(self) -> Decimal | None:
        """Average cost per hour of incident."""
        if self.duration_hours and self.duration_hours > 0:
            return self.total_cost / Decimal(str(self.duration_hours))
        return None

    def add_entry(self, entry: CostEntry) -> None:
        """Add a cost entry and update totals."""
        self.entries.append(entry)
        category_total = self.totals_by_category.get(entry.category, Decimal("0"))
        self.totals_by_category[entry.category] = category_total + entry.amount_usd
        self.total_cost += entry.amount_usd


class CostTrend(BaseModel):
    """Cost trend over a time period."""

    period: str  # "7d", "30d", "90d", etc.
    start_date: datetime
    end_date: datetime

    # Totals
    total_cost: Decimal
    incident_count: int
    average_cost_per_incident: Decimal

    # By category
    by_category: dict[CostCategory, Decimal] = Field(default_factory=dict)

    # By team/department
    by_team: dict[str, Decimal] = Field(default_factory=dict)
    by_department: dict[str, Decimal] = Field(default_factory=dict)

    # Comparison to previous period
    previous_total: Decimal | None = None
    change_pct: float | None = None
    trend: str = "stable"  # improving, degrading, stable


class CostReport(BaseModel):
    """Comprehensive cost report for a time period."""

    report_id: str
    title: str
    period: str
    start_date: datetime
    end_date: datetime
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Summary
    total_cost: Decimal
    incident_count: int
    avg_cost_per_incident: Decimal
    max_cost_incident: IncidentCost | None = None

    # Breakdowns
    by_category: dict[CostCategory, Decimal] = Field(default_factory=dict)
    by_severity: dict[str, Decimal] = Field(default_factory=dict)
    by_service: dict[str, Decimal] = Field(default_factory=dict)
    by_team: dict[str, Decimal] = Field(default_factory=dict)
    by_department: dict[str, Decimal] = Field(default_factory=dict)

    # Trends
    trend: CostTrend | None = None
    daily_costs: list[tuple[str, Decimal]] = Field(default_factory=list)

    # Top incidents
    top_incidents: list[IncidentCost] = Field(default_factory=list)

    currency: Currency = Currency.USD


class ROIAnalysis(BaseModel):
    """ROI analysis for prevention investments."""

    analysis_id: str
    title: str
    period: str
    start_date: datetime
    end_date: datetime

    # Incident costs
    total_incident_cost: Decimal
    incident_count: int

    # Prevention investment
    prevention_investment: Decimal
    investment_items: list[dict[str, Any]] = Field(default_factory=list)

    # Projected savings
    projected_incidents_prevented: int
    projected_savings: Decimal

    # ROI calculation
    roi_pct: float | None = None
    payback_period_months: float | None = None
    net_benefit: Decimal | None = None

    currency: Currency = Currency.USD
    notes: str | None = None

    @computed_field
    @property
    def is_positive_roi(self) -> bool:
        """Whether the investment shows positive ROI."""
        return self.roi_pct is not None and self.roi_pct > 0


class TeamCostAllocation(BaseModel):
    """Cost allocation for a team or department."""

    team: str
    department: str | None = None
    period: str
    start_date: datetime
    end_date: datetime

    # Costs
    direct_costs: Decimal = Field(default=Decimal("0"))  # Costs directly caused by team
    support_costs: Decimal = Field(
        default=Decimal("0")
    )  # Costs for supporting other teams
    total_costs: Decimal = Field(default=Decimal("0"))

    # Breakdown
    by_category: dict[CostCategory, Decimal] = Field(default_factory=dict)
    incidents: list[str] = Field(default_factory=list)  # Incident IDs

    # Comparison
    previous_period_cost: Decimal | None = None
    change_pct: float | None = None

    currency: Currency = Currency.USD
