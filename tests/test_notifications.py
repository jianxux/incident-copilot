"""Tests for notification preferences and delivery module."""

from datetime import time

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.notifications.models import (
    ROLE_DEFAULTS,
    ChannelType,
    DigestFrequency,
    NotificationChannel,
    NotificationPayload,
    NotificationPreference,
    NotificationRule,
    NotificationType,
    QuietHours,
    Severity,
    UserRole,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_preference() -> NotificationPreference:
    """Create a sample notification preference."""
    return NotificationPreference(
        user_id="user-123",
        role=UserRole.ON_CALL,
        enabled=True,
        channels=[
            NotificationChannel(
                type=ChannelType.EMAIL,
                address="user@example.com",
                verified=True,
                priority=1,
            ),
            NotificationChannel(
                type=ChannelType.SLACK, address="#alerts", verified=True, priority=2
            ),
        ],
        quiet_hours=QuietHours(enabled=False),
        rules=[
            NotificationRule(
                id="rule-1",
                name="Critical Alerts",
                min_severity=Severity.P2,
                notification_types=[
                    NotificationType.INCIDENT_CREATED,
                    NotificationType.BREACH_OCCURRED,
                ],
                channels=[ChannelType.EMAIL, ChannelType.SLACK],
            ),
        ],
    )


class TestNotificationChannel:
    """Tests for NotificationChannel model."""

    def test_channel_creation(self):
        """Test creating a notification channel."""
        channel = NotificationChannel(
            type=ChannelType.EMAIL,
            address="user@example.com",
            verified=True,
            priority=1,
        )
        assert channel.type == ChannelType.EMAIL
        assert channel.enabled
        assert channel.verified
        assert channel.priority == 1

    def test_empty_address_rejected(self):
        """Test that empty address is rejected."""
        with pytest.raises(ValueError):
            NotificationChannel(type=ChannelType.EMAIL, address="")

    def test_whitespace_address_stripped(self):
        """Test that whitespace is stripped from address."""
        channel = NotificationChannel(
            type=ChannelType.SLACK,
            address="  #alerts  ",
        )
        assert channel.address == "#alerts"


class TestQuietHours:
    """Tests for QuietHours model."""

    def test_default_quiet_hours(self):
        """Test default quiet hours configuration."""
        qh = QuietHours()
        assert not qh.enabled
        assert qh.start_time == time(22, 0)
        assert qh.end_time == time(8, 0)
        assert qh.allow_p1

    def test_is_active_disabled(self):
        """Test quiet hours when disabled."""
        qh = QuietHours(enabled=False)
        assert not qh.is_active(time(23, 0))

    def test_is_active_overnight(self):
        """Test overnight quiet hours (22:00 to 08:00)."""
        qh = QuietHours(enabled=True, start_time=time(22, 0), end_time=time(8, 0))

        # During quiet hours
        assert qh.is_active(time(23, 0))
        assert qh.is_active(time(2, 0))
        assert qh.is_active(time(7, 30))

        # Outside quiet hours
        assert not qh.is_active(time(9, 0))
        assert not qh.is_active(time(12, 0))
        assert not qh.is_active(time(21, 0))

    def test_is_active_daytime(self):
        """Test daytime quiet hours (09:00 to 17:00)."""
        qh = QuietHours(enabled=True, start_time=time(9, 0), end_time=time(17, 0))

        # During quiet hours
        assert qh.is_active(time(10, 0))
        assert qh.is_active(time(12, 0))
        assert qh.is_active(time(16, 59))

        # Outside quiet hours
        assert not qh.is_active(time(8, 0))
        assert not qh.is_active(time(17, 0))
        assert not qh.is_active(time(20, 0))

    def test_should_override_p1(self):
        """Test P1 override for quiet hours."""
        qh = QuietHours(enabled=True, allow_p1=True, allow_p2=False)
        assert qh.should_override(Severity.P1)
        assert not qh.should_override(Severity.P2)
        assert not qh.should_override(Severity.P3)

    def test_should_override_p2(self):
        """Test P2 override for quiet hours."""
        qh = QuietHours(enabled=True, allow_p1=True, allow_p2=True)
        assert qh.should_override(Severity.P1)
        assert qh.should_override(Severity.P2)
        assert not qh.should_override(Severity.P3)


class TestNotificationRule:
    """Tests for NotificationRule model."""

    def test_rule_creation(self):
        """Test creating a notification rule."""
        rule = NotificationRule(
            id="rule-1",
            name="Critical Alerts",
            min_severity=Severity.P2,
            notification_types=[NotificationType.INCIDENT_CREATED],
        )
        assert rule.enabled
        assert rule.min_severity == Severity.P2

    def test_severity_range_validation(self):
        """Test severity range validation."""
        # Valid: P3 (min) to P1 (max) - less critical to more critical
        rule = NotificationRule(
            name="Valid Range",
            min_severity=Severity.P3,
            max_severity=Severity.P1,
        )
        assert rule.min_severity == Severity.P3
        assert rule.max_severity == Severity.P1

    def test_matches_notification_type(self):
        """Test rule matching by notification type."""
        rule = NotificationRule(
            name="Test",
            notification_types=[NotificationType.INCIDENT_CREATED],
            min_severity=Severity.P5,
        )

        assert rule.matches(
            notification_type=NotificationType.INCIDENT_CREATED,
            severity=Severity.P3,
        )
        assert not rule.matches(
            notification_type=NotificationType.INCIDENT_RESOLVED,
            severity=Severity.P3,
        )

    def test_matches_severity(self):
        """Test rule matching by severity."""
        rule = NotificationRule(
            name="High Priority",
            min_severity=Severity.P2,  # P2 or higher
            max_severity=Severity.P1,
        )

        assert rule.matches(NotificationType.INCIDENT_CREATED, Severity.P1)
        assert rule.matches(NotificationType.INCIDENT_CREATED, Severity.P2)
        assert not rule.matches(NotificationType.INCIDENT_CREATED, Severity.P3)

    def test_matches_service_filter(self):
        """Test rule matching with service filter."""
        rule = NotificationRule(
            name="API Only",
            min_severity=Severity.P5,
            services=["api-service", "payments"],
        )

        assert rule.matches(
            NotificationType.INCIDENT_CREATED, Severity.P3, service="api-service"
        )
        assert not rule.matches(
            NotificationType.INCIDENT_CREATED, Severity.P3, service="web-service"
        )

    def test_matches_disabled_rule(self):
        """Test that disabled rules don't match."""
        rule = NotificationRule(
            name="Disabled",
            enabled=False,
            min_severity=Severity.P5,
        )
        assert not rule.matches(NotificationType.INCIDENT_CREATED, Severity.P1)


class TestNotificationPreference:
    """Tests for NotificationPreference model."""

    def test_preference_creation(self, sample_preference):
        """Test creating a notification preference."""
        assert sample_preference.user_id == "user-123"
        assert sample_preference.role == UserRole.ON_CALL
        assert len(sample_preference.channels) == 2
        assert len(sample_preference.rules) == 1

    def test_get_enabled_channels(self, sample_preference):
        """Test getting enabled channels."""
        channels = sample_preference.get_enabled_channels()
        assert len(channels) == 2
        # Should be sorted by priority (highest first)
        assert channels[0].priority >= channels[1].priority

    def test_get_enabled_channels_by_type(self, sample_preference):
        """Test filtering enabled channels by type."""
        email_channels = sample_preference.get_enabled_channels([ChannelType.EMAIL])
        assert len(email_channels) == 1
        assert email_channels[0].type == ChannelType.EMAIL

    def test_get_primary_channel(self, sample_preference):
        """Test getting primary (highest priority) channel."""
        primary = sample_preference.get_primary_channel()
        assert primary is not None
        assert primary.priority == 2  # Slack has priority 2

    def test_get_primary_channel_by_type(self, sample_preference):
        """Test getting primary channel of specific type."""
        primary = sample_preference.get_primary_channel(ChannelType.EMAIL)
        assert primary is not None
        assert primary.type == ChannelType.EMAIL


class TestNotificationPayload:
    """Tests for NotificationPayload model."""

    def test_payload_creation(self):
        """Test creating a notification payload."""
        payload = NotificationPayload(
            id="notif-123",
            type=NotificationType.INCIDENT_CREATED,
            severity=Severity.P1,
            title="Database outage",
            message="Production database is down",
            incident_id="inc-123",
            service="database",
            tags=["production", "database"],
        )
        assert payload.id == "notif-123"
        assert payload.severity == Severity.P1
        assert len(payload.channels_attempted) == 0


class TestRoleDefaults:
    """Tests for role-based default preferences."""

    def test_on_call_defaults(self):
        """Test on-call role default preferences."""
        defaults = ROLE_DEFAULTS[UserRole.ON_CALL]
        assert defaults["default_digest_frequency"] == DigestFrequency.REALTIME
        assert len(defaults["rules"]) >= 1

    def test_manager_defaults(self):
        """Test manager role default preferences."""
        defaults = ROLE_DEFAULTS[UserRole.MANAGER]
        assert defaults["default_digest_frequency"] == DigestFrequency.HOURLY

    def test_executive_defaults(self):
        """Test executive role default preferences."""
        defaults = ROLE_DEFAULTS[UserRole.EXECUTIVE]
        assert defaults["default_digest_frequency"] == DigestFrequency.DAILY


class TestNotificationsAPI:
    """Tests for Notifications API endpoints."""

    def test_get_preferences(self, client):
        """Test GET /api/notifications/preferences endpoint."""
        response = client.get("/api/notifications/preferences/user-123")
        assert response.status_code in (200, 404)

    def test_update_preferences(self, client):
        """Test PUT /api/notifications/preferences endpoint."""
        response = client.put(
            "/api/notifications/preferences/user-123",
            json={
                "user_id": "user-123",
                "enabled": True,
                "channels": [
                    {"type": "email", "address": "user@example.com"},
                ],
            },
        )
        assert response.status_code in (200, 201)

    def test_add_channel(self, client):
        """Test POST /api/notifications/preferences/user-123/channels endpoint."""
        response = client.post(
            "/api/notifications/preferences/user-123/channels",
            json={"type": "slack", "address": "#alerts"},
        )
        assert response.status_code in (200, 201)

    def test_verify_channel(self, client):
        """Test POST /api/notifications/verify endpoint."""
        response = client.post(
            "/api/notifications/verify",
            json={"channel_type": "email", "address": "user@example.com"},
        )
        assert response.status_code in (200, 202)

    def test_send_test_notification(self, client):
        """Test POST /api/notifications/test endpoint."""
        response = client.post(
            "/api/notifications/test",
            json={
                "user_id": "user-123",
                "channel_type": "email",
            },
        )
        assert response.status_code in (200, 202)

    def test_get_notification_history(self, client):
        """Test GET /api/notifications/history endpoint."""
        response = client.get("/api/notifications/history?user_id=user-123")
        assert response.status_code == 200
