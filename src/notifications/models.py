"""Notification preference models using Pydantic v2."""

from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ChannelType(StrEnum):
    """Supported notification channel types."""

    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


class Severity(StrEnum):
    """Incident severity levels."""

    P1 = "P1"  # Critical
    P2 = "P2"  # High
    P3 = "P3"  # Medium
    P4 = "P4"  # Low
    P5 = "P5"  # Informational


class UserRole(StrEnum):
    """User roles for default preference assignment."""

    ON_CALL = "on_call"
    ENGINEER = "engineer"
    MANAGER = "manager"
    EXECUTIVE = "executive"
    OBSERVER = "observer"


class NotificationType(StrEnum):
    """Types of notifications that can be sent."""

    INCIDENT_CREATED = "incident_created"
    INCIDENT_UPDATED = "incident_updated"
    INCIDENT_RESOLVED = "incident_resolved"
    BREACH_WARNING = "breach_warning"
    BREACH_OCCURRED = "breach_occurred"
    ESCALATION = "escalation"
    ASSIGNMENT = "assignment"
    COMMENT = "comment"
    DIGEST = "digest"


class DigestFrequency(StrEnum):
    """Frequency options for digest notifications."""

    REALTIME = "realtime"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"


class NotificationChannel(BaseModel):
    """Configuration for a single notification channel."""

    type: ChannelType
    enabled: bool = True
    address: str = Field(..., description="Email, phone, webhook URL, or Slack channel")
    verified: bool = False
    priority: int = Field(
        default=0, ge=0, le=10, description="Higher = preferred channel"
    )

    # Channel-specific settings
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str, info) -> str:
        """Basic address validation based on channel type."""
        if not v or not v.strip():
            raise ValueError("Address cannot be empty")
        return v.strip()


class QuietHours(BaseModel):
    """Do Not Disturb / Quiet Hours configuration."""

    enabled: bool = False
    start_time: time = Field(
        default=time(22, 0), description="Start of quiet period (HH:MM)"
    )
    end_time: time = Field(
        default=time(8, 0), description="End of quiet period (HH:MM)"
    )
    timezone: str = Field(default="UTC", description="Timezone for quiet hours")

    # Override settings
    allow_p1: bool = Field(
        default=True, description="Allow P1 incidents during quiet hours"
    )
    allow_p2: bool = Field(
        default=False, description="Allow P2 incidents during quiet hours"
    )
    weekend_only: bool = Field(
        default=False, description="Only apply quiet hours on weekends"
    )

    def is_active(self, current_time: time | None = None) -> bool:
        """Check if quiet hours are currently active."""
        if not self.enabled:
            return False

        check_time = current_time or datetime.now().time()

        # Handle overnight quiet hours (e.g., 22:00 to 08:00)
        if self.start_time > self.end_time:
            return check_time >= self.start_time or check_time < self.end_time
        else:
            return self.start_time <= check_time < self.end_time

    def should_override(self, severity: Severity) -> bool:
        """Check if a severity level should override quiet hours."""
        if severity == Severity.P1 and self.allow_p1:
            return True
        if severity == Severity.P2 and self.allow_p2:
            return True
        return False


class NotificationRule(BaseModel):
    """Rule for filtering which notifications to receive."""

    id: str = Field(default_factory=lambda: "")
    name: str
    enabled: bool = True

    # Filters
    notification_types: list[NotificationType] = Field(default_factory=list)
    min_severity: Severity = Field(
        default=Severity.P5, description="Minimum severity to notify"
    )
    max_severity: Severity = Field(
        default=Severity.P1, description="Maximum severity to notify"
    )
    services: list[str] = Field(
        default_factory=list, description="Filter by service names"
    )
    teams: list[str] = Field(default_factory=list, description="Filter by team names")
    tags: list[str] = Field(default_factory=list, description="Filter by incident tags")

    # Actions
    channels: list[ChannelType] = Field(
        default_factory=list, description="Channels to use for this rule"
    )
    digest_frequency: DigestFrequency = Field(default=DigestFrequency.REALTIME)

    @model_validator(mode="after")
    def validate_severity_range(self) -> "NotificationRule":
        """Ensure min_severity <= max_severity in terms of priority."""
        severity_order = {
            Severity.P1: 1,
            Severity.P2: 2,
            Severity.P3: 3,
            Severity.P4: 4,
            Severity.P5: 5,
        }
        if severity_order[self.min_severity] < severity_order[self.max_severity]:
            raise ValueError(
                "min_severity must be less critical than or equal to max_severity"
            )
        return self

    def matches(
        self,
        notification_type: NotificationType,
        severity: Severity,
        service: str | None = None,
        team: str | None = None,
        incident_tags: list[str] | None = None,
    ) -> bool:
        """Check if this rule matches the given notification criteria."""
        if not self.enabled:
            return False

        # Check notification type
        if self.notification_types and notification_type not in self.notification_types:
            return False

        # Check severity range
        severity_order = {
            Severity.P1: 1,
            Severity.P2: 2,
            Severity.P3: 3,
            Severity.P4: 4,
            Severity.P5: 5,
        }
        sev_num = severity_order[severity]
        if (
            sev_num < severity_order[self.max_severity]
            or sev_num > severity_order[self.min_severity]
        ):
            return False

        # Check service filter
        if self.services and service and service not in self.services:
            return False

        # Check team filter
        if self.teams and team and team not in self.teams:
            return False

        # Check tag filter (any match)
        if self.tags and incident_tags:
            if not any(tag in self.tags for tag in incident_tags):
                return False

        return True


class NotificationPreference(BaseModel):
    """Complete notification preferences for a user."""

    user_id: str
    role: UserRole = Field(default=UserRole.ENGINEER)

    # Global settings
    enabled: bool = True
    default_digest_frequency: DigestFrequency = Field(default=DigestFrequency.REALTIME)

    # Channels
    channels: list[NotificationChannel] = Field(default_factory=list)

    # Quiet hours
    quiet_hours: QuietHours = Field(default_factory=QuietHours)

    # Rules (evaluated in order, first match wins)
    rules: list[NotificationRule] = Field(default_factory=list)

    # Template customization
    use_custom_templates: bool = False
    template_overrides: dict[str, str] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_enabled_channels(
        self, channel_types: list[ChannelType] | None = None
    ) -> list[NotificationChannel]:
        """Get enabled channels, optionally filtered by type."""
        channels = [c for c in self.channels if c.enabled]
        if channel_types:
            channels = [c for c in channels if c.type in channel_types]
        return sorted(channels, key=lambda c: -c.priority)

    def get_primary_channel(
        self, channel_type: ChannelType | None = None
    ) -> NotificationChannel | None:
        """Get the highest priority enabled channel."""
        channels = self.get_enabled_channels([channel_type] if channel_type else None)
        return channels[0] if channels else None


# Role-based default preferences
ROLE_DEFAULTS: dict[UserRole, dict] = {
    UserRole.ON_CALL: {
        "default_digest_frequency": DigestFrequency.REALTIME,
        "rules": [
            {
                "name": "All Critical",
                "min_severity": Severity.P2,
                "notification_types": [
                    NotificationType.INCIDENT_CREATED,
                    NotificationType.BREACH_WARNING,
                    NotificationType.BREACH_OCCURRED,
                    NotificationType.ESCALATION,
                    NotificationType.ASSIGNMENT,
                ],
            },
            {
                "name": "Updates for P3+",
                "min_severity": Severity.P3,
                "notification_types": [
                    NotificationType.INCIDENT_UPDATED,
                    NotificationType.COMMENT,
                ],
                "digest_frequency": DigestFrequency.HOURLY,
            },
        ],
    },
    UserRole.MANAGER: {
        "default_digest_frequency": DigestFrequency.HOURLY,
        "rules": [
            {
                "name": "Critical Only",
                "min_severity": Severity.P2,
                "notification_types": [
                    NotificationType.INCIDENT_CREATED,
                    NotificationType.BREACH_OCCURRED,
                    NotificationType.INCIDENT_RESOLVED,
                ],
            },
            {
                "name": "Daily Digest",
                "min_severity": Severity.P4,
                "notification_types": [NotificationType.DIGEST],
                "digest_frequency": DigestFrequency.DAILY,
            },
        ],
    },
    UserRole.EXECUTIVE: {
        "default_digest_frequency": DigestFrequency.DAILY,
        "rules": [
            {
                "name": "P1 Only",
                "min_severity": Severity.P1,
                "max_severity": Severity.P1,
                "notification_types": [
                    NotificationType.INCIDENT_CREATED,
                    NotificationType.INCIDENT_RESOLVED,
                ],
            },
        ],
    },
    UserRole.ENGINEER: {
        "default_digest_frequency": DigestFrequency.REALTIME,
        "rules": [
            {
                "name": "My Assignments",
                "min_severity": Severity.P3,
                "notification_types": [
                    NotificationType.ASSIGNMENT,
                    NotificationType.ESCALATION,
                ],
            },
            {
                "name": "Critical Incidents",
                "min_severity": Severity.P2,
                "notification_types": [
                    NotificationType.INCIDENT_CREATED,
                    NotificationType.BREACH_WARNING,
                ],
            },
        ],
    },
    UserRole.OBSERVER: {
        "default_digest_frequency": DigestFrequency.DAILY,
        "rules": [
            {
                "name": "Daily Summary",
                "min_severity": Severity.P3,
                "notification_types": [NotificationType.DIGEST],
                "digest_frequency": DigestFrequency.DAILY,
            },
        ],
    },
}


class NotificationPayload(BaseModel):
    """Payload for a notification to be sent."""

    id: str
    type: NotificationType
    severity: Severity
    title: str
    message: str

    # Context
    incident_id: str | None = None
    service: str | None = None
    team: str | None = None
    tags: list[str] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)

    # Delivery tracking
    channels_attempted: list[ChannelType] = Field(default_factory=list)
    channels_succeeded: list[ChannelType] = Field(default_factory=list)
