from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import Settings
from src.memory.config import IncidentMemoryConfig
from src.memory.correlation import ServiceCorrelationEngine, _avg_gap_minutes
from src.memory.embeddings import (
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
    _fit_dimensions,
    build_embedding_provider,
)
from src.memory.health import MemoryHealthChecker
from src.memory.importer import IncidentMemoryImporter
from src.memory.models import GeneratedRunbook
from src.memory.runbooks import (
    AutoRunbookGenerator,
    _deterministic_runbook_id,
    _parse_json,
)


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TransactionCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def memory_config() -> IncidentMemoryConfig:
    return IncidentMemoryConfig(
        database_url="postgresql+asyncpg://test:test@localhost:5432/test",
        embedding_dimensions=4,
        correlation_min_cooccurrence=2,
        correlation_max_pairs=10,
        runbook_min_occurrences=2,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        openai_api_key="",
        anthropic_api_key="",
        service_repo_map={"payments": "repo/payments", "auth": "repo/auth"},
        oncall_schedule_map={"billing": "sched-billing"},
    )


def test_fit_dimensions_truncates():
    assert _fit_dimensions([1.0, 2.0, 3.0], 2) == [1.0, 2.0]


def test_fit_dimensions_pads():
    assert _fit_dimensions([1.0], 3) == [1.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_openai_embedding_provider_without_key_returns_zeros(memory_config):
    provider = OpenAIEmbeddingProvider(Settings(openai_api_key=""), memory_config)
    result = await provider.embed("incident narrative")
    assert result == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_openai_embedding_provider_success_and_close(memory_config):
    provider = OpenAIEmbeddingProvider(Settings(openai_api_key="secret"), memory_config)

    fake_response = MagicMock()
    fake_response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    fake_response.raise_for_status = MagicMock()

    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_response)
    fake_client.is_closed = False
    fake_client.aclose = AsyncMock()

    provider._get_client = AsyncMock(return_value=fake_client)

    result = await provider.embed("incident")
    assert result == [0.1, 0.2, 0.3, 0.0]

    provider._client = fake_client
    await provider.close()
    fake_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_embedding_provider_embed_with_model(memory_config):
    provider = LocalEmbeddingProvider(memory_config)

    class _Vector:
        def tolist(self):
            return [0.5, 0.6]

    class _Model:
        def encode(self, *_args, **_kwargs):
            return _Vector()

    provider._get_model = AsyncMock(return_value=_Model())
    result = await provider.embed("text")
    assert result == [0.5, 0.6, 0.0, 0.0]


@pytest.mark.asyncio
async def test_local_embedding_provider_no_model_returns_zeros(memory_config):
    provider = LocalEmbeddingProvider(memory_config)
    provider._get_model = AsyncMock(return_value=None)
    result = await provider.embed("text")
    assert result == [0.0, 0.0, 0.0, 0.0]


def test_build_embedding_provider_selects_type(memory_config):
    local = build_embedding_provider(
        Settings(openai_api_key="secret"),
        memory_config.model_copy(update={"embedding_provider": "local"}),
    )
    remote = build_embedding_provider(
        Settings(openai_api_key="secret"),
        memory_config.model_copy(update={"embedding_provider": "openai"}),
    )
    assert isinstance(local, LocalEmbeddingProvider)
    assert isinstance(remote, OpenAIEmbeddingProvider)


@pytest.mark.asyncio
async def test_correlation_rebuild_inserts_pairs(memory_config):
    rows = [
        {
            "id": "1",
            "created_at": datetime(2026, 2, 1, 10, 0, tzinfo=UTC),
            "services_affected": ["payments", "auth"],
        },
        {
            "id": "2",
            "created_at": datetime(2026, 2, 1, 10, 20, tzinfo=UTC),
            "services_affected": ["payments", "auth", "billing"],
        },
    ]

    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_TransactionCtx())
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()

    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    pool.acquire = MagicMock(return_value=_AcquireCtx(conn))

    store = MagicMock()
    store._ensure_pool = AsyncMock(return_value=pool)

    engine = ServiceCorrelationEngine(store=store, config=memory_config)
    count = await engine.rebuild()

    assert count == 1
    conn.execute.assert_awaited_once()
    conn.executemany.assert_awaited_once()


@pytest.mark.asyncio
async def test_correlation_rebuild_filters_low_frequency(memory_config):
    config = memory_config.model_copy(update={"correlation_min_cooccurrence": 3})
    rows = [
        {
            "id": "1",
            "created_at": datetime(2026, 2, 1, 10, 0, tzinfo=UTC),
            "services_affected": ["payments", "auth"],
        },
        {
            "id": "2",
            "created_at": datetime(2026, 2, 1, 10, 20, tzinfo=UTC),
            "services_affected": ["payments", "billing"],
        },
    ]

    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_TransactionCtx())
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()

    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    pool.acquire = MagicMock(return_value=_AcquireCtx(conn))

    store = MagicMock()
    store._ensure_pool = AsyncMock(return_value=pool)

    engine = ServiceCorrelationEngine(store=store, config=config)
    count = await engine.rebuild()

    assert count == 0
    conn.execute.assert_awaited_once()
    conn.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_correlation_get_for_service(memory_config):
    pool = MagicMock()
    pool.fetch = AsyncMock(
        return_value=[
            {
                "service_a": "payments",
                "service_b": "auth",
                "co_occurrence_count": 5,
                "avg_time_gap_minutes": 12.5,
                "confidence": 0.8,
            }
        ]
    )
    store = MagicMock()
    store._ensure_pool = AsyncMock(return_value=pool)

    engine = ServiceCorrelationEngine(store=store, config=memory_config)
    result = await engine.get_for_service("payments", limit=3)

    assert len(result) == 1
    assert result[0].service_b == "auth"
    assert result[0].confidence == pytest.approx(0.8)


def test_avg_gap_minutes():
    now = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)
    value = _avg_gap_minutes(
        [now, now + timedelta(minutes=10), now + timedelta(minutes=25)]
    )
    assert value == pytest.approx(12.5)


@pytest.mark.asyncio
async def test_runbooks_collect_groups(memory_config, settings):
    rows = [
        {
            "id": "i-1",
            "root_cause_category": "deploy",
            "services_affected": ["payments"],
            "resolution_steps": ["rollback"],
            "resolution_summary": "done",
        },
        {
            "id": "i-2",
            "root_cause_category": "deploy",
            "services_affected": ["payments"],
            "resolution_steps": ["rollback", "clear cache"],
            "resolution_summary": "done",
        },
    ]

    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    store = MagicMock()
    store._ensure_pool = AsyncMock(return_value=pool)

    generator = AutoRunbookGenerator(
        settings=settings, store=store, config=memory_config
    )
    groups = await generator._collect_groups()

    assert len(groups) == 1
    assert groups[0]["root_cause_category"] == "deploy"


@pytest.mark.asyncio
async def test_runbooks_generate_for_group_fallback(memory_config, settings):
    store = MagicMock()
    generator = AutoRunbookGenerator(
        settings=settings, store=store, config=memory_config
    )

    group = {
        "root_cause_category": "database",
        "services_affected": ["payments"],
        "incidents": [
            {"id": "i-1", "steps": ["restart db", "flush pool"]},
            {"id": "i-2", "steps": ["restart db"]},
        ],
    }

    runbook = await generator._generate_for_group(group)

    assert runbook is not None
    assert "restart db" in runbook.steps
    assert runbook.root_cause_category == "database"
    assert runbook.id == "dd0adb9ddbd1df1c"


def test_deterministic_runbook_id_is_stable_and_16_chars():
    value = _deterministic_runbook_id(
        category="database",
        services=["payments"],
        source_ids=["i-2", "i-1"],
    )
    assert value == "dd0adb9ddbd1df1c"
    assert len(value) == 16


@pytest.mark.asyncio
async def test_runbooks_generate_for_group_uses_synthesized(memory_config, settings):
    store = MagicMock()
    generator = AutoRunbookGenerator(
        settings=settings, store=store, config=memory_config
    )
    generator._synthesize_with_claude = AsyncMock(
        return_value={
            "title": "DB Recovery",
            "trigger_conditions": ["p95 > 1s"],
            "steps": ["Scale DB", "Flush cache"],
        }
    )

    group = {
        "root_cause_category": "database",
        "services_affected": ["payments"],
        "incidents": [{"id": "i-1", "steps": ["restart db"]}],
    }

    runbook = await generator._generate_for_group(group)

    assert runbook is not None
    assert runbook.title == "DB Recovery"
    assert runbook.steps == ["Scale DB", "Flush cache"]


@pytest.mark.asyncio
async def test_runbooks_replace_runbooks(memory_config, settings):
    runbook = GeneratedRunbook(
        id="rb-1",
        title="title",
        trigger_conditions=["cond"],
        steps=["step"],
        source_incident_ids=["i-1"],
        confidence=0.7,
        root_cause_category="deploy",
        services_affected=["payments"],
        last_updated=datetime.now(UTC),
    )

    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_TransactionCtx())
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCtx(conn))

    store = MagicMock()
    store._ensure_pool = AsyncMock(return_value=pool)

    generator = AutoRunbookGenerator(
        settings=settings, store=store, config=memory_config
    )
    await generator._replace_runbooks([runbook])

    conn.execute.assert_awaited_once()
    conn.executemany.assert_awaited_once()


def test_runbooks_parse_json_with_code_fence():
    parsed = _parse_json('```json\n{"title":"A"}\n```')
    assert parsed["title"] == "A"


@pytest.mark.asyncio
async def test_health_check_generates_alerts(memory_config, settings):
    pool = MagicMock()
    pool.fetchval = AsyncMock(side_effect=[0, datetime.utcnow() - timedelta(days=30)])

    checker = MemoryHealthChecker(settings=settings, config=memory_config, pool=pool)
    checker._recall_hit_rate = AsyncMock(return_value=0.1)
    checker._missing_services = AsyncMock(return_value=["auth"])

    report = await checker.check(min_recall_hit_rate=0.35, stale_after_days=14)

    assert report.status == "critical"
    assert report.total_records == 0
    assert len(report.alerts) >= 3


@pytest.mark.asyncio
async def test_health_recall_hit_rate_handles_missing_feedback_table(
    memory_config, settings
):
    pool = MagicMock()
    pool.fetchval = AsyncMock(side_effect=Exception("relation does not exist"))

    checker = MemoryHealthChecker(settings=settings, config=memory_config, pool=pool)
    rate = await checker._recall_hit_rate(pool)

    assert rate is None


@pytest.mark.asyncio
async def test_health_missing_services_diff(memory_config, settings):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[{"service": "payments"}])

    checker = MemoryHealthChecker(settings=settings, config=memory_config, pool=pool)
    missing = await checker._missing_services(pool)

    assert missing == ["auth", "billing"]


def test_importer_parse_json_and_csv():
    importer = IncidentMemoryImporter(capture=MagicMock())

    json_rows = importer._parse_incidents(
        filename="incidents.json",
        content=b'[{"id":"1"},{"id":"2"}]',
        format_hint=None,
    )
    csv_rows = importer._parse_incidents(
        filename="incidents.csv",
        content=b"id,title\n1,one\n2,two\n",
        format_hint=None,
    )

    assert [row["id"] for row in json_rows] == ["1", "2"]
    assert [row["id"] for row in csv_rows] == ["1", "2"]


@pytest.mark.asyncio
async def test_importer_import_content_collects_failures():
    capture = MagicMock()
    capture.capture = AsyncMock(side_effect=[MagicMock(id="ok-1"), Exception("boom")])

    importer = IncidentMemoryImporter(capture=capture)
    result = await importer.import_content(
        filename="incidents.json",
        content=b'[{"id":"ok-1"},{"id":"bad-2"}]',
        format_hint="json",
    )

    assert result.imported_count == 1
    assert result.failed_count == 1
    assert result.failed_items[0]["incident_id"] == "bad-2"
