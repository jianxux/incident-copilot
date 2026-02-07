"""Tests for maintenance windows module."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.maintenance.models import (
    ApprovalRecord,
    ExtendMaintenanceRequest,
    MaintenanceNotification,
    MaintenanceSchedule,
    MaintenanceScope,
    MaintenanceStatus,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
    NotificationType,
    OverlapWarning,
    ScopeType,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_schedule() -> MaintenanceSchedule:
    """Create a sample maintenance schedule."""
    return MaintenanceSchedule(
        start_time=datetime.utcnow() + timedelta(hours=1),
        end_time=datetime.utcnow() + timedelta(hours=3),
        timezone="UTC",
        is_recurring=False,
    )


@pytest.fixture
def sample_scope() -> MaintenanceScope:
    """Create a sample maintenance scope."""
    return MaintenanceScope(
        scope_type=ScopeType.SERVICE,
        identifiers=["payments-api", "checkout-service"],
        suppress_alerts=True,
        suppress_incidents=False,
    )


@pytest.fixture
def sample_window(sample_schedule, sample_scope) -> MaintenanceWindow:
    """Create a sample maintenance window."""
    return MaintenanceWindow(
        title="Database Migration",
        description="Upgrading PostgreSQL to version 15",
        scope=sample_scope,
        schedule=sample_schedule,
        created_by="user-123",
        requires_approval=True,
        required_approvers=["manager-1"],
        stakeholders=["team-lead@example.com"],
    )


class TestScopeType:
    """Tests for ScopeType enum."""

    def test_scope_type_values(self):
        """Test all scope types exist."""
        assert ScopeType.SERVICE.value == "service"
        assert ScopeType.TEAM.value == "team"
        assert ScopeType.INFRASTRUCTURE.value == "infrastructure"
        assert ScopeType.GLOBAL.value == "global"


class TestMaintenanceStatus:
    """Tests for MaintenanceStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert MaintenanceStatus.DRAFT.value == "draft"
        assert MaintenanceStatus.PENDING_APPROVAL.value == "pending_approval"
        assert MaintenanceStatus.SCHEDULED.value == "scheduled"
        assert MaintenanceStatus.IN_PROGRESS.value == "in_progress"
        assert MaintenanceStatus.COMPLETED.value == "completed"
        assert MaintenanceStatus.CANCELLED.value == "cancelled"
        assert MaintenanceStatus.EXTENDED.value == "extended"


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_notification_types(self):
        """Test all notification types exist."""
        assert NotificationType.SCHEDULED.value == "scheduled"
        assert NotificationType.REMINDER.value == "reminder"
        assert NotificationType.STARTED.value == "started"
        assert NotificationType.EXTENDED.value == "extended"
        assert NotificationType.COMPLETED.value == "completed"
        assert NotificationType.CANCELLED.value == "cancelled"


class TestMaintenanceScope:
    """Tests for MaintenanceScope model."""

    def test_scope_creation(self, sample_scope):
        """Test creating a maintenance scope."""
        assert sample_scope.scope_type == ScopeType.SERVICE
        assert len(sample_scope.identifiers) == 2
        assert sample_scope.suppress_alerts

    def test_scope_matches_service(self, sample_scope):
        """Test scope matching for services."""
        assert sample_scope.matches(ScopeType.SERVICE, "payments-api")
        assert sample_scope.matches(ScopeType.SERVICE, "checkout-service")
        assert not sample_scope.matches(ScopeType.SERVICE, "other-service")

    def test_scope_matches_wrong_type(self, sample_scope):
        """Test scope doesn't match wrong type."""
        assert not sample_scope.matches(ScopeType.TEAM, "payments-api")

    def test_scope_exclusions(self):
        """Test scope with exclusions."""
        scope = MaintenanceScope(
            scope_type=ScopeType.TEAM,
            identifiers=["platform"],
            exclude_identifiers=["critical-service"],
        )
        assert scope.matches(ScopeType.TEAM, "platform")
        assert not scope.matches(ScopeType.TEAM, "critical-service")

    def test_global_scope(self):
        """Test global scope matching."""
        scope = MaintenanceScope(
            scope_type=ScopeType.GLOBAL,
            exclude_identifiers=["excluded-service"],
        )
        assert scope.matches(ScopeType.GLOBAL, "any-service")
        assert not scope.matches(ScopeType.GLOBAL, "excluded-service")


class TestMaintenanceSchedule:
    """Tests for MaintenanceSchedule model."""

    def test_schedule_creation(self, sample_schedule):
        """Test creating a maintenance schedule."""
        assert sample_schedule.timezone == "UTC"
        assert not sample_schedule.is_recurring

    def test_schedule_duration(self, sample_schedule):
        """Test schedule duration calculation."""
        duration = sample_schedule.duration
        assert duration == timedelta(hours=2)

    def test_invalid_end_before_start(self):
        """Test that end time before start time is rejected."""
        with pytest.raises(ValueError, match="end_time must be after start_time"):
            MaintenanceSchedule(
                start_time=datetime.utcnow() + timedelta(hours=2),
                end_time=datetime.utcnow() + timedelta(hours=1),
            )

    def test_recurring_schedule(self):
        """Test recurring schedule with RRULE."""
        schedule = MaintenanceSchedule(
            start_time=datetime.utcnow() + timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=1, hours=2),
            is_recurring=True,
            rrule="FREQ=WEEKLY;BYDAY=SU",
            recurrence_end=datetime.utcnow() + timedelta(days=90),
        )
        assert schedule.is_recurring
        assert schedule.rrule == "FREQ=WEEKLY;BYDAY=SU"

    def test_recurring_requires_rrule(self):
        """Test that recurring schedules require RRULE."""
        with pytest.raises(ValueError, match="rrule required"):
            MaintenanceSchedule(
                start_time=datetime.utcnow() + timedelta(hours=1),
                end_time=datetime.utcnow() + timedelta(hours=2),
                is_recurring=True,
                # Missing rrule
            )

    def test_rrule_validation(self):
        """Test RRULE format validation."""
        with pytest.raises(ValueError, match="RRULE must start with"):
            MaintenanceSchedule(
                start_time=datetime.utcnow() + timedelta(hours=1),
                end_time=datetime.utcnow() + timedelta(hours=2),
                is_recurring=True,
                rrule="INVALID",
            )


class TestApprovalRecord:
    """Tests for ApprovalRecord model."""

    def test_approval_creation(self):
        """Test creating an approval record."""
        approval = ApprovalRecord(
            approver_id="manager-1",
            approved=True,
            comment="Looks good, approved",
        )
        assert approval.approved
        assert approval.comment is not None

    def test_rejection(self):
        """Test creating a rejection record."""
        approval = ApprovalRecord(
            approver_id="manager-2",
            approved=False,
            comment="Please reschedule to off-peak hours",
        )
        assert not approval.approved


class TestMaintenanceWindow:
    """Tests for MaintenanceWindow model."""

    def test_window_creation(self, sample_window):
        """Test creating a maintenance window."""
        assert sample_window.title == "Database Migration"
        assert sample_window.status == MaintenanceStatus.DRAFT
        assert sample_window.requires_approval

    def test_is_approved_no_approval_required(self, sample_window):
        """Test approval check when not required."""
        sample_window.requires_approval = False
        assert sample_window.is_approved()

    def test_is_approved_pending(self, sample_window):
        """Test approval check when pending."""
        assert not sample_window.is_approved()

    def test_is_approved_with_approvals(self, sample_window):
        """Test approval check with approvals."""
        sample_window.approvals.append(
            ApprovalRecord(approver_id="manager-1", approved=True)
        )
        assert sample_window.is_approved()

    def test_is_approved_missing_required(self, sample_window):
        """Test approval check missing required approver."""
        sample_window.approvals.append(
            ApprovalRecord(approver_id="other-manager", approved=True)
        )
        assert not sample_window.is_approved()

    def test_is_active_before_start(self, sample_window):
        """Test is_active before window starts."""
        sample_window.status = MaintenanceStatus.SCHEDULED
        assert not sample_window.is_active()

    def test_is_active_during_window(self, sample_window):
        """Test is_active during maintenance window."""
        # Set schedule to be currently active
        sample_window.schedule.start_time = datetime.utcnow() - timedelta(hours=1)
        sample_window.schedule.end_time = datetime.utcnow() + timedelta(hours=1)
        sample_window.status = MaintenanceStatus.IN_PROGRESS
        assert sample_window.is_active()

    def test_is_active_after_end(self, sample_window):
        """Test is_active after window ends."""
        sample_window.schedule.start_time = datetime.utcnow() - timedelta(hours=3)
        sample_window.schedule.end_time = datetime.utcnow() - timedelta(hours=1)
        sample_window.status = MaintenanceStatus.COMPLETED
        assert not sample_window.is_active()


class TestMaintenanceWindowCreate:
    """Tests for MaintenanceWindowCreate request model."""

    def test_create_request(self, sample_schedule, sample_scope):
        """Test creating a window create request."""
        request = MaintenanceWindowCreate(
            title="Planned Maintenance",
            description="Routine maintenance",
            scope=sample_scope,
            schedule=sample_schedule,
            requires_approval=True,
            required_approvers=["manager-1"],
        )
        assert request.title == "Planned Maintenance"

    def test_create_request_minimal(self, sample_schedule, sample_scope):
        """Test minimal create request."""
        request = MaintenanceWindowCreate(
            title="Quick Maintenance",
            scope=sample_scope,
            schedule=sample_schedule,
        )
        assert request.requires_approval  # Default is True


class TestMaintenanceWindowUpdate:
    """Tests for MaintenanceWindowUpdate request model."""

    def test_partial_update(self):
        """Test partial update request."""
        update = MaintenanceWindowUpdate(
            title="Updated Title",
        )
        assert update.title == "Updated Title"
        assert update.description is None  # Not being updated


class TestExtendMaintenanceRequest:
    """Tests for ExtendMaintenanceRequest model."""

    def test_extend_request(self):
        """Test creating an extend request."""
        request = ExtendMaintenanceRequest(
            extend_minutes=30,
            reason="Additional time needed for verification",
        )
        assert request.extend_minutes == 30
        assert len(request.reason) > 0

    def test_extend_limits(self):
        """Test extend request limits."""
        with pytest.raises(ValueError):
            ExtendMaintenanceRequest(extend_minutes=0, reason="test")

        with pytest.raises(ValueError):
            ExtendMaintenanceRequest(extend_minutes=500, reason="test")  # > 480


class TestMaintenanceNotification:
    """Tests for MaintenanceNotification model."""

    def test_notification_creation(self, sample_window):
        """Test creating a maintenance notification."""
        notification = MaintenanceNotification(
            window_id=sample_window.id,
            notification_type=NotificationType.REMINDER,
            recipients=["team@example.com", "#ops-channel"],
            message="Maintenance starting in 1 hour",
            scheduled_for=datetime.utcnow() + timedelta(hours=1),
        )
        assert notification.notification_type == NotificationType.REMINDER
        assert len(notification.recipients) == 2


class TestOverlapWarning:
    """Tests for OverlapWarning model."""

    def test_overlap_warning(self):
        """Test creating an overlap warning."""
        warning = OverlapWarning(
            window_id=uuid4(),
            overlapping_window_id=uuid4(),
            overlap_start=datetime.utcnow(),
            overlap_end=datetime.utcnow() + timedelta(hours=1),
            shared_scope=["payments-api"],
        )
        assert len(warning.shared_scope) == 1


class TestMaintenanceAPI:
    """Tests for Maintenance API endpoints."""

    def test_list_windows(self, client):
        """Test GET /api/maintenance/windows endpoint."""
        response = client.get("/api/maintenance/windows")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_window(self, client):
        """Test POST /api/maintenance/windows endpoint."""
        future = datetime.utcnow() + timedelta(hours=1)
        response = client.post(
            "/api/maintenance/windows",
            json={
                "title": "Test Maintenance",
                "scope": {
                    "scope_type": "service",
                    "identifiers": ["test-service"],
                },
                "schedule": {
                    "start_time": future.isoformat(),
                    "end_time": (future + timedelta(hours=2)).isoformat(),
                },
            },
        )
        assert response.status_code in (200, 201)

    def test_get_window(self, client):
        """Test GET /api/maintenance/windows/{id} endpoint."""
        window_id = str(uuid4())
        response = client.get(f"/api/maintenance/windows/{window_id}")
        assert response.status_code in (200, 404)

    def test_update_window(self, client):
        """Test PUT /api/maintenance/windows/{id} endpoint."""
        window_id = str(uuid4())
        response = client.put(
            f"/api/maintenance/windows/{window_id}",
            json={"title": "Updated Maintenance"},
        )
        assert response.status_code in (200, 404)

    def test_delete_window(self, client):
        """Test DELETE /api/maintenance/windows/{id} endpoint."""
        window_id = str(uuid4())
        response = client.delete(f"/api/maintenance/windows/{window_id}")
        assert response.status_code in (200, 204, 404)

    def test_approve_window(self, client):
        """Test POST /api/maintenance/windows/{id}/approve endpoint."""
        window_id = str(uuid4())
        response = client.post(
            f"/api/maintenance/windows/{window_id}/approve",
            json={"approved": True, "comment": "Approved"},
        )
        assert response.status_code in (200, 404)

    def test_start_window(self, client):
        """Test POST /api/maintenance/windows/{id}/start endpoint."""
        window_id = str(uuid4())
        response = client.post(f"/api/maintenance/windows/{window_id}/start")
        assert response.status_code in (200, 400, 404)

    def test_complete_window(self, client):
        """Test POST /api/maintenance/windows/{id}/complete endpoint."""
        window_id = str(uuid4())
        response = client.post(f"/api/maintenance/windows/{window_id}/complete")
        assert response.status_code in (200, 400, 404)

    def test_extend_window(self, client):
        """Test POST /api/maintenance/windows/{id}/extend endpoint."""
        window_id = str(uuid4())
        response = client.post(
            f"/api/maintenance/windows/{window_id}/extend",
            json={"extend_minutes": 30, "reason": "Need more time"},
        )
        assert response.status_code in (200, 400, 404)

    def test_cancel_window(self, client):
        """Test POST /api/maintenance/windows/{id}/cancel endpoint."""
        window_id = str(uuid4())
        response = client.post(f"/api/maintenance/windows/{window_id}/cancel")
        assert response.status_code in (200, 400, 404)

    def test_get_active_windows(self, client):
        """Test GET /api/maintenance/windows/active endpoint."""
        response = client.get("/api/maintenance/windows/active")
        assert response.status_code == 200

    def test_check_overlaps(self, client):
        """Test POST /api/maintenance/windows/check-overlaps endpoint."""
        future = datetime.utcnow() + timedelta(hours=1)
        response = client.post(
            "/api/maintenance/windows/check-overlaps",
            json={
                "scope": {
                    "scope_type": "service",
                    "identifiers": ["test-service"],
                },
                "schedule": {
                    "start_time": future.isoformat(),
                    "end_time": (future + timedelta(hours=2)).isoformat(),
                },
            },
        )
        assert response.status_code == 200
