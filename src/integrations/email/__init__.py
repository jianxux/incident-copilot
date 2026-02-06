"""Email notification integration for incident-copilot."""

from .client import EmailClient, SendGridClient, SESClient, SMTPClient
from .models import (
    DigestConfig,
    DigestFrequency,
    EmailConfig,
    EmailMessage,
    EmailProvider,
    EmailRecipient,
    EmailTemplate,
    EmailTemplateType,
    SendResult,
)
from .service import EmailNotificationService
from .templates import EmailTemplateRenderer

__all__ = [
    # Models
    "EmailConfig",
    "EmailProvider",
    "EmailTemplate",
    "EmailTemplateType",
    "EmailMessage",
    "EmailRecipient",
    "SendResult",
    "DigestConfig",
    "DigestFrequency",
    # Clients
    "EmailClient",
    "SMTPClient",
    "SendGridClient",
    "SESClient",
    # Service
    "EmailNotificationService",
    # Templates
    "EmailTemplateRenderer",
]
