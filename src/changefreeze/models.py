"""Data models for Change Freeze Management."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FreezeStatus(str, Enum):
    """Status of a change freeze."""

    SCHEDULED = "scheduled"  # Freeze period not yet started
    ACTIVE = "active"  # Currently in freeze period
    COMPLETED = "completed"  # Freeze period has ended
    CANCELLED = "cancelled"  # Freeze was cancelled before completion


class FreezeScope(str, Enum):
    """Scope of the change freeze."""

    GLOBAL = "global"  # Applies to all services
    SERVICE = "service"  # Applies to specific services only
    ENVIRONMENT = "environment"  # Applies to specific environments (prod, staging)
    TEAM = "team"  # Applies to specific team's services


class ApprovalStatus(str, Enum):
    """Status of a freeze exception request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"  # Request expired without decision


class ViolationSeverity(str, Enum):
    """Severity of a freeze violation."""

    CRITICAL = "critical"  # Production deployment during global freeze
    HIGH = "high"  # Production deployment during service freeze
    MEDIUM = "medium"  # Staging deployment during freeze
    LOW = "low"  # Non-production environment deployment


class ChangeFreeze(BaseModel):
    """A change freeze period definition."""

    freeze_id: str = Field(description="Unique identifier for the freeze")
    name: str = Field(description="Human-readable name (e.g., 'Holiday Freeze 2024')")
    description: str | None = Field(default=None, description="Detailed description")
    
    # Timing
    starts_at: datetime = Field(description="When the freeze period begins")
    ends_at: datetime = Field(description="When the freeze period ends")
    
    # Scope
    scope: FreezeScope = Field(default=FreezeScope.GLOBAL)
    services: list[str] = Field(
        default_factory=list,
        description="List of services affected (if scope is SERVICE)"
    )
    environments: list[str] = Field(
        default_factory=list,
        description="Environments affected (e.g., ['production', 'staging'])"
    )
    teams: list[str] = Field(
        default_factory=list,
        description="Teams affected (if scope is TEAM)"
    )
    
    # Status
    status: FreezeStatus = Field(default=FreezeStatus.SCHEDULED)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(description="User who created the freeze")
    updated_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by: str | None = None
    cancellation_reason: str | None = None
    
    # Configuration
    allow_emergency_deployments: bool = Field(
        default=True,
        description="Allow pre-approved emergency deployments"
    )
    require_approval_for_exceptions: bool = Field(
        default=True,
        description="Require explicit approval for exceptions"
    )
    notification_channels: list[str] = Field(
        default_factory=list,
        description="Slack channels/email lists to notify"
    )
    approvers: list[str] = Field(
        default_factory=list,
        description="Users who can approve exceptions"
    )
    
    # Statistics (updated as events occur)
    total_exceptions_requested: int = 0
    total_exceptions_approved: int = 0
    total_violations: int = 0

    def is_active(self, at_time: datetime | None = None) -> bool:
        """Check if freeze is currently active."""
        check_time = at_time or datetime.utcnow()
        return (
            self.status in (FreezeStatus.SCHEDULED, FreezeStatus.ACTIVE)
            and self.starts_at <= check_time <= self.ends_at
        )

    def affects_service(self, service_name: str) -> bool:
        """Check if this freeze affects a specific service."""
        if self.scope == FreezeScope.GLOBAL:
            return True
        if self.scope == FreezeScope.SERVICE:
            return service_name in self.services
        return False

    def affects_environment(self, environment: str) -> bool:
        """Check if this freeze affects a specific environment."""
        if not self.environments:
            return True  # No environment restriction = all environments
        return environment.lower() in [e.lower() for e in self.environments]


class FreezeException(BaseModel):
    """A request for exception from a change freeze."""

    exception_id: str = Field(description="Unique identifier for the exception")
    freeze_id: str = Field(description="ID of the freeze this exception is for")
    
    # Request details
    requested_by: str = Field(description="User requesting the exception")
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    
    service_name: str = Field(description="Service that needs to deploy")
    environment: str = Field(default="production")
    
    reason: str = Field(description="Reason for the exception request")
    justification: str | None = Field(
        default=None,
        description="Detailed business/technical justification"
    )
    risk_assessment: str | None = Field(
        default=None,
        description="Assessment of deployment risks"
    )
    rollback_plan: str | None = Field(
        default=None,
        description="Plan for rollback if issues occur"
    )
    
    # Emergency flag
    is_emergency: bool = Field(
        default=False,
        description="Pre-approved emergency deployment"
    )
    emergency_ticket_id: str | None = Field(
        default=None,
        description="Incident/ticket ID for emergency deployments"
    )
    
    # Approval workflow
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    
    # Time window
    valid_from: datetime | None = Field(
        default=None,
        description="Start of approved deployment window"
    )
    valid_until: datetime | None = Field(
        default=None,
        description="End of approved deployment window"
    )
    
    # Tracking
    deployment_completed: bool = False
    deployment_completed_at: datetime | None = None
    deployment_event_ids: list[str] = Field(default_factory=list)

    def is_valid(self, at_time: datetime | None = None) -> bool:
        """Check if exception is currently valid for deployment."""
        if self.status != ApprovalStatus.APPROVED:
            return False
        
        check_time = at_time or datetime.utcnow()
        
        if self.valid_from and check_time < self.valid_from:
            return False
        if self.valid_until and check_time > self.valid_until:
            return False
        
        return True


class DeploymentEvent(BaseModel):
    """A deployment event detected from GitHub webhooks or other sources."""

    event_id: str = Field(description="Unique identifier for the event")
    
    # Source information
    source: str = Field(
        default="github",
        description="Source of the deployment event (github, gitlab, custom)"
    )
    source_event_id: str | None = Field(
        default=None,
        description="Original event ID from source system"
    )
    
    # Deployment details
    service_name: str = Field(description="Service being deployed")
    repository: str = Field(description="Repository name (org/repo)")
    environment: str = Field(default="production")
    
    # Git details
    commit_sha: str | None = None
    commit_message: str | None = None
    branch: str | None = None
    tag: str | None = None
    
    # Actor
    deployed_by: str = Field(description="User who triggered deployment")
    deployed_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Freeze context
    during_freeze: bool = Field(
        default=False,
        description="Whether deployment occurred during a freeze"
    )
    freeze_id: str | None = Field(
        default=None,
        description="ID of active freeze if during_freeze is True"
    )
    exception_id: str | None = Field(
        default=None,
        description="ID of approved exception (if any)"
    )
    
    # Violation tracking
    is_violation: bool = Field(
        default=False,
        description="Whether this deployment is a freeze violation"
    )
    violation_id: str | None = None
    
    # Metadata
    metadata: dict = Field(
        default_factory=dict,
        description="Additional event metadata"
    )


class FreezeViolation(BaseModel):
    """An audit record of a change freeze violation."""

    violation_id: str = Field(description="Unique identifier for the violation")
    
    # References
    freeze_id: str = Field(description="ID of the violated freeze")
    deployment_event_id: str = Field(description="ID of the deployment event")
    
    # Details
    service_name: str
    environment: str
    repository: str
    deployed_by: str
    deployed_at: datetime
    
    # Severity
    severity: ViolationSeverity = Field(default=ViolationSeverity.HIGH)
    
    # Audit trail
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Alert status
    alert_sent: bool = False
    alert_sent_at: datetime | None = None
    alert_channels: list[str] = Field(default_factory=list)
    
    # Resolution
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    acknowledgement_reason: str | None = None
    
    # Context
    freeze_name: str | None = None
    commit_sha: str | None = None
    commit_message: str | None = None


# --- Request/Response Models ---


class CreateFreezeRequest(BaseModel):
    """Request to create a new change freeze."""

    name: str
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    scope: FreezeScope = FreezeScope.GLOBAL
    services: list[str] = Field(default_factory=list)
    environments: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    allow_emergency_deployments: bool = True
    require_approval_for_exceptions: bool = True
    notification_channels: list[str] = Field(default_factory=list)
    approvers: list[str] = Field(default_factory=list)


class UpdateFreezeRequest(BaseModel):
    """Request to update a change freeze."""

    name: str | None = None
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    services: list[str] | None = None
    environments: list[str] | None = None
    allow_emergency_deployments: bool | None = None
    notification_channels: list[str] | None = None
    approvers: list[str] | None = None


class CreateExceptionRequest(BaseModel):
    """Request to create a freeze exception."""

    freeze_id: str
    service_name: str
    environment: str = "production"
    reason: str
    justification: str | None = None
    risk_assessment: str | None = None
    rollback_plan: str | None = None
    is_emergency: bool = False
    emergency_ticket_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class ReviewExceptionRequest(BaseModel):
    """Request to review (approve/reject) an exception."""

    approved: bool
    notes: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class FreezeStatusResponse(BaseModel):
    """Response for freeze status check."""

    is_frozen: bool
    active_freezes: list[ChangeFreeze]
    applicable_exceptions: list[FreezeException]
    can_deploy: bool
    reason: str


class ViolationListResponse(BaseModel):
    """Response for listing violations."""

    violations: list[FreezeViolation]
    total: int
    unacknowledged_count: int
