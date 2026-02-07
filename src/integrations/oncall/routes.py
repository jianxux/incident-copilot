"""FastAPI routes for On-Call Scheduling integration."""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .models import (
    OnCallSchedule,
    OnCallShift,
    OnCallUser,
    OnCallOverride,
    ProviderType,
    OverrideStatus,
    ScheduleSyncResult,
    Rotation,
)
from .service import OnCallService


router = APIRouter(prefix="/oncall", tags=["oncall"])

# Dependency injection for service
_service: Optional[OnCallService] = None


def get_service() -> OnCallService:
    """Get the on-call service instance."""
    global _service
    if _service is None:
        _service = OnCallService()
    return _service


def init_service(pagerduty_key: Optional[str] = None, opsgenie_key: Optional[str] = None):
    """Initialize the service with API keys."""
    global _service
    _service = OnCallService(pagerduty_key=pagerduty_key, opsgenie_key=opsgenie_key)


# === Request/Response Models ===


class CreateOverrideRequest(BaseModel):
    """Request to create a schedule override."""

    override_user_id: str
    override_user_name: str
    override_user_email: str
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = None


class CreateScheduleRequest(BaseModel):
    """Request to create a manual schedule."""

    name: str
    description: Optional[str] = None
    team_id: str
    timezone: str = "UTC"


class AddRotationRequest(BaseModel):
    """Request to add a rotation to a schedule."""

    name: str
    type: str = "weekly"
    handoff_time: str = "09:00"
    handoff_day: Optional[int] = None
    participant_ids: list[str] = Field(default_factory=list)


class WhoIsOnCallResponse(BaseModel):
    """Response for who-is-on-call query."""

    schedule_id: str
    schedule_name: str
    oncall_user: Optional[OnCallUser] = None
    is_override: bool = False
    shift_ends_at: Optional[datetime] = None


class UpcomingShiftsResponse(BaseModel):
    """Response for upcoming shifts query."""

    schedule_id: str
    shifts: list[OnCallShift]
    total_count: int


class ScheduleVisualization(BaseModel):
    """Response for schedule visualization."""

    schedule_id: str
    schedule_name: str
    timezone: str
    range_days: int
    participants: list[dict]
    rotations: list[dict]


# === Routes ===


@router.get("/schedules", response_model=list[OnCallSchedule])
async def list_schedules(
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
    service: OnCallService = Depends(get_service),
):
    """List all on-call schedules."""
    return await service.list_schedules(team_id=team_id)


@router.get("/schedules/{schedule_id}", response_model=OnCallSchedule)
async def get_schedule(schedule_id: str, service: OnCallService = Depends(get_service)):
    """Get a specific schedule by ID."""
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("/schedules", response_model=OnCallSchedule)
async def create_schedule(
    request: CreateScheduleRequest, service: OnCallService = Depends(get_service)
):
    """Create a new manual schedule."""
    schedule = OnCallSchedule(
        id="",  # Will be assigned
        name=request.name,
        description=request.description,
        team_id=request.team_id,
        provider=ProviderType.MANUAL,
        timezone=request.timezone,
    )
    return await service.create_manual_schedule(schedule)


@router.post("/schedules/sync", response_model=list[ScheduleSyncResult])
async def sync_schedules(service: OnCallService = Depends(get_service)):
    """Sync all schedules from configured providers."""
    return await service.sync_all_schedules()


@router.get("/schedules/{schedule_id}/oncall", response_model=WhoIsOnCallResponse)
async def who_is_oncall(
    schedule_id: str,
    at: Optional[datetime] = Query(None, description="Check at specific time (ISO format)"),
    service: OnCallService = Depends(get_service),
):
    """Get the currently on-call user for a schedule."""
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    user = await service.who_is_oncall(schedule_id, at_time=at)

    # Check if this is an override
    overrides = await service.list_overrides(schedule_id=schedule_id, active_only=True)
    is_override = any(o.override_user.id == user.id if user else False for o in overrides)

    # Get current shift end time
    shifts = await service.get_upcoming_shifts(schedule_id, days=1)
    current_shift = next((s for s in shifts if s.is_active), None)

    return WhoIsOnCallResponse(
        schedule_id=schedule_id,
        schedule_name=schedule.name,
        oncall_user=user,
        is_override=is_override,
        shift_ends_at=current_shift.end_time if current_shift else None,
    )


@router.get("/oncall/all")
async def get_all_oncall(service: OnCallService = Depends(get_service)):
    """Get currently on-call users for all schedules."""
    result = await service.get_all_oncall_now()
    return {
        "schedules": [{"schedule_id": sid, "oncall_user": user} for sid, user in result.items()]
    }


@router.get("/schedules/{schedule_id}/shifts", response_model=UpcomingShiftsResponse)
async def get_upcoming_shifts(
    schedule_id: str,
    days: int = Query(7, ge=1, le=90, description="Number of days to look ahead"),
    service: OnCallService = Depends(get_service),
):
    """Get upcoming shifts for a schedule."""
    schedule = await service.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    shifts = await service.get_upcoming_shifts(schedule_id, days=days)
    return UpcomingShiftsResponse(schedule_id=schedule_id, shifts=shifts, total_count=len(shifts))


@router.get("/schedules/{schedule_id}/visualization", response_model=ScheduleVisualization)
async def get_schedule_visualization(
    schedule_id: str,
    days: int = Query(14, ge=1, le=90, description="Number of days to visualize"),
    service: OnCallService = Depends(get_service),
):
    """Get rotation visualization data for a schedule."""
    viz = await service.get_rotation_visualization(schedule_id, days=days)
    if not viz:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return ScheduleVisualization(**viz)


# === Override Routes ===


@router.get("/overrides", response_model=list[OnCallOverride])
async def list_overrides(
    schedule_id: Optional[str] = Query(None),
    active_only: bool = Query(False),
    service: OnCallService = Depends(get_service),
):
    """List schedule overrides."""
    return await service.list_overrides(schedule_id=schedule_id, active_only=active_only)


@router.post("/schedules/{schedule_id}/overrides", response_model=OnCallOverride)
async def create_override(
    schedule_id: str, request: CreateOverrideRequest, service: OnCallService = Depends(get_service)
):
    """Create a schedule override (temporary handoff)."""
    override_user = OnCallUser(
        id=request.override_user_id,
        name=request.override_user_name,
        email=request.override_user_email,
    )

    try:
        override = await service.create_override(
            schedule_id=schedule_id,
            override_user=override_user,
            start_time=request.start_time,
            end_time=request.end_time,
            reason=request.reason,
        )
        return override
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/overrides/{override_id}")
async def cancel_override(override_id: str, service: OnCallService = Depends(get_service)):
    """Cancel an override."""
    success = await service.cancel_override(override_id)
    if not success:
        raise HTTPException(status_code=404, detail="Override not found")
    return {"status": "cancelled", "override_id": override_id}


# === History Routes ===


@router.get("/history")
async def get_oncall_history(
    schedule_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    service: OnCallService = Depends(get_service),
):
    """Query on-call history."""
    entries = await service.get_history(
        schedule_id=schedule_id, user_id=user_id, since=since, until=until, limit=limit
    )
    return {"entries": entries, "count": len(entries)}


# === Handoff Notification Routes ===


@router.get("/handoffs/pending")
async def get_pending_handoffs(
    lookahead_hours: int = Query(2, ge=1, le=24), service: OnCallService = Depends(get_service)
):
    """Get pending handoff notifications."""
    notifications = await service.get_pending_handoffs(lookahead_hours=lookahead_hours)
    return {"notifications": notifications, "count": len(notifications)}


@router.post("/handoffs/{notification_id}/sent")
async def mark_handoff_sent(notification_id: str, service: OnCallService = Depends(get_service)):
    """Mark a handoff notification as sent."""
    success = await service.mark_handoff_sent(notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "marked_sent", "notification_id": notification_id}
