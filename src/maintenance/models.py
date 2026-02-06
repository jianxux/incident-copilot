"""Data models for maintenance windows."""

import secrets
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MaintenanceStatus(str, Enum):
    """Status of a maintenance window."""

    SCHEDULED = "scheduled"  # Future maintenance
    ACTIVE = "active"  # Currently in maintenance
    COMPLETED = "completed"  # Maintenance ended normally
    CANCELLED = "cancelled"  # Maintenance was cancelled
    OVERRIDDEN = "overridden"  # Maintenance bypassed by emergency


class RecurrencePattern(str, Enum):
    """Recurrence patterns for maintenance windows."""

    NONE = "none"  # One-time window
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"  # Custom cron expression


class SuppressionAction(str, Enum):
    """What to do with alerts during maintenance."""

    SUPPRESS = "suppress"  # Completely suppress (no notification)
    ANNOTATE = "annotate"  # Deliver but mark as maintenance-related
    LOG_ONLY = "log_only"  # Log but don't notify
    NONE = "none"  # No suppression (alerts delivered normally)


class NotificationType(str, Enum):
    """Types of maintenance notifications."""

    MAINTENANCE_STARTING = "maintenance_starting"
    MAINTENANCE_STARTED = "maintenance_started"
    MAINTENANCE_ENDING_SOON = "maintenance_ending_soon"
    MAINTENANCE_ENDED = "maintenance_ended"
    MAINTENANCE_EXTENDED = "maintenance_extended"
    MAINTENANCE_CANCELLED = "maintenance_cancelled"
    EMERGENCY_OVERRIDE = "emergency_override"


class RecurringSchedule(BaseModel):
    """Recurring schedule configuration for maintenance windows."""

    pattern: RecurrencePattern = RecurrencePattern.NONE
    
    # For weekly: which days (0=Monday, 6=Sunday)
    days_of_week: list[int] = Field(default_factory=list)
    
    # For monthly: which day of month (1-31, -1 for last day)
    day_of_month: int | None = None
    
    # For custom: cron expression
    cron_expression: str | None = None
    
    # Time of day (in UTC or specified timezone)
    start_time: str = "00:00"  # HH:MM format
    
    # Duration of each maintenance window
    duration_minutes: int = 60
    
    # Timezone for schedule (e.g., "America/New_York")
    timezone: str = "UTC"
    
    # End date for recurring schedule (None = indefinite)
    recurrence_end_date: datetime | None = None
    
    # Maximum number of occurrences (None = unlimited)
    max_occurrences: int | None = None
    
    # Skip certain dates
    excluded_dates: list[datetime] = Field(default_factory=list)

    @field_validator("days_of_week")
    @classmethod
    def validate_days_of_week(cls, v: list[int]) -> list[int]:
        """Validate days of week are 0-6."""
        for day in v:
            if not 0 <= day <= 6:
                raise ValueError(f"Day of week must be 0-6, got {day}")
        return sorted(set(v))

    @field_validator("day_of_month")
    @classmethod
    def validate_day_of_month(cls, v: int | None) -> int | None:
        """Validate day of month."""
        if v is not None and not (-1 <= v <= 31 and v != 0):
            raise ValueError(f"Day of month must be 1-31 or -1, got {v}")
        return v


class MaintenanceNotification(BaseModel):
    """Configuration for maintenance notifications."""

    # When to send notifications (minutes before/after)
    notify_before_minutes: list[int] = Field(default_factory=lambda: [60, 15])
    notify_on_start: bool = True
    notify_before_end_minutes: int = 15
    notify_on_end: bool = True
    
    # Notification channels
    slack_channels: list[str] = Field(default_factory=list)
    email_recipients: list[str] = Field(default_factory=list)
    webhook_urls: list[str] = Field(default_factory=list)
    
    # Include in on-call handoff
    include_in_handoff: bool = True


class MaintenanceWindow(BaseModel):
    """A maintenance window for suppressing alerts."""

    id: str = Field(default_factory=lambda: f"mw_{secrets.token_urlsafe(12)}")
    
    # Basic info
    title: str
    description: str | None = None
    status: MaintenanceStatus = MaintenanceStatus.SCHEDULED
    
    # Scope
    services: list[str] = Field(default_factory=list)  # Empty = global
    environments: list[str] = Field(default_factory=list)  # e.g., ["prod", "staging"]
    alert_types: list[str] = Field(default_factory=list)  # Specific alert types to suppress
    
    # Is this a global maintenance (affects all services)?
    is_global: bool = False
    
    # Timing (for one-time windows)
    start_time: datetime
    end_time: datetime
    
    # Recurring schedule (optional)
    recurring: RecurringSchedule | None = None
    
    # What to do with alerts
    suppression_action: SuppressionAction = SuppressionAction.SUPPRESS
    
    # Notification settings
    notifications: MaintenanceNotification = Field(
        default_factory=MaintenanceNotification
    )
    
    # Metadata
    created_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Tags for organization
    tags: list[str] = Field(default_factory=list)
    
    # Ticket/change management link
    change_ticket_url: str | None = None
    change_ticket_id: str | None = None
    
    # Arbitrary metadata
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    # Tenant isolation
    tenant_id: str | None = None

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
    )

    @property
    def is_active(self) -> bool:
        """Check if maintenance is currently active."""
        now = datetime.utcnow()
        return (
            self.status == MaintenanceStatus.ACTIVE
            or (
                self.status == MaintenanceStatus.SCHEDULED
                and self.start_time <= now <= self.end_time
            )
        )

    @property
    def is_recurring(self) -> bool:
        """Check if this is a recurring maintenance window."""
        return (
            self.recurring is not None
            and self.recurring.pattern != RecurrencePattern.NONE
        )

    @property
    def duration_minutes(self) -> int:
        """Get duration in minutes."""
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)

    def affects_service(self, service: str) -> bool:
        """Check if this maintenance affects a specific service."""
        if self.is_global:
            return True
        if not self.services:
            return True  # Empty services list = affects all
        return service.lower() in [s.lower() for s in self.services]

    def affects_environment(self, environment: str) -> bool:
        """Check if this maintenance affects a specific environment."""
        if not self.environments:
            return True  # Empty = affects all
        return environment.lower() in [e.lower() for e in self.environments]


class MaintenanceWindowCreate(BaseModel):
    """Request model for creating a maintenance window."""

    title: str
    description: str | None = None
    services: list[str] = Field(default_factory=list)
    environments: list[str] = Field(default_factory=list)
    alert_types: list[str] = Field(default_factory=list)
    is_global: bool = False
    start_time: datetime
    end_time: datetime
    recurring: RecurringSchedule | None = None
    suppression_action: SuppressionAction = SuppressionAction.SUPPRESS
    notifications: MaintenanceNotification | None = None
    tags: list[str] = Field(default_factory=list)
    change_ticket_url: str | None = None
    change_ticket_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("end_time")
    @classmethod
    def validate_end_after_start(cls, v: datetime, info) -> datetime:
        """Ensure end time is after start time."""
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class MaintenanceWindowUpdate(BaseModel):
    """Request model for updating a maintenance window."""

    title: str | None = None
    description: str | None = None
    services: list[str] | None = None
    environments: list[str] | None = None
    alert_types: list[str] | None = None
    is_global: bool | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    recurring: RecurringSchedule | None = None
    suppression_action: SuppressionAction | None = None
    notifications: MaintenanceNotification | None = None
    status: MaintenanceStatus | None = None
    tags: list[str] | None = None
    change_ticket_url: str | None = None
    change_ticket_id: str | None = None
    metadata: dict[str, Any] | None = None


class EmergencyOverride(BaseModel):
    """Emergency override for a maintenance window."""

    id: str = Field(default_factory=lambda: f"eo_{secrets.token_urlsafe(12)}")
    maintenance_window_id: str
    reason: str
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Which services to override (empty = all services in the window)
    services: list[str] = Field(default_factory=list)
    
    # Automatically revoke after duration
    auto_revoke_minutes: int | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    
    # Is this override currently active?
    is_active: bool = True

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
    )


class MaintenanceAuditEntry(BaseModel):
    """Audit log entry for maintenance-related actions."""

    id: str = Field(default_factory=lambda: f"ma_{secrets.token_urlsafe(12)}")
    maintenance_window_id: str | None = None
    
    # What happened
    action: str  # created, updated, started, ended, override, suppressed_alert, etc.
    
    # Context
    alert_id: str | None = None
    service: str | None = None
    user_id: str | None = None
    
    # Details
    details: dict[str, Any] = Field(default_factory=dict)
    
    # When
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Tenant isolation
    tenant_id: str | None = None

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
    )


class CalendarEvent(BaseModel):
    """Calendar representation of a maintenance window."""

    id: str
    title: str
    description: str | None = None
    start: datetime
    end: datetime
    all_day: bool = False
    
    # Color coding by status
    color: str = "#FFA500"  # Orange for maintenance
    
    # Links
    url: str | None = None
    
    # Categorization
    category: str = "maintenance"
    services: list[str] = Field(default_factory=list)
    
    # For recurring events
    recurrence_rule: str | None = None  # iCal RRULE format
    
    # Status
    status: MaintenanceStatus = MaintenanceStatus.SCHEDULED


class MaintenanceQuery(BaseModel):
    """Query parameters for listing maintenance windows."""

    tenant_id: str | None = None
    status: MaintenanceStatus | None = None
    service: str | None = None
    environment: str | None = None
    start_after: datetime | None = None
    start_before: datetime | None = None
    is_active: bool | None = None
    is_global: bool | None = None
    tags: list[str] | None = None
    include_recurring: bool = True
    limit: int = 100
    offset: int = 0
