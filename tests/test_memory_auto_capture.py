"""Tests for orchestrator-driven automatic memory capture."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.auth.middleware import AuthContext
from src.config import Settings
from src.models import (
    AILogSummary,
    DatadogContext,
    LogEntry,
    PagerDutyIncident,
    Severity,
)
from src.orchestrator import ContextOrchestrator
from src.web.store import incident_store


def _make_incident(incident_id: str = "INC-AUTO-1") -> PagerDutyIncident:
    return PagerDutyIncident(
        incident_id=incident_id,
        title="Checkout API elevated 5xx",
        description="Customers are seeing checkout failures",
        severity=Severity.HIGH,
        service_name="checkout-api",
        triggered_at=datetime(2026, 2, 22, 10, 0, tzinfo=UTC),
    )


def _stub_orchestrator_dependencies(orchestrator: ContextOrchestrator) -> None:
    orchestrator._fetch_scm_context = AsyncMock(return_value=None)
    orchestrator._fetch_log_context = AsyncMock(return_value=None)
    orchestrator._fetch_oncall_roster = AsyncMock(return_value=None)
    orchestrator._fetch_topology_context = AsyncMock(return_value=None)
    orchestrator.runbook_linker.find_relevant_runbooks = MagicMock(return_value=[])
    orchestrator.verdict_engine.generate_verdict = AsyncMock(return_value=None)
    orchestrator.similarity_search.store_and_search = AsyncMock(return_value=[])
    orchestrator.slack.send_context_card = AsyncMock(return_value=True)


@pytest.mark.asyncio
async def test_process_incident_auto_capture_scheduled():
    orchestrator = ContextOrchestrator(Settings())
    _stub_orchestrator_dependencies(orchestrator)

    orchestrator._capture_incident_to_memory = AsyncMock(return_value=None)

    await orchestrator.process_incident(_make_incident(), slack_channel=None)
    await asyncio.sleep(0)

    orchestrator._capture_incident_to_memory.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_failure_does_not_break_incident_processing():
    orchestrator = ContextOrchestrator(Settings())
    _stub_orchestrator_dependencies(orchestrator)

    orchestrator.incident_capture = MagicMock()
    orchestrator.incident_capture.capture = AsyncMock(
        side_effect=RuntimeError("memory capture failed")
    )

    card = await orchestrator.process_incident(_make_incident("INC-AUTO-2"))
    await asyncio.sleep(0)

    assert card.incident_id == "INC-AUTO-2"
    orchestrator.slack.send_context_card.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_incident_wraps_string_ai_summary_and_handles_string_verdict(
    monkeypatch,
):
    orchestrator = ContextOrchestrator(Settings())
    _stub_orchestrator_dependencies(orchestrator)

    orchestrator._fetch_log_context = AsyncMock(
        return_value=DatadogContext(
            service="checkout-api",
            logs=[
                LogEntry(
                    timestamp=datetime(2026, 2, 22, 10, 1, tzinfo=UTC),
                    level="error",
                    message="connection timeout",
                    service="checkout-api",
                )
            ],
            metrics=None,
        )
    )
    orchestrator.summarizer.summarize = AsyncMock(return_value="LLM summary text")
    orchestrator.verdict_engine.generate_verdict = AsyncMock(
        return_value="verdict text"
    )
    # Keep explicit-channel delivery active, but avoid ts assignment onto strict ContextCard.
    orchestrator.slack.send_context_card = AsyncMock(return_value={})

    captured: dict = {}

    def _fake_generate_actions(self, verdict, context):
        captured["verdict"] = verdict
        captured["context"] = context
        return []

    monkeypatch.setattr(
        "src.actions.engine.ActionEngine.generate_actions", _fake_generate_actions
    )

    card = await orchestrator.process_incident(
        _make_incident("INC-AUTO-3"), slack_channel="C123"
    )
    await asyncio.sleep(0)

    assert isinstance(card.ai_summary, AILogSummary)
    assert card.ai_summary.explanation == "LLM summary text"
    assert captured["verdict"] == {"summary": "verdict text"}


@pytest.mark.asyncio
async def test_resolve_incident_triggers_resolution_capture(monkeypatch):
    from src.api import incidents as incidents_api

    if hasattr(incident_store, "_incidents"):
        incident_store._incidents.clear()
    if hasattr(incident_store, "_order"):
        incident_store._order.clear()

    now = datetime.now(UTC)
    await incident_store.add_incident(
        incident_id="inc-resolve-memory",
        title="Payments API degradation",
        service_name="payments-api",
        severity=Severity.CRITICAL,
        triggered_at=now,
    )

    captured_calls: list[dict] = []

    async def _fake_resolution_capture_best_effort(**kwargs):
        captured_calls.append(kwargs)

    def _run_now(coro):
        return asyncio.get_running_loop().create_task(coro)

    monkeypatch.setattr(incidents_api, "is_supabase_db_enabled", lambda: False)
    monkeypatch.setattr(
        incidents_api,
        "_capture_resolution_memory_best_effort",
        _fake_resolution_capture_best_effort,
    )
    monkeypatch.setattr(incidents_api.asyncio, "create_task", _run_now)

    tenant = MagicMock()
    tenant.id = "tenant-auto-memory"
    user = MagicMock()
    user.email = "oncall@example.com"
    auth = AuthContext(user=user, tenant=tenant)

    payload = await incidents_api.resolve_incident(
        "inc-resolve-memory",
        incidents_api.ResolveRequest(resolution="Rollback complete"),
        auth=auth,
    )
    await asyncio.sleep(0)

    assert payload["status"] == "resolved"
    assert len(captured_calls) == 1
    assert captured_calls[0]["incident"]["id"] == "inc-resolve-memory"
    assert captured_calls[0]["resolution"] == "Rollback complete"
