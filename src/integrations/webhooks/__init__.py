"""Webhook Outbound Module for Incident Copilot.

Provides configurable outbound webhooks with:
- HMAC signature verification
- Retry with exponential backoff
- Circuit breaker for failing endpoints
- Customizable payload templates
- Bulk delivery support
"""

from .models import (
    BulkDeliveryRequest,
    BulkDeliveryResponse,
    CircuitState,
    DeliveryStatus,
    WebhookConfig,
    WebhookConfigCreate,
    WebhookConfigUpdate,
    WebhookDelivery,
    WebhookEvent,
    WebhookEventType,
    WebhookStats,
    WebhookTestRequest,
    WebhookTestResponse,
)
from .routes import router
from .service import webhook_service
from .signatures import generate_signature, generate_signing_secret, verify_signature
from .templates import PayloadTemplate, render_webhook_payload, template_manager

__all__ = [
    # Models
    "WebhookConfig",
    "WebhookConfigCreate",
    "WebhookConfigUpdate",
    "WebhookEvent",
    "WebhookDelivery",
    "WebhookEventType",
    "DeliveryStatus",
    "CircuitState",
    "WebhookStats",
    "WebhookTestRequest",
    "WebhookTestResponse",
    "BulkDeliveryRequest",
    "BulkDeliveryResponse",
    # Service
    "webhook_service",
    # Routes
    "router",
    # Signatures
    "generate_signature",
    "verify_signature",
    "generate_signing_secret",
    # Templates
    "PayloadTemplate",
    "template_manager",
    "render_webhook_payload",
]
