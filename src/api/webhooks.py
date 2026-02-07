"""Webhook endpoints for receiving alerts."""

import structlog
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from ..config import get_settings
from ..correlation.engine import get_correlation_engine
from ..integrations.opsgenie import OpsgenieAdapter
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
    """Receive PagerDuty v3 webhook events with alert correlation."""
    settings = get_settings()
    body = await request.body()
    pd_adapter = PagerDutyAdapter(settings)
    if x_pagerduty_signature and not pd_adapter.verify_webhook_signature(
        body, x_pagerduty_signature
    ):
        logger.warning("pagerduty_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("pagerduty_invalid_json", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")
    incident = pd_adapter.parse_webhook(payload)
    if not incident:
        return {"status": "ignored", "reason": "not an incident trigger"}
    logger.info(
        "pagerduty_incident_received",
        incident_id=incident.incident_id,
        service=incident.service_name,
        severity=incident.severity.value,
    )
    background_tasks.add_task(process_pagerduty_incident_background, incident, settings)
    return {
        "status": "accepted",
        "incident_id": incident.incident_id,
        "service": incident.service_name,
    }


@router.post("/opsgenie")
async def opsgenie_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_opsgenie_signature: str | None = Header(None, alias="X-OpsGenie-Signature"),
):
    """Receive Opsgenie webhook events with alert correlation."""
    settings = get_settings()
    body = await request.body()
    og_adapter = OpsgenieAdapter(settings)
    if x_opsgenie_signature and not og_adapter.verify_webhook_signature(body, x_opsgenie_signature):
        logger.warning("opsgenie_invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("opsgenie_invalid_json", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON")
    alert = og_adapter.parse_webhook(payload)
    if not alert:
        return {"status": "ignored", "reason": "not an alert creation"}
    logger.info(
        "opsgenie_alert_received",
        alert_id=alert.alert_id,
        service=alert.service_name,
        severity=alert.severity.value,
    )
    background_tasks.add_task(process_opsgenie_alert_background, alert, settings)
    return {
        "status": "accepted",
        "alert_id": alert.alert_id,
        "service": alert.service_name,
    }


async def process_pagerduty_incident_background(incident, settings):
    """Background task to correlate and process PagerDuty incident."""
    try:
        if getattr(settings, "correlation_enabled", True):
            engine = await get_correlation_engine(settings)
            result = await engine.correlate_pagerduty(incident)
            if not result.should_notify:
                logger.info(
                    "pagerduty_notification_suppressed",
                    incident_id=incident.incident_id,
                    group_id=result.group.group_id if result.group else None,
                    reason=result.suppression_reason,
                )
                return
            logger.info(
                "pagerduty_notification_allowed",
                incident_id=incident.incident_id,
                correlated=result.correlated,
                new_group=result.new_group,
            )
        orchestrator = ContextOrchestrator(settings)
        await orchestrator.process_incident(incident)
    except Exception as e:
        logger.error(
            "pagerduty_background_processing_failed",
            incident_id=incident.incident_id,
            error=str(e),
        )


async def process_opsgenie_alert_background(alert, settings):
    """Background task to correlate and process Opsgenie alert."""
    try:
        if getattr(settings, "correlation_enabled", True):
            engine = await get_correlation_engine(settings)
            result = await engine.correlate_opsgenie(alert)
            if not result.should_notify:
                logger.info(
                    "opsgenie_notification_suppressed",
                    alert_id=alert.alert_id,
                    group_id=result.group.group_id if result.group else None,
                    reason=result.suppression_reason,
                )
                return
            logger.info(
                "opsgenie_notification_allowed",
                alert_id=alert.alert_id,
                correlated=result.correlated,
                new_group=result.new_group,
            )
        from ..models import PagerDutyIncident

        pd_incident = PagerDutyIncident(
            incident_id=alert.alert_id,
            title=alert.title,
            description=alert.description,
            severity=alert.severity,
            service_name=alert.service_name,
            triggered_at=alert.triggered_at,
            html_url=alert.url,
        )
        orchestrator = ContextOrchestrator(settings)
        await orchestrator.process_incident(pd_incident)
    except Exception as e:
        logger.error(
            "opsgenie_background_processing_failed",
            alert_id=alert.alert_id,
            error=str(e),
        )


async def process_incident_background(incident, settings):
    """Legacy background task for backward compatibility."""
    await process_pagerduty_incident_background(incident, settings)


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
