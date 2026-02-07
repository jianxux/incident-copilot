"""Tests for the alert correlation engine."""

from datetime import datetime

import pytest

from src.config import Settings
from src.correlation import (
    AlertGroup,
    AlertGroupStatus,
    CorrelationEngine,
    CorrelationRule,
    CorrelationStrategy,
    IncomingAlert,
)
from src.correlation.rules import (
    RuleManager,
    fuzzy_similarity,
    normalize_title_for_matching,
)
from src.correlation.store import CorrelationStore
from src.models import PagerDutyIncident, Severity


@pytest.fixture
def settings():
    return Settings(
        redis_url="", correlation_enabled=True, correlation_default_rules=False
    )


@pytest.fixture
def store():
    return CorrelationStore(redis_url=None)


@pytest.fixture
async def initialized_store(store):
    await store.initialize()
    return store


@pytest.fixture
def sample_alert():
    return IncomingAlert(
        alert_id="alert-001",
        source="pagerduty",
        title="High CPU usage",
        service="payments-api",
        severity="high",
        tags=["service:payments-api", "env:prod"],
        triggered_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_rule():
    return CorrelationRule(
        rule_id="rule-001",
        name="Test Rule",
        strategy=CorrelationStrategy.TIME_BASED,
        priority=10,
        time_window_seconds=300,
        suppress_duplicates=True,
    )


class TestFuzzySimilarity:
    def test_identical_strings(self):
        assert fuzzy_similarity("hello world", "hello world") == pytest.approx(1.0)

    def test_similar_strings(self):
        assert (
            fuzzy_similarity(
                "Database connection timeout", "Database connection timed out"
            )
            > 0.7
        )

    def test_different_strings(self):
        assert fuzzy_similarity("CPU usage high", "Memory leak detected") < 0.5

    def test_empty_strings(self):
        assert fuzzy_similarity("", "hello") == 0.0


class TestNormalizeTitleForMatching:
    def test_removes_timestamps(self):
        assert "2024-01-15" not in normalize_title_for_matching(
            "Error at 2024-01-15T10:30:00 in service"
        )

    def test_removes_uuids(self):
        assert (
            "abc12345-1234-5678-abcd-ef1234567890"
            not in normalize_title_for_matching(
                "Request abc12345-1234-5678-abcd-ef1234567890 failed"
            )
        )

    def test_removes_ip_addresses(self):
        assert "192.168.1.100" not in normalize_title_for_matching(
            "Connection from 192.168.1.100 refused"
        )


class TestCorrelationStore:
    @pytest.mark.asyncio
    async def test_store_and_retrieve_group(self, initialized_store):
        group = AlertGroup(
            group_id="grp-001",
            strategy=CorrelationStrategy.TIME_BASED,
            fingerprint="fp123",
        )
        await initialized_store.store_group(group)
        assert (await initialized_store.get_group("grp-001")).group_id == "grp-001"

    @pytest.mark.asyncio
    async def test_get_nonexistent_group(self, initialized_store):
        assert await initialized_store.get_group("nonexistent") is None

    @pytest.mark.asyncio
    async def test_fingerprint_mapping(self, initialized_store):
        group = AlertGroup(
            group_id="grp-002",
            strategy=CorrelationStrategy.TIME_BASED,
            fingerprint="fp456",
        )
        await initialized_store.store_group(group)
        await initialized_store.store_fingerprint_mapping("fp456", "grp-002")
        assert (
            await initialized_store.get_group_by_fingerprint("fp456")
        ).group_id == "grp-002"

    @pytest.mark.asyncio
    async def test_store_and_retrieve_rule(self, initialized_store):
        rule = CorrelationRule(
            rule_id="rule-001",
            name="Test Rule",
            strategy=CorrelationStrategy.TIME_BASED,
        )
        await initialized_store.store_rule(rule)
        assert (await initialized_store.get_rule("rule-001")).name == "Test Rule"


class TestRuleManager:
    @pytest.mark.asyncio
    async def test_generate_fingerprint(
        self, initialized_store, sample_alert, sample_rule
    ):
        manager = RuleManager(initialized_store)
        assert manager.generate_fingerprint(
            sample_alert, sample_rule
        ) == manager.generate_fingerprint(sample_alert, sample_rule)

    @pytest.mark.asyncio
    async def test_matches_rule_service_filter(self, initialized_store, sample_alert):
        manager = RuleManager(initialized_store)
        assert (
            manager.matches_rule(
                sample_alert,
                CorrelationRule(
                    rule_id="r1",
                    name="Specific",
                    strategy=CorrelationStrategy.TIME_BASED,
                    services=["payments-api"],
                ),
            )
            is True
        )
        assert (
            manager.matches_rule(
                sample_alert,
                CorrelationRule(
                    rule_id="r2",
                    name="Other",
                    strategy=CorrelationStrategy.TIME_BASED,
                    services=["auth-api"],
                ),
            )
            is False
        )


class TestCorrelationEngine:
    @pytest.mark.asyncio
    async def test_normalize_pagerduty(self, settings):
        engine = CorrelationEngine(settings)
        alert = engine.normalize_pagerduty(
            PagerDutyIncident(
                incident_id="inc-001",
                incident_number=12345,
                title="DB timeout",
                service_name="db-service",
                triggered_at=datetime.utcnow(),
                severity=Severity.HIGH,
            )
        )
        assert alert.alert_id == "inc-001" and alert.source == "pagerduty"

    @pytest.mark.asyncio
    async def test_correlate_new_alert_creates_group(self, settings):
        engine = CorrelationEngine(settings)
        await engine.initialize()
        await engine.create_rule(
            CorrelationRule(
                rule_id="test-rule",
                name="Test",
                strategy=CorrelationStrategy.TIME_BASED,
            )
        )
        result = await engine.correlate(
            IncomingAlert(
                alert_id="alert-new",
                source="test",
                title="Test",
                service="test-service",
            )
        )
        assert result.correlated and result.new_group

    @pytest.mark.asyncio
    async def test_correlate_similar_alerts_same_group(self, settings):
        engine = CorrelationEngine(settings)
        await engine.initialize()
        await engine.create_rule(
            CorrelationRule(
                rule_id="test-rule",
                name="Test",
                strategy=CorrelationStrategy.TIME_BASED,
            )
        )
        result1 = await engine.correlate(
            IncomingAlert(
                alert_id="alert-1", source="test", title="CPU high", service="web"
            )
        )
        result2 = await engine.correlate(
            IncomingAlert(
                alert_id="alert-2", source="test", title="CPU high", service="web"
            )
        )
        assert result1.group.group_id == result2.group.group_id

    @pytest.mark.asyncio
    async def test_suppression(self, settings):
        engine = CorrelationEngine(settings)
        await engine.initialize()
        await engine.create_rule(
            CorrelationRule(
                rule_id="test-rule",
                name="Test",
                strategy=CorrelationStrategy.TIME_BASED,
                suppress_duplicates=True,
                max_alerts_before_notify=1,
            )
        )
        result1 = await engine.correlate(
            IncomingAlert(
                alert_id="alert-1", source="test", title="Error", service="svc"
            )
        )
        result2 = await engine.correlate(
            IncomingAlert(
                alert_id="alert-2", source="test", title="Error", service="svc"
            )
        )
        assert result1.should_notify and not result2.should_notify

    @pytest.mark.asyncio
    async def test_no_rule_matches(self, settings):
        store = CorrelationStore(redis_url=None)
        await store.initialize()
        engine = CorrelationEngine(settings, store=store)
        engine._initialized = True
        result = await engine.correlate(
            IncomingAlert(
                alert_id="alert-1", source="test", title="Orphan", service="orphan"
            )
        )
        assert not result.correlated and result.should_notify

    @pytest.mark.asyncio
    async def test_close_group(self, settings):
        engine = CorrelationEngine(settings)
        await engine.initialize()
        await engine.create_rule(
            CorrelationRule(
                rule_id="test-rule",
                name="Test",
                strategy=CorrelationStrategy.TIME_BASED,
            )
        )
        result = await engine.correlate(
            IncomingAlert(
                alert_id="alert-1", source="test", title="Test", service="svc"
            )
        )
        assert await engine.close_group(result.group.group_id)
        assert (
            await engine.get_group(result.group.group_id)
        ).status == AlertGroupStatus.CLOSED


class TestAlertGroup:
    def test_add_alert(self, sample_alert):
        group = AlertGroup(
            group_id="grp-001",
            strategy=CorrelationStrategy.TIME_BASED,
            fingerprint="fp123",
        )
        group.add_alert(sample_alert)
        assert group.alert_count == 1 and sample_alert.alert_id in group.alert_ids

    def test_update_summary(self, sample_alert):
        group = AlertGroup(
            group_id="grp-001",
            strategy=CorrelationStrategy.TIME_BASED,
            fingerprint="fp123",
        )
        group.add_alert(sample_alert)
        group.suppressed_count = 5
        group.update_summary()
        assert (
            "1 alert" in group.summary and "5 notifications suppressed" in group.summary
        )


class TestCorrelationIntegration:
    @pytest.mark.asyncio
    async def test_high_volume_alerts(self, settings):
        engine = CorrelationEngine(settings)
        await engine.initialize()
        await engine.create_rule(
            CorrelationRule(
                rule_id="v-rule", name="Volume", strategy=CorrelationStrategy.TIME_BASED
            )
        )
        group_id = None
        for i in range(50):
            result = await engine.correlate(
                IncomingAlert(
                    alert_id=f"alert-{i}",
                    source="test",
                    title="High CPU",
                    service="api",
                )
            )
            if i == 0:
                group_id = result.group.group_id
                assert result.new_group
            else:
                assert not result.new_group
        assert (await engine.get_group(group_id)).alert_count == 50

    @pytest.mark.asyncio
    async def test_multiple_services_separate_groups(self, settings):
        engine = CorrelationEngine(settings)
        await engine.initialize()
        await engine.create_rule(
            CorrelationRule(
                rule_id="m-rule", name="Multi", strategy=CorrelationStrategy.TIME_BASED
            )
        )
        group_ids = [
            (
                await engine.correlate(
                    IncomingAlert(
                        alert_id=f"alert-{s}", source="test", title="Error", service=s
                    )
                )
            ).group.group_id
            for s in ["auth", "payments", "shipping"]
        ]
        assert len(set(group_ids)) == 3
