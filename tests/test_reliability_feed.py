"""Tests for reliability feed generator."""

from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.models import IncidentMetrics
from src.insights.models import ServiceHealthScore
from src.insights.reliability_feed import ReliabilityFeedGenerator


@pytest.fixture
def generator():
    return ReliabilityFeedGenerator()


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


@pytest.fixture
def diverse_incidents(now):
    """Incidents across services with various patterns."""
    incidents = []
    # Payments: many critical incidents (triggers lessons)
    for i in range(6):
        incidents.append(
            IncidentMetrics(
                incident_id=f"timeout-payments-{i}",
                triggered_at=now - timedelta(days=i * 2),
                resolved_at=now - timedelta(days=i * 2) + timedelta(hours=3),
                service_name="payments-api",
                severity="critical" if i < 2 else "high",
                status="resolved",
            )
        )
    # Auth: a few low incidents
    for i in range(2):
        incidents.append(
            IncidentMetrics(
                incident_id=f"auth-issue-{i}",
                triggered_at=now - timedelta(days=i * 7),
                resolved_at=now - timedelta(days=i * 7) + timedelta(minutes=10),
                service_name="auth-service",
                severity="low",
                status="resolved",
            )
        )
    return incidents


class TestExtractLessons:
    @pytest.mark.asyncio
    async def test_extracts_critical_lesson(self, generator, diverse_incidents):
        lessons = await generator.extract_lessons(diverse_incidents, "payments-api")
        assert len(lessons) > 0
        titles = [l.title for l in lessons]
        assert any("high-severity" in t.lower() or "critical" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_extracts_slow_mttr_lesson(self, generator, diverse_incidents):
        lessons = await generator.extract_lessons(diverse_incidents, "payments-api")
        assert any("slow" in l.title.lower() or "resolution" in l.title.lower() for l in lessons)

    @pytest.mark.asyncio
    async def test_extracts_frequency_lesson(self, generator, diverse_incidents):
        lessons = await generator.extract_lessons(diverse_incidents, "payments-api")
        assert any("volume" in l.title.lower() or "frequent" in l.title.lower() for l in lessons)

    @pytest.mark.asyncio
    async def test_no_lessons_for_healthy_service(self, generator):
        lessons = await generator.extract_lessons([], "clean-svc")
        assert len(lessons) == 0

    @pytest.mark.asyncio
    async def test_lessons_have_required_fields(self, generator, diverse_incidents):
        lessons = await generator.extract_lessons(diverse_incidents)
        for lesson in lessons:
            assert lesson.lesson_id
            assert lesson.service_name
            assert lesson.title
            assert lesson.category in ("prevention", "detection", "response", "recovery")


class TestShiftLeftReport:
    @pytest.mark.asyncio
    async def test_generates_report(self, generator, diverse_incidents):
        report = await generator.generate_shift_left_report(
            "payments-api", diverse_incidents, lookback_days=90
        )
        assert report.service_name == "payments-api"
        assert report.total_incidents > 0
        assert len(report.recommendations) > 0

    @pytest.mark.asyncio
    async def test_report_has_categories(self, generator, diverse_incidents):
        report = await generator.generate_shift_left_report(
            "payments-api", diverse_incidents, lookback_days=90
        )
        assert len(report.top_categories) > 0

    @pytest.mark.asyncio
    async def test_empty_service(self, generator):
        report = await generator.generate_shift_left_report(
            "nonexistent", [], lookback_days=30
        )
        assert report.total_incidents == 0
        assert len(report.recommendations) >= 1


class TestReliabilityDigest:
    @pytest.mark.asyncio
    async def test_generates_digest(self, generator, diverse_incidents, now):
        digest = await generator.generate_reliability_digest(
            "payments-api", diverse_incidents, lookback_days=90
        )
        assert digest.service_name == "payments-api"
        assert digest.summary is not None
        assert len(digest.lessons) > 0

    @pytest.mark.asyncio
    async def test_digest_with_health_score(self, generator, diverse_incidents, now):
        health = ServiceHealthScore(
            service_name="payments-api",
            overall_score=35.0,
            incident_frequency_score=20.0,
            severity_score=25.0,
            mttr_score=50.0,
            trend_score=40.0,
            recent_incidents=6,
            assessed_at=now,
        )
        digest = await generator.generate_reliability_digest(
            "payments-api",
            diverse_incidents,
            health_score=health,
            lookback_days=90,
        )
        assert digest.health_score is not None
        assert "35.0" in digest.summary

    @pytest.mark.asyncio
    async def test_digest_all_services(self, generator, diverse_incidents):
        digest = await generator.generate_reliability_digest(
            None, diverse_incidents, lookback_days=90
        )
        assert digest.service_name is None
        assert "all services" in digest.summary

    @pytest.mark.asyncio
    async def test_digest_includes_shift_left(self, generator, diverse_incidents):
        digest = await generator.generate_reliability_digest(
            "payments-api", diverse_incidents, lookback_days=90
        )
        assert digest.shift_left_report is not None
        assert digest.shift_left_report.service_name == "payments-api"
