"""Real-time WebSocket updates for Incident Copilot.

This module provides WebSocket-based real-time updates for incidents,
comments, timeline events, and other collaborative features.

Usage:
    from src.realtime import connection_manager, broadcaster, RealtimeEvent

    # Broadcast an event
    await broadcaster.broadcast_incident_update(tenant_id, incident_id, data)

    # Or use the manager directly
    await connection_manager.broadcast_to_room(room_id, event)
"""

from .broadcaster import broadcaster
from .events import (
    EventType,
    RealtimeEvent,
    AssignmentChangedPayload,
    CommentAddedPayload,
    IncidentCreatedPayload,
    IncidentResolvedPayload,
    IncidentUpdatedPayload,
    TimelineEventPayload,
)
from .manager import ConnectionManager, connection_manager
from .routes import router as realtime_router

__all__ = [
    # Manager
    "ConnectionManager",
    "connection_manager",
    # Events
    "EventType",
    "RealtimeEvent",
    "IncidentCreatedPayload",
    "IncidentUpdatedPayload",
    "IncidentResolvedPayload",
    "CommentAddedPayload",
    "TimelineEventPayload",
    "AssignmentChangedPayload",
    # Broadcaster
    "broadcaster",
    # Router
    "realtime_router",
]
