"""Data models for analytics and MTTR tracking."""

from datetime import datetime

from pydantic import BaseModel


class IncidentMetrics(BaseModel):
    """Metrics for a single incident lifecycle."""

    incident_id: str
    triggered_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    context_card_delivered_at: datetime | None = None
    service_name: str
    severity: str  # critical, high, medium, low, info

    @property
    def time_to_acknowledge_seconds(self) -> float | None:
        """Time from trigger to acknowledgement in seconds."""
        if self.triggered_at and self.acknowledged_at:
            return (self.acknowledged_at - self.triggered_at).total_seconds()
        return None

    @property
    def time_to_resolve_seconds(self) -> float | None:
        """Time from trigger to resolution in seconds."""
        if self.triggered_at and self.resolved_at:
            return (self.resolved_at - self.triggered_at).total_seconds()
        return None

    @property
    def time_to_context_card_seconds(self) -> float | None:
        """Time from trigger to context card delivery in seconds."""
        if self.triggered_at and self.context_card_delivered_at:
            return (self.context_card_delivered_at - self.triggered_at).total_seconds()
        return None


class MTTRStats(BaseModel):
    """MTTR statistics for a time period."""

    period: str  # e.g., "7d", "30d", "90d", or date range like "2024-01-01 to 2024-01-07"
    period_start: datetime
    period_end: datetime
    mean_mttr_seconds: float | None = None
    median_mttr_seconds: float | None = None
    p90_mttr_seconds: float | None = None
    incidents_count: int = 0
    resolved_count: int = 0
    improvement_percent: float | None = None  # Compared to previous period

    # Additional metrics
    mean_time_to_acknowledge_seconds: float | None = None
    mean_time_to_context_card_seconds: float | None = None

    @property
    def mean_mttr_minutes(self) -> float | None:
        """Mean MTTR in minutes."""
        if self.mean_mttr_seconds is not None:
            return self.mean_mttr_seconds / 60
        return None

    @property
    def median_mttr_minutes(self) -> float | None:
        """Median MTTR in minutes."""
        if self.median_mttr_seconds is not None:
            return self.median_mttr_seconds / 60
        return None

    @property
    def p90_mttr_minutes(self) -> float | None:
        """P90 MTTR in minutes."""
        if self.p90_mttr_seconds is not None:
            return self.p90_mttr_seconds / 60
        return None


class PeriodComparison(BaseModel):
    """Comparison between two time periods."""

    current_period: MTTRStats
    previous_period: MTTRStats
    mttr_change_percent: float | None = None
    incidents_count_change: int = 0
    trend: str = "stable"  # "improving", "degrading", "stable"

    @classmethod
    def from_stats(cls, current: MTTRStats, previous: MTTRStats) -> "PeriodComparison":
        """Create comparison from two stats objects."""
        mttr_change = None
        trend = "stable"

        if current.mean_mttr_seconds and previous.mean_mttr_seconds:
            mttr_change = (
                (previous.mean_mttr_seconds - current.mean_mttr_seconds)
                / previous.mean_mttr_seconds
                * 100
            )
            if mttr_change > 5:
                trend = "improving"
            elif mttr_change < -5:
                trend = "degrading"

        return cls(
            current_period=current,
            previous_period=previous,
            mttr_change_percent=mttr_change,
            incidents_count_change=current.incidents_count - previous.incidents_count,
            trend=trend,
        )
