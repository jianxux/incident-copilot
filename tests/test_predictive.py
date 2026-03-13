"""Tests for predictive alerting engine."""

from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.models import IncidentMetrics
from src.insights.models import MetricDataPoint, ServiceHealthScore
from src.insights.predictive import PredictiveEngine


@pytest.fixture
def engine():
    return PredictiveEngine()


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def sample_incidents(now):
    """Create incidents with varying severity and timing."""
    incidents = []
    for i in range(8):
        incidents.append(
            IncidentMetrics(
                incident_id=f"inc-{i}",
                triggered_at=now - timedelta(days=i * 3),
                resolved_at=now
                - timedelta(days=i * 3)
                + timedelta(minutes=30 + i * 10),
                service_name="payments-api",
                severity="high" if i < 3 else "medium",
                status="resolved",
            )
        )
    # Add a few for another service
    for i in range(2):
        incidents.append(
            IncidentMetrics(
                incident_id=f"other-{i}",
                triggered_at=now - timedelta(days=i * 5),
                resolved_at=now - timedelta(days=i * 5) + timedelta(minutes=15),
                service_name="auth-service",
                severity="low",
                status="resolved",
            )
        )
    return incidents


class TestLinearRegression:
    def test_perfect_positive_slope(self, engine):
        xs = [0.0, 1.0, 2.0, 3.0]
        ys = [0.0, 1.0, 2.0, 3.0]
        slope, intercept, r2 = engine._linear_regression(xs, ys)
        assert abs(slope - 1.0) < 0.001
        assert abs(intercept) < 0.001
        assert abs(r2 - 1.0) < 0.001

    def test_negative_slope(self, engine):
        xs = [0.0, 1.0, 2.0, 3.0]
        ys = [10.0, 7.0, 4.0, 1.0]
        slope, intercept, r2 = engine._linear_regression(xs, ys)
        assert slope < 0
        assert r2 > 0.99

    def test_flat_line(self, engine):
        xs = [0.0, 1.0, 2.0]
        ys = [5.0, 5.0, 5.0]
        slope, intercept, r2 = engine._linear_regression(xs, ys)
        assert abs(slope) < 0.001

    def test_single_point(self, engine):
        slope, intercept, r2 = engine._linear_regression([1.0], [5.0])
        assert slope == 0.0
        assert intercept == 5.0


class TestMetricTrends:
    @pytest.mark.asyncio
    async def test_increasing_trend(self, engine, now):
        metrics = [
            MetricDataPoint(
                timestamp=now - timedelta(hours=10 - i),
                value=50.0 + i * 5.0,
                metric_name="cpu_usage",
                service_name="payments-api",
            )
            for i in range(10)
        ]
        trends = await engine.analyze_metric_trends(metrics)
        assert len(trends) == 1
        assert trends[0].direction == "increasing"
        assert trends[0].slope > 0
        assert trends[0].predicted_value_1h > trends[0].current_value

    @pytest.mark.asyncio
    async def test_stable_trend(self, engine, now):
        metrics = [
            MetricDataPoint(
                timestamp=now - timedelta(hours=10 - i),
                value=50.0 + (i % 2) * 0.1,  # Tiny oscillation
                metric_name="memory",
                service_name="auth-service",
            )
            for i in range(10)
        ]
        trends = await engine.analyze_metric_trends(metrics)
        assert len(trends) == 1
        assert trends[0].direction == "stable"

    @pytest.mark.asyncio
    async def test_breach_threshold(self, engine, now):
        metrics = [
            MetricDataPoint(
                timestamp=now - timedelta(hours=5 - i),
                value=70.0 + i * 5.0,
                metric_name="cpu_usage",
                service_name="web",
            )
            for i in range(5)
        ]
        trends = await engine.analyze_metric_trends(metrics, breach_threshold=100.0)
        assert len(trends) == 1
        assert trends[0].estimated_breach_time is not None

    @pytest.mark.asyncio
    async def test_empty_metrics(self, engine):
        trends = await engine.analyze_metric_trends([])
        assert trends == []

    @pytest.mark.asyncio
    async def test_multiple_metric_groups(self, engine, now):
        metrics = []
        for name in ["cpu", "mem"]:
            for i in range(5):
                metrics.append(
                    MetricDataPoint(
                        timestamp=now - timedelta(hours=5 - i),
                        value=50.0 + i,
                        metric_name=name,
                        service_name="svc",
                    )
                )
        trends = await engine.analyze_metric_trends(metrics)
        assert len(trends) == 2


class TestServiceHealthScore:
    @pytest.mark.asyncio
    async def test_healthy_service(self, engine, now):
        # No incidents = perfect health
        score = await engine.calculate_service_health_score(
            "healthy-svc", [], lookback_days=30
        )
        assert score.overall_score >= 90.0  # Near-perfect with no incidents
        assert score.recent_incidents == 0

    @pytest.mark.asyncio
    async def test_unhealthy_service(self, engine, sample_incidents):
        score = await engine.calculate_service_health_score(
            "payments-api", sample_incidents, lookback_days=90
        )
        assert score.overall_score < 60  # Should be degraded
        assert score.recent_incidents > 0

    @pytest.mark.asyncio
    async def test_score_components_valid(self, engine, sample_incidents):
        score = await engine.calculate_service_health_score(
            "payments-api", sample_incidents, lookback_days=90
        )
        assert 0 <= score.incident_frequency_score <= 100
        assert 0 <= score.severity_score <= 100
        assert 0 <= score.mttr_score <= 100
        assert 0 <= score.trend_score <= 100


class TestEarlyWarnings:
    @pytest.mark.asyncio
    async def test_warning_on_low_health(self, engine, now):
        scores = {
            "bad-svc": ServiceHealthScore(
                service_name="bad-svc",
                overall_score=15.0,
                incident_frequency_score=0.0,
                severity_score=0.0,
                mttr_score=30.0,
                trend_score=20.0,
                recent_incidents=10,
                assessed_at=now,
            ),
        }
        warnings = await engine.generate_early_warnings([], scores)
        assert len(warnings) >= 1
        assert any(w.warning_type == "health_degradation" for w in warnings)

    @pytest.mark.asyncio
    async def test_no_warnings_healthy(self, engine, now):
        scores = {
            "good-svc": ServiceHealthScore(
                service_name="good-svc",
                overall_score=95.0,
                incident_frequency_score=100.0,
                severity_score=90.0,
                mttr_score=95.0,
                trend_score=90.0,
                recent_incidents=0,
                assessed_at=now,
            ),
        }
        warnings = await engine.generate_early_warnings([], scores)
        assert len(warnings) == 0

    @pytest.mark.asyncio
    async def test_warning_on_bad_trend(self, engine, now):
        scores = {
            "degrading-svc": ServiceHealthScore(
                service_name="degrading-svc",
                overall_score=45.0,
                incident_frequency_score=40.0,
                severity_score=50.0,
                mttr_score=60.0,
                trend_score=10.0,
                recent_incidents=5,
                assessed_at=now,
            ),
        }
        warnings = await engine.generate_early_warnings([], scores)
        assert any(w.warning_type == "pattern_acceleration" for w in warnings)
