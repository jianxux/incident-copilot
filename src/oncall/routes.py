"""API routes for on-call handoff summaries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from .aggregator import OnCallActivityAggregator
from .delivery import HandoffDeliveryService
from .generator import HandoffSummaryGenerator
from .models import HandoffConfig, HandoffDeliveryChannel, HandoffSummary
from .schedule import OnCallScheduleClient

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/oncall", tags=["oncall-handoff"])


# ---- In-memory stores (dev/test) ----

_HANDOFF_HISTORY: list[HandoffSummary] = []
_HANDOFF_CONFIGS: dict[str, HandoffConfig] = {}


def _store_summary(summary: HandoffSummary) -> None:
    _HANDOFF_HISTORY.insert(0, summary)
    # keep last N
    del _HANDOFF_HISTORY[50:]


# ---- Dependencies ----


def get_oncall_schedule_client(settings: Settings = Depends(get_settings)):
    return OnCallScheduleClient(settings)


def get_aggregator(settings: Settings = Depends(get_settings)):
    return OnCallActivityAggregator(settings)


def get_generator(settings: Settings = Depends(get_settings)):
    return HandoffSummaryGenerator(settings)


def get_delivery(settings: Settings = Depends(get_settings)):
    return HandoffDeliveryService(settings)


# ---- Request/Response models ----


class GenerateHandoffRequest(BaseModel):
    schedule_id: str = Field(..., description="Internal schedule id (e.g., pd_<id>)")
    reference_time: datetime | None = Field(
        None, description="Detect handoff boundary at/near this time (ISO)"
    )
    deliver: bool = Field(
        default=False, description="If true, attempt delivery per stored config"
    )
    base_url: str | None = Field(
        default=None, description="Public base URL used for links in messages"
    )


class GenerateHandoffResponse(BaseModel):
    summary: HandoffSummary
    delivery: list[dict[str, Any]] = Field(default_factory=list)


class GenerateCatchupRequest(BaseModel):
    since_message_count: int = Field(default=10, ge=1, le=200)


class LatestHandoffResponse(BaseModel):
    summary: HandoffSummary | None


class HistoryResponse(BaseModel):
    total: int
    summaries: list[HandoffSummary]


class ScheduleResponse(BaseModel):
    schedule_id: str
    detected_shift: dict[str, Any] | None = None


class UpdateHandoffConfigRequest(BaseModel):
    enabled: bool = False
    grace_minutes: int = 15
    lookahead_minutes: int = 60

    delivery_channels: list[HandoffDeliveryChannel] = Field(default_factory=list)
    slack_target: str | None = None
    teams_webhook_url: str | None = None
    email_target: str | None = None


class TestDeliveryRequest(BaseModel):
    schedule_id: str
    base_url: str | None = None
    title: str = "On-Call Handoff Delivery Test"
    message: str = "This is a delivery test for on-call handoff configuration."


# ---- Routes ----


@router.post("/handoff/generate", response_model=GenerateHandoffResponse)
async def generate_handoff(
    request: GenerateHandoffRequest,
    schedule: OnCallScheduleClient = Depends(get_oncall_schedule_client),
    aggregator: OnCallActivityAggregator = Depends(get_aggregator),
    generator: HandoffSummaryGenerator = Depends(get_generator),
    delivery: HandoffDeliveryService = Depends(get_delivery),
):
    """Manually generate a handoff summary for the most recent handoff."""
    ref = request.reference_time or datetime.now(UTC)

    shift = await schedule.detect_shift_boundary(
        schedule_id=request.schedule_id,
        reference_time=ref,
        window_hours=24,
    )
    if not shift:
        raise HTTPException(status_code=404, detail="No recent shift boundary found")

    aggregate = await aggregator.aggregate(shift)
    summary = await generator.generate(aggregate)

    _store_summary(summary)

    delivery_results: list[dict[str, Any]] = []
    if request.deliver:
        cfg = _HANDOFF_CONFIGS.get(request.schedule_id)
        if not cfg:
            raise HTTPException(
                status_code=400,
                detail="No handoff delivery config for this schedule_id",
            )
        delivery_results = await delivery.deliver(
            summary, cfg, base_url=request.base_url
        )
        summary.delivered_to = delivery_results

    return GenerateHandoffResponse(summary=summary, delivery=delivery_results)


@router.get("/handoff/latest", response_model=LatestHandoffResponse)
async def latest_handoff():
    """Get the most recent generated handoff summary."""
    return LatestHandoffResponse(
        summary=_HANDOFF_HISTORY[0] if _HANDOFF_HISTORY else None
    )


@router.get("/handoff/history", response_model=HistoryResponse)
async def handoff_history(limit: int = 20):
    """List past handoff summaries."""
    limit = max(1, min(limit, 50))
    return HistoryResponse(
        total=len(_HANDOFF_HISTORY), summaries=_HANDOFF_HISTORY[:limit]
    )


@router.post("/handoff/catchup/{schedule_id}", response_model=GenerateHandoffResponse)
async def generate_handoff_catchup(
    schedule_id: str,
    request: GenerateCatchupRequest,
    schedule: OnCallScheduleClient = Depends(get_oncall_schedule_client),
    aggregator: OnCallActivityAggregator = Depends(get_aggregator),
    generator: HandoffSummaryGenerator = Depends(get_generator),
):
    """Generate a catch-up summary for a recent shift boundary."""
    shift = await schedule.detect_shift_boundary(
        schedule_id=schedule_id,
        reference_time=datetime.now(UTC),
        window_hours=24,
    )
    if not shift:
        raise HTTPException(status_code=404, detail="No recent shift boundary found")

    aggregate = await aggregator.aggregate(shift)
    summary = await generator.generate_catchup(
        aggregate=aggregate, since_message_count=request.since_message_count
    )
    _store_summary(summary)
    return GenerateHandoffResponse(summary=summary, delivery=[])


@router.get("/handoff/{handoff_id}", response_model=HandoffSummary)
async def get_handoff_by_id(handoff_id: str):
    """Get a specific handoff summary by id."""
    for summary in _HANDOFF_HISTORY:
        if summary.id == handoff_id:
            return summary
    raise HTTPException(status_code=404, detail="Handoff not found")


@router.delete("/handoff/{handoff_id}")
async def delete_handoff(handoff_id: str):
    """Delete a specific handoff summary by id."""
    idx = next(
        (i for i, item in enumerate(_HANDOFF_HISTORY) if item.id == handoff_id), -1
    )
    if idx < 0:
        raise HTTPException(status_code=404, detail="Handoff not found")
    removed = _HANDOFF_HISTORY.pop(idx)
    return {"status": "ok", "deleted_id": removed.id}


@router.get("/schedule", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: str,
    reference_time: datetime | None = None,
    schedule: OnCallScheduleClient = Depends(get_oncall_schedule_client),
):
    """View current schedule information and nearest shift handoff boundary."""
    shift = await schedule.detect_shift_boundary(
        schedule_id=schedule_id,
        reference_time=reference_time or datetime.now(UTC),
        window_hours=48,
    )
    return ScheduleResponse(
        schedule_id=schedule_id,
        detected_shift=shift.model_dump(mode="json") if shift else None,
    )


@router.post("/handoff/schedule")
async def configure_handoff_schedule(
    schedule_id: str,
    request: UpdateHandoffConfigRequest,
):
    """Configure auto-handoff timing & delivery for a schedule.

    Note: auto-generation is not executed by a background scheduler yet; this endpoint
    stores configuration used when calling /handoff/generate with deliver=true.
    """

    cfg = HandoffConfig(
        schedule_id=schedule_id,
        enabled=request.enabled,
        grace_minutes=request.grace_minutes,
        lookahead_minutes=request.lookahead_minutes,
        delivery_channels=request.delivery_channels,
        slack_target=request.slack_target,
        teams_webhook_url=request.teams_webhook_url,
        email_target=request.email_target,
        updated_at=datetime.now(UTC),
    )

    _HANDOFF_CONFIGS[schedule_id] = cfg

    return {"status": "ok", "config": cfg.model_dump(mode="json")}


@router.post("/handoff/test-delivery")
async def test_handoff_delivery(
    request: TestDeliveryRequest,
    delivery: HandoffDeliveryService = Depends(get_delivery),
):
    """Test delivery channels for an existing schedule config."""
    cfg = _HANDOFF_CONFIGS.get(request.schedule_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="No handoff config for schedule_id")

    now = datetime.now(UTC)
    summary = HandoffSummary(
        id=f"handoff_test_{request.schedule_id}",
        created_at=now,
        shift={
            "schedule_id": request.schedule_id,
            "schedule_name": "Test Schedule",
            "outgoing": {"id": "outgoing", "name": "Outgoing Engineer"},
            "incoming": {"id": "incoming", "name": "Incoming Engineer"},
            "shift_start": now,
            "shift_end": now,
            "handoff_time": now,
            "timezone": "UTC",
            "provider": "test",
            "raw": {},
        },
        aggregate={
            "shift": {
                "schedule_id": request.schedule_id,
                "schedule_name": "Test Schedule",
                "outgoing": {"id": "outgoing", "name": "Outgoing Engineer"},
                "incoming": {"id": "incoming", "name": "Incoming Engineer"},
                "shift_start": now,
                "shift_end": now,
                "handoff_time": now,
                "timezone": "UTC",
                "provider": "test",
                "raw": {},
            },
            "active_incidents": [],
            "resolved_incidents": [],
            "watch_items": [],
            "metrics": {
                "incidents_opened": 0,
                "incidents_resolved": 0,
                "incidents_escalated": 0,
                "alerts_acknowledged_unresolved": 0,
            },
            "data_sources": ["test"],
            "errors": [],
        },
        title=request.title,
        brief_markdown=request.message,
        generator="test",
        model=None,
    )

    results = await delivery.deliver(
        summary=summary, config=cfg, base_url=request.base_url
    )
    return {"status": "ok", "delivery": results}
