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
) -> str:
    """Create and start processing a synthetic incident.

    Returns incident_id.
    """

    incident_id = str(uuid.uuid4())
    triggered_at = datetime.now(UTC)
    title = title or f"[TEST] Incident Copilot onboarding test for {service_name}"

    await incident_store.add_incident(
        incident_id=incident_id,
        title=title,
        service_name=service_name,
        severity=severity,
        triggered_at=triggered_at,
    )

    settings = get_settings()
    incident = PagerDutyIncident(
        incident_id=incident_id,
        title=title,
        description="Synthetic test incident created by onboarding flow.",
        severity=severity,
        service_name=service_name,
        triggered_at=triggered_at,
        html_url=f"{settings.app_url}/dashboard/incident/{incident_id}",
    )

    asyncio.create_task(_process(incident, slack_channel))

    return incident_id


async def _process(incident: PagerDutyIncident, slack_channel: str | None) -> None:
    settings = get_settings()
    try:
        orchestrator = ContextOrchestrator(settings)
        card = await orchestrator.process_incident(incident, slack_channel=slack_channel)
        await incident_store.complete_incident(incident.incident_id, card)
        logger.info("test_incident_completed", incident_id=incident.incident_id)
    except Exception as e:
        logger.error("test_incident_failed", incident_id=incident.incident_id, error=str(e))
        await incident_store.fail_incident(incident.incident_id, str(e))
