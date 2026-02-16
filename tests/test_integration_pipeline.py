"""Integration-style tests for the PagerDuty webhook endpoint.

Covers request validation (signature, JSON), event filtering, and basic
severity mapping by ensuring the parsed incident passed into the background
pipeline matches expectations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from src.api.webhooks import router as webhooks_router
from src.config import Settings


def _pd_v3_payload(
    *,
    event_type: str,
    incident_id: str = "P1234567",
    urgency: str = "high",
    service_summary: str = "payments-api",
) -> dict[str, Any]:
    return {
        "event": {
            "event_type": event_type,
            "data": {
                "id": incident_id,
                "incident_number": 42,
                "title": "High error rate on payments-api",
                "description": "Error rate exceeded threshold",
                "urgency": urgency,
                "created_at": "2026-02-16T11:30:00Z",
                "html_url": f"https://acme.pagerduty.com/incidents/{incident_id}",
                "service": {"id": "PSVC123", "summary": service_summary},
                "assignments": [{"assignee": {"summary": "Jane Doe"}}],
            },
        }
    }


def _sign_pd(payload_bytes: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(webhooks_router)
    return app


@pytest.mark.anyio
async def test_pagerduty_webhook_realistic_v3_payload_returns_200(monkeypatch):
    import src.api.webhooks as webhooks

    secret = "test-secret"
    settings = Settings(
        pagerduty_webhook_secret=secret,
        correlation_enabled=False,
        ratelimit_enabled=False,
        audit_enabled=False,
        oncall_enabled=False,
    )
    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)

    captured: dict[str, Any] = {"incident": None}

    async def _capture_bg(incident, _settings):
        captured["incident"] = incident

    monkeypatch.setattr(webhooks, "process_pagerduty_incident_background", _capture_bg)

    payload = _pd_v3_payload(event_type="incident.triggered", urgency="high")
    body = json.dumps(payload).encode("utf-8")

    transport = httpx.ASGITransport(app=_app(), lifespan="off")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhooks/pagerduty",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PagerDuty-Signature": _sign_pd(body, secret),
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert captured["incident"] is not None
    assert captured["incident"].incident_id == "P1234567"


@pytest.mark.anyio
async def test_pagerduty_webhook_invalid_json_returns_400(monkeypatch):
    import src.api.webhooks as webhooks

    secret = "test-secret"
    settings = Settings(
        pagerduty_webhook_secret=secret,
        correlation_enabled=False,
        ratelimit_enabled=False,
        audit_enabled=False,
        oncall_enabled=False,
    )
    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)

    body = b"{not-json"

    transport = httpx.ASGITransport(app=_app(), lifespan="off")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhooks/pagerduty",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PagerDuty-Signature": _sign_pd(body, secret),
            },
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid JSON"


@pytest.mark.anyio
async def test_pagerduty_webhook_non_incident_event_is_ignored(monkeypatch):
    import src.api.webhooks as webhooks

    secret = "test-secret"
    settings = Settings(
        pagerduty_webhook_secret=secret,
        correlation_enabled=False,
        ratelimit_enabled=False,
        audit_enabled=False,
        oncall_enabled=False,
    )
    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)

    # Ensure no background pipeline is invoked for ignored events
    called = {"count": 0}

    async def _bg(_incident, _settings):
        called["count"] += 1

    monkeypatch.setattr(webhooks, "process_pagerduty_incident_background", _bg)

    payload = _pd_v3_payload(event_type="incident.acknowledged")
    body = json.dumps(payload).encode("utf-8")

    transport = httpx.ASGITransport(app=_app(), lifespan="off")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhooks/pagerduty",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PagerDuty-Signature": _sign_pd(body, secret),
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ignored"
    assert called["count"] == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "urgency,expected",
    [("high", "high"), ("low", "low"), ("unknown", "medium")],
)
async def test_pagerduty_webhook_severity_mapping(monkeypatch, urgency, expected):
    import src.api.webhooks as webhooks

    secret = "test-secret"
    settings = Settings(
        pagerduty_webhook_secret=secret,
        correlation_enabled=False,
        ratelimit_enabled=False,
        audit_enabled=False,
        oncall_enabled=False,
    )
    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)

    captured: dict[str, Any] = {"severity": None}

    async def _capture_bg(incident, _settings):
        captured["severity"] = incident.severity.value

    monkeypatch.setattr(webhooks, "process_pagerduty_incident_background", _capture_bg)

    payload = _pd_v3_payload(event_type="incident.triggered", urgency=urgency)
    body = json.dumps(payload).encode("utf-8")

    transport = httpx.ASGITransport(app=_app(), lifespan="off")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/webhooks/pagerduty",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-PagerDuty-Signature": _sign_pd(body, secret),
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert captured["severity"] == expected
