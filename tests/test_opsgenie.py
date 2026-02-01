"""Tests for Opsgenie integration."""

import hashlib
import hmac

import pytest

from src.config import Settings
from src.integrations.opsgenie import OpsgenieAdapter
from src.models import Severity


@pytest.fixture
def settings():
    return Settings(
        opsgenie_api_key="test-api-key",
        opsgenie_webhook_secret="test-secret",
        opsgenie_region="us",
    )


@pytest.fixture
def adapter(settings):
    return OpsgenieAdapter(settings)


# --- Webhook Signature Tests ---


def test_verify_webhook_signature_valid(adapter):
    """Test valid webhook signature verification."""
    payload = b'{"action":"Create","alert":{"alertId":"123"}}'
    expected_sig = hmac.new(
        b"test-secret",
        payload,
        hashlib.sha256,
    ).hexdigest()

    assert adapter.verify_webhook_signature(payload, expected_sig) is True


def test_verify_webhook_signature_invalid(adapter):
    """Test invalid webhook signature is rejected."""
    payload = b'{"action":"Create","alert":{"alertId":"123"}}'
    assert adapter.verify_webhook_signature(payload, "invalid-signature") is False


def test_verify_webhook_signature_no_secret():
    """Test signature verification skipped when no secret configured."""
    settings = Settings(opsgenie_webhook_secret="")
    adapter = OpsgenieAdapter(settings)

    # Should return True (skip verification) when no secret
    assert adapter.verify_webhook_signature(b"any-payload", "any-signature") is True


# --- Webhook Parsing Tests ---


def test_parse_webhook_alert_create(adapter):
    """Test parsing an Opsgenie alert creation webhook."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "12345678-1234-1234-1234-123456789012",
            "tinyId": "1234",
            "message": "High CPU usage on payments-api",
            "description": "CPU usage exceeded 90% threshold",
            "priority": "P2",
            "tags": ["service:payments-api", "env:production", "critical"],
            "alias": "payments-api/high-cpu",
            "createdAt": 1705312200000,  # milliseconds
            "source": "Datadog",
            "entity": "payments-api",
            "responders": [
                {"type": "team", "name": "Platform Team"},
                {"type": "user", "username": "jane.doe@example.com"},
            ],
            "details": {
                "cpu_percent": "95",
                "host": "prod-payments-1",
            },
        },
        "integrationId": "integration-123",
        "integrationName": "Datadog Integration",
    }

    alert = adapter.parse_webhook(payload)

    assert alert is not None
    assert alert.alert_id == "12345678-1234-1234-1234-123456789012"
    assert alert.tiny_id == "1234"
    assert alert.message == "High CPU usage on payments-api"
    assert alert.description == "CPU usage exceeded 90% threshold"
    assert alert.priority == "P2"
    assert alert.severity == Severity.HIGH
    assert "service:payments-api" in alert.tags
    assert alert.service_name == "payments-api"  # Extracted from service: tag
    assert alert.alias == "payments-api/high-cpu"
    assert alert.source == "Datadog"
    assert "Platform Team" in alert.responders
    assert "jane.doe@example.com" in alert.responders
    assert alert.extra_properties["cpu_percent"] == "95"


def test_parse_webhook_ignores_non_create_actions(adapter):
    """Test that non-Create actions are ignored."""
    for action in ["Acknowledge", "Close", "AddNote", "Delete", "Escalate"]:
        payload = {
            "action": action,
            "alert": {"alertId": "123", "message": "Test"},
        }
        assert adapter.parse_webhook(payload) is None


def test_parse_webhook_priority_mapping(adapter):
    """Test Opsgenie priority to severity mapping."""
    priority_to_severity = {
        "P1": Severity.CRITICAL,
        "P2": Severity.HIGH,
        "P3": Severity.MEDIUM,
        "P4": Severity.LOW,
        "P5": Severity.INFO,
    }

    for priority, expected_severity in priority_to_severity.items():
        payload = {
            "action": "Create",
            "alert": {
                "alertId": f"alert-{priority}",
                "message": f"Test {priority}",
                "priority": priority,
                "tags": ["test-service"],
            },
        }
        alert = adapter.parse_webhook(payload)
        assert alert is not None
        assert alert.severity == expected_severity


def test_parse_webhook_service_from_entity(adapter):
    """Test service extraction from entity field."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test alert",
            "entity": "my-service",
            "tags": [],
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    assert alert.service_name == "my-service"


def test_parse_webhook_service_from_alias(adapter):
    """Test service extraction from alias field."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test alert",
            "alias": "auth-service/login-failure",
            "tags": [],
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    assert alert.service_name == "auth-service"


def test_parse_webhook_service_from_tag(adapter):
    """Test service extraction from tags."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test alert",
            "tags": ["env:prod", "api-gateway", "critical"],
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    # Should use first non-generic tag
    assert alert.service_name == "env:prod" or alert.service_name == "api-gateway"


def test_parse_webhook_handles_missing_fields(adapter):
    """Test graceful handling of missing optional fields."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "minimal-alert-123",
            "message": "Minimal alert",
        },
    }

    alert = adapter.parse_webhook(payload)

    assert alert is not None
    assert alert.alert_id == "minimal-alert-123"
    assert alert.message == "Minimal alert"
    assert alert.priority == "P3"  # Default
    assert alert.severity == Severity.MEDIUM  # Default
    assert alert.service_name == "unknown-service"  # Default
    assert alert.tags == []
    assert alert.responders == []


def test_parse_webhook_timestamp_milliseconds(adapter):
    """Test parsing timestamp in milliseconds format."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test",
            "createdAt": 1705312200000,  # 2024-01-15T10:30:00Z
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    assert alert.triggered_at.year == 2024
    assert alert.triggered_at.month == 1
    assert alert.triggered_at.day == 15


def test_parse_webhook_timestamp_iso_format(adapter):
    """Test parsing timestamp in ISO format."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test",
            "createdAt": "2024-01-15T10:30:00Z",
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    assert alert.triggered_at.year == 2024


def test_parse_webhook_string_tags(adapter):
    """Test parsing comma-separated string tags."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test",
            "tags": "production, critical, payments",
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    assert "production" in alert.tags
    assert "critical" in alert.tags
    assert "payments" in alert.tags


def test_parse_webhook_empty_alert_data(adapter):
    """Test handling of empty alert data."""
    payload = {
        "action": "Create",
        "alert": {},
    }

    alert = adapter.parse_webhook(payload)
    # Should still create an alert with defaults
    assert alert is not None
    assert alert.alert_id == ""
    assert alert.message == "Unknown Alert"


def test_parse_webhook_malformed_payload(adapter):
    """Test handling of malformed payload."""
    # Missing alert key entirely
    payload = {
        "action": "Create",
    }

    alert = adapter.parse_webhook(payload)
    assert alert is None


# --- Model Property Tests ---


def test_opsgenie_alert_title_property(adapter):
    """Test that title property returns message."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "This is the alert message",
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    assert alert.title == "This is the alert message"


def test_opsgenie_alert_assigned_to_property(adapter):
    """Test that assigned_to property returns responders."""
    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test",
            "responders": [
                {"type": "user", "username": "john@example.com"},
            ],
        },
    }

    alert = adapter.parse_webhook(payload)
    assert alert is not None
    assert alert.assigned_to == ["john@example.com"]


# --- API Integration Tests (Mock) ---


@pytest.mark.asyncio
async def test_get_alert_details_no_api_key():
    """Test get_alert_details returns None when no API key configured."""
    settings = Settings(opsgenie_api_key="")
    adapter = OpsgenieAdapter(settings)

    result = await adapter.get_alert_details("some-alert-id")
    assert result is None


@pytest.mark.asyncio
async def test_enrich_alert_no_api_key(adapter):
    """Test enrich_alert returns alert unchanged when no API key."""
    settings = Settings(opsgenie_api_key="")
    adapter_no_key = OpsgenieAdapter(settings)

    payload = {
        "action": "Create",
        "alert": {
            "alertId": "123",
            "message": "Test",
        },
    }
    alert = adapter.parse_webhook(payload)

    enriched = await adapter_no_key.enrich_alert(alert)
    assert enriched.alert_id == alert.alert_id
