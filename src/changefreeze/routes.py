"""FastAPI routes for Change Freeze Management."""

import uuid
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .alerts import FreezeAlertService, freeze_alert_service
from .detector import DeploymentDetector, deployment_detector
from .models import (
    ApprovalStatus,
    ChangeFreeze,
    CreateExceptionRequest,
    CreateFreezeRequest,
    DeploymentEvent,
    FreezeException,
    FreezeScope,
    FreezeStatus,
    FreezeStatusResponse,
    FreezeViolation,
    ReviewExceptionRequest,
    UpdateFreezeRequest,
    ViolationListResponse,
)
from .store import ChangeFreezeStore, changefreeze_store

logger = structlog.get_logger()
router = APIRouter(prefix="/api/changefreeze", tags=["changefreeze"])


# --- Response Models ---


class FreezeResponse(BaseModel):
    """Response for freeze operations."""

    freeze: ChangeFreeze
    message: str


class FreezeListResponse(BaseModel):
    """Response for listing freezes."""

    freezes: list[ChangeFreeze]
    total: int
    active_count: int


class ExceptionResponse(BaseModel):
    """Response for exception operations."""

    exception: FreezeException
    message: str


class ExceptionListResponse(BaseModel):
    """Response for listing exceptions."""

    exceptions: list[FreezeException]
    total: int
    pending_count: int


class DeploymentCheckResponse(BaseModel):
    """Response for deployment check."""

    allowed: bool
    reason: str
    active_freezes: list[ChangeFreeze]
    valid_exceptions: list[FreezeException]


class StatsResponse(BaseModel):
    """Response for statistics."""

    stats: dict


# --- Freeze Endpoints ---


@router.post("/freezes", response_model=FreezeResponse)
async def create_freeze(
    request: CreateFreezeRequest,
    created_by: Annotated[str, Query(description="User creating the freeze")] = "system",
) -> FreezeResponse:
    """
    Create a new change freeze.

    Example request:
    ```json
    {
        "name": "Holiday Freeze 2024",
        "description": "End of year change freeze",
        "starts_at": "2024-12-20T00:00:00Z",
        "ends_at": "2025-01-02T00:00:00Z",
        "scope": "global",
        "allow_emergency_deployments": true,
        "notification_channels": ["#incidents", "#deployments"],
        "approvers": ["alice", "bob"]
    }
    ```
    """
    if request.ends_at <= request.starts_at:
        raise HTTPException(
            status_code=400,
            detail="End time must be after start time",
        )

    freeze = ChangeFreeze(
        freeze_id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        starts_at=request.starts_at,
        ends_at=request.ends_at,
        scope=request.scope,
        services=request.services,
        environments=request.environments,
        teams=request.teams,
        allow_emergency_deployments=request.allow_emergency_deployments,
        require_approval_for_exceptions=request.require_approval_for_exceptions,
        notification_channels=request.notification_channels,
        approvers=request.approvers,
        created_by=created_by,
    )

    # Set status based on timing
    now = datetime.utcnow()
    if freeze.starts_at <= now <= freeze.ends_at:
        freeze.status = FreezeStatus.ACTIVE
    elif now > freeze.ends_at:
        freeze.status = FreezeStatus.COMPLETED

    await changefreeze_store.save_freeze(freeze)

    logger.info(
        "freeze_created",
        freeze_id=freeze.freeze_id,
        name=freeze.name,
        starts_at=freeze.starts_at.isoformat(),
        ends_at=freeze.ends_at.isoformat(),
        created_by=created_by,
    )

    return FreezeResponse(
        freeze=freeze,
        message=f"Change freeze '{freeze.name}' created successfully",
    )


@router.get("/freezes", response_model=FreezeListResponse)
async def list_freezes(
    status: Annotated[
        FreezeStatus | None,
        Query(description="Filter by status"),
    ] = None,
    include_completed: Annotated[
        bool,
        Query(description="Include completed freezes"),
    ] = False,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum results"),
    ] = 50,
) -> FreezeListResponse:
    """
    List change freezes with optional filtering.

    Returns freezes sorted by start date (most recent first).
    """
    freezes = await changefreeze_store.get_all_freezes(
        status=status,
        include_completed=include_completed,
        limit=limit,
    )

    active_count = len([f for f in freezes if f.is_active()])

    return FreezeListResponse(
        freezes=freezes,
        total=len(freezes),
        active_count=active_count,
    )


@router.get("/freezes/active", response_model=FreezeListResponse)
async def get_active_freezes(
    service_name: Annotated[
        str | None,
        Query(description="Filter by service"),
    ] = None,
    environment: Annotated[
        str | None,
        Query(description="Filter by environment"),
    ] = None,
) -> FreezeListResponse:
    """Get all currently active freezes."""
    freezes = await changefreeze_store.get_active_freezes(
        service_name=service_name,
        environment=environment,
    )

    return FreezeListResponse(
        freezes=freezes,
        total=len(freezes),
        active_count=len(freezes),
    )


@router.get("/freezes/{freeze_id}", response_model=ChangeFreeze)
async def get_freeze(freeze_id: str) -> ChangeFreeze:
    """Get a freeze by ID."""
    freeze = await changefreeze_store.get_freeze(freeze_id)
    if not freeze:
        raise HTTPException(
            status_code=404,
            detail=f"Freeze {freeze_id} not found",
        )
    return freeze


@router.put("/freezes/{freeze_id}", response_model=FreezeResponse)
async def update_freeze(
    freeze_id: str,
    request: UpdateFreezeRequest,
) -> FreezeResponse:
    """Update an existing freeze."""
    freeze = await changefreeze_store.get_freeze(freeze_id)
    if not freeze:
        raise HTTPException(
            status_code=404,
            detail=f"Freeze {freeze_id} not found",
        )

    if freeze.status in (FreezeStatus.COMPLETED, FreezeStatus.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update {freeze.status.value} freeze",
        )

    # Apply updates
    if request.name is not None:
        freeze.name = request.name
    if request.description is not None:
        freeze.description = request.description
    if request.starts_at is not None:
        freeze.starts_at = request.starts_at
    if request.ends_at is not None:
        freeze.ends_at = request.ends_at
    if request.services is not None:
        freeze.services = request.services
    if request.environments is not None:
        freeze.environments = request.environments
    if request.allow_emergency_deployments is not None:
        freeze.allow_emergency_deployments = request.allow_emergency_deployments
    if request.notification_channels is not None:
        freeze.notification_channels = request.notification_channels
    if request.approvers is not None:
        freeze.approvers = request.approvers

    await changefreeze_store.save_freeze(freeze)

    logger.info("freeze_updated", freeze_id=freeze_id)

    return FreezeResponse(
        freeze=freeze,
        message=f"Freeze '{freeze.name}' updated successfully",
    )


@router.post("/freezes/{freeze_id}/cancel", response_model=FreezeResponse)
async def cancel_freeze(
    freeze_id: str,
    cancelled_by: Annotated[str, Query(description="User cancelling")] = "system",
    reason: Annotated[str | None, Query(description="Cancellation reason")] = None,
) -> FreezeResponse:
    """Cancel a freeze."""
    freeze = await changefreeze_store.cancel_freeze(
        freeze_id=freeze_id,
        cancelled_by=cancelled_by,
        reason=reason,
    )

    if not freeze:
        raise HTTPException(
            status_code=404,
            detail=f"Freeze {freeze_id} not found",
        )

    logger.info(
        "freeze_cancelled",
        freeze_id=freeze_id,
        cancelled_by=cancelled_by,
        reason=reason,
    )

    return FreezeResponse(
        freeze=freeze,
        message=f"Freeze '{freeze.name}' cancelled",
    )


@router.delete("/freezes/{freeze_id}")
async def delete_freeze(freeze_id: str) -> dict:
    """Delete a freeze (only if not active)."""
    freeze = await changefreeze_store.get_freeze(freeze_id)
    if not freeze:
        raise HTTPException(
            status_code=404,
            detail=f"Freeze {freeze_id} not found",
        )

    if freeze.is_active():
        raise HTTPException(
            status_code=400,
            detail="Cannot delete an active freeze. Cancel it first.",
        )

    await changefreeze_store.delete_freeze(freeze_id)

    logger.info("freeze_deleted", freeze_id=freeze_id)

    return {"message": f"Freeze {freeze_id} deleted"}


# --- Exception Endpoints ---


@router.post("/exceptions", response_model=ExceptionResponse)
async def create_exception(
    request: CreateExceptionRequest,
    requested_by: Annotated[str, Query(description="User requesting")] = "system",
) -> ExceptionResponse:
    """
    Request a freeze exception.

    For emergency deployments, set `is_emergency: true` and provide
    the `emergency_ticket_id` for the incident/outage.

    Example request:
    ```json
    {
        "freeze_id": "uuid-here",
        "service_name": "payments-api",
        "environment": "production",
        "reason": "Critical security patch for CVE-2024-1234",
        "justification": "This CVE allows remote code execution...",
        "risk_assessment": "Low risk - single line change",
        "rollback_plan": "Revert commit abc123",
        "is_emergency": true,
        "emergency_ticket_id": "INC-5678"
    }
    ```
    """
    freeze = await changefreeze_store.get_freeze(request.freeze_id)
    if not freeze:
        raise HTTPException(
            status_code=404,
            detail=f"Freeze {request.freeze_id} not found",
        )

    if not freeze.is_active() and freeze.status != FreezeStatus.SCHEDULED:
        raise HTTPException(
            status_code=400,
            detail="Cannot request exception for inactive freeze",
        )

    exception = FreezeException(
        exception_id=str(uuid.uuid4()),
        freeze_id=request.freeze_id,
        requested_by=requested_by,
        service_name=request.service_name,
        environment=request.environment,
        reason=request.reason,
        justification=request.justification,
        risk_assessment=request.risk_assessment,
        rollback_plan=request.rollback_plan,
        is_emergency=request.is_emergency,
        emergency_ticket_id=request.emergency_ticket_id,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
    )

    # Auto-approve emergency deployments if allowed
    if request.is_emergency and freeze.allow_emergency_deployments:
        exception.status = ApprovalStatus.APPROVED
        exception.reviewed_by = "system"
        exception.reviewed_at = datetime.utcnow()
        exception.review_notes = "Auto-approved emergency deployment"

    await changefreeze_store.save_exception(exception)

    # Send notification
    await freeze_alert_service.alert_exception_requested(exception, freeze)

    logger.info(
        "exception_requested",
        exception_id=exception.exception_id,
        freeze_id=request.freeze_id,
        service=request.service_name,
        is_emergency=request.is_emergency,
        auto_approved=exception.status == ApprovalStatus.APPROVED,
    )

    return ExceptionResponse(
        exception=exception,
        message="Exception request submitted"
        if exception.status == ApprovalStatus.PENDING
        else "Emergency exception auto-approved",
    )


@router.get("/exceptions", response_model=ExceptionListResponse)
async def list_exceptions(
    freeze_id: Annotated[
        str | None,
        Query(description="Filter by freeze ID"),
    ] = None,
    status: Annotated[
        ApprovalStatus | None,
        Query(description="Filter by status"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,
) -> ExceptionListResponse:
    """List freeze exceptions."""
    if freeze_id:
        exceptions = await changefreeze_store.get_exceptions_for_freeze(
            freeze_id=freeze_id,
            status=status,
        )
    else:
        if status == ApprovalStatus.PENDING:
            exceptions = await changefreeze_store.get_pending_exceptions()
        else:
            # Get all exceptions (need to implement full listing)
            exceptions = []
            freezes = await changefreeze_store.get_all_freezes(include_completed=True)
            for freeze in freezes:
                freeze_exceptions = await changefreeze_store.get_exceptions_for_freeze(
                    freeze_id=freeze.freeze_id,
                    status=status,
                )
                exceptions.extend(freeze_exceptions)

    pending_count = len([e for e in exceptions if e.status == ApprovalStatus.PENDING])

    return ExceptionListResponse(
        exceptions=exceptions[:limit],
        total=len(exceptions),
        pending_count=pending_count,
    )


@router.get("/exceptions/pending", response_model=ExceptionListResponse)
async def get_pending_exceptions() -> ExceptionListResponse:
    """Get all pending exception requests."""
    exceptions = await changefreeze_store.get_pending_exceptions()

    return ExceptionListResponse(
        exceptions=exceptions,
        total=len(exceptions),
        pending_count=len(exceptions),
    )


@router.get("/exceptions/{exception_id}", response_model=FreezeException)
async def get_exception(exception_id: str) -> FreezeException:
    """Get an exception by ID."""
    exception = await changefreeze_store.get_exception(exception_id)
    if not exception:
        raise HTTPException(
            status_code=404,
            detail=f"Exception {exception_id} not found",
        )
    return exception


@router.post("/exceptions/{exception_id}/review", response_model=ExceptionResponse)
async def review_exception(
    exception_id: str,
    request: ReviewExceptionRequest,
    reviewed_by: Annotated[str, Query(description="Reviewer")] = "system",
) -> ExceptionResponse:
    """
    Review (approve or reject) an exception request.

    Example request:
    ```json
    {
        "approved": true,
        "notes": "Approved for critical fix",
        "valid_from": "2024-12-25T10:00:00Z",
        "valid_until": "2024-12-25T12:00:00Z"
    }
    ```
    """
    exception = await changefreeze_store.get_exception(exception_id)
    if not exception:
        raise HTTPException(
            status_code=404,
            detail=f"Exception {exception_id} not found",
        )

    if exception.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Exception already {exception.status.value}",
        )

    if request.approved:
        exception = await changefreeze_store.approve_exception(
            exception_id=exception_id,
            reviewed_by=reviewed_by,
            notes=request.notes,
            valid_from=request.valid_from,
            valid_until=request.valid_until,
        )
        message = "Exception approved"
    else:
        exception = await changefreeze_store.reject_exception(
            exception_id=exception_id,
            reviewed_by=reviewed_by,
            notes=request.notes,
        )
        message = "Exception rejected"

    # Notify requester
    freeze = await changefreeze_store.get_freeze(exception.freeze_id)
    await freeze_alert_service.alert_exception_reviewed(exception, freeze)

    logger.info(
        "exception_reviewed",
        exception_id=exception_id,
        approved=request.approved,
        reviewed_by=reviewed_by,
    )

    return ExceptionResponse(
        exception=exception,
        message=message,
    )


# --- Violation Endpoints ---


@router.get("/violations", response_model=ViolationListResponse)
async def list_violations(
    freeze_id: Annotated[
        str | None,
        Query(description="Filter by freeze ID"),
    ] = None,
    acknowledged: Annotated[
        bool | None,
        Query(description="Filter by acknowledgement status"),
    ] = None,
    service_name: Annotated[
        str | None,
        Query(description="Filter by service"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,
) -> ViolationListResponse:
    """List freeze violations."""
    if freeze_id:
        violations = await changefreeze_store.get_violations_for_freeze(
            freeze_id=freeze_id,
            acknowledged=acknowledged,
            limit=limit,
        )
    else:
        violations = await changefreeze_store.get_all_violations(
            acknowledged=acknowledged,
            service_name=service_name,
            limit=limit,
        )

    unacknowledged_count = len([v for v in violations if not v.acknowledged])

    return ViolationListResponse(
        violations=violations,
        total=len(violations),
        unacknowledged_count=unacknowledged_count,
    )


@router.get("/violations/{violation_id}", response_model=FreezeViolation)
async def get_violation(violation_id: str) -> FreezeViolation:
    """Get a violation by ID."""
    violation = await changefreeze_store.get_violation(violation_id)
    if not violation:
        raise HTTPException(
            status_code=404,
            detail=f"Violation {violation_id} not found",
        )
    return violation


@router.post("/violations/{violation_id}/acknowledge")
async def acknowledge_violation(
    violation_id: str,
    acknowledged_by: Annotated[str, Query(description="User acknowledging")] = "system",
    reason: Annotated[str | None, Query(description="Acknowledgement reason")] = None,
) -> FreezeViolation:
    """Acknowledge a violation."""
    violation = await changefreeze_store.acknowledge_violation(
        violation_id=violation_id,
        acknowledged_by=acknowledged_by,
        reason=reason,
    )

    if not violation:
        raise HTTPException(
            status_code=404,
            detail=f"Violation {violation_id} not found",
        )

    logger.info(
        "violation_acknowledged",
        violation_id=violation_id,
        acknowledged_by=acknowledged_by,
    )

    return violation


# --- Deployment Check Endpoint ---


@router.get("/check", response_model=DeploymentCheckResponse)
async def check_deployment(
    service_name: Annotated[str, Query(description="Service to deploy")],
    environment: Annotated[
        str,
        Query(description="Target environment"),
    ] = "production",
) -> DeploymentCheckResponse:
    """
    Check if a deployment is allowed for a service.

    This endpoint should be called by CI/CD pipelines before deploying.

    Example:
    ```
    GET /api/changefreeze/check?service_name=payments-api&environment=production
    ```

    Returns whether deployment is allowed and any active freezes/exceptions.
    """
    allowed, reason, freezes, exceptions = await deployment_detector.check_deployment_allowed(
        service_name=service_name,
        environment=environment,
    )

    return DeploymentCheckResponse(
        allowed=allowed,
        reason=reason,
        active_freezes=freezes,
        valid_exceptions=exceptions,
    )


@router.get("/status", response_model=FreezeStatusResponse)
async def get_freeze_status(
    service_name: Annotated[
        str | None,
        Query(description="Optional service filter"),
    ] = None,
    environment: Annotated[
        str | None,
        Query(description="Optional environment filter"),
    ] = None,
) -> FreezeStatusResponse:
    """
    Get current freeze status.

    Returns summary of active freezes and applicable exceptions.
    """
    is_frozen, freezes, exceptions = await changefreeze_store.check_freeze_status(
        service_name=service_name or "*",
        environment=environment or "production",
    )

    can_deploy = not is_frozen or len(exceptions) > 0
    
    if not is_frozen:
        reason = "No active change freeze"
    elif exceptions:
        reason = f"Freeze active, but {len(exceptions)} exception(s) available"
    else:
        reason = f"{len(freezes)} active freeze(s), no exceptions"

    return FreezeStatusResponse(
        is_frozen=is_frozen,
        active_freezes=freezes,
        applicable_exceptions=exceptions,
        can_deploy=can_deploy,
        reason=reason,
    )


# --- GitHub Webhook Endpoint ---


@router.post("/webhooks/github")
async def github_webhook(request: Request) -> dict:
    """
    Receive GitHub webhook events for deployment detection.

    Configure your GitHub repository to send the following events:
    - deployment
    - deployment_status
    - push (optional, for deploy branches)
    - release (optional)

    Webhook URL: `https://your-domain/api/changefreeze/webhooks/github`
    """
    event_type = request.headers.get("X-GitHub-Event", "")
    
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    logger.info(
        "github_webhook_received",
        event_type=event_type,
        delivery_id=request.headers.get("X-GitHub-Delivery"),
    )

    if event_type == "ping":
        return {"message": "pong", "zen": payload.get("zen")}

    deployment_event = await deployment_detector.process_github_webhook(
        event_type=event_type,
        payload=payload,
    )

    if deployment_event:
        # If violation, send alert
        if deployment_event.is_violation and deployment_event.violation_id:
            violation = await changefreeze_store.get_violation(
                deployment_event.violation_id
            )
            if violation:
                await freeze_alert_service.alert_violation(violation)

        return {
            "message": "Deployment detected",
            "event_id": deployment_event.event_id,
            "during_freeze": deployment_event.during_freeze,
            "is_violation": deployment_event.is_violation,
        }

    return {"message": "Event processed, no deployment detected"}


# --- Stats Endpoint ---


@router.get("/stats", response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """Get change freeze statistics."""
    stats = await changefreeze_store.get_stats()
    return StatsResponse(stats=stats)
