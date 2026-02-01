"""Webhook endpoints for receiving alerts."""

import structlog
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from ..config import get_settings
from ..integrations.pagerduty import PagerDutyAdapter
from ..orchestrator import ContextOrchestrator

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/pagerduty")
async def pagerduty_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_pagerduty_signature: str | None = Header(None, alias="X-PagerDuty-Signature"),
):
    """
    Receive PagerDuty v3 webhook events.

    Verifies signature, parses incident, and triggers context assembly.
    """
    settings = get_settings()

    # Get raw body for signature verification
    body = await request.body()

    # Verify signature
    pd_adapter = PagerDutyAdapter(settings)
    if x_pagerduty_signature and not pd_adapter.verify_webhook_signature(
        body, x_pagerduty_signature
    ):
        logger.warning("pagerduty_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("pagerduty_invalid_json", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Parse incident
    incident = pd_adapter.parse_webhook(payload)

    if not incident:
        # Not an incident trigger event, acknowledge anyway
        return {"status": "ignored", "reason": "not an incident trigger"}

    logger.info(
        "pagerduty_incident_received",
        incident_id=incident.incident_id,
        service=incident.service_name,
        severity=incident.severity.value,
    )

    # Process in background to respond quickly to PagerDuty
    background_tasks.add_task(process_incident_background, incident, settings)

    return {
        "status": "accepted",
        "incident_id": incident.incident_id,
        "service": incident.service_name,
    }


async def process_incident_background(incident, settings):
    """Background task to process incident and send context card."""
    try:
        orchestrator = ContextOrchestrator(settings)
        await orchestrator.process_incident(incident)
    except Exception as e:
        logger.error(
            "background_processing_failed",
            incident_id=incident.incident_id,
            error=str(e),
        )


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
