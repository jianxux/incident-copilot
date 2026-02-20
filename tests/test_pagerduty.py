"""Tests for PagerDuty integration."""

import pytest

from src.config import Settings
from src.integrations.pagerduty import PagerDutyAdapter
from src.models import Severity


@pytest.fixture
def settings():
    return Settings(pagerduty_webhook_secret="test-secret")


@pytest.fixture
def adapter(settings):
    return PagerDutyAdapter(settings)


def test_parse_webhook_incident_triggered(adapter):
    """Test parsing a PagerDuty incident.triggered webhook."""
    payload = {
        "event": {
            "event_type": "incident.triggered",
            "data": {
                "id": "P1234567",
                "incident_number": 42,
                "title": "High error rate on payments-api",
                "description": "Error rate exceeded threshold",
                "urgency": "high",
                "created_at": "2024-01-15T10:30:00Z",
                "html_url": "https://mycompany.pagerduty.com/incidents/P1234567",
                "service": {
                    "id": "PSVC123",
                    "summary": "payments-api",
                },
                "assignments": [
                    {"assignee": {"summary": "Jane Doe"}},
                    {"assignee": {"summary": "John Smith"}},
                ],
            },
        }
    }

    incident = adapter.parse_webhook(payload)

    assert incident is not None
    assert incident.incident_id == "P1234567"
    assert incident.incident_number == 42
    assert incident.title == "High error rate on payments-api"
    assert incident.severity == Severity.HIGH
    assert incident.service_name == "payments-api"
    assert incident.assigned_to == ["Jane Doe", "John Smith"]


def test_parse_webhook_ignores_other_events(adapter):
    """Test that non-incident.triggered events are ignored."""
    payload = {
        "event": {
            "event_type": "incident.resolved",
            "data": {"id": "P1234567"},
        }
    }

    incident = adapter.parse_webhook(payload)
    assert incident is None


def test_parse_webhook_handles_missing_fields(adapter):
    """Test graceful handling of missing fields."""
    payload = {
        "event": {
            "event_type": "incident.triggered",
            "data": {
                "id": "P1234567",
                "title": "Some incident",
                "service": {},
            },
        }
    }

    incident = adapter.parse_webhook(payload)

    assert incident is not None
    assert incident.incident_id == "P1234567"
    assert incident.service_name == "unknown-service"
    assert incident.severity == Severity.LOW  # default in legacy adapter
