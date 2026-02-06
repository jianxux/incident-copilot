"""API routes for managing escalation policies and rules."""

from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from .engine import EscalationEngine, get_escalation_engine
from .models import (
    AuditListResponse,
    CreateMaintenanceWindowRequest,
    CreatePolicyRequest,
    CreateRuleRequest,
    EscalationPolicy,
    EscalationRule,
    EscalationStep,
    MaintenanceWindow,
    PolicyListResponse,
    RuleListResponse,
    ServiceTier,
    UpdatePolicyRequest,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/escalation", tags=["escalation"])


async def get_engine() -> EscalationEngine:
    """Dependency to get the escalation engine."""
    return await get_escalation_engine()


# ============================================================================
# Policy Endpoints
# ============================================================================


@router.post("/policies", response_model=EscalationPolicy, status_code=status.HTTP_201_CREATED)
async def create_policy(
    request: CreatePolicyRequest,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> EscalationPolicy:
    """Create a new escalation policy.

    Escalation policies define multi-step escalation chains for incidents.
    Each step triggers after a specified delay with its own actions.

    Example policy:
    - Step 1 (5 min): Page primary on-call
    - Step 2 (15 min): Page secondary on-call
    - Step 3 (30 min): Page engineering manager
    """
    policy = EscalationPolicy(
        name=request.name,
        description=request.description,
        service_id=request.service_id,
        service_pattern=request.service_pattern,
        team_id=request.team_id,
        service_tier=request.service_tier,
        steps=request.steps,
        primary_responder=request.primary_responder,
        secondary_responder=request.secondary_responder,
        manager=request.manager,
        skip_during_maintenance=request.skip_during_maintenance,
        business_hours_only=request.business_hours_only,
    )

    created = await engine.create_policy(policy)
    logger.info("api_policy_created", policy_id=created.id)
    return created


@router.get("/policies", response_model=PolicyListResponse)
async def list_policies(
    engine: Annotated[EscalationEngine, Depends(get_engine)],
    tenant_id: str | None = None,
    service_id: str | None = None,
    team_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PolicyListResponse:
    """List escalation policies with optional filters."""
    policies, total = await engine.list_policies(
        tenant_id=tenant_id,
        service_id=service_id,
        team_id=team_id,
        limit=limit,
        offset=offset,
    )
    return PolicyListResponse(
        policies=policies,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/policies/{policy_id}", response_model=EscalationPolicy)
async def get_policy(
    policy_id: str,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> EscalationPolicy:
    """Get an escalation policy by ID."""
    policy = await engine.get_policy(policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )
    return policy


@router.patch("/policies/{policy_id}", response_model=EscalationPolicy)
async def update_policy(
    policy_id: str,
    request: UpdatePolicyRequest,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> EscalationPolicy:
    """Update an existing escalation policy."""
    updates = request.model_dump(exclude_unset=True)
    policy = await engine.update_policy(policy_id, updates)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )
    logger.info("api_policy_updated", policy_id=policy_id)
    return policy


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: str,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> None:
    """Delete an escalation policy."""
    deleted = await engine.delete_policy(policy_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )
    logger.info("api_policy_deleted", policy_id=policy_id)


@router.post("/policies/{policy_id}/enable", response_model=EscalationPolicy)
async def enable_policy(
    policy_id: str,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> EscalationPolicy:
    """Enable an escalation policy."""
    policy = await engine.update_policy(policy_id, {"enabled": True})
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )
    return policy


@router.post("/policies/{policy_id}/disable", response_model=EscalationPolicy)
async def disable_policy(
    policy_id: str,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> EscalationPolicy:
    """Disable an escalation policy."""
    policy = await engine.update_policy(policy_id, {"enabled": False})
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy not found: {policy_id}",
        )
    return policy


# ============================================================================
# Rule Endpoints
# ============================================================================


@router.post("/rules", response_model=EscalationRule, status_code=status.HTTP_201_CREATED)
async def create_rule(
    request: CreateRuleRequest,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> EscalationRule:
    """Create a new escalation rule.

    Rules are standalone condition/action pairs that can match incidents
    based on service pattern, severity, team, etc. Unlike policies, rules
    don't have multi-step escalation chains.
    """
    rule = EscalationRule(
        name=request.name,
        description=request.description,
        priority=request.priority,
        service_pattern=request.service_pattern,
        team_id=request.team_id,
        severity_filter=request.severity_filter,
        conditions=request.conditions,
        actions=request.actions,
    )

    created = await engine.create_rule(rule)
    logger.info("api_rule_created", rule_id=created.id)
    return created


@router.get("/rules", response_model=RuleListResponse)
async def list_rules(
    engine: Annotated[EscalationEngine, Depends(get_engine)],
    enabled_only: bool = True,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> RuleListResponse:
    """List escalation rules."""
    rules, total = await engine.list_rules(
        enabled_only=enabled_only,
        limit=limit,
        offset=offset,
    )
    return RuleListResponse(
        rules=rules,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> None:
    """Delete an escalation rule."""
    deleted = await engine.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule not found: {rule_id}",
        )
    logger.info("api_rule_deleted", rule_id=rule_id)


# ============================================================================
# Maintenance Window Endpoints
# ============================================================================


@router.post(
    "/maintenance-windows",
    response_model=MaintenanceWindow,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_window(
    request: CreateMaintenanceWindowRequest,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> MaintenanceWindow:
    """Create a maintenance window.

    During maintenance windows, escalations can be suppressed for
    specified services or teams.
    """
    if request.end_time <= request.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time",
        )

    window = MaintenanceWindow(
        name=request.name,
        description=request.description,
        service_id=request.service_id,
        service_pattern=request.service_pattern,
        team_id=request.team_id,
        start_time=request.start_time,
        end_time=request.end_time,
        timezone=request.timezone,
        suppress_notifications=request.suppress_notifications,
        suppress_pages=request.suppress_pages,
        suppress_escalations=request.suppress_escalations,
    )

    created = await engine.create_maintenance_window(window)
    logger.info("api_maintenance_window_created", window_id=created.id)
    return created


@router.delete(
    "/maintenance-windows/{window_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_maintenance_window(
    window_id: str,
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> None:
    """Delete a maintenance window."""
    deleted = await engine.delete_maintenance_window(window_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Maintenance window not found: {window_id}",
        )
    logger.info("api_maintenance_window_deleted", window_id=window_id)


# ============================================================================
# Audit Log Endpoints
# ============================================================================


@router.get("/audit", response_model=AuditListResponse)
async def get_audit_log(
    engine: Annotated[EscalationEngine, Depends(get_engine)],
    incident_id: str | None = None,
    policy_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> AuditListResponse:
    """Get escalation audit log.

    Returns a log of all escalation events including:
    - Escalations triggered
    - Actions executed (success/failure)
    - Escalations suppressed (with reason)
    """
    entries, total = await engine.get_audit_log(
        incident_id=incident_id,
        policy_id=policy_id,
        limit=limit,
        offset=offset,
    )
    return AuditListResponse(
        entries=entries,
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Stats and Health Endpoints
# ============================================================================


@router.get("/stats")
async def get_escalation_stats(
    engine: Annotated[EscalationEngine, Depends(get_engine)],
) -> dict:
    """Get escalation engine statistics."""
    return await engine.get_stats()


# ============================================================================
# Template Endpoints (Convenience for common patterns)
# ============================================================================


@router.post("/templates/standard-policy", response_model=EscalationPolicy)
async def create_standard_policy(
    engine: Annotated[EscalationEngine, Depends(get_engine)],
    name: str,
    service_pattern: str | None = None,
    team_id: str | None = None,
    service_tier: ServiceTier | None = None,
    primary_responder: str | None = None,
    secondary_responder: str | None = None,
    manager: str | None = None,
) -> EscalationPolicy:
    """Create a standard 3-step escalation policy.

    Creates a policy with:
    - Step 1 (5 min): Notify primary responder
    - Step 2 (15 min): Page secondary responder
    - Step 3 (30 min): Escalate to manager

    This is a convenience endpoint for common escalation patterns.
    """
    from .models import (
        ActionType,
        ConditionOperator,
        ConditionType,
        EscalationAction,
        EscalationCondition,
    )

    policy = EscalationPolicy(
        name=name,
        description="Standard 3-step escalation policy",
        service_pattern=service_pattern,
        team_id=team_id,
        service_tier=service_tier,
        primary_responder=primary_responder,
        secondary_responder=secondary_responder,
        manager=manager,
        steps=[
            EscalationStep(
                step_number=1,
                delay_minutes=5,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.PAGE,
                        params={"message": "Incident requires attention"},
                    ),
                ],
            ),
            EscalationStep(
                step_number=2,
                delay_minutes=15,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.ADD_RESPONDER,
                        params={"message": "Escalating - primary did not respond"},
                    ),
                    EscalationAction(
                        action_type=ActionType.NOTIFY,
                        params={
                            "channel": "slack",
                            "message": "🔺 Incident escalated to secondary responder",
                        },
                    ),
                ],
            ),
            EscalationStep(
                step_number=3,
                delay_minutes=30,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.ESCALATE_TO_MANAGER,
                        params={"method": "page"},
                    ),
                    EscalationAction(
                        action_type=ActionType.UPDATE_SEVERITY,
                        params={"severity": "critical"},
                    ),
                    EscalationAction(
                        action_type=ActionType.POST_TO_CHANNEL,
                        params={
                            "channel": "#incidents",
                            "message": "🚨 Critical escalation - manager paged",
                        },
                    ),
                ],
            ),
        ],
    )

    created = await engine.create_policy(policy)
    logger.info("api_standard_policy_created", policy_id=created.id)
    return created


@router.post("/templates/critical-service-policy", response_model=EscalationPolicy)
async def create_critical_service_policy(
    engine: Annotated[EscalationEngine, Depends(get_engine)],
    name: str,
    service_pattern: str | None = None,
    team_id: str | None = None,
    primary_responder: str | None = None,
    secondary_responder: str | None = None,
    manager: str | None = None,
) -> EscalationPolicy:
    """Create an aggressive escalation policy for critical services.

    Creates a policy with shorter intervals:
    - Step 1 (2 min): Page primary immediately
    - Step 2 (5 min): Page secondary + update severity
    - Step 3 (10 min): Page manager + post to incident channel
    - Step 4 (20 min): Repeat step 3 every 10 minutes

    Use for Tier 0/critical services that require immediate response.
    """
    from .models import (
        ActionType,
        ConditionOperator,
        ConditionType,
        EscalationAction,
        EscalationCondition,
    )

    policy = EscalationPolicy(
        name=name,
        description="Aggressive escalation for critical services",
        service_pattern=service_pattern,
        team_id=team_id,
        service_tier=ServiceTier.CRITICAL,
        primary_responder=primary_responder,
        secondary_responder=secondary_responder,
        manager=manager,
        steps=[
            EscalationStep(
                step_number=1,
                delay_minutes=2,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.PAGE,
                        params={"message": "🚨 CRITICAL: Immediate response required"},
                    ),
                    EscalationAction(
                        action_type=ActionType.POST_TO_CHANNEL,
                        params={
                            "channel": "#critical-incidents",
                            "message": "🚨 Critical incident opened",
                        },
                    ),
                ],
            ),
            EscalationStep(
                step_number=2,
                delay_minutes=5,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.ADD_RESPONDER,
                        params={"message": "Primary non-responsive - escalating"},
                    ),
                    EscalationAction(
                        action_type=ActionType.UPDATE_SEVERITY,
                        params={"severity": "critical"},
                    ),
                ],
            ),
            EscalationStep(
                step_number=3,
                delay_minutes=10,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.ESCALATE_TO_MANAGER,
                        params={"method": "page"},
                    ),
                    EscalationAction(
                        action_type=ActionType.POST_TO_CHANNEL,
                        params={
                            "channel": "#leadership",
                            "message": "⚠️ Critical incident - manager escalation",
                        },
                    ),
                ],
            ),
            EscalationStep(
                step_number=4,
                delay_minutes=20,
                conditions=[
                    EscalationCondition(
                        condition_type=ConditionType.UNACKNOWLEDGED,
                        operator=ConditionOperator.EQUALS,
                        value=True,
                    ),
                ],
                actions=[
                    EscalationAction(
                        action_type=ActionType.PAGE,
                        params={"message": "🔴 CRITICAL: Repeated escalation"},
                    ),
                ],
                repeat=True,
                repeat_interval_minutes=10,
            ),
        ],
    )

    created = await engine.create_policy(policy)
    logger.info("api_critical_policy_created", policy_id=created.id)
    return created
