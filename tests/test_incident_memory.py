"""Unit tests for Incident Memory Phase 1 core functionality."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.memory.capture import IncidentCapture
from src.memory.config import IncidentMemoryConfig
from src.memory.models import IncidentRecallResult, IncidentRecord
from src.memory.recall import IncidentRecall, RecallQuery
from src.memory.store import IncidentMemoryStore


@pytest.fixture
def memory_config() -> IncidentMemoryConfig:
    return IncidentMemoryConfig(
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        embedding_dimensions=4,
    )


@pytest.fixture
def sample_record() -> IncidentRecord:
    return IncidentRecord(
        id="inc-123",
        title="Auth service latency spike",
        created_at=datetime(2026, 2, 10, 10, 0, 0),
        resolved_at=datetime(2026, 2, 10, 10, 25, 0),
        duration_minutes=25,
        severity="high",
        services_affected=["auth-service"],
        root_cause_category="deploy",
        root_cause_summary="Regression in JWT validation",
        error_signatures=["jwt_timeout"],
        metric_anomalies=["p99_latency_spike"],
        deploy_involved=True,
        deploy_sha="abc123def",
        resolution_steps=["rollback deployment", "clear cache"],
        resolution_summary="Rolled back and latency normalized",
        time_to_diagnose_minutes=10,
        time_to_fix_minutes=15,
        was_rollback=True,
        runbook_used="auth-latency-runbook",
        what_helped="deploy timeline",
        what_was_missing="better canary alerting",
        tags=["auth", "latency", "rollback"],
        embedding=[0.1, 0.2, 0.3, 0.4],
    )


def test_incident_record_model_defaults():
    record = IncidentRecord(
        id="inc-defaults",
        title="test",
        created_at=datetime(2026, 2, 10, 10, 0, 0),
    )

    assert record.services_affected == []
    assert record.error_signatures == []
    assert record.metric_anomalies == []
    assert record.tags == []
    assert record.embedding == []
    assert record.deploy_involved is False


@pytest.mark.asyncio
async def test_store_crud_and_count(memory_config, sample_record):
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="DELETE 1")
    pool.fetchval = AsyncMock(return_value=3)
    pool.fetchrow = AsyncMock(
        return_value={
            **sample_record.model_dump(),
            "embedding": "[0.1,0.2,0.3,0.4]",
        }
    )
    pool.fetch = AsyncMock(
        return_value=[
            {
                **sample_record.model_dump(),
                "embedding": "[0.1,0.2,0.3,0.4]",
            }
        ]
    )

    store = IncidentMemoryStore(
        database_url=memory_config.database_url,
        config=memory_config,
        pool=pool,
    )

    stored = await store.store(sample_record)
    fetched = await store.get(sample_record.id)
    recent = await store.list_recent(limit=1)
    deleted = await store.delete(sample_record.id)
    total = await store.count()

    assert stored.id == sample_record.id
    assert fetched is not None
    assert fetched.title == sample_record.title
    assert len(recent) == 1
    assert deleted is True
    assert total == 3
    assert pool.execute.await_count == 2


@pytest.mark.asyncio
async def test_store_recall(memory_config, sample_record):
    pool = MagicMock()
    pool.fetch = AsyncMock(
        return_value=[
            {
                **sample_record.model_dump(),
                "embedding": "[0.1,0.2,0.3,0.4]",
                "vector_similarity": 0.91,
                "temporal_decay": 0.85,
                "score": 0.88,
            }
        ]
    )

    store = IncidentMemoryStore(
        database_url=memory_config.database_url,
        config=memory_config,
        pool=pool,
    )
    query = RecallQuery(
        narrative="Auth timeouts after deploy",
        services=["auth-service"],
        severity="high",
        limit=3,
        embedding=[0.1, 0.2, 0.3, 0.4],
    )

    matches = await store.recall(query)

    assert len(matches) == 1
    assert matches[0].record.id == sample_record.id
    assert matches[0].score == pytest.approx(0.88)
    assert matches[0].vector_similarity == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_capture_extracts_embeds_and_stores(memory_config):
    settings = Settings(
        anthropic_api_key="anthropic-test",
        openai_api_key="openai-test",
        ai_model="claude-3-haiku-20240307",
    )

    anthropic_client = MagicMock()
    anthropic_client.messages = MagicMock()
    anthropic_client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[
                MagicMock(
                    text='{"title":"Auth failure","created_at":"2026-02-10T10:00:00Z","severity":"high","services_affected":["auth-service"],"resolution_steps":["rollback"],"deploy_involved":true,"tags":["auth"]}'
                )
            ]
        )
    )

    store = MagicMock()
    store.store = AsyncMock()

    capture = IncidentCapture(
        settings=settings,
        store=store,
        config=memory_config,
        anthropic_client=anthropic_client,
    )
    capture._embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])

    raw_incident = {
        "incident_id": "inc-456",
        "title": "Auth service outage",
        "description": "Users unable to login",
    }

    result = await capture.capture(raw_incident)

    assert result.id == "inc-456"
    assert result.title == "Auth failure"
    assert result.services_affected == ["auth-service"]
    assert result.embedding == [0.1, 0.2, 0.3, 0.4]
    store.store.assert_awaited_once()


@pytest.mark.asyncio
async def test_recall_with_high_severity_reranks(memory_config):
    settings = Settings(
        anthropic_api_key="anthropic-test",
        openai_api_key="",
        ai_model="claude-3-haiku-20240307",
    )

    store = MagicMock()
    store.recall = AsyncMock(
        return_value=[
            IncidentRecallResult(
                record=IncidentRecord(
                    id="inc-a",
                    title="Older match",
                    created_at=datetime(2026, 2, 1, 10, 0, 0),
                    embedding=[0.0, 0.0, 0.0, 0.0],
                ),
                score=0.80,
                vector_similarity=0.80,
                temporal_decay=1.0,
            ),
            IncidentRecallResult(
                record=IncidentRecord(
                    id="inc-b",
                    title="Best practical match",
                    created_at=datetime(2026, 2, 2, 10, 0, 0),
                    embedding=[0.0, 0.0, 0.0, 0.0],
                ),
                score=0.75,
                vector_similarity=0.75,
                temporal_decay=1.0,
            ),
        ]
    )

    anthropic_client = MagicMock()
    anthropic_client.messages = MagicMock()
    anthropic_client.messages.create = AsyncMock(
        return_value=MagicMock(
            content=[MagicMock(text='{"ranked_ids":["inc-b","inc-a"]}')]
        )
    )

    recall = IncidentRecall(
        settings=settings,
        store=store,
        config=memory_config,
        anthropic_client=anthropic_client,
    )

    query = RecallQuery(
        narrative="Auth latency spike after deployment",
        services=["auth-service"],
        severity="critical",
    )

    results = await recall.recall(query)

    assert [item.record.id for item in results] == ["inc-b", "inc-a"]
    assert query.embedding == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_recall_low_severity_skips_rerank(memory_config):
    settings = Settings(anthropic_api_key="anthropic-test", openai_api_key="")

    store = MagicMock()
    store.recall = AsyncMock(return_value=[])

    anthropic_client = MagicMock()
    anthropic_client.messages = MagicMock()
    anthropic_client.messages.create = AsyncMock()

    recall = IncidentRecall(
        settings=settings,
        store=store,
        config=memory_config,
        anthropic_client=anthropic_client,
    )

    query = RecallQuery(narrative="Minor alert", severity="low")
    await recall.recall(query)

    anthropic_client.messages.create.assert_not_called()
