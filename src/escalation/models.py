"""
Escalation Policies - Data Models
Pydantic v2 models for escalation policies, levels, actions, and history.
"""

from datetime import datetime, time
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class ActionType(str, Enum):
    """Types of escalation actions."""
    PAGE = "page"
    EMAIL = "email"
    SLACK = "slack"
    PHONE = "phone"
    WEBHOOK = "webhook"
    SMS = "sms"


class Severity(str, Enum):
    """Incident severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class EscalationStatus(str, Enum):
    """Status of an escalation."""
    PENDING = "pending"
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SKIPPED = "skipped"
    OVERRIDDEN = "overridden"


class ConditionOperator(str, Enum):
    """Operators for condition evaluation."""
    EQUALS = "eq"
    NOT_EQUALS = "neq"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    IN = "in"
    NOT_IN = "not_in"
    MATCHES = "matches"  # regex


class TimeWindow(BaseModel):
    """Time window for condition-based escalation."""
    start_time: time = Field(..., description="Start time (HH:MM)")
    end_time: time = Field(..., description="End time (HH:MM)")
    days_of_week: list[int] = Field(
        default=[0, 1, 2, 3, 4, 5, 6],
        description="Days of week (0=Monday, 6=Sunday)"
    )
    timezone: str = Field(default="UTC")

    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: list[int]) -> list[int]:
        if not all(0 <= d <= 6 for d in v):
            raise ValueError("Days must be 0-6")
        return v


class EscalationCondition(BaseModel):
    """A condition that triggers escalation."""
    field: str = Field(..., description="Field to evaluate (e.g., 'severity', 'service')")
    operator: ConditionOperator
    value: Any
    time_window: TimeWindow | None = None

    def matches(self, context: dict[str, Any]) -> bool:
        """Check if condition matches the given context."""
        field_value = context.get(self.field)
        if field_value is None:
            return False

        if self.operator == ConditionOperator.EQUALS:
            return field_value == self.value
        elif self.operator == ConditionOperator.NOT_EQUALS:
            return field_value != self.value
        elif self.operator == ConditionOperator.CONTAINS:
            return self.value in str(field_value)
        elif self.operator == ConditionOperator.NOT_CONTAINS:
            return self.value not in str(field_value)
        elif self.operator == ConditionOperator.GREATER_THAN:
            return field_value > self.value
        elif self.operator == ConditionOperator.LESS_THAN:
            return field_value < self.value
        elif self.operator == ConditionOperator.IN:
            return field_value in self.value
        elif self.operator == ConditionOperator.NOT_IN:
            return field_value not in self.value
        elif self.operator == ConditionOperator.MATCHES:
            import re
            return bool(re.match(self.value, str(field_value)))
        return False


class EscalationAction(BaseModel):
    """An action to perform during escalation."""
    id: UUID = Field(default_factory=uuid4)
    action_type: ActionType
    target: str = Field(..., description="Target (email, phone, slack channel, etc.)")
    template: str | None = Field(None, description="Message template")
    metadata: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: int = Field(default=60, ge=0)


class OnCallAssignment(BaseModel):
    """On-call schedule assignment."""
    user_id: str
    user_name: str
    user_email: str
    user_phone: str | None = None
    slack_id: str | None = None
    start_time: datetime
    end_time: datetime
    is_primary: bool = True
    team_id: str | None = None


class TeamRotation(BaseModel):
    """Team rotation configuration."""
    id: UUID = Field(default_factory=uuid4)
    team_id: str
    team_name: str
    rotation_type: str = Field(default="weekly")  # weekly, daily, custom
    members: list[OnCallAssignment] = Field(default_factory=list)
    current_index: int = Field(default=0)
    last_rotation: datetime | None = None


class EscalationLevel(BaseModel):
    """A level in the escalation chain."""
    level: int = Field(..., ge=1, le=10, description="Level number (1=L1, 2=L2, etc.)")
    name: str = Field(..., description="Level name (e.g., 'L1 Support', 'Manager')")
    delay_minutes: int = Field(
        default=15,
        ge=0,
        description="Minutes to wait before escalating to this level"
    )
    actions: list[EscalationAction] = Field(default_factory=list)
    conditions: list[EscalationCondition] = Field(default_factory=list)
    use_oncall: bool = Field(default=True, description="Use on-call schedule for targets")
    team_id: str | None = Field(None, description="Team ID for on-call lookup")
    fallback_targets: list[str] = Field(
        default_factory=list,
        description="Fallback targets if no on-call found"
    )
    auto_acknowledge_minutes: int | None = Field(
        None,
        description="Auto-acknowledge if no response after N minutes"
    )

    def get_effective_targets(self, oncall: "OnCallAssignment | None") -> list[str]:
        """Get targets, preferring on-call if available."""
        if self.use_oncall and oncall:
            targets = []
            for action in self.actions:
                if action.action_type == ActionType.EMAIL:
                    targets.append(oncall.user_email)
                elif action.action_type in (ActionType.PHONE, ActionType.SMS):
                    if oncall.user_phone:
                        targets.append(oncall.user_phone)
                elif action.action_type == ActionType.SLACK:
                    if oncall.slack_id:
                        targets.append(oncall.slack_id)
                else:
                    targets.append(action.target)
            return targets or self.fallback_targets
        return self.fallback_targets


class DeescalationRule(BaseModel):
    """Rule for automatic de-escalation."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    conditions: list[EscalationCondition] = Field(default_factory=list)
    target_level: int = Field(..., ge=1, description="Level to de-escalate to")
    cooldown_minutes: int = Field(default=30, description="Cooldown before re-escalation")


class EscalationPolicy(BaseModel):
    """Complete escalation policy configuration."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    enabled: bool = True
    priority: int = Field(default=0, description="Higher priority policies evaluated first")
    
    # Matching criteria
    services: list[str] = Field(default_factory=list, description="Services this policy applies to")
    severities: list[Severity] = Field(default_factory=list)
    conditions: list[EscalationCondition] = Field(default_factory=list)
    
    # Escalation chain
    levels: list[EscalationLevel] = Field(default_factory=list)
    deescalation_rules: list[DeescalationRule] = Field(default_factory=list)
    
    # Behavior
    repeat_enabled: bool = Field(default=False, description="Repeat escalation cycle if unresolved")
    repeat_delay_minutes: int = Field(default=60)
    max_repeats: int = Field(default=3)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, v: list[EscalationLevel]) -> list[EscalationLevel]:
        """Ensure levels are sequential and unique."""
        if not v:
            return v
        levels = sorted(v, key=lambda x: x.level)
        seen = set()
        for level in levels:
            if level.level in seen:
                raise ValueError(f"Duplicate level: {level.level}")
            seen.add(level.level)
        return levels


class EscalationHistoryEntry(BaseModel):
    """A single entry in escalation history."""
    id: UUID = Field(default_factory=uuid4)
    incident_id: str
    policy_id: UUID
    policy_name: str
    level: int
    level_name: str
    status: EscalationStatus
    action_type: ActionType | None = None
    target: str | None = None
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    skipped_reason: str | None = None
    override_reason: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationState(BaseModel):
    """Current escalation state for an incident."""
    incident_id: str
    policy_id: UUID
    current_level: int = 1
    status: EscalationStatus = EscalationStatus.PENDING
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_escalation_at: datetime | None = None
    next_escalation_at: datetime | None = None
    repeat_count: int = 0
    is_paused: bool = False
    paused_until: datetime | None = None
    history: list[EscalationHistoryEntry] = Field(default_factory=list)


# Request/Response models for API
class CreatePolicyRequest(BaseModel):
    """Request to create a new escalation policy."""
    name: str
    description: str | None = None
    services: list[str] = Field(default_factory=list)
    severities: list[Severity] = Field(default_factory=list)
    conditions: list[EscalationCondition] = Field(default_factory=list)
    levels: list[EscalationLevel] = Field(default_factory=list)
    deescalation_rules: list[DeescalationRule] = Field(default_factory=list)
    priority: int = 0
    repeat_enabled: bool = False
    repeat_delay_minutes: int = 60
    max_repeats: int = 3
    tags: list[str] = Field(default_factory=list)


class UpdatePolicyRequest(BaseModel):
    """Request to update an escalation policy."""
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    services: list[str] | None = None
    severities: list[Severity] | None = None
    conditions: list[EscalationCondition] | None = None
    levels: list[EscalationLevel] | None = None
    deescalation_rules: list[DeescalationRule] | None = None
    priority: int | None = None
    repeat_enabled: bool | None = None
    repeat_delay_minutes: int | None = None
    max_repeats: int | None = None
    tags: list[str] | None = None


class TriggerEscalationRequest(BaseModel):
    """Request to manually trigger escalation."""
    incident_id: str
    policy_id: UUID | None = None
    target_level: int | None = None
    reason: str | None = None
    skip_conditions: bool = False


class OverrideEscalationRequest(BaseModel):
    """Request to override/skip escalation."""
    incident_id: str
    action: str = Field(..., pattern="^(skip|pause|resume|override)$")
    reason: str
    target_level: int | None = None
    pause_until: datetime | None = None


class EscalationHistoryFilter(BaseModel):
    """Filter for querying escalation history."""
    incident_id: str | None = None
    policy_id: UUID | None = None
    status: EscalationStatus | None = None
    level: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
