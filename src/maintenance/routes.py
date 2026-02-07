"""Maintenance Windows - FastAPI Routes"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from .models import (
    ExtendMaintenanceRequest,
    MaintenanceStatus,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
    OverlapWarning,
    ScopeType,
)
from .scheduler import MaintenanceScheduler
from .service import MaintenanceService, get_maintenance_service

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class MaintenanceCheckResponse(BaseModel):
    in_maintenance: bool
    window: Optional[MaintenanceWindow] = None
    message: str


class UpcomingResponse(BaseModel):
    windows: list[MaintenanceWindow]
    next_maintenance: Optional[datetime] = None


class OverlapResponse(BaseModel):
    has_overlaps: bool
    overlaps: list[OverlapWarning]


class ApprovalRequest(BaseModel):
    approver_id: str
    comment: Optional[str] = None


class RejectRequest(BaseModel):
    approver_id: str
    reason: str


class CancelRequest(BaseModel):
    reason: str


async def get_svc() -> MaintenanceService:
    return get_maintenance_service()


@router.post("", response_model=MaintenanceWindow, status_code=201)
async def create_window(
    request: MaintenanceWindowCreate,
    created_by: str = Query(...),
    svc: MaintenanceService = Depends(get_svc),
):
    try:
        return await svc.create_window(request, created_by)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[MaintenanceWindow])
async def list_windows(
    status: Optional[MaintenanceStatus] = None,
    scope_type: Optional[ScopeType] = None,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=200),
    svc: MaintenanceService = Depends(get_svc),
):
    return await svc.list_windows(status, scope_type, from_time, to_time, limit)


@router.get("/active", response_model=list[MaintenanceWindow])
async def get_active(
    at_time: Optional[datetime] = None, svc: MaintenanceService = Depends(get_svc)
):
    return await svc.get_active_windows(at_time)


@router.get("/upcoming", response_model=UpcomingResponse)
async def get_upcoming(
    hours: int = Query(24, ge=1, le=168), svc: MaintenanceService = Depends(get_svc)
):
    windows = await svc.get_upcoming_windows(hours)
    return UpcomingResponse(
        windows=windows,
        next_maintenance=windows[0].schedule.start_time if windows else None,
    )


@router.get("/{window_id}", response_model=MaintenanceWindow)
async def get_window(window_id: UUID, svc: MaintenanceService = Depends(get_svc)):
    window = await svc.get_window(window_id)
    if not window:
        raise HTTPException(404, "Not found")
    return window


@router.patch("/{window_id}", response_model=MaintenanceWindow)
async def update_window(
    window_id: UUID,
    request: MaintenanceWindowUpdate,
    svc: MaintenanceService = Depends(get_svc),
):
    try:
        window = await svc.update_window(window_id, request)
        if not window:
            raise HTTPException(404, "Not found")
        return window
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{window_id}", status_code=204)
async def delete_window(window_id: UUID, svc: MaintenanceService = Depends(get_svc)):
    try:
        if not await svc.delete_window(window_id):
            raise HTTPException(404, "Not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/check/{scope_type}/{identifier}", response_model=MaintenanceCheckResponse)
async def check_status(
    scope_type: ScopeType,
    identifier: str,
    at_time: Optional[datetime] = None,
    svc: MaintenanceService = Depends(get_svc),
):
    in_maint, window = await svc.is_in_maintenance(scope_type, identifier, at_time)
    msg = (
        f"{identifier} in maintenance: {window.title}"
        if in_maint and window
        else f"{identifier} not in maintenance"
    )
    return MaintenanceCheckResponse(in_maintenance=in_maint, window=window, message=msg)


@router.post("/check/alerts")
async def check_alerts(
    alerts: list[dict],
    at_time: Optional[datetime] = None,
    svc: MaintenanceService = Depends(get_svc),
):
    return await svc.suppress_alerts(alerts, at_time)


@router.post("/{window_id}/approve", response_model=MaintenanceWindow)
async def approve(
    window_id: UUID, req: ApprovalRequest, svc: MaintenanceService = Depends(get_svc)
):
    try:
        return await svc.approve(window_id, req.approver_id, req.comment)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{window_id}/reject", response_model=MaintenanceWindow)
async def reject(
    window_id: UUID, req: RejectRequest, svc: MaintenanceService = Depends(get_svc)
):
    try:
        return await svc.reject(window_id, req.approver_id, req.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{window_id}/start", response_model=MaintenanceWindow)
async def start(window_id: UUID, svc: MaintenanceService = Depends(get_svc)):
    try:
        return await svc.start_maintenance(window_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{window_id}/complete", response_model=MaintenanceWindow)
async def complete(window_id: UUID, svc: MaintenanceService = Depends(get_svc)):
    try:
        return await svc.complete_maintenance(window_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{window_id}/cancel", response_model=MaintenanceWindow)
async def cancel(
    window_id: UUID, req: CancelRequest, svc: MaintenanceService = Depends(get_svc)
):
    try:
        return await svc.cancel_maintenance(window_id, req.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{window_id}/extend", response_model=MaintenanceWindow)
async def extend(
    window_id: UUID,
    req: ExtendMaintenanceRequest,
    svc: MaintenanceService = Depends(get_svc),
):
    try:
        return await svc.extend_maintenance(window_id, req)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{window_id}/check-overlaps", response_model=OverlapResponse)
async def check_overlaps(window_id: UUID, svc: MaintenanceService = Depends(get_svc)):
    window = await svc.get_window(window_id)
    if not window:
        raise HTTPException(404, "Not found")
    overlaps = await svc.detect_overlaps(window)
    return OverlapResponse(has_overlaps=bool(overlaps), overlaps=overlaps)


@router.get("/calendar/ical")
async def export_calendar(
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    scope_type: Optional[ScopeType] = None,
    svc: MaintenanceService = Depends(get_svc),
):
    windows = await svc.list_windows(
        from_time=from_time or datetime.utcnow(),
        to_time=to_time or datetime.utcnow() + timedelta(days=30),
        scope_type=scope_type,
    )
    return Response(
        MaintenanceScheduler().generate_ical_calendar(windows),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=maintenance.ics"},
    )


@router.get("/{window_id}/ical")
async def export_window_ical(
    window_id: UUID, svc: MaintenanceService = Depends(get_svc)
):
    window = await svc.get_window(window_id)
    if not window:
        raise HTTPException(404, "Not found")
    return Response(
        MaintenanceScheduler().generate_ical_calendar([window]),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f"attachment; filename=maintenance-{window_id}.ics"
        },
    )


@router.post("/annotate-incident")
async def annotate(
    incident_id: str = Query(...),
    scope_type: ScopeType = Query(...),
    identifier: str = Query(...),
    svc: MaintenanceService = Depends(get_svc),
):
    annotation = await svc.annotate_incident(incident_id, scope_type, identifier)
    return (
        {"annotated": bool(annotation), "annotation": annotation}
        if annotation
        else {"annotated": False}
    )


@router.post("/process-scheduled", response_model=list[MaintenanceWindow])
async def process_scheduled(svc: MaintenanceService = Depends(get_svc)):
    return await svc.process_scheduled_windows()
