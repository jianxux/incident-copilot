"""Test incident helper for onboarding.

Creates a synthetic incident and runs it through the normal pipeline:
webhook -> processing -> context assembly -> Slack notification.

For now we skip the actual external webhook delivery and invoke the orchestrator
directly, while still emitting progress via the shared IncidentStore.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from ..config import get_settings
from ..models import PagerDutyIncident, Severity
from ..orchestrator import ContextOrchestrator
from ..web.store import incident_store

logger = structlog.get_logger()


async def start_test_incident(
    *,
    service_name: str = "payments-api",
    severity: Severity = Severity.HIGH,
    title: str | None = None,
    slack_channel: str | None = None,
    tenant_id: str | None = None,
) -> str:
    """Create and start processing a synthetic incident.

    Returns incident_id.
    """

    incident_id = str(uuid.uuid4())
    triggered_at = datetime.now(UTC)
    title = title or f"[TEST] Incident Copilot onboarding test for {service_name}"
    settings = get_settings()
    supabase_enabled = bool(
        settings.supabase_db_enabled and settings.supabase_url and settings.supabase_anon_key
    )

    if supabase_enabled and not tenant_id:
        raise ValueError("tenant_id is required when SUPABASE_DB_ENABLED=true")

    try:
        await incident_store.add_incident(
            incident_id=incident_id,
            title=title,
            service_name=service_name,
            severity=severity,
            triggered_at=triggered_at,
            tenant_id=tenant_id,
            description="Synthetic test incident created by onboarding flow.",
        )
        logger.info(
            "test_incident_add_succeeded",
            incident_id=incident_id,
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.error(
            "test_incident_add_failed",
            incident_id=incident_id,
            tenant_id=tenant_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise

    incident = PagerDutyIncident(
        incident_id=incident_id,
        title=title,
        description="Synthetic test incident created by onboarding flow.",
        severity=severity,
        service_name=service_name,
        triggered_at=triggered_at,
        html_url=f"{settings.app_url}/dashboard/incident/{incident_id}",
    )

    asyncio.create_task(_process(incident, slack_channel, tenant_id))

    return incident_id


_PROCESS_TIMEOUT_SECONDS = 120  # Max time for orchestrator processing


async def _process(
    incident: PagerDutyIncident,
    slack_channel: str | None,
    tenant_id: str | None,
) -> None:
    settings = get_settings()
    try:
        orchestrator = ContextOrchestrator(settings)
        # Apply a timeout so we don't hang forever
        card = await asyncio.wait_for(
            orchestrator.process_incident(
                incident, slack_channel=slack_channel, tenant_id=tenant_id
            ),
            timeout=_PROCESS_TIMEOUT_SECONDS,
        )
        await incident_store.complete_incident(
            incident.incident_id, card, tenant_id=tenant_id
        )
        logger.info("test_incident_completed", incident_id=incident.incident_id)
    except Exception as e:
        error_message = str(e)
        if isinstance(e, asyncio.TimeoutError):
            error_message = f"Processing timed out after {_PROCESS_TIMEOUT_SECONDS}s"
        logger.error(
            "test_incident_processing_failed",
            incident_id=incident.incident_id,
            tenant_id=tenant_id,
            error=error_message,
        )

        # Keep onboarding incidents visible as "processing" even when orchestration
        # fails. If the row was not persisted (for example due to transient DB
        # issues), re-add it in processing state as a best-effort recovery.
        try:
            existing = await incident_store.get_incident(
                incident.incident_id, tenant_id=tenant_id
            )
            if existing is None:
                await incident_store.add_incident(
                    incident_id=incident.incident_id,
                    title=incident.title,
                    service_name=incident.service_name,
                    severity=incident.severity,
                    triggered_at=incident.triggered_at,
                    source="manual",
                    source_url=incident.html_url,
                    source_id=incident.incident_id,
                    tenant_id=tenant_id,
                    description=incident.description,
                    metadata={"processing_error": error_message},
                )
                logger.info(
                    "test_incident_readded_after_processing_failure",
                    incident_id=incident.incident_id,
                    tenant_id=tenant_id,
                )
        except Exception as store_err:
            logger.error(
                "test_incident_processing_failure_persist_check_failed",
                incident_id=incident.incident_id,
                tenant_id=tenant_id,
                error=str(store_err),
                error_type=type(store_err).__name__,
            )
