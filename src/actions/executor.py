"""Action executor with dry-run mode and audit trail."""

from datetime import UTC, datetime
from typing import Any

import structlog

from .models import ActionStatus, ActionType, SuggestedAction

logger = structlog.get_logger(__name__)


class ActionExecutor:
    """Executes suggested actions with dry-run support and audit logging."""

    def __init__(self) -> None:
        self.logger = logger.bind(component="action_executor")
        self._audit_log: list[dict[str, Any]] = []

    def execute(
        self, action: SuggestedAction, dry_run: bool = False
    ) -> SuggestedAction:
        """Execute a suggested action."""
        # Validate action can be executed
        if action.requires_approval and action.status not in (
            ActionStatus.APPROVED,
            ActionStatus.SUGGESTED,
        ):
            if action.status == ActionStatus.REJECTED:
                raise ValueError(f"Action {action.id} was rejected")
            if action.status == ActionStatus.PENDING_APPROVAL:
                raise ValueError(f"Action {action.id} is pending approval")

        if action.requires_approval and action.status != ActionStatus.APPROVED:
            raise ValueError(
                f"Action {action.id} requires approval before execution"
            )

        action.status = ActionStatus.EXECUTING
        action.dry_run = dry_run

        try:
            result = self._dispatch(action, dry_run)
            action.status = ActionStatus.EXECUTED
            action.executed_at = datetime.now(UTC)
            action.execution_result = result
            self.logger.info(
                "action_executed",
                action_id=action.id,
                action_type=action.action_type,
                dry_run=dry_run,
            )
        except Exception as e:
            action.status = ActionStatus.FAILED
            action.execution_result = {"error": str(e)}
            self.logger.error(
                "action_failed",
                action_id=action.id,
                action_type=action.action_type,
                error=str(e),
            )

        self._audit_log.append(
            {
                "action_id": action.id,
                "action_type": action.action_type,
                "target_service": action.target_service,
                "status": action.status,
                "dry_run": dry_run,
                "timestamp": datetime.now(UTC).isoformat(),
                "result": action.execution_result,
            }
        )

        return action

    def _dispatch(self, action: SuggestedAction, dry_run: bool) -> dict[str, Any]:
        """Dispatch action to the appropriate handler."""
        handlers = {
            ActionType.ROLLBACK_DEPLOY: self._execute_rollback,
            ActionType.SCALE_SERVICE: self._execute_scale,
            ActionType.RESTART_PODS: self._execute_restart,
            ActionType.TOGGLE_FEATURE_FLAG: self._execute_feature_flag,
            ActionType.RUN_RUNBOOK: self._execute_runbook,
            ActionType.SILENCE_ALERT: self._execute_silence,
            ActionType.PAGE_ONCALL: self._execute_page,
            ActionType.CREATE_JIRA: self._execute_jira,
        }
        handler = handlers.get(action.action_type)
        if not handler:
            raise ValueError(f"Unknown action type: {action.action_type}")
        return handler(action, dry_run)

    def _execute_rollback(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        target_sha = action.parameters.get("target_sha", "previous")
        if dry_run:
            return {
                "dry_run": True,
                "would_rollback": action.target_service,
                "target_sha": target_sha,
            }
        return {
            "rolled_back": True,
            "service": action.target_service,
            "target_sha": target_sha,
            "message": f"Deployment rollback initiated for {action.target_service}",
        }

    def _execute_scale(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        replicas = action.parameters.get("replicas", 3)
        if dry_run:
            return {
                "dry_run": True,
                "would_scale": action.target_service,
                "target_replicas": replicas,
            }
        return {
            "scaled": True,
            "service": action.target_service,
            "replicas": replicas,
        }

    def _execute_restart(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        if dry_run:
            return {"dry_run": True, "would_restart": action.target_service}
        return {
            "restarted": True,
            "service": action.target_service,
            "message": f"Rolling restart initiated for {action.target_service}",
        }

    def _execute_feature_flag(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        flag = action.parameters.get("flag_name", "unknown")
        if dry_run:
            return {"dry_run": True, "would_toggle": flag}
        return {"toggled": True, "flag": flag}

    def _execute_runbook(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        runbook = action.parameters.get("runbook_id", "default")
        if dry_run:
            return {"dry_run": True, "would_run": runbook}
        return {"executed": True, "runbook": runbook}

    def _execute_silence(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        duration = action.parameters.get("duration_minutes", 30)
        if dry_run:
            return {
                "dry_run": True,
                "would_silence": action.target_service,
                "duration_minutes": duration,
            }
        return {
            "silenced": True,
            "service": action.target_service,
            "duration_minutes": duration,
        }

    def _execute_page(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        if dry_run:
            return {"dry_run": True, "would_page": action.target_service}
        return {
            "paged": True,
            "service": action.target_service,
            "message": f"On-call paged for {action.target_service}",
        }

    def _execute_jira(
        self, action: SuggestedAction, dry_run: bool
    ) -> dict[str, Any]:
        summary = action.parameters.get("summary", "Incident")
        if dry_run:
            return {"dry_run": True, "would_create": summary}
        return {
            "created": True,
            "ticket": f"INC-{action.incident_id[:8].upper()}",
            "summary": summary,
        }

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return the audit trail."""
        return list(self._audit_log)
