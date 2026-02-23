"""Tests for feedback-driven learning in incident memory recall."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.memory.feedback import FeedbackStore, ResolutionFeedback
from src.memory.models import IncidentRecallResult, IncidentRecord
from src.memory.recall import IncidentRecall, RecallQuery
from src.memory.scoring import apply_feedback_weight


def test_helpful_feedback_boosts_recall_score():
    score = apply_feedback_weight(
        score=1.0,
        feedback_summary={
            "helpful": 2,
            "not_helpful": 0,
            "partial": 0,
            "net_score": 1.0,
        },
    )

    assert score == pytest.approx(1.2)


def test_not_helpful_feedback_penalizes_recall_score():
    score = apply_feedback_weight(
        score=1.0,
        feedback_summary={
            "helpful": 0,
            "not_helpful": 2,
            "partial": 0,
            "net_score": -1.0,
        },
    )

    assert score == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_feedback_summary_aggregation(tmp_path):
    store = FeedbackStore(database_path=str(tmp_path / "feedback.db"))

    await store.submit(
        ResolutionFeedback(
            incident_id="INC-1",
            recalled_incident_id="INC-100",
            feedback="helpful",
        )
    )
    await store.submit(
        ResolutionFeedback(
            incident_id="INC-2",
            recalled_incident_id="INC-100",
            feedback="not_helpful",
        )
    )
    await store.submit(
        ResolutionFeedback(
            incident_id="INC-3",
            recalled_incident_id="INC-100",
            feedback="partial",
        )
    )

    summary = await store.get_feedback_summary("INC-100")

    assert summary["helpful"] == 1
    assert summary["not_helpful"] == 1
    assert summary["partial"] == 1
    assert summary["net_score"] == pytest.approx(0.0833)


@pytest.mark.asyncio
async def test_recall_ordering_changes_based_on_feedback(tmp_path):
    settings = Settings(openai_api_key="")
    feedback_store = FeedbackStore(database_path=str(tmp_path / "feedback_recall.db"))

    await feedback_store.submit(
        ResolutionFeedback(
            incident_id="INC-10",
            recalled_incident_id="inc-a",
            feedback="not_helpful",
        )
    )
    await feedback_store.submit(
        ResolutionFeedback(
            incident_id="INC-11",
            recalled_incident_id="inc-b",
            feedback="helpful",
        )
    )

    created_at = datetime(2026, 2, 22, 10, 0, 0)
    store = MagicMock()
    store.recall = AsyncMock(
        return_value=[
            IncidentRecallResult(
                record=IncidentRecord(
                    id="inc-a",
                    title="Candidate A",
                    created_at=created_at,
                    embedding=[0.0, 0.0, 0.0, 0.0],
                ),
                score=0.80,
                vector_similarity=0.80,
                temporal_decay=1.0,
            ),
            IncidentRecallResult(
                record=IncidentRecord(
                    id="inc-b",
                    title="Candidate B",
                    created_at=created_at,
                    embedding=[0.0, 0.0, 0.0, 0.0],
                ),
                score=0.78,
                vector_similarity=0.78,
                temporal_decay=1.0,
            ),
        ]
    )

    recall = IncidentRecall(
        settings=settings,
        store=store,
        feedback_store=feedback_store,
    )
    recall._embed_text = AsyncMock(return_value=[0.0] * 1536)

    results = await recall.recall(RecallQuery(narrative="payment API latency spike"))

    assert [item.record.id for item in results] == ["inc-b", "inc-a"]
    assert results[0].score > results[1].score
