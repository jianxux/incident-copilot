"""Notification Preferences module for incident-copilot.

This module provides:
- Per-user notification preferences with role-based defaults
- Multiple notification channels (email, Slack, SMS, push, webhook)
- Quiet hours / Do Not Disturb settings
- Severity-based filtering and notification rules
- Notification batching and digest options
- Customizable notification templates

Usage:
    from notifications import (
        NotificationService,
        NotificationPreference,
        NotificationPayload,
        NotificationType,
        Severity,
        ChannelType,
        router,
    )

    # Get service singleton
    service = get_notification_service()

    # Check if user should be notified
    should_send, channels, frequency = await service.should_notify(
        user_id="user-123",
        notification_type=NotificationType.INCIDENT_CREATED,
        severity=Severity.P1,
    )

    # Send a notification
    payload = NotificationPayload(
        id="notif-001",
        type=NotificationType.INCIDENT_CREATED,
        severity=Severity.P1,
        title="Critical: Database Outage",
        message="Production database is unreachable",
    )
    result = await service.send_notification("user-123", payload)

    # Include router in FastAPI app
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
"""

from .channels import (
    BaseChannel,
    ChannelConfigError,
    ChannelDeliveryError,
    ChannelError,
    ChannelManager,
    EmailChannel,
    PushChannel,
    SlackChannel,
    SMSChannel,
    WebhookChannel,
    create_channel,
)
from .models import (
    ROLE_DEFAULTS,
    ChannelType,
    DigestFrequency,
    NotificationChannel,
    NotificationPayload,
    NotificationPreference,
    NotificationRule,
    NotificationType,
    QuietHours,
    Severity,
    UserRole,
)
from .routes import router
from .service import (
    InMemoryPreferenceStore,
    NotificationService,
    PreferenceStore,
    get_notification_service,
)
from .templates import (
    DEFAULT_TEMPLATES,
    SEVERITY_COLOR,
    SEVERITY_EMOJI,
    NotificationTemplate,
    TemplateRenderer,
)

__all__ = [
    # Models
    "ChannelType",
    "DigestFrequency",
    "NotificationChannel",
    "NotificationPayload",
    "NotificationPreference",
    "NotificationRule",
    "NotificationType",
    "QuietHours",
    "ROLE_DEFAULTS",
    "Severity",
    "UserRole",
    # Service
    "NotificationService",
    "PreferenceStore",
    "InMemoryPreferenceStore",
    "get_notification_service",
    # Channels
    "BaseChannel",
    "ChannelError",
    "ChannelConfigError",
    "ChannelDeliveryError",
    "ChannelManager",
    "EmailChannel",
    "PushChannel",
    "SlackChannel",
    "SMSChannel",
    "WebhookChannel",
    "create_channel",
    # Templates
    "DEFAULT_TEMPLATES",
    "NotificationTemplate",
    "SEVERITY_COLOR",
    "SEVERITY_EMOJI",
    "TemplateRenderer",
    # Routes
    "router",
]
