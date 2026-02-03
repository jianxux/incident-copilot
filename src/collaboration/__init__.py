"""Collaboration module for incident response.

Provides comments, @mentions, status updates, activity feeds,
watchers, and war room links for incident collaboration.
"""

from .mentions import MentionParser, parse_mentions
from .models import (
    Activity,
    ActivityType,
    Comment,
    CommentCreateRequest,
    CommentUpdateRequest,
    IncidentStatus,
    StatusUpdate,
    StatusUpdateRequest,
    WarRoomLink,
    WarRoomType,
    Watcher,
)
from .service import CollaborationService, collaboration_service
from .store import CollaborationStore, collaboration_store

__all__ = [
    # Models
    "Comment",
    "CommentCreateRequest",
    "CommentUpdateRequest",
    "StatusUpdate",
    "StatusUpdateRequest",
    "IncidentStatus",
    "Watcher",
    "Activity",
    "ActivityType",
    "WarRoomLink",
    "WarRoomType",
    # Store
    "CollaborationStore",
    "collaboration_store",
    # Service
    "CollaborationService",
    "collaboration_service",
    # Mentions
    "MentionParser",
    "parse_mentions",
]
