"""Data models for the Incident Communication Hub."""

import secrets
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AudienceType(str, Enum):
    """Types of communication audiences."""

    TECHNICAL = "technical"  # Engineering team, SREs
    EXECUTIVE = "executive"  # Leadership, C-suite
    CUSTOMER = "customer"  # External customers
    SUPPORT = "support"  # Customer support team
    STAKEHOLDER = "stakeholder"  # Business stakeholders
    PUBLIC = "public"  # Status page, public announcements


class DeliveryChannel(str, Enum):
    """Communication delivery channels."""

    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    STATUS_PAGE = "status_page"
    TEAMS = "teams"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"


class DeliveryStatus(str, Enum):
    """Status of a communication delivery."""

    PENDING = "pending"
    SENDING = "sending"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    SKIPPED = "skipped"


class UpdatePriority(str, Enum):
    """Priority level for communication updates."""

    CRITICAL = "critical"  # Immediate notification required
    HIGH = "high"  # Important update, send ASAP
    NORMAL = "normal"  # Standard update
    LOW = "low"  # Informational, can batch


class Stakeholder(BaseModel):
    """A stakeholder who receives incident communications."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    name: str
    email: str | None = None
    phone: str | None = None
    slack_user_id: str | None = None
    teams_user_id: str | None = None

    # Audience classification
    audience_type: AudienceType = AudienceType.STAKEHOLDER

    # Communication preferences
    preferred_channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.EMAIL]
    )
    notification_threshold: UpdatePriority = UpdatePriority.NORMAL

    # Role and department
    role: str | None = None
    department: str | None = None
    organization: str | None = None

    # Service subscriptions (which services they care about)
    subscribed_services: list[str] = Field(default_factory=list)
    subscribed_severity_levels: list[str] = Field(
        default_factory=lambda: ["critical", "high"]
    )

    # Metadata
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    @property
    def contact_info(self) -> dict[str, str | None]:
        """Get all contact information."""
        return {
            "email": self.email,
            "phone": self.phone,
            "slack": self.slack_user_id,
            "teams": self.teams_user_id,
        }


class StakeholderGroup(BaseModel):
    """A group of stakeholders for bulk communication."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    name: str
    description: str | None = None

    # Group members
    stakeholder_ids: list[str] = Field(default_factory=list)

    # Group settings
    audience_type: AudienceType = AudienceType.STAKEHOLDER
    default_channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.EMAIL]
    )

    # Service subscriptions for the group
    subscribed_services: list[str] = Field(default_factory=list)

    # Metadata
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str | None = None

    model_config = ConfigDict(use_enum_values=True)


class CommunicationUpdate(BaseModel):
    """A single communication update during an incident."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    incident_id: str
    plan_id: str | None = None

    # Content
    subject: str
    body: str
    body_html: str | None = None  # Rich HTML version

    # Audience targeting
    audience_type: AudienceType
    stakeholder_ids: list[str] = Field(default_factory=list)
    stakeholder_group_ids: list[str] = Field(default_factory=list)

    # Delivery configuration
    channels: list[DeliveryChannel] = Field(default_factory=list)
    priority: UpdatePriority = UpdatePriority.NORMAL

    # Status tracking
    status: DeliveryStatus = DeliveryStatus.PENDING
    delivery_results: dict[str, DeliveryStatus] = Field(
        default_factory=dict
    )  # channel -> status

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scheduled_for: datetime | None = None
    sent_at: datetime | None = None

    # Author
    created_by: str | None = None
    template_id: str | None = None

    # Metadata
    tenant_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    @property
    def is_sent(self) -> bool:
        """Check if update has been sent."""
        return self.status in [DeliveryStatus.DELIVERED, DeliveryStatus.FAILED]

    @property
    def successful_channels(self) -> list[str]:
        """Get channels that delivered successfully."""
        return [
            ch for ch, status in self.delivery_results.items()
            if status == DeliveryStatus.DELIVERED
        ]


class ScheduledReminder(BaseModel):
    """A scheduled reminder for posting updates."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    incident_id: str
    plan_id: str | None = None

    # Reminder configuration
    interval_minutes: int = 15
    message: str = "You haven't posted an update in {minutes} minutes"
    notify_channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.SLACK]
    )
    notify_user_ids: list[str] = Field(default_factory=list)

    # Status
    is_active: bool = True
    last_reminder_at: datetime | None = None
    reminder_count: int = 0

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    next_reminder_at: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)


class CommunicationPlan(BaseModel):
    """A complete communication plan for an incident."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    incident_id: str
    incident_title: str
    severity: str

    # Stakeholder configuration
    stakeholder_ids: list[str] = Field(default_factory=list)
    stakeholder_group_ids: list[str] = Field(default_factory=list)

    # Communication history
    updates: list[CommunicationUpdate] = Field(default_factory=list)

    # Scheduled reminders
    reminders: list[ScheduledReminder] = Field(default_factory=list)
    auto_reminder_enabled: bool = True
    auto_reminder_interval_minutes: int = 15

    # Templates to use by audience
    template_ids: dict[str, str] = Field(
        default_factory=dict
    )  # AudienceType -> template_id

    # Status
    is_active: bool = True
    last_update_at: datetime | None = None
    total_updates_sent: int = 0

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str | None = None
    tenant_id: str | None = None

    model_config = ConfigDict(use_enum_values=True)

    @property
    def minutes_since_last_update(self) -> float | None:
        """Get minutes since last communication update."""
        if not self.last_update_at:
            return None
        delta = datetime.utcnow() - self.last_update_at
        return delta.total_seconds() / 60

    @property
    def needs_update_reminder(self) -> bool:
        """Check if an update reminder should be sent."""
        if not self.auto_reminder_enabled:
            return False
        minutes = self.minutes_since_last_update
        if minutes is None:
            # No updates yet, check time since creation
            delta = datetime.utcnow() - self.created_at
            minutes = delta.total_seconds() / 60
        return minutes >= self.auto_reminder_interval_minutes


class CommunicationAuditEntry(BaseModel):
    """Audit log entry for communication events."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    incident_id: str
    plan_id: str | None = None
    update_id: str | None = None

    # Event details
    event_type: str  # created, sent, delivered, failed, reminder_sent
    channel: DeliveryChannel | None = None
    audience_type: AudienceType | None = None
    recipient_count: int = 0

    # Outcome
    success: bool = True
    error_message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    # Actor
    triggered_by: str | None = None  # user_id or "system"

    # Tenant
    tenant_id: str | None = None

    model_config = ConfigDict(use_enum_values=True)


# ============================================================================
# Request/Response Models for API
# ============================================================================


class CreateStakeholderRequest(BaseModel):
    """Request to create a new stakeholder."""

    name: str
    email: str | None = None
    phone: str | None = None
    slack_user_id: str | None = None
    teams_user_id: str | None = None
    audience_type: AudienceType = AudienceType.STAKEHOLDER
    preferred_channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.EMAIL]
    )
    notification_threshold: UpdatePriority = UpdatePriority.NORMAL
    role: str | None = None
    department: str | None = None
    organization: str | None = None
    subscribed_services: list[str] = Field(default_factory=list)
    subscribed_severity_levels: list[str] = Field(
        default_factory=lambda: ["critical", "high"]
    )


class UpdateStakeholderRequest(BaseModel):
    """Request to update an existing stakeholder."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    slack_user_id: str | None = None
    teams_user_id: str | None = None
    audience_type: AudienceType | None = None
    preferred_channels: list[DeliveryChannel] | None = None
    notification_threshold: UpdatePriority | None = None
    role: str | None = None
    department: str | None = None
    subscribed_services: list[str] | None = None
    subscribed_severity_levels: list[str] | None = None
    is_active: bool | None = None


class CreateStakeholderGroupRequest(BaseModel):
    """Request to create a stakeholder group."""

    name: str
    description: str | None = None
    stakeholder_ids: list[str] = Field(default_factory=list)
    audience_type: AudienceType = AudienceType.STAKEHOLDER
    default_channels: list[DeliveryChannel] = Field(
        default_factory=lambda: [DeliveryChannel.EMAIL]
    )
    subscribed_services: list[str] = Field(default_factory=list)


class CreateCommunicationPlanRequest(BaseModel):
    """Request to create a communication plan for an incident."""

    incident_id: str
    incident_title: str
    severity: str
    stakeholder_ids: list[str] = Field(default_factory=list)
    stakeholder_group_ids: list[str] = Field(default_factory=list)
    auto_reminder_enabled: bool = True
    auto_reminder_interval_minutes: int = 15
    template_ids: dict[str, str] = Field(default_factory=dict)


class SendUpdateRequest(BaseModel):
    """Request to send a communication update."""

    incident_id: str
    subject: str
    body: str
    body_html: str | None = None
    audience_types: list[AudienceType] = Field(default_factory=list)
    stakeholder_ids: list[str] = Field(default_factory=list)
    stakeholder_group_ids: list[str] = Field(default_factory=list)
    channels: list[DeliveryChannel] = Field(default_factory=list)
    priority: UpdatePriority = UpdatePriority.NORMAL
    scheduled_for: datetime | None = None
    template_id: str | None = None


class BroadcastUpdateRequest(BaseModel):
    """Request to broadcast update to all stakeholders in a plan."""

    plan_id: str
    subject: str
    body: str
    body_html: str | None = None
    priority: UpdatePriority = UpdatePriority.NORMAL
    template_id: str | None = None
    exclude_audience_types: list[AudienceType] = Field(default_factory=list)


class StakeholderListResponse(BaseModel):
    """Response for listing stakeholders."""

    stakeholders: list[Stakeholder]
    total: int
    limit: int
    offset: int


class StakeholderGroupListResponse(BaseModel):
    """Response for listing stakeholder groups."""

    groups: list[StakeholderGroup]
    total: int
    limit: int
    offset: int


class CommunicationPlanListResponse(BaseModel):
    """Response for listing communication plans."""

    plans: list[CommunicationPlan]
    total: int
    limit: int
    offset: int


class CommunicationAuditListResponse(BaseModel):
    """Response for listing audit entries."""

    entries: list[CommunicationAuditEntry]
    total: int
    limit: int
    offset: int
