"""Tests for verdict memory enrichment context."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.verdict import VerdictEngine
from src.config import Settings
from src.models import PastIncident


def _mock_llm_response(payload: dict) -> MagicMock:
    response = MagicMock()
    block = MagicMock()
    block.text = json.dumps(payload)
    response.content = [block]
    return response


@pytest.mark.asyncio
async def test_verdict_with_similar_incidents_includes_them_in_prompt():
    engine = VerdictEngine(Settings())
    engine.client = AsyncMock()
    engine.client.messages.create = AsyncMock(
        return_value=_mock_llm_response(
            {
                "most_likely_cause": "Likely repeated DB pool exhaustion",
                "confidence": "high",
                "evidence": "Pattern matched prior incidents",
                "recommended_action": "Increase pool and recycle workers",
            }
        )
    )

    similar = [
        PastIncident(
            incident_id="inc-101",
            title="Checkout API timeout spike",
            service="checkout-api",
            root_cause="DB pool exhaustion during traffic spike",
            resolution="Increased pool size and restarted workers",
            occurred_at=datetime(2026, 2, 1, 10, 0, 0),
            resolved_at=datetime(2026, 2, 1, 11, 30, 0),
            similarity_score=91.0,
        )
    ]

    await engine.generate_verdict(
        title="Checkout API errors",
        service_name="checkout-api",
        severity="high",
        triggered_at=datetime(2026, 2, 13, 10, 0, 0),
        similar_incidents=similar,
    )

    prompt = engine.client.messages.create.await_args.kwargs["messages"][0]["content"]
    assert "Here are similar past incidents and their resolutions:" in prompt
    assert "What happened: Checkout API timeout spike" in prompt
    assert "Root cause: DB pool exhaustion during traffic spike" in prompt
    assert "Resolution: Increased pool size and restarted workers" in prompt
    assert "Time to resolve: 1h 30m" in prompt


@pytest.mark.asyncio
async def test_verdict_without_similar_incidents_still_works():
    engine = VerdictEngine(Settings())
    engine.client = AsyncMock()
    engine.client.messages.create = AsyncMock(
        return_value=_mock_llm_response(
            {
                "most_likely_cause": "Unknown transient failure",
                "confidence": "low",
                "evidence": "Limited context",
                "recommended_action": "Investigate logs",
            }
        )
    )

    verdict = await engine.generate_verdict(
        title="Random failures",
        service_name="checkout-api",
        severity="medium",
        triggered_at=datetime(2026, 2, 13, 10, 0, 0),
    )

    prompt = engine.client.messages.create.await_args.kwargs["messages"][0]["content"]
    assert "Here are similar past incidents and their resolutions:" not in prompt
    assert verdict.most_likely_cause == "Unknown transient failure"


@pytest.mark.asyncio
async def test_similar_incident_context_appears_in_generated_verdict():
    engine = VerdictEngine(Settings())
    engine.client = AsyncMock()

    async def _fake_create(**kwargs):
        prompt = kwargs["messages"][0]["content"]
        has_memory_context = (
            "Here are similar past incidents and their resolutions:" in prompt
        )
        return _mock_llm_response(
            {
                "most_likely_cause": "Repeated deploy-related regression",
                "confidence": "medium",
                "evidence": f"Used past incident context: {has_memory_context}",
                "recommended_action": "Rollback and apply prior fix",
            }
        )

    engine.client.messages.create = AsyncMock(side_effect=_fake_create)

    verdict = await engine.generate_verdict(
        title="Checkout API latency spike",
        service_name="checkout-api",
        severity="high",
        triggered_at=datetime(2026, 2, 13, 10, 0, 0),
        similar_incidents=[
            {
                "title": "Checkout latency spike in Jan",
                "root_cause": "Bad retry policy after deploy",
                "resolution": "Rollback and fix retry configuration",
                "occurred_at": "2026-01-15T10:00:00Z",
                "resolved_at": "2026-01-15T10:45:00Z",
            }
        ],
    )

    assert verdict.evidence == "Used past incident context: True"
