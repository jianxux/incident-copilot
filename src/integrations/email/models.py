"""Email notification models."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


class EmailProvider(StrEnum):
    """Supported email providers."""

    SMTP = "smtp"
    SENDGRID = "sendgrid"
    SES = "ses"


class EmailTemplateType(StrEnum):
    """Email template types."""

    CONTEXT_CARD = "context_card"
    DIGEST_DAILY = "digest_daily"
    DIGEST_WEEKLY = "digest_weekly"
    TEST = "test"
    CUSTOM = "custom"


class DigestFrequency(StrEnum):
    """Digest email frequency."""

    DAILY = "daily"
    WEEKLY = "weekly"
    DISABLED = "disabled"


class EmailRecipient(BaseModel):
    """Email recipient configuration."""

    email: EmailStr
    name: str | None = None
    type: str = "to"  # to, cc, bcc

    @property
    def formatted(self) -> str:
        """Return formatted email address."""
        if self.name:
            return f"{self.name} <{self.email}>"
        return self.email


class SMTPConfig(BaseModel):
    """SMTP server configuration."""

    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    timeout: int = 30


class SendGridConfig(BaseModel):
    """SendGrid API configuration."""

    api_key: str
    sandbox_mode: bool = False


class SESConfig(BaseModel):
    """AWS SES configuration."""

    region: str = "us-east-1"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    configuration_set: str | None = None


class EmailConfig(BaseModel):
    """Email configuration for a tenant."""

    tenant_id: str
    enabled: bool = True
    provider: EmailProvider = EmailProvider.SMTP

    # Common settings
    from_email: EmailStr
    from_name: str = "Incident Copilot"
    reply_to: EmailStr | None = None

    # Default recipients
    default_recipients: list[EmailRecipient] = Field(default_factory=list)

    # Provider-specific configs
    smtp: SMTPConfig | None = None
    sendgrid: SendGridConfig | None = None
    ses: SESConfig | None = None

    # Digest settings
    digest_enabled: bool = False
    digest_frequency: DigestFrequency = DigestFrequency.DAILY
    digest_recipients: list[EmailRecipient] = Field(default_factory=list)
    digest_hour: int = Field(default=9, ge=0, le=23)  # Hour to send digest (UTC)
    digest_day: int = Field(default=1, ge=1, le=7)  # Day for weekly digest (1=Monday)

    # Template settings
    custom_footer: str | None = None
    logo_url: str | None = None
    brand_color: str = "#2563eb"  # Primary brand color

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("brand_color")
    @classmethod
    def validate_brand_color(cls, v: str) -> str:
        """Validate hex color format."""
        if not v.startswith("#") or len(v) != 7:
            raise ValueError("Brand color must be a valid hex color (e.g., #2563eb)")
        return v


class EmailTemplate(BaseModel):
    """Email template definition."""

    id: str
    name: str
    type: EmailTemplateType
    subject: str
    html_template: str
    text_template: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class EmailMessage(BaseModel):
    """Email message to be sent."""

    to: list[EmailRecipient]
    cc: list[EmailRecipient] = Field(default_factory=list)
    bcc: list[EmailRecipient] = Field(default_factory=list)
    subject: str
    html_body: str
    text_body: str
    from_email: EmailStr | None = None
    from_name: str | None = None
    reply_to: EmailStr | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SendResult(BaseModel):
    """Result of sending an email."""

    success: bool
    message_id: str | None = None
    provider: EmailProvider | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DigestConfig(BaseModel):
    """Digest email configuration."""

    tenant_id: str
    frequency: DigestFrequency
    recipients: list[EmailRecipient]
    hour: int = 9
    day: int = 1  # For weekly: 1=Monday
    last_sent: datetime | None = None
    incidents_since_last: int = 0


class IncidentDigestItem(BaseModel):
    """An incident item for digest emails."""

    incident_id: str
    title: str
    service_name: str
    severity: str
    triggered_at: datetime
    resolved_at: datetime | None = None
    status: str = "open"
    url: str | None = None


class DigestData(BaseModel):
    """Data for rendering digest emails."""

    tenant_id: str
    period_start: datetime
    period_end: datetime
    incidents: list[IncidentDigestItem]
    total_incidents: int
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    mttr_minutes: float | None = None  # Mean time to resolve
    services_affected: list[str] = Field(default_factory=list)
