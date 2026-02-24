"""
Realtime Connection Manager

Manages WebSocket connections, rooms, subscriptions, and broadcasting.
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from .events import BaseEvent, UserJoined, UserLeft
from .models import (
    ConnectionInfo,
    MessageType,
    PresenceInfo,
    PresenceStatus,
    Room,
    RoomType,
    WebSocketMessage,
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """Per-connection rate limiter."""

    def __init__(self, max_messages: int = 100, window_seconds: int = 60):
        self.max_messages = max_messages
        self.window_seconds = window_seconds

    def check(self, conn_info: ConnectionInfo) -> tuple[bool, int]:
        """Check if connection can send a message. Returns (allowed, remaining)."""
        now = datetime.now(UTC)

        # Reset window if expired
        if now >= conn_info.rate_limit_reset:
            conn_info.rate_limit_remaining = self.max_messages
            conn_info.rate_limit_reset = now + timedelta(seconds=self.window_seconds)

        if conn_info.rate_limit_remaining <= 0:
            return False, 0

        conn_info.rate_limit_remaining -= 1
        return True, conn_info.rate_limit_remaining


class ConnectionManager:
    """Manages all WebSocket connections and rooms."""

    def __init__(self, ping_interval: int = 30, ping_timeout: int = 10):
        # Connection tracking
        self._connections: dict[str, WebSocket] = {}
        self._connection_info: dict[str, ConnectionInfo] = {}

        # Room management
        self._rooms: dict[str, Room] = {}
        self._room_connections: dict[str, set[str]] = {}  # room_key -> connection_ids

        # Presence tracking
        self._presence: dict[str, dict[str, PresenceInfo]] = (
            {}
        )  # room_key -> {user_id: presence}

        # Rate limiting
        self._rate_limiter = RateLimiter()

        # Ping/pong config
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._ping_tasks: dict[str, asyncio.Task] = {}

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        user_name: str,
    ) -> str:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        connection_id = uuid4().hex

        async with self._lock:
            self._connections[connection_id] = websocket
            self._connection_info[connection_id] = ConnectionInfo(
                connection_id=connection_id,
                user_id=user_id,
                user_name=user_name,
            )

        # Start ping task
        self._ping_tasks[connection_id] = asyncio.create_task(
            self._ping_loop(connection_id)
        )

        # Send connected message
        await self._send_message(
            connection_id,
            WebSocketMessage(
                type=MessageType.CONNECTED,
                payload={
                    "connection_id": connection_id,
                    "user_id": user_id,
                    "ping_interval": self._ping_interval,
                },
            ),
        )

        logger.info(f"Connection {connection_id} established for user {user_id}")
        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """Clean up a disconnected connection."""
        async with self._lock:
            # Cancel ping task
            if connection_id in self._ping_tasks:
                self._ping_tasks[connection_id].cancel()
                del self._ping_tasks[connection_id]

            # Get connection info before cleanup
            conn_info = self._connection_info.get(connection_id)
            if not conn_info:
                return

            # Unsubscribe from all rooms
            for room_key in list(conn_info.subscriptions):
                await self._unsubscribe_internal(connection_id, room_key)

            # Remove connection
            self._connections.pop(connection_id, None)
            self._connection_info.pop(connection_id, None)

        logger.info(f"Connection {connection_id} disconnected")

    async def subscribe(
        self,
        connection_id: str,
        room_type: RoomType,
        room_id: str,
    ) -> bool:
        """Subscribe a connection to a room."""
        room_key = f"{room_type.value}:{room_id}"

        async with self._lock:
            conn_info = self._connection_info.get(connection_id)
            if not conn_info:
                return False

            # Create room if needed
            if room_key not in self._rooms:
                self._rooms[room_key] = Room(room_type=room_type, room_id=room_id)
                self._room_connections[room_key] = set()
                self._presence[room_key] = {}

            # Add to room
            self._room_connections[room_key].add(connection_id)
            conn_info.subscriptions.add(room_key)

            # Add presence
            presence = PresenceInfo(
                user_id=conn_info.user_id,
                user_name=conn_info.user_name,
                room_key=room_key,
            )
            self._presence[room_key][conn_info.user_id] = presence

        # Broadcast join event to room (outside lock)
        await self.broadcast_to_room(
            room_key,
            UserJoined(
                user_id=conn_info.user_id,
                user_name=conn_info.user_name,
                room_key=room_key,
                source=conn_info.user_id,
            ),
            exclude_connection=connection_id,
        )

        logger.info(f"Connection {connection_id} subscribed to {room_key}")
        return True

    async def unsubscribe(self, connection_id: str, room_key: str) -> bool:
        """Unsubscribe a connection from a room."""
        async with self._lock:
            return await self._unsubscribe_internal(connection_id, room_key)

    async def _unsubscribe_internal(self, connection_id: str, room_key: str) -> bool:
        """Internal unsubscribe (must hold lock)."""
        conn_info = self._connection_info.get(connection_id)
        if not conn_info or room_key not in conn_info.subscriptions:
            return False

        # Remove from room
        conn_info.subscriptions.discard(room_key)
        if room_key in self._room_connections:
            self._room_connections[room_key].discard(connection_id)

        # Remove presence
        if room_key in self._presence:
            self._presence[room_key].pop(conn_info.user_id, None)

        # Clean up empty rooms
        if room_key in self._room_connections and not self._room_connections[room_key]:
            self._rooms.pop(room_key, None)
            self._room_connections.pop(room_key, None)
            self._presence.pop(room_key, None)
        else:
            # Broadcast leave event (schedule outside lock)
            asyncio.create_task(
                self.broadcast_to_room(
                    room_key,
                    UserLeft(
                        user_id=conn_info.user_id,
                        user_name=conn_info.user_name,
                        room_key=room_key,
                        source=conn_info.user_id,
                    ),
                )
            )

        logger.info(f"Connection {connection_id} unsubscribed from {room_key}")
        return True

    async def broadcast_event(self, event: BaseEvent) -> int:
        """Broadcast an event to all relevant rooms."""
        room_keys = event.get_room_keys()
        sent_to: set[str] = set()

        for room_key in room_keys:
            async with self._lock:
                connections = self._room_connections.get(room_key, set()).copy()

            for conn_id in connections:
                if conn_id not in sent_to:
                    await self._send_message(
                        conn_id,
                        WebSocketMessage(
                            type=MessageType.EVENT,
                            payload=event.to_message(),
                        ),
                    )
                    sent_to.add(conn_id)

        return len(sent_to)

    async def broadcast_to_room(
        self,
        room_key: str,
        event: BaseEvent,
        exclude_connection: str | None = None,
    ) -> int:
        """Broadcast an event to a specific room."""
        async with self._lock:
            connections = self._room_connections.get(room_key, set()).copy()

        count = 0
        for conn_id in connections:
            if conn_id != exclude_connection:
                await self._send_message(
                    conn_id,
                    WebSocketMessage(
                        type=MessageType.EVENT,
                        payload=event.to_message(),
                    ),
                )
                count += 1

        return count

    async def send_to_connection(
        self,
        connection_id: str,
        message: WebSocketMessage,
    ) -> bool:
        """Send a message to a specific connection."""
        return await self._send_message(connection_id, message)

    async def _send_message(
        self,
        connection_id: str,
        message: WebSocketMessage,
    ) -> bool:
        """Internal message sending."""
        websocket = self._connections.get(connection_id)
        if not websocket:
            return False

        try:
            await websocket.send_json(message.model_dump(mode="json"))
            return True
        except Exception as e:
            logger.error(f"Failed to send to {connection_id}: {e}")
            asyncio.create_task(self.disconnect(connection_id))
            return False

    def check_rate_limit(self, connection_id: str) -> tuple[bool, int]:
        """Check rate limit for a connection."""
        conn_info = self._connection_info.get(connection_id)
        if not conn_info:
            return False, 0
        return self._rate_limiter.check(conn_info)

    async def update_presence(
        self,
        connection_id: str,
        room_key: str,
        status: PresenceStatus,
    ) -> bool:
        """Update user presence in a room."""
        async with self._lock:
            conn_info = self._connection_info.get(connection_id)
            if not conn_info or room_key not in conn_info.subscriptions:
                return False

            if room_key in self._presence:
                presence = self._presence[room_key].get(conn_info.user_id)
                if presence:
                    presence.status = status
                    presence.last_activity = datetime.now(UTC)
                    return True

        return False

    def get_room_presence(self, room_key: str) -> list[PresenceInfo]:
        """Get all users present in a room."""
        return list(self._presence.get(room_key, {}).values())

    def get_connection_info(self, connection_id: str) -> ConnectionInfo | None:
        """Get connection info."""
        return self._connection_info.get(connection_id)

    def get_room(self, room_key: str) -> Room | None:
        """Get room info."""
        return self._rooms.get(room_key)

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics."""
        return {
            "total_connections": len(self._connections),
            "total_rooms": len(self._rooms),
            "rooms": {
                key: {
                    "connections": len(self._room_connections.get(key, [])),
                    "presence": len(self._presence.get(key, {})),
                }
                for key in self._rooms
            },
        }

    async def _ping_loop(self, connection_id: str) -> None:
        """Send periodic pings to keep connection alive."""
        try:
            while connection_id in self._connections:
                await asyncio.sleep(self._ping_interval)

                conn_info = self._connection_info.get(connection_id)
                if not conn_info:
                    break

                # Check if last ping was responded to
                time_since_ping = datetime.now(UTC) - conn_info.last_ping
                if (
                    time_since_ping.total_seconds()
                    > self._ping_interval + self._ping_timeout
                ):
                    logger.warning(f"Connection {connection_id} ping timeout")
                    await self.disconnect(connection_id)
                    break

                # Send ping
                await self._send_message(
                    connection_id,
                    WebSocketMessage(type=MessageType.PING),
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ping loop error for {connection_id}: {e}")

    def handle_pong(self, connection_id: str) -> None:
        """Handle pong response from client."""
        conn_info = self._connection_info.get(connection_id)
        if conn_info:
            conn_info.last_ping = datetime.now(UTC)


# Global connection manager instance
manager = ConnectionManager()
