"""Webhook endpoints for receiving alerts."""

import time

import structlog
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from ..config import get_settings
from ..correlation.engine import get_correlation_engine
from ..integrations.opsgenie import OpsgenieAdapter
from ..integrations.pagerduty_legacy import PagerDutyAdapter
from ..metrics import WEBHOOK_PROCESSING_SECONDS, WEBHOOK_REQUESTS_TOTAL
from ..orchestrator import ContextOrchestrator
from ..web.store import incident_store

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/pagerduty")
async def pagerduty_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_pagerduty_signature: str | None = Header(None, alias="X-PagerDuty-Signature"),
):
    """Receive PagerDuty v3 webhook events with alert correlation."""
    start_time = time.perf_counter()
    status = "error"
    settings = get_settings()
    try:
        body = await request.body()
        pd_adapter = PagerDutyAdapter(settings)

        # Verify signature when a secret is configured; otherwise log a warning
        # (we don't want to silently skip verification).
        if settings.pagerduty_webhook_secret:
            if not x_pagerduty_signature:
                status = "invalid"
                logger.warning("pagerduty_missing_signature")
                raise HTTPException(status_code=401, detail="Missing signature")

            if not pd_adapter.verify_webhook_signature(body, x_pagerduty_signature):
                status = "invalid"
                logger.warning("pagerduty_invalid_signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        else:
            logger.warning("pagerduty_webhook_secret_not_configured_signature_not_verified")
        try:
            payload = await request.json()
        except Exception as e:
            status = "invalid"
            logger.error("pagerduty_invalid_json", error=str(e))
            raise HTTPException(status_code=400, detail="Invalid JSON")
        incident = pd_adapter.parse_webhook(payload)
        if not incident:
            status = "success"
            return {"status": "ignored", "reason": "not an incident trigger"}
        logger.info(
            "pagerduty_incident_received",
            incident_id=incident.incident_id,
            service=incident.service_name,
            severity=incident.severity.value,
        )
        background_tasks.add_task(
            process_pagerduty_incident_background, incident, settings
        )
        status = "success"
        return {
            "status": "accepted",
            "incident_id": incident.incident_id,
            "service": incident.service_name,
        }
    finally:
        WEBHOOK_REQUESTS_TOTAL.labels(source="pagerduty", status=status).inc()
        WEBHOOK_PROCESSING_SECONDS.labels(source="pagerduty").observe(
            time.perf_counter() - start_time
        )


@router.post("/opsgenie")
async def opsgenie_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_opsgenie_signature: str | None = Header(None, alias="X-OpsGenie-Signature"),
):
    """Receive Opsgenie webhook events with alert correlation."""
    start_time = time.perf_counter()
    status = "error"
    settings = get_settings()
    try:
        body = await request.body()
        og_adapter = OpsgenieAdapter(settings)

        # Verify signature when a secret is configured; otherwise log a warning
        # (we don't want to silently skip verification).
        if settings.opsgenie_webhook_secret:
            if not x_opsgenie_signature:
                status = "invalid"
                logger.warning("opsgenie_missing_signature")
                raise HTTPException(status_code=401, detail="Missing signature")
            if not og_adapter.verify_webhook_signature(body, x_opsgenie_signature):
                status = "invalid"
                logger.warning("opsgenie_invalid_signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        else:
            logger.warning("opsgenie_webhook_secret_not_configured_signature_not_verified")
        try:
            payload = await request.json()
        except Exception as e:
            status = "invalid"
            logger.error("opsgenie_invalid_json", error=str(e))
            raise HTTPException(status_code=400, detail="Invalid JSON")
        alert = og_adapter.parse_webhook(payload)
        if not alert:
            status = "success"
            return {"status": "ignored", "reason": "not an alert creation"}
        logger.info(
            "opsgenie_alert_received",
            alert_id=alert.alert_id,
            service=alert.service_name,
            severity=alert.severity.value,
        )
        background_tasks.add_task(process_opsgenie_alert_background, alert, settings)
        status = "success"
        return {
            "status": "accepted",
            "alert_id": alert.alert_id,
            "service": alert.service_name,
        }
    finally:
        WEBHOOK_REQUESTS_TOTAL.labels(source="opsgenie", status=status).inc()
        WEBHOOK_PROCESSING_SECONDS.labels(source="opsgenie").observe(
            time.perf_counter() - start_time
        )


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
        await incident_store.add_incident(
            incident_id=incident.incident_id,
            title=incident.title,
            service_name=incident.service_name,
            severity=incident.severity,
            triggered_at=incident.triggered_at,
        )
        orchestrator = ContextOrchestrator(settings)
        context_card = await orchestrator.process_incident(incident)
        await incident_store.complete_incident(
            incident_id=incident.incident_id,
            context_card=context_card,
        )
    except Exception as e:
        await incident_store.fail_incident(
            incident.incident_id,
            str(e),
        )
        logger.error(
            "pagerduty_background_processing_failed",
            incident_id=incident.incident_id,
            error=str(e),
        )


async def process_opsgenie_alert_background(alert, settings):
    """Background task to correlate and process Opsgenie alert."""
    incident_id = alert.alert_id
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
            incident_id=incident_id,
            title=alert.title,
            description=alert.description,
            severity=alert.severity,
            service_name=alert.service_name,
            triggered_at=alert.triggered_at,
            html_url=alert.url,
        )
        await incident_store.add_incident(
            incident_id=incident_id,
            title=pd_incident.title,
            service_name=pd_incident.service_name,
            severity=pd_incident.severity,
            triggered_at=pd_incident.triggered_at,
        )
        orchestrator = ContextOrchestrator(settings)
        context_card = await orchestrator.process_incident(pd_incident)
        await incident_store.complete_incident(
            incident_id=incident_id,
            context_card=context_card,
        )
    except Exception as e:
        await incident_store.fail_incident(
            incident_id,
            str(e),
        )
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
