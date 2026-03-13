"""Performance analytics data models.

Provides Pydantic v2 models for team and engineer performance tracking,
including DORA-style metrics, burnout indicators, and industry benchmarks.
"""

import statistics
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class PerformanceTier(StrEnum):
    """Performance tier classification based on DORA research."""

    ELITE = "elite"  # Top 10% performers
    HIGH = "high"  # Top 30% performers
    MEDIUM = "medium"  # Average performers
    LOW = "low"  # Below average


class BurnoutRisk(StrEnum):
    """Burnout risk levels for engineers."""

    LOW = "low"  # Healthy workload
    MODERATE = "moderate"  # Monitor closely
    HIGH = "high"  # Intervention recommended
    CRITICAL = "critical"  # Immediate action needed


class PerformancePeriod(BaseModel):
    """Time period for performance analysis."""

    start: datetime
    end: datetime
    label: str = ""

    @computed_field
    @property
    def days(self) -> int:
        """Number of days in the period."""
        return (self.end - self.start).days

    @computed_field
    @property
    def hours(self) -> float:
        """Total hours in the period."""
        return (self.end - self.start).total_seconds() / 3600

    @classmethod
    def last_n_days(cls, n: int, label: str = "") -> "PerformancePeriod":
        """Create a period for the last N days."""
        end = datetime.now(UTC)
        return cls(
            start=end - timedelta(days=n), end=end, label=label or f"Last {n} days"
        )

    @classmethod
    def week(cls) -> "PerformancePeriod":
        return cls.last_n_days(7, "Last 7 days")

    @classmethod
    def month(cls) -> "PerformancePeriod":
        return cls.last_n_days(30, "Last 30 days")

    @classmethod
    def quarter(cls) -> "PerformancePeriod":
        return cls.last_n_days(90, "Last 90 days")

    def previous(self) -> "PerformancePeriod":
        """Get the previous period of same duration."""
        duration = self.end - self.start
        return PerformancePeriod(
            start=self.start - duration, end=self.start, label=f"Previous {self.label}"
        )


class MetricValue(BaseModel):
    """Single metric with value, trend, and benchmark classification."""

    name: str
    value: float
    unit: str = ""
    trend: float | None = None  # Percentage change (positive = improvement)
    tier: PerformanceTier | None = None

    @computed_field
    @property
    def trend_direction(self) -> str | None:
        """Get trend direction: up, down, or stable."""
        if self.trend is None:
            return None
        return "up" if self.trend > 5 else ("down" if self.trend < -5 else "stable")

    @computed_field
    @property
    def display_value(self) -> str:
        """Formatted value with unit for display."""
        if self.unit == "%":
            return f"{self.value:.1f}%"
        if self.unit == "min":
            return f"{self.value:.0f} min"
        return f"{self.value:.2f}{' ' + self.unit if self.unit else ''}"


class WorkloadDistribution(BaseModel):
    """Workload distribution metrics using Gini coefficient.

    Gini coefficient: 0 = perfectly equal distribution, 1 = one person does all work.
    A healthy team should have Gini < 0.3.
    """

    gini_coefficient: float = Field(ge=0, le=1, description="0=equal, 1=unequal")
    top_10_pct_share: float = Field(description="% of work done by top 10%")
    bottom_50_pct_share: float = Field(description="% of work done by bottom 50%")
    std_deviation: float
    is_balanced: bool = True

    @classmethod
    def from_workloads(cls, workloads: list[float]) -> "WorkloadDistribution":
        """Calculate distribution metrics from list of workload values."""
        if not workloads or sum(workloads) == 0:
            return cls(
                gini_coefficient=0,
                top_10_pct_share=0,
                bottom_50_pct_share=0,
                std_deviation=0,
            )
        n, total = len(workloads), sum(workloads)
        sorted_loads = sorted(workloads)
        cumsum = sum(
            (2 * (i + 1) - n - 1) * load for i, load in enumerate(sorted_loads)
        )
        gini = max(0, min(1, cumsum / (n * total)))
        top_n = max(1, n // 10)
        return cls(
            gini_coefficient=round(gini, 3),
            top_10_pct_share=round(sum(sorted_loads[-top_n:]) / total * 100, 1),
            bottom_50_pct_share=(
                round(sum(sorted_loads[: n // 2]) / total * 100, 1) if n > 1 else 0
            ),
            std_deviation=round(statistics.stdev(workloads) if n > 1 else 0, 2),
            is_balanced=gini < 0.3,
        )


class BurnoutIndicators(BaseModel):
    """Burnout risk assessment for an engineer.

    Factors considered: after-hours pages, consecutive oncall days,
    high-severity incidents, and average incident duration.
    """

    risk_level: BurnoutRisk
    risk_score: float = Field(ge=0, le=100, description="0-100 risk score")
    factors: list[str] = Field(default_factory=list, description="Contributing factors")
    consecutive_oncall_days: int = 0
    after_hours_incidents: int = 0
    high_severity_count: int = 0
    avg_incident_duration_hours: float = 0
    recommendations: list[str] = Field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        """Check if engineer needs immediate attention."""
        return self.risk_level in (BurnoutRisk.HIGH, BurnoutRisk.CRITICAL)


class EngineerMetrics(BaseModel):
    """Individual engineer performance metrics with privacy controls."""

    engineer_id: str
    engineer_name: str
    period: PerformancePeriod
    # Core metrics
    incidents_handled: int = 0
    incidents_resolved: int = 0
    avg_response_time_min: float = 0
    avg_resolution_time_min: float = 0
    # Workload
    oncall_hours: float = 0
    after_hours_pages: int = 0
    escalations_made: int = 0
    escalations_received: int = 0
    # Quality
    reopen_rate: float = 0
    customer_impact_score: float = 0
    # Privacy
    is_anonymized: bool = False
    # Risk
    burnout: BurnoutIndicators | None = None

    @computed_field
    @property
    def resolution_rate(self) -> float:
        """Percentage of handled incidents that were resolved."""
        return (
            round(self.incidents_resolved / self.incidents_handled * 100, 1)
            if self.incidents_handled
            else 0
        )

    @computed_field
    @property
    def efficiency_score(self) -> float:
        """Composite efficiency score (0-100)."""
        if not self.incidents_handled:
            return 0
        # Weighted: 50% resolution rate, 30% response time, 20% reopen rate
        resp_score = max(
            0, 100 - self.avg_response_time_min * 2
        )  # Penalize slow response
        reopen_score = max(0, 100 - self.reopen_rate * 5)  # Penalize reopens
        return round(
            self.resolution_rate * 0.5 + resp_score * 0.3 + reopen_score * 0.2, 1
        )

    def anonymize(self) -> "EngineerMetrics":
        """Return anonymized copy for privacy-safe sharing."""
        return self.model_copy(
            update={
                "engineer_id": f"eng_{hash(self.engineer_id) % 10000:04d}",
                "engineer_name": "Anonymous",
                "is_anonymized": True,
            }
        )


class TeamMetrics(BaseModel):
    """Team-level performance metrics aligned with DORA framework."""

    team_id: str
    team_name: str
    period: PerformancePeriod
    # Incident counts
    total_incidents: int = 0
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    # DORA metrics
    mttr_minutes: float = Field(default=0, description="Mean Time To Resolve")
    mtta_minutes: float = Field(default=0, description="Mean Time To Acknowledge")
    mttd_minutes: float = Field(default=0, description="Mean Time To Detect")
    # Rates
    sla_compliance_rate: float = 0
    first_call_resolution_rate: float = 0
    escalation_rate: float = 0
    reopen_rate: float = 0
    # Workload
    workload_distribution: WorkloadDistribution | None = None
    oncall_burden_hours: float = 0
    avg_incidents_per_engineer: float = 0
    # Team health
    team_burnout_risk: BurnoutRisk = BurnoutRisk.LOW
    engineers_at_risk: int = 0
    # Benchmarks
    tier: PerformanceTier = PerformanceTier.MEDIUM
    industry_percentile: int | None = None

    @computed_field
    @property
    def change_failure_rate(self) -> float:
        """DORA metric: percentage of incidents caused by deployments."""
        return (
            round(
                self.incidents_by_severity.get("deploy", 0)
                / self.total_incidents
                * 100,
                1,
            )
            if self.total_incidents
            else 0
        )

    @computed_field
    @property
    def incidents_per_day(self) -> float:
        """Average incidents per day in period."""
        return round(self.total_incidents / max(1, self.period.days), 2)

    @computed_field
    @property
    def critical_incident_ratio(self) -> float:
        """Percentage of incidents that were critical severity."""
        critical = self.incidents_by_severity.get(
            "critical", 0
        ) + self.incidents_by_severity.get("sev1", 0)
        return (
            round(critical / self.total_incidents * 100, 1)
            if self.total_incidents
            else 0
        )


class Benchmark(BaseModel):
    """Industry benchmark for metric comparison.

    Thresholds define boundaries between performance tiers.
    Based on DORA State of DevOps research.
    """

    name: str
    metric: str
    elite_threshold: float
    high_threshold: float
    medium_threshold: float
    unit: str = ""
    lower_is_better: bool = True
    source: str = "DORA"

    def classify(self, value: float) -> PerformanceTier:
        """Classify a value against this benchmark."""
        thresholds = [
            (self.elite_threshold, PerformanceTier.ELITE),
            (self.high_threshold, PerformanceTier.HIGH),
            (self.medium_threshold, PerformanceTier.MEDIUM),
        ]
        for thresh, tier in thresholds:
            if (value <= thresh) if self.lower_is_better else (value >= thresh):
                return tier
        return PerformanceTier.LOW

    def distance_to_next_tier(
        self, value: float
    ) -> tuple[PerformanceTier | None, float]:
        """Calculate distance to next performance tier."""
        current = self.classify(value)
        if current == PerformanceTier.ELITE:
            return None, 0
        thresholds = {
            PerformanceTier.HIGH: self.elite_threshold,
            PerformanceTier.MEDIUM: self.high_threshold,
            PerformanceTier.LOW: self.medium_threshold,
        }
        target = thresholds.get(current, self.medium_threshold)
        distance = abs(value - target)
        next_tier = {
            PerformanceTier.HIGH: PerformanceTier.ELITE,
            PerformanceTier.MEDIUM: PerformanceTier.HIGH,
            PerformanceTier.LOW: PerformanceTier.MEDIUM,
        }
        return next_tier.get(current), distance


class PeriodComparison(BaseModel):
    """Comparison between two time periods."""

    current: PerformancePeriod
    previous: PerformancePeriod
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    improved: list[str] = Field(
        default_factory=list, description="Metrics that improved"
    )
    degraded: list[str] = Field(
        default_factory=list, description="Metrics that degraded"
    )
    stable: list[str] = Field(
        default_factory=list, description="Metrics with minimal change"
    )
    summary: str = ""

    @computed_field
    @property
    def overall_trend(self) -> str:
        """Overall trend direction."""
        if len(self.improved) > len(self.degraded) + 1:
            return "improving"
        if len(self.degraded) > len(self.improved) + 1:
            return "declining"
        return "stable"


class LeaderboardEntry(BaseModel):
    """Leaderboard entry for gamification features."""

    rank: int
    engineer_id: str
    engineer_name: str
    score: float
    metric_name: str
    badge: str | None = None  # Emoji badge: 🥇🥈🥉🏅
    is_anonymized: bool = False

    @computed_field
    @property
    def display_rank(self) -> str:
        """Formatted rank with badge."""
        return f"{self.badge} #{self.rank}" if self.badge else f"#{self.rank}"


class PerformanceReport(BaseModel):
    """Comprehensive performance report for management review."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    period: PerformancePeriod
    team_metrics: TeamMetrics
    engineer_metrics: list[EngineerMetrics] = Field(default_factory=list)
    comparison: PeriodComparison | None = None
    benchmarks: dict[str, PerformanceTier] = Field(default_factory=dict)
    highlights: list[str] = Field(
        default_factory=list, description="Positive observations"
    )
    concerns: list[str] = Field(
        default_factory=list, description="Areas needing attention"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )

    @computed_field
    @property
    def executive_summary(self) -> str:
        """One-line executive summary."""
        tier = self.team_metrics.tier.value.upper()
        pct = self.team_metrics.industry_percentile or 50
        return f"{self.team_metrics.team_name}: {tier} performer ({pct}th percentile) with {self.team_metrics.total_incidents} incidents"
