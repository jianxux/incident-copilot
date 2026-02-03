"""Tests for the webhook plugin framework."""

from __future__ import annotations
from unittest.mock import AsyncMock, patch
import pytest
from src.plugins import (
    PayloadTransformer,
    PluginEvent,
    PluginRegistry,
    PluginStatus,
    PluginType,
    WebhookConfig,
    WebhookExecutor,
)
from src.plugins.models import (
    EnrichmentConfig,
    FilterCondition,
    FilterConfig,
    HmacConfig,
    PluginCreateRequest,
    PluginUpdateRequest,
    RetryConfig,
)
from src.plugins.registry import PluginExistsError, PluginNotFoundError


@pytest.fixture
def sample_context_card():
    return {
        "incident_id": "INC-12345",
        "title": "High error rate on payments-api",
        "severity": "high",
        "service_name": "payments-api",
        "owners": ["team"],
        "ai_summary": {"explanation": "Test"},
        "runbooks": [],
    }


@pytest.fixture
def webhook_plugin_request():
    return PluginCreateRequest(
        id="test-webhook",
        name="Test",
        type=PluginType.WEBHOOK,
        webhook_config=WebhookConfig(url="https://example.com"),
    )


@pytest.fixture
def registry():
    return PluginRegistry()


class TestPluginRegistry:
    @pytest.mark.asyncio
    async def test_register_plugin(self, registry, webhook_plugin_request):
        plugin = await registry.register(webhook_plugin_request)
        assert plugin.id == "test-webhook"
        assert plugin.type == PluginType.WEBHOOK
        assert plugin.status == PluginStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_register_duplicate_plugin(self, registry, webhook_plugin_request):
        await registry.register(webhook_plugin_request)
        with pytest.raises(PluginExistsError):
            await registry.register(webhook_plugin_request)

    @pytest.mark.asyncio
    async def test_register_webhook_without_config(self, registry):
        with pytest.raises(ValueError, match="webhook_config"):
            await registry.register(
                PluginCreateRequest(
                    id="bad-webhook", name="Bad", type=PluginType.WEBHOOK
                )
            )

    @pytest.mark.asyncio
    async def test_get_plugin(self, registry, webhook_plugin_request):
        await registry.register(webhook_plugin_request)
        assert registry.get("test-webhook").id == "test-webhook"

    @pytest.mark.asyncio
    async def test_get_nonexistent_plugin(self, registry):
        with pytest.raises(PluginNotFoundError):
            registry.get("nonexistent")

    @pytest.mark.asyncio
    async def test_list_plugins(self, registry, webhook_plugin_request):
        await registry.register(webhook_plugin_request)
        assert len(registry.list()) == 1

    @pytest.mark.asyncio
    async def test_update_plugin(self, registry, webhook_plugin_request):
        await registry.register(webhook_plugin_request)
        plugin = await registry.update(
            "test-webhook",
            PluginUpdateRequest(name="Updated", status=PluginStatus.DISABLED),
        )
        assert plugin.name == "Updated"
        assert plugin.status == PluginStatus.DISABLED

    @pytest.mark.asyncio
    async def test_unregister_plugin(self, registry, webhook_plugin_request):
        await registry.register(webhook_plugin_request)
        await registry.unregister("test-webhook")
        with pytest.raises(PluginNotFoundError):
            registry.get("test-webhook")


class TestWebhookExecutor:
    def test_compute_signature_sha256(self):
        sig = WebhookExecutor()._compute_signature(
            b'{"test": "data"}', "secret", "sha256"
        )
        assert sig.startswith("sha256=") and len(sig) == len("sha256=") + 64

    def test_verify_signature(self):
        body, secret = b'{"test": "data"}', "secret"
        executor = WebhookExecutor()
        sig = executor._compute_signature(body, secret, "sha256")
        assert WebhookExecutor.verify_signature(body, sig, secret)
        assert not WebhookExecutor.verify_signature(body, sig, "wrong")

    def test_calculate_delay(self):
        delay = WebhookExecutor()._calculate_delay(1, 1000, 30000, 2.0)
        assert 750 <= delay <= 1250

    @pytest.mark.asyncio
    async def test_send_webhook_success(self):
        executor = WebhookExecutor()
        with patch.object(
            executor, "_attempt_delivery", new_callable=AsyncMock
        ) as mock:
            mock.return_value = {"status": 200, "body": '{"ok": true}'}
            delivery = await executor.send(
                url="https://example.com", method="POST", payload={}, plugin_id="test"
            )
            assert delivery.success and delivery.response_status == 200


class TestPayloadTransformer:
    def test_transform_simple(self, sample_context_card):
        result = PayloadTransformer().transform(
            '{"id": "{{ incident_id }}"}', sample_context_card
        )
        assert result["id"] == "INC-12345"

    def test_transform_with_filters(self, sample_context_card):
        result = PayloadTransformer().transform(
            '{"title": "{{ title | truncate(20) }}"}', sample_context_card
        )
        assert result["title"] == "High error rate o..."

    def test_transform_invalid_json(self, sample_context_card):
        with pytest.raises(ValueError, match="valid JSON"):
            PayloadTransformer().transform("{ invalid }", sample_context_card)

    def test_render_string(self, sample_context_card):
        assert (
            PayloadTransformer().render_string(
                "ID: {{ incident_id }}", sample_context_card
            )
            == "ID: INC-12345"
        )


class TestFilterPlugin:
    @pytest.mark.asyncio
    async def test_filter_include(self, registry, sample_context_card):
        await registry.register(
            PluginCreateRequest(
                id="filter-test",
                name="Filter",
                type=PluginType.FILTER,
                filter_config=FilterConfig(
                    conditions=[
                        FilterCondition(field="severity", operator="eq", value="high")
                    ]
                ),
            )
        )
        result = await registry.test_plugin(
            "filter-test", sample_context_card, dry_run=False
        )
        assert result.success and result.details["conditions_matched"]

    @pytest.mark.asyncio
    async def test_filter_modify(self, registry, sample_context_card):
        await registry.register(
            PluginCreateRequest(
                id="filter-mod",
                name="Modify",
                type=PluginType.FILTER,
                filter_config=FilterConfig(
                    conditions=[
                        FilterCondition(field="severity", operator="eq", value="high")
                    ],
                    action="modify",
                    modifications={"priority": "P1"},
                ),
            )
        )
        result = await registry.test_plugin(
            "filter-mod", sample_context_card, dry_run=False
        )
        assert (
            result.details["action_taken"] == "modified"
            and result.details["result_data"]["priority"] == "P1"
        )


class TestEnrichmentPlugin:
    @pytest.mark.asyncio
    async def test_enrichment_config(self, registry):
        plugin = await registry.register(
            PluginCreateRequest(
                id="enrich-test",
                name="Enrich",
                type=PluginType.ENRICHMENT,
                enrichment_config=EnrichmentConfig(
                    url="https://api.example.com", target_field="metadata"
                ),
            )
        )
        assert plugin.enrichment_config.target_field == "metadata"


class TestHmacConfig:
    def test_valid_algorithms(self):
        HmacConfig(secret="test", algorithm="sha256")
        HmacConfig(secret="test", algorithm="sha512")

    def test_invalid_algorithm(self):
        with pytest.raises(ValueError):
            HmacConfig(secret="test", algorithm="md5")


class TestModelValidation:
    def test_plugin_id_validation(self):
        PluginCreateRequest(
            id="my-plugin",
            name="Test",
            type=PluginType.FILTER,
            filter_config=FilterConfig(),
        )
        with pytest.raises(ValueError):
            PluginCreateRequest(
                id="ab",
                name="Test",
                type=PluginType.FILTER,
                filter_config=FilterConfig(),
            )

    def test_retry_config_validation(self):
        RetryConfig(max_retries=5, initial_delay_ms=1000)
        with pytest.raises(ValueError):
            RetryConfig(max_retries=100)
        with pytest.raises(ValueError):
            RetryConfig(initial_delay_ms=50)
