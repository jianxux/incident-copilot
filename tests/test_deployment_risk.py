"""Tests for deployment risk scoring."""

from datetime import UTC, datetime, timedelta

import pytest

from src.analytics.models import IncidentMetrics
from src.insights.deployment_risk import DeploymentRiskScorer
from src.insights.models import DeploymentInfo


@pytest.fixture
def scorer():
    return DeploymentRiskScorer()


@pytest.fixture
def now():
    return datetime.now(UTC)


@pytest.fixture
def sample_incidents(now):
    incidents = []
    for i in range(6):
        incidents.append(
            IncidentMetrics(
                incident_id=f"inc-{i}",
                triggered_at=now - timedelta(days=i * 3),
                resolved_at=now - timedelta(days=i * 3) + timedelta(minutes=45),
                service_name="payments-api",
                severity="critical" if i == 0 else "medium",
                status="resolved",
            )
        )
    return incidents


class TestBlastRadius:
    @pytest.mark.asyncio
    async def test_single_service(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-1",
            service_name="payments-api",
            services_touched=["payments-api"],
            deploy_time=now.replace(hour=10),
            files_changed=2,
            lines_added=10,
            lines_removed=5,
        )
        score = await scorer.score_deployment(deploy, [])
        blast = next(f for f in score.factors if f.name == "blast_radius")
        assert blast.score == 20.0

    @pytest.mark.asyncio
    async def test_many_services(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-2",
            service_name="payments-api",
            services_touched=["payments-api", "auth", "orders", "billing", "gateway"],
            deploy_time=now.replace(hour=10),
        )
        score = await scorer.score_deployment(deploy, [])
        blast = next(f for f in score.factors if f.name == "blast_radius")
        assert blast.score == 100.0

    @pytest.mark.asyncio
    async def test_rollback_reduces_risk(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-3",
            service_name="payments-api",
            services_touched=["payments-api", "auth"],
            deploy_time=now.replace(hour=10),
            is_rollback=True,
        )
        score = await scorer.score_deployment(deploy, [])
        blast = next(f for f in score.factors if f.name == "blast_radius")
        assert blast.score == 20.0  # 40 - 20 rollback discount


class TestTiming:
    @pytest.mark.asyncio
    async def test_business_hours(self, scorer):
        deploy = DeploymentInfo(
            deployment_id="d-4",
            service_name="svc",
            deploy_time=datetime(2026, 2, 25, 10, 0, tzinfo=UTC),  # Wednesday 10am
        )
        score = await scorer.score_deployment(deploy, [])
        timing = next(f for f in score.factors if f.name == "timing")
        assert timing.score == 10.0

    @pytest.mark.asyncio
    async def test_friday_afternoon(self, scorer):
        deploy = DeploymentInfo(
            deployment_id="d-5",
            service_name="svc",
            deploy_time=datetime(2026, 2, 27, 16, 0, tzinfo=UTC),  # Friday 4pm
        )
        score = await scorer.score_deployment(deploy, [])
        timing = next(f for f in score.factors if f.name == "timing")
        assert timing.score == 80.0

    @pytest.mark.asyncio
    async def test_late_night(self, scorer):
        deploy = DeploymentInfo(
            deployment_id="d-6",
            service_name="svc",
            deploy_time=datetime(2026, 2, 25, 3, 0, tzinfo=UTC),  # Wednesday 3am
        )
        score = await scorer.score_deployment(deploy, [])
        timing = next(f for f in score.factors if f.name == "timing")
        assert timing.score == 60.0


class TestIncidentHistory:
    @pytest.mark.asyncio
    async def test_no_history(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-7",
            service_name="clean-svc",
            deploy_time=now.replace(hour=10),
        )
        score = await scorer.score_deployment(deploy, [])
        history = next(f for f in score.factors if f.name == "incident_history")
        assert history.score == 0.0

    @pytest.mark.asyncio
    async def test_with_critical_history(self, scorer, sample_incidents, now):
        deploy = DeploymentInfo(
            deployment_id="d-8",
            service_name="payments-api",
            services_touched=["payments-api"],
            deploy_time=now.replace(hour=10),
        )
        score = await scorer.score_deployment(deploy, sample_incidents)
        history = next(f for f in score.factors if f.name == "incident_history")
        assert history.score > 50  # Lots of incidents + critical


class TestChangeSize:
    @pytest.mark.asyncio
    async def test_small_change(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-9",
            service_name="svc",
            deploy_time=now.replace(hour=10),
            files_changed=1,
            lines_added=5,
            lines_removed=2,
        )
        score = await scorer.score_deployment(deploy, [])
        size = next(f for f in score.factors if f.name == "change_size")
        assert size.score < 10

    @pytest.mark.asyncio
    async def test_large_change(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-10",
            service_name="svc",
            deploy_time=now.replace(hour=10),
            files_changed=30,
            lines_added=2000,
            lines_removed=500,
        )
        score = await scorer.score_deployment(deploy, [])
        size = next(f for f in score.factors if f.name == "change_size")
        assert size.score > 50


class TestOverallRisk:
    @pytest.mark.asyncio
    async def test_low_risk_deploy(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-low",
            service_name="svc",
            services_touched=["svc"],
            deploy_time=now.replace(hour=10),
            files_changed=2,
            lines_added=20,
            lines_removed=10,
        )
        score = await scorer.score_deployment(deploy, [])
        assert score.risk_level == "low"
        assert score.overall_risk < 25

    @pytest.mark.asyncio
    async def test_high_risk_deploy(self, scorer, sample_incidents, now):
        deploy = DeploymentInfo(
            deployment_id="d-high",
            service_name="payments-api",
            services_touched=["payments-api", "auth", "orders", "billing"],
            deploy_time=datetime(2026, 2, 27, 23, 0, tzinfo=UTC),  # Friday 11pm
            files_changed=25,
            lines_added=1500,
            lines_removed=800,
        )
        score = await scorer.score_deployment(deploy, sample_incidents)
        assert score.risk_level in ("high", "critical")
        assert len(score.recommended_actions) > 0

    @pytest.mark.asyncio
    async def test_recommendations_present(self, scorer, now):
        deploy = DeploymentInfo(
            deployment_id="d-rec",
            service_name="svc",
            deploy_time=now.replace(hour=10),
        )
        score = await scorer.score_deployment(deploy, [])
        assert len(score.recommended_actions) >= 1
