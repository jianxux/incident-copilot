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
from ..models import AILogSummary, ContextCard, PagerDutyIncident, Severity
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

    await incident_store.add_incident(
        incident_id=incident_id,
        title=title,
        service_name=service_name,
        severity=severity,
        triggered_at=triggered_at,
        tenant_id=tenant_id,
        description="Synthetic test incident created by onboarding flow.",
    )

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


async def _process(
    incident: PagerDutyIncident,
    slack_channel: str | None,
    tenant_id: str | None,
) -> None:
    settings = get_settings()
    try:
        orchestrator = ContextOrchestrator(settings)
        card = await orchestrator.process_incident(
            incident, slack_channel=slack_channel, tenant_id=tenant_id
        )
        await incident_store.complete_incident(
            incident.incident_id, card, tenant_id=tenant_id
        )
        logger.info("test_incident_completed", incident_id=incident.incident_id)
    except Exception as e:
        error_message = str(e)
        fallback_card = ContextCard(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=incident.severity,
            service_name=incident.service_name,
            triggered_at=incident.triggered_at,
            alert_url=incident.html_url,
            ai_summary=AILogSummary(
                top_issues=[f"Orchestrator error: {error_message}"],
                explanation="Generated fallback context after orchestrator failure.",
                likely_cause=error_message,
                suggested_actions=[
                    "Verify onboarding integrations are connected and credentials are valid.",
                    "Re-run onboarding test incident after fixing integration errors.",
                ],
            ),
            assembly_time_ms=0,
            errors=[f"orchestrator: {error_message}"],
        )
        logger.error(
            "test_incident_fallback_completed",
            incident_id=incident.incident_id,
            error=error_message,
        )
        await incident_store.complete_incident(
            incident.incident_id,
            fallback_card,
            metadata={"fallback": True, "error": error_message},
            tenant_id=tenant_id,
        )
