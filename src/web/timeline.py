"""Incident Timeline API and utilities."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..models import ContextCard, Severity

logger = structlog.get_logger()


class TimelineEventType(str, Enum):
    """Types of events that appear on the timeline."""

    ALERT_TRIGGERED = "alert_triggered"
    ALERT_ACKNOWLEDGED = "alert_acknowledged"
    ALERT_ESCALATED = "alert_escalated"
    ALERT_RESOLVED = "alert_resolved"

    DEPLOYMENT = "deployment"
    ROLLBACK = "rollback"
    CONFIG_CHANGE = "config_change"

    LOG_ERROR = "log_error"
    LOG_WARNING = "log_warning"
    METRIC_ANOMALY = "metric_anomaly"

    INVESTIGATION_START = "investigation_start"
    ROOT_CAUSE_FOUND = "root_cause_found"
    MITIGATION_START = "mitigation_start"
    MITIGATION_COMPLETE = "mitigation_complete"

    COMMENT = "comment"
    RUNBOOK_LINKED = "runbook_linked"
    SIMILAR_INCIDENT = "similar_incident"

    CONTEXT_ASSEMBLED = "context_assembled"
    NOTIFICATION_SENT = "notification_sent"

    JIRA_TICKET = "jira_ticket"
    POSTMORTEM_CREATED = "postmortem_created"


class TimelineEvent(BaseModel):
    """A single event in the incident timeline."""

    id: str
    timestamp: datetime
    event_type: TimelineEventType
    title: str
    description: str | None = None
    actor: str | None = None  # Who/what triggered this event
    source: str | None = None  # PagerDuty, GitHub, Datadog, etc.
    severity: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # UI hints
    icon: str = "circle"  # FontAwesome icon name
    color: str = "gray"  # Tailwind color (blue, red, green, etc.)
    is_key_event: bool = False  # Highlight important events


class TimelineBuilder:
    """Builds a timeline from incident data and context card."""

    EVENT_ICONS = {
        TimelineEventType.ALERT_TRIGGERED: ("exclamation-circle", "red"),
        TimelineEventType.ALERT_ACKNOWLEDGED: ("check-circle", "blue"),
        TimelineEventType.ALERT_ESCALATED: ("arrow-up", "orange"),
        TimelineEventType.ALERT_RESOLVED: ("check-double", "green"),
        TimelineEventType.DEPLOYMENT: ("rocket", "purple"),
        TimelineEventType.ROLLBACK: ("undo", "yellow"),
        TimelineEventType.CONFIG_CHANGE: ("cog", "slate"),
        TimelineEventType.LOG_ERROR: ("bug", "red"),
        TimelineEventType.LOG_WARNING: ("exclamation-triangle", "yellow"),
        TimelineEventType.METRIC_ANOMALY: ("chart-line", "orange"),
        TimelineEventType.INVESTIGATION_START: ("search", "blue"),
        TimelineEventType.ROOT_CAUSE_FOUND: ("bullseye", "purple"),
        TimelineEventType.MITIGATION_START: ("tools", "yellow"),
        TimelineEventType.MITIGATION_COMPLETE: ("check", "green"),
        TimelineEventType.COMMENT: ("comment", "slate"),
        TimelineEventType.RUNBOOK_LINKED: ("book", "blue"),
        TimelineEventType.SIMILAR_INCIDENT: ("clone", "slate"),
        TimelineEventType.CONTEXT_ASSEMBLED: ("layer-group", "purple"),
        TimelineEventType.NOTIFICATION_SENT: ("bell", "blue"),
        TimelineEventType.JIRA_TICKET: ("ticket-alt", "blue"),
        TimelineEventType.POSTMORTEM_CREATED: ("file-alt", "green"),
    }

    def __init__(self):
        self.events: list[TimelineEvent] = []
        self._event_counter = 0

    def _generate_id(self) -> str:
        """Generate a unique event ID."""
        self._event_counter += 1
        return f"evt_{self._event_counter}"

    def _get_icon_and_color(self, event_type: TimelineEventType) -> tuple[str, str]:
        """Get icon and color for an event type."""
        return self.EVENT_ICONS.get(event_type, ("circle", "gray"))

    def add_event(
        self,
        timestamp: datetime,
        event_type: TimelineEventType,
        title: str,
        description: str | None = None,
        actor: str | None = None,
        source: str | None = None,
        severity: str | None = None,
        metadata: dict | None = None,
        is_key_event: bool = False,
    ) -> TimelineEvent:
        """Add an event to the timeline."""
        icon, color = self._get_icon_and_color(event_type)

        event = TimelineEvent(
            id=self._generate_id(),
            timestamp=timestamp,
            event_type=event_type,
            title=title,
            description=description,
            actor=actor,
            source=source,
            severity=severity,
            metadata=metadata or {},
            icon=icon,
            color=color,
            is_key_event=is_key_event,
        )

        self.events.append(event)
        return event

    def build_from_context_card(
        self, card: ContextCard, incident_data: dict
    ) -> list[TimelineEvent]:
        """Build timeline from a context card and incident data."""

        # Alert triggered
        if card.triggered_at:
            self.add_event(
                timestamp=card.triggered_at,
                event_type=TimelineEventType.ALERT_TRIGGERED,
                title=f"Alert triggered: {card.alert_title or 'Unknown'}",
                description=card.alert_description,
                source=card.source.value if card.source else "Unknown",
                severity=card.severity.value if card.severity else None,
                is_key_event=True,
            )

        # Recent deployments (before the alert)
        if card.github and card.github.recent_deployments:
            for deploy in card.github.recent_deployments:
                if deploy.deployed_at and deploy.deployed_at < (
                    card.triggered_at or datetime.now(timezone.utc)
                ):
                    self.add_event(
                        timestamp=deploy.deployed_at,
                        event_type=TimelineEventType.DEPLOYMENT,
                        title=f"Deployment: {deploy.version or 'Unknown'}",
                        description=deploy.commit_message,
                        actor=deploy.deployed_by,
                        source="GitHub",
                        metadata={
                            "sha": deploy.sha,
                            "environment": deploy.environment,
                        },
                    )

        # Log entries (errors/warnings around the incident time)
        if card.logs and card.logs.entries:
            error_count = 0
            for entry in card.logs.entries[:10]:  # Limit to first 10
                if entry.level in ("ERROR", "FATAL"):
                    event_type = TimelineEventType.LOG_ERROR
                    error_count += 1
                elif entry.level == "WARN":
                    event_type = TimelineEventType.LOG_WARNING
                else:
                    continue

                self.add_event(
                    timestamp=entry.timestamp,
                    event_type=event_type,
                    title=f"{entry.level}: {entry.message[:100]}",
                    description=entry.message if len(entry.message) > 100 else None,
                    source=entry.source or "Logs",
                    metadata={"service": entry.service},
                    is_key_event=error_count == 1,  # First error is key
                )

        # Runbooks linked
        if card.runbooks:
            for runbook in card.runbooks:
                self.add_event(
                    timestamp=card.triggered_at or datetime.now(timezone.utc),
                    event_type=TimelineEventType.RUNBOOK_LINKED,
                    title=f"Runbook: {runbook.title}",
                    description=f"Matched with {runbook.match_score}% confidence",
                    source="Runbook Linker",
                    metadata={"url": runbook.url},
                )

        # Similar incidents found
        if card.similar_incidents:
            for similar in card.similar_incidents[:3]:
                self.add_event(
                    timestamp=card.triggered_at or datetime.now(timezone.utc),
                    event_type=TimelineEventType.SIMILAR_INCIDENT,
                    title=f"Similar: {similar.title[:50]}",
                    description=f"Similarity: {similar.similarity_score:.0%}",
                    source="Similarity Search",
                    metadata={
                        "incident_id": similar.incident_id,
                        "resolution": similar.resolution,
                    },
                )

        # Context assembled
        if card.assembly_time_ms:
            self.add_event(
                timestamp=card.triggered_at or datetime.now(timezone.utc),
                event_type=TimelineEventType.CONTEXT_ASSEMBLED,
                title="Context card assembled",
                description=f"Assembled in {card.assembly_time_ms}ms",
                source="Incident Copilot",
                is_key_event=True,
            )

        # Notification sent
        if incident_data.get("notification_sent"):
            self.add_event(
                timestamp=incident_data.get(
                    "notification_time", datetime.now(timezone.utc)
                ),
                event_type=TimelineEventType.NOTIFICATION_SENT,
                title=f"Notification sent to {incident_data.get('notification_channel', 'Slack')}",
                source="Incident Copilot",
            )

        # Sort by timestamp
        self.events.sort(key=lambda e: e.timestamp)

        return self.events

    def get_events(self) -> list[TimelineEvent]:
        """Get all events sorted by timestamp."""
        return sorted(self.events, key=lambda e: e.timestamp)

    def get_key_events(self) -> list[TimelineEvent]:
        """Get only key events."""
        return [e for e in self.get_events() if e.is_key_event]

    def get_events_by_type(self, event_type: TimelineEventType) -> list[TimelineEvent]:
        """Get events of a specific type."""
        return [e for e in self.get_events() if e.event_type == event_type]

    def to_dict(self) -> list[dict]:
        """Convert timeline to list of dicts for JSON serialization."""
        return [
            {
                **event.model_dump(),
                "timestamp": event.timestamp.isoformat(),
            }
            for event in self.get_events()
        ]


def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time (e.g., '5 minutes ago')."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    diff = now - dt
    seconds = int(diff.total_seconds())

    if seconds < 0:
        return "in the future"
    elif seconds < 60:
        return f"{seconds} seconds ago"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''} ago"


def format_duration(start: datetime, end: datetime) -> str:
    """Format duration between two timestamps."""
    diff = end - start
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining = seconds % 60
        return f"{minutes}m {remaining}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
