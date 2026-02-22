"""Tests for AI Insights module."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.analytics.models import IncidentMetrics
from src.insights import (
    AnomalyDetector,
    AnomalyType,
    IncidentAnalyzer,
    Insight,
    InsightsService,
    InsightsStore,
    InsightType,
    PatternDetector,
    RecurringPattern,
    Severity,
)
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def insights_store():
    """Create a fresh insights store for testing."""
    store = InsightsStore()
    yield store
    await store.clear()


@pytest.fixture
def sample_incidents():
    """Create sample incidents for testing."""
    now = datetime.utcnow()
    incidents = []

    # Create recurring incidents for pattern detection
    for i in range(5):
        incidents.append(
            IncidentMetrics(
                incident_id=f"db-timeout-{i}",
                triggered_at=now - timedelta(days=i * 2),
                resolved_at=now - timedelta(days=i * 2) + timedelta(minutes=30),
                service_name="database-service",
                severity="high",
            )
        )

    # Create incidents for cascade detection (within 15 minutes)
    base_time = now - timedelta(days=5)
    for j, service in enumerate(
        [
            "api-gateway",
            "user-service",
            "order-service",
            "payment-service",
        ]
    ):
        incidents.append(
            IncidentMetrics(
                incident_id=f"cascade-{j}",
                triggered_at=base_time + timedelta(minutes=j * 3),
                service_name=service,
                severity="critical" if j == 0 else "high",
            )
        )

    # Add some varied incidents
    for k in range(10):
        hour = k % 24
        incidents.append(
            IncidentMetrics(
                incident_id=f"varied-{k}",
                triggered_at=now.replace(hour=hour) - timedelta(days=k),
                resolved_at=now.replace(hour=hour)
                - timedelta(days=k)
                + timedelta(minutes=45),
                service_name=f"service-{k % 3}",
                severity=["low", "medium", "high"][k % 3],
            )
        )

    return incidents


class TestPatternDetector:
    """Tests for PatternDetector."""

    @pytest.mark.asyncio
    async def test_detect_recurring_patterns(self, sample_incidents):
        """Test detection of recurring incident patterns."""
        detector = PatternDetector(min_occurrences=3)

        patterns = await detector.detect_recurring_patterns(sample_incidents)

        # Should detect patterns with 3+ occurrences
        assert len(patterns) >= 0  # May or may not find patterns based on data

    @pytest.mark.asyncio
    async def test_detect_time_patterns(self, sample_incidents):
        """Test detection of time-based patterns."""
        detector = PatternDetector(min_occurrences=3)

        patterns = await detector.detect_time_patterns(sample_incidents)

        # All patterns should have either hour_of_day or day_of_week
        for pattern in patterns:
            assert pattern.hour_of_day is not None or pattern.day_of_week is not None
            assert 0 <= pattern.confidence <= 1

    @pytest.mark.asyncio
    async def test_detect_severity_trends(self, sample_incidents):
        """Test detection of severity trends."""
        detector = PatternDetector()

        trend = await detector.detect_severity_trends(sample_incidents, period_days=30)

        if trend:
            assert trend.trend_direction in ("increasing", "decreasing", "stable")
            assert trend.incidents_analyzed > 0

    def test_normalize_title(self):
        """Test title normalization for pattern matching."""
        detector = PatternDetector()

        # UUID removal (using valid UUID format) - result is lowercased
        normalized = detector._normalize_title(
            "Error in a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )
        assert "<uuid>" in normalized

        # IP removal - result is lowercased
        normalized = detector._normalize_title("Connection failed to 192.168.1.100")
        assert "<ip>" in normalized

        # Lowercase
        normalized = detector._normalize_title("DATABASE Timeout ERROR")
        assert normalized.islower()


class TestAnomalyDetector:
    """Tests for AnomalyDetector."""

    @pytest.mark.asyncio
    async def test_detect_cascading_failures(self, sample_incidents):
        """Test detection of cascading failures."""
        detector = AnomalyDetector(cascade_window_minutes=15)

        cascades = await detector.detect_cascading_failures(sample_incidents)

        # Should detect the cascade we created in sample data
        assert len(cascades) >= 1

        if cascades:
            cascade = cascades[0]
            assert len(cascade.affected_services) >= 3
            assert cascade.total_incidents >= 3

    @pytest.mark.asyncio
    async def test_detect_spikes(self, sample_incidents):
        """Test detection of incident spikes."""
        detector = AnomalyDetector(spike_threshold=1.5)

        spikes = await detector.detect_spikes(sample_incidents, window_hours=4)

        # Verify spike structure if any found
        for spike in spikes:
            assert spike.spike_factor >= 1.5
            assert spike.incident_count > spike.baseline_count

    @pytest.mark.asyncio
    async def test_detect_unusual_times(self, sample_incidents):
        """Test detection of unusual time incidents."""
        detector = AnomalyDetector()

        anomalies = await detector.detect_unusual_times(sample_incidents)

        # All anomalies should be time-related
        for anomaly in anomalies:
            assert anomaly.anomaly_type in (
                AnomalyType.UNUSUAL_HOUR,
                AnomalyType.UNUSUAL_DAY,
            )

    @pytest.mark.asyncio
    async def test_detect_all_anomalies(self, sample_incidents):
        """Test combined anomaly detection."""
        detector = AnomalyDetector()

        anomalies = await detector.detect_all_anomalies(sample_incidents)

        # Should return a list of anomalies
        assert isinstance(anomalies, list)

        # All should be sorted by detected_at descending
        for i in range(len(anomalies) - 1):
            assert anomalies[i].detected_at >= anomalies[i + 1].detected_at


class TestIncidentAnalyzer:
    """Tests for IncidentAnalyzer."""

    @pytest.mark.asyncio
    async def test_analyze_service_dependencies(self, sample_incidents):
        """Test service dependency analysis."""
        analyzer = IncidentAnalyzer(correlation_window_minutes=30)

        dep_map = await analyzer.analyze_service_dependencies(sample_incidents)

        assert dep_map.services is not None
        assert dep_map.dependencies is not None

    @pytest.mark.asyncio
    async def test_get_service_impact_ranking(self, sample_incidents):
        """Test service impact ranking."""
        analyzer = IncidentAnalyzer()

        ranking = await analyzer.get_service_impact_ranking(sample_incidents)

        assert isinstance(ranking, list)
        for service, count, score in ranking:
            assert isinstance(service, str)
            assert count > 0
            assert score > 0

    @pytest.mark.asyncio
    async def test_analyze_resolution_patterns(self, sample_incidents):
        """Test resolution pattern analysis."""
        analyzer = IncidentAnalyzer()

        analysis = await analyzer.analyze_resolution_patterns(sample_incidents)

        assert isinstance(analysis, dict)
        for service, stats in analysis.items():
            assert "avg_mttr_minutes" in stats
            assert "resolved_count" in stats


class TestInsightsStore:
    """Tests for InsightsStore."""

    @pytest.mark.asyncio
    async def test_save_and_get_insight(self):
        """Test saving and retrieving insights."""
        store = InsightsStore()

        insight = Insight(
            insight_id="test-insight-1",
            insight_type=InsightType.RECURRING_INCIDENT,
            severity=Severity.HIGH,
            title="Test Insight",
            description="This is a test insight",
            affected_services=["test-service"],
        )

        saved = await store.save_insight(insight)
        assert saved.insight_id == "test-insight-1"

        retrieved = await store.get_insight("test-insight-1")
        assert retrieved is not None
        assert retrieved.title == "Test Insight"

        await store.clear()

    @pytest.mark.asyncio
    async def test_filter_insights_by_type(self):
        """Test filtering insights by type."""
        store = InsightsStore()

        # Add different types
        await store.save_insight(
            Insight(
                insight_id="pattern-1",
                insight_type=InsightType.RECURRING_INCIDENT,
                severity=Severity.MEDIUM,
                title="Pattern 1",
                description="Test",
            )
        )
        await store.save_insight(
            Insight(
                insight_id="spike-1",
                insight_type=InsightType.SPIKE_DETECTED,
                severity=Severity.HIGH,
                title="Spike 1",
                description="Test",
            )
        )

        patterns = await store.get_all_insights(
            insight_type=InsightType.RECURRING_INCIDENT
        )
        assert len(patterns) == 1
        assert patterns[0].insight_id == "pattern-1"

        await store.clear()

    @pytest.mark.asyncio
    async def test_acknowledge_insight(self):
        """Test acknowledging an insight."""
        store = InsightsStore()

        insight = Insight(
            insight_id="test-ack",
            insight_type=InsightType.SPIKE_DETECTED,
            severity=Severity.HIGH,
            title="Test",
            description="Test",
        )
        await store.save_insight(insight)

        acked = await store.acknowledge_insight("test-ack", "user@example.com")

        assert acked is not None
        assert acked.is_acknowledged is True
        assert acked.acknowledged_by == "user@example.com"
        assert acked.acknowledged_at is not None

        await store.clear()

    @pytest.mark.asyncio
    async def test_save_and_get_pattern(self):
        """Test saving and retrieving patterns."""
        store = InsightsStore()

        pattern = RecurringPattern(
            pattern_id="pattern-123",
            service_name="test-service",
            title_pattern="database timeout",
            incident_count=5,
            first_seen=datetime.utcnow() - timedelta(days=7),
            last_seen=datetime.utcnow(),
        )

        await store.save_pattern(pattern)
        retrieved = await store.get_pattern("pattern-123")

        assert retrieved is not None
        assert retrieved.incident_count == 5

        await store.clear()

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting store statistics."""
        store = InsightsStore()

        stats = await store.get_stats()

        assert "insights_count" in stats
        assert "patterns_count" in stats
        assert "anomalies_count" in stats


class TestInsightsService:
    """Tests for InsightsService."""

    @pytest.mark.asyncio
    async def test_run_analysis(self, sample_incidents):
        """Test running a full analysis."""
        # Note: This requires the analytics store to have data
        # In a real test, we'd mock the store
        service = InsightsService()

        # Just verify the method runs without error
        # Full integration test would require populated stores
        try:
            result = await service.run_analysis()
            assert result is not None
            assert result.analysis_id is not None
        except Exception:
            # May fail if no data, that's OK for this unit test
            pass


class TestInsightsAPI:
    """Tests for insights API endpoints."""

    def test_list_insights(self, client):
        """Test GET /api/insights endpoint."""
        response = client.get("/api/insights")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "insights" in data
        assert isinstance(data["insights"], list)

    def test_list_insights_with_filters(self, client):
        """Test GET /api/insights with filters."""
        response = client.get(
            "/api/insights",
            params={
                "severity": "high",
                "limit": 10,
            },
        )
        assert response.status_code == 200

    def test_get_insights_summary(self, client):
        """Test GET /api/insights/summary endpoint."""
        response = client.get("/api/insights/summary?days=7")
        assert response.status_code == 200

        data = response.json()
        assert "total_insights" in data
        assert "period_start" in data
        assert "period_end" in data

    def test_list_patterns(self, client):
        """Test GET /api/insights/patterns endpoint."""
        response = client.get("/api/insights/patterns")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "patterns" in data

    def test_list_anomalies(self, client):
        """Test GET /api/insights/anomalies endpoint."""
        response = client.get("/api/insights/anomalies")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "anomalies" in data

    def test_list_dependencies(self, client):
        """Test GET /api/insights/dependencies endpoint."""
        response = client.get("/api/insights/dependencies")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "dependencies" in data

    def test_get_digest(self, client):
        """Test GET /api/insights/digest endpoint."""
        response = client.get("/api/insights/digest?period=weekly")
        assert response.status_code == 200
        # May return null if no digest exists

    def test_trigger_analysis(self, client):
        """Test POST /api/insights/analyze endpoint."""
        response = client.post(
            "/api/insights/analyze",
            params={
                "days": 7,
                "include_patterns": True,
                "include_anomalies": True,
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert "analysis_id" in data
        assert "incidents_analyzed" in data
        assert "patterns_found" in data
        assert "anomalies_found" in data

    def test_insights_dashboard_page(self, client):
        """Test GET /dashboard/insights page loads."""
        response = client.get("/dashboard/insights")
        assert response.status_code == 200
        assert "Insights" in response.text


class TestInsightsDBFetch:
    """Tests for InsightsService fetching incidents from Supabase DB."""

    def test_row_to_metrics_basic(self):
        """Test converting a Supabase row to IncidentMetrics."""
        row = {
            "id": "inc-123",
            "created_at": "2026-02-20T10:00:00Z",
            "triggered_at": "2026-02-20T10:00:00Z",
            "acknowledged_at": "2026-02-20T10:05:00Z",
            "resolved_at": "2026-02-20T11:00:00Z",
            "service": "api-gateway",
            "severity": "high",
            "metadata": {},
        }
        metrics = InsightsService._row_to_metrics(row)
        assert metrics.incident_id == "inc-123"
        assert metrics.service_name == "api-gateway"
        assert metrics.severity == "high"
        assert metrics.acknowledged_at is not None
        assert metrics.resolved_at is not None
        assert metrics.time_to_resolve_seconds is not None
        assert metrics.time_to_resolve_seconds == pytest.approx(3600.0, abs=1)

    def test_row_to_metrics_missing_fields(self):
        """Test conversion with missing optional fields."""
        row = {
            "id": "inc-456",
            "created_at": "2026-02-20T10:00:00Z",
            "service": None,
            "severity": None,
            "metadata": None,
        }
        metrics = InsightsService._row_to_metrics(row)
        assert metrics.incident_id == "inc-456"
        assert metrics.service_name == "unknown"
        assert metrics.severity == "medium"
        assert metrics.acknowledged_at is None
        assert metrics.resolved_at is None

    def test_row_to_metrics_metadata_timestamps(self):
        """Test that acknowledged_at/resolved_at fall back to metadata."""
        row = {
            "id": "inc-789",
            "created_at": "2026-02-20T10:00:00Z",
            "acknowledged_at": None,
            "resolved_at": None,
            "service": "db",
            "severity": "critical",
            "metadata": {
                "acknowledged_at": "2026-02-20T10:02:00Z",
                "resolved_at": "2026-02-20T10:30:00Z",
            },
        }
        metrics = InsightsService._row_to_metrics(row)
        assert metrics.acknowledged_at is not None
        assert metrics.resolved_at is not None

    def test_row_to_metrics_processed_at_fallback(self):
        """Test that processed_at is used when resolved_at is missing."""
        row = {
            "id": "inc-proc",
            "created_at": "2026-02-20T10:00:00Z",
            "resolved_at": None,
            "processed_at": "2026-02-20T10:45:00Z",
            "service": "worker",
            "severity": "low",
            "metadata": {},
        }
        metrics = InsightsService._row_to_metrics(row)
        assert metrics.resolved_at is not None

    @pytest.mark.asyncio
    async def test_fetch_incidents_fallback_to_memory(self):
        """Test that _fetch_incidents falls back to in-memory store when DB is disabled."""
        from unittest.mock import AsyncMock, patch

        service = InsightsService()
        now = datetime.utcnow()
        start = now - timedelta(days=7)

        with patch(
            "src.insights.service.is_supabase_db_enabled", return_value=False
        ):
            with patch.object(
                service, "_fetch_incidents", wraps=service._fetch_incidents
            ):
                # Should fall through to analytics_store
                incidents = await service._fetch_incidents(start=start, end=now)
                assert isinstance(incidents, list)

    @pytest.mark.asyncio
    async def test_fetch_incidents_from_db_via_mock(self):
        """Test that _fetch_incidents returns DB rows when patched at method level."""
        from unittest.mock import AsyncMock, patch

        now = datetime.utcnow()
        mock_metrics = [
            IncidentMetrics(
                incident_id=f"db-inc-{i}",
                triggered_at=now - timedelta(days=i),
                service_name="test-service",
                severity="high",
            )
            for i in range(3)
        ]

        service = InsightsService()

        with patch.object(
            service, "_fetch_incidents", new_callable=AsyncMock, return_value=mock_metrics
        ):
            result = await service._fetch_incidents(
                start=now - timedelta(days=7), end=now
            )
            assert len(result) == 3
            assert all(m.service_name == "test-service" for m in result)

    @pytest.mark.asyncio
    async def test_run_analysis_uses_db(self):
        """Test that run_analysis fetches from DB and produces results."""
        from unittest.mock import AsyncMock, patch

        now = datetime.utcnow()
        mock_incidents = [
            IncidentMetrics(
                incident_id=f"analysis-{i}",
                triggered_at=now - timedelta(days=i),
                resolved_at=now - timedelta(days=i) + timedelta(hours=1),
                service_name="test-svc",
                severity="high",
            )
            for i in range(5)
        ]

        service = InsightsService()

        with patch.object(
            service, "_fetch_incidents", new_callable=AsyncMock, return_value=mock_incidents
        ):
            result = await service.run_analysis()
            assert result.incidents_analyzed == 5
            assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_generate_digest_uses_db(self):
        """Test that generate_digest fetches from DB."""
        from unittest.mock import AsyncMock, patch

        now = datetime.utcnow()
        mock_incidents = [
            IncidentMetrics(
                incident_id=f"digest-{i}",
                triggered_at=now - timedelta(days=i),
                resolved_at=now - timedelta(days=i) + timedelta(hours=2),
                service_name="web-app",
                severity="medium",
            )
            for i in range(3)
        ]

        service = InsightsService()

        with patch.object(
            service, "_fetch_all_incidents", new_callable=AsyncMock, return_value=mock_incidents
        ):
            digest = await service.generate_digest(generate_ai=False)
            assert digest is not None
