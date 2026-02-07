"""Performance analytics data models."""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class PerformanceTier(str, Enum):
    """Performance tier classification."""
    ELITE = "elite"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BurnoutRisk(str, Enum):
    """Burnout risk levels."""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class PerformancePeriod(BaseModel):
    """Time period for performance analysis."""
    start: datetime
    end: datetime
    label: str = ""
    
    @computed_field
    @property
    def days(self) -> int:
        return (self.end - self.start).days
    
    @classmethod
    def last_n_days(cls, n: int, label: str = "") -> "PerformancePeriod":
        end = datetime.utcnow()
        start = end - timedelta(days=n)
        return cls(start=start, end=end, label=label or f"Last {n} days")
    
    @classmethod
    def week(cls) -> "PerformancePeriod":
        return cls.last_n_days(7, "Last 7 days")
    
    @classmethod
    def month(cls) -> "PerformancePeriod":
        return cls.last_n_days(30, "Last 30 days")
    
    @classmethod
    def quarter(cls) -> "PerformancePeriod":
        return cls.last_n_days(90, "Last 90 days")


class MetricValue(BaseModel):
    """Single metric with value and metadata."""
    name: str
    value: float
    unit: str = ""
    trend: Optional[float] = None  # % change from previous period
    tier: Optional[PerformanceTier] = None
    
    @computed_field
    @property
    def trend_direction(self) -> Optional[str]:
        if self.trend is None:
            return None
        if self.trend > 5:
            return "up"
        elif self.trend < -5:
            return "down"
        return "stable"


class WorkloadDistribution(BaseModel):
    """Workload distribution metrics."""
    gini_coefficient: float = Field(ge=0, le=1, description="0=equal, 1=unequal")
    top_10_pct_share: float = Field(description="% of work done by top 10%")
    bottom_50_pct_share: float = Field(description="% of work done by bottom 50%")
    std_deviation: float
    is_balanced: bool = Field(default=True)
    
    @classmethod
    def from_workloads(cls, workloads: list[float]) -> "WorkloadDistribution":
        if not workloads:
            return cls(gini_coefficient=0, top_10_pct_share=0, bottom_50_pct_share=0, std_deviation=0)
        
        import statistics
        n = len(workloads)
        sorted_loads = sorted(workloads)
        total = sum(sorted_loads)
        
        if total == 0:
            return cls(gini_coefficient=0, top_10_pct_share=0, bottom_50_pct_share=0, std_deviation=0)
        
        # Gini coefficient
        cumulative = 0
        gini_sum = 0
        for i, load in enumerate(sorted_loads):
            cumulative += load
            gini_sum += (2 * (i + 1) - n - 1) * load
        gini = gini_sum / (n * total) if n > 0 else 0
        gini = max(0, min(1, gini))
        
        # Top 10% share
        top_n = max(1, n // 10)
        top_share = sum(sorted_loads[-top_n:]) / total * 100
        
        # Bottom 50% share
        bottom_n = n // 2
        bottom_share = sum(sorted_loads[:bottom_n]) / total * 100 if bottom_n > 0 else 0
        
        std_dev = statistics.stdev(workloads) if len(workloads) > 1 else 0
        
        return cls(
            gini_coefficient=round(gini, 3),
            top_10_pct_share=round(top_share, 1),
            bottom_50_pct_share=round(bottom_share, 1),
            std_deviation=round(std_dev, 2),
            is_balanced=gini < 0.3
        )


class BurnoutIndicators(BaseModel):
    """Burnout risk assessment."""
    risk_level: BurnoutRisk
    risk_score: float = Field(ge=0, le=100)
    factors: list[str] = Field(default_factory=list)
    consecutive_oncall_days: int = 0
    after_hours_incidents: int = 0
    high_severity_count: int = 0
    avg_incident_duration_hours: float = 0
    recommendations: list[str] = Field(default_factory=list)


class EngineerMetrics(BaseModel):
    """Individual engineer performance metrics."""
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
    reopen_rate: float = 0  # %
    customer_impact_score: float = 0
    # Privacy flag
    is_anonymized: bool = False
    # Burnout
    burnout: Optional[BurnoutIndicators] = None
    
    @computed_field
    @property
    def resolution_rate(self) -> float:
        if self.incidents_handled == 0:
            return 0
        return round(self.incidents_resolved / self.incidents_handled * 100, 1)
    
    def anonymize(self) -> "EngineerMetrics":
        """Return anonymized copy for privacy."""
        return self.model_copy(update={
            "engineer_id": f"eng_{hash(self.engineer_id) % 10000:04d}",
            "engineer_name": "Anonymous",
            "is_anonymized": True
        })


class TeamMetrics(BaseModel):
    """Team-level performance metrics."""
    team_id: str
    team_name: str
    period: PerformancePeriod
    # Aggregate metrics
    total_incidents: int = 0
    incidents_by_severity: dict[str, int] = Field(default_factory=dict)
    mttr_minutes: float = Field(default=0, description="Mean Time To Resolve")
    mtta_minutes: float = Field(default=0, description="Mean Time To Acknowledge")
    mttd_minutes: float = Field(default=0, description="Mean Time To Detect")
    # Rates
    sla_compliance_rate: float = 0  # %
    first_call_resolution_rate: float = 0  # %
    escalation_rate: float = 0  # %
    reopen_rate: float = 0  # %
    # Workload
    workload_distribution: Optional[WorkloadDistribution] = None
    oncall_burden_hours: float = 0
    avg_incidents_per_engineer: float = 0
    # Team health
    team_burnout_risk: BurnoutRisk = BurnoutRisk.LOW
    engineers_at_risk: int = 0
    # Comparisons
    tier: PerformanceTier = PerformanceTier.MEDIUM
    industry_percentile: Optional[int] = None
    
    @computed_field
    @property
    def change_failure_rate(self) -> float:
        """DORA metric: incidents caused by changes."""
        deploy_related = self.incidents_by_severity.get("deploy", 0)
        return round(deploy_related / self.total_incidents * 100, 1) if self.total_incidents else 0


class Benchmark(BaseModel):
    """Industry benchmark for comparison."""
    name: str
    metric: str
    elite_threshold: float
    high_threshold: float
    medium_threshold: float
    unit: str = ""
    lower_is_better: bool = True
    source: str = "DORA"
    
    def classify(self, value: float) -> PerformanceTier:
        if self.lower_is_better:
            if value <= self.elite_threshold:
                return PerformanceTier.ELITE
            elif value <= self.high_threshold:
                return PerformanceTier.HIGH
            elif value <= self.medium_threshold:
                return PerformanceTier.MEDIUM
            return PerformanceTier.LOW
        else:
            if value >= self.elite_threshold:
                return PerformanceTier.ELITE
            elif value >= self.high_threshold:
                return PerformanceTier.HIGH
            elif value >= self.medium_threshold:
                return PerformanceTier.MEDIUM
            return PerformanceTier.LOW


class PeriodComparison(BaseModel):
    """Comparison between two periods."""
    current: PerformancePeriod
    previous: PerformancePeriod
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    improved: list[str] = Field(default_factory=list)
    degraded: list[str] = Field(default_factory=list)
    stable: list[str] = Field(default_factory=list)
    summary: str = ""


class LeaderboardEntry(BaseModel):
    """Leaderboard entry for gamification."""
    rank: int
    engineer_id: str
    engineer_name: str
    score: float
    metric_name: str
    badge: Optional[str] = None
    is_anonymized: bool = False


class PerformanceReport(BaseModel):
    """Comprehensive performance report."""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    period: PerformancePeriod
    team_metrics: TeamMetrics
    engineer_metrics: list[EngineerMetrics] = Field(default_factory=list)
    comparison: Optional[PeriodComparison] = None
    benchmarks: dict[str, PerformanceTier] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
