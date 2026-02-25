"""Regression tests for datetime.utcnow() -> datetime.now(UTC) migration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.analytics.store import AnalyticsStore, _to_utc_aware
from src.analytics.tracker import AnalyticsTracker
from src.api import analytics as api_analytics
from src.audit.models import AuditEvent, AuditLogQuery, EventCategory, EventType
from src.audit.store import AuditStore
from src.config import Settings
from src.correlation import CorrelationEngine
from src.correlation.models import (
    AlertGroup,
    CorrelationRule,
    CorrelationStrategy,
    IncomingAlert,
)
from src.correlation.store import CorrelationStore
from src.ratelimit.limiter import RateLimiter
from src.ratelimit.models import RateLimitConfig, RateLimitOverride, RateLimitScope


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            datetime(2026, 1, 1, 0, 0, 0),
            datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        ),
        (
            datetime(1970, 1, 1, 0, 0, 0),
            datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC),
        ),
    ],
)
def test_to_utc_aware_naive_datetime_gets_utc_tzinfo(value: datetime, expected: datetime):
    assert _to_utc_aware(value) == expected


def test_to_utc_aware_utc_datetime_passes_through_unchanged_instant():
    value = datetime(2026, 2, 1, 12, 34, 56, tzinfo=UTC)
    result = _to_utc_aware(value)

    assert result == value
    assert result.tzinfo == UTC


def test_to_utc_aware_non_utc_timezone_converts_to_utc():
    eastern = ZoneInfo("America/New_York")
    local = datetime(2026, 1, 15, 7, 30, tzinfo=eastern)

    result = _to_utc_aware(local)

    assert result.tzinfo == UTC
    assert result == local.astimezone(UTC)


@pytest.mark.asyncio
async def test_analytics_store_get_metrics_for_period_handles_mixed_naive_and_aware_datetimes():
    store = AnalyticsStore()

    await store.record_event(
        incident_id="naive-incident",
        event_type="triggered",
        timestamp=datetime(2026, 1, 1, 0, 0, 0),
        service_name="svc",
        severity="high",
    )
    await store.record_event(
        incident_id="aware-incident",
        event_type="triggered",
        timestamp=datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC),
        service_name="svc",
        severity="high",
    )

    # Regression check: this mixed comparison previously raised TypeError.
    results = await store.get_metrics_for_period(
        start=datetime(2025, 12, 31, 23, 0, 0, tzinfo=UTC),
        end=datetime(2026, 1, 1, 2, 0, 0),
    )

    assert {m.incident_id for m in results} == {"naive-incident", "aware-incident"}


@pytest.mark.asyncio
async def test_tracker_get_stats_for_days_uses_datetime_now_with_utc(monkeypatch: pytest.MonkeyPatch):
    fixed_now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=UTC)

    class DateTimeSpy:
        calls: list[object] = []

        @classmethod
        def now(cls, tz=None):
            cls.calls.append(tz)
            return fixed_now

    import src.analytics.tracker as tracker_module

    monkeypatch.setattr(tracker_module, "datetime", DateTimeSpy)

    tracker = AnalyticsTracker(store=AsyncMock())
    tracker.calculate_mttr_stats = AsyncMock()

    await tracker.get_stats_for_days(7)

    assert DateTimeSpy.calls == [UTC]
    tracker.calculate_mttr_stats.assert_awaited_once()
    kwargs = tracker.calculate_mttr_stats.await_args.kwargs
    assert kwargs["end"] == fixed_now
    assert kwargs["end"].tzinfo == UTC
    assert kwargs["start"] == fixed_now - timedelta(days=7)


@pytest.mark.asyncio
async def test_tracker_compare_to_previous_uses_datetime_now_with_utc(monkeypatch: pytest.MonkeyPatch):
    fixed_now = datetime(2026, 2, 25, 13, 0, 0, tzinfo=UTC)

    class DateTimeSpy:
        calls: list[object] = []

        @classmethod
        def now(cls, tz=None):
            cls.calls.append(tz)
            return fixed_now

    import src.analytics.tracker as tracker_module

    monkeypatch.setattr(tracker_module, "datetime", DateTimeSpy)

    tracker = AnalyticsTracker(store=AsyncMock())
    tracker.compare_periods = AsyncMock()

    await tracker.compare_to_previous(3)

    assert DateTimeSpy.calls == [UTC]
    tracker.compare_periods.assert_awaited_once()
    kwargs = tracker.compare_periods.await_args.kwargs
    assert kwargs["current_end"] == fixed_now
    assert kwargs["current_start"] == fixed_now - timedelta(days=3)
    assert kwargs["previous_end"] == fixed_now - timedelta(days=3)
    assert kwargs["previous_start"] == fixed_now - timedelta(days=6)
    assert kwargs["current_end"].tzinfo == UTC


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fn_name", "tracker_method", "field_name"),
    [
        ("record_incident_triggered", "record_incident_triggered", "triggered_at"),
        (
            "record_incident_acknowledged",
            "record_incident_acknowledged",
            "acknowledged_at",
        ),
        ("record_incident_resolved", "record_incident_resolved", "resolved_at"),
        (
            "record_context_card_delivered",
            "record_context_card_delivered",
            "delivered_at",
        ),
    ],
)
async def test_api_record_endpoints_default_to_datetime_now_utc(
    monkeypatch: pytest.MonkeyPatch,
    fn_name: str,
    tracker_method: str,
    field_name: str,
):
    fixed_now = datetime(2026, 2, 25, 15, 0, 0, tzinfo=UTC)

    class DateTimeSpy:
        calls: list[object] = []

        @classmethod
        def now(cls, tz=None):
            cls.calls.append(tz)
            return fixed_now

    monkeypatch.setattr(api_analytics, "datetime", DateTimeSpy)

    mock_metrics = MagicMock()
    mock_metrics.model_dump.return_value = {"incident_id": "inc-1"}

    tracker_mock = AsyncMock()
    setattr(tracker_mock, tracker_method, AsyncMock(return_value=mock_metrics))
    monkeypatch.setattr(api_analytics, "tracker", tracker_mock)

    fn = getattr(api_analytics, fn_name)

    kwargs = {"incident_id": "inc-1"}
    if fn_name == "record_incident_triggered":
        kwargs.update({"service_name": "payments", "severity": "high"})

    response = await fn(**kwargs)

    assert DateTimeSpy.calls == [UTC]
    mocked = getattr(tracker_mock, tracker_method)
    mocked.assert_awaited_once()
    called_at = mocked.await_args.kwargs[field_name]
    assert called_at == fixed_now
    assert called_at.tzinfo == UTC
    assert response["status"] == "recorded"


@pytest.mark.asyncio
async def test_audit_store_query_events_handles_naive_and_aware_ranges_without_type_error():
    store = AuditStore()

    event = AuditEvent(
        event_type=EventType.LOGIN_SUCCESS,
        category=EventCategory.AUTHENTICATION,
        action="aware",
        tenant_id="tenant-1",
        timestamp=datetime(2026, 2, 25, 2, 0, 0, tzinfo=UTC),
    )
    await store.store_event(event)

    query = AuditLogQuery(
        tenant_id="tenant-1",
        start_date=datetime(2026, 2, 25, 0, 30, 0),  # naive query bound
        end_date=datetime(2026, 2, 25, 2, 30, 0),  # naive query bound
        limit=10,
    )

    events = await store.query_events(query)

    assert [e.action for e in events] == ["aware"]
    assert events[0].timestamp.tzinfo == UTC


@pytest.mark.asyncio
async def test_correlation_engine_group_times_are_timezone_aware_utc():
    settings = Settings(
        redis_url="",
        correlation_enabled=True,
        correlation_default_rules=False,
    )
    engine = CorrelationEngine(settings)
    await engine.initialize()

    rule = await engine.create_rule(
        CorrelationRule(
            rule_id="utc-rule",
            name="UTC Rule",
            strategy=CorrelationStrategy.TIME_BASED,
            time_window_seconds=300,
            suppress_duplicates=False,
        )
    )

    result = await engine.correlate(
        IncomingAlert(
            alert_id="alert-utc-1",
            source="test",
            title="CPU high",
            service="svc",
        )
    )

    assert rule is not None
    assert result.group is not None
    assert result.group.window_expires_at is not None
    assert result.group.window_expires_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_correlation_store_fingerprint_expiry_supports_naive_mapping_timestamp():
    store = CorrelationStore(redis_url=None)
    await store.initialize()

    group = AlertGroup(
        group_id="grp-utc-1",
        strategy=CorrelationStrategy.TIME_BASED,
        fingerprint="fp-utc-1",
    )
    await store.store_group(group)

    # Simulate legacy naive expiry in memory mapping.
    store._memory_store["correlation:fingerprint:fp-utc-1"] = {
        "group_id": "grp-utc-1",
        "expires_at": (
            datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
        ).isoformat(),
    }

    resolved = await store.get_group_by_fingerprint("fp-utc-1")

    assert resolved is not None
    assert resolved.group_id == "grp-utc-1"


@pytest.mark.asyncio
async def test_ratelimiter_check_returns_aware_reset_at_datetime():
    limiter = RateLimiter(redis_url=None)
    limiter._use_memory_fallback = True
    limiter._configs[RateLimitScope.IP] = RateLimitConfig(
        name="test",
        scope=RateLimitScope.IP,
        capacity=5,
        refill_rate=1.0,
    )

    result = await limiter.check(RateLimitScope.IP, "127.0.0.1")

    assert result.reset_at.tzinfo == UTC


def test_ratelimiter_override_expiry_accepts_naive_datetime_without_type_error():
    limiter = RateLimiter(redis_url=None)
    limiter._use_memory_fallback = True
    limiter._configs[RateLimitScope.TENANT] = RateLimitConfig(
        name="tenant",
        scope=RateLimitScope.TENANT,
        capacity=10,
        refill_rate=1.0,
    )

    override = RateLimitOverride(
        key="tenant-1",
        scope=RateLimitScope.TENANT,
        capacity=50,
        refill_rate=5.0,
        expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    limiter.set_override(override)

    config = limiter._get_config(RateLimitScope.TENANT, "tenant-1")

    assert config.capacity == 10
    assert "tenant:tenant-1" not in limiter._overrides


def test_datetime_now_utc_is_timezone_aware_and_utc():
    now = datetime.now(UTC)

    assert now.tzinfo is not None
    assert now.tzinfo == UTC
