"""
Gamification Models
==================

Achievements, badges, and leaderboards for incident response excellence.
Motivates engineers through recognition and friendly competition.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BadgeRarity(StrEnum):
    """Badge rarity levels."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class AchievementCategory(StrEnum):
    """Achievement categories."""

    RESPONSE = "response"  # Fast response achievements
    RESOLUTION = "resolution"  # Quick resolution achievements
    COLLABORATION = "collaboration"  # Teamwork achievements
    DOCUMENTATION = "documentation"  # Postmortem, runbook contributions
    PREVENTION = "prevention"  # Proactive improvements
    STREAK = "streak"  # Consistency achievements
    SPECIAL = "special"  # Special/seasonal achievements


class LeaderboardPeriod(StrEnum):
    """Leaderboard time periods."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ALL_TIME = "all_time"


class LeaderboardMetric(StrEnum):
    """Metrics for leaderboard ranking."""

    INCIDENTS_RESOLVED = "incidents_resolved"
    FASTEST_MTTR = "fastest_mttr"
    FASTEST_MTTA = "fastest_mtta"
    POSTMORTEMS_WRITTEN = "postmortems_written"
    RUNBOOKS_CREATED = "runbooks_created"
    SLA_COMPLIANCE = "sla_compliance"
    HELPFUL_COMMENTS = "helpful_comments"
    POINTS_EARNED = "points_earned"


class Badge(BaseModel):
    """
    Badge definition.

    Badges are visual recognition of specific achievements.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Badge display name")
    description: str = Field(..., description="How to earn this badge")
    icon: str = Field(..., description="Icon identifier or emoji")
    rarity: BadgeRarity = Field(default=BadgeRarity.COMMON)
    points: int = Field(default=10, description="Points awarded with badge")
    category: AchievementCategory = Field(default=AchievementCategory.RESPONSE)

    # Unlock criteria
    achievement_id: UUID | None = Field(None, description="Linked achievement")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = Field(default=True)
    is_hidden: bool = Field(default=False, description="Secret badge")


class Achievement(BaseModel):
    """
    Achievement definition with unlock criteria.

    Achievements track progress toward badges and recognition.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Achievement name")
    description: str = Field(..., description="Achievement description")
    category: AchievementCategory = Field(default=AchievementCategory.RESPONSE)

    # Unlock criteria
    metric: str = Field(..., description="Metric to track")
    target_value: int = Field(..., description="Value needed to unlock")
    comparison: str = Field(default=">=", description="Comparison operator")

    # Rewards
    points: int = Field(default=100, description="Points awarded")
    badge_id: UUID | None = Field(None, description="Badge awarded on unlock")

    # Tiered achievements
    tier: int = Field(default=1, description="Achievement tier (1-5)")
    next_tier_id: UUID | None = Field(None, description="Next tier achievement")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = Field(default=True)
    is_hidden: bool = Field(default=False, description="Secret achievement")


class UserAchievement(BaseModel):
    """
    User's progress toward or completion of an achievement.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(..., description="User ID")
    achievement_id: UUID = Field(..., description="Achievement ID")

    # Progress tracking
    current_value: int = Field(default=0, description="Current progress")
    target_value: int = Field(..., description="Target to unlock")
    progress_percent: float = Field(default=0.0)

    # Unlock status
    is_unlocked: bool = Field(default=False)
    unlocked_at: datetime | None = Field(None)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserBadge(BaseModel):
    """
    Badge awarded to a user.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(..., description="User ID")
    badge_id: UUID = Field(..., description="Badge ID")

    # Award details
    awarded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    awarded_for: str | None = Field(None, description="Specific reason/incident")

    # Display options
    is_featured: bool = Field(default=False, description="Show on profile")
    display_order: int = Field(default=0)


class UserPoints(BaseModel):
    """
    User's point balance and history.
    """

    user_id: UUID = Field(..., description="User ID")
    total_points: int = Field(default=0)
    current_level: int = Field(default=1)
    points_to_next_level: int = Field(default=100)

    # Period-specific points
    weekly_points: int = Field(default=0)
    monthly_points: int = Field(default=0)
    quarterly_points: int = Field(default=0)
    yearly_points: int = Field(default=0)

    # Stats
    achievements_unlocked: int = Field(default=0)
    badges_earned: int = Field(default=0)

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PointTransaction(BaseModel):
    """
    Point award/deduction record.
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID = Field(..., description="User ID")
    points: int = Field(..., description="Points (positive=award, negative=deduction)")
    reason: str = Field(..., description="Reason for transaction")

    # Source
    source_type: str = Field(..., description="incident, achievement, badge, manual")
    source_id: UUID | None = Field(None, description="Related entity ID")

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: UUID | None = Field(None, description="Admin who made manual award")


class LeaderboardEntry(BaseModel):
    """
    Single entry in a leaderboard.
    """

    rank: int = Field(..., description="Current rank")
    user_id: UUID = Field(..., description="User ID")
    user_name: str = Field(..., description="Display name")
    user_avatar: str | None = Field(None)

    # Score
    value: float = Field(..., description="Metric value")
    formatted_value: str = Field(..., description="Human-readable value")

    # Trend
    previous_rank: int | None = Field(None)
    rank_change: int = Field(default=0, description="Positive=moved up")

    # Badges preview
    featured_badges: list[str] = Field(default_factory=list)


class Leaderboard(BaseModel):
    """
    Leaderboard with rankings.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Leaderboard name")
    metric: LeaderboardMetric = Field(...)
    period: LeaderboardPeriod = Field(default=LeaderboardPeriod.WEEKLY)

    # Scope
    organization_id: UUID | None = Field(None)
    team_id: UUID | None = Field(None, description="Team-specific leaderboard")

    # Entries
    entries: list[LeaderboardEntry] = Field(default_factory=list)
    total_participants: int = Field(default=0)

    # Period info
    period_start: datetime = Field(...)
    period_end: datetime = Field(...)

    # Metadata
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GamificationSettings(BaseModel):
    """
    Organization-level gamification settings.
    """

    organization_id: UUID = Field(...)

    # Feature toggles
    is_enabled: bool = Field(default=True)
    show_leaderboards: bool = Field(default=True)
    show_badges: bool = Field(default=True)
    show_points: bool = Field(default=True)

    # Privacy
    anonymous_leaderboards: bool = Field(default=False)
    opt_out_allowed: bool = Field(default=True)

    # Customization
    custom_badge_prefix: str | None = Field(None)
    point_multiplier: float = Field(default=1.0)

    # Notifications
    notify_on_achievement: bool = Field(default=True)
    notify_on_leaderboard_change: bool = Field(default=True)
    weekly_summary: bool = Field(default=True)

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Point values for common actions
POINT_VALUES = {
    "incident_acknowledged": 5,
    "incident_resolved": 20,
    "incident_resolved_fast": 50,  # Under 15 minutes
    "incident_resolved_critical": 100,  # P1 incident
    "postmortem_written": 30,
    "postmortem_reviewed": 10,
    "runbook_created": 40,
    "runbook_updated": 15,
    "helpful_comment": 5,
    "on_call_shift_completed": 25,
    "sla_met": 10,
    "mentor_new_engineer": 50,
    "first_incident_response": 100,  # One-time bonus
}

# Level thresholds
LEVEL_THRESHOLDS = [
    0,  # Level 1
    100,  # Level 2
    300,  # Level 3
    600,  # Level 4
    1000,  # Level 5
    1500,  # Level 6
    2200,  # Level 7
    3000,  # Level 8
    4000,  # Level 9
    5500,  # Level 10
    7500,  # Level 11
    10000,  # Level 12
    15000,  # Level 13
    20000,  # Level 14
    30000,  # Level 15 (max)
]
