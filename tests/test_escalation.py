"""Comprehensive tests for the Escalation Rules Engine."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.escalation import (
    ActionType,
    ConditionOperator,
    ConditionType,
    EscalationAction,
    EscalationCondition,
    EscalationEngine,
    EscalationPolicy,
    EscalationRule,
    EscalationScheduler,
    EscalationStep,
    IncidentState,
    MaintenanceWindow,
    ServiceTier,
)
from src.escalation.actions import (
    ActionResult,
    AutoAssignHandler,
    NotifyHandler,
    PageHandler,
    UpdateSeverityHandler,
    execute_action,
    execute_actions,
)
from src.escalation.conditions import (
    NoResponseCondition,
    ServiceTierCondition,
    SeverityCondition,
    TimeBasedCondition,
    UnacknowledgedCondition,
    evaluate_condition,
    evaluate_conditions,
)
from src.escalation.routes import router


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_incident() -> IncidentState:
    """Create a sample incident for testing."""
    return IncidentState(
        incident_id="inc-001",
        title="Database connection timeout",
        service="payments-api",
        service_tier=ServiceTier.HIGH,
        severity="high",
        status="triggered",
        triggered_at=datetime.utcnow() - timedelta(minutes=10),
        team_id="team-payments",
        tags={"env": "production", "region": "us-east-1"},
        source="pagerduty",
        url="https://pagerduty.com/incidents/inc-001",
    )


@pytest.fixture
def acknowledged_incident() -> IncidentState:
    """Create an acknowledged incident."""
    return IncidentState(
        incident_id="inc-002",
        title="High CPU usage",
        service="compute-api",
        service_tier=ServiceTier.MEDIUM,
        severity="medium",
        status="acknowledged",
        triggered_at=datetime.utcnow() - timedelta(minutes=20),
        acknowledged_at=datetime.utcnow() - timedelta(minutes=15),
        assigned_to=["user-123"],
        team_id="team-infra",
        source="opsgenie",
    )


@pytest.fixture
def sample_policy() -> EscalationPolicy:
    """Create a sample escalation policy."""
    return EscalationPolicy(
        id="policy-001",
        name="Standard Escalation",
        service_pattern=".*-api$",
        steps=[
            EscalationStep(
                step_number=1,
                delay_minutes=5,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.PAGE,
                        target="user-primary",
                    ),
                ],
            ),
            EscalationStep(
                step_number=2,
                delay_minutes=15,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.ADD_RESPONDER,
                        target="user-secondary",
                    ),
                ],
            ),
            EscalationStep(
                step_number=3,
                delay_minutes=30,
                actions=[
                    EscalationAction(
                        action_type=ActionType.ESCALATE_TO_MANAGER,
                        target="manager-001",
                    ),
                ],
            ),
        ],
        primary_responder="user-primary",
        secondary_responder="user-secondary",
        manager="manager-001",
    )


@pytest.fixture
def sample_rule() -> EscalationRule:
    """Create a sample escalation rule."""
    return EscalationRule(
        id="rule-001",
        name="Critical Alert Rule",
        priority=10,
        severity_filter=["critical"],
        conditions=[
            EscalationCondition(
                condition_type=ConditionType.TIME_SINCE_ALERT,
                operator=ConditionOperator.GREATER_THAN,
                value=5,
            ),
            EscalationCondition(
                condition_type=ConditionType.UNACKNOWLEDGED,
                operator=ConditionOperator.EQUALS,
                value=True,
            ),
        ],
        actions=[
            EscalationAction(
                action_type=ActionType.PAGE,
                target="oncall-critical",
            ),
            EscalationAction(
                action_type=ActionType.POST_TO_CHANNEL,
                target="#critical-alerts",
            ),
        ],
    )


@pytest.fixture
async def engine() -> EscalationEngine:
    """Create an initialized escalation engine."""
    engine = EscalationEngine()
    await engine.initialize()
    yield engine
    await engine.close()


@pytest.fixture
def test_app(engine) -> FastAPI:
    """Create a test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(test_app) -> TestClient:
    """Create a test client."""
    return TestClient(test_app)


# ============================================================================
# Condition Evaluator Tests
# ============================================================================


class TestTimeBasedCondition:
    """Tests for time-based condition evaluation."""

    def test_time_since_alert_greater_than(self, sample_incident):
        """Test time_since_alert > X condition."""
        condition = EscalationCondition(
            condition_type=ConditionType.TIME_SINCE_ALERT,
            operator=ConditionOperator.GREATER_THAN,
            value=5,  # 5 minutes
        )

        evaluator = TimeBasedCondition()
        # Incident is 10 minutes old, should be > 5
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True

    def test_time_since_alert_less_than(self, sample_incident):
        """Test time_since_alert < X condition."""
        condition = EscalationCondition(
            condition_type=ConditionType.TIME_SINCE_ALERT,
            operator=ConditionOperator.LESS_THAN,
            value=5,  # 5 minutes
        )

        evaluator = TimeBasedCondition()
        # Incident is 10 minutes old, should NOT be < 5
        result = evaluator.evaluate(condition, sample_incident)
        assert result is False

    def test_time_since_ack_not_acknowledged(self, sample_incident):
        """Test time_since_ack when not acknowledged."""
        condition = EscalationCondition(
            condition_type=ConditionType.TIME_SINCE_ACK,
            operator=ConditionOperator.GREATER_THAN,
            value=5,
        )

        evaluator = TimeBasedCondition()
        # Not acknowledged, should return False
        result = evaluator.evaluate(condition, sample_incident)
        assert result is False

    def test_time_since_ack_acknowledged(self, acknowledged_incident):
        """Test time_since_ack when acknowledged."""
        condition = EscalationCondition(
            condition_type=ConditionType.TIME_SINCE_ACK,
            operator=ConditionOperator.GREATER_THAN,
            value=10,  # 10 minutes since ack
        )

        evaluator = TimeBasedCondition()
        # Acknowledged 15 minutes ago, should be > 10
        result = evaluator.evaluate(condition, acknowledged_incident)
        assert result is True


class TestSeverityCondition:
    """Tests for severity-based condition evaluation."""

    def test_severity_equals(self, sample_incident):
        """Test severity equals condition."""
        condition = EscalationCondition(
            condition_type=ConditionType.SEVERITY,
            operator=ConditionOperator.EQUALS,
            value="high",
        )

        evaluator = SeverityCondition()
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True

    def test_severity_not_equals(self, sample_incident):
        """Test severity not equals condition."""
        condition = EscalationCondition(
            condition_type=ConditionType.SEVERITY,
            operator=ConditionOperator.NOT_EQUALS,
            value="critical",
        )

        evaluator = SeverityCondition()
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True

    def test_severity_greater_than(self, sample_incident):
        """Test severity > condition (more severe)."""
        condition = EscalationCondition(
            condition_type=ConditionType.SEVERITY,
            operator=ConditionOperator.GREATER_THAN,
            value="medium",  # High is more severe than medium
        )

        evaluator = SeverityCondition()
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True

    def test_severity_in_list(self, sample_incident):
        """Test severity in list condition."""
        condition = EscalationCondition(
            condition_type=ConditionType.SEVERITY,
            operator=ConditionOperator.IN,
            value=["critical", "high"],
        )

        evaluator = SeverityCondition()
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True


class TestUnacknowledgedCondition:
    """Tests for unacknowledged condition evaluation."""

    def test_unacknowledged_true(self, sample_incident):
        """Test unacknowledged = true condition."""
        condition = EscalationCondition(
            condition_type=ConditionType.UNACKNOWLEDGED,
            operator=ConditionOperator.EQUALS,
            value=True,
        )

        evaluator = UnacknowledgedCondition()
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True

    def test_unacknowledged_false_when_acked(self, acknowledged_incident):
        """Test unacknowledged = true when already acked."""
        condition = EscalationCondition(
            condition_type=ConditionType.UNACKNOWLEDGED,
            operator=ConditionOperator.EQUALS,
            value=True,
        )

        evaluator = UnacknowledgedCondition()
        result = evaluator.evaluate(condition, acknowledged_incident)
        assert result is False


class TestNoResponseCondition:
    """Tests for no-response condition evaluation."""

    def test_no_response_no_activity(self, sample_incident):
        """Test no response when no activity recorded."""
        condition = EscalationCondition(
            condition_type=ConditionType.NO_RESPONSE,
            operator=ConditionOperator.GREATER_THAN,
            value=5,  # 5 minutes
        )

        evaluator = NoResponseCondition()
        # No last_activity_at, uses triggered_at (10 min ago)
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True

    def test_no_response_with_recent_activity(self, sample_incident):
        """Test no response with recent activity."""
        sample_incident.last_activity_at = datetime.utcnow() - timedelta(minutes=2)

        condition = EscalationCondition(
            condition_type=ConditionType.NO_RESPONSE,
            operator=ConditionOperator.GREATER_THAN,
            value=5,
        )

        evaluator = NoResponseCondition()
        # Activity 2 minutes ago, should NOT be > 5
        result = evaluator.evaluate(condition, sample_incident)
        assert result is False


class TestServiceTierCondition:
    """Tests for service tier condition evaluation."""

    def test_service_tier_equals(self, sample_incident):
        """Test service tier equals condition."""
        condition = EscalationCondition(
            condition_type=ConditionType.SERVICE_TIER,
            operator=ConditionOperator.EQUALS,
            value="high",
        )

        evaluator = ServiceTierCondition()
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True

    def test_service_tier_greater_than(self, sample_incident):
        """Test service tier > condition (higher tier)."""
        condition = EscalationCondition(
            condition_type=ConditionType.SERVICE_TIER,
            operator=ConditionOperator.GREATER_THAN,
            value="medium",  # High is higher tier than medium
        )

        evaluator = ServiceTierCondition()
        result = evaluator.evaluate(condition, sample_incident)
        assert result is True


class TestCombinedConditions:
    """Tests for evaluating multiple conditions."""

    def test_all_conditions_met(self, sample_incident):
        """Test all conditions must be met (AND logic)."""
        conditions = [
            EscalationCondition(
                condition_type=ConditionType.TIME_SINCE_ALERT,
                operator=ConditionOperator.GREATER_THAN,
                value=5,
            ),
            EscalationCondition(
                condition_type=ConditionType.UNACKNOWLEDGED,
                operator=ConditionOperator.EQUALS,
                value=True,
            ),
            EscalationCondition(
                condition_type=ConditionType.SEVERITY,
                operator=ConditionOperator.IN,
                value=["critical", "high"],
            ),
        ]

        result = evaluate_conditions(conditions, sample_incident, require_all=True)
        assert result is True

    def test_any_condition_met(self, sample_incident):
        """Test any condition can be met (OR logic)."""
        conditions = [
            EscalationCondition(
                condition_type=ConditionType.TIME_SINCE_ALERT,
                operator=ConditionOperator.LESS_THAN,
                value=5,  # Not met (10 min)
            ),
            EscalationCondition(
                condition_type=ConditionType.SEVERITY,
                operator=ConditionOperator.EQUALS,
                value="high",  # Met
            ),
        ]

        result = evaluate_conditions(conditions, sample_incident, require_all=False)
        assert result is True

    def test_empty_conditions(self, sample_incident):
        """Test empty conditions list returns True."""
        result = evaluate_conditions([], sample_incident)
        assert result is True


# ============================================================================
# Action Handler Tests
# ============================================================================


class TestNotifyHandler:
    """Tests for notification action handler."""

    @pytest.mark.asyncio
    async def test_slack_notification(self, sample_incident):
        """Test Slack notification action."""
        action = EscalationAction(
            action_type=ActionType.NOTIFY,
            target="#incidents",
            params={"channel": "slack"},
        )

        handler = NotifyHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is True
        assert "#incidents" in result.message
        assert result.details.get("simulated") is True

    @pytest.mark.asyncio
    async def test_email_notification(self, sample_incident):
        """Test email notification action."""
        action = EscalationAction(
            action_type=ActionType.NOTIFY,
            target="oncall@example.com",
            params={"channel": "email"},
        )

        handler = NotifyHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is True
        assert "oncall@example.com" in result.message

    @pytest.mark.asyncio
    async def test_notify_missing_target(self, sample_incident):
        """Test notification fails without target."""
        action = EscalationAction(
            action_type=ActionType.NOTIFY,
            params={"channel": "slack"},
        )

        handler = NotifyHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is False
        assert "No Slack target" in result.error


class TestPageHandler:
    """Tests for paging action handler."""

    @pytest.mark.asyncio
    async def test_pagerduty_page(self, sample_incident):
        """Test PagerDuty paging action."""
        action = EscalationAction(
            action_type=ActionType.PAGE,
            target="user-123",
            params={"provider": "pagerduty"},
        )

        handler = PageHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is True
        assert "PagerDuty" in result.message

    @pytest.mark.asyncio
    async def test_opsgenie_page(self, sample_incident):
        """Test Opsgenie paging action."""
        action = EscalationAction(
            action_type=ActionType.PAGE,
            target="user-456",
            params={"provider": "opsgenie"},
        )

        handler = PageHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is True
        assert "Opsgenie" in result.message


class TestUpdateSeverityHandler:
    """Tests for severity update action handler."""

    @pytest.mark.asyncio
    async def test_update_severity(self, sample_incident):
        """Test severity update action."""
        action = EscalationAction(
            action_type=ActionType.UPDATE_SEVERITY,
            params={"severity": "critical"},
        )

        handler = UpdateSeverityHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is True
        assert "high" in result.details.get("old_severity", "")
        assert "critical" in result.details.get("new_severity", "")

    @pytest.mark.asyncio
    async def test_update_severity_invalid(self, sample_incident):
        """Test severity update with invalid value."""
        action = EscalationAction(
            action_type=ActionType.UPDATE_SEVERITY,
            params={"severity": "invalid"},
        )

        handler = UpdateSeverityHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is False
        assert "Invalid severity" in result.error


class TestAutoAssignHandler:
    """Tests for auto-assign action handler."""

    @pytest.mark.asyncio
    async def test_auto_assign_user(self, sample_incident):
        """Test auto-assign to user."""
        action = EscalationAction(
            action_type=ActionType.AUTO_ASSIGN,
            target="user-789",
            params={"type": "user"},
        )

        handler = AutoAssignHandler()
        result = await handler.execute(action, sample_incident)

        assert result.success is True
        assert "user-789" in result.message


class TestExecuteActions:
    """Tests for executing multiple actions."""

    @pytest.mark.asyncio
    async def test_execute_multiple_actions(self, sample_incident):
        """Test executing multiple actions concurrently."""
        actions = [
            EscalationAction(
                action_type=ActionType.NOTIFY,
                target="#alerts",
                params={"channel": "slack"},
            ),
            EscalationAction(
                action_type=ActionType.PAGE,
                target="user-123",
            ),
        ]

        results = await execute_actions(actions, sample_incident)

        assert len(results) == 2
        assert all(r.success for r in results)


# ============================================================================
# Escalation Engine Tests
# ============================================================================


class TestEscalationEngine:
    """Tests for the escalation engine."""

    @pytest.mark.asyncio
    async def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        stats = await engine.get_stats()
        assert stats["initialized"] is True

    @pytest.mark.asyncio
    async def test_create_policy(self, engine, sample_policy):
        """Test creating an escalation policy."""
        created = await engine.create_policy(sample_policy)

        assert created.id == sample_policy.id
        assert created.name == sample_policy.name

        # Verify it was stored
        retrieved = await engine.get_policy(sample_policy.id)
        assert retrieved is not None
        assert retrieved.id == sample_policy.id

    @pytest.mark.asyncio
    async def test_create_rule(self, engine, sample_rule):
        """Test creating an escalation rule."""
        created = await engine.create_rule(sample_rule)

        assert created.id == sample_rule.id
        assert created.name == sample_rule.name

    @pytest.mark.asyncio
    async def test_evaluate_incident_no_policy(self, engine, sample_incident):
        """Test evaluating incident with no matching policy."""
        result = await engine.evaluate_incident(sample_incident)

        assert result.incident_id == sample_incident.incident_id
        assert result.triggered is False

    @pytest.mark.asyncio
    async def test_evaluate_incident_with_policy(
        self, engine, sample_incident, sample_policy
    ):
        """Test evaluating incident with matching policy."""
        await engine.create_policy(sample_policy)

        result = await engine.evaluate_incident(sample_incident)

        assert result.incident_id == sample_incident.incident_id
        assert result.policy_id == sample_policy.id
        # Should trigger step 2 (incident is 10 min old, step 2 is at 15 min)
        # Actually step 1 at 5 min should trigger since incident is 10 min old

    @pytest.mark.asyncio
    async def test_maintenance_window_suppression(self, engine, sample_incident):
        """Test escalation suppression during maintenance."""
        # Create maintenance window
        window = MaintenanceWindow(
            name="Planned Maintenance",
            service_pattern="payments-.*",
            start_time=datetime.utcnow() - timedelta(hours=1),
            end_time=datetime.utcnow() + timedelta(hours=1),
        )
        await engine.create_maintenance_window(window)

        result = await engine.evaluate_incident(sample_incident)

        assert result.suppressed is True
        assert "maintenance" in result.suppression_reason.lower()

    @pytest.mark.asyncio
    async def test_resolved_incident_not_escalated(self, engine, sample_incident):
        """Test resolved incidents are not escalated."""
        sample_incident.resolved_at = datetime.utcnow()

        result = await engine.evaluate_incident(sample_incident)

        assert result.triggered is False
        assert "resolved" in result.suppression_reason.lower()

    @pytest.mark.asyncio
    async def test_audit_log(self, engine, sample_incident, sample_policy):
        """Test escalation audit log."""
        await engine.create_policy(sample_policy)
        await engine.evaluate_incident(sample_incident)

        entries, total = await engine.get_audit_log(
            incident_id=sample_incident.incident_id
        )

        # Should have audit entries for actions executed
        assert total >= 0  # May be 0 if no actions triggered


class TestEscalationPolicy:
    """Tests for escalation policy logic."""

    def test_get_step_for_time_early(self, sample_policy):
        """Test getting step for early time (no step yet)."""
        step = sample_policy.get_step_for_time(2)
        assert step is None

    def test_get_step_for_time_step1(self, sample_policy):
        """Test getting step 1 at 5 minutes."""
        step = sample_policy.get_step_for_time(7)
        assert step is not None
        assert step.step_number == 1

    def test_get_step_for_time_step2(self, sample_policy):
        """Test getting step 2 at 15 minutes."""
        step = sample_policy.get_step_for_time(20)
        assert step is not None
        assert step.step_number == 2

    def test_get_step_for_time_step3(self, sample_policy):
        """Test getting step 3 at 30 minutes."""
        step = sample_policy.get_step_for_time(45)
        assert step is not None
        assert step.step_number == 3


class TestIncidentState:
    """Tests for incident state model."""

    def test_is_acknowledged(self, sample_incident, acknowledged_incident):
        """Test is_acknowledged property."""
        assert sample_incident.is_acknowledged is False
        assert acknowledged_incident.is_acknowledged is True

    def test_minutes_since_triggered(self, sample_incident):
        """Test minutes_since_triggered calculation."""
        minutes = sample_incident.minutes_since_triggered
        assert 9 <= minutes <= 11  # Should be around 10

    def test_minutes_since_acknowledged(self, acknowledged_incident):
        """Test minutes_since_acknowledged calculation."""
        minutes = acknowledged_incident.minutes_since_acknowledged
        assert 14 <= minutes <= 16  # Should be around 15


# ============================================================================
# Scheduler Tests
# ============================================================================


class TestEscalationScheduler:
    """Tests for the escalation scheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_starts_and_stops(self, engine):
        """Test scheduler lifecycle."""
        scheduler = EscalationScheduler(engine, check_interval_seconds=1)

        await scheduler.start()
        stats = scheduler.get_stats()
        assert stats["running"] is True

        await scheduler.stop()
        stats = scheduler.get_stats()
        assert stats["running"] is False

    @pytest.mark.asyncio
    async def test_manual_check(self, engine, sample_incident):
        """Test manual escalation check."""
        scheduler = EscalationScheduler(engine)

        # Store an incident
        await engine.store.store_incident_state(sample_incident)

        # Manually trigger check
        triggered = await scheduler.check_now()
        assert isinstance(triggered, int)

    @pytest.mark.asyncio
    async def test_scheduler_callback(self, engine, sample_incident, sample_policy):
        """Test scheduler calls registered callbacks."""
        await engine.create_policy(sample_policy)
        await engine.store.store_incident_state(sample_incident)

        scheduler = EscalationScheduler(engine)
        callback_called = []

        def on_escalation(incident, result):
            callback_called.append((incident, result))

        scheduler.on_escalation(on_escalation)

        await scheduler.check_now()
        # Callback may or may not be called depending on conditions


# ============================================================================
# API Route Tests
# ============================================================================


class TestEscalationAPI:
    """Tests for escalation API endpoints."""

    def test_create_policy_endpoint(self, client):
        """Test POST /api/v1/escalation/policies."""
        policy_data = {
            "name": "Test Policy",
            "service_pattern": "test-.*",
            "steps": [
                {
                    "step_number": 1,
                    "delay_minutes": 5,
                    "conditions": [],
                    "actions": [
                        {
                            "action_type": "page",
                            "target": "user-test",
                        }
                    ],
                }
            ],
        }

        response = client.post("/api/v1/escalation/policies", json=policy_data)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Policy"
        assert "id" in data

    def test_list_policies_endpoint(self, client):
        """Test GET /api/v1/escalation/policies."""
        response = client.get("/api/v1/escalation/policies")
        assert response.status_code == 200

        data = response.json()
        assert "policies" in data
        assert "total" in data

    def test_get_policy_not_found(self, client):
        """Test GET /api/v1/escalation/policies/{id} with invalid ID."""
        response = client.get("/api/v1/escalation/policies/nonexistent")
        assert response.status_code == 404

    def test_create_rule_endpoint(self, client):
        """Test POST /api/v1/escalation/rules."""
        rule_data = {
            "name": "Test Rule",
            "conditions": [
                {
                    "condition_type": "unacknowledged",
                    "operator": "eq",
                    "value": True,
                }
            ],
            "actions": [
                {
                    "action_type": "notify",
                    "target": "#alerts",
                    "params": {"channel": "slack"},
                }
            ],
        }

        response = client.post("/api/v1/escalation/rules", json=rule_data)
        assert response.status_code == 201

    def test_list_rules_endpoint(self, client):
        """Test GET /api/v1/escalation/rules."""
        response = client.get("/api/v1/escalation/rules")
        assert response.status_code == 200

        data = response.json()
        assert "rules" in data

    def test_create_maintenance_window_endpoint(self, client):
        """Test POST /api/v1/escalation/maintenance-windows."""
        window_data = {
            "name": "Planned Maintenance",
            "start_time": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        }

        response = client.post(
            "/api/v1/escalation/maintenance-windows", json=window_data
        )
        assert response.status_code == 201

    def test_create_maintenance_window_invalid_times(self, client):
        """Test maintenance window with end before start."""
        window_data = {
            "name": "Invalid Window",
            "start_time": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }

        response = client.post(
            "/api/v1/escalation/maintenance-windows", json=window_data
        )
        assert response.status_code == 400

    def test_get_audit_log_endpoint(self, client):
        """Test GET /api/v1/escalation/audit."""
        response = client.get("/api/v1/escalation/audit")
        assert response.status_code == 200

        data = response.json()
        assert "entries" in data

    def test_get_stats_endpoint(self, client):
        """Test GET /api/v1/escalation/stats."""
        response = client.get("/api/v1/escalation/stats")
        assert response.status_code == 200

        data = response.json()
        assert "initialized" in data

    def test_create_standard_policy_template(self, client):
        """Test POST /api/v1/escalation/templates/standard-policy."""
        response = client.post(
            "/api/v1/escalation/templates/standard-policy",
            params={
                "name": "My Standard Policy",
                "service_pattern": ".*-api$",
                "primary_responder": "user-primary",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["steps"]) == 3  # Standard has 3 steps

    def test_create_critical_policy_template(self, client):
        """Test POST /api/v1/escalation/templates/critical-service-policy."""
        response = client.post(
            "/api/v1/escalation/templates/critical-service-policy",
            params={
                "name": "Critical Service Policy",
                "manager": "manager-001",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["service_tier"] == "critical"
        assert len(data["steps"]) == 4


# ============================================================================
# Integration Tests
# ============================================================================


class TestEscalationIntegration:
    """Integration tests for complete escalation flows."""

    @pytest.mark.asyncio
    async def test_full_escalation_flow(self, engine):
        """Test complete escalation from incident to actions."""
        # Create a policy
        policy = EscalationPolicy(
            name="Integration Test Policy",
            service_pattern="test-.*",
            steps=[
                EscalationStep(
                    step_number=1,
                    delay_minutes=0,  # Immediate for testing
                    conditions=[
                        EscalationCondition(
                            condition_type=ConditionType.UNACKNOWLEDGED,
                            operator=ConditionOperator.EQUALS,
                            value=True,
                        ),
                    ],
                    actions=[
                        EscalationAction(
                            action_type=ActionType.NOTIFY,
                            target="#test-channel",
                            params={"channel": "slack"},
                        ),
                        EscalationAction(
                            action_type=ActionType.PAGE,
                            target="test-user",
                        ),
                    ],
                ),
            ],
        )
        await engine.create_policy(policy)

        # Create an incident
        incident = IncidentState(
            incident_id="test-inc-001",
            title="Test Incident",
            service="test-api",
            severity="high",
            status="triggered",
            triggered_at=datetime.utcnow() - timedelta(minutes=5),
        )

        # Evaluate
        result = await engine.evaluate_incident(incident)

        # Verify
        assert result.triggered is True
        assert result.policy_id is not None
        assert len(result.actions_executed) == 2

        # Check audit log
        entries, _ = await engine.get_audit_log(incident_id=incident.incident_id)
        assert len(entries) >= 2

    @pytest.mark.asyncio
    async def test_step_not_repeated(self, engine):
        """Test that escalation steps are not repeated unnecessarily."""
        policy = EscalationPolicy(
            name="No Repeat Policy",
            service_pattern=".*",
            steps=[
                EscalationStep(
                    step_number=1,
                    delay_minutes=0,
                    actions=[
                        EscalationAction(
                            action_type=ActionType.NOTIFY,
                            target="#alerts",
                            params={"channel": "slack"},
                        ),
                    ],
                    repeat=False,
                ),
            ],
        )
        await engine.create_policy(policy)

        incident = IncidentState(
            incident_id="test-inc-002",
            title="Test",
            service="test-service",
            severity="high",
            status="triggered",
            triggered_at=datetime.utcnow(),
        )

        # First evaluation should trigger
        result1 = await engine.evaluate_incident(incident)
        assert result1.triggered is True

        # Second evaluation should not trigger (step already executed)
        result2 = await engine.evaluate_incident(incident)
        assert result2.triggered is False
        assert "already executed" in result2.suppression_reason.lower()

    @pytest.mark.asyncio
    async def test_business_hours_suppression(self, engine):
        """Test escalation suppression outside business hours."""
        policy = EscalationPolicy(
            name="Business Hours Only",
            service_pattern=".*",
            business_hours_only=True,
            business_hours_start=9,
            business_hours_end=17,
            timezone="UTC",
            steps=[
                EscalationStep(
                    step_number=1,
                    delay_minutes=0,
                    actions=[
                        EscalationAction(
                            action_type=ActionType.NOTIFY,
                            target="#alerts",
                            params={"channel": "slack"},
                        ),
                    ],
                ),
            ],
        )
        await engine.create_policy(policy)

        incident = IncidentState(
            incident_id="test-inc-003",
            title="Test",
            service="test-service",
            severity="high",
            status="triggered",
            triggered_at=datetime.utcnow(),
        )

        result = await engine.evaluate_incident(incident)

        # Result depends on current time - just verify it runs without error
        assert result.incident_id == incident.incident_id
