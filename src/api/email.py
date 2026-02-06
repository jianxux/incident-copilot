"""Email notification API endpoints."""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr, Field

from ..integrations.email import (
    DigestFrequency,
    EmailConfig,
    EmailNotificationService,
    EmailProvider,
    EmailRecipient,
    EmailTemplateRenderer,
    SendResult,
)
from ..integrations.email.models import (
    SendGridConfig,
    SESConfig,
    SMTPConfig,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/notifications/email", tags=["email"])


# --- Request/Response Models ---


class EmailRecipientInput(BaseModel):
    """Email recipient input."""

    email: EmailStr
    name: str | None = None
    type: str = "to"


class SMTPConfigInput(BaseModel):
    """SMTP configuration input."""

    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False


class SendGridConfigInput(BaseModel):
    """SendGrid configuration input."""

    api_key: str
    sandbox_mode: bool = False


class SESConfigInput(BaseModel):
    """AWS SES configuration input."""

    region: str = "us-east-1"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    configuration_set: str | None = None


class EmailConfigInput(BaseModel):
    """Email configuration input."""

    enabled: bool = True
    provider: EmailProvider = EmailProvider.SMTP

    from_email: EmailStr
    from_name: str = "Incident Copilot"
    reply_to: EmailStr | None = None

    default_recipients: list[EmailRecipientInput] = Field(default_factory=list)

    smtp: SMTPConfigInput | None = None
    sendgrid: SendGridConfigInput | None = None
    ses: SESConfigInput | None = None

    digest_enabled: bool = False
    digest_frequency: DigestFrequency = DigestFrequency.DAILY
    digest_recipients: list[EmailRecipientInput] = Field(default_factory=list)
    digest_hour: int = Field(default=9, ge=0, le=23)
    digest_day: int = Field(default=1, ge=1, le=7)

    custom_footer: str | None = None
    logo_url: str | None = None
    brand_color: str = "#2563eb"


class EmailConfigResponse(BaseModel):
    """Email configuration response."""

    tenant_id: str
    enabled: bool
    provider: EmailProvider
    from_email: str
    from_name: str
    reply_to: str | None
    default_recipients: list[dict[str, Any]]
    digest_enabled: bool
    digest_frequency: DigestFrequency
    digest_recipients: list[dict[str, Any]]
    digest_hour: int
    digest_day: int
    custom_footer: str | None
    logo_url: str | None
    brand_color: str
    created_at: datetime
    updated_at: datetime
    # Don't expose sensitive config details (passwords, API keys)
    smtp_configured: bool
    sendgrid_configured: bool
    ses_configured: bool


class SendEmailRequest(BaseModel):
    """Request to send an email notification."""

    incident_id: str
    recipients: list[EmailRecipientInput] | None = None
    cc: list[EmailRecipientInput] | None = None
    bcc: list[EmailRecipientInput] | None = None


class SendTestEmailRequest(BaseModel):
    """Request to send a test email."""

    recipient: EmailRecipientInput | None = None


class SendResultResponse(BaseModel):
    """Send result response."""

    success: bool
    message_id: str | None
    provider: str | None
    error: str | None
    timestamp: datetime


class TemplateInfo(BaseModel):
    """Template information."""

    id: str
    name: str
    type: str
    file: str


# --- In-memory config store (replace with real DB in production) ---
_config_store: dict[str, EmailConfig] = {}


def _get_tenant_id() -> str:
    """Get current tenant ID (placeholder)."""
    # In production, get from auth context
    return "default"


def _get_config(tenant_id: str) -> EmailConfig | None:
    """Get email config for tenant."""
    return _config_store.get(tenant_id)


def _save_config(config: EmailConfig) -> None:
    """Save email config."""
    _config_store[config.tenant_id] = config


def _input_to_recipient(inp: EmailRecipientInput) -> EmailRecipient:
    """Convert input to EmailRecipient."""
    return EmailRecipient(email=inp.email, name=inp.name, type=inp.type)


def _input_to_config(tenant_id: str, inp: EmailConfigInput) -> EmailConfig:
    """Convert input to EmailConfig."""
    return EmailConfig(
        tenant_id=tenant_id,
        enabled=inp.enabled,
        provider=inp.provider,
        from_email=inp.from_email,
        from_name=inp.from_name,
        reply_to=inp.reply_to,
        default_recipients=[_input_to_recipient(r) for r in inp.default_recipients],
        smtp=SMTPConfig(**inp.smtp.model_dump()) if inp.smtp else None,
        sendgrid=SendGridConfig(**inp.sendgrid.model_dump()) if inp.sendgrid else None,
        ses=SESConfig(**inp.ses.model_dump()) if inp.ses else None,
        digest_enabled=inp.digest_enabled,
        digest_frequency=inp.digest_frequency,
        digest_recipients=[_input_to_recipient(r) for r in inp.digest_recipients],
        digest_hour=inp.digest_hour,
        digest_day=inp.digest_day,
        custom_footer=inp.custom_footer,
        logo_url=inp.logo_url,
        brand_color=inp.brand_color,
    )


def _config_to_response(config: EmailConfig) -> EmailConfigResponse:
    """Convert EmailConfig to response."""
    return EmailConfigResponse(
        tenant_id=config.tenant_id,
        enabled=config.enabled,
        provider=config.provider,
        from_email=config.from_email,
        from_name=config.from_name,
        reply_to=config.reply_to,
        default_recipients=[r.model_dump() for r in config.default_recipients],
        digest_enabled=config.digest_enabled,
        digest_frequency=config.digest_frequency,
        digest_recipients=[r.model_dump() for r in config.digest_recipients],
        digest_hour=config.digest_hour,
        digest_day=config.digest_day,
        custom_footer=config.custom_footer,
        logo_url=config.logo_url,
        brand_color=config.brand_color,
        created_at=config.created_at,
        updated_at=config.updated_at,
        smtp_configured=config.smtp is not None,
        sendgrid_configured=config.sendgrid is not None,
        ses_configured=config.ses is not None,
    )


def _result_to_response(result: SendResult) -> SendResultResponse:
    """Convert SendResult to response."""
    return SendResultResponse(
        success=result.success,
        message_id=result.message_id,
        provider=result.provider.value if result.provider else None,
        error=result.error,
        timestamp=result.timestamp,
    )


# --- API Endpoints ---


@router.get("/config", response_model=EmailConfigResponse)
async def get_email_config():
    """Get email configuration for current tenant."""
    tenant_id = _get_tenant_id()
    config = _get_config(tenant_id)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Email configuration not found. Please configure email settings first.",
        )

    return _config_to_response(config)


@router.put("/config", response_model=EmailConfigResponse)
async def update_email_config(config_input: EmailConfigInput):
    """Create or update email configuration."""
    tenant_id = _get_tenant_id()

    # Validate provider-specific config
    if config_input.provider == EmailProvider.SMTP and not config_input.smtp:
        raise HTTPException(
            status_code=400,
            detail="SMTP configuration required when provider is 'smtp'",
        )
    if config_input.provider == EmailProvider.SENDGRID and not config_input.sendgrid:
        raise HTTPException(
            status_code=400,
            detail="SendGrid configuration required when provider is 'sendgrid'",
        )
    if config_input.provider == EmailProvider.SES and not config_input.ses:
        raise HTTPException(
            status_code=400,
            detail="SES configuration required when provider is 'ses'",
        )

    # Get existing config or create new
    existing = _get_config(tenant_id)
    config = _input_to_config(tenant_id, config_input)

    if existing:
        config.created_at = existing.created_at

    config.updated_at = datetime.utcnow()
    _save_config(config)

    logger.info(
        "email_config_updated",
        tenant_id=tenant_id,
        provider=config.provider.value,
        enabled=config.enabled,
    )

    return _config_to_response(config)


@router.post("/send", response_model=SendResultResponse)
async def send_email_notification(
    request: SendEmailRequest,
    background_tasks: BackgroundTasks,
):
    """Send an email notification for an incident.

    This endpoint fetches the incident context card and sends it via email.
    """
    tenant_id = _get_tenant_id()
    config = _get_config(tenant_id)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Email configuration not found",
        )

    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail="Email notifications are disabled",
        )

    # In production, fetch the actual context card from storage
    # For now, return an error if incident not found
    # This would integrate with your incident storage/orchestrator

    # Placeholder: we would fetch the context card here
    # card = await get_context_card(request.incident_id)
    # if not card:
    #     raise HTTPException(status_code=404, detail="Incident not found")

    raise HTTPException(
        status_code=501,
        detail="Send notification requires incident storage integration. Use /test endpoint to verify configuration.",
    )


@router.post("/test", response_model=SendResultResponse)
async def send_test_email(request: SendTestEmailRequest | None = None):
    """Send a test email to verify configuration."""
    tenant_id = _get_tenant_id()
    config = _get_config(tenant_id)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Email configuration not found. Please configure email settings first.",
        )

    service = EmailNotificationService(config)

    recipient = None
    if request and request.recipient:
        recipient = _input_to_recipient(request.recipient)

    result = await service.send_test_email(recipient)

    if not result.success:
        logger.error(
            "test_email_failed",
            tenant_id=tenant_id,
            error=result.error,
        )

    return _result_to_response(result)


@router.post("/connection-test", response_model=SendResultResponse)
async def test_email_connection():
    """Test the email provider connection without sending an email."""
    tenant_id = _get_tenant_id()
    config = _get_config(tenant_id)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Email configuration not found",
        )

    service = EmailNotificationService(config)
    result = await service.test_connection()

    return _result_to_response(result)


@router.get("/templates", response_model=list[TemplateInfo])
async def list_email_templates():
    """List available email templates."""
    renderer = EmailTemplateRenderer()
    templates = renderer.list_templates()

    return [
        TemplateInfo(
            id=t["id"],
            name=t["name"],
            type=t["type"],
            file=t["file"],
        )
        for t in templates
    ]


@router.get("/templates/{template_id}/preview")
async def preview_template(template_id: str):
    """Preview an email template with sample data."""
    tenant_id = _get_tenant_id()
    config = _get_config(tenant_id)

    if not config:
        # Use a default config for preview
        config = EmailConfig(
            tenant_id=tenant_id,
            from_email="noreply@example.com",
            from_name="Incident Copilot",
        )

    renderer = EmailTemplateRenderer()

    if template_id == "test":
        html_body, text_body = renderer.render_test(config)
        return {
            "template_id": template_id,
            "subject": renderer.get_subject(renderer._infer_template_type(template_id)),
            "html": html_body,
            "text": text_body,
        }

    # For other templates, we'd need sample data
    raise HTTPException(
        status_code=501,
        detail=f"Preview for template '{template_id}' requires sample data. Only 'test' template preview is available.",
    )


@router.delete("/config")
async def delete_email_config():
    """Delete email configuration for current tenant."""
    tenant_id = _get_tenant_id()

    if tenant_id not in _config_store:
        raise HTTPException(
            status_code=404,
            detail="Email configuration not found",
        )

    del _config_store[tenant_id]

    logger.info("email_config_deleted", tenant_id=tenant_id)

    return {"status": "deleted", "tenant_id": tenant_id}
