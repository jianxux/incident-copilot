"""Data models for the Escalation Rules Engine."""

import secrets
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ServiceTier(str, Enum):
    """Service tier levels for escalation priority."""

    CRITICAL = "critical"  # Tier 0 - Revenue-critical services
    HIGH = "high"  # Tier 1 - Customer-facing services
    MEDIUM = "medium"  # Tier 2 - Internal services
    LOW = "low"  # Tier 3 - Non-critical services


class ConditionType(str, Enum):
    """Types of conditions that can trigger escalation."""

    TIME_SINCE_ALERT = "time_since_alert"  # Minutes since alert created
    TIME_SINCE_ACK = "time_since_ack"  # Minutes since acknowledged
    SEVERITY = "severity"  # Alert severity level
    UNACKNOWLEDGED = "unacknowledged"  # Alert not acknowledged
    NO_RESPONSE = "no_response"  # No response from assignee
    SERVICE_TIER = "service_tier"  # Service tier level
    CUSTOM = "custom"  # Custom condition with expression


class ConditionOperator(str, Enum):
    """Operators for condition evaluation."""

    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUALS = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUALS = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    MATCHES = "matches"  # Regex match


class ActionType(str, Enum):
    """Types of actions that can be triggered by escalation."""

    NOTIFY = "notify"  # Send notification (email, Slack, etc.)
    PAGE = "page"  # Page via PagerDuty/Opsgenie
    UPDATE_SEVERITY = "update_severity"  # Increase severity level
    AUTO_ASSIGN = "auto_assign"  # Assign to user/team
    ESCALATE_TO_MANAGER = "escalate_to_manager"  # Escalate to manager
    CREATE_INCIDENT = "create_incident"  # Create linked incident
    RUN_WEBHOOK = "run_webhook"  # Trigger external webhook
    ADD_RESPONDER = "add_responder"  # Add additional responder
    POST_TO_CHANNEL = "post_to_channel"  # Post to Slack/Teams channel


class EscalationCondition(BaseModel):
    """A single condition for escalation evaluation."""

    condition_type: ConditionType
    operator: ConditionOperator = ConditionOperator.EQUALS
    value: Any  # The value to compare against
    field: str | None = None  # Optional field path for custom conditions

    model_config = ConfigDict(use_enum_values=True)

    def __str__(self) -> str:
        return f"{self.condition_type} {self.operator} {self.value}"


class EscalationAction(BaseModel):
    """An action to execute when escalation is triggered."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(8))
    action_type: ActionType
    target: str | None = None  # Target user, team, or channel
    target_id: str | None = None  # Target ID (user_id, team_id, etc.)
    params: dict[str, Any] = Field(default_factory=dict)  # Action-specific parameters
    retry_count: int = 3  # Number of retries on failure
    retry_delay_seconds: int = 30  # Delay between retries

    model_config = ConfigDict(use_enum_values=True)


class EscalationStep(BaseModel):
    """A step in a multi-step escalation policy.

    Example: 5min -> primary, 15min -> secondary, 30min -> manager
    """

    step_number: int
    delay_minutes: int  # Minutes after alert before this step triggers
    conditions: list[EscalationCondition] = Field(default_factory=list)
    actions: list[EscalationAction]
    repeat: bool = False  # Whether to repeat this step
    repeat_interval_minutes: int = 30  # Interval for repeat


class EscalationRule(BaseModel):
    """A single escalation rule with conditions and actions."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    name: str
    description: str | None = None
    enabled: bool = True
    priority: int = 100  # Lower number = higher priority

    # Matching criteria
    service_pattern: str | None = None  # Regex pattern to match service names
    team_id: str | None = None  # Team this rule applies to
    severity_filter: list[str] | None = None  # Only apply to these severities
    tag_filters: dict[str, str] = Field(default_factory=dict)  # Tag-based filtering

    # Conditions and actions
    conditions: list[EscalationCondition] = Field(default_factory=list)
    actions: list[EscalationAction] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
        use_enum_values=True,
    )


class EscalationPolicy(BaseModel):
    """A complete escalation policy with multiple steps.

    Policies can be assigned per-service or per-team and support
    multi-step escalation chains.
    """

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    name: str
    description: str | None = None
    enabled: bool = True

    # Scope
    service_id: str | None = None  # Apply to specific service
    service_pattern: str | None = None  # Apply to services matching pattern
    team_id: str | None = None  # Apply to specific team
    service_tier: ServiceTier | None = None  # Apply to service tier

    # Escalation steps (ordered by step_number)
    steps: list[EscalationStep] = Field(default_factory=list)

    # Default targets
    primary_responder: str | None = None  # Default primary responder
    secondary_responder: str | None = None  # Default secondary responder
    manager: str | None = None  # Manager for final escalation

    # Override settings
    skip_during_maintenance: bool = True  # Skip escalation during maintenance
    business_hours_only: bool = False  # Only escalate during business hours
    business_hours_start: int = 9  # Start of business hours (0-23)
    business_hours_end: int = 17  # End of business hours (0-23)
    timezone: str = "UTC"

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    tenant_id: str | None = None

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
        use_enum_values=True,
    )

    def get_step_for_time(self, minutes_elapsed: int) -> EscalationStep | None:
        """Get the appropriate escalation step for elapsed time."""
        applicable_step = None
        for step in sorted(self.steps, key=lambda s: s.delay_minutes):
            if minutes_elapsed >= step.delay_minutes:
                applicable_step = step
            else:
                break
        return applicable_step


class MaintenanceWindow(BaseModel):
    """A maintenance window during which escalations are suppressed."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    name: str
    description: str | None = None

    # Scope
    service_id: str | None = None  # Apply to specific service
    service_pattern: str | None = None  # Apply to services matching pattern
    team_id: str | None = None  # Apply to specific team

    # Time window
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"

    # Suppression settings
    suppress_notifications: bool = True
    suppress_pages: bool = True
    suppress_escalations: bool = True

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    tenant_id: str | None = None

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    def is_active(self, at_time: datetime | None = None) -> bool:
        """Check if maintenance window is currently active."""
        check_time = at_time or datetime.utcnow()
        return self.start_time <= check_time <= self.end_time


class IncidentState(BaseModel):
    """Current state of an incident for escalation evaluation."""

    incident_id: str
    title: str
    service: str
    service_tier: ServiceTier | None = None
    severity: str
    status: str  # triggered, acknowledged, resolved

    # Timestamps
    triggered_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    last_activity_at: datetime | None = None

    # Assignment
    assigned_to: list[str] = Field(default_factory=list)
    team_id: str | None = None

    # Metadata
    tags: dict[str, str] = Field(default_factory=dict)
    source: str = "unknown"  # pagerduty, opsgenie, manual
    url: str | None = None
    tenant_id: str | None = None

    # Escalation tracking
    current_escalation_step: int = 0
    escalation_policy_id: str | None = None
    last_escalation_at: datetime | None = None
    escalation_count: int = 0

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_at is not None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    @property
    def minutes_since_triggered(self) -> float:
        delta = datetime.utcnow() - self.triggered_at
        return delta.total_seconds() / 60

    @property
    def minutes_since_acknowledged(self) -> float | None:
        if not self.acknowledged_at:
            return None
        delta = datetime.utcnow() - self.acknowledged_at
        return delta.total_seconds() / 60

    @property
    def minutes_since_last_activity(self) -> float | None:
        if not self.last_activity_at:
            return None
        delta = datetime.utcnow() - self.last_activity_at
        return delta.total_seconds() / 60


class EscalationResult(BaseModel):
    """Result of an escalation evaluation."""

    incident_id: str
    triggered: bool
    rule_id: str | None = None
    policy_id: str | None = None
    step_number: int | None = None
    actions_executed: list[str] = Field(default_factory=list)
    actions_failed: list[str] = Field(default_factory=list)
    suppressed: bool = False
    suppression_reason: str | None = None
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(ser_json_timedelta="iso8601")


class EscalationAuditEntry(BaseModel):
    """Audit log entry for escalation events."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    incident_id: str
    policy_id: str | None = None
    rule_id: str | None = None
    step_number: int | None = None

    # Event details
    event_type: str  # escalation_triggered, action_executed, action_failed, suppressed
    action_type: ActionType | None = None
    target: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    # Outcome
    success: bool = True
    error_message: str | None = None

    # Tenant
    tenant_id: str | None = None

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
        use_enum_values=True,
    )


# Request/Response models for API


class CreatePolicyRequest(BaseModel):
    """Request to create a new escalation policy."""

    name: str
    description: str | None = None
    service_id: str | None = None
    service_pattern: str | None = None
    team_id: str | None = None
    service_tier: ServiceTier | None = None
    steps: list[EscalationStep]
    primary_responder: str | None = None
    secondary_responder: str | None = None
    manager: str | None = None
    skip_during_maintenance: bool = True
    business_hours_only: bool = False


class UpdatePolicyRequest(BaseModel):
    """Request to update an existing escalation policy."""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    service_id: str | None = None
    service_pattern: str | None = None
    team_id: str | None = None
    service_tier: ServiceTier | None = None
    steps: list[EscalationStep] | None = None
    primary_responder: str | None = None
    secondary_responder: str | None = None
    manager: str | None = None
    skip_during_maintenance: bool | None = None
    business_hours_only: bool | None = None


class CreateRuleRequest(BaseModel):
    """Request to create a new escalation rule."""

    name: str
    description: str | None = None
    priority: int = 100
    service_pattern: str | None = None
    team_id: str | None = None
    severity_filter: list[str] | None = None
    conditions: list[EscalationCondition]
    actions: list[EscalationAction]


class CreateMaintenanceWindowRequest(BaseModel):
    """Request to create a maintenance window."""

    name: str
    description: str | None = None
    service_id: str | None = None
    service_pattern: str | None = None
    team_id: str | None = None
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    suppress_notifications: bool = True
    suppress_pages: bool = True
    suppress_escalations: bool = True


class PolicyListResponse(BaseModel):
    """Response for listing escalation policies."""

    policies: list[EscalationPolicy]
    total: int
    limit: int
    offset: int


class RuleListResponse(BaseModel):
    """Response for listing escalation rules."""

    rules: list[EscalationRule]
    total: int
    limit: int
    offset: int


class AuditListResponse(BaseModel):
    """Response for listing escalation audit entries."""

    entries: list[EscalationAuditEntry]
    total: int
    limit: int
    offset: int
