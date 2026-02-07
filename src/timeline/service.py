"""Timeline service for managing incident timelines."""

from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

from .models import (
    EventSeverity,
    EventSource,
    EventType,
    TimelineEntry,
    TimelineEvent,
    TimelineFilter,
    TimelineGap,
    TimelineSummary,
)

# Event type display properties
EVENT_DISPLAY = {
    EventType.STATUS_CHANGE: {"icon": "🔄", "color": "#3498db", "milestone": True},
    EventType.ASSIGNMENT: {"icon": "👤", "color": "#9b59b6", "milestone": False},
    EventType.COMMENT: {"icon": "💬", "color": "#95a5a6", "milestone": False},
    EventType.DEPLOYMENT: {"icon": "🚀", "color": "#e67e22", "milestone": True},
    EventType.ALERT: {"icon": "🚨", "color": "#e74c3c", "milestone": True},
    EventType.ESCALATION: {"icon": "📈", "color": "#c0392b", "milestone": True},
    EventType.NOTIFICATION: {"icon": "📢", "color": "#1abc9c", "milestone": False},
    EventType.ACTION_TAKEN: {"icon": "⚡", "color": "#2ecc71", "milestone": False},
    EventType.METRIC_ANOMALY: {"icon": "📊", "color": "#f39c12", "milestone": False},
    EventType.LOG_PATTERN: {"icon": "📝", "color": "#7f8c8d", "milestone": False},
    EventType.ROLLBACK: {"icon": "⏪", "color": "#e74c3c", "milestone": True},
    EventType.MITIGATION: {"icon": "🛡️", "color": "#27ae60", "milestone": True},
    EventType.RESOLUTION: {"icon": "✅", "color": "#2ecc71", "milestone": True},
    EventType.POSTMORTEM: {"icon": "📋", "color": "#34495e", "milestone": True},
    EventType.MANUAL: {"icon": "✍️", "color": "#bdc3c7", "milestone": False},
}

# Gap severity thresholds (in seconds)
GAP_THRESHOLDS = {
    "info": 300,  # 5 minutes
    "warning": 900,  # 15 minutes
    "critical": 1800,  # 30 minutes
}


class TimelineService:
    """Service for managing incident timelines."""

    def __init__(self):
        self._events: dict[str, list[TimelineEvent]] = {}  # incident_id -> events
        self._event_hooks: list[Callable[[TimelineEvent], None]] = []

    def register_hook(self, hook: Callable[[TimelineEvent], None]) -> None:
        """Register a hook to be called when events are added."""
        self._event_hooks.append(hook)

    async def add_event(self, event: TimelineEvent) -> TimelineEvent:
        """Add an event to the timeline."""
        if event.incident_id not in self._events:
            self._events[event.incident_id] = []

        self._events[event.incident_id].append(event)
        self._events[event.incident_id].sort(key=lambda e: e.timestamp)

        # Trigger hooks
        for hook in self._event_hooks:
            try:
                hook(event)
            except Exception:
                pass  # Don't let hook failures break event addition

        return event

    async def add_events(self, events: list[TimelineEvent]) -> list[TimelineEvent]:
        """Add multiple events to the timeline."""
        for event in events:
            await self.add_event(event)
        return events

    async def get_event(self, incident_id: str, event_id: UUID) -> TimelineEvent | None:
        """Get a specific event by ID."""
        events = self._events.get(incident_id, [])
        for event in events:
            if event.id == event_id:
                return event
        return None

    async def get_timeline(
        self, incident_id: str, filters: TimelineFilter | None = None
    ) -> list[TimelineEntry]:
        """Get timeline entries for an incident with optional filtering."""
        events = self._events.get(incident_id, [])

        if filters:
            events = self._apply_filters(events, filters)

        # Find reference time (first event)
        reference_time = events[0].timestamp if events else datetime.utcnow()

        entries = []
        for event in events:
            display = EVENT_DISPLAY.get(event.event_type, {})
            entry = TimelineEntry(
                event=event,
                relative_time=self._format_relative_time(
                    event.timestamp, reference_time
                ),
                is_milestone=display.get("milestone", False),
                icon=display.get("icon"),
                color=display.get("color"),
                display_group=self._get_display_group(event),
            )
            entries.append(entry)

        return entries

    async def get_summary(self, incident_id: str) -> TimelineSummary:
        """Get summary statistics for an incident timeline."""
        events = self._events.get(incident_id, [])

        type_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        milestones: list[UUID] = []

        for event in events:
            type_counts[event.event_type.value] = (
                type_counts.get(event.event_type.value, 0) + 1
            )
            source_counts[event.source.value] = (
                source_counts.get(event.source.value, 0) + 1
            )
            if EVENT_DISPLAY.get(event.event_type, {}).get("milestone"):
                milestones.append(event.id)

        gaps = self._detect_gaps(events)

        first = events[0].timestamp if events else None
        last = events[-1].timestamp if events else None
        duration = (last - first).total_seconds() if first and last else None

        return TimelineSummary(
            incident_id=incident_id,
            total_events=len(events),
            event_counts_by_type=type_counts,
            event_counts_by_source=source_counts,
            first_event=first,
            last_event=last,
            duration_seconds=duration,
            gaps=gaps,
            key_milestones=milestones,
        )

    async def reconstruct_timeline(
        self, incident_id: str, collected_events: list[TimelineEvent]
    ) -> list[TimelineEntry]:
        """Reconstruct timeline from collected events, merging with existing."""
        existing = self._events.get(incident_id, [])
        existing_ids = {e.id for e in existing}

        # Add new events that don't exist
        for event in collected_events:
            if event.id not in existing_ids:
                await self.add_event(event)

        return await self.get_timeline(incident_id)

    async def annotate_event(
        self, incident_id: str, event_id: UUID, annotation: str
    ) -> TimelineEvent | None:
        """Add an annotation to an event."""
        event = await self.get_event(incident_id, event_id)
        if event:
            event.annotations.append(annotation)
            return event
        return None

    async def tag_event(
        self, incident_id: str, event_id: UUID, tags: list[str]
    ) -> TimelineEvent | None:
        """Add tags to an event."""
        event = await self.get_event(incident_id, event_id)
        if event:
            event.tags.extend(tags)
            event.tags = list(set(event.tags))  # Dedupe
            return event
        return None

    async def link_events(
        self, incident_id: str, event_id: UUID, related_ids: list[UUID]
    ) -> TimelineEvent | None:
        """Link related events together."""
        event = await self.get_event(incident_id, event_id)
        if event:
            event.related_events.extend(related_ids)
            event.related_events = list(set(event.related_events))
            return event
        return None

    async def delete_event(self, incident_id: str, event_id: UUID) -> bool:
        """Delete an event from the timeline."""
        events = self._events.get(incident_id, [])
        for i, event in enumerate(events):
            if event.id == event_id:
                del events[i]
                return True
        return False

    def _apply_filters(
        self, events: list[TimelineEvent], filters: TimelineFilter
    ) -> list[TimelineEvent]:
        """Apply filters to events list."""
        result = events

        if filters.event_types:
            result = [e for e in result if e.event_type in filters.event_types]

        if filters.sources:
            result = [e for e in result if e.source in filters.sources]

        if filters.severities:
            result = [e for e in result if e.severity in filters.severities]

        if filters.start_time:
            result = [e for e in result if e.timestamp >= filters.start_time]

        if filters.end_time:
            result = [e for e in result if e.timestamp <= filters.end_time]

        if filters.actors:
            result = [e for e in result if e.actor in filters.actors]

        if filters.tags:
            result = [e for e in result if any(t in e.tags for t in filters.tags)]

        if filters.search_query:
            query = filters.search_query.lower()
            result = [
                e
                for e in result
                if query in e.title.lower()
                or (e.description and query in e.description.lower())
            ]

        return result

    def _detect_gaps(self, events: list[TimelineEvent]) -> list[TimelineGap]:
        """Detect gaps in the timeline."""
        gaps = []

        for i in range(len(events) - 1):
            current = events[i]
            next_event = events[i + 1]
            duration = (next_event.timestamp - current.timestamp).total_seconds()

            if duration >= GAP_THRESHOLDS["info"]:
                severity = "info"
                if duration >= GAP_THRESHOLDS["critical"]:
                    severity = "critical"
                elif duration >= GAP_THRESHOLDS["warning"]:
                    severity = "warning"

                gaps.append(
                    TimelineGap(
                        start_time=current.timestamp,
                        end_time=next_event.timestamp,
                        duration_seconds=duration,
                        preceding_event_id=current.id,
                        following_event_id=next_event.id,
                        severity=severity,
                    )
                )

        return gaps

    def _format_relative_time(self, timestamp: datetime, reference: datetime) -> str:
        """Format timestamp relative to reference time."""
        delta = timestamp - reference
        total_seconds = int(delta.total_seconds())

        if total_seconds == 0:
            return "T+0"

        prefix = "+" if total_seconds > 0 else "-"
        total_seconds = abs(total_seconds)

        if total_seconds < 60:
            return f"T{prefix}{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"T{prefix}{minutes}m"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"T{prefix}{hours}h{minutes}m" if minutes else f"T{prefix}{hours}h"
        else:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            return f"T{prefix}{days}d{hours}h" if hours else f"T{prefix}{days}d"

    def _get_display_group(self, event: TimelineEvent) -> str:
        """Determine display group for event clustering."""
        # Group by source and type for visual clustering
        return f"{event.source.value}:{event.event_type.value}"


# Singleton instance
_timeline_service: TimelineService | None = None


def get_timeline_service() -> TimelineService:
    """Get or create the timeline service singleton."""
    global _timeline_service
    if _timeline_service is None:
        _timeline_service = TimelineService()
    return _timeline_service
