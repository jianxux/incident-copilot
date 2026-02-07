"""
Realtime Event Types

Event definitions for incident updates, comments, status changes, and SLA warnings.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Types of realtime events."""

    # Incident events
    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_RESOLVED = "incident.resolved"
    INCIDENT_ESCALATED = "incident.escalated"
    INCIDENT_ASSIGNED = "incident.assigned"
    INCIDENT_ACKNOWLEDGED = "incident.acknowledged"

    # Comment events
    COMMENT_ADDED = "comment.added"
    COMMENT_UPDATED = "comment.updated"
    COMMENT_DELETED = "comment.deleted"

    # Status events
    STATUS_CHANGED = "status.changed"
    SEVERITY_CHANGED = "severity.changed"

    # SLA events
    SLA_WARNING = "sla.warning"
    SLA_BREACHED = "sla.breached"

    # Timeline events
    TIMELINE_ENTRY = "timeline.entry"

    # Presence events
    USER_JOINED = "presence.joined"
    USER_LEFT = "presence.left"
    USER_TYPING = "presence.typing"


class BaseEvent(BaseModel):
    """Base event structure."""

    event_type: EventType
    event_id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = "system"  # Who triggered the event

    # Routing info
    incident_id: str | None = None
    service_id: str | None = None
    team_id: str | None = None

    def get_room_keys(self) -> list[str]:
        """Get all room keys this event should be broadcast to."""
        keys = ["global:all"]
        if self.incident_id:
            keys.append(f"incident:{self.incident_id}")
        if self.service_id:
            keys.append(f"service:{self.service_id}")
        if self.team_id:
            keys.append(f"team:{self.team_id}")
        return keys

    def to_message(self) -> dict[str, Any]:
        """Convert event to WebSocket message payload."""
        return {
            "event_type": self.event_type.value,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "data": self.get_event_data(),
        }

    def get_event_data(self) -> dict[str, Any]:
        """Get event-specific data. Override in subclasses."""
        return {}


class IncidentCreated(BaseEvent):
    """Event when a new incident is created."""

    event_type: EventType = EventType.INCIDENT_CREATED
    title: str
    severity: str
    description: str | None = None
    created_by: str

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity,
            "description": self.description,
            "created_by": self.created_by,
        }


class IncidentUpdated(BaseEvent):
    """Event when an incident is updated."""

    event_type: EventType = EventType.INCIDENT_UPDATED
    changes: dict[str, Any] = Field(default_factory=dict)
    updated_by: str

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "changes": self.changes,
            "updated_by": self.updated_by,
        }


class IncidentResolved(BaseEvent):
    """Event when an incident is resolved."""

    event_type: EventType = EventType.INCIDENT_RESOLVED
    resolution_summary: str | None = None
    resolved_by: str
    resolution_time_minutes: int | None = None

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "resolution_summary": self.resolution_summary,
            "resolved_by": self.resolved_by,
            "resolution_time_minutes": self.resolution_time_minutes,
        }


class IncidentAssigned(BaseEvent):
    """Event when an incident is assigned."""

    event_type: EventType = EventType.INCIDENT_ASSIGNED
    assignee_id: str
    assignee_name: str
    assigned_by: str
    previous_assignee_id: str | None = None

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "assignee_id": self.assignee_id,
            "assignee_name": self.assignee_name,
            "assigned_by": self.assigned_by,
            "previous_assignee_id": self.previous_assignee_id,
        }


class IncidentAcknowledged(BaseEvent):
    """Event when an incident is acknowledged."""

    event_type: EventType = EventType.INCIDENT_ACKNOWLEDGED
    acknowledged_by: str

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "acknowledged_by": self.acknowledged_by,
        }


class IncidentEscalated(BaseEvent):
    """Event when an incident is escalated."""

    event_type: EventType = EventType.INCIDENT_ESCALATED
    escalated_by: str
    escalation_level: int
    reason: str | None = None

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "escalated_by": self.escalated_by,
            "escalation_level": self.escalation_level,
            "reason": self.reason,
        }


class CommentAdded(BaseEvent):
    """Event when a comment is added to an incident."""

    event_type: EventType = EventType.COMMENT_ADDED
    comment_id: str
    content: str
    author_id: str
    author_name: str
    is_internal: bool = False

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "comment_id": self.comment_id,
            "content": self.content,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "is_internal": self.is_internal,
        }


class CommentUpdated(BaseEvent):
    """Event when a comment is updated."""

    event_type: EventType = EventType.COMMENT_UPDATED
    comment_id: str
    content: str
    edited_by: str

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "comment_id": self.comment_id,
            "content": self.content,
            "edited_by": self.edited_by,
        }


class CommentDeleted(BaseEvent):
    """Event when a comment is deleted."""

    event_type: EventType = EventType.COMMENT_DELETED
    comment_id: str
    deleted_by: str

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "comment_id": self.comment_id,
            "deleted_by": self.deleted_by,
        }


class StatusChanged(BaseEvent):
    """Event when incident status changes."""

    event_type: EventType = EventType.STATUS_CHANGED
    old_status: str
    new_status: str
    changed_by: str

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "changed_by": self.changed_by,
        }


class SeverityChanged(BaseEvent):
    """Event when incident severity changes."""

    event_type: EventType = EventType.SEVERITY_CHANGED
    old_severity: str
    new_severity: str
    changed_by: str
    reason: str | None = None

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "old_severity": self.old_severity,
            "new_severity": self.new_severity,
            "changed_by": self.changed_by,
            "reason": self.reason,
        }


class SLAWarning(BaseEvent):
    """Event when SLA is approaching breach."""

    event_type: EventType = EventType.SLA_WARNING
    sla_type: str  # "response", "acknowledgement", "resolution"
    deadline: datetime
    time_remaining_minutes: int

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "sla_type": self.sla_type,
            "deadline": self.deadline.isoformat(),
            "time_remaining_minutes": self.time_remaining_minutes,
        }


class SLABreached(BaseEvent):
    """Event when SLA is breached."""

    event_type: EventType = EventType.SLA_BREACHED
    sla_type: str
    deadline: datetime
    breach_time: datetime = Field(default_factory=datetime.utcnow)

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "sla_type": self.sla_type,
            "deadline": self.deadline.isoformat(),
            "breach_time": self.breach_time.isoformat(),
        }


class TimelineEntry(BaseEvent):
    """Generic timeline entry event."""

    event_type: EventType = EventType.TIMELINE_ENTRY
    entry_type: str
    content: str
    actor_id: str | None = None
    actor_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_event_data(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "entry_type": self.entry_type,
            "content": self.content,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "metadata": self.metadata,
        }


class PresenceEvent(BaseEvent):
    """Presence change event."""

    user_id: str
    user_name: str
    room_key: str

    def get_room_keys(self) -> list[str]:
        # Presence events only go to the specific room
        return [self.room_key]

    def get_event_data(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "room_key": self.room_key,
        }


class UserJoined(PresenceEvent):
    """Event when user joins a room."""

    event_type: EventType = EventType.USER_JOINED


class UserLeft(PresenceEvent):
    """Event when user leaves a room."""

    event_type: EventType = EventType.USER_LEFT


class UserTyping(PresenceEvent):
    """Event when user is typing."""

    event_type: EventType = EventType.USER_TYPING


# Event factory for deserializing events
EVENT_CLASSES: dict[EventType, type[BaseEvent]] = {
    EventType.INCIDENT_CREATED: IncidentCreated,
    EventType.INCIDENT_UPDATED: IncidentUpdated,
    EventType.INCIDENT_RESOLVED: IncidentResolved,
    EventType.INCIDENT_ASSIGNED: IncidentAssigned,
    EventType.INCIDENT_ACKNOWLEDGED: IncidentAcknowledged,
    EventType.INCIDENT_ESCALATED: IncidentEscalated,
    EventType.COMMENT_ADDED: CommentAdded,
    EventType.COMMENT_UPDATED: CommentUpdated,
    EventType.COMMENT_DELETED: CommentDeleted,
    EventType.STATUS_CHANGED: StatusChanged,
    EventType.SEVERITY_CHANGED: SeverityChanged,
    EventType.SLA_WARNING: SLAWarning,
    EventType.SLA_BREACHED: SLABreached,
    EventType.TIMELINE_ENTRY: TimelineEntry,
    EventType.USER_JOINED: UserJoined,
    EventType.USER_LEFT: UserLeft,
    EventType.USER_TYPING: UserTyping,
}
