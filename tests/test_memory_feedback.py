"""Tests for Incident Memory Phase 3 feedback and scoring."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.memory_feedback import router as feedback_router
from src.api.memory_stats import router as stats_router
from src.memory.feedback import FeedbackStore, ResolutionFeedback
from src.memory.scoring import apply_temporal_decay


@pytest.mark.asyncio
async def test_feedback_model_validation_and_store(tmp_path):
    store = FeedbackStore(database_path=str(tmp_path / "feedback.db"))

    item = ResolutionFeedback(
        incident_id="INC-1",
        recalled_incident_id="INC-100",
        feedback="helpful",
        notes="Matched root cause",
    )
    saved = await store.submit(item)
    assert saved.feedback == "helpful"

    rows = await store.list_for_incident("INC-1")
    assert len(rows) == 1
    assert rows[0].recalled_incident_id == "INC-100"

    with pytest.raises(ValidationError):
        ResolutionFeedback(
            incident_id="INC-1",
            recalled_incident_id="INC-100",
            feedback="bad-value",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_similarity_weight_adjustment(tmp_path):
    store = FeedbackStore(database_path=str(tmp_path / "feedback.db"))
    await store.submit(
        ResolutionFeedback(
            incident_id="INC-2",
            recalled_incident_id="INC-200",
            feedback="helpful",
        )
    )
    await store.submit(
        ResolutionFeedback(
            incident_id="INC-2",
            recalled_incident_id="INC-200",
            feedback="partial",
        )
    )
    await store.submit(
        ResolutionFeedback(
            incident_id="INC-2",
            recalled_incident_id="INC-200",
            feedback="not_helpful",
        )
    )

    adjustment = await store.similarity_weight_adjustment("INC-2", "INC-200")
    assert adjustment == pytest.approx(0.02)


def test_apply_temporal_decay():
    same_day = apply_temporal_decay(0.8, 0)
    thirty_days = apply_temporal_decay(0.8, 30)
    sixty_days = apply_temporal_decay(0.8, 60)

    assert same_day == pytest.approx(0.8)
    assert thirty_days == pytest.approx(0.76)
    assert sixty_days < thirty_days


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(feedback_router)
    app.include_router(stats_router)

    feedback_store = FeedbackStore(database_path=str(tmp_path / "feedback_api.db"))
    monkeypatch.setattr(
        "src.api.memory_feedback._feedback_store", lambda: feedback_store
    )

    class _FakeMemoryStore:
        def __init__(self, *args, **kwargs):
            pass

        async def count(self):
            return 12

        async def disconnect(self):
            return None

    monkeypatch.setattr("src.api.memory_stats.IncidentMemoryStore", _FakeMemoryStore)
    monkeypatch.setattr(
        "src.api.memory_stats.get_feedback_store",
        lambda *_args, **_kwargs: feedback_store,
    )

    return TestClient(app), feedback_store


def test_feedback_api_submit_and_get(api_client):
    client, _ = api_client

    submit = client.post(
        "/api/memory/feedback",
        json={
            "incident_id": "INC-3",
            "recalled_incident_id": "INC-300",
            "feedback": "partial",
            "notes": "Some overlap but different service dependency",
        },
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "ok"

    fetched = client.get("/api/memory/feedback/INC-3")
    assert fetched.status_code == 200
    data = fetched.json()
    assert data["count"] == 1
    assert data["feedback"][0]["feedback"] == "partial"


def test_feedback_api_slack_interaction(api_client):
    client, _ = api_client

    payload = {
        "type": "block_actions",
        "actions": [
            {
                "action_id": "memory_feedback_helpful",
                "value": json.dumps(
                    {"incident_id": "INC-4", "recalled_incident_id": "INC-400"}
                ),
            }
        ],
    }

    response = client.post(
        "/api/memory/feedback/slack",
        data={"payload": json.dumps(payload)},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "stored"

    fetched = client.get("/api/memory/feedback/INC-4")
    assert fetched.status_code == 200
    assert fetched.json()["count"] == 1
    assert fetched.json()["feedback"][0]["feedback"] == "helpful"


def test_memory_stats_endpoint(api_client):
    client, feedback_store = api_client

    async def _seed():
        await feedback_store.submit(
            ResolutionFeedback(
                incident_id="INC-5",
                recalled_incident_id="INC-500",
                feedback="helpful",
            )
        )
        await feedback_store.submit(
            ResolutionFeedback(
                incident_id="INC-6",
                recalled_incident_id="INC-600",
                feedback="not_helpful",
            )
        )

    import asyncio

    asyncio.run(_seed())

    response = client.get("/api/memory/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_records"] == 12
    assert data["feedback_breakdown"]["helpful"] == 1
    assert data["feedback_breakdown"]["not_helpful"] == 1
    assert 0.0 <= data["recall_hit_rate"] <= 1.0
