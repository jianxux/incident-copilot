"""Action engine that generates suggested actions based on verdict and context."""

from typing import Any

import structlog

from .models import ActionType, RiskLevel, SuggestedAction

logger = structlog.get_logger(__name__)


class ActionEngine:
    """Generates suggested remediation actions from investigation verdicts."""

    def __init__(self) -> None:
        self.logger = logger.bind(component="action_engine")

    def generate_actions(
        self, verdict: dict[str, Any], context: dict[str, Any]
    ) -> list[SuggestedAction]:
        """Generate suggested actions based on verdict and context."""
        actions: list[SuggestedAction] = []
        incident_id = context.get("incident_id", "unknown")
        service = context.get("service", verdict.get("service", "unknown"))

        # Rollback if recommended
        if verdict.get("rollback_recommended"):
            deploy_sha = verdict.get("rollback_target", "previous")
            risk = RiskLevel.HIGH
            actions.append(
                SuggestedAction(
                    action_type=ActionType.ROLLBACK_DEPLOY,
                    target_service=service,
                    description=f"Rollback {service} to {deploy_sha}",
                    risk_level=risk,
                    requires_approval=self._needs_approval(risk),
                    parameters={"target_sha": deploy_sha},
                    incident_id=incident_id,
                )
            )

        # Check recommended_actions from verdict
        for rec in verdict.get("recommended_actions", []):
            rec_lower = rec.lower() if isinstance(rec, str) else ""
            if "scale" in rec_lower:
                risk = RiskLevel.MEDIUM
                actions.append(
                    SuggestedAction(
                        action_type=ActionType.SCALE_SERVICE,
                        target_service=service,
                        description=f"Scale {service}: {rec}",
                        risk_level=risk,
                        requires_approval=self._needs_approval(risk),
                        parameters={"recommendation": rec},
                        incident_id=incident_id,
                    )
                )
            elif "restart" in rec_lower:
                risk = RiskLevel.MEDIUM
                actions.append(
                    SuggestedAction(
                        action_type=ActionType.RESTART_PODS,
                        target_service=service,
                        description=f"Restart {service} pods",
                        risk_level=risk,
                        requires_approval=self._needs_approval(risk),
                        parameters={"recommendation": rec},
                        incident_id=incident_id,
                    )
                )
            elif "feature" in rec_lower and "flag" in rec_lower:
                risk = RiskLevel.LOW
                actions.append(
                    SuggestedAction(
                        action_type=ActionType.TOGGLE_FEATURE_FLAG,
                        target_service=service,
                        description=f"Toggle feature flag: {rec}",
                        risk_level=risk,
                        requires_approval=self._needs_approval(risk),
                        parameters={"recommendation": rec},
                        incident_id=incident_id,
                    )
                )
            elif "runbook" in rec_lower:
                risk = RiskLevel.LOW
                actions.append(
                    SuggestedAction(
                        action_type=ActionType.RUN_RUNBOOK,
                        target_service=service,
                        description=f"Run runbook: {rec}",
                        risk_level=risk,
                        requires_approval=self._needs_approval(risk),
                        parameters={"recommendation": rec},
                        incident_id=incident_id,
                    )
                )

        # If severity is high, suggest paging on-call
        severity = context.get("severity", "")
        if severity in ("P1", "P0", "critical", "high"):
            risk = RiskLevel.LOW
            actions.append(
                SuggestedAction(
                    action_type=ActionType.PAGE_ONCALL,
                    target_service=service,
                    description=f"Page on-call engineer for {service}",
                    risk_level=risk,
                    requires_approval=False,
                    parameters={"severity": severity},
                    incident_id=incident_id,
                )
            )

        # Suggest silencing alert if noisy
        if context.get("alert_count", 0) > 5:
            risk = RiskLevel.LOW
            actions.append(
                SuggestedAction(
                    action_type=ActionType.SILENCE_ALERT,
                    target_service=service,
                    description=f"Silence duplicate alerts for {service}",
                    risk_level=risk,
                    requires_approval=False,
                    parameters={"alert_count": context["alert_count"]},
                    incident_id=incident_id,
                )
            )

        # Always suggest creating a JIRA ticket
        actions.append(
            SuggestedAction(
                action_type=ActionType.CREATE_JIRA,
                target_service=service,
                description=f"Create JIRA ticket for incident {incident_id}",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                parameters={
                    "summary": verdict.get("summary", f"Incident {incident_id}"),
                    "root_cause": verdict.get("root_cause_hypothesis", ""),
                },
                incident_id=incident_id,
            )
        )

        self.logger.info(
            "actions_generated",
            incident_id=incident_id,
            count=len(actions),
            types=[a.action_type for a in actions],
        )
        return actions

    def _estimate_risk(
        self, action_type: ActionType, context: dict[str, Any]
    ) -> RiskLevel:
        """Estimate risk level for an action type."""
        high_risk = {ActionType.ROLLBACK_DEPLOY, ActionType.RESTART_PODS}
        medium_risk = {ActionType.SCALE_SERVICE, ActionType.TOGGLE_FEATURE_FLAG}

        if action_type in high_risk:
            return RiskLevel.HIGH
        if action_type in medium_risk:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _needs_approval(self, risk_level: RiskLevel) -> bool:
        """Determine if an action needs approval based on risk."""
        return risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
