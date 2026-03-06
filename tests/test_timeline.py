"""Tests for incident timeline functionality."""

from datetime import UTC, datetime, timedelta

import pytest

from src.models import (
    ContextCard,
    DatadogContext,
    Deployment,
    GitHubContext,
    LogEntry,
    Severity,
)
from src.web.timeline import (
    TimelineBuilder,
    TimelineEvent,
    TimelineEventType,
    format_duration,
    format_relative_time,
)


class TestTimelineEventType:
    """Tests for TimelineEventType enum."""

    def test_alert_types(self):
        """Test alert-related event types."""
        assert TimelineEventType.ALERT_TRIGGERED == "alert_triggered"
        assert TimelineEventType.ALERT_ACKNOWLEDGED == "alert_acknowledged"
        assert TimelineEventType.ALERT_RESOLVED == "alert_resolved"

    def test_deployment_types(self):
        """Test deployment-related event types."""
        assert TimelineEventType.DEPLOYMENT == "deployment"
        assert TimelineEventType.ROLLBACK == "rollback"

    def test_log_types(self):
        """Test log-related event types."""
        assert TimelineEventType.LOG_ERROR == "log_error"
        assert TimelineEventType.LOG_WARNING == "log_warning"


class TestTimelineEvent:
    """Tests for TimelineEvent model."""

    def test_create_event(self):
        """Test creating a timeline event."""
        event = TimelineEvent(
            id="evt_1",
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="High error rate detected",
            description="Error rate exceeded 5% threshold",
            actor="PagerDuty",
            source="PagerDuty",
            severity="high",
        )

        assert event.id == "evt_1"
        assert event.event_type == TimelineEventType.ALERT_TRIGGERED
        assert event.title == "High error rate detected"
        assert event.actor == "PagerDuty"

    def test_event_defaults(self):
        """Test default values for timeline events."""
        event = TimelineEvent(
            id="evt_1",
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.COMMENT,
            title="Test comment",
        )

        assert event.icon == "circle"
        assert event.color == "gray"
        assert event.is_key_event is False
        assert event.metadata == {}


class TestTimelineBuilder:
    """Tests for TimelineBuilder."""

    @pytest.fixture
    def builder(self):
        """Create a TimelineBuilder instance."""
        return TimelineBuilder()

    def test_add_event(self, builder):
        """Test adding an event to the timeline."""
        event = builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="Test alert",
            is_key_event=True,
        )

        assert event.id == "evt_1"
        assert event.event_type == TimelineEventType.ALERT_TRIGGERED
        assert event.is_key_event is True
        assert len(builder.get_events()) == 1

    def test_event_icons_and_colors(self, builder):
        """Test that events get correct icons and colors."""
        alert_event = builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="Alert",
        )

        deploy_event = builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.DEPLOYMENT,
            title="Deploy",
        )

        assert alert_event.icon == "exclamation-circle"
        assert alert_event.color == "red"
        assert deploy_event.icon == "rocket"
        assert deploy_event.color == "purple"

    def test_events_sorted_by_timestamp(self, builder):
        """Test that events are returned sorted by timestamp."""
        now = datetime.now(UTC)

        builder.add_event(
            timestamp=now + timedelta(hours=1),
            event_type=TimelineEventType.ALERT_RESOLVED,
            title="Resolved",
        )
        builder.add_event(
            timestamp=now,
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="Triggered",
        )

        events = builder.get_events()
        assert events[0].title == "Triggered"
        assert events[1].title == "Resolved"

    def test_get_key_events(self, builder):
        """Test filtering for key events only."""
        builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="Key Event",
            is_key_event=True,
        )
        builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.COMMENT,
            title="Regular Event",
            is_key_event=False,
        )

        key_events = builder.get_key_events()
        assert len(key_events) == 1
        assert key_events[0].title == "Key Event"

    def test_get_events_by_type(self, builder):
        """Test filtering events by type."""
        builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.DEPLOYMENT,
            title="Deploy 1",
        )
        builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.LOG_ERROR,
            title="Error 1",
        )
        builder.add_event(
            timestamp=datetime.now(UTC),
            event_type=TimelineEventType.DEPLOYMENT,
            title="Deploy 2",
        )

        deployments = builder.get_events_by_type(TimelineEventType.DEPLOYMENT)
        assert len(deployments) == 2

    def test_to_dict(self, builder):
        """Test converting timeline to dict for JSON serialization."""
        builder.add_event(
            timestamp=datetime(2026, 2, 2, 4, 0, 0, tzinfo=UTC),
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="Test",
        )

        result = builder.to_dict()
        assert len(result) == 1
        assert result[0]["title"] == "Test"
        assert "2026-02-02" in result[0]["timestamp"]


class TestBuildFromContextCard:
    """Tests for building timeline from a context card."""

    @pytest.fixture
    def builder(self):
        """Create a TimelineBuilder instance."""
        return TimelineBuilder()

    @pytest.fixture
    def sample_context_card(self):
        """Create a sample context card for testing."""
        triggered_at = datetime(2026, 2, 2, 3, 0, 0, tzinfo=UTC)

        return ContextCard(
            incident_id="inc-123",
            title="High Error Rate",
            severity=Severity.HIGH,
            service_name="payments-api",
            triggered_at=triggered_at,
            github=GitHubContext(
                repo="payments-api",
                recent_deploys=[
                    Deployment(
                        sha="abc123",
                        short_sha="abc123",
                        author="deploy-bot",
                        message="Add new payment flow",
                        timestamp=triggered_at - timedelta(minutes=30),
                        url="https://github.com/acme/payments/commit/abc123",
                    ),
                ],
            ),
            datadog=DatadogContext(
                service="payments-api",
                logs=[
                    LogEntry(
                        timestamp=triggered_at - timedelta(minutes=5),
                        message="Connection timeout to payment gateway",
                        level="ERROR",
                        service="payments-api",
                    ),
                ],
            ),
            assembly_time_ms=150,
        )

    def test_builds_from_context_card(self, builder, sample_context_card):
        """Test building timeline from a full context card."""
        incident_data = {"notification_sent": True}

        events = builder.build_from_context_card(sample_context_card, incident_data)

        # Should have events for: alert, deployment, log error, context assembled
        assert len(events) >= 3

    def test_includes_alert_triggered(self, builder, sample_context_card):
        """Test that alert triggered event is included."""
        events = builder.build_from_context_card(sample_context_card, {})

        alert_events = [
            e for e in events if e.event_type == TimelineEventType.ALERT_TRIGGERED
        ]
        assert len(alert_events) == 1
        assert alert_events[0].is_key_event is True

    def test_includes_deployments(self, builder, sample_context_card):
        """Test that deployment events are included."""
        events = builder.build_from_context_card(sample_context_card, {})

        deploy_events = [
            e for e in events if e.event_type == TimelineEventType.DEPLOYMENT
        ]
        assert len(deploy_events) == 1
        assert "abc123" in deploy_events[0].title

    def test_github_deploys_added_to_timeline(self, builder):
        """Test multiple GitHub deploys are added with deployment metadata."""
        triggered_at = datetime(2026, 2, 2, 3, 0, 0, tzinfo=UTC)
        card = ContextCard(
            incident_id="inc-456",
            title="Checkout latency spike",
            severity=Severity.HIGH,
            service_name="checkout-api",
            triggered_at=triggered_at,
            github=GitHubContext(
                repo="checkout-api",
                recent_deploys=[
                    Deployment(
                        sha="111111111111",
                        short_sha="1111111",
                        author="alice",
                        message="Optimize query path",
                        timestamp=triggered_at - timedelta(minutes=45),
                        url="https://github.com/acme/checkout/commit/111111111111",
                    ),
                    Deployment(
                        sha="222222222222",
                        short_sha="2222222",
                        author="bob",
                        message="Add cache warming",
                        timestamp=triggered_at - timedelta(minutes=20),
                        url="https://github.com/acme/checkout/commit/222222222222",
                    ),
                ],
            ),
        )

        events = builder.build_from_context_card(card, {})
        deploy_events = [
            e for e in events if e.event_type == TimelineEventType.DEPLOYMENT
        ]

        assert len(deploy_events) == 2
        assert {event.metadata.get("sha") for event in deploy_events} == {
            "111111111111",
            "222222222222",
        }
        assert all(event.source == "GitHub" for event in deploy_events)

    def test_github_deploys_only_before_alert(self, builder):
        """Test only deploys before the alert trigger time are included."""
        triggered_at = datetime(2026, 2, 2, 3, 0, 0, tzinfo=UTC)
        card = ContextCard(
            incident_id="inc-789",
            title="Cart errors",
            severity=Severity.HIGH,
            service_name="cart-api",
            triggered_at=triggered_at,
            github=GitHubContext(
                repo="cart-api",
                recent_deploys=[
                    Deployment(
                        sha="aaaaaa111111",
                        short_sha="aaaaaa1",
                        author="alice",
                        message="Safe change",
                        timestamp=triggered_at - timedelta(minutes=10),
                    ),
                    Deployment(
                        sha="bbbbbb222222",
                        short_sha="bbbbbb2",
                        author="bob",
                        message="Exactly at trigger",
                        timestamp=triggered_at,
                    ),
                    Deployment(
                        sha="cccccc333333",
                        short_sha="cccccc3",
                        author="carol",
                        message="After trigger",
                        timestamp=triggered_at + timedelta(minutes=5),
                    ),
                ],
            ),
        )

        events = builder.build_from_context_card(card, {})
        deploy_events = [
            e for e in events if e.event_type == TimelineEventType.DEPLOYMENT
        ]

        assert len(deploy_events) == 1
        assert deploy_events[0].metadata["sha"] == "aaaaaa111111"

    def test_includes_log_errors(self, builder, sample_context_card):
        """Test that log error events are included."""
        events = builder.build_from_context_card(sample_context_card, {})

        error_events = [
            e for e in events if e.event_type == TimelineEventType.LOG_ERROR
        ]
        assert len(error_events) == 1
        assert "timeout" in error_events[0].title.lower()

    def test_includes_context_assembled(self, builder, sample_context_card):
        """Test that context assembled event is included."""
        events = builder.build_from_context_card(sample_context_card, {})

        context_events = [
            e for e in events if e.event_type == TimelineEventType.CONTEXT_ASSEMBLED
        ]
        assert len(context_events) == 1
        assert "150ms" in context_events[0].description


class TestFormatRelativeTime:
    """Tests for relative time formatting."""

    def test_seconds_ago(self):
        """Test formatting for seconds ago."""
        now = datetime.now(UTC)
        result = format_relative_time(now - timedelta(seconds=30))
        assert "30 seconds ago" in result

    def test_minutes_ago(self):
        """Test formatting for minutes ago."""
        now = datetime.now(UTC)
        result = format_relative_time(now - timedelta(minutes=5))
        assert "5 minute" in result

    def test_hours_ago(self):
        """Test formatting for hours ago."""
        now = datetime.now(UTC)
        result = format_relative_time(now - timedelta(hours=3))
        assert "3 hour" in result

    def test_days_ago(self):
        """Test formatting for days ago."""
        now = datetime.now(UTC)
        result = format_relative_time(now - timedelta(days=2))
        assert "2 day" in result


class TestFormatDuration:
    """Tests for duration formatting."""

    def test_seconds_duration(self):
        """Test formatting for seconds duration."""
        start = datetime(2026, 2, 2, 4, 0, 0)
        end = datetime(2026, 2, 2, 4, 0, 45)

        result = format_duration(start, end)
        assert result == "45s"

    def test_minutes_duration(self):
        """Test formatting for minutes duration."""
        start = datetime(2026, 2, 2, 4, 0, 0)
        end = datetime(2026, 2, 2, 4, 5, 30)

        result = format_duration(start, end)
        assert "5m" in result
        assert "30s" in result

    def test_hours_duration(self):
        """Test formatting for hours duration."""
        start = datetime(2026, 2, 2, 4, 0, 0)
        end = datetime(2026, 2, 2, 6, 30, 0)

        result = format_duration(start, end)
        assert "2h" in result
        assert "30m" in result
