"""SLA Tracking API Routes.

FastAPI routes for SLA policy management, status queries, and reporting.
"""

import logging
import uuid
from datetime import datetime, timedelta, UTC
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .models import (
    DEFAULT_SLA_TARGETS,
    BusinessHours,
    SLABreach,
    SLAIncidentStatus,
    SLAMetrics,
    SLAPolicy,
    SLASeverity,
    SLAStatus,
    SLATarget,
    SLAType,
)
from .service import SLAService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sla", tags=["SLA Tracking"])


# --- Dependency Injection ---


async def get_sla_service() -> SLAService:
    """Get SLA service instance.

    Override this dependency in your app to provide configured service.
    """
    from .store import SLAStore

    # Default: no Redis or DB (in-memory only for demo)
    store = SLAStore()
    return SLAService(store)


SLAServiceDep = Annotated[SLAService, Depends(get_sla_service)]


# --- Request/Response Models ---


class CreatePolicyRequest(BaseModel):
    """Request to create a new SLA policy."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    organization_id: str
    team_id: str | None = None
    service_id: str | None = None
    targets: list[SLATarget] = Field(default_factory=lambda: DEFAULT_SLA_TARGETS.copy())
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    escalation_enabled: bool = True
    escalation_contacts: list[str] = Field(default_factory=list)


class UpdatePolicyRequest(BaseModel):
    """Request to update an SLA policy."""

    name: str | None = None
    description: str | None = None
    targets: list[SLATarget] | None = None
    business_hours: BusinessHours | None = None
    escalation_enabled: bool | None = None
    escalation_contacts: list[str] | None = None
    is_active: bool | None = None


class StartTimerRequest(BaseModel):
    """Request to start SLA timers for an incident."""

    incident_id: str
    severity: SLASeverity
    policy_id: str
    started_at: datetime | None = None
    start_response: bool = True
    start_resolution: bool = True


class StopTimerRequest(BaseModel):
    """Request to stop an SLA timer."""

    incident_id: str
    sla_type: SLAType
    completed_at: datetime | None = None


class AcknowledgeBreachRequest(BaseModel):
    """Request to acknowledge an SLA breach."""

    user: str
    notes: str | None = None


class PolicyResponse(BaseModel):
    """SLA policy response."""

    policy: SLAPolicy
    message: str = "Success"


class PoliciesListResponse(BaseModel):
    """List of SLA policies response."""

    policies: list[SLAPolicy]
    total: int


class TimerResponse(BaseModel):
    """SLA timer response."""

    incident_id: str
    sla_type: SLAType
    status: SLAStatus
    elapsed_minutes: float
    remaining_minutes: float
    percent_elapsed: float
    target_minutes: int
    paused: bool
    breach_eta: str | None = None


class IncidentStatusResponse(BaseModel):
    """Complete incident SLA status response."""

    status: SLAIncidentStatus


class BreachListResponse(BaseModel):
    """List of SLA breaches response."""

    breaches: list[SLABreach]
    total: int


class MetricsResponse(BaseModel):
    """SLA metrics response."""

    metrics: SLAMetrics


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    service: str = "sla-tracking"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- Health Check ---


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check SLA service health."""
    return HealthResponse()


# --- Policy CRUD Routes ---


@router.post(
    "/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED
)
async def create_policy(
    request: CreatePolicyRequest,
    service: SLAServiceDep,
) -> PolicyResponse:
    """Create a new SLA policy.

    Creates an SLA policy with targets for different severities.
    Default targets are provided if not specified.
    """
    policy = SLAPolicy(
        id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        organization_id=request.organization_id,
        team_id=request.team_id,
        service_id=request.service_id,
        targets=request.targets,
        business_hours=request.business_hours,
        escalation_enabled=request.escalation_enabled,
        escalation_contacts=request.escalation_contacts,
    )

    await service.store.save_policy(policy)
    logger.info(f"Created SLA policy: {policy.id} ({policy.name})")

    return PolicyResponse(policy=policy, message="Policy created successfully")


@router.get("/policies", response_model=PoliciesListResponse)
async def list_policies(
    service: SLAServiceDep,
    organization_id: str = Query(..., description="Organization ID"),
    team_id: str | None = Query(None, description="Filter by team"),
    service_id: str | None = Query(None, description="Filter by service"),
    active_only: bool = Query(True, description="Only return active policies"),
) -> PoliciesListResponse:
    """List SLA policies for an organization.

    Optionally filter by team, service, or active status.
    """
    policies = await service.store.get_policies(
        organization_id=organization_id,
        team_id=team_id,
        service_id=service_id,
        active_only=active_only,
    )
    return PoliciesListResponse(policies=policies, total=len(policies))


@router.get("/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    service: SLAServiceDep,
) -> PolicyResponse:
    """Get an SLA policy by ID."""
    policy = await service.store.get_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )
    return PolicyResponse(policy=policy)


@router.patch("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    request: UpdatePolicyRequest,
    service: SLAServiceDep,
) -> PolicyResponse:
    """Update an existing SLA policy.

    Only provided fields will be updated.
    """
    policy = await service.store.get_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    # Update fields
    if request.name is not None:
        policy.name = request.name
    if request.description is not None:
        policy.description = request.description
    if request.targets is not None:
        policy.targets = request.targets
    if request.business_hours is not None:
        policy.business_hours = request.business_hours
    if request.escalation_enabled is not None:
        policy.escalation_enabled = request.escalation_enabled
    if request.escalation_contacts is not None:
        policy.escalation_contacts = request.escalation_contacts
    if request.is_active is not None:
        policy.is_active = request.is_active

    await service.store.save_policy(policy)
    logger.info(f"Updated SLA policy: {policy_id}")

    return PolicyResponse(policy=policy, message="Policy updated successfully")


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: str,
    service: SLAServiceDep,
) -> None:
    """Delete an SLA policy.

    Note: This will not affect existing timers using this policy.
    Consider deactivating instead of deleting.
    """
    deleted = await service.store.delete_policy(policy_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )
    logger.info(f"Deleted SLA policy: {policy_id}")


# --- Timer Management Routes ---


@router.post("/timers/start", response_model=dict[str, Any])
async def start_timers(
    request: StartTimerRequest,
    service: SLAServiceDep,
) -> dict[str, Any]:
    """Start SLA timers for an incident.

    Starts response and/or resolution timers based on the policy.
    """
    policy = await service.store.get_policy(request.policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {request.policy_id}",
        )

    result: dict[str, Any] = {
        "incident_id": request.incident_id,
        "policy_id": request.policy_id,
        "severity": request.severity,
        "timers": {},
    }

    if request.start_response:
        timer = await service.start_timer(
            incident_id=request.incident_id,
            policy=policy,
            severity=request.severity,
            sla_type=SLAType.RESPONSE,
            started_at=request.started_at,
        )
        if timer:
            result["timers"]["response"] = {
                "target_minutes": timer.target_minutes,
                "status": timer.status,
            }

    if request.start_resolution:
        timer = await service.start_timer(
            incident_id=request.incident_id,
            policy=policy,
            severity=request.severity,
            sla_type=SLAType.RESOLUTION,
            started_at=request.started_at,
        )
        if timer:
            result["timers"]["resolution"] = {
                "target_minutes": timer.target_minutes,
                "status": timer.status,
            }

    logger.info(f"Started SLA timers for incident {request.incident_id}")
    return result


@router.post("/timers/stop", response_model=TimerResponse)
async def stop_timer(
    request: StopTimerRequest,
    service: SLAServiceDep,
) -> TimerResponse:
    """Stop an SLA timer (mark as completed)."""
    timer = await service.stop_timer(
        incident_id=request.incident_id,
        sla_type=request.sla_type,
        completed_at=request.completed_at,
    )
    if not timer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Timer not found: {request.incident_id}/{request.sla_type}",
        )

    return TimerResponse(
        incident_id=timer.incident_id,
        sla_type=timer.sla_type,
        status=timer.status,
        elapsed_minutes=round(timer.elapsed_minutes, 2),
        remaining_minutes=round(timer.remaining_minutes, 2),
        percent_elapsed=round(timer.percent_elapsed, 2),
        target_minutes=timer.target_minutes,
        paused=timer.paused,
    )


@router.post("/timers/{incident_id}/{sla_type}/pause", response_model=TimerResponse)
async def pause_timer(
    incident_id: str,
    sla_type: SLAType,
    service: SLAServiceDep,
) -> TimerResponse:
    """Pause an SLA timer."""
    timer = await service.pause_timer(incident_id, sla_type)
    if not timer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Timer not found: {incident_id}/{sla_type}",
        )

    return TimerResponse(
        incident_id=timer.incident_id,
        sla_type=timer.sla_type,
        status=timer.status,
        elapsed_minutes=round(timer.elapsed_minutes, 2),
        remaining_minutes=round(timer.remaining_minutes, 2),
        percent_elapsed=round(timer.percent_elapsed, 2),
        target_minutes=timer.target_minutes,
        paused=timer.paused,
    )


@router.post("/timers/{incident_id}/{sla_type}/resume", response_model=TimerResponse)
async def resume_timer(
    incident_id: str,
    sla_type: SLAType,
    service: SLAServiceDep,
) -> TimerResponse:
    """Resume a paused SLA timer."""
    timer = await service.resume_timer(incident_id, sla_type)
    if not timer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Timer not found: {incident_id}/{sla_type}",
        )

    return TimerResponse(
        incident_id=timer.incident_id,
        sla_type=timer.sla_type,
        status=timer.status,
        elapsed_minutes=round(timer.elapsed_minutes, 2),
        remaining_minutes=round(timer.remaining_minutes, 2),
        percent_elapsed=round(timer.percent_elapsed, 2),
        target_minutes=timer.target_minutes,
        paused=timer.paused,
    )


# --- Status & Remaining Time Routes ---


@router.get("/incidents/{incident_id}/status", response_model=IncidentStatusResponse)
async def get_incident_sla_status(
    incident_id: str,
    policy_id: str = Query(..., description="Policy ID to use"),
    service: SLAServiceDep = None,
) -> IncidentStatusResponse:
    """Get complete SLA status for an incident.

    Returns both response and resolution timer status, plus any breaches.
    """
    policy = await service.store.get_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    incident_status = await service.get_incident_status(incident_id, policy)
    return IncidentStatusResponse(status=incident_status)


@router.get("/incidents/{incident_id}/remaining", response_model=dict[str, Any])
async def get_remaining_time(
    incident_id: str,
    sla_type: SLAType = Query(..., description="SLA type"),
    policy_id: str = Query(..., description="Policy ID"),
    service: SLAServiceDep = None,
) -> dict[str, Any]:
    """Get remaining time until SLA breach.

    Accounts for business hours if configured in the policy.
    """
    policy = await service.store.get_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )

    result = await service.calculate_remaining_time(incident_id, sla_type, policy)
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )

    return result


# --- Breach Routes ---


@router.get("/breaches", response_model=BreachListResponse)
async def list_breaches(
    service: SLAServiceDep,
    organization_id: str = Query(..., description="Organization ID"),
    days: int = Query(30, ge=1, le=365, description="Days to look back"),
    severity: SLASeverity | None = Query(None, description="Filter by severity"),
    sla_type: SLAType | None = Query(None, description="Filter by SLA type"),
) -> BreachListResponse:
    """List SLA breaches for an organization.

    Returns breaches within the specified time period.
    """
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days)

    breaches = await service.store.get_breaches_in_period(
        organization_id=organization_id,
        period_start=period_start,
        period_end=period_end,
        severity=severity,
        sla_type=sla_type,
    )
    return BreachListResponse(breaches=breaches, total=len(breaches))


@router.get("/incidents/{incident_id}/breaches", response_model=BreachListResponse)
async def get_incident_breaches(
    incident_id: str,
    service: SLAServiceDep,
) -> BreachListResponse:
    """Get all SLA breaches for a specific incident."""
    breaches = await service.store.get_incident_breaches(incident_id)
    return BreachListResponse(breaches=breaches, total=len(breaches))


@router.post("/breaches/{breach_id}/acknowledge", response_model=dict[str, Any])
async def acknowledge_breach(
    breach_id: str,
    request: AcknowledgeBreachRequest,
    service: SLAServiceDep,
) -> dict[str, Any]:
    """Acknowledge an SLA breach.

    Records who acknowledged the breach and any notes.
    """
    breach = await service.store.acknowledge_breach(breach_id, request.user)
    if not breach:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Breach not found: {breach_id}",
        )

    logger.info(f"Breach {breach_id} acknowledged by {request.user}")
    return {
        "breach_id": breach_id,
        "acknowledged_by": request.user,
        "acknowledged_at": (
            breach.acknowledged_at.isoformat() if breach.acknowledged_at else None
        ),
        "message": "Breach acknowledged successfully",
    }


# --- Metrics & Reporting Routes ---


@router.get("/metrics", response_model=MetricsResponse)
async def get_sla_metrics(
    service: SLAServiceDep,
    organization_id: str = Query(..., description="Organization ID"),
    days: int = Query(30, ge=1, le=365, description="Days to analyze"),
    team_id: str | None = Query(None, description="Filter by team"),
    service_id: str | None = Query(None, description="Filter by service"),
    policy_id: str | None = Query(None, description="Filter by policy"),
) -> MetricsResponse:
    """Get SLA compliance metrics.

    Returns aggregated metrics including:
    - Response and resolution SLA compliance percentages
    - Average response and resolution times
    - Breach counts by severity
    - Daily compliance trends
    """
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days)

    metrics = await service.calculate_metrics(
        organization_id=organization_id,
        period_start=period_start,
        period_end=period_end,
        team_id=team_id,
        service_id=service_id,
        policy_id=policy_id,
    )
    return MetricsResponse(metrics=metrics)


@router.get("/metrics/summary", response_model=dict[str, Any])
async def get_metrics_summary(
    service: SLAServiceDep,
    organization_id: str = Query(..., description="Organization ID"),
) -> dict[str, Any]:
    """Get a quick SLA summary for dashboards.

    Returns high-level stats for the last 7 and 30 days.
    """
    now = datetime.now(UTC)

    # Last 7 days
    metrics_7d = await service.calculate_metrics(
        organization_id=organization_id,
        period_start=now - timedelta(days=7),
        period_end=now,
    )

    # Last 30 days
    metrics_30d = await service.calculate_metrics(
        organization_id=organization_id,
        period_start=now - timedelta(days=30),
        period_end=now,
    )

    return {
        "organization_id": organization_id,
        "generated_at": now.isoformat(),
        "last_7_days": {
            "total_incidents": metrics_7d.total_incidents,
            "overall_compliance": metrics_7d.overall_compliance_percent,
            "response_compliance": metrics_7d.response_compliance_percent,
            "resolution_compliance": metrics_7d.resolution_compliance_percent,
            "breaches": metrics_7d.response_sla_breached
            + metrics_7d.resolution_sla_breached,
        },
        "last_30_days": {
            "total_incidents": metrics_30d.total_incidents,
            "overall_compliance": metrics_30d.overall_compliance_percent,
            "response_compliance": metrics_30d.response_compliance_percent,
            "resolution_compliance": metrics_30d.resolution_compliance_percent,
            "breaches": metrics_30d.response_sla_breached
            + metrics_30d.resolution_sla_breached,
            "avg_response_minutes": metrics_30d.avg_response_minutes,
            "avg_resolution_minutes": metrics_30d.avg_resolution_minutes,
        },
    }


@router.get("/reports/compliance", response_model=dict[str, Any])
async def get_compliance_report(
    service: SLAServiceDep,
    organization_id: str = Query(..., description="Organization ID"),
    start_date: datetime = Query(..., description="Report start date"),
    end_date: datetime = Query(..., description="Report end date"),
    group_by: str = Query("day", pattern="^(day|week|month)$", description="Grouping"),
) -> dict[str, Any]:
    """Generate an SLA compliance report.

    Groups data by day, week, or month for trend analysis.
    """
    metrics = await service.calculate_metrics(
        organization_id=organization_id,
        period_start=start_date,
        period_end=end_date,
    )

    return {
        "organization_id": organization_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "summary": {
            "total_incidents": metrics.total_incidents,
            "overall_compliance": metrics.overall_compliance_percent,
            "response_compliance": metrics.response_compliance_percent,
            "resolution_compliance": metrics.resolution_compliance_percent,
        },
        "by_severity": metrics.incidents_by_severity,
        "trends": metrics.compliance_trend,
        "generated_at": datetime.now(UTC).isoformat(),
    }
