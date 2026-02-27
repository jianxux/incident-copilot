"""Approval workflow for suggested actions."""

from datetime import UTC, datetime

import structlog

from .models import ActionStatus, SuggestedAction

logger = structlog.get_logger(__name__)


class ApprovalWorkflow:
    """Manages approval workflow for high-risk actions."""

    def __init__(self) -> None:
        self.logger = logger.bind(component="approval_workflow")
        self._pending: dict[str, SuggestedAction] = {}

    def submit_for_approval(self, action: SuggestedAction) -> SuggestedAction:
        """Submit an action for approval."""
        action.status = ActionStatus.PENDING_APPROVAL
        self._pending[action.id] = action
        self.logger.info(
            "action_submitted_for_approval",
            action_id=action.id,
            action_type=action.action_type,
            risk_level=action.risk_level,
        )
        return action

    def approve(
        self, action_id: str, approved_by: str, reason: str | None = None
    ) -> SuggestedAction:
        """Approve a pending action."""
        action = self._pending.get(action_id)
        if not action:
            raise KeyError(f"Action {action_id} not found in pending approvals")
        if action.status != ActionStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Action {action_id} is not pending approval (status: {action.status})"
            )

        action.status = ActionStatus.APPROVED
        action.approved_by = approved_by
        action.approved_at = datetime.now(UTC)
        self.logger.info(
            "action_approved",
            action_id=action_id,
            approved_by=approved_by,
            reason=reason,
        )
        return action

    def reject(
        self, action_id: str, rejected_by: str, reason: str | None = None
    ) -> SuggestedAction:
        """Reject a pending action."""
        action = self._pending.get(action_id)
        if not action:
            raise KeyError(f"Action {action_id} not found in pending approvals")
        if action.status != ActionStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Action {action_id} is not pending approval (status: {action.status})"
            )

        action.status = ActionStatus.REJECTED
        action.approved_by = rejected_by
        action.approved_at = datetime.now(UTC)
        self.logger.info(
            "action_rejected",
            action_id=action_id,
            rejected_by=rejected_by,
            reason=reason,
        )
        return action

    def get_pending(self) -> list[SuggestedAction]:
        """Return all pending actions."""
        return [
            a
            for a in self._pending.values()
            if a.status == ActionStatus.PENDING_APPROVAL
        ]

    def get_action(self, action_id: str) -> SuggestedAction | None:
        """Get an action by ID."""
        return self._pending.get(action_id)
