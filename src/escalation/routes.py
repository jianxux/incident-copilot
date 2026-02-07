"""
Escalation Routes - FastAPI endpoints for escalation management.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from .engine import PolicyEngine, get_policy_engine
from .models import (
    CreatePolicyRequest,
    EscalationHistoryEntry,
    EscalationPolicy,
    EscalationState,
    EscalationStatus,
    OnCallAssignment,
    OverrideEscalationRequest,
    Severity,
    TeamRotation,
    TriggerEscalationRequest,
    UpdatePolicyRequest,
)
from .scheduler import EscalationScheduler, get_scheduler
from .service import EscalationService, get_escalation_service

router = APIRouter(prefix="/escalation", tags=["escalation"])


# Dependency injection
def get_service() -> EscalationService:
    return get_escalation_service()


def get_engine() -> PolicyEngine:
    return get_policy_engine()


def get_sched() -> EscalationScheduler:
    return get_scheduler()


# Response models
class PolicyListResponse(BaseModel):
    policies: list[EscalationPolicy]
    total: int


class HistoryListResponse(BaseModel):
    entries: list[EscalationHistoryEntry]
    total: int


class StatusResponse(BaseModel):
    status: str
    message: str
    data: dict[str, Any] | None = None


# Policy CRUD endpoints
@router.post("/policies", response_model=EscalationPolicy, status_code=201)
async def create_policy(
    request: CreatePolicyRequest,
    service: EscalationService = Depends(get_service),
):
    """Create a new escalation policy."""
    policy = EscalationPolicy(
        name=request.name,
        description=request.description,
        services=request.services,
        severities=request.severities,
        conditions=request.conditions,
        levels=request.levels,
        deescalation_rules=request.deescalation_rules,
        priority=request.priority,
        repeat_enabled=request.repeat_enabled,
        repeat_delay_minutes=request.repeat_delay_minutes,
        max_repeats=request.max_repeats,
        tags=request.tags,
    )
    return await service.create_policy(policy)


@router.get("/policies", response_model=PolicyListResponse)
async def list_policies(
    enabled_only: bool = Query(False, description="Only return enabled policies"),
    service_filter: str | None = Query(None, alias="service"),
    severity: Severity | None = None,
    tags: list[str] | None = Query(None),
    service: EscalationService = Depends(get_service),
):
    """List all escalation policies with optional filters."""
    policies = await service.list_policies(
        enabled_only=enabled_only,
        service=service_filter,
        severity=severity,
        tags=tags,
    )
    return PolicyListResponse(policies=policies, total=len(policies))


@router.get("/policies/{policy_id}", response_model=EscalationPolicy)
async def get_policy(
    policy_id: UUID,
    service: EscalationService = Depends(get_service),
):
    """Get a specific escalation policy."""
    policy = await service.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.patch("/policies/{policy_id}", response_model=EscalationPolicy)
async def update_policy(
    policy_id: UUID,
    request: UpdatePolicyRequest,
    service: EscalationService = Depends(get_service),
):
    """Update an escalation policy."""
    updates = request.model_dump(exclude_unset=True)
    policy = await service.update_policy(policy_id, updates)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.delete("/policies/{policy_id}", response_model=StatusResponse)
async def delete_policy(
    policy_id: UUID,
    service: EscalationService = Depends(get_service),
):
    """Delete an escalation policy."""
    deleted = await service.delete_policy(policy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy not found")
    return StatusResponse(status="success", message="Policy deleted")


@router.post("/policies/{policy_id}/enable", response_model=EscalationPolicy)
async def enable_policy(
    policy_id: UUID,
    service: EscalationService = Depends(get_service),
):
    """Enable an escalation policy."""
    policy = await service.update_policy(policy_id, {"enabled": True})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.post("/policies/{policy_id}/disable", response_model=EscalationPolicy)
async def disable_policy(
    policy_id: UUID,
    service: EscalationService = Depends(get_service),
):
    """Disable an escalation policy."""
    policy = await service.update_policy(policy_id, {"enabled": False})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


# Escalation trigger endpoints
@router.post("/trigger", response_model=EscalationState)
async def trigger_escalation(
    request: TriggerEscalationRequest,
    background_tasks: BackgroundTasks,
    service: EscalationService = Depends(get_service),
    engine: PolicyEngine = Depends(get_engine),
):
    """Manually trigger escalation for an incident."""
    # Get or find policy
    if request.policy_id:
        policy = await service.get_policy(request.policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
    else:
        # Find matching policy based on incident context
        context = {"incident_id": request.incident_id}
        policy = await engine.evaluate_incident(request.incident_id, context)
        if not policy:
            raise HTTPException(
                status_code=400, detail="No matching policy found for incident"
            )

    # Start or get existing escalation
    state = await service.get_escalation_state(request.incident_id)
    if not state:
        state = await service.start_escalation(request.incident_id, policy)

    # If target level specified, escalate to that level
    if request.target_level:
        state = await service.escalate(request.incident_id, request)

    # Execute escalation in background
    if state:
        context = {
            "incident_id": request.incident_id,
            "reason": request.reason,
            "skip_conditions": request.skip_conditions,
        }
        background_tasks.add_task(engine.execute_escalation, state, context)

    return state


@router.post("/override", response_model=EscalationState)
async def override_escalation(
    request: OverrideEscalationRequest,
    service: EscalationService = Depends(get_service),
):
    """Override, skip, pause, or resume escalation."""
    state = await service.override_escalation(request)
    if not state:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return state


@router.post("/acknowledge/{incident_id}", response_model=EscalationState)
async def acknowledge_escalation(
    incident_id: str,
    acknowledged_by: str = Query(..., description="User acknowledging"),
    service: EscalationService = Depends(get_service),
):
    """Acknowledge an escalation."""
    state = await service.acknowledge(incident_id, acknowledged_by)
    if not state:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return state


@router.post("/resolve/{incident_id}", response_model=EscalationState)
async def resolve_escalation(
    incident_id: str,
    resolved_by: str = Query(..., description="User resolving"),
    service: EscalationService = Depends(get_service),
):
    """Resolve an escalation."""
    state = await service.resolve(incident_id, resolved_by)
    if not state:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return state


# State and history endpoints
@router.get("/state/{incident_id}", response_model=EscalationState)
async def get_escalation_state(
    incident_id: str,
    service: EscalationService = Depends(get_service),
):
    """Get current escalation state for an incident."""
    state = await service.get_escalation_state(incident_id)
    if not state:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return state


@router.get("/history", response_model=HistoryListResponse)
async def get_escalation_history(
    incident_id: str | None = None,
    policy_id: UUID | None = None,
    status: EscalationStatus | None = None,
    level: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: EscalationService = Depends(get_service),
):
    """Query escalation history with filters."""
    entries = await service.get_history(
        incident_id=incident_id,
        policy_id=policy_id,
        status=status,
        level=level,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return HistoryListResponse(entries=entries, total=len(entries))


# On-call management endpoints
@router.post("/oncall/{team_id}", response_model=OnCallAssignment)
async def set_oncall(
    team_id: str,
    assignment: OnCallAssignment,
    service: EscalationService = Depends(get_service),
):
    """Set the current on-call for a team."""
    return await service.set_oncall(team_id, assignment)


@router.get("/oncall/{team_id}", response_model=OnCallAssignment)
async def get_oncall(
    team_id: str,
    service: EscalationService = Depends(get_service),
):
    """Get the current on-call for a team."""
    oncall = await service.get_oncall(team_id)
    if not oncall:
        raise HTTPException(status_code=404, detail="No on-call found for team")
    return oncall


@router.post("/rotation", response_model=TeamRotation)
async def set_rotation(
    rotation: TeamRotation,
    service: EscalationService = Depends(get_service),
):
    """Set up a team rotation schedule."""
    return await service.set_rotation(rotation)


@router.post("/rotation/{team_id}/rotate", response_model=OnCallAssignment)
async def rotate_oncall(
    team_id: str,
    service: EscalationService = Depends(get_service),
):
    """Manually rotate to the next on-call person."""
    oncall = await service.rotate_oncall(team_id)
    if not oncall:
        raise HTTPException(
            status_code=400,
            detail="Unable to rotate - no rotation configured or no members",
        )
    return oncall


# Scheduler endpoints
@router.get("/scheduler/status", response_model=dict)
async def get_scheduler_status(
    scheduler: EscalationScheduler = Depends(get_sched),
):
    """Get the scheduler status."""
    return await scheduler.get_status()


@router.post("/scheduler/start", response_model=StatusResponse)
async def start_scheduler(
    background_tasks: BackgroundTasks,
    scheduler: EscalationScheduler = Depends(get_sched),
):
    """Start the escalation scheduler."""
    background_tasks.add_task(scheduler.start)
    return StatusResponse(status="success", message="Scheduler starting")


@router.post("/scheduler/stop", response_model=StatusResponse)
async def stop_scheduler(
    scheduler: EscalationScheduler = Depends(get_sched),
):
    """Stop the escalation scheduler."""
    await scheduler.stop()
    return StatusResponse(status="success", message="Scheduler stopped")


@router.get("/pending", response_model=list[EscalationState])
async def get_pending_escalations(
    service: EscalationService = Depends(get_service),
):
    """Get all pending escalations that need action."""
    return await service.get_pending_escalations()
