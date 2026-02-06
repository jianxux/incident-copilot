"""Data models for Incident Cost Tracking."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class CostCategory(str, Enum):
    """Categories of incident costs."""

    ENGINEER_TIME = "engineer_time"
    REVENUE_IMPACT = "revenue_impact"
    SLA_PENALTY = "sla_penalty"
    INFRASTRUCTURE = "infrastructure"
    EXTERNAL_SUPPORT = "external_support"
    CUSTOMER_CREDIT = "customer_credit"
    OTHER = "other"


class ReportPeriod(str, Enum):
    """Time periods for cost reports."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class ResponderCost(BaseModel):
    """Cost associated with a single incident responder."""

    responder_id: str
    responder_name: str
    team: str | None = None
    role: str | None = None
    hourly_rate: Decimal = Field(default=Decimal("0"))
    time_spent_minutes: int = 0
    total_cost: Decimal = Field(default=Decimal("0"))
    is_overtime: bool = False
    overtime_multiplier: Decimal = Field(default=Decimal("1.5"))


class CostBreakdown(BaseModel):
    """Breakdown of costs by category."""

    category: CostCategory
    amount: Decimal = Field(default=Decimal("0"))
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class SLAPenalty(BaseModel):
    """SLA penalty details."""

    sla_id: str
    sla_name: str
    customer_id: str | None = None
    customer_name: str | None = None
    breach_type: str  # e.g., "uptime", "response_time", "resolution_time"
    target_value: str  # e.g., "99.9%", "15 minutes"
    actual_value: str  # e.g., "99.5%", "45 minutes"
    penalty_amount: Decimal = Field(default=Decimal("0"))
    penalty_type: str = "fixed"  # "fixed", "percentage", "tiered"
    is_waived: bool = False
    waiver_reason: str | None = None


class IncidentCost(BaseModel):
    """Complete cost record for a single incident."""

    cost_id: str = Field(default_factory=lambda: f"COST-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
    incident_id: str
    service_name: str
    severity: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Time-based info
    incident_started_at: datetime
    incident_resolved_at: datetime | None = None
    duration_minutes: int = 0
    time_to_detect_minutes: int | None = None
    time_to_resolve_minutes: int | None = None

    # Impact metrics
    affected_users: int = 0
    affected_transactions: int = 0
    affected_services: list[str] = Field(default_factory=list)

    # Cost breakdown
    responder_costs: list[ResponderCost] = Field(default_factory=list)
    cost_breakdown: list[CostBreakdown] = Field(default_factory=list)
    sla_penalties: list[SLAPenalty] = Field(default_factory=list)

    # Totals
    total_engineer_cost: Decimal = Field(default=Decimal("0"))
    total_revenue_impact: Decimal = Field(default=Decimal("0"))
    total_sla_penalties: Decimal = Field(default=Decimal("0"))
    total_other_costs: Decimal = Field(default=Decimal("0"))
    total_cost: Decimal = Field(default=Decimal("0"))

    # Currency
    currency: str = "USD"

    # ROI calculation fields
    baseline_mttr_minutes: int | None = None  # Average MTTR without copilot
    actual_mttr_minutes: int | None = None
    estimated_savings: Decimal = Field(default=Decimal("0"))

    # Metadata
    is_finalized: bool = False
    finalized_at: datetime | None = None
    finalized_by: str | None = None
    notes: str | None = None
    metadata: dict = Field(default_factory=dict)

    def calculate_totals(self) -> None:
        """Recalculate total costs from breakdown."""
        self.total_engineer_cost = sum(
            r.total_cost for r in self.responder_costs
        )

        category_totals = {cat: Decimal("0") for cat in CostCategory}
        for breakdown in self.cost_breakdown:
            category_totals[breakdown.category] += breakdown.amount

        self.total_revenue_impact = category_totals[CostCategory.REVENUE_IMPACT]
        self.total_sla_penalties = sum(
            p.penalty_amount for p in self.sla_penalties if not p.is_waived
        )
        self.total_other_costs = (
            category_totals[CostCategory.INFRASTRUCTURE]
            + category_totals[CostCategory.EXTERNAL_SUPPORT]
            + category_totals[CostCategory.CUSTOMER_CREDIT]
            + category_totals[CostCategory.OTHER]
        )

        self.total_cost = (
            self.total_engineer_cost
            + self.total_revenue_impact
            + self.total_sla_penalties
            + self.total_other_costs
        )
        self.updated_at = datetime.utcnow()


class CostFactor(BaseModel):
    """Configurable cost factor for calculations."""

    factor_id: str
    name: str
    description: str | None = None
    category: CostCategory
    value: Decimal
    unit: str  # e.g., "per_hour", "per_user", "per_minute", "percentage"
    applies_to: list[str] = Field(default_factory=list)  # Service names, teams, or "*" for all
    severity_multipliers: dict[str, Decimal] = Field(default_factory=dict)
    is_active: bool = True
    effective_from: datetime = Field(default_factory=datetime.utcnow)
    effective_until: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class TeamCostSummary(BaseModel):
    """Cost summary for a team."""

    team_name: str
    incident_count: int = 0
    total_response_time_minutes: int = 0
    total_cost: Decimal = Field(default=Decimal("0"))
    average_cost_per_incident: Decimal = Field(default=Decimal("0"))
    responder_count: int = 0
    top_responders: list[dict] = Field(default_factory=list)  # name, cost, incident_count


class ServiceCostSummary(BaseModel):
    """Cost summary for a service."""

    service_name: str
    incident_count: int = 0
    total_cost: Decimal = Field(default=Decimal("0"))
    total_revenue_impact: Decimal = Field(default=Decimal("0"))
    total_sla_penalties: Decimal = Field(default=Decimal("0"))
    average_cost_per_incident: Decimal = Field(default=Decimal("0"))
    cost_by_severity: dict[str, Decimal] = Field(default_factory=dict)
    mttr_minutes: float = 0.0


class ROIAnalysis(BaseModel):
    """ROI analysis for incident management improvements."""

    analysis_id: str
    period_start: datetime
    period_end: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Metrics
    total_incidents: int = 0
    baseline_mttr_minutes: float = 0.0  # Average MTTR before/without improvements
    actual_mttr_minutes: float = 0.0  # Average MTTR with improvements
    mttr_reduction_percent: float = 0.0

    # Cost impact
    baseline_cost_per_incident: Decimal = Field(default=Decimal("0"))
    actual_cost_per_incident: Decimal = Field(default=Decimal("0"))
    total_savings: Decimal = Field(default=Decimal("0"))

    # Revenue protection
    revenue_protected: Decimal = Field(default=Decimal("0"))  # Revenue saved from faster resolution
    sla_penalties_avoided: Decimal = Field(default=Decimal("0"))

    # ROI calculation
    investment_cost: Decimal = Field(default=Decimal("0"))  # Cost of copilot/tooling
    roi_percentage: float = 0.0
    payback_period_months: float | None = None

    # Breakdown by category
    savings_by_category: dict[str, Decimal] = Field(default_factory=dict)
    savings_by_service: dict[str, Decimal] = Field(default_factory=dict)

    # Additional metrics
    engineer_hours_saved: float = 0.0
    incidents_prevented: int = 0  # Estimated incidents avoided via proactive detection

    notes: str | None = None


class CostReport(BaseModel):
    """Comprehensive cost report for a period."""

    report_id: str
    title: str
    period: ReportPeriod
    period_start: datetime
    period_end: datetime
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generated_by: str | None = None

    # Summary
    total_incidents: int = 0
    total_cost: Decimal = Field(default=Decimal("0"))
    average_cost_per_incident: Decimal = Field(default=Decimal("0"))

    # Breakdown by category
    cost_by_category: dict[str, Decimal] = Field(default_factory=dict)

    # Breakdown by severity
    cost_by_severity: dict[str, Decimal] = Field(default_factory=dict)
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)

    # Team summaries
    team_summaries: list[TeamCostSummary] = Field(default_factory=list)

    # Service summaries
    service_summaries: list[ServiceCostSummary] = Field(default_factory=list)

    # Top costly incidents
    top_incidents: list[IncidentCost] = Field(default_factory=list)

    # SLA summary
    total_sla_penalties: Decimal = Field(default=Decimal("0"))
    sla_breach_count: int = 0
    sla_penalties_waived: Decimal = Field(default=Decimal("0"))

    # Trends
    cost_trend: list[dict] = Field(default_factory=list)  # {date, cost}
    mttr_trend: list[dict] = Field(default_factory=list)  # {date, mttr_minutes}

    # ROI
    roi_analysis: ROIAnalysis | None = None

    # Comparisons
    previous_period_cost: Decimal | None = None
    cost_change_percent: float | None = None

    # Currency
    currency: str = "USD"

    # Export info
    export_formats: list[str] = Field(default_factory=lambda: ["json", "csv", "pdf"])
    metadata: dict = Field(default_factory=dict)


# --- Request/Response Models ---


class CalculateCostRequest(BaseModel):
    """Request to calculate incident cost."""

    incident_id: str
    service_name: str
    severity: str
    incident_started_at: datetime
    incident_resolved_at: datetime | None = None
    responders: list[dict] = Field(default_factory=list)  # {id, name, team, role, time_minutes}
    affected_users: int = 0
    affected_transactions: int = 0
    custom_costs: list[dict] = Field(default_factory=list)  # {category, amount, description}


class UpdateCostRequest(BaseModel):
    """Request to update incident cost."""

    responders: list[dict] | None = None
    affected_users: int | None = None
    affected_transactions: int | None = None
    custom_costs: list[dict] | None = None
    sla_penalties: list[dict] | None = None
    notes: str | None = None
    is_finalized: bool | None = None


class GenerateReportRequest(BaseModel):
    """Request to generate a cost report."""

    period: ReportPeriod = ReportPeriod.MONTHLY
    period_start: datetime | None = None
    period_end: datetime | None = None
    services: list[str] | None = None  # Filter by services
    teams: list[str] | None = None  # Filter by teams
    include_roi: bool = True
    compare_previous: bool = True
    top_incidents_limit: int = 10


class ExportReportRequest(BaseModel):
    """Request to export a cost report."""

    format: str = "csv"  # csv, json, pdf
    include_details: bool = True
    include_roi: bool = True
