"""WebSocket endpoint routes for real-time updates.

This module provides WebSocket endpoints for connecting to real-time updates.

Authentication can be done via:
1. Token in query params: /api/realtime/ws?token=xxx
2. First message after connection: {"type": "auth", "token": "xxx"}

Usage:
    # Connect with token in URL
    ws = websocket.connect("/api/realtime/ws?token=xxx")

    # Or connect and authenticate via message
    ws = websocket.connect("/api/realtime/ws")
    ws.send({"type": "auth", "token": "xxx"})

    # Subscribe to specific incidents
    ws.send({"type": "subscribe", "incident_id": "inc-123"})

    # Unsubscribe
    ws.send({"type": "unsubscribe", "incident_id": "inc-123"})
"""

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..auth.service import auth_service
from .events import (
    ErrorPayload,
    EventType,
    UserPresencePayload,
    create_event,
)
from .manager import connection_manager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


class AuthMessage(BaseModel):
    """Authentication message sent as first message."""

    type: str = "auth"
    token: str


class SubscribeMessage(BaseModel):
    """Subscribe to an incident room."""

    type: str = "subscribe"
    incident_id: str


class UnsubscribeMessage(BaseModel):
    """Unsubscribe from an incident room."""

    type: str = "unsubscribe"
    incident_id: str


class TypingMessage(BaseModel):
    """User typing indicator."""

    type: str = "typing"
    incident_id: str
    is_typing: bool = True


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(default=None, description="Authentication token"),
    last_event_id: str | None = Query(
        default=None, description="Last received event ID for replay"
    ),
    incident_id: str | None = Query(
        default=None, description="Auto-subscribe to incident"
    ),
):
    """WebSocket endpoint for real-time updates.

    Authentication:
    - Pass token as query param: /api/realtime/ws?token=xxx
    - Or send auth message after connect: {"type": "auth", "token": "xxx"}

    Messages you can send:
    - {"type": "subscribe", "incident_id": "xxx"} - Subscribe to incident updates
    - {"type": "unsubscribe", "incident_id": "xxx"} - Unsubscribe from incident
    - {"type": "typing", "incident_id": "xxx", "is_typing": true} - Typing indicator

    Events you'll receive:
    - incident.created, incident.updated, incident.resolved
    - comment.added, comment.updated, comment.deleted
    - timeline.event, assignment.changed
    - user.joined, user.left, user.typing
    - system.connected, system.heartbeat, system.error
    """
    tenant_id = None
    user_id = None
    user_name = None
    connection_info = None

    try:
        # Authenticate via token in query params
        if token:
            tenant_id, user_id, user_name = await _authenticate_token(token)

        # If not authenticated via query param, accept and wait for auth message
        if not tenant_id:
            await websocket.accept()

            # Wait for auth message (with timeout)
            try:
                message = await websocket.receive_json()

                if message.get("type") == "auth":
                    auth_token = message.get("token")
                    if auth_token:
                        tenant_id, user_id, user_name = await _authenticate_token(
                            auth_token
                        )

                if not tenant_id:
                    error_event = create_event(
                        EventType.ERROR,
                        "unknown",
                        ErrorPayload(
                            code="auth_failed",
                            message="Authentication required. Send {type: 'auth', token: '...'} or connect with ?token=...",
                        ),
                    )
                    await websocket.send_json(error_event.model_dump())
                    await websocket.close(code=4001, reason="Authentication required")
                    return

            except WebSocketDisconnect:
                return
            except Exception as e:
                logger.error("websocket_auth_error", error=str(e))
                await websocket.close(code=4001, reason="Authentication error")
                return

            # Now connect via manager (already accepted)
            connection_info = await connection_manager.connect(
                websocket,
                tenant_id,
                user_id=user_id,
                user_name=user_name,
                last_event_id=last_event_id,
                incident_id=incident_id,
            )

        else:
            # Connect with pre-authenticated credentials
            connection_info = await connection_manager.connect(
                websocket,
                tenant_id,
                user_id=user_id,
                user_name=user_name,
                last_event_id=last_event_id,
                incident_id=incident_id,
            )

        if not connection_info:
            # Rate limited - manager already closed connection
            return

        # Main message loop
        while True:
            try:
                message = await websocket.receive_json()
                await _handle_message(
                    connection_info.connection_id,
                    tenant_id,
                    user_id,
                    user_name,
                    message,
                )
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(
                    "websocket_message_error",
                    connection_id=connection_info.connection_id,
                    error=str(e),
                )
                # Send error but don't disconnect
                error_event = create_event(
                    EventType.ERROR,
                    tenant_id,
                    ErrorPayload(
                        code="message_error",
                        message=str(e),
                    ),
                )
                try:
                    await websocket.send_json(error_event.model_dump())
                except Exception:
                    break

    finally:
        if connection_info:
            await connection_manager.disconnect(connection_info.connection_id)


async def _authenticate_token(token: str) -> tuple[str | None, str | None, str | None]:
    """Authenticate a token and return (tenant_id, user_id, user_name).

    Returns:
        Tuple of (tenant_id, user_id, user_name) or (None, None, None) if invalid
    """
    try:
        # Try as session token
        session = await auth_service.get_session_by_token(token)
        if session:
            user = await auth_service.get_user(session.user_id)
            tenant = await auth_service.get_tenant(session.tenant_id)
            if user and tenant:
                return tenant.id, user.id, user.name

        # Try as API key
        result = await auth_service.verify_api_key(token)
        if result:
            key, tenant = result
            return tenant.id, None, None

    except Exception as e:
        logger.error("websocket_auth_error", error=str(e))

    return None, None, None


async def _handle_message(
    connection_id: str,
    tenant_id: str,
    user_id: str | None,
    user_name: str | None,
    message: dict,
):
    """Handle an incoming WebSocket message."""
    message_type = message.get("type")

    if message_type == "subscribe":
        # Subscribe to an incident room
        incident_id = message.get("incident_id")
        if incident_id:
            room_id = f"incident:{tenant_id}:{incident_id}"
            await connection_manager.join_room(connection_id, room_id)

            # Notify others that user joined
            if user_id and user_name:
                event = create_event(
                    EventType.USER_JOINED,
                    tenant_id,
                    UserPresencePayload(
                        user_id=user_id,
                        user_name=user_name,
                        incident_id=incident_id,
                    ),
                    incident_id=incident_id,
                    actor_id=user_id,
                    actor_name=user_name,
                )
                await connection_manager.broadcast_to_room(
                    room_id, event, exclude_connections={connection_id}
                )

            logger.info(
                "user_subscribed_to_incident",
                connection_id=connection_id,
                incident_id=incident_id,
            )

    elif message_type == "unsubscribe":
        # Unsubscribe from an incident room
        incident_id = message.get("incident_id")
        if incident_id:
            room_id = f"incident:{tenant_id}:{incident_id}"

            # Notify others that user left
            if user_id and user_name:
                event = create_event(
                    EventType.USER_LEFT,
                    tenant_id,
                    UserPresencePayload(
                        user_id=user_id,
                        user_name=user_name,
                        incident_id=incident_id,
                    ),
                    incident_id=incident_id,
                    actor_id=user_id,
                    actor_name=user_name,
                )
                await connection_manager.broadcast_to_room(
                    room_id, event, exclude_connections={connection_id}
                )

            await connection_manager.leave_room(connection_id, room_id)

            logger.info(
                "user_unsubscribed_from_incident",
                connection_id=connection_id,
                incident_id=incident_id,
            )

    elif message_type == "typing":
        # Typing indicator
        incident_id = message.get("incident_id")
        is_typing = message.get("is_typing", True)

        if incident_id and user_id and user_name:
            from .events import UserTypingPayload

            room_id = f"incident:{tenant_id}:{incident_id}"
            event = create_event(
                EventType.USER_TYPING,
                tenant_id,
                UserTypingPayload(
                    user_id=user_id,
                    user_name=user_name,
                    incident_id=incident_id,
                    is_typing=is_typing,
                ),
                incident_id=incident_id,
                actor_id=user_id,
                actor_name=user_name,
            )
            await connection_manager.broadcast_to_room(
                room_id, event, exclude_connections={connection_id}
            )

    elif message_type == "ping":
        # Client ping - respond with pong
        info = connection_manager.get_connection_info(connection_id)
        if info:
            await info.websocket.send_json({"type": "pong"})

    else:
        logger.warning(
            "unknown_websocket_message_type",
            connection_id=connection_id,
            message_type=message_type,
        )


@router.get("/stats")
async def get_realtime_stats():
    """Get real-time connection statistics.

    Returns connection counts and other metrics.
    """
    return connection_manager.get_stats()


@router.get("/health")
async def realtime_health():
    """Health check for real-time service."""
    return {
        "status": "ok",
        "connections": connection_manager.get_connection_count(),
    }
