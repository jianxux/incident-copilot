"""Tests for escalation policies and engine module."""

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.escalation.models import (
    ActionType,
    ConditionOperator,
    CreatePolicyRequest,
    DeescalationRule,
    EscalationAction,
    EscalationCondition,
    EscalationHistoryEntry,
    EscalationHistoryFilter,
    EscalationLevel,
    EscalationPolicy,
    EscalationState,
    EscalationStatus,
    OnCallAssignment,
    OverrideEscalationRequest,
    Severity,
    TeamRotation,
    TimeWindow,
    TriggerEscalationRequest,
    UpdatePolicyRequest,
)
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_policy() -> EscalationPolicy:
    """Create a sample escalation policy."""
    return EscalationPolicy(
        id=uuid4(),
        name="Standard Escalation",
        description="Default escalation for all incidents",
        services=["payments", "api-gateway"],
        severities=[Severity.CRITICAL, Severity.HIGH],
        levels=[
            EscalationLevel(
                level=1,
                name="L1 On-Call",
                delay_minutes=0,
                actions=[
                    EscalationAction(
                        action_type=ActionType.PAGE,
                        target="oncall-pagerduty",
                    ),
                    EscalationAction(
                        action_type=ActionType.SLACK,
                        target="#incidents",
                    ),
                ],
                use_oncall=True,
                team_id="platform",
            ),
            EscalationLevel(
                level=2,
                name="L2 Manager",
                delay_minutes=15,
                actions=[
                    EscalationAction(
                        action_type=ActionType.EMAIL,
                        target="manager@example.com",
                    ),
                ],
                fallback_targets=["backup-manager@example.com"],
            ),
        ],
        priority=10,
    )


@pytest.fixture
def sample_oncall() -> OnCallAssignment:
    """Create a sample on-call assignment."""
    return OnCallAssignment(
        user_id="user-123",
        user_name="John Doe",
        user_email="john@example.com",
        user_phone="+1234567890",
        slack_id="U12345",
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(days=7),
        is_primary=True,
        team_id="platform",
    )


class TestActionType:
    """Tests for ActionType enum."""

    def test_action_types(self):
        """Test all action types exist."""
        assert ActionType.PAGE.value == "page"
        assert ActionType.EMAIL.value == "email"
        assert ActionType.SLACK.value == "slack"
        assert ActionType.PHONE.value == "phone"
        assert ActionType.WEBHOOK.value == "webhook"
        assert ActionType.SMS.value == "sms"


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test all severity levels exist."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"


class TestConditionOperator:
    """Tests for ConditionOperator enum."""

    def test_operator_values(self):
        """Test all operators exist."""
        assert ConditionOperator.EQUALS.value == "eq"
        assert ConditionOperator.NOT_EQUALS.value == "neq"
        assert ConditionOperator.CONTAINS.value == "contains"
        assert ConditionOperator.IN.value == "in"
        assert ConditionOperator.MATCHES.value == "matches"


class TestTimeWindow:
    """Tests for TimeWindow model."""

    def test_time_window_creation(self):
        """Test creating a time window."""
        window = TimeWindow(
            start_time=time(9, 0),
            end_time=time(17, 0),
            days_of_week=[0, 1, 2, 3, 4],  # Mon-Fri
            timezone="America/New_York",
        )
        assert window.start_time == time(9, 0)
        assert len(window.days_of_week) == 5

    def test_invalid_days(self):
        """Test invalid days are rejected."""
        with pytest.raises(ValueError):
            TimeWindow(
                start_time=time(9, 0),
                end_time=time(17, 0),
                days_of_week=[0, 7],  # 7 is invalid
            )


class TestEscalationCondition:
    """Tests for EscalationCondition model."""

    def test_equals_condition(self):
        """Test equals condition matching."""
        condition = EscalationCondition(
            field="severity",
            operator=ConditionOperator.EQUALS,
            value="critical",
        )
        assert condition.matches({"severity": "critical"})
        assert not condition.matches({"severity": "high"})

    def test_not_equals_condition(self):
        """Test not equals condition matching."""
        condition = EscalationCondition(
            field="status",
            operator=ConditionOperator.NOT_EQUALS,
            value="resolved",
        )
        assert condition.matches({"status": "open"})
        assert not condition.matches({"status": "resolved"})

    def test_contains_condition(self):
        """Test contains condition matching."""
        condition = EscalationCondition(
            field="title",
            operator=ConditionOperator.CONTAINS,
            value="database",
        )
        assert condition.matches({"title": "Database outage in production"})
        assert not condition.matches({"title": "API timeout"})

    def test_in_condition(self):
        """Test in condition matching."""
        condition = EscalationCondition(
            field="service",
            operator=ConditionOperator.IN,
            value=["payments", "api-gateway", "auth"],
        )
        assert condition.matches({"service": "payments"})
        assert not condition.matches({"service": "notifications"})

    def test_regex_condition(self):
        """Test regex condition matching."""
        condition = EscalationCondition(
            field="error_code",
            operator=ConditionOperator.MATCHES,
            value=r"5\d{2}",  # 5xx errors
        )
        assert condition.matches({"error_code": "500"})
        assert condition.matches({"error_code": "503"})
        assert not condition.matches({"error_code": "404"})

    def test_missing_field(self):
        """Test condition with missing field."""
        condition = EscalationCondition(
            field="missing",
            operator=ConditionOperator.EQUALS,
            value="something",
        )
        assert not condition.matches({"other": "field"})


class TestEscalationAction:
    """Tests for EscalationAction model."""

    def test_action_creation(self):
        """Test creating an escalation action."""
        action = EscalationAction(
            action_type=ActionType.PAGE,
            target="pagerduty-service-key",
            retry_count=3,
            retry_delay_seconds=60,
        )
        assert action.action_type == ActionType.PAGE
        assert action.retry_count == 3

    def test_action_with_template(self):
        """Test action with message template."""
        action = EscalationAction(
            action_type=ActionType.EMAIL,
            target="team@example.com",
            template="Incident {{incident_id}} requires attention",
        )
        assert "{{incident_id}}" in action.template


class TestEscalationLevel:
    """Tests for EscalationLevel model."""

    def test_level_creation(self, sample_oncall):
        """Test creating an escalation level."""
        level = EscalationLevel(
            level=1,
            name="L1 Support",
            delay_minutes=0,
            actions=[
                EscalationAction(action_type=ActionType.SLACK, target="#alerts"),
            ],
            use_oncall=True,
            team_id="platform",
        )
        assert level.level == 1
        assert level.delay_minutes == 0

    def test_get_effective_targets_with_oncall(self, sample_oncall):
        """Test getting effective targets with on-call."""
        level = EscalationLevel(
            level=1,
            name="L1",
            actions=[
                EscalationAction(
                    action_type=ActionType.EMAIL, target="default@example.com"
                ),
                EscalationAction(action_type=ActionType.SLACK, target="#default"),
            ],
            use_oncall=True,
            fallback_targets=["fallback@example.com"],
        )
        targets = level.get_effective_targets(sample_oncall)
        assert "john@example.com" in targets
        assert "U12345" in targets

    def test_get_effective_targets_fallback(self):
        """Test fallback targets when no on-call."""
        level = EscalationLevel(
            level=1,
            name="L1",
            actions=[],
            use_oncall=True,
            fallback_targets=["fallback@example.com"],
        )
        targets = level.get_effective_targets(None)
        assert targets == ["fallback@example.com"]


class TestOnCallAssignment:
    """Tests for OnCallAssignment model."""

    def test_assignment_creation(self, sample_oncall):
        """Test creating an on-call assignment."""
        assert sample_oncall.user_id == "user-123"
        assert sample_oncall.is_primary
        assert sample_oncall.user_phone is not None


class TestTeamRotation:
    """Tests for TeamRotation model."""

    def test_rotation_creation(self, sample_oncall):
        """Test creating a team rotation."""
        rotation = TeamRotation(
            team_id="platform",
            team_name="Platform Team",
            rotation_type="weekly",
            members=[sample_oncall],
            current_index=0,
        )
        assert rotation.rotation_type == "weekly"
        assert len(rotation.members) == 1


class TestEscalationPolicy:
    """Tests for EscalationPolicy model."""

    def test_policy_creation(self, sample_policy):
        """Test creating an escalation policy."""
        assert sample_policy.name == "Standard Escalation"
        assert len(sample_policy.levels) == 2
        assert sample_policy.priority == 10

    def test_policy_level_validation(self):
        """Test that duplicate levels are rejected."""
        with pytest.raises(ValueError):
            EscalationPolicy(
                name="Bad Policy",
                levels=[
                    EscalationLevel(level=1, name="L1"),
                    EscalationLevel(level=1, name="L1 Again"),  # Duplicate
                ],
            )

    def test_policy_levels_sorted(self):
        """Test that levels are sorted by level number."""
        policy = EscalationPolicy(
            name="Unordered",
            levels=[
                EscalationLevel(level=3, name="L3"),
                EscalationLevel(level=1, name="L1"),
                EscalationLevel(level=2, name="L2"),
            ],
        )
        assert policy.levels[0].level == 1
        assert policy.levels[1].level == 2
        assert policy.levels[2].level == 3


class TestDeescalationRule:
    """Tests for DeescalationRule model."""

    def test_rule_creation(self):
        """Test creating a de-escalation rule."""
        rule = DeescalationRule(
            name="Downgrade to L1",
            conditions=[
                EscalationCondition(
                    field="severity",
                    operator=ConditionOperator.EQUALS,
                    value="low",
                )
            ],
            target_level=1,
            cooldown_minutes=30,
        )
        assert rule.target_level == 1
        assert rule.cooldown_minutes == 30


class TestEscalationState:
    """Tests for EscalationState model."""

    def test_state_creation(self, sample_policy):
        """Test creating escalation state."""
        state = EscalationState(
            incident_id="inc-123",
            policy_id=sample_policy.id,
            current_level=1,
            status=EscalationStatus.TRIGGERED,
        )
        assert state.current_level == 1
        assert state.repeat_count == 0
        assert not state.is_paused


class TestEscalationHistoryEntry:
    """Tests for EscalationHistoryEntry model."""

    def test_history_entry(self, sample_policy):
        """Test creating a history entry."""
        entry = EscalationHistoryEntry(
            incident_id="inc-123",
            policy_id=sample_policy.id,
            policy_name=sample_policy.name,
            level=1,
            level_name="L1 On-Call",
            status=EscalationStatus.TRIGGERED,
            action_type=ActionType.PAGE,
            target="oncall@pagerduty.com",
        )
        assert entry.status == EscalationStatus.TRIGGERED


class TestEscalationAPI:
    """Tests for Escalation API endpoints."""

    def test_list_policies(self, client):
        """Test GET /api/escalation/policies endpoint."""
        response = client.get("/api/escalation/policies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_policy(self, client):
        """Test POST /api/escalation/policies endpoint."""
        response = client.post(
            "/api/escalation/policies",
            json={
                "name": "New Policy",
                "services": ["api"],
                "severities": ["critical"],
                "levels": [
                    {
                        "level": 1,
                        "name": "L1",
                        "delay_minutes": 0,
                        "actions": [{"action_type": "slack", "target": "#alerts"}],
                    }
                ],
            },
        )
        assert response.status_code in (200, 201)

    def test_get_policy(self, client):
        """Test GET /api/escalation/policies/{id} endpoint."""
        policy_id = str(uuid4())
        response = client.get(f"/api/escalation/policies/{policy_id}")
        assert response.status_code in (200, 404)

    def test_update_policy(self, client):
        """Test PUT /api/escalation/policies/{id} endpoint."""
        policy_id = str(uuid4())
        response = client.put(
            f"/api/escalation/policies/{policy_id}",
            json={"name": "Updated Policy"},
        )
        assert response.status_code in (200, 404)

    def test_trigger_escalation(self, client):
        """Test POST /api/escalation/trigger endpoint."""
        response = client.post(
            "/api/escalation/trigger",
            json={
                "incident_id": "inc-123",
                "reason": "Manual escalation requested",
            },
        )
        assert response.status_code in (200, 202, 404)

    def test_override_escalation(self, client):
        """Test POST /api/escalation/override endpoint."""
        response = client.post(
            "/api/escalation/override",
            json={
                "incident_id": "inc-123",
                "action": "skip",
                "reason": "Issue resolved, no escalation needed",
            },
        )
        assert response.status_code in (200, 404)

    def test_get_escalation_state(self, client):
        """Test GET /api/escalation/incidents/{id} endpoint."""
        response = client.get("/api/escalation/incidents/inc-123")
        assert response.status_code in (200, 404)

    def test_get_escalation_history(self, client):
        """Test GET /api/escalation/history endpoint."""
        response = client.get("/api/escalation/history?incident_id=inc-123")
        assert response.status_code == 200

    def test_get_oncall(self, client):
        """Test GET /api/escalation/oncall endpoint."""
        response = client.get("/api/escalation/oncall?team_id=platform")
        assert response.status_code in (200, 404)
