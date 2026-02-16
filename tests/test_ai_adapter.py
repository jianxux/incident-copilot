"""Tests for src.ai.adapter (AI service boundary adapter layer)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from src.ai import adapter


@pytest.mark.asyncio
async def test_verdict_engine_accepts_orchestrator_kwargs(monkeypatch):
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


@pytest.mark.asyncio
async def test_verdict_engine_accepts_direct_args(monkeypatch):
    engine = adapter.VerdictEngine(settings=None)

    mock_generate = AsyncMock(return_value={"verdict": "ok"})
    monkeypatch.setattr(adapter.ai_client, "generate_verdict", mock_generate)

    await engine.generate_verdict(
        alert_data={"title": "T"},
        deploys=[{"sha": "1"}],
        log_summary="log summary",
        metrics={"m": 1},
        similar_incidents=[],
    )

    mock_generate.assert_awaited_once_with(
        alert_data={"title": "T"},
        deploys=[{"sha": "1"}],
        log_summary="log summary",
        metrics={"m": 1},
        similar_incidents=[],
    )


@pytest.mark.asyncio
async def test_log_summarizer_delegates_to_ai_client(monkeypatch):
    summarizer = adapter.LogSummarizer(settings=None)

    mock_summarize = AsyncMock(return_value={"summary": "summarized"})
    monkeypatch.setattr(adapter.ai_client, "summarize_logs", mock_summarize)

    out = await summarizer.summarize([
        {"message": "err"},
        "string log",
    ])

    assert out == "summarized"
    mock_summarize.assert_awaited_once()

    called_logs, called_similar = mock_summarize.await_args.args
    assert called_logs[0]["message"] == "err"
    assert called_logs[1]["message"] == "string log"
    assert called_similar is None


@pytest.mark.asyncio
async def test_ai_copilot_chat_delegates_and_appends_to_session(monkeypatch):
    copilot = adapter.AICopilot(settings=None)

    mock_chat = AsyncMock(return_value={"response": "hello back"})
    monkeypatch.setattr(adapter.ai_client, "chat", mock_chat)

    msg = await copilot.chat(
        incident_id="INC-123",
        message="hello",
        context={"k": "v"},
    )

    assert msg.content == "hello back"
    session = await copilot.get_or_create_session("INC-123")
    assert len(session.messages) == 1
    assert session.messages[0].content == "hello back"

    mock_chat.assert_awaited_once_with(
        session_id="INC-123", message="hello", context={"k": "v"}
    )


@pytest.mark.asyncio
async def test_adapter_surfaces_ai_service_errors(monkeypatch):
    engine = adapter.VerdictEngine(settings=None)

    async def _boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(adapter.ai_client, "generate_verdict", _boom)

    with pytest.raises(httpx.ConnectError):
        await engine.generate_verdict(alert_data={"title": "T"})
