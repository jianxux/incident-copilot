"""Pydantic models for webhook outbound system."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class WebhookEventType(StrEnum):
    """Supported webhook event types."""

    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_RESOLVED = "incident.resolved"
    INCIDENT_ESCALATED = "incident.escalated"
    INCIDENT_ACKNOWLEDGED = "incident.acknowledged"
    SLA_BREACHED = "sla.breached"
    SLA_WARNING = "sla.warning"
    ALERT_TRIGGERED = "alert.triggered"
    ALERT_RESOLVED = "alert.resolved"
    COMMENT_ADDED = "comment.added"
    ASSIGNMENT_CHANGED = "assignment.changed"
    STATUS_CHANGED = "status.changed"


class DeliveryStatus(StrEnum):
    """Webhook delivery status."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class WebhookConfigBase(BaseModel):
    """Base webhook configuration."""

    name: str = Field(..., min_length=1, max_length=100)
    url: HttpUrl
    events: list[WebhookEventType] = Field(default_factory=list)
    is_active: bool = True
    custom_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    max_retries: int = Field(default=3, ge=0, le=10)
    payload_template_id: str | None = None

    @field_validator("events", mode="before")
    @classmethod
    def validate_events(cls, v: Any) -> list[WebhookEventType]:
        if not v:
            return list(WebhookEventType)  # Subscribe to all by default
        return v


class WebhookConfigCreate(WebhookConfigBase):
    """Create webhook configuration."""

    pass


class WebhookConfigUpdate(BaseModel):
    """Update webhook configuration (partial)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: HttpUrl | None = None
    events: list[WebhookEventType] | None = None
    is_active: bool | None = None
    secret: str | None = None
    custom_headers: dict[str, str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    payload_template_id: str | None = None


class WebhookConfig(WebhookConfigBase):
    """Full webhook configuration with metadata."""

    id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    secret: str  # For HMAC signing
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Circuit breaker state
    circuit_state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_at: datetime | None = None
    circuit_opened_at: datetime | None = None

    # Stats
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0

    model_config = {"from_attributes": True}


class WebhookEvent(BaseModel):
    """Webhook event to be delivered."""

    id: UUID = Field(default_factory=uuid4)
    event_type: WebhookEventType
    organization_id: UUID
    payload: dict[str, Any]
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: str | None = None  # For tracing

    # Optional metadata
    source: str = "incident-copilot"
    version: str = "1.0"


class WebhookDelivery(BaseModel):
    """Record of a webhook delivery attempt."""

    id: UUID = Field(default_factory=uuid4)
    webhook_id: UUID
    event_id: UUID
    event_type: WebhookEventType

    # Delivery info
    url: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempt_number: int = 1

    # Request/Response
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: str = ""
    response_status_code: int | None = None
    response_body: str | None = None
    response_headers: dict[str, str] | None = None

    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    delivered_at: datetime | None = None
    duration_ms: int | None = None
    next_retry_at: datetime | None = None

    # Error info
    error_message: str | None = None

    model_config = {"from_attributes": True}


class WebhookTestRequest(BaseModel):
    """Request to test a webhook endpoint."""

    event_type: WebhookEventType = WebhookEventType.INCIDENT_CREATED
    custom_payload: dict[str, Any] | None = None


class WebhookTestResponse(BaseModel):
    """Response from webhook test."""

    success: bool
    status_code: int | None = None
    response_body: str | None = None
    duration_ms: int
    error: str | None = None
    signature_header: str


class BulkDeliveryRequest(BaseModel):
    """Request for bulk webhook delivery."""

    events: list[WebhookEvent]
    webhook_ids: list[UUID] | None = None  # None = all active webhooks


class BulkDeliveryResponse(BaseModel):
    """Response from bulk delivery."""

    total_events: int
    total_webhooks: int
    queued_deliveries: int
    errors: list[str] = Field(default_factory=list)


class WebhookStats(BaseModel):
    """Statistics for a webhook."""

    webhook_id: UUID
    total_deliveries: int
    successful_deliveries: int
    failed_deliveries: int
    success_rate: float
    avg_response_time_ms: float | None
    last_delivery_at: datetime | None
    circuit_state: CircuitState
