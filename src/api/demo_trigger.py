"""Interactive demo trigger endpoints.

This router provides a lightweight way for new users to experience the full
incident processing pipeline without needing external integrations configured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..models import PagerDutyIncident, Severity
from ..orchestrator import ContextOrchestrator

logger = structlog.get_logger()

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _fake_incident_for_scenario(scenario: str) -> PagerDutyIncident:
    now = datetime.now(UTC)
    incident_id = f"DEMO-{scenario.upper()}-{uuid4().hex[:8]}"

    if scenario == "deploy-regression":
        return PagerDutyIncident(
            incident_id=incident_id,
            incident_number=42001,
            title="🚨 Checkout API returning 500s after v2.14.0 deploy",
            description=(
                "Error rate spiked immediately after deploy. Customers cannot place orders. "
                "Symptoms: HTTP 500 on /checkout/submit, elevated latency, rollback pending."
            ),
            severity=Severity.CRITICAL,
            service_name="checkout-api",
            service_id="P0DEMO1",
            triggered_at=now,
            html_url="https://pagerduty.example/incidents/DEMO-DEPLOY",
            assigned_to=["oncall-payments"],
        )

    if scenario == "database-outage":
        return PagerDutyIncident(
            incident_id=incident_id,
            incident_number=42002,
            title="Database connection pool exhausted (timeouts across services)",
            description=(
                "P95 latency climbing; requests timing out waiting for DB connections. "
                "Errors: 'timeout acquiring a connection from the pool'."
            ),
            severity=Severity.HIGH,
            service_name="orders-api",
            service_id="P0DEMO2",
            triggered_at=now,
            html_url="https://pagerduty.example/incidents/DEMO-DB",
            assigned_to=["oncall-platform"],
        )

    if scenario == "memory-leak":
        return PagerDutyIncident(
            incident_id=incident_id,
            incident_number=42003,
            title="Worker OOMKilled: suspected memory leak (restarts every ~6m)",
            description=(
                "Kubernetes reports OOMKilled for worker pods. Restart loop causes backlog. "
                "Heap usage grows steadily after processing large jobs."
            ),
            severity=Severity.HIGH,
            service_name="async-worker",
            service_id="P0DEMO3",
            triggered_at=now,
            html_url="https://pagerduty.example/incidents/DEMO-OOM",
            assigned_to=["oncall-core"],
        )

    raise HTTPException(
        status_code=400,
        detail={
            "error": "unknown_scenario",
            "supported": [
                "deploy-regression",
                "database-outage",
                "memory-leak",
            ],
        },
    )


@router.post("/trigger")
async def trigger_demo(scenario: str = "deploy-regression"):
    """Trigger a demo incident and run it through the real processing pipeline."""

    settings = get_settings()

    try:
        incident = _fake_incident_for_scenario(scenario)
        orchestrator = ContextOrchestrator(settings)
        context_card = await orchestrator.process_incident(incident)

        return {
            "status": "ok",
            "scenario": scenario,
            "incident": incident.model_dump(mode="json"),
            "context_card": context_card.model_dump(mode="json"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("demo_trigger_failed", scenario=scenario, error=str(e))
        return {
            "status": "error",
            "scenario": scenario,
            "error": str(e),
        }
