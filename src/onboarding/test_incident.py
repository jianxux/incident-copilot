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


async def _is_supabase_persisted(incident_id: str, tenant_id: str | None) -> bool:
    supabase_store = getattr(incident_store, "_supabase", None)
    if supabase_store is None:
        return False
    try:
        persisted = await supabase_store.get_incident(incident_id, tenant_id=tenant_id)
        return persisted is not None
    except Exception as exc:
        logger.error(
            "test_incident_supabase_verify_failed",
            incident_id=incident_id,
            tenant_id=tenant_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return False


async def _complete_with_retry(
    incident: PagerDutyIncident,
    context_card: ContextCard,
    tenant_id: str | None,
    metadata: dict | None = None,
    max_attempts: int = 2,
) -> bool:
    for attempt in range(1, max_attempts + 1):
        try:
            result = await incident_store.complete_incident(
                incident.incident_id,
                context_card,
                metadata=metadata,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning(
                "test_incident_complete_retryable_failure",
                incident_id=incident.incident_id,
                tenant_id=tenant_id,
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if attempt >= max_attempts:
                raise
            continue
        if result is not None:
            if attempt > 1:
                logger.info(
                    "test_incident_complete_retry_succeeded",
                    incident_id=incident.incident_id,
                    tenant_id=tenant_id,
                    attempt=attempt,
                )
            return True

        logger.warning(
            "test_incident_complete_missing_retrying",
            incident_id=incident.incident_id,
            tenant_id=tenant_id,
            attempt=attempt,
            max_attempts=max_attempts,
        )
        await incident_store.add_incident(
            incident_id=incident.incident_id,
            title=incident.title,
            service_name=incident.service_name,
            severity=incident.severity,
            triggered_at=incident.triggered_at,
            tenant_id=tenant_id,
            description=incident.description,
        )

    logger.error(
        "test_incident_complete_missing_after_retries",
        incident_id=incident.incident_id,
        tenant_id=tenant_id,
        max_attempts=max_attempts,
    )
    return False


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
        add_kwargs = {
            "incident_id": incident_id,
            "title": title,
            "service_name": service_name,
            "severity": severity,
            "triggered_at": triggered_at,
            "tenant_id": tenant_id,
            "description": "Synthetic test incident created by onboarding flow.",
        }
        await incident_store.add_incident(**add_kwargs)
        stored = await incident_store.get_incident(incident_id, tenant_id=tenant_id)
        if stored is None:
            logger.warning(
                "test_incident_add_verification_failed_retrying",
                incident_id=incident_id,
                tenant_id=tenant_id,
            )
            await incident_store.add_incident(**add_kwargs)
            stored = await incident_store.get_incident(incident_id, tenant_id=tenant_id)
            if stored is None:
                logger.error(
                    "test_incident_add_verification_failed_after_retry",
                    incident_id=incident_id,
                    tenant_id=tenant_id,
                )
                raise RuntimeError(
                    "test incident was not persisted in store after retry"
                )

        persisted_to_supabase = (
            await _is_supabase_persisted(incident_id, tenant_id) if supabase_enabled else False
        )
        logger.info(
            "test_incident_add_succeeded",
            incident_id=incident_id,
            tenant_id=tenant_id,
            storage_mode="supabase" if persisted_to_supabase else "memory_only",
            persisted_to_supabase=persisted_to_supabase,
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
        await _complete_with_retry(
            incident=incident,
            context_card=card,
            tenant_id=tenant_id,
        )
        logger.info("test_incident_completed", incident_id=incident.incident_id)
    except Exception as e:
        error_message = str(e)
        if isinstance(e, asyncio.TimeoutError):
            error_message = f"Processing timed out after {_PROCESS_TIMEOUT_SECONDS}s"

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
        try:
            await _complete_with_retry(
                incident=incident,
                context_card=fallback_card,
                tenant_id=tenant_id,
                metadata={"fallback": True, "error": error_message},
            )
        except Exception as store_err:
            # Last resort: try to mark as error so it doesn't stay "processing" forever
            logger.error(
                "test_incident_fallback_store_failed",
                incident_id=incident.incident_id,
                error=str(store_err),
            )
            try:
                await incident_store.fail_incident(
                    incident.incident_id,
                    error_message=error_message,
                    metadata={"fallback": True},
                    tenant_id=tenant_id,
                )
            except Exception:
                logger.error(
                    "test_incident_fail_store_also_failed",
                    incident_id=incident.incident_id,
                )
