"""API routes for the Incident Communication Hub.

Provides endpoints for:
- Stakeholder management
- Communication plans
- Sending updates
- Template management
- Reminder configuration
- Audit log access
"""

from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from .channels import ChannelDelivery, DeliveryResult, get_channel_delivery
from .models import (
    AudienceType,
    BroadcastUpdateRequest,
    CommunicationAuditListResponse,
    CommunicationPlan,
    CommunicationPlanListResponse,
    CommunicationUpdate,
    CreateCommunicationPlanRequest,
    CreateStakeholderGroupRequest,
    CreateStakeholderRequest,
    DeliveryChannel,
    SendUpdateRequest,
    Stakeholder,
    StakeholderGroup,
    StakeholderGroupListResponse,
    StakeholderListResponse,
    UpdatePriority,
    UpdateStakeholderRequest,
)
from .scheduler import UpdateScheduler, get_update_scheduler
from .templates import (
    CommunicationTemplate,
    RenderedTemplate,
    TemplateLibrary,
    get_template_library,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/comms", tags=["communications"])


# In-memory storage (replace with database in production)
_stakeholders: dict[str, Stakeholder] = {}
_stakeholder_groups: dict[str, StakeholderGroup] = {}
_plans: dict[str, CommunicationPlan] = {}
_updates: dict[str, CommunicationUpdate] = {}


# ============================================================================
# Dependencies
# ============================================================================


async def get_scheduler() -> UpdateScheduler:
    """Dependency to get the update scheduler."""
    return await get_update_scheduler()


async def get_templates() -> TemplateLibrary:
    """Dependency to get the template library."""
    return await get_template_library()


async def get_delivery() -> ChannelDelivery:
    """Dependency to get the channel delivery service."""
    return await get_channel_delivery()


# ============================================================================
# Stakeholder Endpoints
# ============================================================================


@router.post(
    "/stakeholders",
    response_model=Stakeholder,
    status_code=status.HTTP_201_CREATED,
)
async def create_stakeholder(
    request: CreateStakeholderRequest,
) -> Stakeholder:
    """Create a new stakeholder.

    Stakeholders are people or groups who need to receive incident communications.
    Each stakeholder can have preferred channels and notification thresholds.
    """
    stakeholder = Stakeholder(
        name=request.name,
        email=request.email,
        phone=request.phone,
        slack_user_id=request.slack_user_id,
        teams_user_id=request.teams_user_id,
        audience_type=request.audience_type,
        preferred_channels=request.preferred_channels,
        notification_threshold=request.notification_threshold,
        role=request.role,
        department=request.department,
        organization=request.organization,
        subscribed_services=request.subscribed_services,
        subscribed_severity_levels=request.subscribed_severity_levels,
    )

    _stakeholders[stakeholder.id] = stakeholder
    logger.info("stakeholder_created", stakeholder_id=stakeholder.id, name=stakeholder.name)
    return stakeholder


@router.get("/stakeholders", response_model=StakeholderListResponse)
async def list_stakeholders(
    audience_type: AudienceType | None = None,
    is_active: bool | None = True,
    service: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> StakeholderListResponse:
    """List stakeholders with optional filters."""
    stakeholders = list(_stakeholders.values())

    if audience_type:
        stakeholders = [s for s in stakeholders if s.audience_type == audience_type]

    if is_active is not None:
        stakeholders = [s for s in stakeholders if s.is_active == is_active]

    if service:
        stakeholders = [
            s for s in stakeholders
            if not s.subscribed_services or service in s.subscribed_services
        ]

    total = len(stakeholders)
    stakeholders = stakeholders[offset:offset + limit]

    return StakeholderListResponse(
        stakeholders=stakeholders,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/stakeholders/{stakeholder_id}", response_model=Stakeholder)
async def get_stakeholder(stakeholder_id: str) -> Stakeholder:
    """Get a stakeholder by ID."""
    stakeholder = _stakeholders.get(stakeholder_id)
    if not stakeholder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stakeholder not found: {stakeholder_id}",
        )
    return stakeholder


@router.patch("/stakeholders/{stakeholder_id}", response_model=Stakeholder)
async def update_stakeholder(
    stakeholder_id: str,
    request: UpdateStakeholderRequest,
) -> Stakeholder:
    """Update an existing stakeholder."""
    stakeholder = _stakeholders.get(stakeholder_id)
    if not stakeholder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stakeholder not found: {stakeholder_id}",
        )

    updates = request.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(stakeholder, key, value)

    stakeholder.updated_at = datetime.utcnow()
    _stakeholders[stakeholder_id] = stakeholder

    logger.info("stakeholder_updated", stakeholder_id=stakeholder_id)
    return stakeholder


@router.delete("/stakeholders/{stakeholder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stakeholder(stakeholder_id: str) -> None:
    """Delete a stakeholder."""
    if stakeholder_id not in _stakeholders:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stakeholder not found: {stakeholder_id}",
        )

    del _stakeholders[stakeholder_id]
    logger.info("stakeholder_deleted", stakeholder_id=stakeholder_id)


# ============================================================================
# Stakeholder Group Endpoints
# ============================================================================


@router.post(
    "/stakeholder-groups",
    response_model=StakeholderGroup,
    status_code=status.HTTP_201_CREATED,
)
async def create_stakeholder_group(
    request: CreateStakeholderGroupRequest,
) -> StakeholderGroup:
    """Create a stakeholder group for bulk communications."""
    group = StakeholderGroup(
        name=request.name,
        description=request.description,
        stakeholder_ids=request.stakeholder_ids,
        audience_type=request.audience_type,
        default_channels=request.default_channels,
        subscribed_services=request.subscribed_services,
    )

    _stakeholder_groups[group.id] = group
    logger.info("stakeholder_group_created", group_id=group.id, name=group.name)
    return group


@router.get("/stakeholder-groups", response_model=StakeholderGroupListResponse)
async def list_stakeholder_groups(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> StakeholderGroupListResponse:
    """List stakeholder groups."""
    groups = list(_stakeholder_groups.values())
    total = len(groups)
    groups = groups[offset:offset + limit]

    return StakeholderGroupListResponse(
        groups=groups,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/stakeholder-groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_stakeholder_group(group_id: str) -> None:
    """Delete a stakeholder group."""
    if group_id not in _stakeholder_groups:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stakeholder group not found: {group_id}",
        )

    del _stakeholder_groups[group_id]
    logger.info("stakeholder_group_deleted", group_id=group_id)


# ============================================================================
# Communication Plan Endpoints
# ============================================================================


@router.post(
    "/plans",
    response_model=CommunicationPlan,
    status_code=status.HTTP_201_CREATED,
)
async def create_communication_plan(
    request: CreateCommunicationPlanRequest,
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
) -> CommunicationPlan:
    """Create a communication plan for an incident.

    A communication plan defines who receives updates, how often reminders
    are sent, and which templates to use for different audiences.
    """
    plan = CommunicationPlan(
        incident_id=request.incident_id,
        incident_title=request.incident_title,
        severity=request.severity,
        stakeholder_ids=request.stakeholder_ids,
        stakeholder_group_ids=request.stakeholder_group_ids,
        auto_reminder_enabled=request.auto_reminder_enabled,
        auto_reminder_interval_minutes=request.auto_reminder_interval_minutes,
        template_ids=request.template_ids,
    )

    _plans[plan.id] = plan

    # Register plan with scheduler for reminders
    await scheduler.register_plan(plan)

    logger.info(
        "communication_plan_created",
        plan_id=plan.id,
        incident_id=plan.incident_id,
    )
    return plan


@router.get("/plans", response_model=CommunicationPlanListResponse)
async def list_communication_plans(
    incident_id: str | None = None,
    is_active: bool | None = True,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> CommunicationPlanListResponse:
    """List communication plans."""
    plans = list(_plans.values())

    if incident_id:
        plans = [p for p in plans if p.incident_id == incident_id]

    if is_active is not None:
        plans = [p for p in plans if p.is_active == is_active]

    total = len(plans)
    plans = plans[offset:offset + limit]

    return CommunicationPlanListResponse(
        plans=plans,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/plans/{plan_id}", response_model=CommunicationPlan)
async def get_communication_plan(plan_id: str) -> CommunicationPlan:
    """Get a communication plan by ID."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Communication plan not found: {plan_id}",
        )
    return plan


@router.post("/plans/{plan_id}/close", response_model=CommunicationPlan)
async def close_communication_plan(
    plan_id: str,
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
) -> CommunicationPlan:
    """Close a communication plan (e.g., when incident is resolved)."""
    plan = _plans.get(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Communication plan not found: {plan_id}",
        )

    plan.is_active = False
    plan.updated_at = datetime.utcnow()
    _plans[plan_id] = plan

    # Unregister from scheduler
    await scheduler.unregister_plan(plan_id)

    logger.info("communication_plan_closed", plan_id=plan_id)
    return plan


# ============================================================================
# Send Update Endpoints
# ============================================================================


@router.post("/updates/send", response_model=CommunicationUpdate)
async def send_update(
    request: SendUpdateRequest,
    delivery: Annotated[ChannelDelivery, Depends(get_delivery)],
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
    templates: Annotated[TemplateLibrary, Depends(get_templates)],
) -> CommunicationUpdate:
    """Send a communication update to specified recipients.

    This is the main endpoint for sending incident communications.
    You can target specific stakeholders, groups, or audiences.
    """
    # Build stakeholder list from IDs
    stakeholders: list[Stakeholder] = []

    for sid in request.stakeholder_ids:
        if sid in _stakeholders:
            stakeholders.append(_stakeholders[sid])

    for gid in request.stakeholder_group_ids:
        group = _stakeholder_groups.get(gid)
        if group:
            for sid in group.stakeholder_ids:
                if sid in _stakeholders:
                    stakeholders.append(_stakeholders[sid])

    # Filter by audience type if specified
    if request.audience_types:
        stakeholders = [
            s for s in stakeholders
            if s.audience_type in request.audience_types
        ]

    # Build the update
    update = CommunicationUpdate(
        incident_id=request.incident_id,
        subject=request.subject,
        body=request.body,
        body_html=request.body_html,
        audience_type=request.audience_types[0] if request.audience_types else AudienceType.STAKEHOLDER,
        stakeholder_ids=request.stakeholder_ids,
        stakeholder_group_ids=request.stakeholder_group_ids,
        channels=request.channels,
        priority=request.priority,
        scheduled_for=request.scheduled_for,
        template_id=request.template_id,
    )

    # Send the update
    if not request.scheduled_for:
        await delivery.send_update(update, stakeholders)

    # Store the update
    _updates[update.id] = update

    # Update any associated plan
    plan = await scheduler.get_plan(request.incident_id)
    if plan:
        plan.updates.append(update)
        plan.last_update_at = datetime.utcnow()
        plan.total_updates_sent += 1
        await scheduler.record_update_sent(plan.id)

    logger.info(
        "communication_update_sent",
        update_id=update.id,
        incident_id=update.incident_id,
        recipient_count=len(stakeholders),
    )

    return update


@router.post("/updates/broadcast", response_model=CommunicationUpdate)
async def broadcast_update(
    request: BroadcastUpdateRequest,
    delivery: Annotated[ChannelDelivery, Depends(get_delivery)],
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
) -> CommunicationUpdate:
    """Broadcast an update to all stakeholders in a communication plan.

    This is the "one-click send to all stakeholders" endpoint.
    """
    plan = _plans.get(request.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Communication plan not found: {request.plan_id}",
        )

    # Get all stakeholders from the plan
    stakeholders: list[Stakeholder] = []

    for sid in plan.stakeholder_ids:
        if sid in _stakeholders:
            stakeholders.append(_stakeholders[sid])

    for gid in plan.stakeholder_group_ids:
        group = _stakeholder_groups.get(gid)
        if group:
            for sid in group.stakeholder_ids:
                if sid in _stakeholders:
                    stakeholders.append(_stakeholders[sid])

    # Remove duplicates
    seen = set()
    unique_stakeholders = []
    for s in stakeholders:
        if s.id not in seen:
            seen.add(s.id)
            unique_stakeholders.append(s)
    stakeholders = unique_stakeholders

    # Filter excluded audience types
    if request.exclude_audience_types:
        stakeholders = [
            s for s in stakeholders
            if s.audience_type not in request.exclude_audience_types
        ]

    # Build the update
    update = CommunicationUpdate(
        incident_id=plan.incident_id,
        plan_id=plan.id,
        subject=request.subject,
        body=request.body,
        body_html=request.body_html,
        audience_type=AudienceType.STAKEHOLDER,
        priority=request.priority,
        template_id=request.template_id,
    )

    # Determine channels based on stakeholder preferences
    all_channels: set[DeliveryChannel] = set()
    for s in stakeholders:
        all_channels.update(s.preferred_channels)
    update.channels = list(all_channels)

    # Send the update
    await delivery.send_update(update, stakeholders)

    # Store and update plan
    _updates[update.id] = update
    plan.updates.append(update)
    plan.last_update_at = datetime.utcnow()
    plan.total_updates_sent += 1
    await scheduler.record_update_sent(plan.id)

    logger.info(
        "broadcast_update_sent",
        update_id=update.id,
        plan_id=plan.id,
        recipient_count=len(stakeholders),
        channels=list(all_channels),
    )

    return update


@router.get("/updates/{update_id}", response_model=CommunicationUpdate)
async def get_update(update_id: str) -> CommunicationUpdate:
    """Get a communication update by ID."""
    update = _updates.get(update_id)
    if not update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Update not found: {update_id}",
        )
    return update


# ============================================================================
# Template Endpoints
# ============================================================================


@router.get("/templates", response_model=list[CommunicationTemplate])
async def list_templates(
    templates: Annotated[TemplateLibrary, Depends(get_templates)],
    audience_type: AudienceType | None = None,
    category: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[CommunicationTemplate]:
    """List available communication templates."""
    template_list, _ = await templates.list_templates(
        audience_type=audience_type,
        category=category,
        limit=limit,
        offset=offset,
    )
    return template_list


@router.get("/templates/{template_id}", response_model=CommunicationTemplate)
async def get_template(
    template_id: str,
    templates: Annotated[TemplateLibrary, Depends(get_templates)],
) -> CommunicationTemplate:
    """Get a template by ID."""
    template = await templates.get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template not found: {template_id}",
        )
    return template


@router.post("/templates/{template_id}/render", response_model=RenderedTemplate)
async def render_template(
    template_id: str,
    variables: dict[str, str],
    templates: Annotated[TemplateLibrary, Depends(get_templates)],
) -> RenderedTemplate:
    """Render a template with provided variables.

    Pass a JSON body with variables like:
    {
        "incident_id": "INC-001",
        "incident_title": "Database outage",
        "severity": "critical",
        "service": "payments-api",
        "impact": "Customers unable to process payments"
    }
    """
    rendered = await templates.render_template(template_id, variables)
    if not rendered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to render template: {template_id}",
        )
    return rendered


# ============================================================================
# Reminder Endpoints
# ============================================================================


@router.post("/plans/{plan_id}/reminders/pause")
async def pause_reminders(
    plan_id: str,
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
) -> dict:
    """Pause update reminders for a plan."""
    success = await scheduler.pause_reminders(plan_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan not found: {plan_id}",
        )
    return {"status": "paused", "plan_id": plan_id}


@router.post("/plans/{plan_id}/reminders/resume")
async def resume_reminders(
    plan_id: str,
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
) -> dict:
    """Resume update reminders for a plan."""
    success = await scheduler.resume_reminders(plan_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan not found: {plan_id}",
        )
    return {"status": "resumed", "plan_id": plan_id}


@router.post("/plans/{plan_id}/reminders/interval")
async def set_reminder_interval(
    plan_id: str,
    interval_minutes: int = Query(ge=5, le=120),
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
) -> dict:
    """Set the reminder interval for a plan."""
    success = await scheduler.set_reminder_interval(plan_id, interval_minutes)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan not found: {plan_id}",
        )
    return {
        "status": "updated",
        "plan_id": plan_id,
        "interval_minutes": interval_minutes,
    }


@router.get("/plans/{plan_id}/reminders/history")
async def get_reminder_history(
    plan_id: str,
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Get reminder history for a plan."""
    reminders, total = await scheduler.get_reminder_history(
        plan_id=plan_id,
        limit=limit,
        offset=offset,
    )
    return {
        "reminders": [r.model_dump() for r in reminders],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ============================================================================
# Audit Log Endpoints
# ============================================================================


@router.get("/audit", response_model=CommunicationAuditListResponse)
async def get_audit_log(
    delivery: Annotated[ChannelDelivery, Depends(get_delivery)],
    incident_id: str | None = None,
    update_id: str | None = None,
    channel: DeliveryChannel | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> CommunicationAuditListResponse:
    """Get communication audit log.

    Returns a log of all communication events including:
    - Updates sent
    - Delivery successes/failures per channel
    - Recipient counts
    """
    entries, total = await delivery.get_audit_log(
        incident_id=incident_id,
        update_id=update_id,
        channel=channel,
        limit=limit,
        offset=offset,
    )
    return CommunicationAuditListResponse(
        entries=entries,
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Statistics Endpoints
# ============================================================================


@router.get("/stats")
async def get_communication_stats(
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
    delivery: Annotated[ChannelDelivery, Depends(get_delivery)],
) -> dict:
    """Get communication statistics."""
    scheduler_stats = scheduler.get_stats()
    channels = delivery.get_available_channels()

    return {
        "total_stakeholders": len(_stakeholders),
        "total_groups": len(_stakeholder_groups),
        "active_plans": scheduler_stats["active_plans"],
        "total_updates_sent": len(_updates),
        "reminders_sent": scheduler_stats["total_reminders_sent"],
        "available_channels": [c.value for c in channels],
        "scheduler": {
            "running": scheduler_stats["running"],
            "check_interval_seconds": scheduler_stats["check_interval_seconds"],
            "last_check_at": scheduler_stats["last_check_at"],
        },
    }


@router.get("/stats/overdue-plans")
async def get_overdue_plans(
    scheduler: Annotated[UpdateScheduler, Depends(get_scheduler)],
) -> dict:
    """Get plans that are overdue for an update."""
    overdue = await scheduler.get_overdue_plans()
    return {
        "count": len(overdue),
        "plans": [
            {
                "id": p.id,
                "incident_id": p.incident_id,
                "incident_title": p.incident_title,
                "minutes_since_update": p.minutes_since_last_update,
                "interval_minutes": p.auto_reminder_interval_minutes,
            }
            for p in overdue
        ],
    }
