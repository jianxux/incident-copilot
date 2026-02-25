"""FastAPI routes for notification preferences."""

from datetime import datetime, UTC
from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ..auth.middleware import _try_supabase_auth
from ..auth.service import auth_service
from .models import (
    ChannelType,
    DigestFrequency,
    NotificationChannel,
    NotificationPayload,
    NotificationRule,
    NotificationType,
    QuietHours,
    Severity,
    UserRole,
)
from .service import NotificationService, get_notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = structlog.get_logger()
security = HTTPBearer(auto_error=False)


# Request/Response Models


class ChannelCreate(BaseModel):
    """Request model for creating a notification channel."""

    type: ChannelType
    address: str
    enabled: bool = True
    priority: int = Field(default=0, ge=0, le=10)
    settings: dict[str, Any] = Field(default_factory=dict)


class ChannelUpdate(BaseModel):
    """Request model for updating a notification channel."""

    enabled: bool | None = None
    address: str | None = None
    priority: int | None = None
    settings: dict[str, Any] | None = None


class RuleCreate(BaseModel):
    """Request model for creating a notification rule."""

    name: str
    enabled: bool = True
    notification_types: list[NotificationType] = Field(default_factory=list)
    min_severity: Severity = Severity.P5
    max_severity: Severity = Severity.P1
    services: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    channels: list[ChannelType] = Field(default_factory=list)
    digest_frequency: DigestFrequency = DigestFrequency.REALTIME


class QuietHoursUpdate(BaseModel):
    """Request model for updating quiet hours."""

    enabled: bool | None = None
    start_time: str | None = None  # HH:MM format
    end_time: str | None = None  # HH:MM format
    timezone: str | None = None
    allow_p1: bool | None = None
    allow_p2: bool | None = None
    weekend_only: bool | None = None


class PreferenceUpdate(BaseModel):
    """Request model for updating preferences."""

    enabled: bool | None = None
    role: UserRole | None = None
    default_digest_frequency: DigestFrequency | None = None
    use_custom_templates: bool | None = None
    template_overrides: dict[str, str] | None = None


class TestNotificationRequest(BaseModel):
    """Request model for testing notifications."""

    channel_type: ChannelType | None = None
    notification_type: NotificationType = NotificationType.INCIDENT_CREATED
    severity: Severity = Severity.P3
    title: str = "Test Notification"
    message: str = "This is a test notification from incident-copilot."


class PreferenceResponse(BaseModel):
    """Response model for notification preferences."""

    user_id: str
    role: UserRole
    enabled: bool
    default_digest_frequency: DigestFrequency
    channels: list[NotificationChannel]
    quiet_hours: QuietHours
    rules: list[NotificationRule]
    use_custom_templates: bool
    created_at: datetime
    updated_at: datetime


class NotificationResult(BaseModel):
    """Response model for notification send results."""

    status: str
    results: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


# Dependency for getting current user (stub - replace with your auth)
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Get the current user ID from auth context."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization",
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    token = credentials.credentials
    session = await auth_service.get_session_by_token(token)
    if session:
        return session.user_id

    ctx = await _try_supabase_auth(token)
    if ctx and ctx.user:
        return ctx.user.id

    logger.warning("notifications_auth_failed")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token",
    )


# Routes


@router.get("/preferences", response_model=PreferenceResponse)
async def get_preferences(
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> PreferenceResponse:
    """Get current user's notification preferences."""
    prefs = await service.preference_store.get(user_id)

    if not prefs:
        # Return default preferences
        prefs = service._create_default_preferences(user_id, UserRole.ENGINEER)
        await service.preference_store.save(prefs)

    return PreferenceResponse(
        user_id=prefs.user_id,
        role=prefs.role,
        enabled=prefs.enabled,
        default_digest_frequency=prefs.default_digest_frequency,
        channels=prefs.channels,
        quiet_hours=prefs.quiet_hours,
        rules=prefs.rules,
        use_custom_templates=prefs.use_custom_templates,
        created_at=prefs.created_at,
        updated_at=prefs.updated_at,
    )


@router.patch("/preferences", response_model=PreferenceResponse)
async def update_preferences(
    updates: PreferenceUpdate,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> PreferenceResponse:
    """Update current user's notification preferences."""
    update_dict = updates.model_dump(exclude_none=True)
    prefs = await service.apply_preferences(user_id, update_dict)

    return PreferenceResponse(
        user_id=prefs.user_id,
        role=prefs.role,
        enabled=prefs.enabled,
        default_digest_frequency=prefs.default_digest_frequency,
        channels=prefs.channels,
        quiet_hours=prefs.quiet_hours,
        rules=prefs.rules,
        use_custom_templates=prefs.use_custom_templates,
        created_at=prefs.created_at,
        updated_at=prefs.updated_at,
    )


@router.get("/preferences/channels", response_model=list[NotificationChannel])
async def list_channels(
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationChannel]:
    """List all notification channels for current user."""
    return await service.get_channels(user_id)


@router.post(
    "/preferences/channels",
    response_model=NotificationChannel,
    status_code=status.HTTP_201_CREATED,
)
async def add_channel(
    channel: ChannelCreate,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationChannel:
    """Add a new notification channel."""
    prefs = await service.preference_store.get(user_id)

    if not prefs:
        prefs = service._create_default_preferences(user_id, UserRole.ENGINEER)

    new_channel = NotificationChannel(
        type=channel.type,
        address=channel.address,
        enabled=channel.enabled,
        priority=channel.priority,
        settings=channel.settings,
    )

    prefs.channels.append(new_channel)
    prefs.updated_at = datetime.now(UTC)
    await service.preference_store.save(prefs)

    return new_channel


@router.patch(
    "/preferences/channels/{channel_index}", response_model=NotificationChannel
)
async def update_channel(
    channel_index: int,
    updates: ChannelUpdate,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationChannel:
    """Update a notification channel by index."""
    prefs = await service.preference_store.get(user_id)

    if not prefs or channel_index >= len(prefs.channels):
        raise HTTPException(status_code=404, detail="Channel not found")

    channel = prefs.channels[channel_index]

    if updates.enabled is not None:
        channel.enabled = updates.enabled
    if updates.address is not None:
        channel.address = updates.address
    if updates.priority is not None:
        channel.priority = updates.priority
    if updates.settings is not None:
        channel.settings.update(updates.settings)

    prefs.updated_at = datetime.now(UTC)
    await service.preference_store.save(prefs)

    return channel


@router.delete(
    "/preferences/channels/{channel_index}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_channel(
    channel_index: int,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """Delete a notification channel by index."""
    prefs = await service.preference_store.get(user_id)

    if not prefs or channel_index >= len(prefs.channels):
        raise HTTPException(status_code=404, detail="Channel not found")

    prefs.channels.pop(channel_index)
    prefs.updated_at = datetime.now(UTC)
    await service.preference_store.save(prefs)


@router.patch("/preferences/quiet-hours", response_model=QuietHours)
async def update_quiet_hours(
    updates: QuietHoursUpdate,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> QuietHours:
    """Update quiet hours settings."""
    from datetime import time as dt_time, UTC

    prefs = await service.preference_store.get(user_id)

    if not prefs:
        prefs = service._create_default_preferences(user_id, UserRole.ENGINEER)

    quiet_hours = prefs.quiet_hours

    if updates.enabled is not None:
        quiet_hours.enabled = updates.enabled
    if updates.start_time is not None:
        h, m = map(int, updates.start_time.split(":"))
        quiet_hours.start_time = dt_time(h, m)
    if updates.end_time is not None:
        h, m = map(int, updates.end_time.split(":"))
        quiet_hours.end_time = dt_time(h, m)
    if updates.timezone is not None:
        quiet_hours.timezone = updates.timezone
    if updates.allow_p1 is not None:
        quiet_hours.allow_p1 = updates.allow_p1
    if updates.allow_p2 is not None:
        quiet_hours.allow_p2 = updates.allow_p2
    if updates.weekend_only is not None:
        quiet_hours.weekend_only = updates.weekend_only

    prefs.updated_at = datetime.now(UTC)
    await service.preference_store.save(prefs)

    return quiet_hours


@router.get("/preferences/rules", response_model=list[NotificationRule])
async def list_rules(
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationRule]:
    """List all notification rules for current user."""
    prefs = await service.preference_store.get(user_id)
    return prefs.rules if prefs else []


@router.post(
    "/preferences/rules",
    response_model=NotificationRule,
    status_code=status.HTTP_201_CREATED,
)
async def add_rule(
    rule: RuleCreate,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationRule:
    """Add a new notification rule."""
    prefs = await service.preference_store.get(user_id)

    if not prefs:
        prefs = service._create_default_preferences(user_id, UserRole.ENGINEER)

    new_rule = NotificationRule(
        id=str(uuid4()),
        name=rule.name,
        enabled=rule.enabled,
        notification_types=rule.notification_types,
        min_severity=rule.min_severity,
        max_severity=rule.max_severity,
        services=rule.services,
        teams=rule.teams,
        tags=rule.tags,
        channels=rule.channels,
        digest_frequency=rule.digest_frequency,
    )

    prefs.rules.append(new_rule)
    prefs.updated_at = datetime.now(UTC)
    await service.preference_store.save(prefs)

    return new_rule


@router.delete("/preferences/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """Delete a notification rule by ID."""
    prefs = await service.preference_store.get(user_id)

    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")

    original_len = len(prefs.rules)
    prefs.rules = [r for r in prefs.rules if r.id != rule_id]

    if len(prefs.rules) == original_len:
        raise HTTPException(status_code=404, detail="Rule not found")

    prefs.updated_at = datetime.now(UTC)
    await service.preference_store.save(prefs)


@router.post("/test", response_model=NotificationResult)
async def test_notification(
    request: TestNotificationRequest,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResult:
    """Send a test notification to the current user."""
    payload = NotificationPayload(
        id=str(uuid4()),
        type=request.notification_type,
        severity=request.severity,
        title=request.title,
        message=request.message,
        incident_id="test-incident-001",
        service="test-service",
        team="test-team",
        data={
            "incident_url": "https://example.com/incidents/test-001",
            "test": True,
        },
    )

    # If specific channel requested, temporarily modify channels
    if request.channel_type:
        prefs = await service.preference_store.get(user_id)
        if prefs:
            matching = [
                c
                for c in prefs.channels
                if c.type == request.channel_type and c.enabled
            ]
            if not matching:
                raise HTTPException(
                    status_code=400,
                    detail=f"No enabled {request.channel_type.value} channel found",
                )

    result = await service.send_notification(user_id, payload, force=True)

    return NotificationResult(
        status=result.get("status", "unknown"),
        results=result.get("results", {}),
        reason=result.get("reason"),
    )


@router.post("/send", response_model=NotificationResult)
async def send_notification(
    payload: NotificationPayload,
    target_user_ids: list[str] | None = None,
    force: bool = False,
    user_id: str = Depends(get_current_user_id),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResult:
    """Send a notification to specified users or current user."""
    targets = target_user_ids or [user_id]

    if len(targets) == 1:
        result = await service.send_notification(targets[0], payload, force=force)
    else:
        result = await service.send_to_multiple(targets, payload)

    return NotificationResult(
        status="completed",
        results=result,
    )


@router.post("/digests/process")
async def process_digests(
    service: NotificationService = Depends(get_notification_service),
) -> dict[str, Any]:
    """Manually trigger digest processing (normally run via scheduler)."""
    results = await service.process_digests()
    return {
        "processed": len(results),
        "results": results,
    }
