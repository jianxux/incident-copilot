"""
Change Tracking Routes - FastAPI endpoints for change queries.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .models import (
    ChangeCorrelation,
    ChangeEvent,
    ChangeFreeze,
    ChangeSource,
    ChangeTimeline,
    ChangeType,
)
from .service import ChangeTrackingService, get_change_service

router = APIRouter(prefix="/changes", tags=["changes"])


# ========== Request/Response Models ==========


class RecentChangesRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    environment: str | None = None
    service: str | None = None
    types: list[ChangeType] | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CorrelateRequest(BaseModel):
    incident_id: str
    incident_started_at: datetime
    window_minutes: int = Field(default=60, ge=5, le=360)
    service: str | None = None
    environment: str = "production"


class CreateFreezeRequest(BaseModel):
    id: str
    name: str
    reason: str
    start_time: datetime
    end_time: datetime
    environments: list[str] = Field(default_factory=lambda: ["production"])
    services: list[str] = Field(default_factory=list)
    allowed_change_types: list[ChangeType] = Field(default_factory=list)
    exception_approvers: list[str] = Field(default_factory=list)
    created_by: str


class TimelineRequest(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    environment: str | None = None
    services: list[str] | None = None


class ChangeStatsResponse(BaseModel):
    total: int
    by_type: dict[str, int]
    by_source: dict[str, int]
    by_status: dict[str, int]
    by_risk: dict[str, int]
    rollbacks: int
    freeze_violations: int
    avg_impact_score: float


# ========== Dependency ==========


def get_service() -> ChangeTrackingService:
    return get_change_service()


# ========== Routes ==========


@router.get("/recent", response_model=list[ChangeEvent])
async def get_recent_changes(
    hours: int = Query(default=24, ge=1, le=168),
    environment: str | None = None,
    service: str | None = None,
    change_type: ChangeType | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    svc: ChangeTrackingService = Depends(get_service),
) -> list[ChangeEvent]:
    """Get recent changes within a time window."""
    types = [change_type] if change_type else None

    return await svc.get_recent_changes(
        hours=hours,
        environment=environment,
        service=service,
        change_types=types,
        limit=limit,
    )


@router.post("/recent", response_model=list[ChangeEvent])
async def query_recent_changes(
    request: RecentChangesRequest, svc: ChangeTrackingService = Depends(get_service)
) -> list[ChangeEvent]:
    """Query recent changes with filters."""
    return await svc.get_recent_changes(
        hours=request.hours,
        environment=request.environment,
        service=request.service,
        change_types=request.types,
        limit=request.limit,
    )


@router.get("/{change_id}", response_model=ChangeEvent)
async def get_change(
    change_id: str, svc: ChangeTrackingService = Depends(get_service)
) -> ChangeEvent:
    """Get a specific change by ID."""
    change = await svc.get_change(change_id)
    if not change:
        raise HTTPException(status_code=404, detail="Change not found")
    return change


@router.post("/correlate", response_model=ChangeCorrelation)
async def correlate_changes(
    request: CorrelateRequest, svc: ChangeTrackingService = Depends(get_service)
) -> ChangeCorrelation:
    """
    Find changes that might have caused an incident.

    Looks for changes in a time window before the incident started
    and scores them by likelihood of being the cause.
    """
    return await svc.correlate_changes(
        incident_id=request.incident_id,
        incident_started_at=request.incident_started_at,
        window_minutes=request.window_minutes,
        service=request.service,
        environment=request.environment,
    )


@router.get("/correlate/{incident_id}", response_model=ChangeCorrelation)
async def correlate_incident(
    incident_id: str,
    incident_time: datetime = Query(...),
    window_minutes: int = Query(default=60, ge=5, le=360),
    service: str | None = None,
    environment: str = "production",
    svc: ChangeTrackingService = Depends(get_service),
) -> ChangeCorrelation:
    """Find changes that might have caused an incident (GET version)."""
    return await svc.correlate_changes(
        incident_id=incident_id,
        incident_started_at=incident_time,
        window_minutes=window_minutes,
        service=service,
        environment=environment,
    )


# ========== Rollbacks ==========


@router.get("/rollbacks/recent", response_model=list[ChangeEvent])
async def get_recent_rollbacks(
    hours: int = Query(default=24, ge=1, le=168),
    environment: str | None = None,
    svc: ChangeTrackingService = Depends(get_service),
) -> list[ChangeEvent]:
    """Get recent rollback events."""
    return await svc.get_rollbacks(hours=hours, environment=environment)


# ========== Change Freezes ==========


@router.get("/freezes/active", response_model=list[ChangeFreeze])
async def get_active_freezes(
    environment: str | None = None, svc: ChangeTrackingService = Depends(get_service)
) -> list[ChangeFreeze]:
    """Get currently active change freezes."""
    return await svc.get_active_freezes(environment=environment)


@router.post("/freezes", response_model=ChangeFreeze)
async def create_freeze(
    request: CreateFreezeRequest, svc: ChangeTrackingService = Depends(get_service)
) -> ChangeFreeze:
    """Create a new change freeze period."""
    freeze = ChangeFreeze(
        id=request.id,
        name=request.name,
        reason=request.reason,
        start_time=request.start_time,
        end_time=request.end_time,
        environments=request.environments,
        services=request.services,
        allowed_change_types=request.allowed_change_types,
        exception_approvers=request.exception_approvers,
        created_by=request.created_by,
    )
    return await svc.create_freeze(freeze)


@router.delete("/freezes/{freeze_id}", response_model=ChangeFreeze)
async def end_freeze(
    freeze_id: str, svc: ChangeTrackingService = Depends(get_service)
) -> ChangeFreeze:
    """End a change freeze early."""
    freeze = await svc.end_freeze(freeze_id)
    if not freeze:
        raise HTTPException(status_code=404, detail="Freeze not found")
    return freeze


@router.post("/freezes/check")
async def check_freeze_violation(
    change: ChangeEvent, svc: ChangeTrackingService = Depends(get_service)
) -> dict:
    """Check if a change would violate any active freeze."""
    violation = await svc.check_freeze_violation(change)
    return {"blocked": violation is not None, "freeze": violation}


# ========== Timeline ==========


@router.get("/timeline", response_model=ChangeTimeline)
async def get_timeline(
    hours: int = Query(default=24, ge=1, le=168),
    environment: str | None = None,
    svc: ChangeTrackingService = Depends(get_service),
) -> ChangeTimeline:
    """Get a change timeline for visualization."""
    return await svc.get_timeline(hours=hours, environment=environment)


@router.post("/timeline", response_model=ChangeTimeline)
async def query_timeline(
    request: TimelineRequest, svc: ChangeTrackingService = Depends(get_service)
) -> ChangeTimeline:
    """Get a change timeline with filters."""
    return await svc.get_timeline(
        hours=request.hours, environment=request.environment, services=request.services
    )


# ========== Statistics ==========


@router.get("/stats", response_model=ChangeStatsResponse)
async def get_change_stats(
    hours: int = Query(default=24, ge=1, le=168),
    environment: str | None = None,
    svc: ChangeTrackingService = Depends(get_service),
) -> ChangeStatsResponse:
    """Get statistics about recent changes."""
    stats = await svc.get_change_stats(hours=hours, environment=environment)
    return ChangeStatsResponse(**stats)


# ========== Collection ==========


@router.post("/collect")
async def trigger_collection(
    hours: int = Query(default=24, ge=1, le=168),
    svc: ChangeTrackingService = Depends(get_service),
) -> dict:
    """Trigger collection from all registered sources."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    changes = await svc.collect_all(since=since)

    return {
        "collected": len(changes),
        "by_source": {
            source.value: sum(1 for c in changes if c.source == source)
            for source in ChangeSource
            if any(c.source == source for c in changes)
        },
    }


# ========== Health ==========


@router.get("/health")
async def health_check(svc: ChangeTrackingService = Depends(get_service)) -> dict:
    """Health check for the change tracking service."""
    collectors = list(svc._collectors.keys())

    return {
        "status": "healthy",
        "collectors": [c.value for c in collectors],
        "collector_count": len(collectors),
    }
