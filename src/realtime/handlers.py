"""
Realtime Message Handlers

Handle incoming WebSocket messages: subscribe, unsubscribe, presence updates, etc.
"""

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from .manager import ConnectionManager
from .models import (
    MessageType,
    PresenceStatus,
    RoomType,
    WebSocketMessage,
)

logger = logging.getLogger(__name__)

# Type alias for handlers
HandlerFunc = Callable[
    [ConnectionManager, str, dict[str, Any]],
    Coroutine[Any, Any, WebSocketMessage | None],
]


class MessageHandler:
    """Handles incoming WebSocket messages."""

    def __init__(self, manager: ConnectionManager):
        self.manager = manager
        self._handlers: dict[MessageType, HandlerFunc] = {
            MessageType.SUBSCRIBE: self._handle_subscribe,
            MessageType.UNSUBSCRIBE: self._handle_unsubscribe,
            MessageType.PING: self._handle_ping,
            MessageType.PONG: self._handle_pong,
            MessageType.PRESENCE_UPDATE: self._handle_presence_update,
        }

    async def handle_message(
        self,
        connection_id: str,
        raw_message: str | bytes,
    ) -> WebSocketMessage | None:
        """Parse and handle an incoming message."""
        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")

            data = json.loads(raw_message)
            message_type = MessageType(data.get("type"))
            payload = data.get("payload", {})
            request_id = data.get("request_id")

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Invalid message from {connection_id}: {e}")
            return WebSocketMessage(
                type=MessageType.ERROR,
                payload={"error": "Invalid message format", "code": "INVALID_FORMAT"},
            )

        # Check rate limit
        allowed, remaining = self.manager.check_rate_limit(connection_id)
        if not allowed:
            logger.warning(f"Rate limit exceeded for {connection_id}")
            return WebSocketMessage(
                type=MessageType.RATE_LIMITED,
                payload={
                    "error": "Rate limit exceeded",
                    "code": "RATE_LIMITED",
                    "retry_after_seconds": 60,
                },
                request_id=request_id,
            )

        # Get handler
        handler = self._handlers.get(message_type)
        if not handler:
            return WebSocketMessage(
                type=MessageType.ERROR,
                payload={
                    "error": f"Unknown message type: {message_type}",
                    "code": "UNKNOWN_TYPE",
                },
                request_id=request_id,
            )

        # Execute handler
        try:
            response = await handler(self.manager, connection_id, payload)
            if response:
                response.request_id = request_id
            return response
        except Exception as e:
            logger.exception(f"Handler error for {message_type}: {e}")
            return WebSocketMessage(
                type=MessageType.ERROR,
                payload={"error": str(e), "code": "HANDLER_ERROR"},
                request_id=request_id,
            )

    async def _handle_subscribe(
        self,
        manager: ConnectionManager,
        connection_id: str,
        payload: dict[str, Any],
    ) -> WebSocketMessage:
        """Handle subscription request."""
        try:
            room_type = RoomType(payload.get("room_type"))
            room_id = payload.get("room_id", "")

            if not room_id:
                return WebSocketMessage(
                    type=MessageType.ERROR,
                    payload={"error": "room_id is required", "code": "MISSING_ROOM_ID"},
                )

            # Check permissions for global room
            if room_type == RoomType.GLOBAL:
                manager.get_connection_info(connection_id)
                # TODO: Add admin check here
                # For now, allow all authenticated users

            success = await manager.subscribe(connection_id, room_type, room_id)

            if success:
                room_key = f"{room_type.value}:{room_id}"
                presence = manager.get_room_presence(room_key)

                return WebSocketMessage(
                    type=MessageType.SUBSCRIBED,
                    payload={
                        "room_type": room_type.value,
                        "room_id": room_id,
                        "room_key": room_key,
                        "presence": [p.model_dump(mode="json") for p in presence],
                    },
                )
            else:
                return WebSocketMessage(
                    type=MessageType.ERROR,
                    payload={
                        "error": "Failed to subscribe",
                        "code": "SUBSCRIBE_FAILED",
                    },
                )

        except ValueError as e:
            return WebSocketMessage(
                type=MessageType.ERROR,
                payload={
                    "error": f"Invalid room_type: {e}",
                    "code": "INVALID_ROOM_TYPE",
                },
            )

    async def _handle_unsubscribe(
        self,
        manager: ConnectionManager,
        connection_id: str,
        payload: dict[str, Any],
    ) -> WebSocketMessage:
        """Handle unsubscription request."""
        room_key = payload.get("room_key")

        if not room_key:
            # Try to build from room_type and room_id
            room_type = payload.get("room_type")
            room_id = payload.get("room_id")
            if room_type and room_id:
                room_key = f"{room_type}:{room_id}"

        if not room_key:
            return WebSocketMessage(
                type=MessageType.ERROR,
                payload={
                    "error": "room_key or (room_type, room_id) required",
                    "code": "MISSING_ROOM",
                },
            )

        success = await manager.unsubscribe(connection_id, room_key)

        return WebSocketMessage(
            type=MessageType.UNSUBSCRIBED,
            payload={"room_key": room_key, "success": success},
        )

    async def _handle_ping(
        self,
        manager: ConnectionManager,
        connection_id: str,
        payload: dict[str, Any],
    ) -> WebSocketMessage:
        """Handle ping request."""
        manager.handle_pong(connection_id)  # Treat ping as proof of life
        return WebSocketMessage(
            type=MessageType.PONG,
            payload={"echo": payload.get("echo")},
        )

    async def _handle_pong(
        self,
        manager: ConnectionManager,
        connection_id: str,
        payload: dict[str, Any],
    ) -> WebSocketMessage | None:
        """Handle pong response."""
        manager.handle_pong(connection_id)
        return None  # No response needed

    async def _handle_presence_update(
        self,
        manager: ConnectionManager,
        connection_id: str,
        payload: dict[str, Any],
    ) -> WebSocketMessage:
        """Handle presence update."""
        room_key = payload.get("room_key")
        status_str = payload.get("status")

        if not room_key:
            return WebSocketMessage(
                type=MessageType.ERROR,
                payload={"error": "room_key is required", "code": "MISSING_ROOM_KEY"},
            )

        try:
            status = (
                PresenceStatus(status_str) if status_str else PresenceStatus.VIEWING
            )
        except ValueError:
            status = PresenceStatus.VIEWING

        success = await manager.update_presence(connection_id, room_key, status)

        if success:
            # Broadcast presence change to room
            from .events import UserTyping

            conn_info = manager.get_connection_info(connection_id)
            if conn_info and status == PresenceStatus.EDITING:
                await manager.broadcast_to_room(
                    room_key,
                    UserTyping(
                        user_id=conn_info.user_id,
                        user_name=conn_info.user_name,
                        room_key=room_key,
                        source=conn_info.user_id,
                    ),
                    exclude_connection=connection_id,
                )

        return WebSocketMessage(
            type=MessageType.PRESENCE,
            payload={
                "room_key": room_key,
                "status": status.value,
                "success": success,
            },
        )


def create_handler(manager: ConnectionManager) -> MessageHandler:
    """Factory function to create a message handler."""
    return MessageHandler(manager)
