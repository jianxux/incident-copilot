"""In-memory store for insights data."""

import asyncio
from datetime import datetime

from .models import (
    AnomalyDetection,
    CascadingFailure,
    IncidentDigest,
    IncidentSpike,
    Insight,
    InsightType,
    RecurringPattern,
    Severity,
    ServiceDependency,
    TimeBasedPattern,
)


class InsightsStore:
    """
    Thread-safe in-memory store for insights data.

    Designed to be replaced with a database backend later.
    """

    def __init__(self, max_items: int = 10000):
        self._insights: dict[str, Insight] = {}
        self._patterns: dict[str, RecurringPattern] = {}
        self._time_patterns: dict[str, TimeBasedPattern] = {}
        self._anomalies: dict[str, AnomalyDetection] = {}
        self._spikes: dict[str, IncidentSpike] = {}
        self._cascades: dict[str, CascadingFailure] = {}
        self._dependencies: dict[str, ServiceDependency] = {}
        self._digests: dict[str, IncidentDigest] = {}
        self._max_items = max_items
        self._lock = asyncio.Lock()

    # --- Insight Operations ---

    async def save_insight(self, insight: Insight) -> Insight:
        """Save or update an insight."""
        async with self._lock:
            self._insights[insight.insight_id] = insight
            self._trim_dict(self._insights)
            return insight

    async def get_insight(self, insight_id: str) -> Insight | None:
        """Get an insight by ID."""
        return self._insights.get(insight_id)

    async def get_all_insights(
        self,
        insight_type: InsightType | None = None,
        severity: Severity | None = None,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[Insight]:
        """Get all insights with optional filtering."""
        results = []
        for insight in self._insights.values():
            if insight_type and insight.insight_type != insight_type:
                continue
            if severity and insight.severity != severity:
                continue
            if service_name and service_name not in insight.affected_services:
                continue
            results.append(insight)

        # Sort by created_at descending
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

    async def acknowledge_insight(
        self, insight_id: str, acknowledged_by: str
    ) -> Insight | None:
        """Acknowledge an insight."""
        async with self._lock:
            if insight_id in self._insights:
                insight = self._insights[insight_id]
                insight.is_acknowledged = True
                insight.acknowledged_at = datetime.utcnow()
                insight.acknowledged_by = acknowledged_by
                return insight
            return None

    # --- Pattern Operations ---

    async def save_pattern(self, pattern: RecurringPattern) -> RecurringPattern:
        """Save or update a recurring pattern."""
        async with self._lock:
            self._patterns[pattern.pattern_id] = pattern
            self._trim_dict(self._patterns)
            return pattern

    async def get_pattern(self, pattern_id: str) -> RecurringPattern | None:
        """Get a pattern by ID."""
        return self._patterns.get(pattern_id)

    async def get_all_patterns(
        self,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[RecurringPattern]:
        """Get all recurring patterns."""
        results = []
        for pattern in self._patterns.values():
            if service_name and pattern.service_name != service_name:
                continue
            results.append(pattern)

        results.sort(key=lambda x: x.last_seen, reverse=True)
        return results[:limit]

    async def save_time_pattern(self, pattern: TimeBasedPattern) -> TimeBasedPattern:
        """Save or update a time-based pattern."""
        async with self._lock:
            self._time_patterns[pattern.pattern_id] = pattern
            self._trim_dict(self._time_patterns)
            return pattern

    async def get_all_time_patterns(
        self,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[TimeBasedPattern]:
        """Get all time-based patterns."""
        results = []
        for pattern in self._time_patterns.values():
            if service_name and pattern.service_name != service_name:
                continue
            results.append(pattern)

        results.sort(key=lambda x: x.confidence, reverse=True)
        return results[:limit]

    # --- Anomaly Operations ---

    async def save_anomaly(self, anomaly: AnomalyDetection) -> AnomalyDetection:
        """Save or update an anomaly."""
        async with self._lock:
            self._anomalies[anomaly.anomaly_id] = anomaly
            self._trim_dict(self._anomalies)
            return anomaly

    async def get_anomaly(self, anomaly_id: str) -> AnomalyDetection | None:
        """Get an anomaly by ID."""
        return self._anomalies.get(anomaly_id)

    async def get_all_anomalies(
        self,
        service_name: str | None = None,
        severity: Severity | None = None,
        limit: int = 100,
    ) -> list[AnomalyDetection]:
        """Get all anomalies with optional filtering."""
        results = []
        for anomaly in self._anomalies.values():
            if severity and anomaly.severity != severity:
                continue
            if service_name and service_name not in anomaly.affected_services:
                continue
            results.append(anomaly)

        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    async def save_spike(self, spike: IncidentSpike) -> IncidentSpike:
        """Save or update a spike detection."""
        async with self._lock:
            self._spikes[spike.spike_id] = spike
            self._trim_dict(self._spikes)
            return spike

    async def get_all_spikes(self, limit: int = 100) -> list[IncidentSpike]:
        """Get all detected spikes."""
        results = list(self._spikes.values())
        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    async def save_cascade(self, cascade: CascadingFailure) -> CascadingFailure:
        """Save or update a cascading failure."""
        async with self._lock:
            self._cascades[cascade.cascade_id] = cascade
            self._trim_dict(self._cascades)
            return cascade

    async def get_all_cascades(self, limit: int = 100) -> list[CascadingFailure]:
        """Get all cascading failures."""
        results = list(self._cascades.values())
        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    # --- Dependency Operations ---

    async def save_dependency(self, dependency: ServiceDependency) -> ServiceDependency:
        """Save or update a service dependency."""
        key = f"{dependency.source_service}:{dependency.target_service}"
        async with self._lock:
            self._dependencies[key] = dependency
            self._trim_dict(self._dependencies)
            return dependency

    async def get_all_dependencies(
        self, service_name: str | None = None
    ) -> list[ServiceDependency]:
        """Get all service dependencies."""
        results = []
        for dep in self._dependencies.values():
            if service_name and (
                dep.source_service != service_name
                and dep.target_service != service_name
            ):
                continue
            results.append(dep)

        results.sort(key=lambda x: x.correlation_strength, reverse=True)
        return results

    # --- Digest Operations ---

    async def save_digest(self, digest: IncidentDigest) -> IncidentDigest:
        """Save or update a digest."""
        async with self._lock:
            self._digests[digest.digest_id] = digest
            self._trim_dict(self._digests)
            return digest

    async def get_digest(self, digest_id: str) -> IncidentDigest | None:
        """Get a digest by ID."""
        return self._digests.get(digest_id)

    async def get_latest_digest(
        self, period: str | None = None
    ) -> IncidentDigest | None:
        """Get the latest digest, optionally filtered by period."""
        digests = list(self._digests.values())
        if period:
            digests = [d for d in digests if d.period.value == period]

        if not digests:
            return None

        return max(digests, key=lambda x: x.generated_at)

    async def get_all_digests(self, limit: int = 50) -> list[IncidentDigest]:
        """Get all digests."""
        results = list(self._digests.values())
        results.sort(key=lambda x: x.generated_at, reverse=True)
        return results[:limit]

    # --- Utility Methods ---

    def _trim_dict(self, d: dict) -> None:
        """Trim dictionary to max size by removing oldest items."""
        if len(d) > self._max_items:
            # For now, remove first items (oldest by insertion order in Python 3.7+)
            items_to_remove = len(d) - self._max_items
            keys_to_remove = list(d.keys())[:items_to_remove]
            for key in keys_to_remove:
                del d[key]

    async def clear(self) -> None:
        """Clear all stored data (for testing)."""
        async with self._lock:
            self._insights.clear()
            self._patterns.clear()
            self._time_patterns.clear()
            self._anomalies.clear()
            self._spikes.clear()
            self._cascades.clear()
            self._dependencies.clear()
            self._digests.clear()

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        return {
            "insights_count": len(self._insights),
            "patterns_count": len(self._patterns),
            "time_patterns_count": len(self._time_patterns),
            "anomalies_count": len(self._anomalies),
            "spikes_count": len(self._spikes),
            "cascades_count": len(self._cascades),
            "dependencies_count": len(self._dependencies),
            "digests_count": len(self._digests),
        }


# Global insights store instance
insights_store = InsightsStore()
