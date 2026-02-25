"""In-memory store for analytics data."""

import asyncio
from datetime import UTC, datetime

from .models import IncidentMetrics


def _to_utc_aware(dt: datetime) -> datetime:
    """Normalize datetimes to timezone-aware UTC, treating naive values as UTC."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class AnalyticsStore:
    """
    Thread-safe in-memory store for incident metrics.

    Designed to be replaced with a database backend later.
    """

    def __init__(self, max_incidents: int = 10000):
        self._metrics: dict[str, IncidentMetrics] = {}
        self._max_incidents = max_incidents
        self._lock = asyncio.Lock()

    async def record_event(
        self,
        incident_id: str,
        event_type: str,
        timestamp: datetime,
        service_name: str | None = None,
        severity: str | None = None,
    ) -> IncidentMetrics:
        """
        Record an incident lifecycle event.

        Event types: triggered, acknowledged, resolved, context_card_delivered
        """
        async with self._lock:
            if incident_id in self._metrics:
                metrics = self._metrics[incident_id]
            else:
                if service_name is None:
                    service_name = "unknown"
                if severity is None:
                    severity = "medium"

                metrics = IncidentMetrics(
                    incident_id=incident_id,
                    triggered_at=timestamp,
                    service_name=service_name,
                    severity=severity,
                )
                self._metrics[incident_id] = metrics

            # Update the appropriate timestamp based on event type
            if event_type == "triggered":
                metrics.triggered_at = timestamp
                if service_name:
                    metrics.service_name = service_name
                if severity:
                    metrics.severity = severity
            elif event_type == "acknowledged":
                metrics.acknowledged_at = timestamp
            elif event_type == "resolved":
                metrics.resolved_at = timestamp
            elif event_type == "context_card_delivered":
                metrics.context_card_delivered_at = timestamp

            # Trim if over max (remove oldest by triggered_at)
            if len(self._metrics) > self._max_incidents:
                oldest_id = min(
                    self._metrics.keys(),
                    key=lambda k: self._metrics[k].triggered_at,
                )
                del self._metrics[oldest_id]

            return metrics

    async def get_incident_metrics(self, incident_id: str) -> IncidentMetrics | None:
        """Get metrics for a specific incident."""
        return self._metrics.get(incident_id)

    async def get_all_metrics(self) -> list[IncidentMetrics]:
        """Get all incident metrics, sorted by triggered_at descending."""
        return sorted(
            self._metrics.values(),
            key=lambda m: m.triggered_at,
            reverse=True,
        )

    async def get_metrics_for_period(
        self,
        start: datetime,
        end: datetime,
        service_name: str | None = None,
        severity: str | None = None,
    ) -> list[IncidentMetrics]:
        """Get metrics for incidents within a time period."""
        start_utc = _to_utc_aware(start)
        end_utc = _to_utc_aware(end)
        results = []
        for metrics in self._metrics.values():
            triggered_at_utc = _to_utc_aware(metrics.triggered_at)
            if start_utc <= triggered_at_utc <= end_utc:
                if service_name and metrics.service_name != service_name:
                    continue
                if severity and metrics.severity != severity:
                    continue
                results.append(metrics)
        return sorted(
            results,
            key=lambda m: _to_utc_aware(m.triggered_at),
            reverse=True,
        )

    async def clear(self):
        """Clear all stored metrics (for testing)."""
        async with self._lock:
            self._metrics.clear()


# Global analytics store instance
analytics_store = AnalyticsStore()
