"""Tests for SLA tracking module."""

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.sla.models import (
    BusinessHours,
    DEFAULT_SLA_TARGETS,
    EscalationLevel,
    SLABreach,
    SLAIncidentStatus,
    SLAMetrics,
    SLAPolicy,
    SLASeverity,
    SLAStatus,
    SLATarget,
    SLATimer,
    SLAType,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_policy() -> SLAPolicy:
    """Create a sample SLA policy for testing."""
    return SLAPolicy(
        id="policy-1",
        name="Standard SLA",
        description="Default SLA policy for all services",
        organization_id="org-123",
        targets=DEFAULT_SLA_TARGETS.copy(),
        business_hours=BusinessHours(enabled=False),
        escalation_enabled=True,
        escalation_contacts=["ops@example.com", "#incidents"],
    )


@pytest.fixture
def business_hours_policy() -> SLAPolicy:
    """Policy with business hours enabled."""
    return SLAPolicy(
        id="policy-bh",
        name="Business Hours SLA",
        organization_id="org-123",
        targets=[
            SLATarget(
                severity=SLASeverity.P1, sla_type=SLAType.RESPONSE, target_minutes=15
            ),
            SLATarget(
                severity=SLASeverity.P1, sla_type=SLAType.RESOLUTION, target_minutes=240
            ),
        ],
        business_hours=BusinessHours(
            enabled=True,
            timezone="America/New_York",
            start_time=time(9, 0),
            end_time=time(17, 0),
            working_days=[0, 1, 2, 3, 4],  # Mon-Fri
        ),
    )


class TestSLATarget:
    """Tests for SLATarget model."""

    def test_target_creation(self):
        """Test creating an SLA target."""
        target = SLATarget(
            severity=SLASeverity.P1,
            sla_type=SLAType.RESPONSE,
            target_minutes=15,
        )
        assert target.severity == SLASeverity.P1
        assert target.sla_type == SLAType.RESPONSE
        assert target.target_minutes == 15
        assert target.warning_threshold_percent == 75

    def test_warning_minutes_calculation(self):
        """Test warning threshold calculation."""
        target = SLATarget(
            severity=SLASeverity.P2,
            sla_type=SLAType.RESOLUTION,
            target_minutes=60,
            warning_threshold_percent=80,
        )
        assert target.warning_minutes == 48.0

    def test_invalid_target_minutes(self):
        """Test that zero or negative target minutes are rejected."""
        with pytest.raises(ValueError):
            SLATarget(
                severity=SLASeverity.P1,
                sla_type=SLAType.RESPONSE,
                target_minutes=0,
            )


class TestBusinessHours:
    """Tests for BusinessHours model."""

    def test_default_business_hours(self):
        """Test default business hours configuration."""
        bh = BusinessHours()
        assert not bh.enabled
        assert bh.timezone == "UTC"
        assert bh.start_time == time(9, 0)
        assert bh.end_time == time(17, 0)
        assert bh.working_days == [0, 1, 2, 3, 4]

    def test_valid_working_days(self):
        """Test valid working days validation."""
        bh = BusinessHours(working_days=[0, 1, 2])
        assert bh.working_days == [0, 1, 2]

    def test_invalid_working_days(self):
        """Test invalid working days are rejected."""
        with pytest.raises(ValueError):
            BusinessHours(working_days=[0, 7])  # 7 is invalid

    def test_invalid_holiday_format(self):
        """Test invalid holiday date format is rejected."""
        with pytest.raises(ValueError):
            BusinessHours(holidays=["2024-13-01"])  # Invalid month

    def test_valid_holidays(self):
        """Test valid holidays are accepted."""
        bh = BusinessHours(holidays=["2024-12-25", "2024-01-01"])
        assert len(bh.holidays) == 2


class TestSLAPolicy:
    """Tests for SLAPolicy model."""

    def test_policy_creation(self, sample_policy):
        """Test creating an SLA policy."""
        assert sample_policy.id == "policy-1"
        assert sample_policy.name == "Standard SLA"
        assert len(sample_policy.targets) == 8
        assert sample_policy.is_active

    def test_get_target(self, sample_policy):
        """Test getting a specific target from policy."""
        target = sample_policy.get_target(SLASeverity.P1, SLAType.RESPONSE)
        assert target is not None
        assert target.target_minutes == 15

    def test_get_nonexistent_target(self, sample_policy):
        """Test getting a nonexistent target returns None."""
        # Remove P1 response target
        sample_policy.targets = [
            t
            for t in sample_policy.targets
            if not (t.severity == SLASeverity.P1 and t.sla_type == SLAType.RESPONSE)
        ]
        target = sample_policy.get_target(SLASeverity.P1, SLAType.RESPONSE)
        assert target is None

    def test_duplicate_targets_rejected(self):
        """Test that duplicate severity+type combinations are rejected."""
        with pytest.raises(ValueError, match="Duplicate target"):
            SLAPolicy(
                id="policy-dup",
                name="Duplicate Test",
                organization_id="org-123",
                targets=[
                    SLATarget(
                        severity=SLASeverity.P1,
                        sla_type=SLAType.RESPONSE,
                        target_minutes=15,
                    ),
                    SLATarget(
                        severity=SLASeverity.P1,
                        sla_type=SLAType.RESPONSE,
                        target_minutes=30,
                    ),
                ],
            )


class TestSLATimer:
    """Tests for SLATimer model."""

    def test_timer_creation(self):
        """Test creating an SLA timer."""
        timer = SLATimer(
            incident_id="inc-1",
            policy_id="policy-1",
            severity=SLASeverity.P1,
            sla_type=SLAType.RESPONSE,
            started_at=datetime.utcnow(),
            target_minutes=15,
        )
        assert timer.status == SLAStatus.ON_TRACK
        assert timer.elapsed_minutes == 0.0
        assert not timer.paused

    def test_remaining_minutes(self):
        """Test remaining time calculation."""
        timer = SLATimer(
            incident_id="inc-1",
            policy_id="policy-1",
            severity=SLASeverity.P1,
            sla_type=SLAType.RESPONSE,
            started_at=datetime.utcnow(),
            target_minutes=15,
            elapsed_minutes=5.0,
        )
        assert timer.remaining_minutes == 10.0

    def test_percent_elapsed(self):
        """Test percentage elapsed calculation."""
        timer = SLATimer(
            incident_id="inc-1",
            policy_id="policy-1",
            severity=SLASeverity.P1,
            sla_type=SLAType.RESPONSE,
            started_at=datetime.utcnow(),
            target_minutes=100,
            elapsed_minutes=25.0,
        )
        assert timer.percent_elapsed == 25.0

    def test_is_breached(self):
        """Test breach detection."""
        timer = SLATimer(
            incident_id="inc-1",
            policy_id="policy-1",
            severity=SLASeverity.P1,
            sla_type=SLAType.RESPONSE,
            started_at=datetime.utcnow(),
            target_minutes=15,
            elapsed_minutes=20.0,
        )
        assert timer.is_breached


class TestSLABreach:
    """Tests for SLABreach model."""

    def test_breach_creation(self):
        """Test creating an SLA breach."""
        breach = SLABreach(
            id="breach-1",
            incident_id="inc-1",
            policy_id="policy-1",
            severity=SLASeverity.P1,
            sla_type=SLAType.RESPONSE,
            target_minutes=15,
            actual_minutes=20.0,
            breach_amount_minutes=5.0,
            breach_percent=33.3,
            breached_at=datetime.utcnow(),
        )
        assert breach.escalation_level == EscalationLevel.BREACH
        assert not breach.is_resolved

    def test_breach_resolved(self):
        """Test breach resolution status."""
        breach = SLABreach(
            id="breach-2",
            incident_id="inc-2",
            policy_id="policy-1",
            severity=SLASeverity.P2,
            sla_type=SLAType.RESOLUTION,
            target_minutes=60,
            actual_minutes=90.0,
            breach_amount_minutes=30.0,
            breach_percent=50.0,
            breached_at=datetime.utcnow() - timedelta(hours=1),
            resolved_at=datetime.utcnow(),
        )
        assert breach.is_resolved


class TestSLAIncidentStatus:
    """Tests for SLAIncidentStatus model."""

    def test_worst_status_breached(self):
        """Test worst status calculation when breached."""
        status = SLAIncidentStatus(
            incident_id="inc-1",
            severity=SLASeverity.P1,
            policy_id="policy-1",
            policy_name="Standard",
            response_timer=SLATimer(
                incident_id="inc-1",
                policy_id="policy-1",
                severity=SLASeverity.P1,
                sla_type=SLAType.RESPONSE,
                started_at=datetime.utcnow(),
                target_minutes=15,
                status=SLAStatus.ON_TRACK,
            ),
            resolution_timer=SLATimer(
                incident_id="inc-1",
                policy_id="policy-1",
                severity=SLASeverity.P1,
                sla_type=SLAType.RESOLUTION,
                started_at=datetime.utcnow(),
                target_minutes=240,
                status=SLAStatus.BREACHED,
            ),
        )
        assert status.worst_status == SLAStatus.BREACHED

    def test_worst_status_at_risk(self):
        """Test worst status when at risk."""
        status = SLAIncidentStatus(
            incident_id="inc-1",
            severity=SLASeverity.P1,
            policy_id="policy-1",
            policy_name="Standard",
            response_timer=SLATimer(
                incident_id="inc-1",
                policy_id="policy-1",
                severity=SLASeverity.P1,
                sla_type=SLAType.RESPONSE,
                started_at=datetime.utcnow(),
                target_minutes=15,
                status=SLAStatus.AT_RISK,
            ),
        )
        assert status.worst_status == SLAStatus.AT_RISK


class TestSLAMetrics:
    """Tests for SLAMetrics model."""

    def test_calculate_compliance(self):
        """Test compliance percentage calculation."""
        metrics = SLAMetrics(
            organization_id="org-123",
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            total_incidents=20,
            response_sla_met=18,
            response_sla_breached=2,
            resolution_sla_met=16,
            resolution_sla_breached=4,
        )
        metrics.calculate_compliance()

        assert metrics.response_compliance_percent == 90.0
        assert metrics.resolution_compliance_percent == 80.0
        assert metrics.overall_compliance_percent == 85.0

    def test_calculate_compliance_no_incidents(self):
        """Test compliance calculation with no incidents."""
        metrics = SLAMetrics(
            organization_id="org-123",
            period_start=datetime.utcnow() - timedelta(days=7),
            period_end=datetime.utcnow(),
            total_incidents=0,
        )
        metrics.calculate_compliance()

        assert metrics.response_compliance_percent == 0.0
        assert metrics.resolution_compliance_percent == 0.0
        assert metrics.overall_compliance_percent == 0.0


class TestSLAAPI:
    """Tests for SLA API endpoints."""

    def test_list_policies(self, client):
        """Test GET /api/sla/policies endpoint."""
        response = client.get("/api/sla/policies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_policy(self, client):
        """Test POST /api/sla/policies endpoint."""
        policy_data = {
            "id": "test-policy",
            "name": "Test Policy",
            "organization_id": "org-test",
            "targets": [
                {"severity": "P1", "sla_type": "response", "target_minutes": 15},
                {"severity": "P1", "sla_type": "resolution", "target_minutes": 240},
            ],
        }
        response = client.post("/api/sla/policies", json=policy_data)
        assert response.status_code in (200, 201)

    def test_get_incident_status(self, client):
        """Test GET /api/sla/incidents/{id}/status endpoint."""
        response = client.get("/api/sla/incidents/test-inc-1/status")
        # Should return 404 if incident doesn't exist, or 200 with status
        assert response.status_code in (200, 404)

    def test_get_metrics(self, client):
        """Test GET /api/sla/metrics endpoint."""
        response = client.get("/api/sla/metrics?days=7")
        assert response.status_code == 200

    def test_get_breaches(self, client):
        """Test GET /api/sla/breaches endpoint."""
        response = client.get("/api/sla/breaches")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
