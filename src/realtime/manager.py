"""WebSocket connection manager for real-time updates.

This module manages WebSocket connections, rooms, and message broadcasting.
Supports:
- Room-based channels (per tenant, per incident)
- Connection tracking with metadata
- Broadcast to rooms or specific connections
- Reconnection handling with last-event-id
- Rate limiting on connections per tenant/user
"""

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from .events import (
    ConnectedPayload,
    ErrorPayload,
    EventType,
    HeartbeatPayload,
    RealtimeEvent,
    create_event,
)

logger = structlog.get_logger()


@dataclass
class ConnectionInfo:
    """Information about a WebSocket connection."""

    connection_id: str
    websocket: WebSocket
    tenant_id: str
    user_id: str | None = None
    user_name: str | None = None
    rooms: set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_ping: datetime = field(default_factory=datetime.utcnow)
    last_event_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimitState:
    """Rate limit state for a tenant or user."""

    connection_count: int = 0
    last_connection: datetime = field(default_factory=datetime.utcnow)
    denied_count: int = 0


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting.

    Features:
    - Room-based channels (per tenant, per incident)
    - Connection tracking with metadata
    - Broadcast to rooms or specific connections
    - Rate limiting on connections
    - Event buffering for reconnection (last-event-id)
    """

    # Rate limit settings
    MAX_CONNECTIONS_PER_TENANT = 100
    MAX_CONNECTIONS_PER_USER = 10
    HEARTBEAT_INTERVAL_SECONDS = 30
    EVENT_BUFFER_SIZE = 1000  # Max events to keep for replay
    EVENT_BUFFER_TTL_SECONDS = 300  # 5 minutes

    def __init__(self):
        # Connection tracking
        self._connections: dict[str, ConnectionInfo] = {}  # connection_id -> info
        self._tenant_connections: dict[str, set[str]] = defaultdict(
            set
        )  # tenant_id -> connection_ids
        self._user_connections: dict[str, set[str]] = defaultdict(
            set
        )  # user_id -> connection_ids
        self._room_connections: dict[str, set[str]] = defaultdict(
            set
        )  # room_id -> connection_ids

        # Rate limiting
        self._tenant_rate_limits: dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._user_rate_limits: dict[str, RateLimitState] = defaultdict(RateLimitState)

        # Event buffer for reconnection (last-event-id support)
        self._event_buffer: dict[str, list[RealtimeEvent]] = defaultdict(
            list
        )  # room_id -> events
        self._event_timestamps: dict[str, datetime] = {}  # event_id -> timestamp

        # Heartbeat task
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        """Start background tasks (heartbeat)."""
        if self._running:
            return

        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("connection_manager_started")

    async def stop(self):
        """Stop background tasks and disconnect all clients."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Disconnect all clients
        for conn_id in list(self._connections.keys()):
            await self.disconnect(conn_id)

        logger.info("connection_manager_stopped")

    def _generate_room_id(self, tenant_id: str, incident_id: str | None = None) -> str:
        """Generate a room ID for a tenant/incident.

        Room ID format:
        - Tenant room: "tenant:{tenant_id}"
        - Incident room: "incident:{tenant_id}:{incident_id}"
        """
        if incident_id:
            return f"incident:{tenant_id}:{incident_id}"
        return f"tenant:{tenant_id}"

    def _check_rate_limit(
        self, tenant_id: str, user_id: str | None = None
    ) -> tuple[bool, str | None]:
        """Check if a new connection is allowed.

        Returns:
            Tuple of (allowed, error_message)
        """
        # Check tenant limit
        tenant_state = self._tenant_rate_limits[tenant_id]
        current_tenant_connections = len(self._tenant_connections.get(tenant_id, set()))

        if current_tenant_connections >= self.MAX_CONNECTIONS_PER_TENANT:
            tenant_state.denied_count += 1
            logger.warning(
                "connection_rate_limited",
                tenant_id=tenant_id,
                limit_type="tenant",
                current=current_tenant_connections,
                max=self.MAX_CONNECTIONS_PER_TENANT,
            )
            return False, f"Too many connections for tenant (max: {self.MAX_CONNECTIONS_PER_TENANT})"

        # Check user limit
        if user_id:
            current_user_connections = len(self._user_connections.get(user_id, set()))
            if current_user_connections >= self.MAX_CONNECTIONS_PER_USER:
                user_state = self._user_rate_limits[user_id]
                user_state.denied_count += 1
                logger.warning(
                    "connection_rate_limited",
                    tenant_id=tenant_id,
                    user_id=user_id,
                    limit_type="user",
                    current=current_user_connections,
                    max=self.MAX_CONNECTIONS_PER_USER,
                )
                return False, f"Too many connections for user (max: {self.MAX_CONNECTIONS_PER_USER})"

        return True, None

    async def connect(
        self,
        websocket: WebSocket,
        tenant_id: str,
        user_id: str | None = None,
        user_name: str | None = None,
        last_event_id: str | None = None,
        incident_id: str | None = None,
    ) -> ConnectionInfo | None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            tenant_id: Tenant ID (required)
            user_id: Optional user ID
            user_name: Optional user display name
            last_event_id: Optional last event ID for replay
            incident_id: Optional incident ID to auto-join room

        Returns:
            ConnectionInfo if successful, None if rate limited
        """
        # Check rate limits
        allowed, error_msg = self._check_rate_limit(tenant_id, user_id)
        if not allowed:
            await websocket.accept()
            error_event = create_event(
                EventType.ERROR,
                tenant_id,
                ErrorPayload(code="rate_limited", message=error_msg or "Rate limited"),
            )
            await websocket.send_json(error_event.model_dump())
            await websocket.close(code=1008, reason=error_msg)
            return None

        # Accept the connection
        await websocket.accept()

        # Create connection info
        connection_id = str(uuid.uuid4())
        info = ConnectionInfo(
            connection_id=connection_id,
            websocket=websocket,
            tenant_id=tenant_id,
            user_id=user_id,
            user_name=user_name,
            last_event_id=last_event_id,
        )

        # Register connection
        self._connections[connection_id] = info
        self._tenant_connections[tenant_id].add(connection_id)
        if user_id:
            self._user_connections[user_id].add(connection_id)

        # Update rate limit state
        self._tenant_rate_limits[tenant_id].connection_count += 1
        self._tenant_rate_limits[tenant_id].last_connection = datetime.utcnow()

        # Auto-join tenant room
        tenant_room = self._generate_room_id(tenant_id)
        await self.join_room(connection_id, tenant_room)

        # Auto-join incident room if specified
        if incident_id:
            incident_room = self._generate_room_id(tenant_id, incident_id)
            await self.join_room(connection_id, incident_room)

        # Send connected event
        rooms_list = list(info.rooms)
        connected_event = create_event(
            EventType.CONNECTED,
            tenant_id,
            ConnectedPayload(
                connection_id=connection_id,
                rooms=rooms_list,
                last_event_id=last_event_id,
            ),
        )
        await self._send_to_connection(connection_id, connected_event)

        # Replay missed events if last_event_id provided
        if last_event_id:
            await self._replay_events(connection_id, last_event_id)

        logger.info(
            "websocket_connected",
            connection_id=connection_id,
            tenant_id=tenant_id,
            user_id=user_id,
            rooms=rooms_list,
        )

        return info

    async def disconnect(self, connection_id: str):
        """Disconnect and unregister a WebSocket connection."""
        info = self._connections.get(connection_id)
        if not info:
            return

        # Remove from all rooms
        for room_id in list(info.rooms):
            await self.leave_room(connection_id, room_id)

        # Unregister connection
        del self._connections[connection_id]
        self._tenant_connections[info.tenant_id].discard(connection_id)
        if info.user_id:
            self._user_connections[info.user_id].discard(connection_id)

        # Update rate limit state
        self._tenant_rate_limits[info.tenant_id].connection_count -= 1

        # Close WebSocket
        try:
            await info.websocket.close()
        except Exception:
            pass

        logger.info(
            "websocket_disconnected",
            connection_id=connection_id,
            tenant_id=info.tenant_id,
            user_id=info.user_id,
        )

    async def join_room(self, connection_id: str, room_id: str):
        """Add a connection to a room."""
        info = self._connections.get(connection_id)
        if not info:
            return

        info.rooms.add(room_id)
        self._room_connections[room_id].add(connection_id)

        logger.debug(
            "connection_joined_room",
            connection_id=connection_id,
            room_id=room_id,
        )

    async def leave_room(self, connection_id: str, room_id: str):
        """Remove a connection from a room."""
        info = self._connections.get(connection_id)
        if not info:
            return

        info.rooms.discard(room_id)
        self._room_connections[room_id].discard(connection_id)

        # Clean up empty rooms
        if not self._room_connections[room_id]:
            del self._room_connections[room_id]

        logger.debug(
            "connection_left_room",
            connection_id=connection_id,
            room_id=room_id,
        )

    async def _send_to_connection(
        self, connection_id: str, event: RealtimeEvent
    ) -> bool:
        """Send an event to a specific connection.

        Returns True if successful, False otherwise.
        """
        info = self._connections.get(connection_id)
        if not info:
            return False

        try:
            await info.websocket.send_json(event.model_dump(mode="json"))
            return True
        except WebSocketDisconnect:
            await self.disconnect(connection_id)
            return False
        except Exception as e:
            logger.error(
                "websocket_send_error",
                connection_id=connection_id,
                error=str(e),
            )
            await self.disconnect(connection_id)
            return False

    async def broadcast_to_room(
        self,
        room_id: str,
        event: RealtimeEvent,
        exclude_connections: set[str] | None = None,
    ) -> int:
        """Broadcast an event to all connections in a room.

        Args:
            room_id: Room ID to broadcast to
            event: Event to broadcast
            exclude_connections: Optional set of connection IDs to exclude

        Returns:
            Number of connections that received the event
        """
        exclude = exclude_connections or set()
        connection_ids = self._room_connections.get(room_id, set())
        sent_count = 0

        # Buffer event for replay
        self._buffer_event(room_id, event)

        # Send to all connections in room
        for conn_id in list(connection_ids):
            if conn_id in exclude:
                continue

            if await self._send_to_connection(conn_id, event):
                sent_count += 1

        logger.debug(
            "broadcast_to_room",
            room_id=room_id,
            event_type=event.type,
            sent_count=sent_count,
            total_connections=len(connection_ids),
        )

        return sent_count

    async def broadcast_to_tenant(
        self,
        tenant_id: str,
        event: RealtimeEvent,
        exclude_connections: set[str] | None = None,
    ) -> int:
        """Broadcast an event to all connections for a tenant.

        Args:
            tenant_id: Tenant ID
            event: Event to broadcast
            exclude_connections: Optional set of connection IDs to exclude

        Returns:
            Number of connections that received the event
        """
        room_id = self._generate_room_id(tenant_id)
        return await self.broadcast_to_room(room_id, event, exclude_connections)

    async def broadcast_to_incident(
        self,
        tenant_id: str,
        incident_id: str,
        event: RealtimeEvent,
        exclude_connections: set[str] | None = None,
    ) -> int:
        """Broadcast an event to all connections watching an incident.

        Args:
            tenant_id: Tenant ID
            incident_id: Incident ID
            event: Event to broadcast
            exclude_connections: Optional set of connection IDs to exclude

        Returns:
            Number of connections that received the event
        """
        room_id = self._generate_room_id(tenant_id, incident_id)
        return await self.broadcast_to_room(room_id, event, exclude_connections)

    def _buffer_event(self, room_id: str, event: RealtimeEvent):
        """Buffer an event for replay on reconnection."""
        buffer = self._event_buffer[room_id]
        buffer.append(event)
        self._event_timestamps[event.id] = datetime.utcnow()

        # Trim buffer if too large
        if len(buffer) > self.EVENT_BUFFER_SIZE:
            removed = buffer[: len(buffer) - self.EVENT_BUFFER_SIZE]
            self._event_buffer[room_id] = buffer[-self.EVENT_BUFFER_SIZE :]
            for evt in removed:
                self._event_timestamps.pop(evt.id, None)

        # Clean old events
        self._clean_old_events(room_id)

    def _clean_old_events(self, room_id: str):
        """Remove events older than TTL."""
        cutoff = datetime.utcnow() - timedelta(seconds=self.EVENT_BUFFER_TTL_SECONDS)
        buffer = self._event_buffer.get(room_id, [])

        new_buffer = []
        for event in buffer:
            timestamp = self._event_timestamps.get(event.id)
            if timestamp and timestamp > cutoff:
                new_buffer.append(event)
            else:
                self._event_timestamps.pop(event.id, None)

        self._event_buffer[room_id] = new_buffer

    async def _replay_events(self, connection_id: str, last_event_id: str):
        """Replay events after last_event_id for reconnection."""
        info = self._connections.get(connection_id)
        if not info:
            return

        replayed = 0
        found_last = False

        for room_id in info.rooms:
            buffer = self._event_buffer.get(room_id, [])

            for event in buffer:
                if found_last:
                    await self._send_to_connection(connection_id, event)
                    replayed += 1
                elif event.id == last_event_id:
                    found_last = True

        if replayed > 0:
            logger.info(
                "events_replayed",
                connection_id=connection_id,
                last_event_id=last_event_id,
                replayed_count=replayed,
            )

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to all connections."""
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)

                for conn_id, info in list(self._connections.items()):
                    event = create_event(
                        EventType.HEARTBEAT,
                        info.tenant_id,
                        HeartbeatPayload(connection_id=conn_id),
                    )

                    success = await self._send_to_connection(conn_id, event)
                    if success:
                        info.last_ping = datetime.utcnow()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))

    # --- Status and Metrics ---

    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)

    def get_tenant_connection_count(self, tenant_id: str) -> int:
        """Get number of connections for a tenant."""
        return len(self._tenant_connections.get(tenant_id, set()))

    def get_room_connection_count(self, room_id: str) -> int:
        """Get number of connections in a room."""
        return len(self._room_connections.get(room_id, set()))

    def get_connection_info(self, connection_id: str) -> ConnectionInfo | None:
        """Get information about a connection."""
        return self._connections.get(connection_id)

    def get_tenant_connections(self, tenant_id: str) -> list[ConnectionInfo]:
        """Get all connections for a tenant."""
        conn_ids = self._tenant_connections.get(tenant_id, set())
        return [self._connections[cid] for cid in conn_ids if cid in self._connections]

    def get_stats(self) -> dict[str, Any]:
        """Get connection manager statistics."""
        return {
            "total_connections": len(self._connections),
            "total_tenants": len(self._tenant_connections),
            "total_rooms": len(self._room_connections),
            "event_buffer_size": sum(
                len(buf) for buf in self._event_buffer.values()
            ),
            "connections_by_tenant": {
                tid: len(conns) for tid, conns in self._tenant_connections.items()
            },
        }


# Global connection manager instance
connection_manager = ConnectionManager()
