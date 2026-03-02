"""Tests for Slack channel preference."""

import json

import pytest

from src.integrations.slack_lifecycle import build_incident_notification_blocks


@pytest.mark.unit
def test_notification_blocks_include_tenant_id():
    """The war room button value should contain tenant_id."""
    blocks = build_incident_notification_blocks(
        incident_id="inc-123",
        title="Test incident",
        service="payments",
        severity="high",
        triggered_at="2026-03-01T00:00:00Z",
        tenant_id="tenant-abc",
    )

    for block in blocks:
        if block.get("type") == "actions":
            for element in block.get("elements", []):
                if element.get("action_id") == "start_warroom":
                    value = json.loads(element["value"])
                    assert value["tenant_id"] == "tenant-abc"
                    assert value["incident_id"] == "inc-123"
                    return

    pytest.fail("start_warroom button not found in blocks")


@pytest.mark.unit
def test_notification_blocks_without_tenant_id():
    """When tenant_id is None, it should still be in the value as null."""
    blocks = build_incident_notification_blocks(
        incident_id="inc-456",
        title="Test",
        service="api",
        severity="low",
        triggered_at="2026-03-01T00:00:00Z",
    )

    for block in blocks:
        if block.get("type") == "actions":
            for element in block.get("elements", []):
                if element.get("action_id") == "start_warroom":
                    value = json.loads(element["value"])
                    assert value["tenant_id"] is None
                    return

    pytest.fail("start_warroom button not found in blocks")
