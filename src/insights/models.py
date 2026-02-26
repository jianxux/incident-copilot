"""Data models for AI Insights and Pattern Detection."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class InsightType(StrEnum):
    """Types of insights detected."""

    RECURRING_INCIDENT = "recurring_incident"
    TIME_BASED_PATTERN = "time_based_pattern"
    SEVERITY_TREND = "severity_trend"
    SERVICE_DEPENDENCY = "service_dependency"
    CASCADING_FAILURE = "cascading_failure"
    SPIKE_DETECTED = "spike_detected"
    UNUSUAL_TIME = "unusual_time"
    CORRELATION = "correlation"


class PatternType(StrEnum):
    """Types of patterns detected."""

    RECURRING = "recurring"
    TEMPORAL = "temporal"
    SEVERITY_ESCALATION = "severity_escalation"
    FREQUENCY_CHANGE = "frequency_change"


class AnomalyType(StrEnum):
    """Types of anomalies detected."""

    SPIKE = "spike"
    CASCADING = "cascading"
    UNUSUAL_HOUR = "unusual_hour"
    UNUSUAL_DAY = "unusual_day"
    OUTLIER = "outlier"


class Severity(StrEnum):
    """Insight severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# --- Pattern Models ---


class RecurringPattern(BaseModel):
    """A recurring incident pattern."""

    pattern_id: str
    service_name: str
    title_pattern: str
    incident_count: int
    first_seen: datetime
    last_seen: datetime
    avg_time_between_hours: float | None = None
    affected_incident_ids: list[str] = Field(default_factory=list)
    suggested_action: str | None = None


class TimeBasedPattern(BaseModel):
    """Time-based incident pattern (e.g., every Monday, 3am)."""

    pattern_id: str
    service_name: str | None = None
    pattern_description: str
    hour_of_day: int | None = None  # 0-23
    day_of_week: int | None = None  # 0=Monday, 6=Sunday
    incident_count: int
    confidence: float = Field(ge=0.0, le=1.0)
    affected_incident_ids: list[str] = Field(default_factory=list)


class SeverityTrend(BaseModel):
    """Trend in incident severity over time."""

    service_name: str | None = None
    trend_direction: str  # "increasing", "decreasing", "stable"
    period_days: int
    start_severity_avg: float
    end_severity_avg: float
    change_percent: float
    incidents_analyzed: int


# --- Anomaly Models ---


class AnomalyDetection(BaseModel):
    """A detected anomaly in incident data."""

    anomaly_id: str
    anomaly_type: AnomalyType
    detected_at: datetime
    severity: Severity
    description: str
    affected_services: list[str] = Field(default_factory=list)
    affected_incident_ids: list[str] = Field(default_factory=list)
    metric_value: float | None = None
    baseline_value: float | None = None
    deviation_percent: float | None = None


class IncidentSpike(BaseModel):
    """A spike in incident count."""

    spike_id: str
    detected_at: datetime
    window_hours: int
    incident_count: int
    baseline_count: float
    spike_factor: float  # How many times above baseline
    affected_services: list[str] = Field(default_factory=list)
    affected_incident_ids: list[str] = Field(default_factory=list)


class CascadingFailure(BaseModel):
    """A cascading failure across services."""

    cascade_id: str
    detected_at: datetime
    trigger_service: str
    trigger_incident_id: str
    affected_services: list[str]
    affected_incident_ids: list[str]
    cascade_window_minutes: int
    total_incidents: int


# --- Insight Models ---


class Insight(BaseModel):
    """A high-level insight combining patterns and anomalies."""

    insight_id: str
    insight_type: InsightType
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    severity: Severity
    title: str
    description: str
    affected_services: list[str] = Field(default_factory=list)
    affected_incident_ids: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    is_acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    metadata: dict = Field(default_factory=dict)


class InsightSummary(BaseModel):
    """Summary of insights for a time period."""

    period_start: datetime
    period_end: datetime
    total_insights: int
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    top_affected_services: list[str] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    analysis_pending: bool = False


# --- Service Dependency Models ---


class ServiceDependency(BaseModel):
    """A detected service dependency."""

    source_service: str
    target_service: str
    correlation_strength: float = Field(ge=0.0, le=1.0)
    co_occurrence_count: int
    avg_time_lag_seconds: float | None = None
    last_observed: datetime


class ServiceDependencyMap(BaseModel):
    """Map of service dependencies."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dependencies: list[ServiceDependency] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)


# --- Digest Models ---


class DigestPeriod(StrEnum):
    """Digest time periods."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class IncidentDigest(BaseModel):
    """AI-generated digest of incidents and insights."""

    digest_id: str
    period: DigestPeriod
    period_start: datetime
    period_end: datetime
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Summary stats
    total_incidents: int
    resolved_incidents: int
    avg_mttr_minutes: float | None = None
    mttr_change_percent: float | None = None

    # Breakdown by severity
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    # Top affected services
    top_services: list[tuple[str, int]] = Field(default_factory=list)

    # Insights
    new_patterns: list[RecurringPattern] = Field(default_factory=list)
    active_anomalies: list[AnomalyDetection] = Field(default_factory=list)
    severity_trend: SeverityTrend | None = None

    # AI-generated content
    executive_summary: str | None = None
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risk_assessment: str | None = None


# --- Analysis Request/Response Models ---


class AnalysisRequest(BaseModel):
    """Request to trigger analysis."""

    service_name: str | None = None
    lookback_days: int = 30
    include_patterns: bool = True
    include_anomalies: bool = True
    include_dependencies: bool = True
    generate_ai_summary: bool = True


class AnalysisResult(BaseModel):
    """Result of an analysis run."""

    analysis_id: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    lookback_days: int
    incidents_analyzed: int
    patterns_found: int
    anomalies_found: int
    insights_generated: int
    patterns: list[RecurringPattern] = Field(default_factory=list)
    anomalies: list[AnomalyDetection] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    service_dependencies: ServiceDependencyMap | None = None
    errors: list[str] = Field(default_factory=list)
