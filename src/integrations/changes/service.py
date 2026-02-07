"""
Change Tracking Service - Core logic for tracking and correlating changes.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Protocol
from collections import defaultdict

from .models import (
    ChangeEvent,
    ChangeType,
    ChangeSource,
    ChangeStatus,
    RiskLevel,
    Deployment,
    ConfigChange,
    FeatureFlag,
    ChangeFreeze,
    ChangeCorrelation,
    ChangeTimeline,
)


class ChangeCollector(Protocol):
    """Protocol for change collectors."""

    source: ChangeSource

    async def collect_changes(
        self, since: datetime, until: Optional[datetime] = None
    ) -> list[ChangeEvent]:
        """Collect changes from the source."""
        ...

    async def get_deployment(self, deployment_id: str) -> Optional[Deployment]:
        """Get a specific deployment by ID."""
        ...


class ChangeTrackingService:
    """
    Central service for tracking, storing, and correlating changes.
    """

    def __init__(self):
        self._collectors: dict[ChangeSource, ChangeCollector] = {}
        self._changes: dict[str, ChangeEvent] = {}  # In-memory store
        self._freezes: dict[str, ChangeFreeze] = {}
        self._service_changes: dict[str, list[str]] = defaultdict(list)  # service -> change_ids

    def register_collector(self, collector: ChangeCollector) -> None:
        """Register a change collector."""
        self._collectors[collector.source] = collector

    def get_collector(self, source: ChangeSource) -> Optional[ChangeCollector]:
        """Get a registered collector."""
        return self._collectors.get(source)

    # ========== Change Storage ==========

    async def store_change(self, change: ChangeEvent) -> ChangeEvent:
        """Store a change event."""
        # Calculate impact if it's a deployment
        if isinstance(change, Deployment):
            change.impact_score = change.calculate_impact()

        self._changes[change.id] = change

        # Index by service
        if change.service:
            self._service_changes[change.service].append(change.id)
        for svc in change.services:
            if svc != change.service:
                self._service_changes[svc].append(change.id)

        return change

    async def get_change(self, change_id: str) -> Optional[ChangeEvent]:
        """Get a change by ID."""
        return self._changes.get(change_id)

    async def update_change_status(
        self, change_id: str, status: ChangeStatus, completed_at: Optional[datetime] = None
    ) -> Optional[ChangeEvent]:
        """Update the status of a change."""
        change = self._changes.get(change_id)
        if change:
            change.status = status
            if completed_at:
                change.completed_at = completed_at
            elif status in (ChangeStatus.COMPLETED, ChangeStatus.FAILED, ChangeStatus.ROLLED_BACK):
                change.completed_at = datetime.utcnow()
        return change

    # ========== Recent Changes ==========

    async def get_recent_changes(
        self,
        hours: int = 24,
        environment: Optional[str] = None,
        service: Optional[str] = None,
        change_types: Optional[list[ChangeType]] = None,
        limit: int = 100,
    ) -> list[ChangeEvent]:
        """Get recent changes within a time window."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        changes = []
        for change in self._changes.values():
            if change.started_at < cutoff:
                continue

            if environment and change.environment != environment:
                continue

            if service and service not in ([change.service] + change.services):
                continue

            if change_types and change.type not in change_types:
                continue

            changes.append(change)

        # Sort by start time descending
        changes.sort(key=lambda c: c.started_at, reverse=True)
        return changes[:limit]

    async def get_changes_in_window(
        self, start: datetime, end: datetime, **filters
    ) -> list[ChangeEvent]:
        """Get changes within a specific time window."""
        changes = []
        for change in self._changes.values():
            if not (start <= change.started_at <= end):
                continue

            if filters.get("environment") and change.environment != filters["environment"]:
                continue

            if filters.get("service"):
                svc = filters["service"]
                if svc not in ([change.service] + change.services):
                    continue

            if filters.get("source") and change.source != filters["source"]:
                continue

            changes.append(change)

        changes.sort(key=lambda c: c.started_at, reverse=True)
        return changes

    # ========== Change Correlation ==========

    async def correlate_changes(
        self,
        incident_id: str,
        incident_started_at: datetime,
        window_minutes: int = 60,
        service: Optional[str] = None,
        environment: str = "production",
    ) -> ChangeCorrelation:
        """
        Find changes that might have caused an incident.

        Looks for changes in a window before the incident started.
        """
        window_start = incident_started_at - timedelta(minutes=window_minutes)
        window_end = incident_started_at

        # Get changes in the window
        changes = await self.get_changes_in_window(
            start=window_start, end=window_end, environment=environment
        )

        # Filter by service if specified
        if service:
            changes = [c for c in changes if service in ([c.service] + c.services)]

        # Score and rank changes
        scored_changes = await self._score_changes_for_incident(
            changes, incident_started_at, service
        )

        correlation = ChangeCorrelation(
            incident_id=incident_id,
            incident_started_at=incident_started_at,
            changes=scored_changes,
            window_start=window_start,
            window_end=window_end,
        )
        correlation.analyze()

        return correlation

    async def _score_changes_for_incident(
        self, changes: list[ChangeEvent], incident_time: datetime, service: Optional[str]
    ) -> list[ChangeEvent]:
        """Score changes based on likelihood of causing incident."""
        for change in changes:
            score = change.impact_score

            # Closer to incident = higher score
            time_diff = (incident_time - change.started_at).total_seconds() / 60
            if time_diff < 5:
                score += 0.3
            elif time_diff < 15:
                score += 0.2
            elif time_diff < 30:
                score += 0.1

            # Deployments more likely to cause issues
            if change.type == ChangeType.DEPLOYMENT:
                score += 0.15
            elif change.type == ChangeType.CONFIG_CHANGE:
                score += 0.1

            # Direct service match
            if service and change.service == service:
                score += 0.2

            # High risk = higher score
            if change.risk_level == RiskLevel.CRITICAL:
                score += 0.2
            elif change.risk_level == RiskLevel.HIGH:
                score += 0.1

            change.impact_score = min(score, 1.0)

        return sorted(changes, key=lambda c: c.impact_score, reverse=True)

    # ========== Rollback Tracking ==========

    async def record_rollback(self, original_change_id: str, rollback: ChangeEvent) -> ChangeEvent:
        """Record a rollback of a previous change."""
        original = await self.get_change(original_change_id)
        if original:
            original.rolled_back_by = rollback.id
            original.status = ChangeStatus.ROLLED_BACK

        rollback.is_rollback = True
        rollback.rollback_of = original_change_id
        rollback.risk_level = RiskLevel.HIGH  # Rollbacks are high priority

        return await self.store_change(rollback)

    async def get_rollbacks(
        self, hours: int = 24, environment: Optional[str] = None
    ) -> list[ChangeEvent]:
        """Get recent rollbacks."""
        changes = await self.get_recent_changes(hours=hours, environment=environment)
        return [c for c in changes if c.is_rollback]

    # ========== Change Freeze ==========

    async def create_freeze(self, freeze: ChangeFreeze) -> ChangeFreeze:
        """Create a change freeze period."""
        self._freezes[freeze.id] = freeze
        return freeze

    async def get_active_freezes(
        self, environment: Optional[str] = None, at_time: Optional[datetime] = None
    ) -> list[ChangeFreeze]:
        """Get currently active change freezes."""
        check_time = at_time or datetime.utcnow()
        active = []

        for freeze in self._freezes.values():
            if not freeze.is_in_effect(check_time):
                continue

            if environment and environment not in freeze.environments:
                continue

            active.append(freeze)

        return active

    async def check_freeze_violation(self, change: ChangeEvent) -> Optional[ChangeFreeze]:
        """Check if a change violates any active freeze."""
        freezes = await self.get_active_freezes(
            environment=change.environment, at_time=change.started_at
        )

        for freeze in freezes:
            if freeze.blocks_change(change):
                return freeze

        return None

    async def end_freeze(self, freeze_id: str) -> Optional[ChangeFreeze]:
        """End a change freeze early."""
        freeze = self._freezes.get(freeze_id)
        if freeze:
            freeze.is_active = False
            freeze.end_time = datetime.utcnow()
        return freeze

    # ========== Timeline ==========

    async def get_timeline(
        self,
        hours: int = 24,
        environment: Optional[str] = None,
        services: Optional[list[str]] = None,
    ) -> ChangeTimeline:
        """Get a change timeline for visualization."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        events = await self.get_changes_in_window(
            start=start_time, end=end_time, environment=environment
        )

        if services:
            events = [
                e for e in events if e.service in services or any(s in e.services for s in services)
            ]

        freezes = await self.get_active_freezes(environment=environment)

        timeline = ChangeTimeline(
            start_time=start_time, end_time=end_time, events=events, active_freezes=freezes
        )
        timeline.aggregate()

        return timeline

    # ========== Collection ==========

    async def collect_all(
        self, since: datetime, until: Optional[datetime] = None
    ) -> list[ChangeEvent]:
        """Collect changes from all registered collectors."""
        all_changes = []

        tasks = [collector.collect_changes(since, until) for collector in self._collectors.values()]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue  # Log error in production
            all_changes.extend(result)

        # Store all collected changes
        for change in all_changes:
            await self.store_change(change)

        return all_changes

    # ========== Impact Scoring ==========

    async def calculate_impact_score(self, change: ChangeEvent) -> float:
        """Calculate comprehensive impact score for a change."""
        score = 0.0

        # Base score by type
        type_scores = {
            ChangeType.DEPLOYMENT: 0.4,
            ChangeType.CONFIG_CHANGE: 0.3,
            ChangeType.FEATURE_FLAG: 0.2,
            ChangeType.DATABASE_MIGRATION: 0.5,
            ChangeType.INFRASTRUCTURE: 0.5,
            ChangeType.ROLLBACK: 0.6,
        }
        score += type_scores.get(change.type, 0.3)

        # Environment factor
        if change.environment == "production":
            score += 0.2
        elif change.environment == "staging":
            score += 0.1

        # Service count
        total_services = (
            len(set([change.service] + change.services)) if change.service else len(change.services)
        )
        if total_services > 5:
            score += 0.2
        elif total_services > 2:
            score += 0.1

        # Risk level
        risk_scores = {
            RiskLevel.LOW: 0.0,
            RiskLevel.MEDIUM: 0.1,
            RiskLevel.HIGH: 0.2,
            RiskLevel.CRITICAL: 0.3,
        }
        score += risk_scores.get(change.risk_level, 0.1)

        return min(score, 1.0)

    # ========== Statistics ==========

    async def get_change_stats(self, hours: int = 24, environment: Optional[str] = None) -> dict:
        """Get statistics about recent changes."""
        changes = await self.get_recent_changes(hours=hours, environment=environment, limit=1000)

        stats = {
            "total": len(changes),
            "by_type": defaultdict(int),
            "by_source": defaultdict(int),
            "by_status": defaultdict(int),
            "by_risk": defaultdict(int),
            "rollbacks": 0,
            "freeze_violations": 0,
            "avg_impact_score": 0.0,
        }

        if not changes:
            return dict(stats)

        total_impact = 0.0
        for change in changes:
            stats["by_type"][change.type.value] += 1
            stats["by_source"][change.source.value] += 1
            stats["by_status"][change.status.value] += 1
            stats["by_risk"][change.risk_level.value] += 1

            if change.is_rollback:
                stats["rollbacks"] += 1

            total_impact += change.impact_score

        stats["avg_impact_score"] = total_impact / len(changes)

        # Convert defaultdicts to regular dicts
        return {k: dict(v) if isinstance(v, defaultdict) else v for k, v in stats.items()}


# Singleton instance
_service: Optional[ChangeTrackingService] = None


def get_change_service() -> ChangeTrackingService:
    """Get or create the change tracking service singleton."""
    global _service
    if _service is None:
        _service = ChangeTrackingService()
    return _service
