"""Broadcaster utility for sending real-time events from anywhere in the codebase.

This module provides a simple interface to broadcast events to connected WebSocket
clients without needing to directly interact with the ConnectionManager.

Usage:
    from src.realtime import broadcaster

    # Broadcast incident update
    await broadcaster.broadcast_incident_update(
        tenant_id="tenant-123",
        incident_id="inc-456",
        changes={"status": {"old": "open", "new": "acknowledged"}},
        actor_id="user-789",
        actor_name="John Doe",
    )

    # Broadcast new comment
    await broadcaster.broadcast_comment_added(
        tenant_id="tenant-123",
        incident_id="inc-456",
        comment_id="comment-001",
        author_id="user-789",
        author_name="John Doe",
        content="Looking into this now...",
    )
"""

from datetime import datetime
from typing import Any

import structlog

from .events import (
    AssignmentChangedPayload,
    CommentAddedPayload,
    CommentDeletedPayload,
    CommentUpdatedPayload,
    EventType,
    IncidentCreatedPayload,
    IncidentResolvedPayload,
    IncidentUpdatedPayload,
    TimelineEventPayload,
    UserPresencePayload,
    UserTypingPayload,
    create_event,
)
from .manager import connection_manager

logger = structlog.get_logger()


class Broadcaster:
    """Utility class for broadcasting real-time events.

    Provides high-level methods for common event types, handling
    event creation and routing to the appropriate rooms.
    """

    def __init__(self, manager=None):
        """Initialize broadcaster with optional custom manager."""
        self._manager = manager or connection_manager

    # --- Incident Events ---

    async def broadcast_incident_created(
        self,
        tenant_id: str,
        incident_id: str,
        title: str,
        severity: str,
        service_name: str,
        triggered_at: datetime | None = None,
        alert_url: str | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> int:
        """Broadcast an incident.created event.

        Args:
            tenant_id: Tenant ID
            incident_id: Incident ID
            title: Incident title
            severity: Incident severity
            service_name: Name of affected service
            triggered_at: When incident was triggered
            alert_url: Optional URL to alert
            actor_id: Optional user who created
            actor_name: Optional user display name

        Returns:
            Number of connections that received the event
        """
        payload = IncidentCreatedPayload(
            incident_id=incident_id,
            title=title,
            severity=severity,
            service_name=service_name,
            triggered_at=triggered_at or datetime.utcnow(),
            alert_url=alert_url,
        )

        event = create_event(
            EventType.INCIDENT_CREATED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        # Broadcast to tenant room (all tenant users should see new incidents)
        count = await self._manager.broadcast_to_tenant(tenant_id, event)

        logger.info(
            "broadcast_incident_created",
            tenant_id=tenant_id,
            incident_id=incident_id,
            recipients=count,
        )

        return count

    async def broadcast_incident_updated(
        self,
        tenant_id: str,
        incident_id: str,
        changes: dict[str, dict[str, Any]],
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> int:
        """Broadcast an incident.updated event.

        Args:
            tenant_id: Tenant ID
            incident_id: Incident ID
            changes: Map of field name to {old, new} values
            actor_id: Optional user who made the change
            actor_name: Optional user display name

        Returns:
            Number of connections that received the event
        """
        payload = IncidentUpdatedPayload(
            incident_id=incident_id,
            changes=changes,
            updated_fields=list(changes.keys()),
        )

        event = create_event(
            EventType.INCIDENT_UPDATED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        # Broadcast to both tenant and incident rooms
        count = await self._manager.broadcast_to_tenant(tenant_id, event)
        count += await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

        logger.info(
            "broadcast_incident_updated",
            tenant_id=tenant_id,
            incident_id=incident_id,
            changes=list(changes.keys()),
            recipients=count,
        )

        return count

    async def broadcast_incident_resolved(
        self,
        tenant_id: str,
        incident_id: str,
        resolution_summary: str | None = None,
        resolved_at: datetime | None = None,
        time_to_resolve_minutes: int | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> int:
        """Broadcast an incident.resolved event.

        Args:
            tenant_id: Tenant ID
            incident_id: Incident ID
            resolution_summary: Optional summary of resolution
            resolved_at: When incident was resolved
            time_to_resolve_minutes: Optional TTR in minutes
            actor_id: Optional user who resolved
            actor_name: Optional user display name

        Returns:
            Number of connections that received the event
        """
        payload = IncidentResolvedPayload(
            incident_id=incident_id,
            resolution_summary=resolution_summary,
            resolved_at=resolved_at or datetime.utcnow(),
            time_to_resolve_minutes=time_to_resolve_minutes,
        )

        event = create_event(
            EventType.INCIDENT_RESOLVED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        # Broadcast to both tenant and incident rooms
        count = await self._manager.broadcast_to_tenant(tenant_id, event)
        count += await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

        logger.info(
            "broadcast_incident_resolved",
            tenant_id=tenant_id,
            incident_id=incident_id,
            recipients=count,
        )

        return count

    # --- Comment Events ---

    async def broadcast_comment_added(
        self,
        tenant_id: str,
        incident_id: str,
        comment_id: str,
        author_id: str,
        author_name: str,
        content: str,
        created_at: datetime | None = None,
        is_internal: bool = False,
    ) -> int:
        """Broadcast a comment.added event.

        Args:
            tenant_id: Tenant ID
            incident_id: Incident ID
            comment_id: Comment ID
            author_id: Author user ID
            author_name: Author display name
            content: Comment content
            created_at: When comment was created
            is_internal: Whether comment is internal only

        Returns:
            Number of connections that received the event
        """
        payload = CommentAddedPayload(
            comment_id=comment_id,
            incident_id=incident_id,
            author_id=author_id,
            author_name=author_name,
            content=content,
            created_at=created_at or datetime.utcnow(),
            is_internal=is_internal,
        )

        event = create_event(
            EventType.COMMENT_ADDED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=author_id,
            actor_name=author_name,
        )

        # Broadcast to incident room
        count = await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

        logger.info(
            "broadcast_comment_added",
            tenant_id=tenant_id,
            incident_id=incident_id,
            comment_id=comment_id,
            recipients=count,
        )

        return count

    async def broadcast_comment_updated(
        self,
        tenant_id: str,
        incident_id: str,
        comment_id: str,
        content: str,
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> int:
        """Broadcast a comment.updated event."""
        payload = CommentUpdatedPayload(
            comment_id=comment_id,
            incident_id=incident_id,
            content=content,
        )

        event = create_event(
            EventType.COMMENT_UPDATED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        return await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

    async def broadcast_comment_deleted(
        self,
        tenant_id: str,
        incident_id: str,
        comment_id: str,
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> int:
        """Broadcast a comment.deleted event."""
        payload = CommentDeletedPayload(
            comment_id=comment_id,
            incident_id=incident_id,
        )

        event = create_event(
            EventType.COMMENT_DELETED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        return await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

    # --- Timeline Events ---

    async def broadcast_timeline_event(
        self,
        tenant_id: str,
        incident_id: str,
        event_id: str,
        event_type: str,
        title: str,
        description: str | None = None,
        occurred_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> int:
        """Broadcast a timeline.event event.

        Args:
            tenant_id: Tenant ID
            incident_id: Incident ID
            event_id: Timeline event ID
            event_type: Type of timeline event (e.g., "alert_triggered", "deploy_detected")
            title: Event title
            description: Optional description
            occurred_at: When event occurred
            metadata: Optional additional data
            actor_id: Optional user who triggered
            actor_name: Optional user display name

        Returns:
            Number of connections that received the event
        """
        payload = TimelineEventPayload(
            event_id=event_id,
            incident_id=incident_id,
            event_type=event_type,
            title=title,
            description=description,
            occurred_at=occurred_at or datetime.utcnow(),
            metadata=metadata or {},
        )

        event = create_event(
            EventType.TIMELINE_EVENT,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        count = await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

        logger.info(
            "broadcast_timeline_event",
            tenant_id=tenant_id,
            incident_id=incident_id,
            event_type=event_type,
            recipients=count,
        )

        return count

    # --- Assignment Events ---

    async def broadcast_assignment_changed(
        self,
        tenant_id: str,
        incident_id: str,
        previous_assignees: list[str],
        new_assignees: list[str],
        assigned_by: str | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
    ) -> int:
        """Broadcast an assignment.changed event.

        Args:
            tenant_id: Tenant ID
            incident_id: Incident ID
            previous_assignees: List of previous assignee user IDs
            new_assignees: List of new assignee user IDs
            assigned_by: Optional user who made the assignment
            actor_id: Optional user who triggered
            actor_name: Optional user display name

        Returns:
            Number of connections that received the event
        """
        payload = AssignmentChangedPayload(
            incident_id=incident_id,
            previous_assignees=previous_assignees,
            new_assignees=new_assignees,
            assigned_by=assigned_by,
        )

        event = create_event(
            EventType.ASSIGNMENT_CHANGED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        # Broadcast to both tenant and incident rooms
        count = await self._manager.broadcast_to_tenant(tenant_id, event)
        count += await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

        logger.info(
            "broadcast_assignment_changed",
            tenant_id=tenant_id,
            incident_id=incident_id,
            previous=previous_assignees,
            new=new_assignees,
            recipients=count,
        )

        return count

    # --- Presence Events ---

    async def broadcast_user_joined(
        self,
        tenant_id: str,
        incident_id: str,
        user_id: str,
        user_name: str,
        avatar_url: str | None = None,
    ) -> int:
        """Broadcast a user.joined event to an incident room."""
        payload = UserPresencePayload(
            user_id=user_id,
            user_name=user_name,
            avatar_url=avatar_url,
            incident_id=incident_id,
        )

        event = create_event(
            EventType.USER_JOINED,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=user_id,
            actor_name=user_name,
        )

        return await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

    async def broadcast_user_left(
        self,
        tenant_id: str,
        incident_id: str,
        user_id: str,
        user_name: str,
    ) -> int:
        """Broadcast a user.left event to an incident room."""
        payload = UserPresencePayload(
            user_id=user_id,
            user_name=user_name,
            incident_id=incident_id,
        )

        event = create_event(
            EventType.USER_LEFT,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=user_id,
            actor_name=user_name,
        )

        return await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

    async def broadcast_user_typing(
        self,
        tenant_id: str,
        incident_id: str,
        user_id: str,
        user_name: str,
        is_typing: bool = True,
    ) -> int:
        """Broadcast a user.typing event to an incident room."""
        payload = UserTypingPayload(
            user_id=user_id,
            user_name=user_name,
            incident_id=incident_id,
            is_typing=is_typing,
        )

        event = create_event(
            EventType.USER_TYPING,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=user_id,
            actor_name=user_name,
        )

        return await self._manager.broadcast_to_incident(tenant_id, incident_id, event)

    # --- Generic Broadcast ---

    async def broadcast_custom_event(
        self,
        event_type: EventType,
        tenant_id: str,
        payload: dict[str, Any],
        incident_id: str | None = None,
        actor_id: str | None = None,
        actor_name: str | None = None,
        to_tenant: bool = True,
        to_incident: bool = False,
    ) -> int:
        """Broadcast a custom event.

        Args:
            event_type: Event type
            tenant_id: Tenant ID
            payload: Event payload as dict
            incident_id: Optional incident ID
            actor_id: Optional actor user ID
            actor_name: Optional actor display name
            to_tenant: Whether to broadcast to tenant room
            to_incident: Whether to broadcast to incident room (requires incident_id)

        Returns:
            Number of connections that received the event
        """
        event = create_event(
            event_type,
            tenant_id,
            payload,
            incident_id=incident_id,
            actor_id=actor_id,
            actor_name=actor_name,
        )

        count = 0
        if to_tenant:
            count += await self._manager.broadcast_to_tenant(tenant_id, event)
        if to_incident and incident_id:
            count += await self._manager.broadcast_to_incident(
                tenant_id, incident_id, event
            )

        return count


# Global broadcaster instance
broadcaster = Broadcaster()
