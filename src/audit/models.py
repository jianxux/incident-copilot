"""Data models for audit logging."""

import secrets
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventCategory(str, Enum):
    """High-level categories for audit events."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    CONFIGURATION = "configuration"
    API_KEY = "api_key"
    WEBHOOK = "webhook"
    USER_MANAGEMENT = "user_management"
    BILLING = "billing"
    INTEGRATION = "integration"
    SYSTEM = "system"


class EventType(str, Enum):
    """Specific event types for audit logging."""

    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    TOKEN_REFRESH = "token_refresh"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_COMPLETE = "password_reset_complete"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    MFA_CHALLENGE = "mfa_challenge"

    # Authorization events
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PERMISSION_CHECK = "permission_check"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"

    # Data access events
    INCIDENT_VIEWED = "incident_viewed"
    INCIDENT_CREATED = "incident_created"
    INCIDENT_UPDATED = "incident_updated"
    INCIDENT_RESOLVED = "incident_resolved"
    CONTEXT_FETCHED = "context_fetched"
    LOGS_ACCESSED = "logs_accessed"
    METRICS_ACCESSED = "metrics_accessed"
    ANALYTICS_VIEWED = "analytics_viewed"
    RUNBOOK_ACCESSED = "runbook_accessed"
    SIMILAR_INCIDENTS_SEARCHED = "similar_incidents_searched"

    # Configuration events
    SETTINGS_VIEWED = "settings_viewed"
    SETTINGS_UPDATED = "settings_updated"
    FEATURE_ENABLED = "feature_enabled"
    FEATURE_DISABLED = "feature_disabled"

    # Integration events
    INTEGRATION_ADDED = "integration_added"
    INTEGRATION_REMOVED = "integration_removed"
    INTEGRATION_UPDATED = "integration_updated"
    INTEGRATION_TESTED = "integration_tested"

    # API key events
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_USED = "api_key_used"
    API_KEY_ROTATED = "api_key_rotated"

    # Webhook events
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_PROCESSED = "webhook_processed"
    WEBHOOK_FAILED = "webhook_failed"
    WEBHOOK_SIGNATURE_INVALID = "webhook_signature_invalid"

    # User management events
    USER_CREATED = "user_created"
    USER_INVITED = "user_invited"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ACTIVATED = "user_activated"
    USER_DEACTIVATED = "user_deactivated"
    USER_ROLE_CHANGED = "user_role_changed"

    # Billing events
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    PLAN_UPGRADED = "plan_upgraded"
    PLAN_DOWNGRADED = "plan_downgraded"

    # System events
    AUDIT_LOG_EXPORTED = "audit_log_exported"
    AUDIT_LOG_VIEWED = "audit_log_viewed"
    SYSTEM_ERROR = "system_error"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


class Outcome(str, Enum):
    """Outcome of an audited action."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"
    PENDING = "pending"


class AuditEvent(BaseModel):
    """An audit log event for compliance and security tracking."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))

    # Event identification
    event_type: EventType
    category: EventCategory

    # Tenant/user context
    tenant_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None

    # Action details
    action: str
    resource_type: str | None = None
    resource_id: str | None = None

    # Outcome
    outcome: Outcome = Outcome.SUCCESS

    # Request context
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    request_path: str | None = None
    request_method: str | None = None

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Audit trail metadata
    api_key_id: str | None = None
    session_id: str | None = None

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
    )


class AuditLogQuery(BaseModel):
    """Query parameters for searching audit logs."""

    tenant_id: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    event_types: list[EventType] | None = None
    categories: list[EventCategory] | None = None
    user_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    outcome: Outcome | None = None
    ip_address: str | None = None
    limit: int = 100
    offset: int = 0
