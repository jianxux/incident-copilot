"""
Realtime WebSocket Models

Pydantic models for WebSocket messages, subscriptions, presence tracking, and rooms.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """WebSocket message types."""

    # Client -> Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"
    PRESENCE_UPDATE = "presence_update"

    # Server -> Client
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    PONG = "pong"
    EVENT = "event"
    PRESENCE = "presence"
    ERROR = "error"
    CONNECTED = "connected"
    RATE_LIMITED = "rate_limited"


class RoomType(str, Enum):
    """Types of subscription rooms."""

    INCIDENT = "incident"  # Updates for a specific incident
    SERVICE = "service"  # Updates for a specific service
    TEAM = "team"  # Updates for a team
    GLOBAL = "global"  # All updates (admin only)


class PresenceStatus(str, Enum):
    """User presence status."""

    VIEWING = "viewing"
    EDITING = "editing"
    IDLE = "idle"


class WebSocketMessage(BaseModel):
    """Base WebSocket message structure."""

    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None  # For request-response correlation


class SubscriptionRequest(BaseModel):
    """Request to subscribe to a room."""

    room_type: RoomType
    room_id: str  # incident_id, service_id, team_id, or "all" for global

    @property
    def room_key(self) -> str:
        """Generate unique room key."""
        return f"{self.room_type.value}:{self.room_id}"


class PresenceInfo(BaseModel):
    """User presence information."""

    user_id: str
    user_name: str
    status: PresenceStatus = PresenceStatus.VIEWING
    room_key: str
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Room(BaseModel):
    """A subscription room with connected users."""

    room_type: RoomType
    room_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def room_key(self) -> str:
        return f"{self.room_type.value}:{self.room_id}"


class ConnectionInfo(BaseModel):
    """Information about a WebSocket connection."""

    connection_id: str
    user_id: str
    user_name: str
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    last_ping: datetime = Field(default_factory=datetime.utcnow)
    subscriptions: set[str] = Field(default_factory=set)
    message_count: int = 0
    rate_limit_remaining: int = 100
    rate_limit_reset: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True


class AuthPayload(BaseModel):
    """Authentication payload from connection params."""

    token: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
