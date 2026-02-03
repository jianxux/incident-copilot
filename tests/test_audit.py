"""Tests for audit logging module."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.audit.logger import AuditLogger
from src.audit.models import (
    AuditEvent,
    AuditLogQuery,
    EventCategory,
    EventType,
    Outcome,
)
from src.audit.store import AuditStore


# Create a minimal test app for API tests
def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing."""
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/audit/logs")
    def get_audit_logs():
        # Simulate auth required
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    @app.get("/api/v1/audit/logs/export")
    def export_audit_logs():
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    @app.get("/api/v1/audit/stats")
    def get_audit_stats():
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Not authenticated")

    return app


@pytest.fixture
def client():
    """Create test client."""
    app = create_test_app()
    return TestClient(app)


@pytest.fixture
async def audit_store():
    """Create a fresh audit store for testing."""
    store = AuditStore(max_events_memory=1000)
    yield store


@pytest.fixture
def audit_logger(audit_store):
    """Create an audit logger with test store."""
    return AuditLogger(store=audit_store)


class TestAuditEvent:
    """Tests for AuditEvent model."""

    def test_create_event(self):
        """Test creating a basic audit event."""
        event = AuditEvent(
            event_type=EventType.LOGIN_SUCCESS,
            category=EventCategory.AUTHENTICATION,
            action="User logged in",
            tenant_id="tenant-123",
            user_id="user-456",
            user_email="test@example.com",
        )

        assert event.event_type == EventType.LOGIN_SUCCESS
        assert event.category == EventCategory.AUTHENTICATION
        assert event.tenant_id == "tenant-123"
        assert event.user_id == "user-456"
        assert event.outcome == Outcome.SUCCESS
        assert event.id is not None
        assert event.timestamp is not None

    def test_event_with_metadata(self):
        """Test creating an event with metadata."""
        event = AuditEvent(
            event_type=EventType.SETTINGS_UPDATED,
            category=EventCategory.CONFIGURATION,
            action="Updated notification settings",
            tenant_id="tenant-123",
            user_id="user-456",
            resource_type="setting",
            resource_id="notifications",
            metadata={"old_value": "email", "new_value": "slack"},
        )

        assert event.metadata["old_value"] == "email"
        assert event.metadata["new_value"] == "slack"
        assert event.resource_type == "setting"
        assert event.resource_id == "notifications"

    def test_event_serialization(self):
        """Test event JSON serialization."""
        event = AuditEvent(
            event_type=EventType.LOGIN_SUCCESS,
            category=EventCategory.AUTHENTICATION,
            action="User logged in",
            tenant_id="tenant-123",
        )

        data = event.model_dump(mode="json")

        assert data["event_type"] == "login_success"
        assert data["category"] == "authentication"
        assert data["outcome"] == "success"
        assert "timestamp" in data


class TestEventTypes:
    """Tests for event type enums."""

    def test_all_event_types_have_values(self):
        """Ensure all event types have string values."""
        for event_type in EventType:
            assert isinstance(event_type.value, str)
            assert len(event_type.value) > 0

    def test_all_categories_have_values(self):
        """Ensure all categories have string values."""
        for category in EventCategory:
            assert isinstance(category.value, str)
            assert len(category.value) > 0

    def test_outcomes(self):
        """Test outcome enum values."""
        assert Outcome.SUCCESS.value == "success"
        assert Outcome.FAILURE.value == "failure"
        assert Outcome.DENIED.value == "denied"
        assert Outcome.ERROR.value == "error"


class TestAuditStore:
    """Tests for AuditStore."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_event(self):
        """Test storing and retrieving an event."""
        store = AuditStore()
        event = AuditEvent(
            event_type=EventType.LOGIN_SUCCESS,
            category=EventCategory.AUTHENTICATION,
            action="User logged in",
            tenant_id="tenant-123",
            user_id="user-456",
        )

        stored = await store.store_event(event)
        assert stored.id == event.id

        # Query it back
        query = AuditLogQuery(tenant_id="tenant-123", limit=10)
        events = await store.query_events(query)

        assert len(events) == 1
        assert events[0].id == event.id
        assert events[0].event_type == EventType.LOGIN_SUCCESS

    @pytest.mark.asyncio
    async def test_tenant_isolation(self):
        """Test that queries are isolated by tenant."""
        store = AuditStore()

        # Store events for different tenants
        await store.store_event(
            AuditEvent(
                event_type=EventType.LOGIN_SUCCESS,
                category=EventCategory.AUTHENTICATION,
                action="Login",
                tenant_id="tenant-a",
            )
        )
        await store.store_event(
            AuditEvent(
                event_type=EventType.LOGIN_SUCCESS,
                category=EventCategory.AUTHENTICATION,
                action="Login",
                tenant_id="tenant-b",
            )
        )

        # Query tenant A
        query_a = AuditLogQuery(tenant_id="tenant-a", limit=10)
        events_a = await store.query_events(query_a)
        assert len(events_a) == 1
        assert events_a[0].tenant_id == "tenant-a"

        # Query tenant B
        query_b = AuditLogQuery(tenant_id="tenant-b", limit=10)
        events_b = await store.query_events(query_b)
        assert len(events_b) == 1
        assert events_b[0].tenant_id == "tenant-b"

    @pytest.mark.asyncio
    async def test_date_range_filter(self):
        """Test filtering by date range."""
        store = AuditStore()
        now = datetime.utcnow()

        # Create events at different times
        old_event = AuditEvent(
            event_type=EventType.LOGIN_SUCCESS,
            category=EventCategory.AUTHENTICATION,
            action="Old login",
            tenant_id="tenant-123",
            timestamp=now - timedelta(days=10),
        )
        recent_event = AuditEvent(
            event_type=EventType.LOGIN_SUCCESS,
            category=EventCategory.AUTHENTICATION,
            action="Recent login",
            tenant_id="tenant-123",
            timestamp=now - timedelta(hours=1),
        )

        await store.store_event(old_event)
        await store.store_event(recent_event)

        # Query last 7 days
        query = AuditLogQuery(
            tenant_id="tenant-123",
            start_date=now - timedelta(days=7),
            end_date=now,
            limit=10,
        )
        events = await store.query_events(query)

        assert len(events) == 1
        assert events[0].action == "Recent login"

    @pytest.mark.asyncio
    async def test_event_type_filter(self):
        """Test filtering by event type."""
        store = AuditStore()

        await store.store_event(
            AuditEvent(
                event_type=EventType.LOGIN_SUCCESS,
                category=EventCategory.AUTHENTICATION,
                action="Login",
                tenant_id="tenant-123",
            )
        )
        await store.store_event(
            AuditEvent(
                event_type=EventType.LOGIN_FAILURE,
                category=EventCategory.AUTHENTICATION,
                action="Failed login",
                tenant_id="tenant-123",
            )
        )

        query = AuditLogQuery(
            tenant_id="tenant-123",
            event_types=[EventType.LOGIN_FAILURE],
            limit=10,
        )
        events = await store.query_events(query)

        assert len(events) == 1
        assert events[0].event_type == EventType.LOGIN_FAILURE

    @pytest.mark.asyncio
    async def test_category_filter(self):
        """Test filtering by category."""
        store = AuditStore()

        await store.store_event(
            AuditEvent(
                event_type=EventType.LOGIN_SUCCESS,
                category=EventCategory.AUTHENTICATION,
                action="Login",
                tenant_id="tenant-123",
            )
        )
        await store.store_event(
            AuditEvent(
                event_type=EventType.API_KEY_CREATED,
                category=EventCategory.API_KEY,
                action="Created API key",
                tenant_id="tenant-123",
            )
        )

        query = AuditLogQuery(
            tenant_id="tenant-123",
            categories=[EventCategory.API_KEY],
            limit=10,
        )
        events = await store.query_events(query)

        assert len(events) == 1
        assert events[0].category == EventCategory.API_KEY

    @pytest.mark.asyncio
    async def test_pagination(self):
        """Test pagination of results."""
        store = AuditStore()

        # Create 25 events
        for i in range(25):
            await store.store_event(
                AuditEvent(
                    event_type=EventType.LOGIN_SUCCESS,
                    category=EventCategory.AUTHENTICATION,
                    action=f"Login {i}",
                    tenant_id="tenant-123",
                )
            )

        # Get first page
        query1 = AuditLogQuery(tenant_id="tenant-123", limit=10, offset=0)
        page1 = await store.query_events(query1)
        assert len(page1) == 10

        # Get second page
        query2 = AuditLogQuery(tenant_id="tenant-123", limit=10, offset=10)
        page2 = await store.query_events(query2)
        assert len(page2) == 10

        # Get third page
        query3 = AuditLogQuery(tenant_id="tenant-123", limit=10, offset=20)
        page3 = await store.query_events(query3)
        assert len(page3) == 5

    @pytest.mark.asyncio
    async def test_count_events(self):
        """Test counting events."""
        store = AuditStore()

        for i in range(15):
            await store.store_event(
                AuditEvent(
                    event_type=EventType.LOGIN_SUCCESS,
                    category=EventCategory.AUTHENTICATION,
                    action=f"Login {i}",
                    tenant_id="tenant-123",
                )
            )

        query = AuditLogQuery(tenant_id="tenant-123", limit=10)
        count = await store.count_events(query)

        assert count == 15

    @pytest.mark.asyncio
    async def test_memory_limit(self):
        """Test that memory store respects max limit."""
        store = AuditStore(max_events_memory=10)

        # Create 15 events
        for i in range(15):
            await store.store_event(
                AuditEvent(
                    event_type=EventType.LOGIN_SUCCESS,
                    category=EventCategory.AUTHENTICATION,
                    action=f"Login {i}",
                    tenant_id="tenant-123",
                )
            )

        # Should only have 10 (oldest removed)
        query = AuditLogQuery(tenant_id="tenant-123", limit=100)
        events = await store.query_events(query)

        assert len(events) == 10


class TestAuditLogger:
    """Tests for AuditLogger."""

    @pytest.mark.asyncio
    async def test_log_login_success(self):
        """Test logging a successful login."""
        store = AuditStore()
        logger = AuditLogger(store=store)

        event = await logger.log_login_success(
            tenant_id="tenant-123",
            user_id="user-456",
            user_email="test@example.com",
            provider="github",
            ip_address="1.2.3.4",
        )

        assert event.event_type == EventType.LOGIN_SUCCESS
        assert event.category == EventCategory.AUTHENTICATION
        assert event.tenant_id == "tenant-123"
        assert event.user_id == "user-456"
        assert event.metadata["provider"] == "github"
        assert event.ip_address == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_log_login_failure(self):
        """Test logging a failed login."""
        store = AuditStore()
        logger = AuditLogger(store=store)

        event = await logger.log_login_failure(
            email="attacker@example.com",
            reason="invalid_password",
            ip_address="5.6.7.8",
        )

        assert event.event_type == EventType.LOGIN_FAILURE
        assert event.outcome == Outcome.FAILURE
        assert event.metadata["reason"] == "invalid_password"

    @pytest.mark.asyncio
    async def test_log_access_denied(self):
        """Test logging access denied."""
        store = AuditStore()
        logger = AuditLogger(store=store)

        event = await logger.log_access_denied(
            tenant_id="tenant-123",
            user_id="user-456",
            resource_type="incident",
            resource_id="inc-789",
            action="delete",
            reason="insufficient_permissions",
        )

        assert event.event_type == EventType.ACCESS_DENIED
        assert event.category == EventCategory.AUTHORIZATION
        assert event.outcome == Outcome.DENIED
        assert event.resource_type == "incident"
        assert event.resource_id == "inc-789"

    @pytest.mark.asyncio
    async def test_log_api_key_created(self):
        """Test logging API key creation."""
        store = AuditStore()
        logger = AuditLogger(store=store)

        event = await logger.log_api_key_created(
            tenant_id="tenant-123",
            user_id="user-456",
            api_key_id="key-789",
            key_name="Production Key",
            scopes=["read", "write"],
        )

        assert event.event_type == EventType.API_KEY_CREATED
        assert event.category == EventCategory.API_KEY
        assert event.resource_type == "api_key"
        assert event.resource_id == "key-789"
        assert event.metadata["scopes"] == ["read", "write"]

    @pytest.mark.asyncio
    async def test_log_webhook_received(self):
        """Test logging webhook received."""
        store = AuditStore()
        logger = AuditLogger(store=store)

        event = await logger.log_webhook_received(
            tenant_id="tenant-123",
            webhook_type="incident.triggered",
            source="pagerduty",
            event_id="pd-event-123",
        )

        assert event.event_type == EventType.WEBHOOK_RECEIVED
        assert event.category == EventCategory.WEBHOOK
        assert event.metadata["source"] == "pagerduty"
        assert event.metadata["webhook_type"] == "incident.triggered"

    @pytest.mark.asyncio
    async def test_log_settings_updated(self):
        """Test logging settings update."""
        store = AuditStore()
        logger = AuditLogger(store=store)

        event = await logger.log_settings_updated(
            tenant_id="tenant-123",
            user_id="user-456",
            setting_name="notification_channel",
            old_value="#incidents",
            new_value="#alerts",
        )

        assert event.event_type == EventType.SETTINGS_UPDATED
        assert event.category == EventCategory.CONFIGURATION
        assert event.metadata["old_value"] == "#incidents"
        assert event.metadata["new_value"] == "#alerts"

    @pytest.mark.asyncio
    async def test_log_user_created(self):
        """Test logging user creation."""
        store = AuditStore()
        logger = AuditLogger(store=store)

        event = await logger.log_user_created(
            tenant_id="tenant-123",
            created_by_user_id="admin-456",
            new_user_id="new-789",
            new_user_email="newuser@example.com",
            role="member",
        )

        assert event.event_type == EventType.USER_CREATED
        assert event.category == EventCategory.USER_MANAGEMENT
        assert event.user_id == "admin-456"  # Created by
        assert event.resource_id == "new-789"  # New user
        assert event.metadata["role"] == "member"


class TestAuditLogQuery:
    """Tests for AuditLogQuery model."""

    def test_basic_query(self):
        """Test creating a basic query."""
        query = AuditLogQuery(
            tenant_id="tenant-123",
            limit=50,
            offset=10,
        )

        assert query.tenant_id == "tenant-123"
        assert query.limit == 50
        assert query.offset == 10

    def test_query_with_filters(self):
        """Test query with all filters."""
        now = datetime.utcnow()
        query = AuditLogQuery(
            tenant_id="tenant-123",
            start_date=now - timedelta(days=7),
            end_date=now,
            event_types=[EventType.LOGIN_SUCCESS, EventType.LOGIN_FAILURE],
            categories=[EventCategory.AUTHENTICATION],
            user_id="user-456",
            resource_type="session",
            outcome=Outcome.SUCCESS,
            limit=100,
        )

        assert len(query.event_types) == 2
        assert len(query.categories) == 1
        assert query.user_id == "user-456"


class TestAuditAPI:
    """Tests for audit API endpoints (basic tests without auth)."""

    def test_health_endpoint_not_affected(self, client):
        """Ensure health endpoint still works with audit middleware."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_audit_logs_requires_auth(self, client):
        """Test that audit logs endpoint requires authentication."""
        response = client.get("/api/v1/audit/logs")
        assert response.status_code == 401

    def test_audit_export_requires_auth(self, client):
        """Test that audit export endpoint requires authentication."""
        response = client.get("/api/v1/audit/logs/export")
        assert response.status_code == 401

    def test_audit_stats_requires_auth(self, client):
        """Test that audit stats endpoint requires authentication."""
        response = client.get("/api/v1/audit/stats")
        assert response.status_code == 401


class TestCleanup:
    """Tests for audit log retention and cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_old_events(self):
        """Test cleaning up events older than retention period."""
        store = AuditStore(retention_days=7)
        now = datetime.utcnow()

        # Create old and new events
        old_event = AuditEvent(
            event_type=EventType.LOGIN_SUCCESS,
            category=EventCategory.AUTHENTICATION,
            action="Old login",
            tenant_id="tenant-123",
            timestamp=now - timedelta(days=30),
        )
        new_event = AuditEvent(
            event_type=EventType.LOGIN_SUCCESS,
            category=EventCategory.AUTHENTICATION,
            action="Recent login",
            tenant_id="tenant-123",
            timestamp=now - timedelta(days=1),
        )

        await store.store_event(old_event)
        await store.store_event(new_event)

        # Run cleanup
        deleted = await store.cleanup_old_events()

        assert deleted == 1

        # Verify only new event remains
        query = AuditLogQuery(tenant_id="tenant-123", limit=10)
        events = await store.query_events(query)
        assert len(events) == 1
        assert events[0].action == "Recent login"
