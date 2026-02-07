"""FastAPI routes for webhook management."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .models import (
    BulkDeliveryRequest,
    BulkDeliveryResponse,
    WebhookConfig,
    WebhookConfigCreate,
    WebhookConfigUpdate,
    WebhookDelivery,
    WebhookStats,
    WebhookTestRequest,
    WebhookTestResponse,
)
from .service import webhook_service
from .signatures import generate_signing_secret

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def get_current_org_id() -> UUID:
    """Dependency to get current organization ID (placeholder)."""
    # In real app, extract from auth token
    return UUID("00000000-0000-0000-0000-000000000001")


OrgId = Annotated[UUID, Depends(get_current_org_id)]


@router.post("", response_model=WebhookConfig, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    config: WebhookConfigCreate,
    org_id: OrgId
) -> WebhookConfig:
    """Create a new webhook configuration."""
    webhook = WebhookConfig(
        **config.model_dump(),
        organization_id=org_id,
        secret=generate_signing_secret()
    )
    webhook_service.register_webhook(webhook)
    return webhook


@router.get("", response_model=list[WebhookConfig])
async def list_webhooks(org_id: OrgId) -> list[WebhookConfig]:
    """List all webhooks for the organization."""
    return webhook_service.get_webhooks_for_org(org_id)


@router.get("/{webhook_id}", response_model=WebhookConfig)
async def get_webhook(webhook_id: UUID, org_id: OrgId) -> WebhookConfig:
    """Get a specific webhook configuration."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.patch("/{webhook_id}", response_model=WebhookConfig)
async def update_webhook(
    webhook_id: UUID,
    update: WebhookConfigUpdate,
    org_id: OrgId
) -> WebhookConfig:
    """Update a webhook configuration."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(webhook, field, value)
    
    from datetime import datetime
    webhook.updated_at = datetime.utcnow()
    
    return webhook


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: UUID, org_id: OrgId) -> None:
    """Delete a webhook configuration."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    webhook_service.unregister_webhook(webhook_id)


@router.post("/{webhook_id}/rotate-secret", response_model=WebhookConfig)
async def rotate_secret(webhook_id: UUID, org_id: OrgId) -> WebhookConfig:
    """Rotate the webhook signing secret."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    webhook.secret = generate_signing_secret()
    from datetime import datetime
    webhook.updated_at = datetime.utcnow()
    
    return webhook


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: UUID,
    request: WebhookTestRequest,
    org_id: OrgId
) -> WebhookTestResponse:
    """Send a test event to the webhook."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    delivery = await webhook_service.test_webhook(
        webhook, request.event_type, request.custom_payload
    )
    
    # Build signature for response
    from .signatures import generate_signature
    sig, _ = generate_signature(delivery.request_body, webhook.secret)
    
    return WebhookTestResponse(
        success=delivery.status.value == "delivered",
        status_code=delivery.response_status_code,
        response_body=delivery.response_body,
        duration_ms=delivery.duration_ms or 0,
        error=delivery.error_message,
        signature_header=sig
    )


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDelivery])
async def list_deliveries(
    webhook_id: UUID,
    org_id: OrgId,
    limit: int = Query(default=50, le=200)
) -> list[WebhookDelivery]:
    """List recent deliveries for a webhook."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    return webhook_service.get_deliveries_for_webhook(webhook_id, limit)


@router.get("/{webhook_id}/deliveries/{delivery_id}", response_model=WebhookDelivery)
async def get_delivery(
    webhook_id: UUID,
    delivery_id: UUID,
    org_id: OrgId
) -> WebhookDelivery:
    """Get details of a specific delivery."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    delivery = webhook_service.get_delivery(delivery_id)
    if not delivery or delivery.webhook_id != webhook_id:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    return delivery


@router.get("/{webhook_id}/stats", response_model=WebhookStats)
async def get_webhook_stats(webhook_id: UUID, org_id: OrgId) -> WebhookStats:
    """Get statistics for a webhook."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    stats = webhook_service.get_stats(webhook_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Stats not available")
    
    return stats


@router.post("/{webhook_id}/reset-circuit")
async def reset_circuit_breaker(webhook_id: UUID, org_id: OrgId) -> dict:
    """Manually reset the circuit breaker for a webhook."""
    webhook = webhook_service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    from .models import CircuitState
    webhook.circuit_state = CircuitState.CLOSED
    webhook.failure_count = 0
    webhook.circuit_opened_at = None
    
    return {"status": "reset", "circuit_state": webhook.circuit_state.value}


@router.post("/bulk-deliver", response_model=BulkDeliveryResponse)
async def bulk_deliver(
    request: BulkDeliveryRequest,
    org_id: OrgId
) -> BulkDeliveryResponse:
    """Deliver multiple events in bulk."""
    # Validate all events belong to org
    for event in request.events:
        if event.organization_id != org_id:
            raise HTTPException(
                status_code=403,
                detail="Event organization mismatch"
            )
    
    # Validate webhook IDs if provided
    if request.webhook_ids:
        for wid in request.webhook_ids:
            webhook = webhook_service.get_webhook(wid)
            if not webhook or webhook.organization_id != org_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Webhook {wid} not found"
                )
    
    deliveries = await webhook_service.deliver_bulk(
        request.events, request.webhook_ids
    )
    
    # Count webhooks involved
    webhook_ids_used = set(d.webhook_id for d in deliveries)
    
    return BulkDeliveryResponse(
        total_events=len(request.events),
        total_webhooks=len(webhook_ids_used),
        queued_deliveries=len(deliveries),
        errors=[]
    )
