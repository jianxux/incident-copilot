"""Comprehensive tests for Change Freeze Management."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.changefreeze.alerts import FreezeAlertService
from src.changefreeze.detector import DeploymentDetector
from src.changefreeze.models import (
    ApprovalStatus,
    ChangeFreeze,
    CreateExceptionRequest,
    CreateFreezeRequest,
    DeploymentEvent,
    FreezeException,
    FreezeScope,
    FreezeStatus,
    FreezeViolation,
    ViolationSeverity,
)
from src.changefreeze.store import ChangeFreezeStore
from src.config import Settings


# --- Fixtures ---


@pytest.fixture
def store():
    """Fresh store for each test."""
    return ChangeFreezeStore()


@pytest.fixture
def settings():
    """Test settings."""
    return Settings(
        slack_bot_token="xoxb-test-token",
        slack_default_channel="#incidents",
        teams_webhook_url="",
        app_url="http://localhost:8000",
    )


@pytest.fixture
def detector(store):
    """Detector with test store."""
    return DeploymentDetector(store=store)


@pytest.fixture
def alert_service(store, settings):
    """Alert service with test settings."""
    return FreezeAlertService(store=store, settings=settings)


@pytest.fixture
def sample_freeze():
    """Sample change freeze."""
    now = datetime.utcnow()
    return ChangeFreeze(
        freeze_id="freeze-001",
        name="Holiday Freeze 2024",
        description="End of year change freeze",
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(days=7),
        scope=FreezeScope.GLOBAL,
        status=FreezeStatus.ACTIVE,
        created_by="admin",
        allow_emergency_deployments=True,
        notification_channels=["#incidents"],
        approvers=["alice", "bob"],
    )


@pytest.fixture
def sample_service_freeze():
    """Sample service-specific freeze."""
    now = datetime.utcnow()
    return ChangeFreeze(
        freeze_id="freeze-002",
        name="Payments Freeze",
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(days=3),
        scope=FreezeScope.SERVICE,
        services=["payments-api", "billing-service"],
        environments=["production"],
        status=FreezeStatus.ACTIVE,
        created_by="payments-team",
    )


@pytest.fixture
def sample_exception():
    """Sample freeze exception."""
    return FreezeException(
        exception_id="exc-001",
        freeze_id="freeze-001",
        requested_by="developer",
        service_name="payments-api",
        environment="production",
        reason="Critical security patch for CVE-2024-1234",
        justification="Remote code execution vulnerability",
        is_emergency=False,
        status=ApprovalStatus.PENDING,
    )


@pytest.fixture
def sample_approved_exception():
    """Sample approved exception."""
    now = datetime.utcnow()
    return FreezeException(
        exception_id="exc-002",
        freeze_id="freeze-001",
        requested_by="developer",
        service_name="payments-api",
        environment="production",
        reason="Hotfix for payment processing",
        status=ApprovalStatus.APPROVED,
        reviewed_by="alice",
        reviewed_at=now,
        valid_from=now - timedelta(hours=1),
        valid_until=now + timedelta(hours=2),
    )


# --- ChangeFreeze Model Tests ---


class TestChangeFreezeModel:
    """Tests for ChangeFreeze model."""

    def test_is_active_during_freeze(self, sample_freeze):
        """Test is_active returns True during freeze period."""
        assert sample_freeze.is_active() is True

    def test_is_active_before_freeze(self):
        """Test is_active returns False before freeze starts."""
        now = datetime.utcnow()
        freeze = ChangeFreeze(
            freeze_id="freeze-future",
            name="Future Freeze",
            starts_at=now + timedelta(days=1),
            ends_at=now + timedelta(days=7),
            created_by="admin",
        )
        assert freeze.is_active() is False

    def test_is_active_after_freeze(self):
        """Test is_active returns False after freeze ends."""
        now = datetime.utcnow()
        freeze = ChangeFreeze(
            freeze_id="freeze-past",
            name="Past Freeze",
            starts_at=now - timedelta(days=7),
            ends_at=now - timedelta(days=1),
            status=FreezeStatus.COMPLETED,
            created_by="admin",
        )
        assert freeze.is_active() is False

    def test_is_active_cancelled_freeze(self, sample_freeze):
        """Test is_active returns False for cancelled freeze."""
        sample_freeze.status = FreezeStatus.CANCELLED
        assert sample_freeze.is_active() is False

    def test_affects_service_global_scope(self, sample_freeze):
        """Test global freeze affects all services."""
        assert sample_freeze.affects_service("payments-api") is True
        assert sample_freeze.affects_service("any-service") is True

    def test_affects_service_service_scope(self, sample_service_freeze):
        """Test service freeze only affects specified services."""
        assert sample_service_freeze.affects_service("payments-api") is True
        assert sample_service_freeze.affects_service("billing-service") is True
        assert sample_service_freeze.affects_service("other-service") is False

    def test_affects_environment_no_restriction(self, sample_freeze):
        """Test freeze with no environment restriction affects all."""
        assert sample_freeze.affects_environment("production") is True
        assert sample_freeze.affects_environment("staging") is True

    def test_affects_environment_with_restriction(self, sample_service_freeze):
        """Test freeze with environment restriction."""
        assert sample_service_freeze.affects_environment("production") is True
        assert sample_service_freeze.affects_environment("staging") is False


# --- FreezeException Model Tests ---


class TestFreezeExceptionModel:
    """Tests for FreezeException model."""

    def test_is_valid_approved_within_window(self, sample_approved_exception):
        """Test approved exception is valid within time window."""
        assert sample_approved_exception.is_valid() is True

    def test_is_valid_pending(self, sample_exception):
        """Test pending exception is not valid."""
        assert sample_exception.is_valid() is False

    def test_is_valid_rejected(self, sample_exception):
        """Test rejected exception is not valid."""
        sample_exception.status = ApprovalStatus.REJECTED
        assert sample_exception.is_valid() is False

    def test_is_valid_expired_window(self):
        """Test exception is invalid after time window expires."""
        now = datetime.utcnow()
        exception = FreezeException(
            exception_id="exc-expired",
            freeze_id="freeze-001",
            requested_by="dev",
            service_name="test",
            reason="Test",
            status=ApprovalStatus.APPROVED,
            reviewed_by="admin",
            reviewed_at=now - timedelta(hours=5),
            valid_from=now - timedelta(hours=4),
            valid_until=now - timedelta(hours=1),
        )
        assert exception.is_valid() is False


# --- ChangeFreezeStore Tests ---


class TestChangeFreezeStore:
    """Tests for ChangeFreezeStore."""

    @pytest.mark.asyncio
    async def test_save_and_get_freeze(self, store, sample_freeze):
        """Test saving and retrieving a freeze."""
        await store.save_freeze(sample_freeze)
        retrieved = await store.get_freeze(sample_freeze.freeze_id)
        
        assert retrieved is not None
        assert retrieved.freeze_id == sample_freeze.freeze_id
        assert retrieved.name == sample_freeze.name

    @pytest.mark.asyncio
    async def test_get_nonexistent_freeze(self, store):
        """Test getting a non-existent freeze returns None."""
        result = await store.get_freeze("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_freeze(self, store, sample_freeze):
        """Test deleting a freeze."""
        await store.save_freeze(sample_freeze)
        deleted = await store.delete_freeze(sample_freeze.freeze_id)
        
        assert deleted is True
        assert await store.get_freeze(sample_freeze.freeze_id) is None

    @pytest.mark.asyncio
    async def test_get_active_freezes(self, store, sample_freeze, sample_service_freeze):
        """Test getting active freezes."""
        await store.save_freeze(sample_freeze)
        await store.save_freeze(sample_service_freeze)
        
        active = await store.get_active_freezes()
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_get_active_freezes_filtered_by_service(
        self, store, sample_freeze, sample_service_freeze
    ):
        """Test filtering active freezes by service."""
        await store.save_freeze(sample_freeze)
        await store.save_freeze(sample_service_freeze)
        
        # payments-api is affected by both
        active = await store.get_active_freezes(service_name="payments-api")
        assert len(active) == 2
        
        # other-service only affected by global
        active = await store.get_active_freezes(service_name="other-service")
        assert len(active) == 1
        assert active[0].scope == FreezeScope.GLOBAL

    @pytest.mark.asyncio
    async def test_cancel_freeze(self, store, sample_freeze):
        """Test cancelling a freeze."""
        await store.save_freeze(sample_freeze)
        cancelled = await store.cancel_freeze(
            freeze_id=sample_freeze.freeze_id,
            cancelled_by="admin",
            reason="Plans changed",
        )
        
        assert cancelled is not None
        assert cancelled.status == FreezeStatus.CANCELLED
        assert cancelled.cancelled_by == "admin"
        assert cancelled.cancellation_reason == "Plans changed"

    @pytest.mark.asyncio
    async def test_save_and_get_exception(self, store, sample_exception):
        """Test saving and retrieving an exception."""
        await store.save_exception(sample_exception)
        retrieved = await store.get_exception(sample_exception.exception_id)
        
        assert retrieved is not None
        assert retrieved.exception_id == sample_exception.exception_id

    @pytest.mark.asyncio
    async def test_approve_exception(self, store, sample_exception):
        """Test approving an exception."""
        await store.save_exception(sample_exception)
        approved = await store.approve_exception(
            exception_id=sample_exception.exception_id,
            reviewed_by="alice",
            notes="Approved for critical fix",
        )
        
        assert approved is not None
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.reviewed_by == "alice"

    @pytest.mark.asyncio
    async def test_reject_exception(self, store, sample_exception):
        """Test rejecting an exception."""
        await store.save_exception(sample_exception)
        rejected = await store.reject_exception(
            exception_id=sample_exception.exception_id,
            reviewed_by="bob",
            notes="Not critical enough",
        )
        
        assert rejected is not None
        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.reviewed_by == "bob"

    @pytest.mark.asyncio
    async def test_get_valid_exceptions(
        self, store, sample_freeze, sample_approved_exception
    ):
        """Test getting valid exceptions for deployment."""
        await store.save_freeze(sample_freeze)
        await store.save_exception(sample_approved_exception)
        
        valid = await store.get_valid_exceptions(
            freeze_id=sample_freeze.freeze_id,
            service_name="payments-api",
            environment="production",
        )
        
        assert len(valid) == 1
        assert valid[0].exception_id == sample_approved_exception.exception_id

    @pytest.mark.asyncio
    async def test_get_pending_exceptions(self, store, sample_exception):
        """Test getting pending exceptions."""
        await store.save_exception(sample_exception)
        pending = await store.get_pending_exceptions()
        
        assert len(pending) == 1
        assert pending[0].status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_save_and_get_violation(self, store):
        """Test saving and retrieving a violation."""
        violation = FreezeViolation(
            violation_id="vio-001",
            freeze_id="freeze-001",
            deployment_event_id="evt-001",
            service_name="payments-api",
            environment="production",
            repository="org/payments-api",
            deployed_by="developer",
            deployed_at=datetime.utcnow(),
            severity=ViolationSeverity.HIGH,
        )
        
        await store.save_violation(violation)
        retrieved = await store.get_violation("vio-001")
        
        assert retrieved is not None
        assert retrieved.violation_id == "vio-001"

    @pytest.mark.asyncio
    async def test_acknowledge_violation(self, store):
        """Test acknowledging a violation."""
        violation = FreezeViolation(
            violation_id="vio-002",
            freeze_id="freeze-001",
            deployment_event_id="evt-002",
            service_name="test",
            environment="production",
            repository="org/test",
            deployed_by="dev",
            deployed_at=datetime.utcnow(),
        )
        
        await store.save_violation(violation)
        acked = await store.acknowledge_violation(
            violation_id="vio-002",
            acknowledged_by="manager",
            reason="Reviewed and accepted",
        )
        
        assert acked is not None
        assert acked.acknowledged is True
        assert acked.acknowledged_by == "manager"

    @pytest.mark.asyncio
    async def test_check_freeze_status(
        self, store, sample_freeze, sample_approved_exception
    ):
        """Test checking freeze status."""
        await store.save_freeze(sample_freeze)
        await store.save_exception(sample_approved_exception)
        
        is_frozen, freezes, exceptions = await store.check_freeze_status(
            service_name="payments-api",
            environment="production",
        )
        
        assert is_frozen is True
        assert len(freezes) == 1
        assert len(exceptions) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self, store, sample_freeze, sample_exception):
        """Test getting storage statistics."""
        await store.save_freeze(sample_freeze)
        await store.save_exception(sample_exception)
        
        stats = await store.get_stats()
        
        assert stats["total_freezes"] == 1
        assert stats["active_freezes"] == 1
        assert stats["total_exceptions"] == 1
        assert stats["pending_exceptions"] == 1


# --- DeploymentDetector Tests ---


class TestDeploymentDetector:
    """Tests for DeploymentDetector."""

    @pytest.mark.asyncio
    async def test_process_deployment_event(self, detector):
        """Test processing GitHub deployment event."""
        payload = {
            "deployment": {
                "id": 12345,
                "sha": "abc123def",
                "ref": "main",
                "environment": "production",
                "payload": {"service_name": "payments-api"},
            },
            "repository": {
                "name": "payments-api",
                "full_name": "org/payments-api",
            },
            "sender": {"login": "developer"},
        }
        
        event = await detector.process_github_webhook("deployment", payload)
        
        assert event is not None
        assert event.source == "github"
        assert event.service_name == "payments-api"
        assert event.environment == "production"
        assert event.deployed_by == "developer"

    @pytest.mark.asyncio
    async def test_process_deployment_status_success(self, detector):
        """Test processing successful deployment status."""
        payload = {
            "deployment_status": {
                "id": 67890,
                "state": "success",
                "environment": "production",
            },
            "deployment": {
                "id": 12345,
                "sha": "abc123",
                "ref": "main",
                "payload": {},
            },
            "repository": {
                "name": "api",
                "full_name": "org/api",
            },
            "sender": {"login": "ci-bot"},
        }
        
        event = await detector.process_github_webhook("deployment_status", payload)
        
        assert event is not None
        assert event.metadata["state"] == "success"

    @pytest.mark.asyncio
    async def test_process_deployment_status_pending_ignored(self, detector):
        """Test pending deployment status is ignored."""
        payload = {
            "deployment_status": {
                "state": "pending",
            },
            "deployment": {},
            "repository": {"name": "api", "full_name": "org/api"},
            "sender": {"login": "bot"},
        }
        
        event = await detector.process_github_webhook("deployment_status", payload)
        assert event is None

    @pytest.mark.asyncio
    async def test_process_push_to_main(self, detector):
        """Test processing push to main branch."""
        payload = {
            "ref": "refs/heads/main",
            "after": "abc123",
            "repository": {
                "name": "payments-api",
                "full_name": "org/payments-api",
            },
            "pusher": {"name": "developer"},
            "head_commit": {"message": "Fix bug"},
            "commits": [{}],
        }
        
        event = await detector.process_github_webhook("push", payload)
        
        assert event is not None
        assert event.branch == "main"
        assert event.environment == "production"

    @pytest.mark.asyncio
    async def test_process_push_to_feature_branch_ignored(self, detector):
        """Test push to feature branch is ignored."""
        payload = {
            "ref": "refs/heads/feature/new-stuff",
            "repository": {"name": "api", "full_name": "org/api"},
            "pusher": {"name": "dev"},
            "head_commit": {},
            "commits": [],
        }
        
        event = await detector.process_github_webhook("push", payload)
        assert event is None

    @pytest.mark.asyncio
    async def test_process_release_published(self, detector):
        """Test processing published release."""
        payload = {
            "action": "published",
            "release": {
                "id": 11111,
                "tag_name": "v1.2.3",
                "target_commitish": "main",
                "name": "Release 1.2.3",
            },
            "repository": {
                "name": "payments-api",
                "full_name": "org/payments-api",
            },
            "sender": {"login": "release-manager"},
        }
        
        event = await detector.process_github_webhook("release", payload)
        
        assert event is not None
        assert event.tag == "v1.2.3"
        assert event.environment == "production"

    @pytest.mark.asyncio
    async def test_detect_violation_during_freeze(
        self, store, detector, sample_freeze
    ):
        """Test deployment during freeze creates violation."""
        await store.save_freeze(sample_freeze)
        
        payload = {
            "deployment": {
                "id": 99999,
                "sha": "xyz789",
                "environment": "production",
                "payload": {"service_name": "payments-api"},
            },
            "repository": {
                "name": "payments-api",
                "full_name": "org/payments-api",
            },
            "sender": {"login": "developer"},
        }
        
        event = await detector.process_github_webhook("deployment", payload)
        
        assert event is not None
        assert event.during_freeze is True
        assert event.is_violation is True
        assert event.freeze_id == sample_freeze.freeze_id
        assert event.violation_id is not None
        
        # Verify violation was created
        violation = await store.get_violation(event.violation_id)
        assert violation is not None
        assert violation.service_name == "payments-api"

    @pytest.mark.asyncio
    async def test_deployment_with_valid_exception(
        self, store, detector, sample_freeze, sample_approved_exception
    ):
        """Test deployment with valid exception is not a violation."""
        await store.save_freeze(sample_freeze)
        await store.save_exception(sample_approved_exception)
        
        payload = {
            "deployment": {
                "id": 88888,
                "sha": "valid123",
                "environment": "production",
                "payload": {"service_name": "payments-api"},
            },
            "repository": {
                "name": "payments-api",
                "full_name": "org/payments-api",
            },
            "sender": {"login": "developer"},
        }
        
        event = await detector.process_github_webhook("deployment", payload)
        
        assert event is not None
        assert event.during_freeze is True
        assert event.is_violation is False
        assert event.exception_id == sample_approved_exception.exception_id

    @pytest.mark.asyncio
    async def test_check_deployment_allowed_no_freeze(self, detector):
        """Test deployment allowed when no freeze."""
        allowed, reason, freezes, exceptions = await detector.check_deployment_allowed(
            service_name="any-service",
            environment="production",
        )
        
        assert allowed is True
        assert "No active" in reason
        assert len(freezes) == 0

    @pytest.mark.asyncio
    async def test_check_deployment_blocked_by_freeze(
        self, store, detector, sample_freeze
    ):
        """Test deployment blocked by active freeze."""
        await store.save_freeze(sample_freeze)
        
        allowed, reason, freezes, exceptions = await detector.check_deployment_allowed(
            service_name="payments-api",
            environment="production",
        )
        
        assert allowed is False
        assert "freeze active" in reason.lower()
        assert len(freezes) == 1


# --- ViolationSeverity Tests ---


class TestViolationSeverity:
    """Tests for violation severity determination."""

    @pytest.mark.asyncio
    async def test_critical_severity_global_freeze(self, store, detector):
        """Test critical severity for global freeze violation."""
        now = datetime.utcnow()
        freeze = ChangeFreeze(
            freeze_id="freeze-global",
            name="Global Freeze",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(days=1),
            scope=FreezeScope.GLOBAL,
            status=FreezeStatus.ACTIVE,
            created_by="admin",
        )
        await store.save_freeze(freeze)
        
        payload = {
            "deployment": {
                "id": 1,
                "environment": "production",
                "payload": {},
            },
            "repository": {"name": "api", "full_name": "org/api"},
            "sender": {"login": "dev"},
        }
        
        event = await detector.process_github_webhook("deployment", payload)
        
        assert event is not None
        violation = await store.get_violation(event.violation_id)
        assert violation.severity == ViolationSeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_medium_severity_staging(self, store, detector, sample_freeze):
        """Test medium severity for staging deployment."""
        await store.save_freeze(sample_freeze)
        
        payload = {
            "deployment": {
                "id": 2,
                "environment": "staging",
                "payload": {},
            },
            "repository": {"name": "api", "full_name": "org/api"},
            "sender": {"login": "dev"},
        }
        
        event = await detector.process_github_webhook("deployment", payload)
        
        assert event is not None
        violation = await store.get_violation(event.violation_id)
        assert violation.severity == ViolationSeverity.MEDIUM


# --- FreezeAlertService Tests ---


class TestFreezeAlertService:
    """Tests for FreezeAlertService."""

    @pytest.mark.asyncio
    async def test_alert_violation_sends_slack(self, store, alert_service, sample_freeze):
        """Test violation alert sends to Slack."""
        await store.save_freeze(sample_freeze)
        
        violation = FreezeViolation(
            violation_id="vio-alert-001",
            freeze_id=sample_freeze.freeze_id,
            deployment_event_id="evt-001",
            service_name="payments-api",
            environment="production",
            repository="org/payments-api",
            deployed_by="developer",
            deployed_at=datetime.utcnow(),
            severity=ViolationSeverity.HIGH,
        )
        await store.save_violation(violation)
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response
            
            channels = await alert_service.alert_violation(violation, sample_freeze)
        
        assert len(channels) > 0
        mock_post.assert_called()

    @pytest.mark.asyncio
    async def test_alert_violation_not_duplicated(
        self, store, alert_service, sample_freeze
    ):
        """Test violation alert not sent twice."""
        await store.save_freeze(sample_freeze)
        
        violation = FreezeViolation(
            violation_id="vio-alert-002",
            freeze_id=sample_freeze.freeze_id,
            deployment_event_id="evt-002",
            service_name="api",
            environment="production",
            repository="org/api",
            deployed_by="dev",
            deployed_at=datetime.utcnow(),
            alert_sent=True,
            alert_channels=["slack:#incidents"],
        )
        await store.save_violation(violation)
        
        channels = await alert_service.alert_violation(violation)
        
        # Should return existing channels without sending again
        assert channels == ["slack:#incidents"]

    @pytest.mark.asyncio
    async def test_format_violation_message(self, alert_service, sample_freeze):
        """Test violation message formatting."""
        violation = FreezeViolation(
            violation_id="vio-format",
            freeze_id=sample_freeze.freeze_id,
            deployment_event_id="evt-format",
            service_name="payments-api",
            environment="production",
            repository="org/payments-api",
            deployed_by="developer",
            deployed_at=datetime.utcnow(),
            severity=ViolationSeverity.CRITICAL,
            commit_sha="abc123def456",
            commit_message="Fix critical bug",
        )
        
        message = alert_service._format_violation_message(violation, sample_freeze)
        
        assert "blocks" in message
        assert "text" in message
        assert "payments-api" in message["text"]


# --- Integration Tests ---


class TestChangeFreezeIntegration:
    """Integration tests for the change freeze system."""

    @pytest.mark.asyncio
    async def test_full_freeze_lifecycle(self, store):
        """Test complete freeze lifecycle."""
        now = datetime.utcnow()
        
        # 1. Create freeze
        freeze = ChangeFreeze(
            freeze_id="int-freeze-001",
            name="Integration Test Freeze",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(days=1),
            scope=FreezeScope.SERVICE,
            services=["test-service"],
            status=FreezeStatus.ACTIVE,
            created_by="test",
            allow_emergency_deployments=True,
        )
        await store.save_freeze(freeze)
        
        # 2. Check status - should be frozen
        is_frozen, _, _ = await store.check_freeze_status(
            service_name="test-service",
            environment="production",
        )
        assert is_frozen is True
        
        # 3. Request exception
        exception = FreezeException(
            exception_id="int-exc-001",
            freeze_id=freeze.freeze_id,
            requested_by="developer",
            service_name="test-service",
            environment="production",
            reason="Critical fix needed",
        )
        await store.save_exception(exception)
        
        # 4. Approve exception
        await store.approve_exception(
            exception_id=exception.exception_id,
            reviewed_by="manager",
            valid_from=now,
            valid_until=now + timedelta(hours=2),
        )
        
        # 5. Check status - should have valid exception
        _, _, exceptions = await store.check_freeze_status(
            service_name="test-service",
            environment="production",
        )
        assert len(exceptions) == 1
        
        # 6. Cancel freeze
        await store.cancel_freeze(
            freeze_id=freeze.freeze_id,
            cancelled_by="admin",
            reason="No longer needed",
        )
        
        # 7. Verify cancelled
        updated = await store.get_freeze(freeze.freeze_id)
        assert updated.status == FreezeStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_emergency_deployment_auto_approved(self, store):
        """Test emergency deployment is auto-approved."""
        now = datetime.utcnow()
        
        freeze = ChangeFreeze(
            freeze_id="emerg-freeze",
            name="Emergency Test",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(days=1),
            status=FreezeStatus.ACTIVE,
            created_by="admin",
            allow_emergency_deployments=True,
        )
        await store.save_freeze(freeze)
        
        # Create emergency exception
        exception = FreezeException(
            exception_id="emerg-exc",
            freeze_id=freeze.freeze_id,
            requested_by="oncall",
            service_name="critical-service",
            environment="production",
            reason="Production outage",
            is_emergency=True,
            emergency_ticket_id="INC-12345",
            status=ApprovalStatus.APPROVED,  # Would be set by routes handler
            reviewed_by="system",
            reviewed_at=now,
        )
        await store.save_exception(exception)
        
        # Should be immediately valid
        valid = await store.get_valid_exceptions(
            freeze_id=freeze.freeze_id,
            service_name="critical-service",
            environment="production",
        )
        assert len(valid) == 1
        assert valid[0].is_emergency is True


# --- Edge Cases ---


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_overlapping_freezes(self, store):
        """Test handling of overlapping freeze periods."""
        now = datetime.utcnow()
        
        # Global freeze
        global_freeze = ChangeFreeze(
            freeze_id="overlap-global",
            name="Global",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=7),
            scope=FreezeScope.GLOBAL,
            status=FreezeStatus.ACTIVE,
            created_by="admin",
        )
        
        # Service freeze (subset)
        service_freeze = ChangeFreeze(
            freeze_id="overlap-service",
            name="Service",
            starts_at=now,
            ends_at=now + timedelta(days=3),
            scope=FreezeScope.SERVICE,
            services=["payments-api"],
            status=FreezeStatus.ACTIVE,
            created_by="team",
        )
        
        await store.save_freeze(global_freeze)
        await store.save_freeze(service_freeze)
        
        # Both should affect payments-api
        active = await store.get_active_freezes(service_name="payments-api")
        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_exception_for_wrong_service(self, store, sample_freeze):
        """Test exception doesn't apply to different service."""
        await store.save_freeze(sample_freeze)
        
        exception = FreezeException(
            exception_id="wrong-service-exc",
            freeze_id=sample_freeze.freeze_id,
            requested_by="dev",
            service_name="other-api",
            environment="production",
            reason="Test",
            status=ApprovalStatus.APPROVED,
            reviewed_by="admin",
            reviewed_at=datetime.utcnow(),
        )
        await store.save_exception(exception)
        
        # Should not find exception for payments-api
        valid = await store.get_valid_exceptions(
            freeze_id=sample_freeze.freeze_id,
            service_name="payments-api",
            environment="production",
        )
        assert len(valid) == 0

    @pytest.mark.asyncio
    async def test_store_max_items_trimming(self):
        """Test store trims old items when max reached."""
        store = ChangeFreezeStore(max_items=5)
        
        for i in range(10):
            event = DeploymentEvent(
                event_id=f"evt-{i}",
                service_name="test",
                repository="org/test",
                deployed_by="dev",
            )
            await store.save_deployment(event)
        
        # Should only keep 5 most recent
        stats = await store.get_stats()
        assert stats["total_deployments"] == 5

    @pytest.mark.asyncio
    async def test_clear_store(self, store, sample_freeze, sample_exception):
        """Test clearing all store data."""
        await store.save_freeze(sample_freeze)
        await store.save_exception(sample_exception)
        
        await store.clear()
        
        stats = await store.get_stats()
        assert stats["total_freezes"] == 0
        assert stats["total_exceptions"] == 0
