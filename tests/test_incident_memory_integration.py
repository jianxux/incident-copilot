"""Integration tests for Incident Memory Phase 2 wiring."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.copilot import AICopilot
from src.config import Settings
from src.memory.models import IncidentRecallResult, IncidentRecord
from src.models import (
    AILogSummary,
    ContextCard,
    DatadogContext,
    LogEntry,
    PagerDutyIncident,
    Severity,
)
from src.orchestrator import ContextOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_uses_incident_recall_before_ai_summary():
    settings = Settings()
    orchestrator = ContextOrchestrator(settings)

    logs = [
        LogEntry(
            timestamp=datetime(2026, 2, 13, 10, 5, 0),
            level="error",
            message="DB connection timeout for checkout",
            service="checkout-api",
        )
    ]
    datadog_context = DatadogContext(service="checkout-api", logs=logs, metrics=None)

    orchestrator._fetch_scm_context = AsyncMock(return_value=None)
    orchestrator._fetch_log_context = AsyncMock(return_value=datadog_context)
    orchestrator._fetch_oncall_roster = AsyncMock(return_value=None)
    orchestrator._fetch_topology_context = AsyncMock(return_value=None)
    orchestrator.runbook_linker.find_relevant_runbooks = MagicMock(return_value=[])
    orchestrator.verdict_engine.generate_verdict = AsyncMock(return_value=None)
    orchestrator.slack.send_context_card = AsyncMock(return_value=True)
    orchestrator.similarity_search.store_and_search = AsyncMock(return_value=[])

    orchestrator.summarizer.summarize = AsyncMock(
        return_value=AILogSummary(
            top_issues=["db timeout"],
            explanation="Database saturation",
            likely_cause="Connection pool exhausted",
            suggested_actions=["Scale DB read replicas"],
        )
    )

    recalled = [
        IncidentRecallResult(
            record=IncidentRecord(
                id="inc-100",
                title="Checkout API timeout spike",
                created_at=datetime(2026, 2, 1, 9, 0, 0),
                severity="high",
                services_affected=["checkout-api"],
                root_cause_summary="DB pool exhaustion during traffic spike",
                resolution_summary="Increased pool size and restarted workers",
                embedding=[0.0, 0.0, 0.0],
            ),
            score=0.87,
            vector_similarity=0.87,
            temporal_decay=0.95,
        )
    ]
    fake_recall = MagicMock()
    fake_recall.recall = AsyncMock(return_value=recalled)
    orchestrator.incident_recall = fake_recall

    incident = PagerDutyIncident(
        incident_id="INC-42",
        title="Checkout API errors",
        description="Customers cannot place orders",
        severity=Severity.HIGH,
        service_name="checkout-api",
        triggered_at=datetime(2026, 2, 13, 10, 0, 0),
    )

    card = await orchestrator.process_incident(incident, slack_channel=None)

    fake_recall.recall.assert_awaited_once()
    orchestrator.summarizer.summarize.assert_awaited_once()
    summarize_kwargs = orchestrator.summarizer.summarize.await_args.kwargs
    assert summarize_kwargs["similar_incidents"]
    assert summarize_kwargs["similar_incidents"][0].incident_id == "inc-100"
    assert card.similar_incidents
    assert card.similar_incidents[0].title == "Checkout API timeout spike"
    assert card.similar_incidents[0].severity == "high"
    orchestrator.similarity_search.store_and_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_copilot_chat_uses_search_past_incidents_tool_for_relevant_question():
    copilot = AICopilot(Settings())

    fake_anthropic = MagicMock()
    fake_anthropic.messages = MagicMock()
    fake_anthropic.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text="This looks like a repeat DB issue.")]
        )
    )
    copilot.client = fake_anthropic

    recalled = [
        IncidentRecallResult(
            record=IncidentRecord(
                id="inc-77",
                title="Payments DB saturation",
                created_at=datetime(2026, 1, 20, 11, 0, 0),
                severity="critical",
                services_affected=["payments-api"],
                root_cause_summary="Connection exhaustion after deploy",
                resolution_summary="Rolled back deploy and increased max connections",
                embedding=[0.0, 0.0, 0.0],
            ),
            score=0.92,
            vector_similarity=0.92,
            temporal_decay=0.9,
        )
    ]
    fake_recall = MagicMock()
    fake_recall.recall = AsyncMock(return_value=recalled)
    copilot.incident_recall = fake_recall

    card = ContextCard(
        incident_id="INC-55",
        title="Payments errors",
        severity=Severity.CRITICAL,
        service_name="payments-api",
        triggered_at=datetime(2026, 2, 13, 11, 0, 0),
    )

    response = await copilot.chat(
        incident_id="INC-55",
        user_message="Has this happened before? Search past incidents for payments",
        context_card=card,
    )

    assert "repeat DB issue" in response
    fake_recall.recall.assert_awaited_once()

    create_kwargs = fake_anthropic.messages.create.await_args.kwargs
    assert "Tool search_past_incidents results" in create_kwargs["system"]
    assert "Rolled back deploy" in create_kwargs["system"]
