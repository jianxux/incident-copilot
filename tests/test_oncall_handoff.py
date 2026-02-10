"""Tests for on-call handoff summaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from src.main import create_app
from src.models import Severity
from src.oncall.models import ShiftInfo, ShiftPerson
from src.web.store import incident_store


@pytest.mark.asyncio
async def test_generate_handoff_summary(monkeypatch):
    app = create_app()

    now = datetime.now(UTC)
    shift = ShiftInfo(
        schedule_id="pd_SCHED1",
        schedule_name="Primary",
        outgoing=ShiftPerson(id="u1", name="Alice"),
        incoming=ShiftPerson(id="u2", name="Bob"),
        shift_start=now - timedelta(hours=8),
        shift_end=now - timedelta(minutes=5),
        handoff_time=now - timedelta(minutes=5),
        timezone="UTC",
        provider="pagerduty",
    )

    monkeypatch.setattr(
        "src.oncall.schedule.OnCallScheduleClient.detect_shift_boundary",
        AsyncMock(return_value=shift),
    )

    # Seed an incident during the shift
    await incident_store.add_incident(
        incident_id="INC1",
        title="Database latency spike",
        service_name="db",
        severity=Severity.HIGH,
        triggered_at=now - timedelta(hours=2),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/oncall/handoff/generate",
            json={"schedule_id": "pd_SCHED1"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["id"].startswith("handoff_")
    md = data["summary"]["brief_markdown"]
    assert "Active Issues" in md
    assert "Key Metrics" in md


@pytest.mark.asyncio
async def test_latest_and_history(monkeypatch):
    app = create_app()

    now = datetime.now(UTC)
    shift = ShiftInfo(
        schedule_id="pd_SCHED2",
        outgoing=ShiftPerson(id="u1", name="Alice"),
        incoming=ShiftPerson(id="u2", name="Bob"),
        shift_start=now - timedelta(hours=8),
        shift_end=now - timedelta(minutes=5),
        handoff_time=now - timedelta(minutes=5),
        timezone="UTC",
        provider="pagerduty",
    )

    monkeypatch.setattr(
        "src.oncall.schedule.OnCallScheduleClient.detect_shift_boundary",
        AsyncMock(return_value=shift),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            "/api/v1/oncall/handoff/generate",
            json={"schedule_id": "pd_SCHED2"},
        )
        assert r1.status_code == 200

        latest = await client.get("/api/v1/oncall/handoff/latest")
        assert latest.status_code == 200
        assert latest.json()["summary"] is not None

        hist = await client.get("/api/v1/oncall/handoff/history?limit=10")
        assert hist.status_code == 200
        assert hist.json()["total"] >= 1
        assert len(hist.json()["summaries"]) >= 1


@pytest.mark.asyncio
async def test_configure_and_deliver(monkeypatch):
    app = create_app()

    now = datetime.now(UTC)
    shift = ShiftInfo(
        schedule_id="pd_SCHED3",
        outgoing=ShiftPerson(id="u1", name="Alice"),
        incoming=ShiftPerson(id="u2", name="Bob"),
        shift_start=now - timedelta(hours=8),
        shift_end=now - timedelta(minutes=5),
        handoff_time=now - timedelta(minutes=5),
        timezone="UTC",
        provider="pagerduty",
    )

    monkeypatch.setattr(
        "src.oncall.schedule.OnCallScheduleClient.detect_shift_boundary",
        AsyncMock(return_value=shift),
    )

    # Patch delivery to avoid network calls
    monkeypatch.setattr(
        "src.oncall.routes.HandoffDeliveryService.deliver",
        AsyncMock(return_value=[{"channel": "slack", "success": True}]),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        cfg = await client.post(
            "/api/v1/oncall/handoff/schedule?schedule_id=pd_SCHED3",
            json={
                "enabled": True,
                "delivery_channels": ["slack"],
                "slack_target": "U123",
            },
        )
        assert cfg.status_code == 200

        resp = await client.post(
            "/api/v1/oncall/handoff/generate",
            json={
                "schedule_id": "pd_SCHED3",
                "deliver": True,
                "base_url": "http://test",
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["delivery"][0]["success"] is True
