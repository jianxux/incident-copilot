"""Analytics tracker for calculating MTTR and other metrics."""

import statistics
from datetime import UTC, datetime, timedelta

import structlog

from .models import IncidentMetrics, MTTRStats, PeriodComparison
from .store import AnalyticsStore, analytics_store

logger = structlog.get_logger()


class AnalyticsTracker:
    """
    Track and calculate incident analytics.

    Provides methods for recording events and computing MTTR statistics.
    """

    def __init__(self, store: AnalyticsStore | None = None):
        self.store = store or analytics_store

    async def record_incident_triggered(
        self,
        incident_id: str,
        triggered_at: datetime,
        service_name: str,
        severity: str,
    ) -> IncidentMetrics:
        """Record an incident trigger event."""
        logger.info(
            "analytics_incident_triggered",
            incident_id=incident_id,
            service=service_name,
            severity=severity,
        )
        return await self.store.record_event(
            incident_id=incident_id,
            event_type="triggered",
            timestamp=triggered_at,
            service_name=service_name,
            severity=severity,
        )

    async def record_incident_acknowledged(
        self,
        incident_id: str,
        acknowledged_at: datetime,
    ) -> IncidentMetrics:
        """Record an incident acknowledgement event."""
        logger.info("analytics_incident_acknowledged", incident_id=incident_id)
        return await self.store.record_event(
            incident_id=incident_id,
            event_type="acknowledged",
            timestamp=acknowledged_at,
        )

    async def record_incident_resolved(
        self,
        incident_id: str,
        resolved_at: datetime,
    ) -> IncidentMetrics:
        """Record an incident resolution event."""
        logger.info("analytics_incident_resolved", incident_id=incident_id)
        return await self.store.record_event(
            incident_id=incident_id,
            event_type="resolved",
            timestamp=resolved_at,
        )

    async def record_context_card_delivered(
        self,
        incident_id: str,
        delivered_at: datetime,
    ) -> IncidentMetrics:
        """Record context card delivery event."""
        logger.info("analytics_context_card_delivered", incident_id=incident_id)
        return await self.store.record_event(
            incident_id=incident_id,
            event_type="context_card_delivered",
            timestamp=delivered_at,
        )

    async def calculate_mttr_stats(
        self,
        start: datetime,
        end: datetime,
        period_label: str | None = None,
        service_name: str | None = None,
        severity: str | None = None,
    ) -> MTTRStats:
        """
        Calculate MTTR statistics for a time period.

        Args:
            start: Period start datetime
            end: Period end datetime
            period_label: Human-readable period label (e.g., "7d", "Last Week")
            service_name: Optional filter by service
            severity: Optional filter by severity

        Returns:
            MTTRStats with calculated metrics
        """
        metrics = await self.store.get_metrics_for_period(
            start=start,
            end=end,
            service_name=service_name,
            severity=severity,
        )

        # Calculate MTTR values (only for resolved incidents)
        mttr_values = []
        tta_values = []  # Time to acknowledge
        ttc_values = []  # Time to context card

        for m in metrics:
            if m.time_to_resolve_seconds is not None:
                mttr_values.append(m.time_to_resolve_seconds)
            if m.time_to_acknowledge_seconds is not None:
                tta_values.append(m.time_to_acknowledge_seconds)
            if m.time_to_context_card_seconds is not None:
                ttc_values.append(m.time_to_context_card_seconds)

        # Calculate statistics
        mean_mttr = statistics.mean(mttr_values) if mttr_values else None
        median_mttr = statistics.median(mttr_values) if mttr_values else None
        p90_mttr = self._percentile(mttr_values, 90) if mttr_values else None
        mean_tta = statistics.mean(tta_values) if tta_values else None
        mean_ttc = statistics.mean(ttc_values) if ttc_values else None

        if period_label is None:
            days = (end - start).days
            period_label = f"{days}d"

        return MTTRStats(
            period=period_label,
            period_start=start,
            period_end=end,
            mean_mttr_seconds=mean_mttr,
            median_mttr_seconds=median_mttr,
            p90_mttr_seconds=p90_mttr,
            incidents_count=len(metrics),
            resolved_count=len(mttr_values),
            mean_time_to_acknowledge_seconds=mean_tta,
            mean_time_to_context_card_seconds=mean_ttc,
        )

    async def compare_periods(
        self,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
        service_name: str | None = None,
        severity: str | None = None,
    ) -> PeriodComparison:
        """
        Compare MTTR statistics between two time periods.

        Args:
            current_start: Current period start
            current_end: Current period end
            previous_start: Previous period start
            previous_end: Previous period end
            service_name: Optional filter by service
            severity: Optional filter by severity

        Returns:
            PeriodComparison with both periods and trend analysis
        """
        current_stats = await self.calculate_mttr_stats(
            start=current_start,
            end=current_end,
            period_label="Current Period",
            service_name=service_name,
            severity=severity,
        )

        previous_stats = await self.calculate_mttr_stats(
            start=previous_start,
            end=previous_end,
            period_label="Previous Period",
            service_name=service_name,
            severity=severity,
        )

        return PeriodComparison.from_stats(current_stats, previous_stats)

    async def get_stats_for_days(
        self,
        days: int,
        service_name: str | None = None,
        severity: str | None = None,
    ) -> MTTRStats:
        """Get MTTR stats for the last N days."""
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        return await self.calculate_mttr_stats(
            start=start,
            end=end,
            period_label=f"{days}d",
            service_name=service_name,
            severity=severity,
        )

    async def compare_to_previous(
        self,
        days: int,
        service_name: str | None = None,
        severity: str | None = None,
    ) -> PeriodComparison:
        """Compare current period to the same duration previous period."""
        now = datetime.now(UTC)
        current_end = now
        current_start = now - timedelta(days=days)
        previous_end = current_start
        previous_start = previous_end - timedelta(days=days)

        return await self.compare_periods(
            current_start=current_start,
            current_end=current_end,
            previous_start=previous_start,
            previous_end=previous_end,
            service_name=service_name,
            severity=severity,
        )

    def _percentile(self, data: list[float], percentile: int) -> float:
        """Calculate percentile value from data."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (percentile / 100)
        f = int(k)
        c = f + 1
        if c >= len(sorted_data):
            return sorted_data[f]
        return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)
