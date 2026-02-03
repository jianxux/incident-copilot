"""Data models for incident collaboration."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IncidentStatus(str, Enum):
    """Incident status levels."""

    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class ActivityType(str, Enum):
    """Types of activity events."""

    COMMENT_ADDED = "comment_added"
    COMMENT_EDITED = "comment_edited"
    COMMENT_DELETED = "comment_deleted"
    STATUS_CHANGED = "status_changed"
    WATCHER_ADDED = "watcher_added"
    WATCHER_REMOVED = "watcher_removed"
    MENTION = "mention"
    WAR_ROOM_CREATED = "war_room_created"
    WAR_ROOM_UPDATED = "war_room_updated"
    ESCALATION = "escalation"
    ASSIGNMENT = "assignment"


class WarRoomType(str, Enum):
    """Types of war room links."""

    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"
    SLACK_HUDDLE = "slack_huddle"
    TEAMS = "teams"
    DISCORD = "discord"
    OTHER = "other"


# --- Comment Models ---


class Comment(BaseModel):
    """A comment on an incident."""

    id: str
    incident_id: str
    author_id: str
    author_name: str
    author_email: str | None = None
    author_avatar_url: str | None = None
    content: str  # Markdown-supported content
    mentions: list[str] = Field(default_factory=list)  # List of mentioned user IDs
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    edited: bool = False
    parent_id: str | None = None  # For threaded comments
    reactions: dict[str, list[str]] = Field(default_factory=dict)  # emoji -> [user_ids]
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommentCreateRequest(BaseModel):
    """Request to create a comment."""

    content: str
    author_id: str
    author_name: str
    author_email: str | None = None
    author_avatar_url: str | None = None
    parent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommentUpdateRequest(BaseModel):
    """Request to update a comment."""

    content: str


# --- Status Update Models ---


class StatusUpdate(BaseModel):
    """A status update for an incident."""

    id: str
    incident_id: str
    previous_status: IncidentStatus | None = None
    new_status: IncidentStatus
    message: str | None = None  # Optional status message
    updated_by_id: str
    updated_by_name: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StatusUpdateRequest(BaseModel):
    """Request to update incident status."""

    status: IncidentStatus
    message: str | None = None
    updated_by_id: str
    updated_by_name: str


# --- Watcher Models ---


class Watcher(BaseModel):
    """A watcher subscribed to incident updates."""

    id: str
    incident_id: str
    user_id: str
    user_name: str
    user_email: str | None = None
    notification_preferences: dict[str, bool] = Field(
        default_factory=lambda: {
            "comments": True,
            "status_changes": True,
            "mentions": True,
            "war_room": True,
        }
    )
    subscribed_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WatchRequest(BaseModel):
    """Request to watch an incident."""

    user_id: str
    user_name: str
    user_email: str | None = None
    notification_preferences: dict[str, bool] | None = None


# --- Activity Models ---


class Activity(BaseModel):
    """An activity event in the incident feed."""

    id: str
    incident_id: str
    activity_type: ActivityType
    actor_id: str
    actor_name: str
    description: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    related_id: str | None = None  # ID of related entity (comment_id, etc.)
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- War Room Models ---


class WarRoomLink(BaseModel):
    """A war room link for incident collaboration."""

    id: str
    incident_id: str
    room_type: WarRoomType
    url: str
    title: str | None = None
    created_by_id: str
    created_by_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class WarRoomCreateRequest(BaseModel):
    """Request to create a war room link."""

    room_type: WarRoomType
    url: str
    title: str | None = None
    created_by_id: str
    created_by_name: str


# --- Mention Models ---


class Mention(BaseModel):
    """A mention parsed from content."""

    user_id: str
    user_name: str | None = None
    start_index: int
    end_index: int
    raw_text: str


class MentionNotification(BaseModel):
    """A notification to send for a mention."""

    incident_id: str
    comment_id: str
    mentioned_user_id: str
    mentioner_id: str
    mentioner_name: str
    content_preview: str
    incident_title: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
