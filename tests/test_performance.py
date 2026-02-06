"""Comprehensive tests for Team Performance Dashboard module."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.performance import (
    Leaderboard,
    LeaderboardEntry,
    LeaderboardType,
    PerformanceCalculator,
    PerformanceReport,
    PerformanceSummary,
    PerformanceTrend,
    ReportFormat,
    ReportGenerator,
    TeamMetrics,
    TrendAnalyzer,
    TrendDirection,
    performance_router,
)
from src.performance.leaderboard import LeaderboardGenerator
from src.performance.models import (
    BurnoutIndicator,
    IncidentVolume,
    OnCallStats,
    SLACompliance,
    TimeDistribution,
    WorkloadDistribution,
)


# --- Fixtures ---


@pytest.fixture
def sample_incidents() -> list[dict]:
    """Create sample incidents for testing."""
    base_time = datetime(2024, 1, 15, 10, 0, 0)
    return [
        {
            "id": "INC-001",
            "title": "High error rate on payments-api",
            "severity": "high",
            "service_name": "payments-api",
            "team_name": "payments-team",
            "triggered_at": base_time,
            "acknowledged_at": base_time + timedelta(minutes=5),
            "resolved_at": base_time + timedelta(minutes=45),
            "assigned_to": ["user-1"],
            "responder_id": "user-1",
        },
        {
            "id": "INC-002",
            "title": "Database connection timeout",
            "severity": "critical",
            "service_name": "orders-api",
            "team_name": "orders-team",
            "triggered_at": base_time + timedelta(hours=1),
            "acknowledged_at": base_time + timedelta(hours=1, minutes=3),
            "resolved_at": base_time + timedelta(hours=1, minutes=30),
            "assigned_to": ["user-2"],
            "responder_id": "user-2",
        },
        {
            "id": "INC-003",
            "title": "Slow response times",
            "severity": "medium",
            "service_name": "payments-api",
            "team_name": "payments-team",
            "triggered_at": base_time + timedelta(hours=2),
            "acknowledged_at": base_time + timedelta(hours=2, minutes=10),
            "resolved_at": base_time + timedelta(hours=3),
            "assigned_to": ["user-1", "user-3"],
            "responder_id": "user-1",
        },
        {
            "id": "INC-004",
            "title": "Authentication failures",
            "severity": "high",
            "service_name": "auth-api",
            "team_name": "platform-team",
            "triggered_at": base_time + timedelta(hours=5),
            "acknowledged_at": base_time + timedelta(hours=5, minutes=2),
            "resolved_at": base_time + timedelta(hours=5, minutes=20),
            "assigned_to": ["user-3"],
            "responder_id": "user-3",
        },
        {
            "id": "INC-005",
            "title": "Memory leak detected",
            "severity": "low",
            "service_name": "reports-api",
            "team_name": "analytics-team",
            "triggered_at": base_time + timedelta(hours=8),
            "acknowledged_at": base_time + timedelta(hours=8, minutes=30),
            "resolved_at": base_time + timedelta(hours=10),
            "assigned_to": ["user-4"],
            "responder_id": "user-4",
        },
    ]


@pytest.fixture
def sample_oncall_data() -> list[dict]:
    """Create sample on-call data for testing."""
    return [
        {
            "id": "user-1",
            "name": "Jane Doe",
            "email": "jane@example.com",
            "team_name": "payments-team",
            "oncall_hours": 168,
        },
        {
            "id": "user-2",
            "name": "John Smith",
            "email": "john@example.com",
            "team_name": "orders-team",
            "oncall_hours": 168,
        },
        {
            "id": "user-3",
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "team_name": "platform-team",
            "oncall_hours": 84,
        },
        {
            "id": "user-4",
            "name": "Bob Wilson",
            "email": "bob@example.com",
            "team_name": "analytics-team",
            "oncall_hours": 168,
        },
    ]


@pytest.fixture
def calculator() -> PerformanceCalculator:
    """Create a PerformanceCalculator instance."""
    return PerformanceCalculator()


@pytest.fixture
def trend_analyzer(calculator) -> TrendAnalyzer:
    """Create a TrendAnalyzer instance."""
    return TrendAnalyzer(calculator)


@pytest.fixture
def leaderboard_generator(calculator) -> LeaderboardGenerator:
    """Create a LeaderboardGenerator instance."""
    return LeaderboardGenerator(calculator)


@pytest.fixture
def report_generator(calculator, trend_analyzer, leaderboard_generator) -> ReportGenerator:
    """Create a ReportGenerator instance."""
    return ReportGenerator(calculator, trend_analyzer, leaderboard_generator)


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(performance_router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


# --- Calculator Tests ---


class TestPerformanceCalculator:
    """Tests for PerformanceCalculator."""

    def test_calculate_team_metrics(self, calculator, sample_incidents):
        """Test calculating team metrics."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        metrics = calculator.calculate_team_metrics(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(metrics, TeamMetrics)
        assert metrics.total_incidents == 5
        assert metrics.mttr_minutes is not None
        assert metrics.mtta_minutes is not None
        assert metrics.resolved_incidents == 5

    def test_calculate_team_metrics_with_filter(self, calculator, sample_incidents):
        """Test team metrics with service filter."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        metrics = calculator.calculate_team_metrics(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
            service_name="payments-api",
        )

        assert metrics.total_incidents == 2

    def test_calculate_team_metrics_severity_counts(self, calculator, sample_incidents):
        """Test severity count breakdown."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        metrics = calculator.calculate_team_metrics(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert metrics.critical_count == 1
        assert metrics.high_count == 2
        assert metrics.medium_count == 1
        assert metrics.low_count == 1

    def test_calculate_oncall_stats(self, calculator, sample_incidents):
        """Test calculating on-call stats for a responder."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        stats = calculator.calculate_oncall_stats(
            incidents=sample_incidents,
            responder_id="user-1",
            responder_name="Jane Doe",
            period_start=period_start,
            period_end=period_end,
            oncall_hours=168,
        )

        assert isinstance(stats, OnCallStats)
        assert stats.responder_name == "Jane Doe"
        assert stats.total_pages == 2  # user-1 is assigned to 2 incidents
        assert stats.avg_ack_time_minutes is not None

    def test_calculate_incident_volume(self, calculator, sample_incidents):
        """Test calculating incident volume."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        volume = calculator.calculate_incident_volume(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(volume, IncidentVolume)
        assert volume.total_count == 5
        assert len(volume.by_severity) > 0
        assert len(volume.by_service) > 0

    def test_calculate_time_distribution(self, calculator, sample_incidents):
        """Test calculating time distribution."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        distribution = calculator.calculate_time_distribution(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(distribution, TimeDistribution)
        assert distribution.busiest_hour is not None
        assert distribution.business_hours_count + distribution.off_hours_count + distribution.weekend_count >= 0

    def test_calculate_workload_distribution(self, calculator, sample_incidents):
        """Test calculating workload distribution."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        # First build oncall stats
        stats = []
        for user_id in ["user-1", "user-2", "user-3", "user-4"]:
            stat = calculator.calculate_oncall_stats(
                incidents=sample_incidents,
                responder_id=user_id,
                responder_name=f"User {user_id}",
                period_start=period_start,
                period_end=period_end,
            )
            if stat.total_pages > 0:
                stats.append(stat)

        distribution = calculator.calculate_workload_distribution(
            oncall_stats=stats,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(distribution, WorkloadDistribution)
        assert distribution.total_responders > 0
        assert distribution.gini_coefficient is not None

    def test_calculate_sla_compliance(self, calculator, sample_incidents):
        """Test calculating SLA compliance."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        compliance = calculator.calculate_sla_compliance(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(compliance, SLACompliance)
        assert compliance.total_incidents == 5
        assert 0 <= compliance.compliance_percent <= 100

    def test_calculate_burnout_indicator(self, calculator, sample_incidents):
        """Test calculating burnout indicator."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        stats = calculator.calculate_oncall_stats(
            incidents=sample_incidents,
            responder_id="user-1",
            responder_name="Jane Doe",
            period_start=period_start,
            period_end=period_end,
            oncall_hours=168,
        )

        indicator = calculator.calculate_burnout_indicator(stats)

        assert isinstance(indicator, BurnoutIndicator)
        assert indicator.responder_name == "Jane Doe"
        assert indicator.risk_level in ("low", "medium", "high", "critical")
        assert 0 <= indicator.risk_score <= 100


# --- Trend Analyzer Tests ---


class TestTrendAnalyzer:
    """Tests for TrendAnalyzer."""

    def test_calculate_mttr_trend(self, trend_analyzer, sample_incidents):
        """Test calculating MTTR trend."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        trend = trend_analyzer.calculate_mttr_trend(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(trend, PerformanceTrend)
        assert trend.metric_name == "mttr"
        assert trend.direction in TrendDirection

    def test_calculate_mtta_trend(self, trend_analyzer, sample_incidents):
        """Test calculating MTTA trend."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        trend = trend_analyzer.calculate_mtta_trend(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(trend, PerformanceTrend)
        assert trend.metric_name == "mtta"

    def test_calculate_incident_count_trend(self, trend_analyzer, sample_incidents):
        """Test calculating incident count trend."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        trend = trend_analyzer.calculate_incident_count_trend(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(trend, PerformanceTrend)
        assert trend.metric_name == "incident_count"
        assert trend.current_value == 5

    def test_calculate_all_trends(self, trend_analyzer, sample_incidents):
        """Test calculating all trends."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        trends = trend_analyzer.calculate_all_trends(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert len(trends) == 4  # mttr, mtta, incident_count, sla_compliance
        metric_names = {t.metric_name for t in trends}
        assert "mttr" in metric_names
        assert "mtta" in metric_names
        assert "incident_count" in metric_names
        assert "sla_compliance" in metric_names

    def test_week_over_week(self, trend_analyzer, sample_incidents):
        """Test week-over-week trends."""
        trends = trend_analyzer.week_over_week(
            incidents=sample_incidents,
            reference_date=datetime(2024, 1, 15),
        )

        assert len(trends) == 4

    def test_month_over_month(self, trend_analyzer, sample_incidents):
        """Test month-over-month trends."""
        trends = trend_analyzer.month_over_month(
            incidents=sample_incidents,
            reference_date=datetime(2024, 1, 15),
        )

        assert len(trends) == 4

    def test_detect_anomalies(self, trend_analyzer, sample_incidents):
        """Test anomaly detection."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        anomalies = trend_analyzer.detect_anomalies(
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
        )

        # May or may not find anomalies depending on data
        assert isinstance(anomalies, list)


# --- Leaderboard Tests ---


class TestLeaderboardGenerator:
    """Tests for LeaderboardGenerator."""

    def test_generate_top_responders(self, leaderboard_generator, calculator, sample_incidents):
        """Test generating top responders leaderboard."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        # Build oncall stats
        stats = []
        for user_id, name in [("user-1", "Jane"), ("user-2", "John"), ("user-3", "Alice")]:
            stat = calculator.calculate_oncall_stats(
                incidents=sample_incidents,
                responder_id=user_id,
                responder_name=name,
                period_start=period_start,
                period_end=period_end,
            )
            if stat.total_pages > 0:
                stats.append(stat)

        leaderboard = leaderboard_generator.generate_top_responders(
            oncall_stats=stats,
            period_start=period_start,
            period_end=period_end,
            limit=10,
        )

        assert isinstance(leaderboard, Leaderboard)
        assert leaderboard.leaderboard_type == LeaderboardType.TOP_RESPONDERS
        assert len(leaderboard.entries) > 0
        assert all(isinstance(e, LeaderboardEntry) for e in leaderboard.entries)

    def test_generate_fastest_response(self, leaderboard_generator, calculator, sample_incidents):
        """Test generating fastest response leaderboard."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        stats = []
        for user_id, name in [("user-1", "Jane"), ("user-2", "John"), ("user-3", "Alice")]:
            stat = calculator.calculate_oncall_stats(
                incidents=sample_incidents,
                responder_id=user_id,
                responder_name=name,
                period_start=period_start,
                period_end=period_end,
            )
            if stat.total_pages > 0:
                stats.append(stat)

        leaderboard = leaderboard_generator.generate_fastest_response(
            oncall_stats=stats,
            period_start=period_start,
            period_end=period_end,
            limit=10,
        )

        assert leaderboard.leaderboard_type == LeaderboardType.FASTEST_RESPONSE
        # Entries should be sorted by ack time (ascending)
        if len(leaderboard.entries) > 1:
            for i in range(len(leaderboard.entries) - 1):
                assert leaderboard.entries[i].primary_value <= leaderboard.entries[i + 1].primary_value

    def test_generate_most_resolved(self, leaderboard_generator, calculator, sample_incidents):
        """Test generating most resolved leaderboard."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        stats = []
        for user_id, name in [("user-1", "Jane"), ("user-2", "John"), ("user-3", "Alice")]:
            stat = calculator.calculate_oncall_stats(
                incidents=sample_incidents,
                responder_id=user_id,
                responder_name=name,
                period_start=period_start,
                period_end=period_end,
            )
            if stat.total_pages > 0:
                stats.append(stat)

        leaderboard = leaderboard_generator.generate_most_resolved(
            oncall_stats=stats,
            incidents=sample_incidents,
            period_start=period_start,
            period_end=period_end,
            limit=10,
        )

        assert leaderboard.leaderboard_type == LeaderboardType.MOST_RESOLVED

    def test_generate_team_rankings(self, leaderboard_generator, calculator, sample_incidents):
        """Test generating team rankings."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        stats = []
        teams = [
            ("user-1", "Jane", "payments-team"),
            ("user-2", "John", "orders-team"),
            ("user-3", "Alice", "platform-team"),
        ]
        for user_id, name, team in teams:
            stat = calculator.calculate_oncall_stats(
                incidents=sample_incidents,
                responder_id=user_id,
                responder_name=name,
                period_start=period_start,
                period_end=period_end,
                team_name=team,
            )
            if stat.total_pages > 0:
                stats.append(stat)

        leaderboard = leaderboard_generator.generate_team_rankings(
            oncall_stats=stats,
            period_start=period_start,
            period_end=period_end,
            limit=10,
        )

        assert leaderboard.leaderboard_type == LeaderboardType.TEAM_RANKINGS

    def test_badges_calculation(self, leaderboard_generator, calculator, sample_incidents):
        """Test that badges are calculated correctly."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        stat = calculator.calculate_oncall_stats(
            incidents=sample_incidents,
            responder_id="user-1",
            responder_name="Jane",
            period_start=period_start,
            period_end=period_end,
        )

        badges = leaderboard_generator._calculate_badges(stat)
        assert isinstance(badges, list)


# --- Report Generator Tests ---


class TestReportGenerator:
    """Tests for ReportGenerator."""

    @pytest.mark.asyncio
    async def test_generate_report(self, report_generator, sample_incidents, sample_oncall_data):
        """Test generating a performance report."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        report = await report_generator.generate_report(
            incidents=sample_incidents,
            oncall_data=sample_oncall_data,
            period_start=period_start,
            period_end=period_end,
        )

        assert isinstance(report, PerformanceReport)
        assert report.team_metrics is not None
        assert isinstance(report.summary, PerformanceSummary)
        assert len(report.trends) > 0

    @pytest.mark.asyncio
    async def test_generate_weekly_digest(self, report_generator, sample_incidents, sample_oncall_data):
        """Test generating a weekly digest."""
        report = await report_generator.generate_weekly_digest(
            incidents=sample_incidents,
            oncall_data=sample_oncall_data,
            reference_date=datetime(2024, 1, 15),
        )

        assert isinstance(report, PerformanceReport)
        # Verify it's a week-long period
        duration = report.period_end - report.period_start
        assert duration.days == 7

    @pytest.mark.asyncio
    async def test_export_markdown(self, report_generator, sample_incidents, sample_oncall_data):
        """Test exporting report as Markdown."""
        report = await report_generator.generate_weekly_digest(
            incidents=sample_incidents,
            oncall_data=sample_oncall_data,
        )

        content = report_generator.export_report(report, ReportFormat.MARKDOWN)

        assert "# Performance Report" in content
        assert "## Executive Summary" in content
        assert "MTTR" in content

    @pytest.mark.asyncio
    async def test_export_json(self, report_generator, sample_incidents, sample_oncall_data):
        """Test exporting report as JSON."""
        import json

        report = await report_generator.generate_weekly_digest(
            incidents=sample_incidents,
            oncall_data=sample_oncall_data,
        )

        content = report_generator.export_report(report, ReportFormat.JSON)

        data = json.loads(content)
        assert "report_id" in data
        assert "summary" in data
        assert "team_metrics" in data

    @pytest.mark.asyncio
    async def test_export_slack(self, report_generator, sample_incidents, sample_oncall_data):
        """Test exporting report as Slack Block Kit."""
        import json

        report = await report_generator.generate_weekly_digest(
            incidents=sample_incidents,
            oncall_data=sample_oncall_data,
        )

        content = report_generator.export_report(report, ReportFormat.SLACK)

        data = json.loads(content)
        assert "blocks" in data
        assert len(data["blocks"]) > 0

    @pytest.mark.asyncio
    async def test_export_html(self, report_generator, sample_incidents, sample_oncall_data):
        """Test exporting report as HTML."""
        report = await report_generator.generate_weekly_digest(
            incidents=sample_incidents,
            oncall_data=sample_oncall_data,
        )

        content = report_generator.export_report(report, ReportFormat.HTML)

        assert "<!DOCTYPE html>" in content
        assert "Performance Report" in content


# --- Model Tests ---


class TestModels:
    """Tests for performance models."""

    def test_team_metrics_model(self):
        """Test TeamMetrics model."""
        now = datetime.utcnow()
        metrics = TeamMetrics(
            team_name="test-team",
            period_start=now - timedelta(days=7),
            period_end=now,
            mttr_minutes=45.5,
            mtta_minutes=5.0,
            total_incidents=10,
        )

        assert metrics.team_name == "test-team"
        assert metrics.mttr_minutes == 45.5
        assert metrics.total_incidents == 10

    def test_oncall_stats_model(self):
        """Test OnCallStats model."""
        now = datetime.utcnow()
        stats = OnCallStats(
            responder_id="user-1",
            responder_name="Jane Doe",
            period_start=now - timedelta(days=7),
            period_end=now,
            total_pages=25,
            off_hours_pages=5,
        )

        assert stats.responder_name == "Jane Doe"
        assert stats.total_pages == 25

    def test_performance_trend_model(self):
        """Test PerformanceTrend model."""
        now = datetime.utcnow()
        trend = PerformanceTrend(
            metric_name="mttr",
            period_start=now - timedelta(days=7),
            period_end=now,
            comparison_period_start=now - timedelta(days=14),
            comparison_period_end=now - timedelta(days=7),
            current_value=30.0,
            previous_value=40.0,
            change_absolute=-10.0,
            change_percent=-25.0,
            direction=TrendDirection.IMPROVING,
            is_improvement=True,
        )

        assert trend.direction == TrendDirection.IMPROVING
        assert trend.is_improvement is True
        assert trend.change_percent == -25.0

    def test_burnout_indicator_model(self):
        """Test BurnoutIndicator model."""
        now = datetime.utcnow()
        indicator = BurnoutIndicator(
            responder_id="user-1",
            responder_name="Jane Doe",
            period_start=now - timedelta(days=7),
            period_end=now,
            total_pages=75,
            off_hours_pages=20,
            risk_score=65.0,
            risk_level="high",
            recommendations=["Reduce on-call load"],
        )

        assert indicator.risk_level == "high"
        assert len(indicator.recommendations) == 1


# --- API Route Tests ---


class TestPerformanceRoutes:
    """Tests for performance API routes."""

    def test_add_incidents(self, client):
        """Test POST /api/performance/incidents."""
        incidents = [
            {
                "id": "INC-001",
                "title": "Test incident",
                "severity": "high",
                "service_name": "test-service",
                "triggered_at": "2024-01-15T10:00:00Z",
                "resolved_at": "2024-01-15T11:00:00Z",
            }
        ]

        response = client.post("/api/performance/incidents", json=incidents)
        assert response.status_code == 200
        assert "Added 1 incidents" in response.json()["message"]

    def test_add_oncall_data(self, client):
        """Test POST /api/performance/oncall."""
        oncall_data = [
            {
                "id": "user-1",
                "name": "Jane Doe",
                "team_name": "test-team",
            }
        ]

        response = client.post("/api/performance/oncall", json=oncall_data)
        assert response.status_code == 200
        assert "Added 1 on-call entries" in response.json()["message"]

    def test_get_metrics(self, client, sample_incidents):
        """Test GET /api/performance/metrics."""
        # First add some incidents
        client.post("/api/performance/incidents", json=sample_incidents)

        response = client.get("/api/performance/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data

    def test_get_trends(self, client, sample_incidents):
        """Test GET /api/performance/trends."""
        client.post("/api/performance/incidents", json=sample_incidents)

        response = client.get("/api/performance/trends")
        assert response.status_code == 200
        data = response.json()
        assert "trends" in data

    def test_get_leaderboard(self, client, sample_incidents, sample_oncall_data):
        """Test GET /api/performance/leaderboard/{type}."""
        client.post("/api/performance/incidents", json=sample_incidents)
        client.post("/api/performance/oncall", json=sample_oncall_data)

        response = client.get("/api/performance/leaderboard/top_responders")
        assert response.status_code == 200
        data = response.json()
        assert "leaderboard" in data

    def test_get_oncall_stats(self, client, sample_incidents, sample_oncall_data):
        """Test GET /api/performance/oncall-stats."""
        client.post("/api/performance/incidents", json=sample_incidents)
        client.post("/api/performance/oncall", json=sample_oncall_data)

        response = client.get("/api/performance/oncall-stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_get_burnout_indicators(self, client, sample_incidents, sample_oncall_data):
        """Test GET /api/performance/burnout."""
        client.post("/api/performance/incidents", json=sample_incidents)
        client.post("/api/performance/oncall", json=sample_oncall_data)

        response = client.get("/api/performance/burnout")
        assert response.status_code == 200
        data = response.json()
        assert "indicators" in data
        assert "high_risk_count" in data

    def test_get_volume(self, client, sample_incidents):
        """Test GET /api/performance/volume."""
        client.post("/api/performance/incidents", json=sample_incidents)

        response = client.get("/api/performance/volume")
        assert response.status_code == 200
        data = response.json()
        assert "volume" in data
        assert "time_distribution" in data

    def test_get_sla_compliance(self, client, sample_incidents):
        """Test GET /api/performance/sla."""
        client.post("/api/performance/incidents", json=sample_incidents)

        response = client.get("/api/performance/sla")
        assert response.status_code == 200
        data = response.json()
        assert "compliance" in data

    def test_get_workload_distribution(self, client, sample_incidents, sample_oncall_data):
        """Test GET /api/performance/workload."""
        client.post("/api/performance/incidents", json=sample_incidents)
        client.post("/api/performance/oncall", json=sample_oncall_data)

        response = client.get("/api/performance/workload")
        assert response.status_code == 200
        data = response.json()
        assert "distribution" in data

    def test_generate_report(self, client, sample_incidents, sample_oncall_data):
        """Test POST /api/performance/reports/generate."""
        client.post("/api/performance/incidents", json=sample_incidents)
        client.post("/api/performance/oncall", json=sample_oncall_data)

        response = client.post(
            "/api/performance/reports/generate",
            json={
                "start_date": "2024-01-15T00:00:00Z",
                "end_date": "2024-01-16T00:00:00Z",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "report" in data

    def test_get_weekly_digest(self, client, sample_incidents, sample_oncall_data):
        """Test GET /api/performance/reports/weekly."""
        client.post("/api/performance/incidents", json=sample_incidents)
        client.post("/api/performance/oncall", json=sample_oncall_data)

        response = client.get("/api/performance/reports/weekly")
        assert response.status_code == 200
        data = response.json()
        assert "report" in data

    def test_export_report(self, client, sample_incidents, sample_oncall_data):
        """Test POST /api/performance/reports/{id}/export."""
        client.post("/api/performance/incidents", json=sample_incidents)
        client.post("/api/performance/oncall", json=sample_oncall_data)

        response = client.post(
            "/api/performance/reports/test-id/export?format=markdown"
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "# Performance Report" in data["content"]

    def test_clear_data(self, client):
        """Test DELETE /api/performance/data."""
        # Add some data first
        client.post("/api/performance/incidents", json=[{"id": "test"}])

        response = client.delete("/api/performance/data")
        assert response.status_code == 200
        assert "cleared" in response.json()["message"]


# --- Edge Cases ---


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_incidents(self, calculator):
        """Test with no incidents."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        metrics = calculator.calculate_team_metrics(
            incidents=[],
            period_start=period_start,
            period_end=period_end,
        )

        assert metrics.total_incidents == 0
        assert metrics.mttr_minutes is None

    def test_incident_without_resolution(self, calculator):
        """Test incident without resolution time."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        incidents = [
            {
                "id": "INC-001",
                "triggered_at": datetime(2024, 1, 15, 10, 0, 0),
                "acknowledged_at": datetime(2024, 1, 15, 10, 5, 0),
                # No resolved_at
            }
        ]

        metrics = calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
        )

        assert metrics.total_incidents == 1
        assert metrics.mttr_minutes is None  # Can't calculate without resolution

    def test_invalid_datetime_format(self, calculator):
        """Test with invalid datetime format."""
        period_start = datetime(2024, 1, 15, 0, 0, 0)
        period_end = datetime(2024, 1, 16, 0, 0, 0)

        incidents = [
            {
                "id": "INC-001",
                "triggered_at": "invalid-date",
            }
        ]

        metrics = calculator.calculate_team_metrics(
            incidents=incidents,
            period_start=period_start,
            period_end=period_end,
        )

        # Should handle gracefully
        assert metrics.total_incidents == 0

    def test_gini_coefficient_equal_distribution(self, calculator):
        """Test Gini coefficient with equal distribution."""
        values = [10, 10, 10, 10]
        gini = calculator._calculate_gini(values)
        # Equal distribution should have Gini close to 0
        assert gini < 0.1

    def test_gini_coefficient_unequal_distribution(self, calculator):
        """Test Gini coefficient with unequal distribution."""
        values = [100, 1, 1, 1]
        gini = calculator._calculate_gini(values)
        # Unequal distribution should have Gini closer to 1
        assert gini > 0.5
