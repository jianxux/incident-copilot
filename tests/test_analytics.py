"""Tests for analytics module."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.analytics.models import IncidentMetrics, MTTRStats, PeriodComparison
from src.analytics.store import AnalyticsStore
from src.analytics.tracker import AnalyticsTracker
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def analytics_store():
    """Create a fresh analytics store for testing."""
    store = AnalyticsStore()
    yield store
    await store.clear()


@pytest.fixture
def tracker(analytics_store):
    """Create a tracker with a fresh store."""
    return AnalyticsTracker(store=analytics_store)


class TestIncidentMetrics:
    """Tests for IncidentMetrics model."""

    def test_time_to_resolve_calculation(self):
        """Test MTTR calculation from timestamps."""
        triggered = datetime(2024, 1, 1, 10, 0, 0)
        resolved = datetime(2024, 1, 1, 10, 30, 0)  # 30 minutes later

        metrics = IncidentMetrics(
            incident_id="test-1",
            triggered_at=triggered,
            resolved_at=resolved,
            service_name="test-service",
            severity="medium",
        )

        assert metrics.time_to_resolve_seconds == 1800  # 30 minutes in seconds

    def test_time_to_acknowledge_calculation(self):
        """Test TTA calculation from timestamps."""
        triggered = datetime(2024, 1, 1, 10, 0, 0)
        acknowledged = datetime(2024, 1, 1, 10, 5, 0)  # 5 minutes later

        metrics = IncidentMetrics(
            incident_id="test-1",
            triggered_at=triggered,
            acknowledged_at=acknowledged,
            service_name="test-service",
            severity="high",
        )

        assert metrics.time_to_acknowledge_seconds == 300  # 5 minutes in seconds

    def test_no_resolution_returns_none(self):
        """Test that unresolved incidents return None for MTTR."""
        metrics = IncidentMetrics(
            incident_id="test-1",
            triggered_at=datetime.utcnow(),
            service_name="test-service",
            severity="low",
        )

        assert metrics.time_to_resolve_seconds is None


class TestMTTRStats:
    """Tests for MTTRStats model."""

    def test_mttr_minutes_conversion(self):
        """Test conversion from seconds to minutes."""
        stats = MTTRStats(
            period="7d",
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            mean_mttr_seconds=1800,  # 30 minutes
            median_mttr_seconds=1200,  # 20 minutes
            p90_mttr_seconds=3600,  # 60 minutes
            incidents_count=10,
            resolved_count=8,
        )

        assert stats.mean_mttr_minutes == 30.0
        assert stats.median_mttr_minutes == 20.0
        assert stats.p90_mttr_minutes == 60.0

    def test_none_values(self):
        """Test that None values are handled correctly."""
        stats = MTTRStats(
            period="7d",
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            incidents_count=0,
            resolved_count=0,
        )

        assert stats.mean_mttr_minutes is None
        assert stats.median_mttr_minutes is None


class TestPeriodComparison:
    """Tests for PeriodComparison model."""

    def test_improvement_detection(self):
        """Test that improvement is detected correctly."""
        current = MTTRStats(
            period="This Week",
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            mean_mttr_seconds=1200,  # 20 minutes (improved)
            incidents_count=10,
            resolved_count=10,
        )
        previous = MTTRStats(
            period="Last Week",
            period_start=datetime.utcnow() - timedelta(days=14),
            period_end=datetime.utcnow() - timedelta(days=7),
            mean_mttr_seconds=1800,  # 30 minutes
            incidents_count=12,
            resolved_count=12,
        )

        comparison = PeriodComparison.from_stats(current, previous)

        assert comparison.trend == "improving"
        assert comparison.mttr_change_percent > 0  # Positive means improvement

    def test_degradation_detection(self):
        """Test that degradation is detected correctly."""
        current = MTTRStats(
            period="This Week",
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            mean_mttr_seconds=2400,  # 40 minutes (worse)
            incidents_count=10,
            resolved_count=10,
        )
        previous = MTTRStats(
            period="Last Week",
            period_start=datetime.utcnow() - timedelta(days=14),
            period_end=datetime.utcnow() - timedelta(days=7),
            mean_mttr_seconds=1800,  # 30 minutes
            incidents_count=10,
            resolved_count=10,
        )

        comparison = PeriodComparison.from_stats(current, previous)

        assert comparison.trend == "degrading"
        assert comparison.mttr_change_percent < 0  # Negative means degradation


class TestAnalyticsStore:
    """Tests for AnalyticsStore."""

    @pytest.mark.asyncio
    async def test_record_event_creates_metrics(self):
        """Test that recording an event creates metrics."""
        store = AnalyticsStore()
        now = datetime.utcnow()

        metrics = await store.record_event(
            incident_id="test-1",
            event_type="triggered",
            timestamp=now,
            service_name="payments-api",
            severity="high",
        )

        assert metrics.incident_id == "test-1"
        assert metrics.service_name == "payments-api"
        assert metrics.severity == "high"
        assert metrics.triggered_at == now

    @pytest.mark.asyncio
    async def test_record_multiple_events(self):
        """Test recording multiple events for same incident."""
        store = AnalyticsStore()
        triggered = datetime.utcnow()
        acknowledged = triggered + timedelta(minutes=5)
        resolved = triggered + timedelta(minutes=30)

        await store.record_event(
            incident_id="test-1",
            event_type="triggered",
            timestamp=triggered,
            service_name="user-service",
            severity="medium",
        )

        await store.record_event(
            incident_id="test-1",
            event_type="acknowledged",
            timestamp=acknowledged,
        )

        metrics = await store.record_event(
            incident_id="test-1",
            event_type="resolved",
            timestamp=resolved,
        )

        assert metrics.triggered_at == triggered
        assert metrics.acknowledged_at == acknowledged
        assert metrics.resolved_at == resolved
        assert metrics.time_to_resolve_seconds == 1800

    @pytest.mark.asyncio
    async def test_get_metrics_for_period(self):
        """Test filtering metrics by time period."""
        store = AnalyticsStore()
        now = datetime.utcnow()

        # Create incidents at different times
        await store.record_event(
            incident_id="old-1",
            event_type="triggered",
            timestamp=now - timedelta(days=30),
            service_name="old-service",
            severity="low",
        )

        await store.record_event(
            incident_id="recent-1",
            event_type="triggered",
            timestamp=now - timedelta(days=3),
            service_name="new-service",
            severity="high",
        )

        # Query last 7 days
        metrics = await store.get_metrics_for_period(
            start=now - timedelta(days=7),
            end=now,
        )

        assert len(metrics) == 1
        assert metrics[0].incident_id == "recent-1"


class TestAnalyticsTracker:
    """Tests for AnalyticsTracker."""

    @pytest.mark.asyncio
    async def test_calculate_mttr_stats(self):
        """Test MTTR statistics calculation."""
        store = AnalyticsStore()
        tracker = AnalyticsTracker(store=store)
        now = datetime.utcnow()

        # Create some resolved incidents
        for i in range(5):
            triggered = now - timedelta(days=i, hours=i)
            resolved = triggered + timedelta(
                minutes=20 + i * 5
            )  # 20, 25, 30, 35, 40 min

            await store.record_event(
                incident_id=f"test-{i}",
                event_type="triggered",
                timestamp=triggered,
                service_name="test-service",
                severity="medium",
            )
            await store.record_event(
                incident_id=f"test-{i}",
                event_type="resolved",
                timestamp=resolved,
            )

        stats = await tracker.calculate_mttr_stats(
            start=now - timedelta(days=7),
            end=now,
        )

        assert stats.incidents_count == 5
        assert stats.resolved_count == 5
        assert stats.mean_mttr_seconds is not None
        assert stats.median_mttr_seconds is not None

    @pytest.mark.asyncio
    async def test_compare_periods(self):
        """Test period comparison."""
        store = AnalyticsStore()
        tracker = AnalyticsTracker(store=store)
        now = datetime.utcnow()

        # Current period incidents (faster resolution) - within last 7 days
        for i in range(3):
            triggered = now - timedelta(days=i + 1)  # 1, 2, 3 days ago
            await store.record_event(
                incident_id=f"current-{i}",
                event_type="triggered",
                timestamp=triggered,
                service_name="service",
                severity="medium",
            )
            await store.record_event(
                incident_id=f"current-{i}",
                event_type="resolved",
                timestamp=triggered + timedelta(minutes=15),  # 15 min resolution
            )

        # Previous period incidents (slower resolution) - 8-14 days ago
        for i in range(3):
            triggered = now - timedelta(days=8 + i)  # 8, 9, 10 days ago
            await store.record_event(
                incident_id=f"previous-{i}",
                event_type="triggered",
                timestamp=triggered,
                service_name="service",
                severity="medium",
            )
            await store.record_event(
                incident_id=f"previous-{i}",
                event_type="resolved",
                timestamp=triggered + timedelta(minutes=30),  # 30 min resolution
            )

        comparison = await tracker.compare_periods(
            current_start=now - timedelta(days=7),
            current_end=now,
            previous_start=now - timedelta(days=14),
            previous_end=now - timedelta(days=7),
        )

        assert comparison.trend == "improving"
        assert comparison.current_period.incidents_count == 3
        assert comparison.previous_period.incidents_count == 3


class TestAnalyticsAPI:
    """Tests for analytics API endpoints."""

    def test_get_mttr_stats(self, client):
        """Test GET /api/analytics/mttr endpoint."""
        response = client.get("/api/analytics/mttr?days=7")
        assert response.status_code == 200

        data = response.json()
        assert "period" in data
        assert "incidents_count" in data
        assert "resolved_count" in data

    def test_get_incidents(self, client):
        """Test GET /api/analytics/incidents endpoint."""
        response = client.get("/api/analytics/incidents?days=7")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_get_comparison(self, client):
        """Test GET /api/analytics/comparison endpoint."""
        response = client.get("/api/analytics/comparison?days=7")
        assert response.status_code == 200

        data = response.json()
        assert "current_period" in data
        assert "previous_period" in data
        assert "trend" in data

    def test_analytics_dashboard_page(self, client):
        """Test GET /dashboard/analytics page loads."""
        response = client.get("/dashboard/analytics")
        assert response.status_code == 200
        assert "Analytics" in response.text

    def test_record_triggered(self, client):
        """Test POST /api/analytics/record/triggered endpoint."""
        response = client.post(
            "/api/analytics/record/triggered",
            params={
                "incident_id": "test-api-1",
                "service_name": "test-service",
                "severity": "high",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"

    def test_record_resolved(self, client):
        """Test POST /api/analytics/record/resolved endpoint."""
        # First trigger
        client.post(
            "/api/analytics/record/triggered",
            params={
                "incident_id": "test-api-2",
                "service_name": "test-service",
                "severity": "medium",
            },
        )

        # Then resolve
        response = client.post(
            "/api/analytics/record/resolved",
            params={"incident_id": "test-api-2"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"
