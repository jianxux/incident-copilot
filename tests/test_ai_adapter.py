"""Tests for src.ai.adapter (AI boundary adapter layer).

Focus:
- Orchestrator-style kwargs compatibility (VerdictEngine)
- LogSummarizer accepts service_name and delegates
- Stub fallback when AI service is not configured
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import AsyncMock

import pytest

from src.ai import adapter


@pytest.mark.anyio
async def test_verdict_engine_accepts_orchestrator_style_kwargs(monkeypatch):
    engine = adapter.VerdictEngine(settings=None)

    mock_generate = AsyncMock(return_value={"verdict": "ok"})
    monkeypatch.setattr(adapter.ai_client, "generate_verdict", mock_generate)

    await engine.generate_verdict(
        title="High error rate",
        service_name="payments-api",
        severity="high",
        triggered_at="2026-02-16T00:00:00Z",
        recent_deploys=[{"sha": "abc"}],
        log_summary={"summary": "things broke"},
        topology={"blast_radius": 3},
        similar_incidents=[{"id": "INC-1"}],
    )

    mock_generate.assert_awaited_once()
    kwargs = mock_generate.await_args.kwargs

    assert kwargs["alert_data"]["title"] == "High error rate"
    assert kwargs["alert_data"]["service_name"] == "payments-api"
    assert kwargs["alert_data"]["severity"] == "high"
    assert kwargs["deploys"] == [{"sha": "abc"}]
    assert isinstance(kwargs["log_summary"], str)
    assert "things broke" in kwargs["log_summary"]
    assert kwargs["metrics"] == {"blast_radius": 3}
    assert kwargs["similar_incidents"] == [{"id": "INC-1"}]


@pytest.mark.anyio
async def test_log_summarizer_accepts_service_name_and_delegates(monkeypatch):
    summarizer = adapter.LogSummarizer(settings=None)

    mock_summarize = AsyncMock(return_value={"summary": "summarized"})
    monkeypatch.setattr(adapter.ai_client, "summarize_logs", mock_summarize)

    out = await summarizer.summarize(
        logs=[{"message": "err"}, "string log"],
        similar_incidents=None,
        service_name="payments-api",  # ensure adapter tolerates extra kwarg
    )

    assert out == "summarized"
    mock_summarize.assert_awaited_once()


@pytest.mark.anyio
async def test_stub_fallback_when_ai_service_url_empty(monkeypatch):
    # Ensure client module is reloaded with AI_SERVICE_URL unset.
    monkeypatch.delenv("AI_SERVICE_URL", raising=False)
    monkeypatch.delenv("AI_SERVICE_SECRET", raising=False)

    import src.ai.client as client_mod

    importlib.reload(client_mod)

    # Stub path should be active
    assert client_mod.ai_client.enabled is False

    verdict = await client_mod.ai_client.generate_verdict(
        alert_data={"title": "Test"},
        deploys=[],
        log_summary="",
        metrics=None,
        similar_incidents=None,
    )
    assert "Configure AI_SERVICE_URL" in verdict["verdict"]

    summary = await client_mod.ai_client.summarize_logs(logs=[{"level": "error"}])
    assert "Configure AI_SERVICE_URL" in summary["summary"]
