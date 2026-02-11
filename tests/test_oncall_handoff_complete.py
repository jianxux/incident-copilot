"""Completion tests for on-call handoff dashboard, scheduler, and routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.main import create_app
from src.oncall.generator import HandoffSummaryGenerator
from src.oncall.models import (
    HandoffAggregate,
    HandoffConfig,
    HandoffDeliveryChannel,
    HandoffSummary,
    IncidentActivityItem,
    ShiftInfo,
    ShiftPerson,
)
from src.oncall.routes import _HANDOFF_CONFIGS, _HANDOFF_HISTORY
from src.oncall.scheduler import OnCallHandoffScheduler


@pytest.fixture(autouse=True)
def clear_handoff_state():
    _HANDOFF_CONFIGS.clear()
    _HANDOFF_HISTORY.clear()
    yield
    _HANDOFF_CONFIGS.clear()
    _HANDOFF_HISTORY.clear()


def _sample_shift(schedule_id: str = "pd_sched") -> ShiftInfo:
    now = datetime.now(UTC)
    return ShiftInfo(
        schedule_id=schedule_id,
        schedule_name="Primary",
        outgoing=ShiftPerson(id="u1", name="Alice"),
        incoming=ShiftPerson(id="u2", name="Bob"),
        shift_start=now - timedelta(hours=8),
        shift_end=now - timedelta(minutes=5),
        handoff_time=now - timedelta(minutes=5),
        timezone="UTC",
        provider="pagerduty",
    )


def _sample_aggregate(schedule_id: str = "pd_sched") -> HandoffAggregate:
    shift = _sample_shift(schedule_id=schedule_id)
    return HandoffAggregate(
        shift=shift,
        active_incidents=[
            IncidentActivityItem(
                id="inc_1",
                title="Database latency spike",
                status="triggered",
                severity="high",
                service="db",
                next_steps=["Verify primary replica lag", "Monitor p99 latency"],
            )
        ],
        resolved_incidents=[
            IncidentActivityItem(
                id="inc_2",
                title="Queue backlog recovered",
                status="resolved",
                severity="medium",
                service="worker",
            )
        ],
        watch_items=["Keep an eye on write saturation"],
    )


@pytest.mark.asyncio
async def test_scheduler_starts_and_stops_cleanly():
    scheduler = OnCallHandoffScheduler(Settings(), poll_interval_seconds=1)
    await scheduler.start()
    assert scheduler.is_running is True
    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_scheduler_detects_and_generates_handoff(monkeypatch):
    cfg = HandoffConfig(
        schedule_id="pd_sched",
        enabled=True,
        grace_minutes=20,
        delivery_channels=[HandoffDeliveryChannel.IN_APP],
    )
    _HANDOFF_CONFIGS[cfg.schedule_id] = cfg

    scheduler = OnCallHandoffScheduler(Settings(), poll_interval_seconds=1)
    shift = _sample_shift(schedule_id=cfg.schedule_id)
    aggregate = _sample_aggregate(schedule_id=cfg.schedule_id)
    summary = HandoffSummary(
        id="handoff_test_1",
        shift=shift,
        aggregate=aggregate,
        title="Test Handoff",
        brief_markdown="## Active Issues\n- Database latency spike",
    )

    monkeypatch.setattr(
        scheduler.schedule_client,
        "detect_shift_boundary",
        AsyncMock(return_value=shift),
    )
    monkeypatch.setattr(
        scheduler.aggregator, "aggregate", AsyncMock(return_value=aggregate)
    )
    monkeypatch.setattr(
        scheduler.generator, "generate", AsyncMock(return_value=summary)
    )
    monkeypatch.setattr(
        scheduler.delivery,
        "deliver",
        AsyncMock(return_value=[{"channel": "in_app", "success": True}]),
    )

    generated = await scheduler.check_once()
    assert generated == 1
    assert len(_HANDOFF_HISTORY) == 1

    generated_again = await scheduler.check_once()
    assert generated_again == 0


@pytest.mark.asyncio
async def test_generate_catchup_heuristic_contains_sections():
    generator = HandoffSummaryGenerator(Settings())
    aggregate = _sample_aggregate()
    summary = await generator.generate_catchup(aggregate, since_message_count=5)
    assert "Current Critical Context" in summary.brief_markdown
    assert "Immediate Next Actions" in summary.brief_markdown


@pytest.mark.asyncio
async def test_generate_title_ai_uses_model_response():
    generator = HandoffSummaryGenerator(Settings())
    aggregate = _sample_aggregate()

    mock_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    content=[
                        SimpleNamespace(text="Payments API elevated error budget burn")
                    ]
                )
            )
        )
    )
    generator.client = mock_client

    title = await generator.generate_title(aggregate)
    assert title == "Payments API elevated error budget burn"


@pytest.mark.asyncio
async def test_catchup_api_route(monkeypatch):
    app = create_app()
    shift = _sample_shift("pd_sched")
    aggregate = _sample_aggregate("pd_sched")
    catchup = HandoffSummary(
        id="handoff_catchup_1",
        shift=shift,
        aggregate=aggregate,
        title="Catchup",
        brief_markdown="## Current Critical Context\n- One issue",
    )

    monkeypatch.setattr(
        "src.oncall.schedule.OnCallScheduleClient.detect_shift_boundary",
        AsyncMock(return_value=shift),
    )
    monkeypatch.setattr(
        "src.oncall.aggregator.OnCallActivityAggregator.aggregate",
        AsyncMock(return_value=aggregate),
    )
    monkeypatch.setattr(
        "src.oncall.generator.HandoffSummaryGenerator.generate_catchup",
        AsyncMock(return_value=catchup),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/oncall/handoff/catchup/pd_sched",
            json={"since_message_count": 6},
        )
    assert resp.status_code == 200
    assert resp.json()["summary"]["id"] == "handoff_catchup_1"


@pytest.mark.asyncio
async def test_get_handoff_by_id_api(monkeypatch):
    app = create_app()
    shift = _sample_shift("pd_sched")

    monkeypatch.setattr(
        "src.oncall.schedule.OnCallScheduleClient.detect_shift_boundary",
        AsyncMock(return_value=shift),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        generated = await client.post(
            "/api/v1/oncall/handoff/generate",
            json={"schedule_id": "pd_sched"},
        )
        handoff_id = generated.json()["summary"]["id"]

        fetched = await client.get(f"/api/v1/oncall/handoff/{handoff_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == handoff_id


@pytest.mark.asyncio
async def test_delete_handoff_api(monkeypatch):
    app = create_app()
    shift = _sample_shift("pd_sched")

    monkeypatch.setattr(
        "src.oncall.schedule.OnCallScheduleClient.detect_shift_boundary",
        AsyncMock(return_value=shift),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        generated = await client.post(
            "/api/v1/oncall/handoff/generate",
            json={"schedule_id": "pd_sched"},
        )
        handoff_id = generated.json()["summary"]["id"]

        deleted = await client.delete(f"/api/v1/oncall/handoff/{handoff_id}")
        assert deleted.status_code == 200

        fetched = await client.get(f"/api/v1/oncall/handoff/{handoff_id}")
        assert fetched.status_code == 404


@pytest.mark.asyncio
async def test_test_delivery_api(monkeypatch):
    app = create_app()
    _HANDOFF_CONFIGS["pd_sched"] = HandoffConfig(
        schedule_id="pd_sched",
        enabled=True,
        delivery_channels=[HandoffDeliveryChannel.SLACK],
        slack_target="#oncall",
    )

    monkeypatch.setattr(
        "src.oncall.routes.HandoffDeliveryService.deliver",
        AsyncMock(return_value=[{"channel": "slack", "success": True}]),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/oncall/handoff/test-delivery",
            json={"schedule_id": "pd_sched"},
        )
    assert resp.status_code == 200
    assert resp.json()["delivery"][0]["success"] is True


def test_handoff_dashboard_page_loads():
    app = create_app()
    client = TestClient(app)
    response = client.get("/dashboard/handoff")
    assert response.status_code == 200
    assert "Generate Handoff" in response.text


def test_handoff_nav_link_present():
    app = create_app()
    client = TestClient(app)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "/dashboard/handoff" in response.text


def test_app_lifespan_starts_and_stops_scheduler(monkeypatch):
    started = {"value": False}
    stopped = {"value": False}

    async def _start(*args, **kwargs):
        started["value"] = True

    async def _stop(*args, **kwargs):
        stopped["value"] = True

    monkeypatch.setattr("src.main.start_oncall_handoff_scheduler", _start)
    monkeypatch.setattr("src.main.stop_oncall_handoff_scheduler", _stop)

    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    assert started["value"] is True
    assert stopped["value"] is True
