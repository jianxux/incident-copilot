"""FastAPI routes for maintenance window management."""

from datetime import datetime, timedelta
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .checker import MaintenanceCheckResult, maintenance_checker
from .models import (
    CalendarEvent,
    EmergencyOverride,
    MaintenanceAuditEntry,
    MaintenanceQuery,
    MaintenanceStatus,
    MaintenanceWindow,
    MaintenanceWindowCreate,
    MaintenanceWindowUpdate,
    RecurrencePattern,
    SuppressionAction,
)
from .store import maintenance_store
from .suppression import SuppressionResult, alert_suppressor

logger = structlog.get_logger()
router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


# --- Response Models ---


class MaintenanceListResponse(BaseModel):
    """Response for listing maintenance windows."""

    windows: list[MaintenanceWindow]
    total: int


class MaintenanceCheckResponse(BaseModel):
    """Response for maintenance check endpoints."""

    in_maintenance: bool
    window_count: int
    window_ids: list[str]
    suppression_action: str
    has_override: bool
    override_reason: str | None = None


class MaintenanceInfoResponse(BaseModel):
    """Detailed maintenance info for a service."""

    service: str
    is_in_maintenance: bool
    current_windows: list[dict[str, Any]]
    has_override: bool
    upcoming_windows: list[dict[str, Any]]
    recent_maintenance: list[dict[str, Any]]


class CalendarResponse(BaseModel):
    """Response for calendar integration."""

    events: list[CalendarEvent]


class SuppressionStatsResponse(BaseModel):
    """Response for suppression statistics."""

    total_alerts: int
    suppressed: int
    annotated: int
    logged_only: int
    by_service: dict[str, int]
    by_window: dict[str, int]


class OverrideCreateRequest(BaseModel):
    """Request to create an emergency override."""

    reason: str
    services: list[str] = Field(default_factory=list)
    auto_revoke_minutes: int | None = None


class AlertCheckRequest(BaseModel):
    """Request to check if an alert should be suppressed."""

    alert_id: str
    service: str
    alert_type: str | None = None
    environment: str | None = None
    alert_data: dict[str, Any] | None = None


# --- Window CRUD Routes ---


@router.post("", response_model=MaintenanceWindow, status_code=201)
async def create_maintenance_window(
    request: MaintenanceWindowCreate,
    created_by: Annotated[str | None, Query(description="User creating the window")] = None,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> MaintenanceWindow:
    """
    Create a new maintenance window.

    Maintenance windows can be:
    - One-time or recurring
    - Per-service or global (affecting all services)
    - Configured to suppress, annotate, or just log alerts

    Example request for a weekly maintenance:
    ```json
    {
        "title": "Weekly Database Maintenance",
        "description": "Routine database optimization",
        "services": ["payments-api", "orders-api"],
        "start_time": "2024-01-20T02:00:00Z",
        "end_time": "2024-01-20T04:00:00Z",
        "recurring": {
            "pattern": "weekly",
            "days_of_week": [5],
            "start_time": "02:00",
            "duration_minutes": 120
        },
        "suppression_action": "suppress"
    }
    ```
    """
    try:
        window = await maintenance_store.create(
            request,
            created_by=created_by,
            tenant_id=tenant_id,
        )
        logger.info(
            "maintenance_window_created_via_api",
            window_id=window.id,
            title=window.title,
        )
        return window
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{window_id}", response_model=MaintenanceWindow)
async def get_maintenance_window(window_id: str) -> MaintenanceWindow:
    """
    Get a maintenance window by ID.

    Returns the full maintenance window details including status,
    schedule, and notification settings.
    """
    window = await maintenance_store.get(window_id)
    if not window:
        raise HTTPException(
            status_code=404,
            detail=f"Maintenance window {window_id} not found",
        )
    return window


@router.put("/{window_id}", response_model=MaintenanceWindow)
async def update_maintenance_window(
    window_id: str,
    updates: MaintenanceWindowUpdate,
    updated_by: Annotated[str | None, Query(description="User updating the window")] = None,
) -> MaintenanceWindow:
    """
    Update an existing maintenance window.

    Only provided fields will be updated. Can update schedule,
    services, suppression action, etc.
    """
    window = await maintenance_store.update(
        window_id,
        updates,
        updated_by=updated_by,
    )
    if not window:
        raise HTTPException(
            status_code=404,
            detail=f"Maintenance window {window_id} not found",
        )
    return window


@router.delete("/{window_id}")
async def delete_maintenance_window(
    window_id: str,
    deleted_by: Annotated[str | None, Query(description="User deleting the window")] = None,
) -> dict:
    """
    Delete a maintenance window.

    This permanently removes the maintenance window. Consider cancelling
    instead if you want to preserve the audit trail.
    """
    deleted = await maintenance_store.delete(window_id, deleted_by=deleted_by)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Maintenance window {window_id} not found",
        )
    return {"message": f"Maintenance window {window_id} deleted successfully"}


@router.post("/{window_id}/cancel", response_model=MaintenanceWindow)
async def cancel_maintenance_window(
    window_id: str,
    cancelled_by: Annotated[str | None, Query(description="User cancelling")] = None,
    reason: Annotated[str | None, Query(description="Reason for cancellation")] = None,
) -> MaintenanceWindow:
    """
    Cancel a scheduled or active maintenance window.

    Cancelled windows are preserved in the audit trail but will no
    longer suppress alerts.
    """
    window = await maintenance_store.cancel(
        window_id,
        cancelled_by=cancelled_by,
        reason=reason,
    )
    if not window:
        raise HTTPException(
            status_code=404,
            detail=f"Maintenance window {window_id} not found",
        )
    return window


@router.get("", response_model=MaintenanceListResponse)
async def list_maintenance_windows(
    status: Annotated[MaintenanceStatus | None, Query(description="Filter by status")] = None,
    service: Annotated[str | None, Query(description="Filter by service")] = None,
    environment: Annotated[str | None, Query(description="Filter by environment")] = None,
    is_active: Annotated[bool | None, Query(description="Filter active windows")] = None,
    is_global: Annotated[bool | None, Query(description="Filter global windows")] = None,
    start_after: Annotated[datetime | None, Query(description="Start time after")] = None,
    start_before: Annotated[datetime | None, Query(description="Start time before")] = None,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MaintenanceListResponse:
    """
    List maintenance windows with optional filters.

    Supports filtering by status, service, environment, and time range.
    Returns windows sorted by start time.
    """
    query = MaintenanceQuery(
        tenant_id=tenant_id,
        status=status,
        service=service,
        environment=environment,
        start_after=start_after,
        start_before=start_before,
        is_active=is_active,
        is_global=is_global,
        limit=limit,
        offset=offset,
    )
    
    windows = await maintenance_store.list(query)
    
    return MaintenanceListResponse(
        windows=windows,
        total=len(windows),
    )


# --- Status Management ---


@router.post("/{window_id}/activate", response_model=MaintenanceWindow)
async def activate_maintenance_window(window_id: str) -> MaintenanceWindow:
    """
    Manually activate a maintenance window.

    Use this to start maintenance early or if the automatic activation
    didn't trigger.
    """
    window = await maintenance_store.activate_window(window_id)
    if not window:
        raise HTTPException(
            status_code=404,
            detail=f"Maintenance window {window_id} not found",
        )
    return window


@router.post("/{window_id}/complete", response_model=MaintenanceWindow)
async def complete_maintenance_window(window_id: str) -> MaintenanceWindow:
    """
    Manually complete a maintenance window.

    Use this to end maintenance early when work is done.
    """
    window = await maintenance_store.complete_window(window_id)
    if not window:
        raise HTTPException(
            status_code=404,
            detail=f"Maintenance window {window_id} not found",
        )
    return window


# --- Maintenance Checks ---


@router.get("/check/service/{service}", response_model=MaintenanceCheckResponse)
async def check_service_maintenance(
    service: str,
    environment: Annotated[str | None, Query(description="Environment")] = None,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> MaintenanceCheckResponse:
    """
    Check if a service is currently in maintenance.

    Returns maintenance status, active windows, and suppression action.
    """
    result = await maintenance_checker.check_service(
        service=service,
        environment=environment,
        tenant_id=tenant_id,
    )
    
    return MaintenanceCheckResponse(
        in_maintenance=result.in_maintenance,
        window_count=len(result.windows),
        window_ids=[w.id for w in result.windows],
        suppression_action=result.suppression_action.value,
        has_override=result.has_override,
        override_reason=result.override_reason,
    )


@router.get("/check/global", response_model=MaintenanceCheckResponse)
async def check_global_maintenance(
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> MaintenanceCheckResponse:
    """
    Check if there's a global maintenance window active.

    Global maintenance affects all services.
    """
    result = await maintenance_checker.check_global_maintenance(tenant_id=tenant_id)
    
    return MaintenanceCheckResponse(
        in_maintenance=result.in_maintenance,
        window_count=len(result.windows),
        window_ids=[w.id for w in result.windows],
        suppression_action=result.suppression_action.value,
        has_override=result.has_override,
        override_reason=result.override_reason,
    )


@router.get("/info/{service}", response_model=MaintenanceInfoResponse)
async def get_service_maintenance_info(
    service: str,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> MaintenanceInfoResponse:
    """
    Get detailed maintenance information for a service.

    Includes current status, upcoming windows, and recent history.
    Useful for dashboard displays.
    """
    info = await maintenance_checker.get_maintenance_info(
        service=service,
        tenant_id=tenant_id,
    )
    return MaintenanceInfoResponse(**info)


# --- Alert Processing ---


@router.post("/alert/check", response_model=dict)
async def check_alert_suppression(
    request: AlertCheckRequest,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> dict:
    """
    Check if an alert should be suppressed and process it.

    This is the main endpoint for integrating with alerting systems.
    It checks maintenance status and returns the appropriate action.

    Example request:
    ```json
    {
        "alert_id": "alert-12345",
        "service": "payments-api",
        "alert_type": "high_latency",
        "environment": "prod",
        "alert_data": {"latency_ms": 500}
    }
    ```
    """
    result = await alert_suppressor.process_alert(
        alert_id=request.alert_id,
        service=request.service,
        alert_type=request.alert_type,
        environment=request.environment,
        tenant_id=tenant_id,
        alert_data=request.alert_data,
    )
    
    return result.to_dict()


@router.get("/alert/should-deliver")
async def should_deliver_alert(
    service: str,
    alert_type: Annotated[str | None, Query(description="Alert type")] = None,
    environment: Annotated[str | None, Query(description="Environment")] = None,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> dict:
    """
    Quick check if an alert should be delivered.

    Returns a simple yes/no with context. Use this for lightweight
    pre-flight checks before sending alerts.
    """
    should_deliver, context = await alert_suppressor.should_deliver_alert(
        service=service,
        alert_type=alert_type,
        environment=environment,
        tenant_id=tenant_id,
    )
    
    return {
        "should_deliver": should_deliver,
        **context,
    }


# --- Emergency Overrides ---


@router.post("/{window_id}/override", response_model=EmergencyOverride, status_code=201)
async def create_emergency_override(
    window_id: str,
    request: OverrideCreateRequest,
    created_by: Annotated[str, Query(description="User creating the override")],
) -> EmergencyOverride:
    """
    Create an emergency override for a maintenance window.

    Emergency overrides allow alerts to pass through during maintenance
    for true emergencies that require immediate attention.

    Example request:
    ```json
    {
        "reason": "Critical production outage detected",
        "services": ["payments-api"],
        "auto_revoke_minutes": 30
    }
    ```
    """
    # Verify window exists
    window = await maintenance_store.get(window_id)
    if not window:
        raise HTTPException(
            status_code=404,
            detail=f"Maintenance window {window_id} not found",
        )
    
    override = EmergencyOverride(
        maintenance_window_id=window_id,
        reason=request.reason,
        created_by=created_by,
        services=request.services,
        auto_revoke_minutes=request.auto_revoke_minutes,
    )
    
    try:
        override = await maintenance_store.create_override(override)
        return override
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{window_id}/overrides", response_model=list[EmergencyOverride])
async def list_window_overrides(window_id: str) -> list[EmergencyOverride]:
    """
    List all overrides for a maintenance window.

    Returns both active and revoked overrides.
    """
    return await maintenance_store.get_active_overrides(window_id)


@router.post("/override/{override_id}/revoke", response_model=EmergencyOverride)
async def revoke_override(
    override_id: str,
    revoked_by: Annotated[str | None, Query(description="User revoking")] = None,
) -> EmergencyOverride:
    """
    Revoke an emergency override.

    After revocation, the maintenance window will resume normal
    suppression behavior.
    """
    override = await maintenance_store.revoke_override(
        override_id,
        revoked_by=revoked_by,
    )
    if not override:
        raise HTTPException(
            status_code=404,
            detail=f"Override {override_id} not found",
        )
    return override


# --- Calendar Integration ---


@router.get("/calendar", response_model=CalendarResponse)
async def get_maintenance_calendar(
    start_date: Annotated[datetime | None, Query(description="Calendar start")] = None,
    end_date: Annotated[datetime | None, Query(description="Calendar end")] = None,
    service: Annotated[str | None, Query(description="Filter by service")] = None,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> CalendarResponse:
    """
    Get maintenance windows as calendar events.

    Returns events in a format suitable for calendar display on dashboards.
    Supports filtering by date range and service.
    """
    # Default to 30 days if not specified
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=7)
    if not end_date:
        end_date = datetime.utcnow() + timedelta(days=30)
    
    query = MaintenanceQuery(
        tenant_id=tenant_id,
        service=service,
        start_after=start_date - timedelta(days=1),  # Include slightly before
        start_before=end_date,
        limit=200,
    )
    
    windows = await maintenance_store.list(query)
    
    # Convert to calendar events
    events = []
    for window in windows:
        # Color based on status
        status_colors = {
            MaintenanceStatus.SCHEDULED: "#3B82F6",  # Blue
            MaintenanceStatus.ACTIVE: "#F59E0B",  # Amber
            MaintenanceStatus.COMPLETED: "#10B981",  # Green
            MaintenanceStatus.CANCELLED: "#6B7280",  # Gray
            MaintenanceStatus.OVERRIDDEN: "#EF4444",  # Red
        }
        
        event = CalendarEvent(
            id=window.id,
            title=window.title,
            description=window.description,
            start=window.start_time,
            end=window.end_time,
            color=status_colors.get(window.status, "#FFA500"),
            services=window.services,
            status=window.status,
            url=window.change_ticket_url,
        )
        
        # Add recurrence rule for recurring windows
        if window.is_recurring and window.recurring:
            event.recurrence_rule = _build_rrule(window.recurring)
        
        events.append(event)
    
    return CalendarResponse(events=events)


def _build_rrule(schedule) -> str:
    """Build iCal RRULE string from recurring schedule."""
    pattern_map = {
        RecurrencePattern.DAILY: "DAILY",
        RecurrencePattern.WEEKLY: "WEEKLY",
        RecurrencePattern.BIWEEKLY: "WEEKLY;INTERVAL=2",
        RecurrencePattern.MONTHLY: "MONTHLY",
        RecurrencePattern.QUARTERLY: "MONTHLY;INTERVAL=3",
        RecurrencePattern.YEARLY: "YEARLY",
    }
    
    freq = pattern_map.get(schedule.pattern, "DAILY")
    rrule = f"FREQ={freq}"
    
    if schedule.days_of_week:
        days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
        byday = ",".join(days[d] for d in schedule.days_of_week)
        rrule += f";BYDAY={byday}"
    
    if schedule.recurrence_end_date:
        until = schedule.recurrence_end_date.strftime("%Y%m%dT%H%M%SZ")
        rrule += f";UNTIL={until}"
    
    if schedule.max_occurrences:
        rrule += f";COUNT={schedule.max_occurrences}"
    
    return rrule


# --- Statistics & Audit ---


@router.get("/stats/suppression", response_model=SuppressionStatsResponse)
async def get_suppression_stats(
    window_id: Annotated[str | None, Query(description="Filter by window")] = None,
    service: Annotated[str | None, Query(description="Filter by service")] = None,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
    since_hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> SuppressionStatsResponse:
    """
    Get alert suppression statistics.

    Shows how many alerts were suppressed, annotated, or logged
    during maintenance windows.
    """
    stats = await alert_suppressor.get_suppression_stats(
        window_id=window_id,
        service=service,
        tenant_id=tenant_id,
        since_hours=since_hours,
    )
    return SuppressionStatsResponse(**stats)


@router.get("/{window_id}/suppressed-alerts")
async def get_suppressed_alerts(
    window_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict]:
    """
    Get list of alerts suppressed by a maintenance window.

    Useful for auditing what was suppressed during maintenance.
    """
    return await alert_suppressor.get_suppressed_alerts(
        window_id=window_id,
        limit=limit,
    )


@router.get("/{window_id}/audit-log", response_model=list[MaintenanceAuditEntry])
async def get_maintenance_audit_log(
    window_id: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MaintenanceAuditEntry]:
    """
    Get audit log for a maintenance window.

    Includes all actions: creation, updates, start/end times,
    overrides, and suppressed alerts.
    """
    return await maintenance_store.get_audit_log(
        window_id=window_id,
        limit=limit,
        offset=offset,
    )


# --- Upcoming & Active ---


@router.get("/upcoming", response_model=MaintenanceListResponse)
async def get_upcoming_maintenance(
    within_hours: Annotated[int, Query(ge=1, le=720)] = 24,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> MaintenanceListResponse:
    """
    Get maintenance windows starting soon.

    Useful for notifications and dashboard displays.
    """
    windows = await maintenance_store.get_upcoming_windows(
        within_hours=within_hours,
        tenant_id=tenant_id,
    )
    return MaintenanceListResponse(windows=windows, total=len(windows))


@router.get("/active", response_model=MaintenanceListResponse)
async def get_active_maintenance(
    service: Annotated[str | None, Query(description="Filter by service")] = None,
    tenant_id: Annotated[str | None, Query(description="Tenant ID")] = None,
) -> MaintenanceListResponse:
    """
    Get all currently active maintenance windows.
    """
    windows = await maintenance_store.get_active_windows(
        service=service,
        tenant_id=tenant_id,
    )
    return MaintenanceListResponse(windows=windows, total=len(windows))
