"""
PagerDuty Models
================

Pydantic models for PagerDuty API integration.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class PDUrgency(StrEnum):
    """PagerDuty incident urgency levels."""

    HIGH = "high"
    LOW = "low"


class PDStatus(StrEnum):
    """PagerDuty incident status."""

    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class PDWebhookType(StrEnum):
    """PagerDuty webhook event types."""

    INCIDENT_TRIGGER = "incident.trigger"
    INCIDENT_ACKNOWLEDGE = "incident.acknowledge"
    INCIDENT_UNACKNOWLEDGE = "incident.unacknowledge"
    INCIDENT_RESOLVE = "incident.resolve"
    INCIDENT_REASSIGN = "incident.reassign"
    INCIDENT_ESCALATE = "incident.escalate"
    INCIDENT_DELEGATE = "incident.delegate"
    INCIDENT_ANNOTATE = "incident.annotate"
    INCIDENT_PRIORITY_UPDATED = "incident.priority_updated"
    INCIDENT_RESPONDER_ADDED = "incident.responder.added"
    INCIDENT_RESPONDER_REPLIED = "incident.responder.replied"
    INCIDENT_ACTION_INVOKED = "incident.action_invoked"
    SERVICE_CREATED = "service.created"
    SERVICE_UPDATED = "service.updated"
    SERVICE_DELETED = "service.deleted"


class PagerDutyConfig(BaseModel):
    """PagerDuty integration configuration."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID

    # API credentials
    api_token: str = Field(..., description="REST API token")
    integration_key: str | None = Field(None, description="Events API integration key")

    # OAuth credentials (alternative)
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None

    # Webhook settings
    webhook_url: HttpUrl | None = None
    webhook_secret: str | None = None

    # Mapping
    default_escalation_policy_id: str | None = None
    service_mapping: dict[str, str] = Field(
        default_factory=dict, description="Internal service ID -> PagerDuty service ID"
    )

    # Sync settings
    sync_incidents: bool = True
    sync_services: bool = True
    sync_schedules: bool = True
    auto_create_services: bool = False

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = True


class PDReference(BaseModel):
    """PagerDuty object reference."""

    id: str
    type: str
    summary: str | None = None
    self_url: str | None = Field(None, alias="self")
    html_url: str | None = None


class PDUser(BaseModel):
    """PagerDuty user."""

    id: str
    type: str = "user"
    summary: str = ""
    self_url: str | None = Field(None, alias="self")
    html_url: str | None = None

    name: str = ""
    email: str = ""
    time_zone: str | None = None
    color: str | None = None
    avatar_url: str | None = None
    role: str | None = None
    job_title: str | None = None

    # Contact methods
    contact_methods: list[dict] = Field(default_factory=list)
    notification_rules: list[dict] = Field(default_factory=list)

    # Teams
    teams: list[PDReference] = Field(default_factory=list)


class PDService(BaseModel):
    """PagerDuty service."""

    id: str
    type: str = "service"
    summary: str = ""
    self_url: str | None = Field(None, alias="self")
    html_url: str | None = None

    name: str
    description: str | None = None
    status: str = "active"  # active, warning, critical, maintenance, disabled

    # Configuration
    auto_resolve_timeout: int | None = None
    acknowledgement_timeout: int | None = None
    alert_creation: str = "create_alerts_and_incidents"
    alert_grouping: str | None = None
    alert_grouping_timeout: int | None = None

    # References
    escalation_policy: PDReference | None = None
    teams: list[PDReference] = Field(default_factory=list)
    integrations: list[PDReference] = Field(default_factory=list)

    created_at: datetime | None = None
    updated_at: datetime | None = None


class PDPriority(BaseModel):
    """PagerDuty priority."""

    id: str
    type: str = "priority"
    summary: str
    self_url: str | None = Field(None, alias="self")

    name: str
    description: str | None = None
    order: int = 0
    color: str | None = None


class PDIncident(BaseModel):
    """PagerDuty incident."""

    id: str
    type: str = "incident"
    summary: str = ""
    self_url: str | None = Field(None, alias="self")
    html_url: str | None = None

    incident_number: int
    title: str
    description: str | None = None

    status: PDStatus = PDStatus.TRIGGERED
    urgency: PDUrgency = PDUrgency.HIGH
    priority: PDPriority | None = None

    # References
    service: PDReference
    escalation_policy: PDReference | None = None
    teams: list[PDReference] = Field(default_factory=list)

    # Assignments
    assignments: list[dict] = Field(default_factory=list)
    acknowledgements: list[dict] = Field(default_factory=list)
    last_status_change_at: datetime | None = None
    last_status_change_by: PDReference | None = None

    # Responders
    first_trigger_log_entry: PDReference | None = None
    escalation_level: int = 1
    pending_actions: list[dict] = Field(default_factory=list)

    # Alerts
    alert_counts: dict | None = None

    # Conference bridge
    conference_bridge: dict | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = None
    resolved_at: datetime | None = None

    # Custom fields
    custom_fields: list[dict] = Field(default_factory=list)


class PDEscalationRule(BaseModel):
    """Escalation policy rule."""

    id: str
    escalation_delay_in_minutes: int = 30
    targets: list[PDReference] = Field(default_factory=list)


class PDEscalationPolicy(BaseModel):
    """PagerDuty escalation policy."""

    id: str
    type: str = "escalation_policy"
    summary: str = ""
    self_url: str | None = Field(None, alias="self")
    html_url: str | None = None

    name: str
    description: str | None = None
    num_loops: int = 0
    on_call_handoff_notifications: str = "if_has_services"

    # Rules
    escalation_rules: list[PDEscalationRule] = Field(default_factory=list)

    # References
    services: list[PDReference] = Field(default_factory=list)
    teams: list[PDReference] = Field(default_factory=list)


class PDScheduleLayer(BaseModel):
    """Schedule layer within a schedule."""

    id: str
    name: str
    start: datetime
    end: datetime | None = None
    rotation_virtual_start: datetime
    rotation_turn_length_seconds: int
    users: list[PDReference] = Field(default_factory=list)
    restrictions: list[dict] = Field(default_factory=list)


class PDSchedule(BaseModel):
    """PagerDuty schedule."""

    id: str
    type: str = "schedule"
    summary: str = ""
    self_url: str | None = Field(None, alias="self")
    html_url: str | None = None

    name: str
    description: str | None = None
    time_zone: str = "UTC"

    # Layers
    schedule_layers: list[PDScheduleLayer] = Field(default_factory=list)
    final_schedule: dict | None = None

    # Overrides
    overrides_subschedule: dict | None = None

    # References
    escalation_policies: list[PDReference] = Field(default_factory=list)
    users: list[PDReference] = Field(default_factory=list)
    teams: list[PDReference] = Field(default_factory=list)


class PDOnCall(BaseModel):
    """PagerDuty on-call entry."""

    user: PDUser
    schedule: PDReference | None = None
    escalation_policy: PDReference
    escalation_level: int = 1
    start: datetime
    end: datetime


class PDWebhookMessage(BaseModel):
    """Individual message within a webhook payload."""

    event: PDWebhookType
    log_entries: list[dict] = Field(default_factory=list)
    incident: PDIncident | None = None
    service: PDService | None = None
    created_on: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PDWebhookEvent(BaseModel):
    """PagerDuty V3 webhook event."""

    id: str
    routing_key: str | None = None
    event_type: str
    resource_type: str
    occurred_at: datetime
    agent: dict | None = None
    client: dict | None = None
    data: dict = Field(default_factory=dict)

    # Parsed data
    incident: PDIncident | None = None
    service: PDService | None = None


class PDEventsAPIPayload(BaseModel):
    """Payload for PagerDuty Events API v2."""

    routing_key: str
    event_action: str = "trigger"  # trigger, acknowledge, resolve
    dedup_key: str | None = None

    payload: dict | None = None
    images: list[dict] = Field(default_factory=list)
    links: list[dict] = Field(default_factory=list)

    class Config:
        extra = "allow"


class CreateIncidentRequest(BaseModel):
    """Request to create an incident via PagerDuty."""

    title: str
    service_id: str
    urgency: PDUrgency = PDUrgency.HIGH
    priority_id: str | None = None
    escalation_policy_id: str | None = None
    body: str | None = None
    incident_key: str | None = None
    assignments: list[str] = Field(default_factory=list)
    conference_bridge: dict | None = None


class UpdateIncidentRequest(BaseModel):
    """Request to update a PagerDuty incident."""

    status: PDStatus | None = None
    title: str | None = None
    urgency: PDUrgency | None = None
    priority_id: str | None = None
    escalation_policy_id: str | None = None
    escalation_level: int | None = None
    assignments: list[str] | None = None
    resolution: str | None = None


class SyncResult(BaseModel):
    """Result of a sync operation."""

    success: bool
    synced_count: int = 0
    error_count: int = 0
    errors: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)
