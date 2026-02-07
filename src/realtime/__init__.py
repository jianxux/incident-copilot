"""
Realtime WebSocket Module

Provides real-time updates for incident management via WebSocket connections.

Features:
- Room-based subscriptions (per-incident, per-service, per-team, global)
- Presence tracking (who's viewing an incident)
- Event broadcasting (incident updates, comments, status changes, SLA warnings)
- Heartbeat/ping-pong for connection health
- Rate limiting per connection
- Authentication via token in connection params

Usage:
    from fastapi import FastAPI
    from realtime import router, publish
    from realtime.events import CommentAdded

    app = FastAPI()
    app.include_router(router)

    # Publish events from your application code
    await publish(CommentAdded(
        incident_id="inc-123",
        comment_id="cmt-456",
        content="Investigation started",
        author_id="user-1",
        author_name="Jane Doe",
    ))

WebSocket Protocol:
    Connect: ws://host/ws/connect?token=YOUR_TOKEN

    Client -> Server:
        {"type": "subscribe", "payload": {"room_type": "incident", "room_id": "inc-123"}}
        {"type": "unsubscribe", "payload": {"room_key": "incident:inc-123"}}
        {"type": "ping", "payload": {"echo": "data"}}
        {"type": "presence_update", "payload": {"room_key": "incident:inc-123", "status": "editing"}}

    Server -> Client:
        {"type": "connected", "payload": {"connection_id": "abc123", "user_id": "user-1"}}
        {"type": "subscribed", "payload": {"room_key": "incident:inc-123", "presence": [...]}}
        {"type": "event", "payload": {"event_type": "comment.added", "data": {...}}}
        {"type": "error", "payload": {"error": "message", "code": "ERROR_CODE"}}
"""

from .routes import router, publish
from .manager import manager, ConnectionManager
from .handlers import MessageHandler, create_handler
from .models import (
    MessageType,
    RoomType,
    PresenceStatus,
    WebSocketMessage,
    SubscriptionRequest,
    PresenceInfo,
    Room,
    ConnectionInfo,
    AuthPayload,
)
from .events import (
    EventType,
    BaseEvent,
    IncidentCreated,
    IncidentUpdated,
    IncidentResolved,
    IncidentAssigned,
    IncidentAcknowledged,
    IncidentEscalated,
    CommentAdded,
    CommentUpdated,
    CommentDeleted,
    StatusChanged,
    SeverityChanged,
    SLAWarning,
    SLABreached,
    TimelineEntry,
    UserJoined,
    UserLeft,
    UserTyping,
)

__all__ = [
    # Routes
    "router",
    "publish",
    # Manager
    "manager",
    "ConnectionManager",
    # Handlers
    "MessageHandler",
    "create_handler",
    # Models
    "MessageType",
    "RoomType",
    "PresenceStatus",
    "WebSocketMessage",
    "SubscriptionRequest",
    "PresenceInfo",
    "Room",
    "ConnectionInfo",
    "AuthPayload",
    # Events
    "EventType",
    "BaseEvent",
    "IncidentCreated",
    "IncidentUpdated",
    "IncidentResolved",
    "IncidentAssigned",
    "IncidentAcknowledged",
    "IncidentEscalated",
    "CommentAdded",
    "CommentUpdated",
    "CommentDeleted",
    "StatusChanged",
    "SeverityChanged",
    "SLAWarning",
    "SLABreached",
    "TimelineEntry",
    "UserJoined",
    "UserLeft",
    "UserTyping",
]
