"""Comprehensive tests for maintenance windows module."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.maintenance.checker import MaintenanceChecker, MaintenanceCheckResult
from src.maintenance.models import (
    CalendarEvent,
    EmergencyOverride,
    MaintenanceAuditEntry,
    MaintenanceNotification,
    MaintenanceQuery,
    MaintenanceStatus,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
    RecurrencePattern,
    RecurringSchedule,
    SuppressionAction,
)
from src.maintenance.routes import router
from src.maintenance.store import MaintenanceStore
from src.maintenance.suppression import AlertSuppressor, SuppressionResult


# --- Fixtures ---


@pytest.fixture
async def store():
    """Create a fresh maintenance store for testing."""
    store = MaintenanceStore()
    yield store
    await store.clear()


@pytest.fixture
def checker(store):
    """Create a maintenance checker with test store."""
    return MaintenanceChecker(store=store)


@pytest.fixture
def suppressor(store, checker):
    """Create an alert suppressor with test store and checker."""
    return AlertSuppressor(store=store, checker=checker)


@pytest.fixture
def client(store, checker, suppressor):
    """Create test client with routes."""
    app = FastAPI()
    app.include_router(router)
    
    # Override dependencies
    from src.maintenance import routes
    routes.maintenance_store = store
    routes.maintenance_checker = checker
    routes.alert_suppressor = suppressor
    
    return TestClient(app)


@pytest.fixture
def sample_window_create():
    """Sample maintenance window creation request."""
    now = datetime.utcnow()
    return MaintenanceWindowCreate(
        title="Database Maintenance",
        description="Routine database optimization",
        services=["payments-api", "orders-api"],
        environments=["prod"],
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=3),
        suppression_action=SuppressionAction.SUPPRESS,
        tags=["database", "routine"],
    )


# --- Model Tests ---


class TestMaintenanceModels:
    """Tests for maintenance data models."""

    def test_maintenance_window_creation(self):
        """Test creating a maintenance window."""
        now = datetime.utcnow()
        window = MaintenanceWindow(
            title="Test Maintenance",
            start_time=now,
            end_time=now + timedelta(hours=2),
        )
        
        assert window.id.startswith("mw_")
        assert window.title == "Test Maintenance"
        assert window.status == MaintenanceStatus.SCHEDULED
        assert window.suppression_action == SuppressionAction.SUPPRESS
        assert window.is_global is False

    def test_maintenance_window_is_active(self):
        """Test is_active property."""
        now = datetime.utcnow()
        
        # Future window
        future_window = MaintenanceWindow(
            title="Future",
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        assert future_window.is_active is False
        
        # Active window
        active_window = MaintenanceWindow(
            title="Active",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
        assert active_window.is_active is True
        
        # Past window
        past_window = MaintenanceWindow(
            title="Past",
            start_time=now - timedelta(hours=3),
            end_time=now - timedelta(hours=1),
            status=MaintenanceStatus.COMPLETED,
        )
        assert past_window.is_active is False

    def test_maintenance_window_affects_service(self):
        """Test affects_service method."""
        window = MaintenanceWindow(
            title="Test",
            services=["payments-api", "orders-api"],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
        )
        
        assert window.affects_service("payments-api") is True
        assert window.affects_service("PAYMENTS-API") is True  # Case insensitive
        assert window.affects_service("other-service") is False
        
        # Global window affects all
        global_window = MaintenanceWindow(
            title="Global",
            is_global=True,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(hours=1),
        )
        assert global_window.affects_service("any-service") is True

    def test_recurring_schedule(self):
        """Test recurring schedule configuration."""
        schedule = RecurringSchedule(
            pattern=RecurrencePattern.WEEKLY,
            days_of_week=[0, 2, 4],  # Mon, Wed, Fri
            start_time="02:00",
            duration_minutes=60,
            timezone="America/New_York",
        )
        
        assert schedule.pattern == RecurrencePattern.WEEKLY
        assert schedule.days_of_week == [0, 2, 4]
        assert schedule.duration_minutes == 60

    def test_recurring_schedule_validation(self):
        """Test recurring schedule validation."""
        # Invalid day of week
        with pytest.raises(ValueError):
            RecurringSchedule(
                pattern=RecurrencePattern.WEEKLY,
                days_of_week=[7],  # Invalid: should be 0-6
            )
        
        # Invalid day of month
        with pytest.raises(ValueError):
            RecurringSchedule(
                pattern=RecurrencePattern.MONTHLY,
                day_of_month=32,  # Invalid: should be 1-31 or -1
            )

    def test_emergency_override(self):
        """Test emergency override creation."""
        override = EmergencyOverride(
            maintenance_window_id="mw_test123",
            reason="Critical production issue",
            created_by="oncall@example.com",
            services=["payments-api"],
            auto_revoke_minutes=30,
        )
        
        assert override.id.startswith("eo_")
        assert override.is_active is True
        assert override.revoked_at is None


# --- Store Tests ---


class TestMaintenanceStore:
    """Tests for maintenance window storage."""

    @pytest.mark.asyncio
    async def test_create_window(self, store, sample_window_create):
        """Test creating a maintenance window."""
        window = await store.create(
            sample_window_create,
            created_by="test@example.com",
            tenant_id="tenant-123",
        )
        
        assert window.id is not None
        assert window.title == "Database Maintenance"
        assert window.created_by == "test@example.com"
        assert window.tenant_id == "tenant-123"

    @pytest.mark.asyncio
    async def test_get_window(self, store, sample_window_create):
        """Test retrieving a maintenance window."""
        created = await store.create(sample_window_create)
        
        retrieved = await store.get(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.title == created.title

    @pytest.mark.asyncio
    async def test_update_window(self, store, sample_window_create):
        """Test updating a maintenance window."""
        window = await store.create(sample_window_create)
        
        updates = MaintenanceWindowUpdate(
            title="Updated Maintenance",
            suppression_action=SuppressionAction.ANNOTATE,
        )
        
        updated = await store.update(window.id, updates)
        assert updated is not None
        assert updated.title == "Updated Maintenance"
        assert updated.suppression_action == SuppressionAction.ANNOTATE

    @pytest.mark.asyncio
    async def test_delete_window(self, store, sample_window_create):
        """Test deleting a maintenance window."""
        window = await store.create(sample_window_create)
        
        deleted = await store.delete(window.id)
        assert deleted is True
        
        retrieved = await store.get(window.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cancel_window(self, store, sample_window_create):
        """Test cancelling a maintenance window."""
        window = await store.create(sample_window_create)
        
        cancelled = await store.cancel(
            window.id,
            cancelled_by="admin@example.com",
            reason="No longer needed",
        )
        
        assert cancelled is not None
        assert cancelled.status == MaintenanceStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_list_windows(self, store):
        """Test listing maintenance windows."""
        now = datetime.utcnow()
        
        # Create multiple windows
        for i in range(5):
            await store.create(
                MaintenanceWindowCreate(
                    title=f"Maintenance {i}",
                    services=["service-{i}"],
                    start_time=now + timedelta(hours=i),
                    end_time=now + timedelta(hours=i + 1),
                )
            )
        
        windows = await store.list()
        assert len(windows) == 5

    @pytest.mark.asyncio
    async def test_list_windows_with_filters(self, store):
        """Test listing windows with filters."""
        now = datetime.utcnow()
        
        # Create windows with different services
        await store.create(
            MaintenanceWindowCreate(
                title="Payments Maintenance",
                services=["payments-api"],
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=2),
            ),
            tenant_id="tenant-1",
        )
        
        await store.create(
            MaintenanceWindowCreate(
                title="Orders Maintenance",
                services=["orders-api"],
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=2),
            ),
            tenant_id="tenant-2",
        )
        
        # Filter by service
        query = MaintenanceQuery(service="payments-api")
        windows = await store.list(query)
        assert len(windows) == 1
        assert windows[0].title == "Payments Maintenance"
        
        # Filter by tenant
        query = MaintenanceQuery(tenant_id="tenant-1")
        windows = await store.list(query)
        assert len(windows) == 1

    @pytest.mark.asyncio
    async def test_get_active_windows(self, store):
        """Test getting active maintenance windows."""
        now = datetime.utcnow()
        
        # Create an active window
        active_create = MaintenanceWindowCreate(
            title="Active Maintenance",
            services=["payments-api"],
            start_time=now - timedelta(minutes=30),
            end_time=now + timedelta(hours=1),
        )
        active = await store.create(active_create)
        
        # Create a future window
        await store.create(
            MaintenanceWindowCreate(
                title="Future Maintenance",
                services=["payments-api"],
                start_time=now + timedelta(hours=2),
                end_time=now + timedelta(hours=3),
            )
        )
        
        active_windows = await store.get_active_windows(service="payments-api")
        assert len(active_windows) == 1
        assert active_windows[0].id == active.id

    @pytest.mark.asyncio
    async def test_emergency_override_crud(self, store, sample_window_create):
        """Test emergency override CRUD operations."""
        window = await store.create(sample_window_create)
        
        # Create override
        override = EmergencyOverride(
            maintenance_window_id=window.id,
            reason="Critical issue",
            created_by="oncall@example.com",
        )
        created = await store.create_override(override)
        assert created.is_active is True
        
        # Get overrides
        overrides = await store.get_active_overrides(window.id)
        assert len(overrides) == 1
        
        # Check override active
        is_active = await store.check_override_active(window.id)
        assert is_active is True
        
        # Revoke override
        revoked = await store.revoke_override(created.id, revoked_by="admin@example.com")
        assert revoked is not None
        assert revoked.is_active is False
        assert revoked.revoked_by == "admin@example.com"

    @pytest.mark.asyncio
    async def test_audit_log(self, store, sample_window_create):
        """Test audit log functionality."""
        window = await store.create(sample_window_create, created_by="test@example.com")
        
        # Get audit log
        entries = await store.get_audit_log(window_id=window.id)
        assert len(entries) >= 1
        
        # Check that creation was logged
        create_entry = next(
            (e for e in entries if e.action == "created"), None
        )
        assert create_entry is not None
        assert create_entry.maintenance_window_id == window.id


# --- Checker Tests ---


class TestMaintenanceChecker:
    """Tests for maintenance window checker."""

    @pytest.mark.asyncio
    async def test_check_service_no_maintenance(self, store, checker):
        """Test checking service with no maintenance."""
        result = await checker.check_service("payments-api")
        
        assert result.in_maintenance is False
        assert len(result.windows) == 0
        assert result.should_suppress is False

    @pytest.mark.asyncio
    async def test_check_service_in_maintenance(self, store, checker):
        """Test checking service during maintenance."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Active Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        result = await checker.check_service("payments-api")
        
        assert result.in_maintenance is True
        assert len(result.windows) == 1
        assert result.should_suppress is True

    @pytest.mark.asyncio
    async def test_check_service_with_override(self, store, checker):
        """Test checking service with emergency override."""
        now = datetime.utcnow()
        
        window = await store.create(
            MaintenanceWindowCreate(
                title="Active Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        # Create override
        override = EmergencyOverride(
            maintenance_window_id=window.id,
            reason="Critical issue",
            created_by="oncall@example.com",
        )
        await store.create_override(override)
        
        result = await checker.check_service("payments-api")
        
        assert result.in_maintenance is True
        assert result.has_override is True
        assert result.should_suppress is False

    @pytest.mark.asyncio
    async def test_check_alert_with_type(self, store, checker):
        """Test checking alert with specific type filter."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="DB Maintenance",
                services=["payments-api"],
                alert_types=["database_error", "connection_timeout"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        # Alert type that matches
        result = await checker.check_alert(
            alert_id="alert-1",
            service="payments-api",
            alert_type="database_error",
        )
        assert result.in_maintenance is True
        
        # Alert type that doesn't match
        result = await checker.check_alert(
            alert_id="alert-2",
            service="payments-api",
            alert_type="cpu_spike",
        )
        assert result.in_maintenance is False

    @pytest.mark.asyncio
    async def test_check_global_maintenance(self, store, checker):
        """Test checking global maintenance."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Global Maintenance",
                is_global=True,
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
            )
        )
        
        result = await checker.check_global_maintenance()
        assert result.in_maintenance is True

    @pytest.mark.asyncio
    async def test_check_recurring_maintenance(self, store, checker):
        """Test checking recurring maintenance window."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Weekly Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                recurring=RecurringSchedule(
                    pattern=RecurrencePattern.DAILY,
                    start_time=now.strftime("%H:%M"),
                    duration_minutes=120,
                ),
            )
        )
        
        result = await checker.check_service("payments-api")
        assert result.in_maintenance is True

    @pytest.mark.asyncio
    async def test_get_maintenance_info(self, store, checker):
        """Test getting detailed maintenance info."""
        now = datetime.utcnow()
        
        # Create active maintenance
        await store.create(
            MaintenanceWindowCreate(
                title="Active",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
            )
        )
        
        # Create upcoming maintenance
        await store.create(
            MaintenanceWindowCreate(
                title="Upcoming",
                services=["payments-api"],
                start_time=now + timedelta(hours=2),
                end_time=now + timedelta(hours=3),
            )
        )
        
        info = await checker.get_maintenance_info("payments-api")
        
        assert info["service"] == "payments-api"
        assert info["is_in_maintenance"] is True
        assert len(info["current_windows"]) == 1
        assert len(info["upcoming_windows"]) == 1


# --- Suppression Tests ---


class TestAlertSuppressor:
    """Tests for alert suppression."""

    @pytest.mark.asyncio
    async def test_process_alert_no_maintenance(self, suppressor):
        """Test processing alert with no maintenance."""
        result = await suppressor.process_alert(
            alert_id="alert-123",
            service="payments-api",
        )
        
        assert result.suppressed is False
        assert result.delivered is True
        assert result.action_taken == SuppressionAction.NONE

    @pytest.mark.asyncio
    async def test_process_alert_suppressed(self, store, suppressor):
        """Test processing alert during suppressive maintenance."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        result = await suppressor.process_alert(
            alert_id="alert-123",
            service="payments-api",
        )
        
        assert result.suppressed is True
        assert result.delivered is False
        assert result.action_taken == SuppressionAction.SUPPRESS
        assert len(result.maintenance_windows) == 1

    @pytest.mark.asyncio
    async def test_process_alert_annotated(self, store, suppressor):
        """Test processing alert with annotation."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.ANNOTATE,
            )
        )
        
        result = await suppressor.process_alert(
            alert_id="alert-123",
            service="payments-api",
        )
        
        assert result.annotated is True
        assert result.delivered is True
        assert result.action_taken == SuppressionAction.ANNOTATE
        assert "maintenance" in result.annotations
        assert result.annotations["maintenance"] is True

    @pytest.mark.asyncio
    async def test_process_alert_log_only(self, store, suppressor):
        """Test processing alert with log-only mode."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.LOG_ONLY,
            )
        )
        
        result = await suppressor.process_alert(
            alert_id="alert-123",
            service="payments-api",
        )
        
        assert result.logged is True
        assert result.delivered is False
        assert result.action_taken == SuppressionAction.LOG_ONLY

    @pytest.mark.asyncio
    async def test_process_alert_with_override(self, store, suppressor):
        """Test processing alert with emergency override."""
        now = datetime.utcnow()
        
        window = await store.create(
            MaintenanceWindowCreate(
                title="Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        # Create override
        override = EmergencyOverride(
            maintenance_window_id=window.id,
            reason="Critical issue",
            created_by="oncall@example.com",
        )
        await store.create_override(override)
        
        result = await suppressor.process_alert(
            alert_id="alert-123",
            service="payments-api",
        )
        
        # Alert should be delivered despite maintenance
        assert result.suppressed is False
        assert result.delivered is True
        assert "Emergency override" in result.reason

    @pytest.mark.asyncio
    async def test_should_deliver_alert(self, store, suppressor):
        """Test quick should_deliver check."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        should_deliver, context = await suppressor.should_deliver_alert("payments-api")
        assert should_deliver is False
        assert context["in_maintenance"] is True
        
        # Different service not in maintenance
        should_deliver, context = await suppressor.should_deliver_alert("orders-api")
        assert should_deliver is True

    @pytest.mark.asyncio
    async def test_suppression_stats(self, store, suppressor):
        """Test suppression statistics."""
        now = datetime.utcnow()
        
        window = await store.create(
            MaintenanceWindowCreate(
                title="Maintenance",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        # Process multiple alerts
        for i in range(5):
            await suppressor.process_alert(
                alert_id=f"alert-{i}",
                service="payments-api",
            )
        
        stats = await suppressor.get_suppression_stats(window_id=window.id)
        assert stats["suppressed"] == 5


# --- API Tests ---


class TestMaintenanceAPI:
    """Tests for maintenance API routes."""

    def test_create_maintenance_window(self, client):
        """Test creating maintenance window via API."""
        now = datetime.utcnow()
        
        response = client.post(
            "/api/maintenance",
            json={
                "title": "API Test Maintenance",
                "services": ["payments-api"],
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
            params={"created_by": "test@example.com"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "API Test Maintenance"
        assert data["id"].startswith("mw_")

    def test_get_maintenance_window(self, client):
        """Test getting maintenance window via API."""
        now = datetime.utcnow()
        
        # Create first
        create_response = client.post(
            "/api/maintenance",
            json={
                "title": "Test",
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
        )
        window_id = create_response.json()["id"]
        
        # Get
        response = client.get(f"/api/maintenance/{window_id}")
        assert response.status_code == 200
        assert response.json()["id"] == window_id

    def test_get_nonexistent_window(self, client):
        """Test getting non-existent window."""
        response = client.get("/api/maintenance/mw_nonexistent")
        assert response.status_code == 404

    def test_update_maintenance_window(self, client):
        """Test updating maintenance window via API."""
        now = datetime.utcnow()
        
        create_response = client.post(
            "/api/maintenance",
            json={
                "title": "Original",
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
        )
        window_id = create_response.json()["id"]
        
        # Update
        response = client.put(
            f"/api/maintenance/{window_id}",
            json={"title": "Updated Title"},
        )
        
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Title"

    def test_delete_maintenance_window(self, client):
        """Test deleting maintenance window via API."""
        now = datetime.utcnow()
        
        create_response = client.post(
            "/api/maintenance",
            json={
                "title": "To Delete",
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
        )
        window_id = create_response.json()["id"]
        
        # Delete
        response = client.delete(f"/api/maintenance/{window_id}")
        assert response.status_code == 200
        
        # Verify deleted
        response = client.get(f"/api/maintenance/{window_id}")
        assert response.status_code == 404

    def test_cancel_maintenance_window(self, client):
        """Test cancelling maintenance window via API."""
        now = datetime.utcnow()
        
        create_response = client.post(
            "/api/maintenance",
            json={
                "title": "To Cancel",
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
        )
        window_id = create_response.json()["id"]
        
        response = client.post(
            f"/api/maintenance/{window_id}/cancel",
            params={"reason": "No longer needed"},
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_list_maintenance_windows(self, client):
        """Test listing maintenance windows via API."""
        now = datetime.utcnow()
        
        # Create multiple
        for i in range(3):
            client.post(
                "/api/maintenance",
                json={
                    "title": f"Window {i}",
                    "start_time": (now + timedelta(hours=i)).isoformat(),
                    "end_time": (now + timedelta(hours=i + 1)).isoformat(),
                },
            )
        
        response = client.get("/api/maintenance")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3

    def test_check_service_maintenance(self, client):
        """Test checking service maintenance via API."""
        now = datetime.utcnow()
        
        client.post(
            "/api/maintenance",
            json={
                "title": "Active",
                "services": ["payments-api"],
                "start_time": (now - timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            },
        )
        
        response = client.get("/api/maintenance/check/service/payments-api")
        assert response.status_code == 200
        data = response.json()
        assert data["in_maintenance"] is True

    def test_check_alert_suppression(self, client):
        """Test alert suppression check via API."""
        now = datetime.utcnow()
        
        client.post(
            "/api/maintenance",
            json={
                "title": "Active",
                "services": ["payments-api"],
                "start_time": (now - timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
                "suppression_action": "suppress",
            },
        )
        
        response = client.post(
            "/api/maintenance/alert/check",
            json={
                "alert_id": "alert-123",
                "service": "payments-api",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["suppressed"] is True
        assert data["delivered"] is False

    def test_create_emergency_override(self, client):
        """Test creating emergency override via API."""
        now = datetime.utcnow()
        
        create_response = client.post(
            "/api/maintenance",
            json={
                "title": "Active",
                "services": ["payments-api"],
                "start_time": (now - timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            },
        )
        window_id = create_response.json()["id"]
        
        response = client.post(
            f"/api/maintenance/{window_id}/override",
            json={
                "reason": "Critical issue",
                "auto_revoke_minutes": 30,
            },
            params={"created_by": "oncall@example.com"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["is_active"] is True
        assert data["reason"] == "Critical issue"

    def test_get_calendar_events(self, client):
        """Test getting calendar events via API."""
        now = datetime.utcnow()
        
        client.post(
            "/api/maintenance",
            json={
                "title": "Calendar Test",
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
        )
        
        response = client.get("/api/maintenance/calendar")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) >= 1

    def test_get_suppression_stats(self, client):
        """Test getting suppression stats via API."""
        response = client.get("/api/maintenance/stats/suppression")
        assert response.status_code == 200
        data = response.json()
        assert "total_alerts" in data
        assert "suppressed" in data

    def test_get_upcoming_maintenance(self, client):
        """Test getting upcoming maintenance via API."""
        now = datetime.utcnow()
        
        client.post(
            "/api/maintenance",
            json={
                "title": "Upcoming",
                "start_time": (now + timedelta(hours=2)).isoformat(),
                "end_time": (now + timedelta(hours=3)).isoformat(),
            },
        )
        
        response = client.get("/api/maintenance/upcoming")
        assert response.status_code == 200
        data = response.json()
        assert len(data["windows"]) >= 1

    def test_get_active_maintenance(self, client):
        """Test getting active maintenance via API."""
        now = datetime.utcnow()
        
        client.post(
            "/api/maintenance",
            json={
                "title": "Active",
                "start_time": (now - timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            },
        )
        
        response = client.get("/api/maintenance/active")
        assert response.status_code == 200
        data = response.json()
        assert len(data["windows"]) >= 1


# --- Integration Tests ---


class TestMaintenanceIntegration:
    """Integration tests for maintenance workflow."""

    @pytest.mark.asyncio
    async def test_full_maintenance_workflow(self, store, checker, suppressor):
        """Test complete maintenance workflow."""
        now = datetime.utcnow()
        
        # 1. Create maintenance window
        window = await store.create(
            MaintenanceWindowCreate(
                title="Planned DB Upgrade",
                description="Database version upgrade",
                services=["payments-api", "orders-api"],
                environments=["prod"],
                start_time=now - timedelta(minutes=10),
                end_time=now + timedelta(hours=2),
                suppression_action=SuppressionAction.SUPPRESS,
                notifications=MaintenanceNotification(
                    notify_before_minutes=[60, 15],
                    slack_channels=["#ops"],
                ),
            ),
            created_by="platform@example.com",
        )
        
        # 2. Verify it's detected as active
        check_result = await checker.check_service("payments-api")
        assert check_result.in_maintenance is True
        
        # 3. Process an alert - should be suppressed
        result = await suppressor.process_alert(
            alert_id="db-alert-1",
            service="payments-api",
            alert_type="connection_error",
        )
        assert result.suppressed is True
        
        # 4. Critical issue occurs - create override
        override = EmergencyOverride(
            maintenance_window_id=window.id,
            reason="Data corruption detected",
            created_by="dba@example.com",
        )
        await store.create_override(override)
        
        # 5. New alert should now be delivered
        result = await suppressor.process_alert(
            alert_id="db-alert-2",
            service="payments-api",
            alert_type="data_corruption",
        )
        assert result.delivered is True
        assert "Emergency override" in result.reason
        
        # 6. Revoke override after issue handled
        await store.revoke_override(override.id, revoked_by="dba@example.com")
        
        # 7. Alerts should be suppressed again
        result = await suppressor.process_alert(
            alert_id="db-alert-3",
            service="payments-api",
        )
        assert result.suppressed is True
        
        # 8. Check audit trail
        audit_entries = await store.get_audit_log(window_id=window.id)
        actions = [e.action for e in audit_entries]
        assert "created" in actions
        assert "emergency_override_created" in actions
        assert "emergency_override_revoked" in actions

    @pytest.mark.asyncio
    async def test_multiple_overlapping_windows(self, store, checker):
        """Test behavior with multiple overlapping maintenance windows."""
        now = datetime.utcnow()
        
        # Create two overlapping windows with different actions
        await store.create(
            MaintenanceWindowCreate(
                title="Window 1",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.ANNOTATE,
            )
        )
        
        await store.create(
            MaintenanceWindowCreate(
                title="Window 2",
                services=["payments-api"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                suppression_action=SuppressionAction.SUPPRESS,
            )
        )
        
        # The most restrictive action (SUPPRESS) should win
        result = await checker.check_service("payments-api")
        assert result.in_maintenance is True
        assert result.suppression_action == SuppressionAction.SUPPRESS
        assert len(result.windows) == 2

    @pytest.mark.asyncio
    async def test_environment_scoped_maintenance(self, store, checker):
        """Test maintenance scoped to specific environments."""
        now = datetime.utcnow()
        
        await store.create(
            MaintenanceWindowCreate(
                title="Staging Maintenance",
                services=["payments-api"],
                environments=["staging"],
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
            )
        )
        
        # Should be in maintenance for staging
        result = await checker.check_service(
            "payments-api",
            environment="staging",
        )
        assert result.in_maintenance is True
        
        # Should not be in maintenance for prod
        result = await checker.check_service(
            "payments-api",
            environment="prod",
        )
        assert result.in_maintenance is False
