"""Data models for Team Performance Dashboard."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TrendDirection(str, Enum):
    """Direction of performance trend."""

    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"


class TimeGranularity(str, Enum):
    """Time granularity for metrics."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# --- Core Metrics Models ---


class TeamMetrics(BaseModel):
    """Core performance metrics for a team or service."""

    team_name: str | None = None
    service_name: str | None = None
    period_start: datetime
    period_end: datetime

    # MTTR/MTTA (Mean Time to Resolve/Acknowledge) in minutes
    mttr_minutes: float | None = None
    mtta_minutes: float | None = None

    # Incident counts
    total_incidents: int = 0
    resolved_incidents: int = 0
    open_incidents: int = 0

    # By severity
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    # SLA metrics
    sla_met_count: int = 0
    sla_breached_count: int = 0
    sla_compliance_percent: float | None = None

    # Comparison to previous period
    mttr_change_percent: float | None = None
    mtta_change_percent: float | None = None
    incident_count_change_percent: float | None = None

    # Metadata
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


class OnCallStats(BaseModel):
    """Statistics for on-call responders."""

    responder_id: str
    responder_name: str
    responder_email: str | None = None
    team_name: str | None = None

    period_start: datetime
    period_end: datetime

    # Page statistics
    total_pages: int = 0
    pages_acknowledged: int = 0
    pages_escalated: int = 0
    pages_reassigned: int = 0

    # Time metrics (in minutes)
    avg_ack_time_minutes: float | None = None
    avg_resolution_time_minutes: float | None = None
    total_oncall_hours: float | None = None

    # Incident breakdown
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    incidents_by_hour: dict[int, int] = Field(default_factory=dict)  # 0-23

    # Off-hours pages (nights/weekends)
    off_hours_pages: int = 0
    weekend_pages: int = 0
    night_pages: int = 0  # 22:00-06:00

    # Quality metrics
    false_positive_count: int = 0
    auto_resolved_count: int = 0


class PerformanceTrend(BaseModel):
    """Performance trend over time."""

    metric_name: str  # e.g., "mttr", "mtta", "incident_count"
    team_name: str | None = None
    service_name: str | None = None

    period_start: datetime
    period_end: datetime
    comparison_period_start: datetime
    comparison_period_end: datetime

    current_value: float
    previous_value: float
    change_absolute: float
    change_percent: float

    direction: TrendDirection
    is_improvement: bool  # Whether the change is positive (depends on metric)

    # Historical data points for charting
    data_points: list[tuple[datetime, float]] = Field(default_factory=list)


# --- Volume and Distribution Models ---


class IncidentVolume(BaseModel):
    """Incident volume statistics."""

    period_start: datetime
    period_end: datetime
    granularity: TimeGranularity

    # Volume by time
    by_hour: dict[int, int] = Field(default_factory=dict)  # 0-23 -> count
    by_day_of_week: dict[int, int] = Field(default_factory=dict)  # 0=Mon -> count
    by_date: dict[str, int] = Field(default_factory=dict)  # YYYY-MM-DD -> count

    # Aggregates
    total_count: int = 0
    daily_average: float = 0.0
    peak_hour: int | None = None
    peak_day: int | None = None

    # By category
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_service: dict[str, int] = Field(default_factory=dict)
    by_team: dict[str, int] = Field(default_factory=dict)


class TimeDistribution(BaseModel):
    """Time-based distribution analysis."""

    period_start: datetime
    period_end: datetime

    # Business vs off-hours (9-17 weekdays vs other)
    business_hours_count: int = 0
    off_hours_count: int = 0
    weekend_count: int = 0

    business_hours_percent: float = 0.0
    off_hours_percent: float = 0.0
    weekend_percent: float = 0.0

    # Busiest times
    busiest_hour: int | None = None  # 0-23
    busiest_day: int | None = None  # 0=Monday
    quietest_hour: int | None = None
    quietest_day: int | None = None


class WorkloadDistribution(BaseModel):
    """Distribution of workload across responders."""

    period_start: datetime
    period_end: datetime
    team_name: str | None = None

    # Distribution stats
    total_responders: int = 0
    total_incidents: int = 0
    avg_incidents_per_responder: float = 0.0
    std_dev_incidents: float = 0.0

    # Fairness metrics
    gini_coefficient: float | None = None  # 0 = perfectly equal, 1 = perfectly unequal
    top_responder_percent: float = 0.0  # % handled by busiest responder

    # Per-responder breakdown
    responder_counts: dict[str, int] = Field(default_factory=dict)  # name -> count


# --- SLA and Compliance Models ---


class SLACompliance(BaseModel):
    """SLA compliance metrics."""

    period_start: datetime
    period_end: datetime
    team_name: str | None = None
    service_name: str | None = None

    # Overall compliance
    total_incidents: int = 0
    sla_met: int = 0
    sla_breached: int = 0
    compliance_percent: float = 0.0

    # By severity (SLA targets typically differ by severity)
    by_severity: dict[str, dict[str, float]] = Field(
        default_factory=dict
    )  # severity -> {met, breached, percent}

    # SLA targets (in minutes)
    sla_targets: dict[str, int] = Field(
        default_factory=lambda: {
            "critical": 15,
            "high": 30,
            "medium": 60,
            "low": 240,
        }
    )

    # Trend
    previous_compliance_percent: float | None = None
    compliance_change_percent: float | None = None


# --- Burnout and Health Models ---


class BurnoutIndicator(BaseModel):
    """Burnout risk indicators for responders."""

    responder_id: str
    responder_name: str
    team_name: str | None = None

    period_start: datetime
    period_end: datetime

    # Risk factors
    total_pages: int = 0
    off_hours_pages: int = 0
    consecutive_oncall_days: int = 0
    pages_per_oncall_hour: float = 0.0

    # Thresholds exceeded
    exceeds_page_threshold: bool = False  # More than 50 pages/week
    exceeds_off_hours_threshold: bool = False  # More than 10 off-hours pages/week
    exceeds_consecutive_days_threshold: bool = False  # More than 7 days straight

    # Overall risk level
    risk_score: float = 0.0  # 0-100
    risk_level: str = "low"  # low, medium, high, critical

    # Recommendations
    recommendations: list[str] = Field(default_factory=list)


# --- Responder and Leaderboard Models ---


class ResponderStats(BaseModel):
    """Statistics for a single responder (for leaderboards)."""

    responder_id: str
    responder_name: str
    responder_email: str | None = None
    team_name: str | None = None
    avatar_url: str | None = None

    period_start: datetime
    period_end: datetime

    # Response metrics
    incidents_handled: int = 0
    incidents_resolved: int = 0
    avg_resolution_time_minutes: float | None = None
    avg_ack_time_minutes: float | None = None

    # Quality metrics
    first_response_rate: float = 0.0  # % of incidents where they responded first
    resolution_rate: float = 0.0  # % of handled incidents they resolved
    sla_compliance_rate: float = 0.0

    # Scores (for gamification)
    response_score: int = 0  # Points for quick responses
    resolution_score: int = 0  # Points for resolutions
    quality_score: int = 0  # Points for SLA compliance, low escalation rate
    total_score: int = 0

    # Rank
    rank: int | None = None
    rank_change: int | None = None  # vs previous period


# --- Summary and Report Models ---


class PerformanceSummary(BaseModel):
    """High-level performance summary."""

    period_start: datetime
    period_end: datetime
    team_name: str | None = None
    service_name: str | None = None

    # Key metrics
    mttr_minutes: float | None = None
    mtta_minutes: float | None = None
    total_incidents: int = 0
    sla_compliance_percent: float | None = None

    # Trends (vs previous period)
    mttr_trend: TrendDirection | None = None
    mtta_trend: TrendDirection | None = None
    incident_trend: TrendDirection | None = None

    # Highlights
    top_responders: list[str] = Field(default_factory=list)
    most_affected_services: list[str] = Field(default_factory=list)
    busiest_day: str | None = None

    # Health indicators
    burnout_risk_count: int = 0  # Number of responders at risk
    workload_imbalance: bool = False

    # AI-generated insights
    ai_summary: str | None = None
    key_insights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PerformanceReport(BaseModel):
    """Full performance report with all metrics."""

    report_id: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime

    # Filters
    team_name: str | None = None
    service_name: str | None = None

    # All metrics
    summary: PerformanceSummary
    team_metrics: TeamMetrics | None = None
    oncall_stats: list[OnCallStats] = Field(default_factory=list)
    trends: list[PerformanceTrend] = Field(default_factory=list)
    incident_volume: IncidentVolume | None = None
    time_distribution: TimeDistribution | None = None
    workload_distribution: WorkloadDistribution | None = None
    sla_compliance: SLACompliance | None = None
    burnout_indicators: list[BurnoutIndicator] = Field(default_factory=list)
    top_responders: list[ResponderStats] = Field(default_factory=list)

    # Report metadata
    version: int = 1
    format: str = "full"


# --- Request/Response Models ---


class MetricsRequest(BaseModel):
    """Request for performance metrics."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    team_name: str | None = None
    service_name: str | None = None
    severity: str | None = None
    responder_id: str | None = None
    granularity: TimeGranularity = TimeGranularity.DAILY
    include_trends: bool = True
    compare_to_previous: bool = True


class LeaderboardRequest(BaseModel):
    """Request for leaderboard data."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    team_name: str | None = None
    limit: int = Field(default=10, ge=1, le=100)
    metric: str = "total_score"  # total_score, resolution_time, incidents_handled


class ReportRequest(BaseModel):
    """Request to generate a performance report."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    team_name: str | None = None
    service_name: str | None = None
    format: str = "full"  # full, summary, executive
    include_ai_summary: bool = True
