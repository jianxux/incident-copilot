"""Tests for the actions module."""

import pytest

from src.actions.approval import ApprovalWorkflow
from src.actions.engine import ActionEngine
from src.actions.executor import ActionExecutor
from src.actions.models import (
    ActionStatus,
    ActionType,
    RiskLevel,
    SuggestedAction,
)
from src.actions.slack_actions import (
    build_action_buttons,
    build_verdict_with_actions,
    format_action_result,
)


# --- Models ---


class TestModels:
    def test_suggested_action_defaults(self):
        action = SuggestedAction(
            action_type=ActionType.CREATE_JIRA,
            target_service="api",
            description="Create ticket",
            risk_level=RiskLevel.LOW,
            incident_id="INC-1",
        )
        assert action.status == ActionStatus.SUGGESTED
        assert action.suggested_by == "copilot"
        assert action.requires_approval is True
        assert action.id  # UUID generated

    def test_action_type_values(self):
        assert ActionType.ROLLBACK_DEPLOY == "rollback_deploy"
        assert ActionType.CREATE_JIRA == "create_jira"

    def test_risk_levels(self):
        assert RiskLevel.LOW == "low"
        assert RiskLevel.CRITICAL == "critical"


# --- Engine ---


class TestActionEngine:
    def setup_method(self):
        self.engine = ActionEngine()

    def test_generates_rollback_when_recommended(self):
        verdict = {"rollback_recommended": True, "rollback_target": "abc123"}
        context = {"incident_id": "INC-1", "service": "payments-api"}
        actions = self.engine.generate_actions(verdict, context)
        rollbacks = [a for a in actions if a.action_type == ActionType.ROLLBACK_DEPLOY]
        assert len(rollbacks) == 1
        assert rollbacks[0].risk_level == RiskLevel.HIGH
        assert rollbacks[0].requires_approval is True
        assert rollbacks[0].parameters["target_sha"] == "abc123"

    def test_always_suggests_jira(self):
        actions = self.engine.generate_actions({}, {"incident_id": "INC-1"})
        jiras = [a for a in actions if a.action_type == ActionType.CREATE_JIRA]
        assert len(jiras) == 1
        assert jiras[0].requires_approval is False

    def test_suggests_scale_from_recommendations(self):
        verdict = {"recommended_actions": ["Scale up the service to handle load"]}
        actions = self.engine.generate_actions(verdict, {"incident_id": "INC-1"})
        scales = [a for a in actions if a.action_type == ActionType.SCALE_SERVICE]
        assert len(scales) == 1

    def test_suggests_restart_from_recommendations(self):
        verdict = {"recommended_actions": ["Restart the pods"]}
        actions = self.engine.generate_actions(verdict, {"incident_id": "INC-1"})
        restarts = [a for a in actions if a.action_type == ActionType.RESTART_PODS]
        assert len(restarts) == 1

    def test_suggests_page_oncall_for_high_severity(self):
        actions = self.engine.generate_actions(
            {}, {"incident_id": "INC-1", "severity": "P1"}
        )
        pages = [a for a in actions if a.action_type == ActionType.PAGE_ONCALL]
        assert len(pages) == 1

    def test_suggests_silence_for_noisy_alerts(self):
        actions = self.engine.generate_actions(
            {}, {"incident_id": "INC-1", "alert_count": 10}
        )
        silences = [a for a in actions if a.action_type == ActionType.SILENCE_ALERT]
        assert len(silences) == 1

    def test_no_page_for_low_severity(self):
        actions = self.engine.generate_actions(
            {}, {"incident_id": "INC-1", "severity": "P3"}
        )
        pages = [a for a in actions if a.action_type == ActionType.PAGE_ONCALL]
        assert len(pages) == 0

    def test_feature_flag_suggestion(self):
        verdict = {"recommended_actions": ["Toggle feature flag for new checkout"]}
        actions = self.engine.generate_actions(verdict, {"incident_id": "INC-1"})
        flags = [
            a for a in actions if a.action_type == ActionType.TOGGLE_FEATURE_FLAG
        ]
        assert len(flags) == 1

    def test_runbook_suggestion(self):
        verdict = {"recommended_actions": ["Run runbook for database failover"]}
        actions = self.engine.generate_actions(verdict, {"incident_id": "INC-1"})
        runbooks = [a for a in actions if a.action_type == ActionType.RUN_RUNBOOK]
        assert len(runbooks) == 1

    def test_needs_approval(self):
        assert self.engine._needs_approval(RiskLevel.HIGH) is True
        assert self.engine._needs_approval(RiskLevel.CRITICAL) is True
        assert self.engine._needs_approval(RiskLevel.MEDIUM) is False
        assert self.engine._needs_approval(RiskLevel.LOW) is False


# --- Executor ---


class TestActionExecutor:
    def setup_method(self):
        self.executor = ActionExecutor()

    def _make_action(self, **kwargs):
        defaults = {
            "action_type": ActionType.CREATE_JIRA,
            "target_service": "api",
            "description": "Test",
            "risk_level": RiskLevel.LOW,
            "incident_id": "INC-1",
            "requires_approval": False,
        }
        defaults.update(kwargs)
        return SuggestedAction(**defaults)

    def test_execute_no_approval_needed(self):
        action = self._make_action()
        result = self.executor.execute(action)
        assert result.status == ActionStatus.EXECUTED
        assert result.execution_result is not None

    def test_execute_dry_run(self):
        action = self._make_action()
        result = self.executor.execute(action, dry_run=True)
        assert result.status == ActionStatus.EXECUTED
        assert result.execution_result.get("dry_run") is True

    def test_execute_requires_approval_not_approved(self):
        action = self._make_action(requires_approval=True)
        with pytest.raises(ValueError, match="requires approval"):
            self.executor.execute(action)

    def test_execute_approved_action(self):
        action = self._make_action(
            requires_approval=True,
            status=ActionStatus.APPROVED,
        )
        result = self.executor.execute(action)
        assert result.status == ActionStatus.EXECUTED

    def test_execute_rejected_action(self):
        action = self._make_action(
            requires_approval=True,
            status=ActionStatus.REJECTED,
        )
        with pytest.raises(ValueError, match="rejected"):
            self.executor.execute(action)

    def test_audit_log(self):
        action = self._make_action()
        self.executor.execute(action)
        log = self.executor.get_audit_log()
        assert len(log) == 1
        assert log[0]["action_id"] == action.id

    def test_rollback_execution(self):
        action = self._make_action(
            action_type=ActionType.ROLLBACK_DEPLOY,
            requires_approval=True,
            status=ActionStatus.APPROVED,
            parameters={"target_sha": "abc123"},
        )
        result = self.executor.execute(action)
        assert result.execution_result["rolled_back"] is True

    def test_rollback_dry_run(self):
        action = self._make_action(
            action_type=ActionType.ROLLBACK_DEPLOY,
            requires_approval=True,
            status=ActionStatus.APPROVED,
        )
        result = self.executor.execute(action, dry_run=True)
        assert result.execution_result["dry_run"] is True

    def test_all_action_types_execute(self):
        """Every action type should execute without error."""
        for action_type in ActionType:
            action = self._make_action(
                action_type=action_type,
                requires_approval=False,
            )
            result = self.executor.execute(action)
            assert result.status == ActionStatus.EXECUTED


# --- Approval ---


class TestApprovalWorkflow:
    def setup_method(self):
        self.workflow = ApprovalWorkflow()

    def _make_action(self):
        return SuggestedAction(
            action_type=ActionType.ROLLBACK_DEPLOY,
            target_service="api",
            description="Rollback",
            risk_level=RiskLevel.HIGH,
            incident_id="INC-1",
        )

    def test_submit_for_approval(self):
        action = self._make_action()
        result = self.workflow.submit_for_approval(action)
        assert result.status == ActionStatus.PENDING_APPROVAL
        assert self.workflow.get_action(action.id) is not None

    def test_approve(self):
        action = self._make_action()
        self.workflow.submit_for_approval(action)
        result = self.workflow.approve(action.id, "alice")
        assert result.status == ActionStatus.APPROVED
        assert result.approved_by == "alice"
        assert result.approved_at is not None

    def test_reject(self):
        action = self._make_action()
        self.workflow.submit_for_approval(action)
        result = self.workflow.reject(action.id, "bob", reason="Too risky")
        assert result.status == ActionStatus.REJECTED

    def test_approve_nonexistent(self):
        with pytest.raises(KeyError):
            self.workflow.approve("nonexistent", "alice")

    def test_reject_nonexistent(self):
        with pytest.raises(KeyError):
            self.workflow.reject("nonexistent", "bob")

    def test_double_approve(self):
        action = self._make_action()
        self.workflow.submit_for_approval(action)
        self.workflow.approve(action.id, "alice")
        with pytest.raises(ValueError, match="not pending"):
            self.workflow.approve(action.id, "bob")

    def test_get_pending(self):
        a1 = self._make_action()
        a2 = self._make_action()
        self.workflow.submit_for_approval(a1)
        self.workflow.submit_for_approval(a2)
        assert len(self.workflow.get_pending()) == 2
        self.workflow.approve(a1.id, "alice")
        assert len(self.workflow.get_pending()) == 1


# --- Slack ---


class TestSlackActions:
    def _make_action(self, **kwargs):
        defaults = {
            "action_type": ActionType.ROLLBACK_DEPLOY,
            "target_service": "api",
            "description": "Rollback api",
            "risk_level": RiskLevel.HIGH,
            "incident_id": "INC-1",
            "requires_approval": True,
        }
        defaults.update(kwargs)
        return SuggestedAction(**defaults)

    def test_build_action_buttons(self):
        actions = [self._make_action()]
        blocks = build_action_buttons(actions)
        assert len(blocks) == 2  # section + actions
        assert blocks[1]["type"] == "actions"
        # Should have approve, reject, dry-run buttons
        assert len(blocks[1]["elements"]) == 3

    def test_build_action_buttons_no_approval(self):
        actions = [self._make_action(requires_approval=False)]
        blocks = build_action_buttons(actions)
        # Should have execute + dry-run buttons
        assert len(blocks[1]["elements"]) == 2

    def test_build_verdict_with_actions(self):
        verdict = {
            "summary": "Test summary",
            "root_cause_hypothesis": "Bad deploy",
            "confidence": 85,
        }
        actions = [self._make_action()]
        blocks = build_verdict_with_actions(verdict, actions)
        assert blocks[0]["type"] == "header"
        assert "divider" in [b["type"] for b in blocks]

    def test_format_action_result(self):
        action = self._make_action(
            status=ActionStatus.EXECUTED,
            execution_result={"rolled_back": True},
        )
        blocks = format_action_result(action)
        assert len(blocks) == 1
        assert "Executed" in blocks[0]["text"]["text"]
