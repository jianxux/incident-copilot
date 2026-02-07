"""Cross-incident analysis and service dependency mapping."""

from collections import defaultdict
from datetime import datetime, timedelta

import structlog

from ..analytics.models import IncidentMetrics
from .models import (
    ServiceDependency,
    ServiceDependencyMap,
)

logger = structlog.get_logger()


class IncidentAnalyzer:
    """Analyzes incidents for cross-cutting patterns and dependencies."""

    def __init__(
        self,
        correlation_window_minutes: int = 30,
        min_co_occurrences: int = 2,
    ):
        self.correlation_window_minutes = correlation_window_minutes
        self.min_co_occurrences = min_co_occurrences

    async def analyze_service_dependencies(
        self,
        incidents: list[IncidentMetrics],
    ) -> ServiceDependencyMap:
        """
        Analyze incidents to infer service dependencies.

        Services that frequently have incidents close together in time
        are likely dependent on each other.
        """
        if not incidents:
            return ServiceDependencyMap(dependencies=[], services=[])

        # Sort incidents by time
        sorted_incidents = sorted(incidents, key=lambda x: x.triggered_at)

        # Track co-occurrences
        co_occurrences: dict[tuple[str, str], list[tuple[datetime, float]]] = (
            defaultdict(list)
        )

        # Find incidents that occur within the correlation window
        for i, incident_a in enumerate(sorted_incidents):
            window_end = incident_a.triggered_at + timedelta(
                minutes=self.correlation_window_minutes
            )

            for incident_b in sorted_incidents[i + 1 :]:
                if incident_b.triggered_at > window_end:
                    break

                if incident_a.service_name == incident_b.service_name:
                    continue

                # Record the co-occurrence with time lag
                time_lag = (
                    incident_b.triggered_at - incident_a.triggered_at
                ).total_seconds()

                # Use ordered pair to track direction
                pair = (incident_a.service_name, incident_b.service_name)
                co_occurrences[pair].append((incident_a.triggered_at, time_lag))

        # Build dependency list
        dependencies = []
        all_services = set()

        for (source, target), occurrences in co_occurrences.items():
            if len(occurrences) < self.min_co_occurrences:
                continue

            all_services.add(source)
            all_services.add(target)

            # Calculate correlation strength based on frequency
            total_incidents = len(incidents)
            correlation_strength = min(1.0, len(occurrences) / (total_incidents * 0.1))

            # Calculate average time lag
            avg_lag = sum(t[1] for t in occurrences) / len(occurrences)
            last_observed = max(t[0] for t in occurrences)

            dep = ServiceDependency(
                source_service=source,
                target_service=target,
                correlation_strength=correlation_strength,
                co_occurrence_count=len(occurrences),
                avg_time_lag_seconds=avg_lag,
                last_observed=last_observed,
            )
            dependencies.append(dep)

        # Sort by correlation strength
        dependencies.sort(key=lambda x: x.correlation_strength, reverse=True)

        logger.info(
            "service_dependencies_analyzed",
            dependencies_found=len(dependencies),
            services_involved=len(all_services),
        )

        return ServiceDependencyMap(
            dependencies=dependencies,
            services=sorted(all_services),
        )

    async def find_correlated_services(
        self,
        incidents: list[IncidentMetrics],
        service_name: str,
    ) -> list[ServiceDependency]:
        """
        Find services that are correlated with the given service.

        Returns services that frequently have incidents around the same
        time as the specified service.
        """
        dep_map = await self.analyze_service_dependencies(incidents)

        # Filter to dependencies involving our service
        related = [
            d
            for d in dep_map.dependencies
            if d.source_service == service_name or d.target_service == service_name
        ]

        return related

    async def get_service_impact_ranking(
        self,
        incidents: list[IncidentMetrics],
    ) -> list[tuple[str, int, float]]:
        """
        Rank services by their incident impact.

        Returns list of (service_name, incident_count, severity_score).
        """
        service_stats: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "severity_sum": 0}
        )

        severity_weights = {
            "critical": 5,
            "high": 4,
            "medium": 3,
            "low": 2,
            "info": 1,
        }

        for incident in incidents:
            service_stats[incident.service_name]["count"] += 1
            service_stats[incident.service_name][
                "severity_sum"
            ] += severity_weights.get(incident.severity, 3)

        # Calculate ranking
        ranking = []
        for service, stats in service_stats.items():
            avg_severity = stats["severity_sum"] / stats["count"]
            # Impact score combines frequency and severity
            impact_score = stats["count"] * avg_severity
            ranking.append((service, stats["count"], impact_score))

        # Sort by impact score descending
        ranking.sort(key=lambda x: x[2], reverse=True)

        return ranking

    async def analyze_resolution_patterns(
        self,
        incidents: list[IncidentMetrics],
    ) -> dict:
        """
        Analyze resolution patterns across services.

        Returns insights about which services resolve fastest/slowest.
        """
        service_resolution_times: dict[str, list[float]] = defaultdict(list)

        for incident in incidents:
            if incident.time_to_resolve_seconds:
                service_resolution_times[incident.service_name].append(
                    incident.time_to_resolve_seconds
                )

        analysis = {}
        for service, times in service_resolution_times.items():
            if times:
                analysis[service] = {
                    "avg_mttr_minutes": (sum(times) / len(times)) / 60,
                    "min_mttr_minutes": min(times) / 60,
                    "max_mttr_minutes": max(times) / 60,
                    "resolved_count": len(times),
                }

        return analysis

    async def identify_hotspots(
        self,
        incidents: list[IncidentMetrics],
        window_hours: int = 24,
    ) -> list[dict]:
        """
        Identify time periods with unusually high incident activity.

        Returns list of hotspot periods with their characteristics.
        """
        if not incidents:
            return []

        # Group incidents by time window
        sorted_incidents = sorted(incidents, key=lambda x: x.triggered_at)
        window = timedelta(hours=window_hours)

        hotspots = []
        i = 0

        while i < len(sorted_incidents):
            window_start = sorted_incidents[i].triggered_at
            window_end = window_start + window

            # Count incidents in this window
            window_incidents = []
            j = i
            while (
                j < len(sorted_incidents)
                and sorted_incidents[j].triggered_at < window_end
            ):
                window_incidents.append(sorted_incidents[j])
                j += 1

            # Check if this is a hotspot (significantly above average)
            avg_per_window = len(incidents) / max(
                1,
                (
                    sorted_incidents[-1].triggered_at - sorted_incidents[0].triggered_at
                ).days
                / (window_hours / 24),
            )

            if (
                len(window_incidents) > avg_per_window * 2
                and len(window_incidents) >= 3
            ):
                services_affected = list(
                    set(inc.service_name for inc in window_incidents)
                )
                hotspots.append(
                    {
                        "window_start": window_start,
                        "window_end": window_end,
                        "incident_count": len(window_incidents),
                        "services_affected": services_affected,
                        "spike_factor": len(window_incidents) / max(1, avg_per_window),
                    }
                )

            # Move to next non-overlapping window
            i = j if j > i else i + 1

        logger.info("hotspots_identified", count=len(hotspots))
        return hotspots
