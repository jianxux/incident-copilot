"""Data models for suggested actions."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    """Types of actions that can be suggested."""

    ROLLBACK_DEPLOY = "rollback_deploy"
    SCALE_SERVICE = "scale_service"
    RESTART_PODS = "restart_pods"
    TOGGLE_FEATURE_FLAG = "toggle_feature_flag"
    RUN_RUNBOOK = "run_runbook"
    SILENCE_ALERT = "silence_alert"
    PAGE_ONCALL = "page_oncall"
    CREATE_JIRA = "create_jira"


class RiskLevel(StrEnum):
    """Risk levels for actions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(StrEnum):
    """Status of a suggested action."""

    SUGGESTED = "suggested"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"


class SuggestedAction(BaseModel):
    """A suggested remediation action for an incident."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: ActionType
    target_service: str
    description: str
    risk_level: RiskLevel
    requires_approval: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: ActionStatus = ActionStatus.SUGGESTED
    incident_id: str
    suggested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    suggested_by: str = "copilot"
    approved_by: str | None = None
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    execution_result: dict[str, Any] | None = None
    dry_run: bool = False


class ActionApproval(BaseModel):
    """Approval or rejection of an action."""

    action_id: str
    approved_by: str
    approved: bool
    reason: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
