"""Incident Memory feedback API endpoints."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import get_settings
from ..integrations.slack import SlackAdapter
from ..memory import (
    IncidentMemoryConfig,
    ResolutionFeedback,
    get_feedback_store,
)
from ..memory.feedback import AIFeedback, AIFeedbackType, AIFeedbackValue, FeedbackType

logger = structlog.get_logger()
router = APIRouter(prefix="/api/memory", tags=["memory-feedback"])
feedback_router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _feedback_store():
    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)
    return get_feedback_store(config.feedback_database_path)


class SubmitFeedbackRequest(BaseModel):
    """Request payload for memory recall feedback."""

    incident_id: str = Field(..., min_length=1)
    recalled_incident_id: str = Field(..., min_length=1)
    feedback: FeedbackType
    notes: str | None = None


class SubmitAIFeedbackRequest(BaseModel):
    """Request payload for verdict/summary/runbook feedback."""

    incident_id: str = Field(..., min_length=1)
    feedback_type: AIFeedbackType
    feedback: AIFeedbackValue
    notes: str | None = None


@router.post("/feedback")
async def submit_feedback(request: SubmitFeedbackRequest):
    """Submit resolution feedback for a recalled incident."""
    store = _feedback_store()
    item = ResolutionFeedback(
        incident_id=request.incident_id,
        recalled_incident_id=request.recalled_incident_id,
        feedback=request.feedback,
        notes=request.notes,
    )
    await store.submit(item)
    return {"status": "ok", "feedback": item.model_dump(mode="json")}


@feedback_router.post("/verdict")
async def submit_ai_feedback(request: SubmitAIFeedbackRequest):
    """Submit operator feedback for AI verdict/summary/runbook suggestions."""
    store = _feedback_store()
    item = AIFeedback(
        incident_id=request.incident_id,
        feedback_type=request.feedback_type,
        feedback=request.feedback,
        notes=request.notes,
    )
    await store.submit_ai_feedback(item)
    return {"status": "ok", "feedback": item.model_dump(mode="json")}


@router.get("/feedback/{incident_id}")
async def get_feedback(incident_id: str):
    """Get feedback entries for an incident."""
    store = _feedback_store()
    rows = await store.list_for_incident(incident_id)
    return {
        "incident_id": incident_id,
        "count": len(rows),
        "feedback": [item.model_dump(mode="json") for item in rows],
    }


@router.post("/feedback/slack")
async def slack_feedback_interaction(
    request: Request,
    x_slack_signature: str | None = Header(None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str | None = Header(
        None, alias="X-Slack-Request-Timestamp"
    ),
):
    """Handle Slack interactive feedback button callbacks."""
    settings = get_settings()
    raw_body = await request.body()
    parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
    payload_raw = (parsed.get("payload") or [None])[0]
    if not payload_raw:
        raise HTTPException(status_code=400, detail="Missing Slack payload")

    payload = json.loads(payload_raw)
    adapter = SlackAdapter(settings)

    # Use adapter utility for signature verification when configured.
    if settings.slack_signing_secret:
        from ..copilot.adapters.slack_adapter import verify_slack_signature

        if not verify_slack_signature(
            body=raw_body,
            timestamp=x_slack_request_timestamp,
            signature=x_slack_signature,
            signing_secret=settings.slack_signing_secret,
        ):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    stored = await adapter.handle_feedback_interaction(payload, _feedback_store())
    if not stored:
        return {"ok": False, "status": "ignored"}
    return {"ok": True, "status": "stored"}
