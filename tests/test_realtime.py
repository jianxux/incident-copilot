"""Tests for the real-time WebSocket updates module."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient

from src.realtime.broadcaster import Broadcaster
from src.realtime.events import (
    AssignmentChangedPayload,
    CommentAddedPayload,
    ConnectedPayload,
    EventType,
    HeartbeatPayload,
    IncidentCreatedPayload,
    IncidentResolvedPayload,
    IncidentUpdatedPayload,
    RealtimeEvent,
    TimelineEventPayload,
    UserPresencePayload,
    UserTypingPayload,
    create_event,
)
from src.realtime.manager import ConnectionInfo, ConnectionManager
from src.realtime.routes import router


# --- Fixtures ---


@pytest.fixture
def manager():
    """Create a fresh connection manager for testing."""
    return ConnectionManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock(spec=WebSocket)
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(router)
    return app


# --- Event Model Tests ---


class TestEventModels:
    """Tests for event models."""

    def test_realtime_event_creation(self):
        """Test creating a RealtimeEvent."""
        event = RealtimeEvent(
            id="evt-123",
            type=EventType.INCIDENT_CREATED,
            tenant_id="tenant-1",
            incident_id="inc-456",
            payload={"title": "Test Incident"},
        )

        assert event.id == "evt-123"
        assert event.type == "incident.created"
        assert event.tenant_id == "tenant-1"
        assert event.incident_id == "inc-456"
        assert event.payload["title"] == "Test Incident"

    def test_incident_created_payload(self):
        """Test IncidentCreatedPayload."""
        payload = IncidentCreatedPayload(
            incident_id="inc-123",
            title="Database connection failure",
            severity="critical",
            service_name="api-gateway",
            triggered_at=datetime.utcnow(),
            alert_url="https://pagerduty.com/...",
        )

        assert payload.incident_id == "inc-123"
        assert payload.severity == "critical"

    def test_incident_updated_payload(self):
        """Test IncidentUpdatedPayload."""
        payload = IncidentUpdatedPayload(
            incident_id="inc-123",
            changes={
                "status": {"old": "open", "new": "acknowledged"},
                "severity": {"old": "high", "new": "critical"},
            },
        )

        assert "status" in payload.changes
        assert payload.updated_fields == ["status", "severity"]

    def test_incident_resolved_payload(self):
        """Test IncidentResolvedPayload."""
        payload = IncidentResolvedPayload(
            incident_id="inc-123",
            resolution_summary="Fixed by restarting the service",
            time_to_resolve_minutes=45,
        )

        assert payload.resolution_summary == "Fixed by restarting the service"
        assert payload.time_to_resolve_minutes == 45

    def test_comment_added_payload(self):
        """Test CommentAddedPayload."""
        payload = CommentAddedPayload(
            comment_id="comment-001",
            incident_id="inc-123",
            author_id="user-789",
            author_name="John Doe",
            content="Looking into this now",
            is_internal=False,
        )

        assert payload.author_name == "John Doe"
        assert payload.is_internal is False

    def test_timeline_event_payload(self):
        """Test TimelineEventPayload."""
        payload = TimelineEventPayload(
            event_id="evt-001",
            incident_id="inc-123",
            event_type="deploy_detected",
            title="Deployment to production",
            metadata={"sha": "abc123", "author": "john"},
        )

        assert payload.event_type == "deploy_detected"
        assert payload.metadata["sha"] == "abc123"

    def test_assignment_changed_payload(self):
        """Test AssignmentChangedPayload."""
        payload = AssignmentChangedPayload(
            incident_id="inc-123",
            previous_assignees=["user-1"],
            new_assignees=["user-1", "user-2"],
            assigned_by="user-admin",
        )

        assert len(payload.new_assignees) == 2
        assert payload.assigned_by == "user-admin"

    def test_user_presence_payload(self):
        """Test UserPresencePayload."""
        payload = UserPresencePayload(
            user_id="user-123",
            user_name="Jane Doe",
            avatar_url="https://example.com/avatar.png",
            incident_id="inc-456",
        )

        assert payload.user_name == "Jane Doe"

    def test_user_typing_payload(self):
        """Test UserTypingPayload."""
        payload = UserTypingPayload(
            user_id="user-123",
            user_name="Jane Doe",
            incident_id="inc-456",
            is_typing=True,
        )

        assert payload.is_typing is True

    def test_heartbeat_payload(self):
        """Test HeartbeatPayload."""
        payload = HeartbeatPayload(connection_id="conn-123")

        assert payload.connection_id == "conn-123"
        assert payload.server_time is not None

    def test_connected_payload(self):
        """Test ConnectedPayload."""
        payload = ConnectedPayload(
            connection_id="conn-123",
            rooms=["tenant:t1", "incident:t1:i1"],
            last_event_id="evt-100",
        )

        assert len(payload.rooms) == 2
        assert payload.last_event_id == "evt-100"

    def test_create_event_helper(self):
        """Test create_event helper function."""
        payload = IncidentCreatedPayload(
            incident_id="inc-123",
            title="Test",
            severity="high",
            service_name="api",
            triggered_at=datetime.utcnow(),
        )

        event = create_event(
            EventType.INCIDENT_CREATED,
            "tenant-1",
            payload,
            incident_id="inc-123",
            actor_id="user-1",
            actor_name="Test User",
        )

        assert event.type == "incident.created"
        assert event.tenant_id == "tenant-1"
        assert event.incident_id == "inc-123"
        assert event.actor_id == "user-1"
        assert event.actor_name == "Test User"
        assert event.id is not None  # Auto-generated

    def test_create_event_with_dict_payload(self):
        """Test create_event with dict payload."""
        event = create_event(
            EventType.INCIDENT_UPDATED,
            "tenant-1",
            {"changes": {"status": "resolved"}},
            incident_id="inc-123",
        )

        assert event.payload["changes"]["status"] == "resolved"


# --- Connection Manager Tests ---


class TestConnectionManager:
    """Tests for ConnectionManager."""

    @pytest.mark.asyncio
    async def test_connect_success(self, manager, mock_websocket):
        """Test successful connection."""
        info = await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
            user_id="user-1",
            user_name="Test User",
        )

        assert info is not None
        assert info.tenant_id == "tenant-1"
        assert info.user_id == "user-1"
        assert info.user_name == "Test User"
        assert len(info.rooms) == 1  # Auto-joined tenant room
        assert "tenant:tenant-1" in info.rooms

        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_incident(self, manager, mock_websocket):
        """Test connection with auto-join incident room."""
        info = await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
            user_id="user-1",
            incident_id="inc-123",
        )

        assert len(info.rooms) == 2
        assert "tenant:tenant-1" in info.rooms
        assert "incident:tenant-1:inc-123" in info.rooms

    @pytest.mark.asyncio
    async def test_disconnect(self, manager, mock_websocket):
        """Test disconnecting a connection."""
        info = await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
            user_id="user-1",
        )

        await manager.disconnect(info.connection_id)

        assert manager.get_connection_count() == 0
        assert manager.get_connection_info(info.connection_id) is None

    @pytest.mark.asyncio
    async def test_join_room(self, manager, mock_websocket):
        """Test joining a room."""
        info = await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
        )

        await manager.join_room(info.connection_id, "incident:tenant-1:inc-456")

        assert "incident:tenant-1:inc-456" in info.rooms
        assert manager.get_room_connection_count("incident:tenant-1:inc-456") == 1

    @pytest.mark.asyncio
    async def test_leave_room(self, manager, mock_websocket):
        """Test leaving a room."""
        info = await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
            incident_id="inc-123",
        )

        await manager.leave_room(info.connection_id, "incident:tenant-1:inc-123")

        assert "incident:tenant-1:inc-123" not in info.rooms

    @pytest.mark.asyncio
    async def test_broadcast_to_room(self, manager, mock_websocket):
        """Test broadcasting to a room."""
        info = await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
        )

        event = create_event(
            EventType.INCIDENT_CREATED,
            "tenant-1",
            {"incident_id": "inc-123"},
        )

        count = await manager.broadcast_to_room("tenant:tenant-1", event)

        assert count == 1
        # First call is connected event, second is our broadcast
        assert mock_websocket.send_json.call_count == 2

    @pytest.mark.asyncio
    async def test_broadcast_to_tenant(self, manager, mock_websocket):
        """Test broadcasting to a tenant."""
        await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
        )

        event = create_event(
            EventType.INCIDENT_UPDATED,
            "tenant-1",
            {"incident_id": "inc-123"},
        )

        count = await manager.broadcast_to_tenant("tenant-1", event)

        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_to_incident(self, manager, mock_websocket):
        """Test broadcasting to an incident room."""
        await manager.connect(
            mock_websocket,
            tenant_id="tenant-1",
            incident_id="inc-123",
        )

        event = create_event(
            EventType.COMMENT_ADDED,
            "tenant-1",
            {"comment": "test"},
            incident_id="inc-123",
        )

        count = await manager.broadcast_to_incident("tenant-1", "inc-123", event)

        assert count == 1

    @pytest.mark.asyncio
    async def test_broadcast_excludes_connections(self, manager):
        """Test that broadcast excludes specified connections."""
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)

        info1 = await manager.connect(ws1, tenant_id="tenant-1")
        info2 = await manager.connect(ws2, tenant_id="tenant-1")

        event = create_event(
            EventType.INCIDENT_UPDATED,
            "tenant-1",
            {"test": "data"},
        )

        count = await manager.broadcast_to_tenant(
            "tenant-1", event, exclude_connections={info1.connection_id}
        )

        # Only ws2 should receive (info1 excluded)
        assert count == 1
        # ws2 receives: connected + broadcast = 2
        # ws1 receives: connected only = 1
        assert ws2.send_json.call_count == 2
        assert ws1.send_json.call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limit_tenant(self, manager):
        """Test tenant connection rate limiting."""
        manager.MAX_CONNECTIONS_PER_TENANT = 3

        connections = []
        for i in range(3):
            ws = AsyncMock(spec=WebSocket)
            info = await manager.connect(ws, tenant_id="tenant-1")
            assert info is not None
            connections.append(info)

        # 4th connection should be rate limited
        ws4 = AsyncMock(spec=WebSocket)
        info4 = await manager.connect(ws4, tenant_id="tenant-1")

        assert info4 is None
        ws4.close.assert_called()

    @pytest.mark.asyncio
    async def test_rate_limit_user(self, manager):
        """Test user connection rate limiting."""
        manager.MAX_CONNECTIONS_PER_USER = 2

        # First 2 connections OK
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)

        info1 = await manager.connect(ws1, tenant_id="tenant-1", user_id="user-1")
        info2 = await manager.connect(ws2, tenant_id="tenant-1", user_id="user-1")

        assert info1 is not None
        assert info2 is not None

        # 3rd connection for same user should be rate limited
        ws3 = AsyncMock(spec=WebSocket)
        info3 = await manager.connect(ws3, tenant_id="tenant-1", user_id="user-1")

        assert info3 is None
        ws3.close.assert_called()

    @pytest.mark.asyncio
    async def test_get_stats(self, manager, mock_websocket):
        """Test getting connection statistics."""
        await manager.connect(mock_websocket, tenant_id="tenant-1")

        stats = manager.get_stats()

        assert stats["total_connections"] == 1
        assert stats["total_tenants"] == 1
        assert stats["connections_by_tenant"]["tenant-1"] == 1

    @pytest.mark.asyncio
    async def test_get_tenant_connections(self, manager):
        """Test getting all connections for a tenant."""
        ws1 = AsyncMock(spec=WebSocket)
        ws2 = AsyncMock(spec=WebSocket)

        await manager.connect(ws1, tenant_id="tenant-1", user_id="user-1")
        await manager.connect(ws2, tenant_id="tenant-1", user_id="user-2")

        connections = manager.get_tenant_connections("tenant-1")

        assert len(connections) == 2

    @pytest.mark.asyncio
    async def test_event_buffering(self, manager, mock_websocket):
        """Test that events are buffered for replay."""
        await manager.connect(mock_websocket, tenant_id="tenant-1")

        # Broadcast some events
        for i in range(5):
            event = create_event(
                EventType.INCIDENT_UPDATED,
                "tenant-1",
                {"update": i},
            )
            await manager.broadcast_to_tenant("tenant-1", event)

        # Check buffer
        buffer = manager._event_buffer.get("tenant:tenant-1", [])
        assert len(buffer) == 5

    @pytest.mark.asyncio
    async def test_event_buffer_limit(self, manager, mock_websocket):
        """Test that event buffer is trimmed when full."""
        manager.EVENT_BUFFER_SIZE = 10

        await manager.connect(mock_websocket, tenant_id="tenant-1")

        # Broadcast more events than buffer size
        for i in range(15):
            event = create_event(
                EventType.INCIDENT_UPDATED,
                "tenant-1",
                {"update": i},
            )
            await manager.broadcast_to_tenant("tenant-1", event)

        # Buffer should be trimmed to max size
        buffer = manager._event_buffer.get("tenant:tenant-1", [])
        assert len(buffer) <= 10


# --- Broadcaster Tests ---


class TestBroadcaster:
    """Tests for the Broadcaster utility."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock connection manager."""
        manager = MagicMock(spec=ConnectionManager)
        manager.broadcast_to_tenant = AsyncMock(return_value=3)
        manager.broadcast_to_incident = AsyncMock(return_value=2)
        return manager

    @pytest.fixture
    def broadcaster(self, mock_manager):
        """Create a broadcaster with mock manager."""
        return Broadcaster(manager=mock_manager)

    @pytest.mark.asyncio
    async def test_broadcast_incident_created(self, broadcaster, mock_manager):
        """Test broadcasting incident created event."""
        count = await broadcaster.broadcast_incident_created(
            tenant_id="tenant-1",
            incident_id="inc-123",
            title="Database failure",
            severity="critical",
            service_name="api-gateway",
            actor_id="system",
        )

        assert count == 3
        mock_manager.broadcast_to_tenant.assert_called_once()
        call_args = mock_manager.broadcast_to_tenant.call_args
        assert call_args[0][0] == "tenant-1"
        event = call_args[0][1]
        assert event.type == "incident.created"

    @pytest.mark.asyncio
    async def test_broadcast_incident_updated(self, broadcaster, mock_manager):
        """Test broadcasting incident updated event."""
        count = await broadcaster.broadcast_incident_updated(
            tenant_id="tenant-1",
            incident_id="inc-123",
            changes={"status": {"old": "open", "new": "acknowledged"}},
            actor_id="user-1",
            actor_name="John Doe",
        )

        # Broadcasts to both tenant and incident rooms
        assert count == 5  # 3 + 2
        mock_manager.broadcast_to_tenant.assert_called_once()
        mock_manager.broadcast_to_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_incident_resolved(self, broadcaster, mock_manager):
        """Test broadcasting incident resolved event."""
        count = await broadcaster.broadcast_incident_resolved(
            tenant_id="tenant-1",
            incident_id="inc-123",
            resolution_summary="Restarted the service",
            time_to_resolve_minutes=30,
        )

        assert count == 5
        event = mock_manager.broadcast_to_tenant.call_args[0][1]
        assert event.type == "incident.resolved"

    @pytest.mark.asyncio
    async def test_broadcast_comment_added(self, broadcaster, mock_manager):
        """Test broadcasting comment added event."""
        count = await broadcaster.broadcast_comment_added(
            tenant_id="tenant-1",
            incident_id="inc-123",
            comment_id="comment-001",
            author_id="user-1",
            author_name="Jane Doe",
            content="Investigating now",
        )

        # Only broadcasts to incident room
        assert count == 2
        mock_manager.broadcast_to_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_timeline_event(self, broadcaster, mock_manager):
        """Test broadcasting timeline event."""
        count = await broadcaster.broadcast_timeline_event(
            tenant_id="tenant-1",
            incident_id="inc-123",
            event_id="evt-001",
            event_type="deploy_detected",
            title="Production deployment",
            metadata={"sha": "abc123"},
        )

        assert count == 2
        event = mock_manager.broadcast_to_incident.call_args[0][1]
        assert event.type == "timeline.event"

    @pytest.mark.asyncio
    async def test_broadcast_assignment_changed(self, broadcaster, mock_manager):
        """Test broadcasting assignment changed event."""
        count = await broadcaster.broadcast_assignment_changed(
            tenant_id="tenant-1",
            incident_id="inc-123",
            previous_assignees=["user-1"],
            new_assignees=["user-1", "user-2"],
            assigned_by="user-admin",
        )

        assert count == 5
        mock_manager.broadcast_to_tenant.assert_called_once()
        mock_manager.broadcast_to_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_user_typing(self, broadcaster, mock_manager):
        """Test broadcasting user typing event."""
        count = await broadcaster.broadcast_user_typing(
            tenant_id="tenant-1",
            incident_id="inc-123",
            user_id="user-1",
            user_name="Jane",
            is_typing=True,
        )

        assert count == 2
        event = mock_manager.broadcast_to_incident.call_args[0][1]
        assert event.type == "user.typing"

    @pytest.mark.asyncio
    async def test_broadcast_custom_event(self, broadcaster, mock_manager):
        """Test broadcasting custom event."""
        count = await broadcaster.broadcast_custom_event(
            event_type=EventType.INCIDENT_ACKNOWLEDGED,
            tenant_id="tenant-1",
            payload={"incident_id": "inc-123", "acknowledged_by": "user-1"},
            to_tenant=True,
            to_incident=False,
        )

        assert count == 3
        mock_manager.broadcast_to_tenant.assert_called_once()
        mock_manager.broadcast_to_incident.assert_not_called()


# --- Event Type Tests ---


class TestEventTypes:
    """Tests for EventType enum."""

    def test_incident_events(self):
        """Test incident event types."""
        assert EventType.INCIDENT_CREATED.value == "incident.created"
        assert EventType.INCIDENT_UPDATED.value == "incident.updated"
        assert EventType.INCIDENT_RESOLVED.value == "incident.resolved"
        assert EventType.INCIDENT_REOPENED.value == "incident.reopened"
        assert EventType.INCIDENT_ACKNOWLEDGED.value == "incident.acknowledged"

    def test_comment_events(self):
        """Test comment event types."""
        assert EventType.COMMENT_ADDED.value == "comment.added"
        assert EventType.COMMENT_UPDATED.value == "comment.updated"
        assert EventType.COMMENT_DELETED.value == "comment.deleted"

    def test_timeline_event(self):
        """Test timeline event type."""
        assert EventType.TIMELINE_EVENT.value == "timeline.event"

    def test_assignment_event(self):
        """Test assignment event type."""
        assert EventType.ASSIGNMENT_CHANGED.value == "assignment.changed"

    def test_user_events(self):
        """Test user event types."""
        assert EventType.USER_JOINED.value == "user.joined"
        assert EventType.USER_LEFT.value == "user.left"
        assert EventType.USER_TYPING.value == "user.typing"

    def test_system_events(self):
        """Test system event types."""
        assert EventType.HEARTBEAT.value == "system.heartbeat"
        assert EventType.ERROR.value == "system.error"
        assert EventType.CONNECTED.value == "system.connected"
        assert EventType.RECONNECTED.value == "system.reconnected"


# --- Connection Info Tests ---


class TestConnectionInfo:
    """Tests for ConnectionInfo dataclass."""

    def test_connection_info_creation(self):
        """Test creating ConnectionInfo."""
        ws = MagicMock(spec=WebSocket)
        info = ConnectionInfo(
            connection_id="conn-123",
            websocket=ws,
            tenant_id="tenant-1",
            user_id="user-1",
            user_name="Test User",
        )

        assert info.connection_id == "conn-123"
        assert info.tenant_id == "tenant-1"
        assert info.user_id == "user-1"
        assert info.user_name == "Test User"
        assert len(info.rooms) == 0
        assert info.last_event_id is None

    def test_connection_info_with_rooms(self):
        """Test ConnectionInfo with rooms."""
        ws = MagicMock(spec=WebSocket)
        info = ConnectionInfo(
            connection_id="conn-123",
            websocket=ws,
            tenant_id="tenant-1",
            rooms={"room1", "room2"},
        )

        assert len(info.rooms) == 2
        assert "room1" in info.rooms


# --- Integration Tests ---


class TestWebSocketRoutes:
    """Integration tests for WebSocket routes."""

    def test_realtime_stats_endpoint(self, test_app):
        """Test the /stats endpoint."""
        client = TestClient(test_app)
        response = client.get("/api/realtime/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_connections" in data
        assert "total_tenants" in data

    def test_realtime_health_endpoint(self, test_app):
        """Test the /health endpoint."""
        client = TestClient(test_app)
        response = client.get("/api/realtime/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "connections" in data


# --- Room ID Generation Tests ---


class TestRoomIdGeneration:
    """Tests for room ID generation."""

    def test_tenant_room_id(self, manager):
        """Test generating tenant room ID."""
        room_id = manager._generate_room_id("tenant-123")
        assert room_id == "tenant:tenant-123"

    def test_incident_room_id(self, manager):
        """Test generating incident room ID."""
        room_id = manager._generate_room_id("tenant-123", "inc-456")
        assert room_id == "incident:tenant-123:inc-456"


# --- Heartbeat Tests ---


class TestHeartbeat:
    """Tests for heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_heartbeat_loop_sends_pings(self, manager, mock_websocket):
        """Test that heartbeat loop sends pings."""
        manager.HEARTBEAT_INTERVAL_SECONDS = 0.1  # Very short for testing

        await manager.connect(mock_websocket, tenant_id="tenant-1")
        await manager.start()

        # Wait for heartbeat
        await asyncio.sleep(0.15)

        await manager.stop()

        # Should have received connected event + at least one heartbeat
        assert mock_websocket.send_json.call_count >= 2

    @pytest.mark.asyncio
    async def test_manager_start_stop(self, manager):
        """Test starting and stopping the manager."""
        await manager.start()
        assert manager._running is True
        assert manager._heartbeat_task is not None

        await manager.stop()
        assert manager._running is False


# --- Error Handling Tests ---


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_send_to_disconnected_connection(self, manager, mock_websocket):
        """Test sending to a disconnected connection."""
        mock_websocket.send_json.side_effect = Exception("Connection closed")

        info = await manager.connect(mock_websocket, tenant_id="tenant-1")

        event = create_event(
            EventType.INCIDENT_UPDATED,
            "tenant-1",
            {"test": "data"},
        )

        # This should handle the exception gracefully
        result = await manager._send_to_connection(info.connection_id, event)

        assert result is False
        # Connection should be cleaned up
        assert manager.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_connection(self, manager):
        """Test disconnecting a non-existent connection."""
        # Should not raise
        await manager.disconnect("nonexistent-id")

    @pytest.mark.asyncio
    async def test_join_room_invalid_connection(self, manager):
        """Test joining a room with invalid connection ID."""
        # Should not raise
        await manager.join_room("nonexistent-id", "some-room")

    @pytest.mark.asyncio
    async def test_leave_room_invalid_connection(self, manager):
        """Test leaving a room with invalid connection ID."""
        # Should not raise
        await manager.leave_room("nonexistent-id", "some-room")
