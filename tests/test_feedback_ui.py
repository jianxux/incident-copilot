"""Tests for incident detail feedback endpoints used by feedback UI."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.memory_feedback import feedback_router
from src.memory.feedback import FeedbackStore


def test_verdict_feedback_endpoint_returns_200(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(feedback_router)

    feedback_store = FeedbackStore(database_path=str(tmp_path / "feedback_ui.db"))
    monkeypatch.setattr(
        "src.api.memory_feedback._feedback_store", lambda: feedback_store
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/feedback/verdict",
            json={
                "incident_id": "INC-UI-1",
                "feedback_type": "verdict",
                "feedback": "helpful",
                "notes": "Good verdict",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["feedback"]["feedback_type"] == "verdict"


def test_verdict_feedback_invalid_feedback_type_returns_422(tmp_path, monkeypatch):
    app = FastAPI()
    app.include_router(feedback_router)

    feedback_store = FeedbackStore(database_path=str(tmp_path / "feedback_ui.db"))
    monkeypatch.setattr(
        "src.api.memory_feedback._feedback_store", lambda: feedback_store
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/feedback/verdict",
            json={
                "incident_id": "INC-UI-2",
                "feedback_type": "invalid_type",
                "feedback": "not_helpful",
            },
        )

    assert response.status_code == 422
