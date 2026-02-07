"""
Mobile-optimized API routes for incident-copilot.
Lightweight endpoints with pagination, caching, and offline support.
"""

import hashlib
import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse

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
    MobileError,
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


# === Dependency Stubs ===
# Replace with actual implementations

async def get_current_user() -> dict:
    """Get current authenticated user. Stub for demo."""
    return {"id": "user_123", "email": "user@example.com", "name": "Demo User"}


async def get_incident_service():
    """Get incident service. Stub for demo."""
    return MockIncidentService()


class MockIncidentService:
    """Mock incident service for demonstration."""
    
    _incidents = [
        {
            "id": f"inc_{i}",
            "title": f"Database connection timeout #{i}",
            "severity": ["critical", "high", "medium", "low"][i % 4],
            "status": ["open", "acknowledged", "investigating"][i % 3],
            "service": "api-gateway",
            "assignee": "user_123" if i % 2 == 0 else None,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
            "description": "Connection pool exhausted under high load.",
            "labels": ["database", "production"],
            "comment_count": i,
        }
        for i in range(20)
    ]
    
    async def list_incidents(
        self,
        cursor: str | None,
        limit: int,
        status_filter: list[str] | None,
        severity_filter: list[str] | None,
        assignee: str | None,
    ) -> tuple[list[dict], str | None, bool]:
        """List incidents with pagination."""
        start = int(cursor) if cursor else 0
        filtered = self._incidents
        
        if status_filter:
            filtered = [i for i in filtered if i["status"] in status_filter]
        if severity_filter:
            filtered = [i for i in filtered if i["severity"] in severity_filter]
        if assignee:
            filtered = [i for i in filtered if i["assignee"] == assignee]
        
        items = filtered[start:start + limit]
        next_cursor = str(start + limit) if start + limit < len(filtered) else None
        has_more = next_cursor is not None
        
        return items, next_cursor, has_more
    
    async def get_incident(self, incident_id: str) -> dict | None:
        """Get single incident by ID."""
        for inc in self._incidents:
            if inc["id"] == incident_id:
                return inc
        return None
    
    async def update_status(self, incident_id: str, new_status: str, user_id: str) -> bool:
        """Update incident status."""
        for inc in self._incidents:
            if inc["id"] == incident_id:
                inc["status"] = new_status
                inc["ack_by"] = user_id if new_status == "acknowledged" else inc.get("ack_by")
                return True
        return False
    
    async def add_comment(self, incident_id: str, user_id: str, text: str, internal: bool) -> dict:
        """Add comment to incident."""
        return {
            "id": f"comment_{int(time.time())}",
            "text": text,
            "author": user_id,
            "ts": int(time.time()),
            "is_internal": internal,
        }
    
    async def get_dashboard(self, user_id: str) -> dict:
        """Get dashboard summary."""
        return {
            "open_count": 8,
            "ack_count": 3,
            "my_incidents": 2,
            "by_severity": {"critical": 2, "high": 3, "medium": 2, "low": 1},
            "mttr_hours": 2.5,
            "last_incident_ts": int(time.time()) - 3600,
        }


# === Helper Functions ===

def compute_etag(data: list | dict) -> str:
    """Compute ETag for response caching."""
    content = str(data).encode()
    return hashlib.md5(content).hexdigest()[:16]


def make_incident_minimal(inc: dict) -> IncidentMinimal:
    """Convert to minimal incident model."""
    return IncidentMinimal(
        id=inc["id"],
        title=inc["title"][:100],
        severity=Severity(inc["severity"]),
        status=IncidentStatus(inc["status"]),
        ts=int(time.time()),  # Would use actual timestamp
        unread=False,
    )


def make_incident_compact(inc: dict) -> IncidentCompact:
    """Convert to compact incident model."""
    return IncidentCompact(
        id=inc["id"],
        title=inc["title"][:100],
        severity=Severity(inc["severity"]),
        status=IncidentStatus(inc["status"]),
        ts=int(time.time()),
        unread=False,
        service=inc.get("service"),
        assignee=inc.get("assignee"),
        ack_by=inc.get("ack_by"),
        comment_count=inc.get("comment_count", 0),
    )


def make_incident_full(inc: dict) -> IncidentFull:
    """Convert to full incident model."""
    from datetime import datetime
    return IncidentFull(
        id=inc["id"],
        title=inc["title"],
        severity=Severity(inc["severity"]),
        status=IncidentStatus(inc["status"]),
        ts=int(time.time()),
        unread=False,
        service=inc.get("service"),
        assignee=inc.get("assignee"),
        ack_by=inc.get("ack_by"),
        comment_count=inc.get("comment_count", 0),
        description=inc.get("description"),
        created_at=datetime.fromisoformat(inc["created_at"].replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(inc["updated_at"].replace("Z", "+00:00")),
        resolved_at=None,
        labels=inc.get("labels", []),
        runbook_url=inc.get("runbook_url"),
        timeline_count=inc.get("comment_count", 0),
        related_ids=[],
    )


# === Incidents ===

@router.get("/incidents", response_model=IncidentListResponse)
async def list_incidents(
    response: Response,
    cursor: Annotated[str | None, Query(description="Pagination cursor")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    expand: Annotated[Literal["minimal", "compact"] | None, Query()] = None,
    status: Annotated[list[IncidentStatus] | None, Query()] = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
    mine: Annotated[bool, Query(description="Only my incidents")] = False,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """
    List incidents with mobile-optimized pagination.
    
    - **cursor**: Opaque pagination cursor
    - **limit**: Items per page (max 100)
    - **expand**: 'minimal' (default) or 'compact' for more fields
    - **status**: Filter by status(es)
    - **severity**: Filter by severity(ies)
    - **mine**: Only incidents assigned to me
    """
    status_filter = [s.value for s in status] if status else None
    severity_filter = [s.value for s in severity] if severity else None
    assignee = user["id"] if mine else None
    
    incidents, next_cursor, has_more = await service.list_incidents(
        cursor=cursor,
        limit=limit,
        status_filter=status_filter,
        severity_filter=severity_filter,
        assignee=assignee,
    )
    
    # Convert based on expand level
    if expand == "compact":
        items = [make_incident_compact(inc) for inc in incidents]
    else:
        items = [make_incident_minimal(inc) for inc in incidents]
    
    # Compute ETag for caching
    etag = compute_etag(incidents)
    
    # Check for conditional GET (304 Not Modified)
    if if_none_match and if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    
    # Set cache headers
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=30"
    response.headers["Last-Modified"] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    
    return IncidentListResponse(
        items=items,
        meta=PaginationMeta(cursor=next_cursor, has_more=has_more),
        etag=etag,
        last_modified=int(time.time()),
    )


@router.get("/incidents/{incident_id}", response_model=IncidentFull)
async def get_incident(
    incident_id: str,
    response: Response,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """Get full incident details."""
    incident = await service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    etag = compute_etag(incident)
    if if_none_match and if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=10"
    
    return make_incident_full(incident)


# === Quick Actions ===

@router.post("/actions", response_model=QuickActionResponse)
async def quick_action(
    request: QuickActionRequest,
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """
    Execute a quick action on an incident.
    
    Supported actions:
    - **acknowledge**: Mark incident as acknowledged
    - **resolve**: Resolve the incident
    - **escalate**: Escalate to another person/team
    - **comment**: Add a comment
    - **snooze**: Snooze notifications for X minutes
    """
    incident = await service.get_incident(request.incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    new_status = None
    message = None
    
    match request.action:
        case QuickActionType.ACKNOWLEDGE:
            await service.update_status(request.incident_id, "acknowledged", user["id"])
            new_status = IncidentStatus.ACKNOWLEDGED
            message = "Incident acknowledged"
            
        case QuickActionType.RESOLVE:
            await service.update_status(request.incident_id, "resolved", user["id"])
            new_status = IncidentStatus.RESOLVED
            message = "Incident resolved"
            
        case QuickActionType.ESCALATE:
            if not request.escalate_to:
                raise HTTPException(status_code=400, detail="escalateTo required for escalate action")
            # Would trigger escalation logic
            message = f"Escalated to {request.escalate_to}"
            
        case QuickActionType.COMMENT:
            if not request.message:
                raise HTTPException(status_code=400, detail="message required for comment action")
            await service.add_comment(request.incident_id, user["id"], request.message, False)
            message = "Comment added"
            
        case QuickActionType.SNOOZE:
            if not request.snooze_minutes:
                raise HTTPException(status_code=400, detail="snoozeMinutes required for snooze action")
            message = f"Snoozed for {request.snooze_minutes} minutes"
    
    # Send push notification to other subscribers
    push_service = get_push_service()
    await push_service.broadcast_incident(
        incident_id=request.incident_id,
        title=f"Incident {request.action.value}d",
        body=f"{user['name']} {request.action.value}d: {incident['title'][:50]}",
        severity=Severity(incident["severity"]),
        user_ids=None,  # Would filter to relevant users
    )
    
    return QuickActionResponse(
        success=True,
        incident_id=request.incident_id,
        new_status=new_status,
        message=message,
        ts=int(time.time()),
    )


@router.post("/actions/bulk", response_model=BulkActionResponse)
async def bulk_action(
    request: BulkActionRequest,
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """Execute an action on multiple incidents."""
    succeeded = []
    failed = []
    
    for inc_id in request.incident_ids:
        try:
            incident = await service.get_incident(inc_id)
            if not incident:
                failed.append({"id": inc_id, "error": "Not found"})
                continue
            
            match request.action:
                case QuickActionType.ACKNOWLEDGE:
                    await service.update_status(inc_id, "acknowledged", user["id"])
                case QuickActionType.RESOLVE:
                    await service.update_status(inc_id, "resolved", user["id"])
                case _:
                    failed.append({"id": inc_id, "error": "Action not supported for bulk"})
                    continue
            
            succeeded.append(inc_id)
            
        except Exception as e:
            failed.append({"id": inc_id, "error": str(e)})
    
    return BulkActionResponse(succeeded=succeeded, failed=failed)


# === Comments ===

@router.post("/incidents/{incident_id}/comments", response_model=CommentMinimal, status_code=201)
async def add_comment(
    incident_id: str,
    comment: CommentCreate,
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """Add a comment to an incident."""
    incident = await service.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    result = await service.add_comment(
        incident_id, 
        user["id"], 
        comment.text, 
        comment.is_internal,
    )
    
    return CommentMinimal(
        id=result["id"],
        text=result["text"],
        author=user["name"],
        ts=result["ts"],
        is_internal=result["is_internal"],
    )


# === Dashboard ===

@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(
    response: Response,
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """
    Get mobile dashboard summary.
    Lightweight endpoint for home screen widgets.
    """
    data = await service.get_dashboard(user["id"])
    
    response.headers["Cache-Control"] = "private, max-age=60"
    
    return DashboardSummary(
        open_count=data["open_count"],
        ack_count=data["ack_count"],
        my_incidents=data["my_incidents"],
        by_severity=SeverityCount(**data["by_severity"]),
        mttr_hours=data.get("mttr_hours"),
        last_incident_ts=data.get("last_incident_ts"),
        ts=int(time.time()),
    )


# === Push Notifications ===

@router.post("/devices", response_model=DeviceRegistrationResponse, status_code=201)
async def register_device(
    registration: DeviceRegistration,
    user: dict = Depends(get_current_user),
):
    """Register a device for push notifications."""
    push_service = get_push_service()
    success = await push_service.register_device(user["id"], registration)
    
    return DeviceRegistrationResponse(
        success=success,
        device_id=registration.device_id,
        expires_at=int(time.time()) + 86400 * 30,  # 30 days
    )


@router.delete("/devices/{device_id}", status_code=204)
async def unregister_device(
    device_id: str,
    user: dict = Depends(get_current_user),
):
    """Unregister a device from push notifications."""
    push_service = get_push_service()
    await push_service.unregister_device(device_id)
    return Response(status_code=204)


@router.put("/devices/{device_id}/preferences", response_model=NotificationPreferences)
async def update_notification_preferences(
    device_id: str,
    preferences: NotificationPreferences,
    user: dict = Depends(get_current_user),
):
    """Update notification preferences for a device."""
    # Would persist to database
    return preferences


# === Auth ===

@router.post("/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(request: TokenRefreshRequest):
    """
    Refresh access token using refresh token.
    Mobile-optimized with biometric hint.
    """
    # Validate refresh token (stub)
    # In production: verify JWT, check revocation, etc.
    
    return TokenRefreshResponse(
        access_token=f"new_access_token_{int(time.time())}",
        refresh_token=f"new_refresh_token_{int(time.time())}",
        expires_in=3600,
        biometric_hint=True,  # Suggest biometric for next auth
    )


@router.post("/auth/biometric", response_model=TokenRefreshResponse)
async def biometric_auth(request: BiometricAuthRequest):
    """
    Authenticate using biometric challenge-response.
    Device signs a server challenge with secure enclave.
    """
    # Verify signature against stored public key
    # In production: validate challenge, verify signature
    
    return TokenRefreshResponse(
        access_token=f"biometric_access_token_{int(time.time())}",
        refresh_token=f"biometric_refresh_token_{int(time.time())}",
        expires_in=3600,
        biometric_hint=True,
    )


# === Offline Support ===

@router.post("/sync/check", response_model=SyncCheckResponse)
async def check_sync(
    request: SyncCheckRequest,
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """
    Check for updates since last sync.
    Returns list of changed/deleted incident IDs.
    """
    # Would query database for changes since last_sync
    # This is a stub returning mock data
    
    has_updates = time.time() - request.last_sync > 60  # Updates if > 1 min
    
    return SyncCheckResponse(
        has_updates=has_updates,
        updated_ids=["inc_0", "inc_1"] if has_updates else [],
        deleted_ids=[],
        server_ts=int(time.time()),
    )


@router.get("/sync/batch")
async def get_incidents_batch(
    ids: Annotated[list[str], Query(description="Incident IDs to fetch")],
    user: dict = Depends(get_current_user),
    service = Depends(get_incident_service),
):
    """
    Fetch multiple incidents in a single request.
    Optimized for offline sync.
    """
    if len(ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 IDs per request")
    
    incidents = []
    for inc_id in ids:
        inc = await service.get_incident(inc_id)
        if inc:
            incidents.append(make_incident_full(inc))
    
    return {"items": incidents, "ts": int(time.time())}


# === Health ===

@router.get("/health")
async def health_check():
    """Mobile API health check."""
    return {
        "status": "ok",
        "ts": int(time.time()),
        "version": "1.0.0",
    }
