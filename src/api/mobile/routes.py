"""Mobile-optimized API routes with pagination, caching, and offline support."""

import hashlib
import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from .models import (
    BiometricAuthRequest,
    BulkActionRequest,
    BulkActionResponse,
    CommentCreate,
    CommentMinimal,
    DashboardSummary,
    DeviceRegistration,
    DeviceRegistrationResponse,
    IncidentCompact,
    IncidentFull,
    IncidentListResponse,
    IncidentMinimal,
    IncidentStatus,
    NotificationPreferences,
    PaginationMeta,
    QuickActionRequest,
    QuickActionResponse,
    QuickActionType,
    Severity,
    SeverityCount,
    SyncCheckRequest,
    SyncCheckResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
)
from .push import PushPayload, get_push_service

router = APIRouter(prefix="/mobile/v1", tags=["mobile"])


# === Stubs (replace with real implementations) ===


async def get_current_user() -> dict:
    return {"id": "user_123", "name": "Demo User"}


class MockIncidentService:
    _incidents = [
        {
            "id": f"inc_{i}",
            "title": f"Database timeout #{i}",
            "severity": ["critical", "high", "medium", "low"][i % 4],
            "status": ["open", "acknowledged"][i % 2],
            "service": "api",
            "assignee": "user_123" if i % 2 == 0 else None,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
            "comment_count": i,
        }
        for i in range(20)
    ]

    async def list_incidents(
        self,
        cursor: str | None,
        limit: int,
        status_filter: list | None,
        severity_filter: list | None,
        assignee: str | None,
    ):
        start = int(cursor) if cursor else 0
        filtered = [
            i
            for i in self._incidents
            if (not status_filter or i["status"] in status_filter)
            and (not severity_filter or i["severity"] in severity_filter)
            and (not assignee or i["assignee"] == assignee)
        ]
        items = filtered[start : start + limit]
        return (
            items,
            str(start + limit) if start + limit < len(filtered) else None,
            start + limit < len(filtered),
        )

    async def get_incident(self, incident_id: str):
        return next((i for i in self._incidents if i["id"] == incident_id), None)

    async def update_status(self, incident_id: str, new_status: str, user_id: str):
        for inc in self._incidents:
            if inc["id"] == incident_id:
                inc["status"] = new_status
                return True
        return False

    async def add_comment(
        self, incident_id: str, user_id: str, text: str, internal: bool
    ):
        return {
            "id": f"c_{int(time.time())}",
            "text": text,
            "author": user_id,
            "ts": int(time.time()),
            "is_internal": internal,
        }

    async def get_dashboard(self, user_id: str):
        return {
            "open_count": 8,
            "ack_count": 3,
            "my_incidents": 2,
            "by_severity": {"critical": 2, "high": 3, "medium": 2, "low": 1},
            "mttr_hours": 2.5,
        }


async def get_service():
    return MockIncidentService()


def compute_etag(data) -> str:
    return hashlib.md5(str(data).encode(), usedforsecurity=False).hexdigest()[:16]


def to_minimal(inc: dict) -> IncidentMinimal:
    return IncidentMinimal(
        id=inc["id"],
        title=inc["title"][:100],
        severity=Severity(inc["severity"]),
        status=IncidentStatus(inc["status"]),
        ts=int(time.time()),
    )


def to_compact(inc: dict) -> IncidentCompact:
    return IncidentCompact(
        id=inc["id"],
        title=inc["title"][:100],
        severity=Severity(inc["severity"]),
        status=IncidentStatus(inc["status"]),
        ts=int(time.time()),
        service=inc.get("service"),
        assignee=inc.get("assignee"),
        comment_count=inc.get("comment_count", 0),
    )


def to_full(inc: dict) -> IncidentFull:
    return IncidentFull(
        id=inc["id"],
        title=inc["title"],
        severity=Severity(inc["severity"]),
        status=IncidentStatus(inc["status"]),
        ts=int(time.time()),
        service=inc.get("service"),
        created_at=datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(inc["updated_at"].replace("Z", "+00:00")),
    )


# === Endpoints ===


@router.get("/incidents", response_model=IncidentListResponse)
async def list_incidents(
    response: Response,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    expand: Literal["minimal", "compact"] | None = None,
    status: list[IncidentStatus] | None = Query(None),
    severity: list[Severity] | None = Query(None),
    mine: bool = False,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    user: dict = Depends(get_current_user),
    svc=Depends(get_service),
):
    """List incidents with pagination and caching."""
    incidents, next_cursor, has_more = await svc.list_incidents(
        cursor,
        limit,
        [s.value for s in status] if status else None,
        [s.value for s in severity] if severity else None,
        user["id"] if mine else None,
    )

    etag = compute_etag(incidents)
    if if_none_match == etag:
        return Response(status_code=304)

    items = (
        [to_compact(i) for i in incidents]
        if expand == "compact"
        else [to_minimal(i) for i in incidents]
    )
    response.headers.update({"ETag": etag, "Cache-Control": "private, max-age=30"})
    return IncidentListResponse(
        items=items,
        meta=PaginationMeta(cursor=next_cursor, has_more=has_more),
        etag=etag,
    )


@router.get("/incidents/{incident_id}", response_model=IncidentFull)
async def get_incident(incident_id: str, response: Response, svc=Depends(get_service)):
    """Get full incident details."""
    inc = await svc.get_incident(incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    response.headers["Cache-Control"] = "private, max-age=10"
    return to_full(inc)


@router.post("/actions", response_model=QuickActionResponse)
async def quick_action(
    req: QuickActionRequest,
    user: dict = Depends(get_current_user),
    svc=Depends(get_service),
):
    """Execute quick action: acknowledge, resolve, escalate, comment, snooze."""
    inc = await svc.get_incident(req.incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")

    new_status, msg = None, None
    if req.action == QuickActionType.ACKNOWLEDGE:
        await svc.update_status(req.incident_id, "acknowledged", user["id"])
        new_status, msg = IncidentStatus.ACKNOWLEDGED, "Acknowledged"
    elif req.action == QuickActionType.RESOLVE:
        await svc.update_status(req.incident_id, "resolved", user["id"])
        new_status, msg = IncidentStatus.RESOLVED, "Resolved"
    elif req.action == QuickActionType.ESCALATE:
        if not req.escalate_to:
            raise HTTPException(400, "escalateTo required")
        msg = f"Escalated to {req.escalate_to}"
    elif req.action == QuickActionType.COMMENT:
        if not req.message:
            raise HTTPException(400, "message required")
        await svc.add_comment(req.incident_id, user["id"], req.message, False)
        msg = "Comment added"
    elif req.action == QuickActionType.SNOOZE:
        msg = f"Snoozed {req.snooze_minutes}m"

    return QuickActionResponse(
        success=True,
        incident_id=req.incident_id,
        new_status=new_status,
        message=msg,
        ts=int(time.time()),
    )


@router.post("/actions/bulk", response_model=BulkActionResponse)
async def bulk_action(
    req: BulkActionRequest,
    user: dict = Depends(get_current_user),
    svc=Depends(get_service),
):
    """Bulk action on multiple incidents."""
    succeeded, failed = [], []
    for iid in req.incident_ids:
        inc = await svc.get_incident(iid)
        if not inc:
            failed.append({"id": iid, "error": "Not found"})
            continue
        if req.action in (QuickActionType.ACKNOWLEDGE, QuickActionType.RESOLVE):
            await svc.update_status(iid, req.action.value + "d", user["id"])
            succeeded.append(iid)
        else:
            failed.append({"id": iid, "error": "Unsupported for bulk"})
    return BulkActionResponse(succeeded=succeeded, failed=failed)


@router.post(
    "/incidents/{incident_id}/comments", response_model=CommentMinimal, status_code=201
)
async def add_comment(
    incident_id: str,
    comment: CommentCreate,
    user: dict = Depends(get_current_user),
    svc=Depends(get_service),
):
    """Add comment to incident."""
    if not await svc.get_incident(incident_id):
        raise HTTPException(404, "Incident not found")
    r = await svc.add_comment(
        incident_id, user["id"], comment.text, comment.is_internal
    )
    return CommentMinimal(
        id=r["id"],
        text=r["text"],
        author=user["name"],
        ts=r["ts"],
        is_internal=r["is_internal"],
    )


@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(
    response: Response, user: dict = Depends(get_current_user), svc=Depends(get_service)
):
    """Mobile dashboard summary."""
    d = await svc.get_dashboard(user["id"])
    response.headers["Cache-Control"] = "private, max-age=60"
    return DashboardSummary(
        open_count=d["open_count"],
        ack_count=d["ack_count"],
        my_incidents=d["my_incidents"],
        by_severity=SeverityCount(**d["by_severity"]),
        mttr_hours=d.get("mttr_hours"),
        ts=int(time.time()),
    )


# === Push Notifications ===


@router.post("/devices", response_model=DeviceRegistrationResponse, status_code=201)
async def register_device(
    reg: DeviceRegistration, user: dict = Depends(get_current_user)
):
    """Register device for push notifications."""
    await get_push_service().register_device(user["id"], reg)
    return DeviceRegistrationResponse(
        success=True, device_id=reg.device_id, expires_at=int(time.time()) + 86400 * 30
    )


@router.delete("/devices/{device_id}", status_code=204)
async def unregister_device(device_id: str):
    """Unregister device."""
    await get_push_service().unregister_device(device_id)


@router.put("/devices/{device_id}/preferences", response_model=NotificationPreferences)
async def update_preferences(device_id: str, prefs: NotificationPreferences):
    """Update notification preferences."""
    return prefs


# === Auth ===


@router.post("/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(req: TokenRefreshRequest):
    """Refresh access token."""
    return TokenRefreshResponse(
        access_token=f"at_{int(time.time())}",
        refresh_token=f"rt_{int(time.time())}",
        expires_in=3600,
        biometric_hint=True,
    )


@router.post("/auth/biometric", response_model=TokenRefreshResponse)
async def biometric_auth(req: BiometricAuthRequest):
    """Biometric auth challenge-response."""
    return TokenRefreshResponse(
        access_token=f"bio_{int(time.time())}",
        refresh_token=f"brt_{int(time.time())}",
        expires_in=3600,
        biometric_hint=True,
    )


# === Sync ===


@router.post("/sync/check", response_model=SyncCheckResponse)
async def check_sync(req: SyncCheckRequest):
    """Check for updates since last sync."""
    has_updates = time.time() - req.last_sync > 60
    return SyncCheckResponse(
        has_updates=has_updates,
        updated_ids=["inc_0"] if has_updates else [],
        deleted_ids=[],
        server_ts=int(time.time()),
    )


@router.get("/sync/batch")
async def get_batch(ids: Annotated[list[str], Query()], svc=Depends(get_service)):
    """Fetch multiple incidents for offline sync."""
    if len(ids) > 50:
        raise HTTPException(400, "Max 50 IDs")
    return {
        "items": [to_full(i) for iid in ids if (i := await svc.get_incident(iid))],
        "ts": int(time.time()),
    }


@router.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "ts": int(time.time()), "version": "1.0.0"}
