"""
Gamification API Routes
=======================

FastAPI routes for achievements, badges, points, and leaderboards.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .models import (
    Achievement,
    AchievementCategory,
    Badge,
    GamificationSettings,
    Leaderboard,
    LeaderboardMetric,
    LeaderboardPeriod,
    PointTransaction,
    UserAchievement,
    UserBadge,
    UserPoints,
)
from .service import gamification_service


router = APIRouter(prefix="/gamification", tags=["gamification"])


# ==================== Request/Response Models ====================

class AwardPointsRequest(BaseModel):
    """Request to manually award points."""
    user_id: UUID
    points: int = Field(..., description="Points to award (can be negative)")
    reason: str = Field(..., description="Reason for the award")


class AwardBadgeRequest(BaseModel):
    """Request to manually award a badge."""
    user_id: UUID
    badge_id: UUID
    reason: Optional[str] = None


class CheckAchievementsRequest(BaseModel):
    """Request to check achievements with metrics."""
    user_id: UUID
    metrics: dict[str, int] = Field(..., description="Metric name -> current value")


class UpdateSettingsRequest(BaseModel):
    """Request to update gamification settings."""
    is_enabled: bool = True
    show_leaderboards: bool = True
    show_badges: bool = True
    show_points: bool = True
    anonymous_leaderboards: bool = False
    opt_out_allowed: bool = True
    point_multiplier: float = 1.0
    notify_on_achievement: bool = True
    notify_on_leaderboard_change: bool = True
    weekly_summary: bool = True


class UserProfileResponse(BaseModel):
    """User's complete gamification profile."""
    user_id: UUID
    points: UserPoints
    badges: list[UserBadge]
    achievements: list[UserAchievement]
    recent_transactions: list[PointTransaction]


class LeaderboardResponse(BaseModel):
    """Leaderboard response with additional metadata."""
    leaderboard: Leaderboard
    user_rank: Optional[int] = None
    user_entry: Optional[dict] = None


# ==================== Points Routes ====================

@router.get("/users/{user_id}/points", response_model=UserPoints)
async def get_user_points(user_id: UUID) -> UserPoints:
    """
    Get user's current point balance and level.
    
    Returns total points, current level, and period-specific points.
    """
    return await gamification_service.get_user_points(user_id)


@router.get("/users/{user_id}/points/history", response_model=list[PointTransaction])
async def get_point_history(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[PointTransaction]:
    """
    Get user's point transaction history.
    
    Returns recent point awards and deductions with reasons.
    """
    return await gamification_service.get_point_history(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


@router.post("/points/award", response_model=PointTransaction)
async def award_points(request: AwardPointsRequest) -> PointTransaction:
    """
    Manually award points to a user (admin only).
    
    Use for special recognitions or corrections.
    """
    return await gamification_service.award_points(
        user_id=request.user_id,
        points=request.points,
        reason=request.reason,
        source_type="manual",
    )


# ==================== Achievement Routes ====================

@router.get("/achievements", response_model=list[Achievement])
async def list_achievements(
    category: Optional[AchievementCategory] = None,
    include_hidden: bool = False,
) -> list[Achievement]:
    """
    List all available achievements.
    
    Optionally filter by category.
    """
    achievements = list(gamification_service._achievements.values())
    
    if category:
        achievements = [a for a in achievements if a.category == category]
    
    if not include_hidden:
        achievements = [a for a in achievements if not a.is_hidden]
    
    return achievements


@router.get("/users/{user_id}/achievements", response_model=list[UserAchievement])
async def get_user_achievements(
    user_id: UUID,
    include_locked: bool = True,
) -> list[UserAchievement]:
    """
    Get user's achievement progress.
    
    Returns all achievements with progress percentages.
    """
    return await gamification_service.get_user_achievements(
        user_id=user_id,
        include_locked=include_locked,
    )


@router.post("/achievements/check", response_model=list[Achievement])
async def check_achievements(request: CheckAchievementsRequest) -> list[Achievement]:
    """
    Check and unlock achievements based on current metrics.
    
    Pass a dict of metric names to current values.
    Returns list of newly unlocked achievements.
    """
    return await gamification_service.check_achievements(
        user_id=request.user_id,
        metrics=request.metrics,
    )


# ==================== Badge Routes ====================

@router.get("/badges", response_model=list[Badge])
async def list_badges(
    category: Optional[AchievementCategory] = None,
    include_hidden: bool = False,
) -> list[Badge]:
    """
    List all available badges.
    
    Badges are earned through achievements or special actions.
    """
    return await gamification_service.list_badges(
        category=category,
        include_hidden=include_hidden,
    )


@router.get("/badges/{badge_id}", response_model=Badge)
async def get_badge(badge_id: UUID) -> Badge:
    """Get badge details by ID."""
    badge = await gamification_service.get_badge_details(badge_id)
    if not badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    return badge


@router.get("/users/{user_id}/badges", response_model=list[UserBadge])
async def get_user_badges(user_id: UUID) -> list[UserBadge]:
    """
    Get all badges earned by a user.
    
    Includes award date and reason.
    """
    return await gamification_service.get_user_badges(user_id)


@router.post("/badges/award", response_model=UserBadge)
async def award_badge(request: AwardBadgeRequest) -> UserBadge:
    """
    Manually award a badge to a user (admin only).
    
    Use for special recognitions.
    """
    user_badge = await gamification_service.award_badge(
        user_id=request.user_id,
        badge_id=request.badge_id,
        reason=request.reason,
    )
    if not user_badge:
        raise HTTPException(status_code=404, detail="Badge not found")
    return user_badge


# ==================== Leaderboard Routes ====================

@router.get("/leaderboards", response_model=LeaderboardResponse)
async def get_leaderboard(
    metric: LeaderboardMetric = LeaderboardMetric.POINTS_EARNED,
    period: LeaderboardPeriod = LeaderboardPeriod.WEEKLY,
    team_id: Optional[UUID] = None,
    limit: int = Query(10, ge=1, le=100),
    user_id: Optional[UUID] = None,
) -> LeaderboardResponse:
    """
    Get leaderboard rankings.
    
    Supports various metrics and time periods.
    Optionally includes the requesting user's rank.
    """
    leaderboard = await gamification_service.get_leaderboard(
        metric=metric,
        period=period,
        team_id=team_id,
        limit=limit,
    )
    
    response = LeaderboardResponse(leaderboard=leaderboard)
    
    # Find user's rank if requested
    if user_id:
        for entry in leaderboard.entries:
            if entry.user_id == user_id:
                response.user_rank = entry.rank
                response.user_entry = entry.model_dump()
                break
    
    return response


@router.get("/leaderboards/metrics")
async def list_leaderboard_metrics() -> list[dict]:
    """
    List available leaderboard metrics.
    
    Returns metric names with descriptions.
    """
    return [
        {"metric": m.value, "name": m.value.replace("_", " ").title()}
        for m in LeaderboardMetric
    ]


@router.get("/leaderboards/periods")
async def list_leaderboard_periods() -> list[dict]:
    """
    List available leaderboard time periods.
    """
    return [
        {"period": p.value, "name": p.value.replace("_", " ").title()}
        for p in LeaderboardPeriod
    ]


# ==================== User Profile Routes ====================

@router.get("/users/{user_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(user_id: UUID) -> UserProfileResponse:
    """
    Get user's complete gamification profile.
    
    Includes points, badges, achievements, and recent activity.
    """
    points = await gamification_service.get_user_points(user_id)
    badges = await gamification_service.get_user_badges(user_id)
    achievements = await gamification_service.get_user_achievements(user_id)
    transactions = await gamification_service.get_point_history(user_id, limit=10)
    
    return UserProfileResponse(
        user_id=user_id,
        points=points,
        badges=badges,
        achievements=achievements,
        recent_transactions=transactions,
    )


# ==================== Settings Routes ====================

@router.get("/settings/{organization_id}", response_model=GamificationSettings)
async def get_settings(organization_id: UUID) -> GamificationSettings:
    """
    Get gamification settings for an organization.
    """
    return await gamification_service.get_settings(organization_id)


@router.put("/settings/{organization_id}", response_model=GamificationSettings)
async def update_settings(
    organization_id: UUID,
    request: UpdateSettingsRequest,
) -> GamificationSettings:
    """
    Update gamification settings for an organization.
    """
    settings = GamificationSettings(
        organization_id=organization_id,
        **request.model_dump(),
    )
    return await gamification_service.update_settings(organization_id, settings)


# ==================== Event Hooks (Internal) ====================

@router.post("/events/incident-acknowledged")
async def on_incident_acknowledged(
    user_id: UUID,
    incident_id: UUID,
    acknowledgment_time_seconds: int,
) -> dict:
    """
    Internal hook for incident acknowledgment events.
    
    Awards points and checks relevant achievements.
    """
    return await gamification_service.on_incident_acknowledged(
        user_id=user_id,
        incident_id=incident_id,
        acknowledgment_time_seconds=acknowledgment_time_seconds,
    )


@router.post("/events/incident-resolved")
async def on_incident_resolved(
    user_id: UUID,
    incident_id: UUID,
    resolution_time_minutes: int,
    severity: str,
) -> dict:
    """
    Internal hook for incident resolution events.
    
    Awards points based on speed and severity.
    """
    return await gamification_service.on_incident_resolved(
        user_id=user_id,
        incident_id=incident_id,
        resolution_time_minutes=resolution_time_minutes,
        severity=severity,
    )


@router.post("/events/postmortem-written")
async def on_postmortem_written(
    user_id: UUID,
    postmortem_id: UUID,
) -> dict:
    """
    Internal hook for postmortem written events.
    """
    return await gamification_service.on_postmortem_written(
        user_id=user_id,
        postmortem_id=postmortem_id,
    )
