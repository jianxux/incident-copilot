"""Pattern detection for incidents."""

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import structlog

from ..analytics.models import IncidentMetrics
from .models import (
    RecurringPattern,
    Severity,
    SeverityTrend,
    TimeBasedPattern,
)

logger = structlog.get_logger()


class PatternDetector:
    """Detects patterns in incident data."""

    def __init__(
        self,
        min_occurrences: int = 3,
        similarity_threshold: float = 0.7,
    ):
        self.min_occurrences = min_occurrences
        self.similarity_threshold = similarity_threshold

    async def detect_recurring_patterns(
        self,
        incidents: list[IncidentMetrics],
        service_name: str | None = None,
    ) -> list[RecurringPattern]:
        """
        Detect recurring incident patterns based on title similarity.

        Groups incidents by normalized title patterns and identifies
        those that occur frequently.
        """
        if not incidents:
            return []

        # Filter by service if specified
        if service_name:
            incidents = [i for i in incidents if i.service_name == service_name]

        # Group incidents by normalized title
        title_groups: dict[str, list[IncidentMetrics]] = defaultdict(list)

        for incident in incidents:
            # Normalize the title to find patterns
            # Note: IncidentMetrics doesn't have title, we'll use incident_id as proxy
            # In real impl, we'd need the actual incident title
            normalized = self._normalize_title(incident.incident_id)
            title_groups[normalized].append(incident)

        patterns = []
        for normalized_title, group in title_groups.items():
            if len(group) >= self.min_occurrences:
                # Sort by triggered_at to calculate time between occurrences
                sorted_group = sorted(group, key=lambda x: x.triggered_at)

                # Calculate average time between incidents
                time_diffs = []
                for i in range(1, len(sorted_group)):
                    diff = (
                        sorted_group[i].triggered_at - sorted_group[i - 1].triggered_at
                    )
                    time_diffs.append(diff.total_seconds() / 3600)  # Hours

                avg_time_between = (
                    sum(time_diffs) / len(time_diffs) if time_diffs else None
                )

                pattern = RecurringPattern(
                    pattern_id=self._generate_pattern_id(normalized_title),
                    service_name=sorted_group[0].service_name,
                    title_pattern=normalized_title,
                    incident_count=len(group),
                    first_seen=sorted_group[0].triggered_at,
                    last_seen=sorted_group[-1].triggered_at,
                    avg_time_between_hours=avg_time_between,
                    affected_incident_ids=[i.incident_id for i in group],
                    suggested_action=self._suggest_action_for_pattern(
                        normalized_title, len(group)
                    ),
                )
                patterns.append(pattern)

        logger.info(
            "recurring_patterns_detected",
            count=len(patterns),
            service=service_name,
        )
        return sorted(patterns, key=lambda x: x.incident_count, reverse=True)

    async def detect_time_patterns(
        self,
        incidents: list[IncidentMetrics],
        service_name: str | None = None,
    ) -> list[TimeBasedPattern]:
        """
        Detect time-based patterns (e.g., incidents at specific hours/days).

        Analyzes incident timestamps to find recurring time patterns.
        """
        if not incidents:
            return []

        if service_name:
            incidents = [i for i in incidents if i.service_name == service_name]

        patterns = []

        # Analyze hour-of-day patterns
        hour_counts = Counter(i.triggered_at.hour for i in incidents)
        total_incidents = len(incidents)

        for hour, count in hour_counts.items():
            # Check if this hour has significantly more incidents
            expected = total_incidents / 24
            if count >= self.min_occurrences and count > expected * 2:
                confidence = min(1.0, count / (expected * 3))
                affected = [
                    i.incident_id
                    for i in incidents
                    if i.triggered_at.hour == hour
                ]

                pattern = TimeBasedPattern(
                    pattern_id=self._generate_pattern_id(f"hour_{hour}_{service_name}"),
                    service_name=service_name,
                    pattern_description=f"High incident frequency at {hour:02d}:00",
                    hour_of_day=hour,
                    incident_count=count,
                    confidence=confidence,
                    affected_incident_ids=affected,
                )
                patterns.append(pattern)

        # Analyze day-of-week patterns
        day_counts = Counter(i.triggered_at.weekday() for i in incidents)
        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        for day, count in day_counts.items():
            expected = total_incidents / 7
            if count >= self.min_occurrences and count > expected * 1.5:
                confidence = min(1.0, count / (expected * 2))
                affected = [
                    i.incident_id
                    for i in incidents
                    if i.triggered_at.weekday() == day
                ]

                pattern = TimeBasedPattern(
                    pattern_id=self._generate_pattern_id(f"day_{day}_{service_name}"),
                    service_name=service_name,
                    pattern_description=f"High incident frequency on {day_names[day]}s",
                    day_of_week=day,
                    incident_count=count,
                    confidence=confidence,
                    affected_incident_ids=affected,
                )
                patterns.append(pattern)

        logger.info(
            "time_patterns_detected",
            count=len(patterns),
            service=service_name,
        )
        return sorted(patterns, key=lambda x: x.confidence, reverse=True)

    async def detect_severity_trends(
        self,
        incidents: list[IncidentMetrics],
        period_days: int = 30,
        service_name: str | None = None,
    ) -> SeverityTrend | None:
        """
        Detect trends in incident severity over time.

        Compares severity distribution between first and second half of period.
        """
        if len(incidents) < 6:
            return None

        if service_name:
            incidents = [i for i in incidents if i.service_name == service_name]

        if len(incidents) < 6:
            return None

        # Sort by time
        sorted_incidents = sorted(incidents, key=lambda x: x.triggered_at)

        # Split into two halves
        mid = len(sorted_incidents) // 2
        first_half = sorted_incidents[:mid]
        second_half = sorted_incidents[mid:]

        # Calculate average severity (higher = worse)
        severity_scores = {
            "critical": 5,
            "high": 4,
            "medium": 3,
            "low": 2,
            "info": 1,
        }

        def avg_severity(incs: list[IncidentMetrics]) -> float:
            scores = [severity_scores.get(i.severity, 3) for i in incs]
            return sum(scores) / len(scores) if scores else 3.0

        first_avg = avg_severity(first_half)
        second_avg = avg_severity(second_half)

        change_percent = ((second_avg - first_avg) / first_avg) * 100 if first_avg else 0

        if change_percent > 10:
            trend = "increasing"
        elif change_percent < -10:
            trend = "decreasing"
        else:
            trend = "stable"

        return SeverityTrend(
            service_name=service_name,
            trend_direction=trend,
            period_days=period_days,
            start_severity_avg=first_avg,
            end_severity_avg=second_avg,
            change_percent=change_percent,
            incidents_analyzed=len(incidents),
        )

    def _normalize_title(self, title: str) -> str:
        """
        Normalize incident title to detect similar patterns.

        Removes timestamps, IDs, and other variable parts.
        """
        # Remove UUIDs
        normalized = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "<UUID>",
            title,
            flags=re.IGNORECASE,
        )

        # Remove timestamps
        normalized = re.sub(
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",
            "<TIMESTAMP>",
            normalized,
        )

        # Remove IP addresses
        normalized = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "<IP>", normalized)

        # Remove numbers that look like IDs
        normalized = re.sub(r"\b\d{5,}\b", "<ID>", normalized)

        # Lowercase and strip
        return normalized.lower().strip()

    def _generate_pattern_id(self, base: str) -> str:
        """Generate a deterministic pattern ID."""
        return hashlib.md5(base.encode()).hexdigest()[:12]

    def _suggest_action_for_pattern(self, pattern: str, count: int) -> str:
        """Generate action suggestion based on pattern."""
        if count >= 10:
            return (
                "This incident recurs frequently. Consider creating an automated "
                "runbook or investigating root cause for permanent fix."
            )
        elif count >= 5:
            return (
                "This incident has occurred multiple times. Review past resolutions "
                "and consider documenting a standard operating procedure."
            )
        else:
            return (
                "Monitor this pattern. If it continues, investigate for "
                "systemic issues."
            )
