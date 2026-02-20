"""
Realtime WebSocket Routes

FastAPI WebSocket routes for real-time incident updates.
"""

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .events import BaseEvent
from .handlers import create_handler
from .manager import manager
from .models import MessageType, RoomType, WebSocketMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["realtime"])

# Security scheme for REST endpoints
security = HTTPBearer(auto_error=False)


async def validate_token(token: str) -> tuple[str, str]:
    """
    Validate authentication token and return (user_id, user_name).
    """
    # First try internal session tokens.
    from ..auth.service import auth_service

    session = await auth_service.get_session_by_token(token)
    if session:
        user = await auth_service.get_user(session.user_id)
        if user:
            return user.id, user.name

    # Then try Supabase bearer tokens.
    from ..supabase_client import get_supabase_admin_client

    admin = get_supabase_admin_client()
    if admin:
        try:
            user_response = admin.auth.get_user(token)
        except Exception as e:
            logger.warning(
                "realtime_token_validation_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
        else:
            if user_response and user_response.user:
                user = user_response.user
                user_name = (
                    (user.user_metadata or {}).get("full_name")
                    or (user.user_metadata or {}).get("name")
                    or user.email
                    or str(user.id)
                )
                return str(user.id), user_name

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token",
    )


async def require_authenticated_bearer(
    credentials: HTTPAuthorizationCredentials | None,
) -> tuple[str, str]:
    """Require and validate a bearer token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization",
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )
    return await validate_token(credentials.credentials)


@router.websocket("/connect")
async def websocket_connect(
    websocket: WebSocket,
    token: str | None = Query(None),
):
    """
    Main WebSocket endpoint for real-time updates.

    Connect with: ws://host/ws/connect?token=YOUR_TOKEN

    Message Protocol:
    - Send: {"type": "subscribe", "payload": {"room_type": "incident", "room_id": "inc-123"}}
    - Receive: {"type": "subscribed", "payload": {"room_key": "incident:inc-123", "presence": [...]}}
    - Receive: {"type": "event", "payload": {"event_type": "comment.added", "data": {...}}}

    Message Types (client -> server):
    - subscribe: Join a room
    - unsubscribe: Leave a room
    - ping: Keep-alive
    - presence_update: Update presence status

    Message Types (server -> client):
    - connected: Connection established
    - subscribed: Successfully subscribed
    - unsubscribed: Successfully unsubscribed
    - pong: Ping response
    - event: Real-time event
    - presence: Presence update
    - error: Error message
    - rate_limited: Rate limit exceeded
    """
    # Validate token
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        user_id, user_name = await validate_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Connect
    connection_id = await manager.connect(websocket, user_id, user_name)
    handler = create_handler(manager)

    try:
        while True:
            # Receive message
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            # Handle message
            response = await handler.handle_message(connection_id, data)

            # Send response if any
            if response:
                await manager.send_to_connection(connection_id, response)

    except Exception as e:
        logger.exception(f"WebSocket error for {connection_id}: {e}")

    finally:
        await manager.disconnect(connection_id)


@router.websocket("/incident/{incident_id}")
async def websocket_incident(
    websocket: WebSocket,
    incident_id: str,
    token: str | None = Query(None),
):
    """
    Convenience endpoint that auto-subscribes to an incident room.

    Connect with: ws://host/ws/incident/inc-123?token=YOUR_TOKEN
    """
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        user_id, user_name = await validate_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Invalid token")
        return

    connection_id = await manager.connect(websocket, user_id, user_name)
    handler = create_handler(manager)

    # Auto-subscribe to incident room
    await manager.subscribe(connection_id, RoomType.INCIDENT, incident_id)

    # Send subscription confirmation
    room_key = f"incident:{incident_id}"
    presence = manager.get_room_presence(room_key)
    await manager.send_to_connection(
        connection_id,
        WebSocketMessage(
            type=MessageType.SUBSCRIBED,
            payload={
                "room_type": "incident",
                "room_id": incident_id,
                "room_key": room_key,
                "presence": [p.model_dump(mode="json") for p in presence],
            },
        ),
    )

    try:
        while True:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            response = await handler.handle_message(connection_id, data)
            if response:
                await manager.send_to_connection(connection_id, response)

    except Exception as e:
        logger.exception(f"WebSocket error for {connection_id}: {e}")

    finally:
        await manager.disconnect(connection_id)


# REST API endpoints for server-side event publishing


@router.post("/publish")
async def publish_event(
    event_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Publish an event to relevant rooms (server-side API).

    This endpoint is for internal use by other services.
    """
    await require_authenticated_bearer(credentials)

    try:
        from .events import EVENT_CLASSES, EventType

        event_type = EventType(event_data.get("event_type"))
        event_class = EVENT_CLASSES.get(event_type)

        if not event_class:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown event type: {event_type}",
            )

        event = event_class(**event_data)
        sent_count = await manager.broadcast_event(event)

        return {
            "success": True,
            "event_id": event.event_id,
            "sent_to": sent_count,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/stats")
async def get_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get WebSocket connection statistics."""
    await require_authenticated_bearer(credentials)

    return manager.get_stats()


@router.get("/rooms/{room_key}/presence")
async def get_room_presence(
    room_key: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get presence information for a room."""
    await require_authenticated_bearer(credentials)

    presence = manager.get_room_presence(room_key)
    return {
        "room_key": room_key,
        "users": [p.model_dump(mode="json") for p in presence],
    }


# Utility function for other modules to publish events
async def publish(event: BaseEvent) -> int:
    """
    Publish an event from application code.

    Usage:
        from realtime.routes import publish
        from realtime.events import CommentAdded

        await publish(CommentAdded(
            incident_id="inc-123",
            comment_id="cmt-456",
            content="Investigation started",
            author_id="user-1",
            author_name="Jane Doe",
        ))
    """
    return await manager.broadcast_event(event)
