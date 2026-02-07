"""Tests for WebSocket connections and realtime events."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.realtime.models import (
    AuthPayload,
    ConnectionInfo,
    MessageType,
    PresenceInfo,
    PresenceStatus,
    Room,
    RoomType,
    SubscriptionRequest,
    WebSocketMessage,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_connection() -> ConnectionInfo:
    """Create a sample WebSocket connection."""
    return ConnectionInfo(
        connection_id="conn-123",
        user_id="user-456",
        user_name="John Doe",
        subscriptions={"incident:inc-123", "service:payments"},
        message_count=5,
    )


class TestMessageType:
    """Tests for MessageType enum."""

    def test_client_message_types(self):
        """Test client-to-server message types exist."""
        assert MessageType.SUBSCRIBE.value == "subscribe"
        assert MessageType.UNSUBSCRIBE.value == "unsubscribe"
        assert MessageType.PING.value == "ping"
        assert MessageType.PRESENCE_UPDATE.value == "presence_update"

    def test_server_message_types(self):
        """Test server-to-client message types exist."""
        assert MessageType.SUBSCRIBED.value == "subscribed"
        assert MessageType.UNSUBSCRIBED.value == "unsubscribed"
        assert MessageType.PONG.value == "pong"
        assert MessageType.EVENT.value == "event"
        assert MessageType.ERROR.value == "error"


class TestRoomType:
    """Tests for RoomType enum."""

    def test_room_types(self):
        """Test all room types exist."""
        assert RoomType.INCIDENT.value == "incident"
        assert RoomType.SERVICE.value == "service"
        assert RoomType.TEAM.value == "team"
        assert RoomType.GLOBAL.value == "global"


class TestPresenceStatus:
    """Tests for PresenceStatus enum."""

    def test_presence_statuses(self):
        """Test all presence statuses exist."""
        assert PresenceStatus.VIEWING.value == "viewing"
        assert PresenceStatus.EDITING.value == "editing"
        assert PresenceStatus.IDLE.value == "idle"


class TestWebSocketMessage:
    """Tests for WebSocketMessage model."""

    def test_message_creation(self):
        """Test creating a WebSocket message."""
        msg = WebSocketMessage(
            type=MessageType.SUBSCRIBE,
            payload={"room_type": "incident", "room_id": "inc-123"},
            request_id="req-1",
        )
        assert msg.type == MessageType.SUBSCRIBE
        assert msg.payload["room_id"] == "inc-123"
        assert msg.request_id == "req-1"

    def test_message_timestamp(self):
        """Test message has timestamp."""
        msg = WebSocketMessage(type=MessageType.PING)
        assert msg.timestamp is not None
        assert isinstance(msg.timestamp, datetime)

    def test_message_default_payload(self):
        """Test message default empty payload."""
        msg = WebSocketMessage(type=MessageType.PONG)
        assert msg.payload == {}


class TestSubscriptionRequest:
    """Tests for SubscriptionRequest model."""

    def test_subscription_creation(self):
        """Test creating a subscription request."""
        sub = SubscriptionRequest(
            room_type=RoomType.INCIDENT,
            room_id="inc-123",
        )
        assert sub.room_type == RoomType.INCIDENT
        assert sub.room_id == "inc-123"

    def test_room_key_generation(self):
        """Test room key generation."""
        sub = SubscriptionRequest(
            room_type=RoomType.SERVICE,
            room_id="payments",
        )
        assert sub.room_key == "service:payments"

    def test_global_room_key(self):
        """Test global room key."""
        sub = SubscriptionRequest(
            room_type=RoomType.GLOBAL,
            room_id="all",
        )
        assert sub.room_key == "global:all"


class TestPresenceInfo:
    """Tests for PresenceInfo model."""

    def test_presence_creation(self):
        """Test creating presence info."""
        presence = PresenceInfo(
            user_id="user-123",
            user_name="Alice",
            status=PresenceStatus.VIEWING,
            room_key="incident:inc-456",
        )
        assert presence.user_id == "user-123"
        assert presence.status == PresenceStatus.VIEWING

    def test_presence_timestamps(self):
        """Test presence timestamps."""
        presence = PresenceInfo(
            user_id="user-123",
            user_name="Bob",
            room_key="incident:inc-789",
        )
        assert presence.joined_at is not None
        assert presence.last_activity is not None

    def test_presence_metadata(self):
        """Test presence with metadata."""
        presence = PresenceInfo(
            user_id="user-123",
            user_name="Charlie",
            room_key="incident:inc-123",
            metadata={"cursor_position": 100, "selected_tab": "timeline"},
        )
        assert presence.metadata["cursor_position"] == 100


class TestRoom:
    """Tests for Room model."""

    def test_room_creation(self):
        """Test creating a room."""
        room = Room(
            room_type=RoomType.INCIDENT,
            room_id="inc-123",
        )
        assert room.room_type == RoomType.INCIDENT
        assert room.room_key == "incident:inc-123"

    def test_room_timestamp(self):
        """Test room creation timestamp."""
        room = Room(
            room_type=RoomType.TEAM,
            room_id="platform",
        )
        assert room.created_at is not None


class TestConnectionInfo:
    """Tests for ConnectionInfo model."""

    def test_connection_creation(self, sample_connection):
        """Test creating connection info."""
        assert sample_connection.connection_id == "conn-123"
        assert sample_connection.user_id == "user-456"
        assert len(sample_connection.subscriptions) == 2

    def test_connection_defaults(self):
        """Test connection default values."""
        conn = ConnectionInfo(
            connection_id="conn-new",
            user_id="user-new",
            user_name="New User",
        )
        assert conn.message_count == 0
        assert conn.rate_limit_remaining == 100
        assert len(conn.subscriptions) == 0

    def test_connection_timestamps(self):
        """Test connection timestamps."""
        conn = ConnectionInfo(
            connection_id="conn-123",
            user_id="user-123",
            user_name="Test User",
        )
        assert conn.connected_at is not None
        assert conn.last_ping is not None


class TestAuthPayload:
    """Tests for AuthPayload model."""

    def test_auth_with_token_only(self):
        """Test auth with just token."""
        auth = AuthPayload(token="jwt-token-here")
        assert auth.token == "jwt-token-here"
        assert auth.user_id is None

    def test_auth_with_user_info(self):
        """Test auth with full user info."""
        auth = AuthPayload(
            token="jwt-token",
            user_id="user-123",
            user_name="John Doe",
        )
        assert auth.user_id == "user-123"
        assert auth.user_name == "John Doe"


class TestRealtimeAPI:
    """Tests for Realtime API endpoints."""

    def test_websocket_connection_info(self, client):
        """Test GET /api/realtime/status endpoint."""
        response = client.get("/api/realtime/status")
        assert response.status_code == 200
        data = response.json()
        assert "connections" in data or "status" in data

    def test_list_active_rooms(self, client):
        """Test GET /api/realtime/rooms endpoint."""
        response = client.get("/api/realtime/rooms")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_room_presence(self, client):
        """Test GET /api/realtime/rooms/{room_key}/presence endpoint."""
        response = client.get("/api/realtime/rooms/incident:inc-123/presence")
        assert response.status_code in (200, 404)

    def test_broadcast_event(self, client):
        """Test POST /api/realtime/broadcast endpoint."""
        response = client.post(
            "/api/realtime/broadcast",
            json={
                "room_type": "incident",
                "room_id": "inc-123",
                "event_type": "timeline_update",
                "data": {"message": "New event added"},
            },
        )
        assert response.status_code in (200, 202)

    def test_get_connection_stats(self, client):
        """Test GET /api/realtime/stats endpoint."""
        response = client.get("/api/realtime/stats")
        assert response.status_code == 200

    def test_disconnect_user(self, client):
        """Test POST /api/realtime/disconnect endpoint."""
        response = client.post(
            "/api/realtime/disconnect",
            json={"user_id": "user-123"},
        )
        assert response.status_code in (200, 404)


class TestWebSocketEndpoints:
    """Tests for WebSocket endpoint behavior."""

    def test_websocket_connect(self, client):
        """Test WebSocket connection."""
        with client.websocket_connect("/ws") as websocket:
            # Should receive connected message
            data = websocket.receive_json()
            assert data["type"] == "connected"

    def test_websocket_ping_pong(self, client):
        """Test WebSocket ping/pong."""
        with client.websocket_connect("/ws") as websocket:
            # Skip connected message
            websocket.receive_json()

            # Send ping
            websocket.send_json({"type": "ping"})

            # Should receive pong
            data = websocket.receive_json()
            assert data["type"] == "pong"

    def test_websocket_subscribe(self, client):
        """Test WebSocket subscription."""
        with client.websocket_connect("/ws") as websocket:
            # Skip connected message
            websocket.receive_json()

            # Subscribe to incident room
            websocket.send_json({
                "type": "subscribe",
                "payload": {"room_type": "incident", "room_id": "inc-123"},
            })

            # Should receive subscribed confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"

    def test_websocket_invalid_message(self, client):
        """Test WebSocket handles invalid messages."""
        with client.websocket_connect("/ws") as websocket:
            # Skip connected message
            websocket.receive_json()

            # Send invalid message
            websocket.send_json({"type": "invalid_type"})

            # Should receive error
            data = websocket.receive_json()
            assert data["type"] == "error"
