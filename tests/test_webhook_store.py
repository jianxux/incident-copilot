import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# Some environments expose a supabase namespace package without Client symbols.
# Stub it so importing src.api.webhooks works consistently in unit tests.
if "supabase" not in sys.modules or not hasattr(sys.modules["supabase"], "Client"):
    supabase_stub = types.ModuleType("supabase")
    supabase_stub.Client = object
    supabase_stub.create_client = lambda *_args, **_kwargs: None
    sys.modules["supabase"] = supabase_stub

from src.api.webhooks import (
    process_opsgenie_alert_background,
    process_pagerduty_incident_background,
)
from src.config import Settings
from src.models import ContextCard, OpsgenieAlert, PagerDutyIncident, Severity
from src.web.store import incident_store


@pytest.fixture(autouse=True)
def _reset_incident_store():
    if hasattr(incident_store, "_incidents"):
        incident_store._incidents.clear()
    if hasattr(incident_store, "_order"):
        incident_store._order.clear()
    if hasattr(incident_store, "_subscribers"):
        incident_store._subscribers.clear()


def _allow_notify_result() -> SimpleNamespace:
    return SimpleNamespace(
        should_notify=True,
        correlated=False,
        new_group=True,
        group=None,
        suppression_reason=None,
    )


def _context_card(incident_id: str, service_name: str) -> ContextCard:
    return ContextCard(
        incident_id=incident_id,
        title="context",
        severity=Severity.HIGH,
        service_name=service_name,
        triggered_at=datetime.now(UTC),
        assembly_time_ms=123,
    )


@pytest.mark.asyncio
async def test_pagerduty_background_stores_and_completes_incident():
    incident = PagerDutyIncident(
        incident_id="pd-store-1",
        title="PD test",
        description="desc",
        severity=Severity.HIGH,
        service_name="payments",
        triggered_at=datetime.now(UTC),
        html_url="https://example.pagerduty.com/incidents/pd-store-1",
    )
    settings = Settings(correlation_enabled=True)

    engine = AsyncMock()
    engine.correlate_pagerduty = AsyncMock(return_value=_allow_notify_result())

    original_complete = incident_store.complete_incident
    statuses_before_complete: list[str | None] = []

    async def _complete(*, incident_id: str, context_card: ContextCard):
        stored = await incident_store.get_incident(incident_id)
        statuses_before_complete.append(stored.status if stored else None)
        return await original_complete(
            incident_id=incident_id, context_card=context_card
        )

    with (
        patch(
            "src.api.webhooks.get_correlation_engine",
            new=AsyncMock(return_value=engine),
        ),
        patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(return_value=_context_card("pd-store-1", "payments")),
        ) as process_mock,
        patch(
            "src.api.webhooks.incident_store.complete_incident",
            new=AsyncMock(side_effect=_complete),
        ),
    ):
        await process_pagerduty_incident_background(incident, settings)

    process_mock.assert_awaited_once_with(incident)
    assert statuses_before_complete == ["processing"]
    stored = await incident_store.get_incident("pd-store-1")
    assert stored is not None
    assert stored.status == "completed"


@pytest.mark.asyncio
async def test_pagerduty_background_failure_calls_fail_incident():
    incident = PagerDutyIncident(
        incident_id="pd-fail-1",
        title="PD fail",
        description="desc",
        severity=Severity.HIGH,
        service_name="payments",
        triggered_at=datetime.now(UTC),
        html_url="https://example.pagerduty.com/incidents/pd-fail-1",
    )
    settings = Settings(correlation_enabled=True)

    engine = AsyncMock()
    engine.correlate_pagerduty = AsyncMock(return_value=_allow_notify_result())

    original_fail = incident_store.fail_incident
    fail_mock = AsyncMock(side_effect=original_fail)

    with (
        patch(
            "src.api.webhooks.get_correlation_engine",
            new=AsyncMock(return_value=engine),
        ),
        patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(side_effect=RuntimeError("pd boom")),
        ),
        patch("src.api.webhooks.incident_store.fail_incident", new=fail_mock),
    ):
        await process_pagerduty_incident_background(incident, settings)

    fail_mock.assert_awaited_once_with("pd-fail-1", "pd boom")


@pytest.mark.asyncio
async def test_opsgenie_background_stores_and_completes_incident():
    alert = OpsgenieAlert(
        alert_id="og-store-1",
        title="OG test",
        description="desc",
        severity=Severity.HIGH,
        service_name="checkout",
        triggered_at=datetime.now(UTC),
        url="https://example.app.opsgenie.com/alert/detail/og-store-1/details",
    )
    settings = Settings(correlation_enabled=True)

    engine = AsyncMock()
    engine.correlate_opsgenie = AsyncMock(return_value=_allow_notify_result())

    original_complete = incident_store.complete_incident
    statuses_before_complete: list[str | None] = []

    async def _complete(*, incident_id: str, context_card: ContextCard):
        stored = await incident_store.get_incident(incident_id)
        statuses_before_complete.append(stored.status if stored else None)
        return await original_complete(
            incident_id=incident_id, context_card=context_card
        )

    with (
        patch(
            "src.api.webhooks.get_correlation_engine",
            new=AsyncMock(return_value=engine),
        ),
        patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(return_value=_context_card("og-store-1", "checkout")),
        ) as process_mock,
        patch(
            "src.api.webhooks.incident_store.complete_incident",
            new=AsyncMock(side_effect=_complete),
        ),
    ):
        await process_opsgenie_alert_background(alert, settings)

    assert process_mock.await_count == 1
    processed_incident = process_mock.await_args.args[0]
    assert processed_incident.incident_id == "og-store-1"
    assert statuses_before_complete == ["processing"]
    stored = await incident_store.get_incident("og-store-1")
    assert stored is not None
    assert stored.status == "completed"


@pytest.mark.asyncio
async def test_opsgenie_background_failure_calls_fail_incident():
    alert = OpsgenieAlert(
        alert_id="og-fail-1",
        title="OG fail",
        description="desc",
        severity=Severity.HIGH,
        service_name="checkout",
        triggered_at=datetime.now(UTC),
        url="https://example.app.opsgenie.com/alert/detail/og-fail-1/details",
    )
    settings = Settings(correlation_enabled=True)

    engine = AsyncMock()
    engine.correlate_opsgenie = AsyncMock(return_value=_allow_notify_result())

    original_fail = incident_store.fail_incident
    fail_mock = AsyncMock(side_effect=original_fail)

    with (
        patch(
            "src.api.webhooks.get_correlation_engine",
            new=AsyncMock(return_value=engine),
        ),
        patch(
            "src.api.webhooks.ContextOrchestrator.process_incident",
            new=AsyncMock(side_effect=RuntimeError("og boom")),
        ),
        patch("src.api.webhooks.incident_store.fail_incident", new=fail_mock),
    ):
        await process_opsgenie_alert_background(alert, settings)

    fail_mock.assert_awaited_once_with("og-fail-1", "og boom")
