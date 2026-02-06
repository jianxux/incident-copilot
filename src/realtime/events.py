"""Real-time event types for WebSocket communication.

This module defines all event types that can be sent over WebSocket connections.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """Types of real-time events."""

    # Incident events
    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_RESOLVED = "incident.resolved"
    INCIDENT_REOPENED = "incident.reopened"
    INCIDENT_ACKNOWLEDGED = "incident.acknowledged"

    # Comment events
    COMMENT_ADDED = "comment.added"
    COMMENT_UPDATED = "comment.updated"
    COMMENT_DELETED = "comment.deleted"

    # Timeline events
    TIMELINE_EVENT = "timeline.event"

    # Assignment events
    ASSIGNMENT_CHANGED = "assignment.changed"

    # Collaboration events
    USER_JOINED = "user.joined"
    USER_LEFT = "user.left"
    USER_TYPING = "user.typing"

    # System events
    HEARTBEAT = "system.heartbeat"
    ERROR = "system.error"
    CONNECTED = "system.connected"
    RECONNECTED = "system.reconnected"


class RealtimeEvent(BaseModel):
    """Base class for all real-time events.

    All events follow this structure:
    - id: Unique event ID for deduplication and last-event-id tracking
    - type: Event type from EventType enum
    - tenant_id: Tenant this event belongs to
    - incident_id: Optional incident ID (for incident-specific events)
    - timestamp: When the event occurred
    - payload: Event-specific data
    - actor_id: Optional user ID who triggered the event
    """

    id: str = Field(description="Unique event ID for deduplication")
    type: EventType = Field(description="Event type")
    tenant_id: str = Field(description="Tenant ID")
    incident_id: str | None = Field(default=None, description="Incident ID if applicable")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = Field(default=None, description="User who triggered the event")
    actor_name: str | None = Field(default=None, description="Display name of actor")

    model_config = ConfigDict(use_enum_values=True)


# --- Payload Models ---


class IncidentCreatedPayload(BaseModel):
    """Payload for incident.created events."""

    incident_id: str
    title: str
    severity: str
    service_name: str
    triggered_at: datetime
    alert_url: str | None = None


class IncidentUpdatedPayload(BaseModel):
    """Payload for incident.updated events."""

    incident_id: str
    changes: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of field name to {old, new} values",
    )
    updated_fields: list[str] = Field(default_factory=list)


class IncidentResolvedPayload(BaseModel):
    """Payload for incident.resolved events."""

    incident_id: str
    resolution_summary: str | None = None
    resolved_at: datetime = Field(default_factory=datetime.utcnow)
    time_to_resolve_minutes: int | None = None


class CommentAddedPayload(BaseModel):
    """Payload for comment.added events."""

    comment_id: str
    incident_id: str
    author_id: str
    author_name: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_internal: bool = False


class CommentUpdatedPayload(BaseModel):
    """Payload for comment.updated events."""

    comment_id: str
    incident_id: str
    content: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CommentDeletedPayload(BaseModel):
    """Payload for comment.deleted events."""

    comment_id: str
    incident_id: str


class TimelineEventPayload(BaseModel):
    """Payload for timeline.event events."""

    event_id: str
    incident_id: str
    event_type: str  # e.g., "alert_triggered", "runbook_executed", "deploy_detected"
    title: str
    description: str | None = None
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssignmentChangedPayload(BaseModel):
    """Payload for assignment.changed events."""

    incident_id: str
    previous_assignees: list[str] = Field(default_factory=list)
    new_assignees: list[str] = Field(default_factory=list)
    assigned_by: str | None = None


class UserPresencePayload(BaseModel):
    """Payload for user.joined/user.left events."""

    user_id: str
    user_name: str
    avatar_url: str | None = None
    incident_id: str | None = None


class UserTypingPayload(BaseModel):
    """Payload for user.typing events."""

    user_id: str
    user_name: str
    incident_id: str
    is_typing: bool = True


class HeartbeatPayload(BaseModel):
    """Payload for system.heartbeat events."""

    server_time: datetime = Field(default_factory=datetime.utcnow)
    connection_id: str


class ErrorPayload(BaseModel):
    """Payload for system.error events."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectedPayload(BaseModel):
    """Payload for system.connected events."""

    connection_id: str
    server_time: datetime = Field(default_factory=datetime.utcnow)
    rooms: list[str] = Field(default_factory=list)
    last_event_id: str | None = None


# --- Helper Functions ---


def create_event(
    event_type: EventType,
    tenant_id: str,
    payload: BaseModel | dict,
    incident_id: str | None = None,
    actor_id: str | None = None,
    actor_name: str | None = None,
    event_id: str | None = None,
) -> RealtimeEvent:
    """Create a new RealtimeEvent with auto-generated ID.

    Args:
        event_type: Type of event
        tenant_id: Tenant ID
        payload: Event payload (Pydantic model or dict)
        incident_id: Optional incident ID
        actor_id: Optional user ID who triggered the event
        actor_name: Optional display name of actor
        event_id: Optional event ID (auto-generated if not provided)

    Returns:
        RealtimeEvent instance
    """
    import uuid

    if event_id is None:
        event_id = str(uuid.uuid4())

    payload_dict = payload.model_dump() if isinstance(payload, BaseModel) else payload

    return RealtimeEvent(
        id=event_id,
        type=event_type,
        tenant_id=tenant_id,
        incident_id=incident_id,
        payload=payload_dict,
        actor_id=actor_id,
        actor_name=actor_name,
    )
