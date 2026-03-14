"""
Gamification Service
====================

Core service for managing achievements, badges, points, and leaderboards.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from .models import (
    LEVEL_THRESHOLDS,
    POINT_VALUES,
    Achievement,
    AchievementCategory,
    Badge,
    BadgeRarity,
    GamificationSettings,
    Leaderboard,
    LeaderboardEntry,
    LeaderboardMetric,
    LeaderboardPeriod,
    PointTransaction,
    UserAchievement,
    UserBadge,
    UserPoints,
)


class GamificationService:
    """
    Service for managing gamification features.

    Handles achievements, badges, points, and leaderboards.
    """

    def __init__(self):
        # In-memory stores (replace with database in production)
        self._achievements: dict[UUID, Achievement] = {}
        self._badges: dict[UUID, Badge] = {}
        self._user_achievements: dict[UUID, list[UserAchievement]] = {}
        self._user_badges: dict[UUID, list[UserBadge]] = {}
        self._user_points: dict[UUID, UserPoints] = {}
        self._point_transactions: list[PointTransaction] = []
        self._settings: dict[UUID, GamificationSettings] = {}
        self._leaderboards: dict[str, Leaderboard] = {}

        # Initialize default achievements and badges
        self._init_defaults()

    def _init_defaults(self) -> None:
        """Initialize default achievements and badges."""
        self._init_default_badges()
        self._init_default_achievements()

    def _init_default_badges(self) -> None:
        """Create default badge definitions."""
        default_badges = [
            Badge(
                name="First Responder",
                description="Acknowledge your first incident",
                icon="🚨",
                rarity=BadgeRarity.COMMON,
                points=50,
                category=AchievementCategory.RESPONSE,
            ),
            Badge(
                name="Speed Demon",
                description="Resolve an incident in under 10 minutes",
                icon="⚡",
                rarity=BadgeRarity.UNCOMMON,
                points=100,
                category=AchievementCategory.RESOLUTION,
            ),
            Badge(
                name="Night Owl",
                description="Resolve 10 incidents between midnight and 6am",
                icon="🦉",
                rarity=BadgeRarity.RARE,
                points=200,
                category=AchievementCategory.RESPONSE,
            ),
            Badge(
                name="Documentation Hero",
                description="Write 10 postmortems",
                icon="📝",
                rarity=BadgeRarity.UNCOMMON,
                points=150,
                category=AchievementCategory.DOCUMENTATION,
            ),
            Badge(
                name="Runbook Master",
                description="Create 5 runbooks",
                icon="📚",
                rarity=BadgeRarity.RARE,
                points=200,
                category=AchievementCategory.DOCUMENTATION,
            ),
            Badge(
                name="Team Player",
                description="Help resolve 25 incidents you weren't assigned",
                icon="🤝",
                rarity=BadgeRarity.RARE,
                points=250,
                category=AchievementCategory.COLLABORATION,
            ),
            Badge(
                name="Streak Master",
                description="Maintain a 30-day on-call streak without SLA breach",
                icon="🔥",
                rarity=BadgeRarity.EPIC,
                points=500,
                category=AchievementCategory.STREAK,
            ),
            Badge(
                name="Incident Commander",
                description="Successfully lead 50 incidents to resolution",
                icon="👨‍✈️",
                rarity=BadgeRarity.EPIC,
                points=500,
                category=AchievementCategory.RESOLUTION,
            ),
            Badge(
                name="Zero Downtime",
                description="Prevent a potential outage through proactive action",
                icon="🛡️",
                rarity=BadgeRarity.LEGENDARY,
                points=1000,
                category=AchievementCategory.PREVENTION,
            ),
            Badge(
                name="Legendary Responder",
                description="Resolve 1000 incidents",
                icon="🏆",
                rarity=BadgeRarity.LEGENDARY,
                points=2000,
                category=AchievementCategory.RESOLUTION,
            ),
        ]

        for badge in default_badges:
            self._badges[badge.id] = badge

    def _init_default_achievements(self) -> None:
        """Create default achievement definitions."""
        default_achievements = [
            # Response achievements
            Achievement(
                name="First Steps",
                description="Acknowledge your first incident",
                category=AchievementCategory.RESPONSE,
                metric="incidents_acknowledged",
                target_value=1,
                points=50,
                tier=1,
            ),
            Achievement(
                name="Quick Draw",
                description="Acknowledge 10 incidents within 1 minute",
                category=AchievementCategory.RESPONSE,
                metric="fast_acknowledgments",
                target_value=10,
                points=100,
                tier=2,
            ),
            # Resolution achievements
            Achievement(
                name="Problem Solver",
                description="Resolve 10 incidents",
                category=AchievementCategory.RESOLUTION,
                metric="incidents_resolved",
                target_value=10,
                points=100,
                tier=1,
            ),
            Achievement(
                name="Veteran Responder",
                description="Resolve 100 incidents",
                category=AchievementCategory.RESOLUTION,
                metric="incidents_resolved",
                target_value=100,
                points=500,
                tier=2,
            ),
            Achievement(
                name="Elite Responder",
                description="Resolve 500 incidents",
                category=AchievementCategory.RESOLUTION,
                metric="incidents_resolved",
                target_value=500,
                points=1000,
                tier=3,
            ),
            # Documentation achievements
            Achievement(
                name="Chronicler",
                description="Write your first postmortem",
                category=AchievementCategory.DOCUMENTATION,
                metric="postmortems_written",
                target_value=1,
                points=50,
                tier=1,
            ),
            Achievement(
                name="Historian",
                description="Write 10 postmortems",
                category=AchievementCategory.DOCUMENTATION,
                metric="postmortems_written",
                target_value=10,
                points=200,
                tier=2,
            ),
            # Collaboration achievements
            Achievement(
                name="Helpful Hand",
                description="Leave 10 helpful comments on incidents",
                category=AchievementCategory.COLLABORATION,
                metric="helpful_comments",
                target_value=10,
                points=100,
                tier=1,
            ),
            Achievement(
                name="Mentor",
                description="Help a new team member resolve their first incident",
                category=AchievementCategory.COLLABORATION,
                metric="mentored_engineers",
                target_value=1,
                points=150,
                tier=1,
            ),
            # Streak achievements
            Achievement(
                name="Consistent",
                description="Complete 7 days on-call without SLA breach",
                category=AchievementCategory.STREAK,
                metric="sla_streak_days",
                target_value=7,
                points=100,
                tier=1,
            ),
            Achievement(
                name="Reliable",
                description="Complete 30 days on-call without SLA breach",
                category=AchievementCategory.STREAK,
                metric="sla_streak_days",
                target_value=30,
                points=500,
                tier=2,
            ),
        ]

        for achievement in default_achievements:
            self._achievements[achievement.id] = achievement

    # ==================== Points Management ====================

    async def award_points(
        self,
        user_id: UUID,
        points: int,
        reason: str,
        source_type: str,
        source_id: UUID | None = None,
    ) -> PointTransaction:
        """
        Award points to a user.

        Args:
            user_id: User to award points to
            points: Number of points (can be negative for deductions)
            reason: Description of why points were awarded
            source_type: Type of source (incident, achievement, badge, manual)
            source_id: Optional ID of the source entity

        Returns:
            The point transaction record
        """
        # Create transaction
        transaction = PointTransaction(
            user_id=user_id,
            points=points,
            reason=reason,
            source_type=source_type,
            source_id=source_id,
        )
        self._point_transactions.append(transaction)

        # Update user points
        user_points = await self.get_user_points(user_id)
        user_points.total_points += points
        user_points.weekly_points += points
        user_points.monthly_points += points
        user_points.quarterly_points += points
        user_points.yearly_points += points

        # Update level
        user_points.current_level = self._calculate_level(user_points.total_points)
        user_points.points_to_next_level = self._points_to_next_level(
            user_points.total_points,
            user_points.current_level,
        )
        user_points.updated_at = datetime.now(UTC)

        self._user_points[user_id] = user_points

        return transaction

    async def get_user_points(self, user_id: UUID) -> UserPoints:
        """Get user's point balance, creating if necessary."""
        if user_id not in self._user_points:
            self._user_points[user_id] = UserPoints(user_id=user_id)
        return self._user_points[user_id]

    def _calculate_level(self, total_points: int) -> int:
        """Calculate level based on total points."""
        for level, threshold in enumerate(LEVEL_THRESHOLDS, start=1):
            if total_points < threshold:
                return max(1, level - 1)
        return len(LEVEL_THRESHOLDS)

    def _points_to_next_level(self, total_points: int, current_level: int) -> int:
        """Calculate points needed for next level."""
        if current_level >= len(LEVEL_THRESHOLDS):
            return 0  # Max level
        next_threshold = LEVEL_THRESHOLDS[current_level]
        return max(0, next_threshold - total_points)

    async def get_point_history(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PointTransaction]:
        """Get user's point transaction history."""
        user_transactions = [
            t for t in self._point_transactions if t.user_id == user_id
        ]
        # Sort by most recent first
        user_transactions.sort(key=lambda t: t.created_at, reverse=True)
        return user_transactions[offset : offset + limit]

    # ==================== Achievements ====================

    async def check_achievements(
        self,
        user_id: UUID,
        metrics: dict[str, int],
    ) -> list[Achievement]:
        """
        Check and unlock achievements based on current metrics.

        Args:
            user_id: User to check achievements for
            metrics: Dict of metric_name -> current_value

        Returns:
            List of newly unlocked achievements
        """
        unlocked = []

        for achievement in self._achievements.values():
            if not achievement.is_active:
                continue

            # Check if already unlocked
            user_achievement = await self._get_user_achievement(user_id, achievement.id)
            if user_achievement and user_achievement.is_unlocked:
                continue

            # Check if metric matches
            if achievement.metric not in metrics:
                continue

            current_value = metrics[achievement.metric]

            # Create or update user achievement
            if not user_achievement:
                user_achievement = UserAchievement(
                    user_id=user_id,
                    achievement_id=achievement.id,
                    current_value=current_value,
                    target_value=achievement.target_value,
                )
            else:
                user_achievement.current_value = current_value

            # Calculate progress
            user_achievement.progress_percent = min(
                100.0,
                (current_value / achievement.target_value) * 100,
            )

            # Check if unlocked
            if self._check_achievement_criteria(current_value, achievement):
                user_achievement.is_unlocked = True
                user_achievement.unlocked_at = datetime.now(UTC)
                unlocked.append(achievement)

                # Award points
                await self.award_points(
                    user_id=user_id,
                    points=achievement.points,
                    reason=f"Achievement unlocked: {achievement.name}",
                    source_type="achievement",
                    source_id=achievement.id,
                )

                # Award badge if linked
                if achievement.badge_id:
                    await self.award_badge(
                        user_id=user_id,
                        badge_id=achievement.badge_id,
                        reason=f"Achievement: {achievement.name}",
                    )

            user_achievement.updated_at = datetime.now(UTC)
            await self._save_user_achievement(user_achievement)

        return unlocked

    def _check_achievement_criteria(
        self,
        current_value: int,
        achievement: Achievement,
    ) -> bool:
        """Check if achievement criteria is met."""
        target = achievement.target_value
        comparison = achievement.comparison

        if comparison == ">=":
            return current_value >= target
        elif comparison == ">":
            return current_value > target
        elif comparison == "==":
            return current_value == target
        elif comparison == "<=":
            return current_value <= target
        elif comparison == "<":
            return current_value < target
        return False

    async def _get_user_achievement(
        self,
        user_id: UUID,
        achievement_id: UUID,
    ) -> UserAchievement | None:
        """Get user's progress on a specific achievement."""
        user_achievements = self._user_achievements.get(user_id, [])
        for ua in user_achievements:
            if ua.achievement_id == achievement_id:
                return ua
        return None

    async def _save_user_achievement(self, user_achievement: UserAchievement) -> None:
        """Save user achievement progress."""
        user_id = user_achievement.user_id
        if user_id not in self._user_achievements:
            self._user_achievements[user_id] = []

        # Update existing or add new
        achievements = self._user_achievements[user_id]
        for i, ua in enumerate(achievements):
            if ua.achievement_id == user_achievement.achievement_id:
                achievements[i] = user_achievement
                return
        achievements.append(user_achievement)

    async def get_user_achievements(
        self,
        user_id: UUID,
        include_locked: bool = True,
    ) -> list[UserAchievement]:
        """Get all of a user's achievements."""
        achievements = self._user_achievements.get(user_id, [])
        if not include_locked:
            achievements = [a for a in achievements if a.is_unlocked]
        return achievements

    # ==================== Badges ====================

    async def award_badge(
        self,
        user_id: UUID,
        badge_id: UUID,
        reason: str | None = None,
    ) -> UserBadge | None:
        """
        Award a badge to a user.

        Args:
            user_id: User to award badge to
            badge_id: Badge to award
            reason: Optional reason for the award

        Returns:
            The user badge record, or None if badge doesn't exist
        """
        badge = self._badges.get(badge_id)
        if not badge:
            return None

        # Check if already has badge
        user_badges = self._user_badges.get(user_id, [])
        for ub in user_badges:
            if ub.badge_id == badge_id:
                return ub  # Already has it

        # Award badge
        user_badge = UserBadge(
            user_id=user_id,
            badge_id=badge_id,
            awarded_for=reason,
        )

        if user_id not in self._user_badges:
            self._user_badges[user_id] = []
        self._user_badges[user_id].append(user_badge)

        # Award badge points
        await self.award_points(
            user_id=user_id,
            points=badge.points,
            reason=f"Badge earned: {badge.name}",
            source_type="badge",
            source_id=badge_id,
        )

        # Update user points stats
        user_points = await self.get_user_points(user_id)
        user_points.badges_earned += 1

        return user_badge

    async def get_user_badges(self, user_id: UUID) -> list[UserBadge]:
        """Get all badges a user has earned."""
        return self._user_badges.get(user_id, [])

    async def get_badge_details(self, badge_id: UUID) -> Badge | None:
        """Get badge definition by ID."""
        return self._badges.get(badge_id)

    async def list_badges(
        self,
        category: AchievementCategory | None = None,
        include_hidden: bool = False,
    ) -> list[Badge]:
        """List all available badges."""
        badges = list(self._badges.values())

        if category:
            badges = [b for b in badges if b.category == category]

        if not include_hidden:
            badges = [b for b in badges if not b.is_hidden]

        return badges

    # ==================== Leaderboards ====================

    async def get_leaderboard(
        self,
        metric: LeaderboardMetric,
        period: LeaderboardPeriod = LeaderboardPeriod.WEEKLY,
        team_id: UUID | None = None,
        limit: int = 10,
    ) -> Leaderboard:
        """
        Get leaderboard rankings.

        Args:
            metric: Metric to rank by
            period: Time period for the leaderboard
            team_id: Optional team filter
            limit: Maximum entries to return

        Returns:
            Leaderboard with ranked entries
        """
        # Calculate period dates
        now = datetime.now(UTC)
        period_start, period_end = self._calculate_period_dates(period, now)

        # Build cache key

        # Create leaderboard
        leaderboard = Leaderboard(
            name=f"{metric.value.replace('_', ' ').title()} - {period.value.title()}",
            metric=metric,
            period=period,
            team_id=team_id,
            period_start=period_start,
            period_end=period_end,
        )

        # Get entries based on metric
        entries = await self._calculate_leaderboard_entries(
            metric=metric,
            period_start=period_start,
            period_end=period_end,
            team_id=team_id,
            limit=limit,
        )

        leaderboard.entries = entries
        leaderboard.total_participants = len(entries)

        return leaderboard

    def _calculate_period_dates(
        self,
        period: LeaderboardPeriod,
        now: datetime,
    ) -> tuple[datetime, datetime]:
        """Calculate start and end dates for a period."""
        if period == LeaderboardPeriod.WEEKLY:
            # Start of week (Monday)
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=7)
        elif period == LeaderboardPeriod.MONTHLY:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                end = start.replace(year=now.year + 1, month=1)
            else:
                end = start.replace(month=now.month + 1)
        elif period == LeaderboardPeriod.QUARTERLY:
            quarter = (now.month - 1) // 3
            start_month = quarter * 3 + 1
            start = now.replace(
                month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            if start_month + 3 > 12:
                end = start.replace(year=now.year + 1, month=(start_month + 3 - 12))
            else:
                end = start.replace(month=start_month + 3)
        elif period == LeaderboardPeriod.YEARLY:
            start = now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            end = start.replace(year=now.year + 1)
        else:  # ALL_TIME
            start = datetime(2000, 1, 1)
            end = now + timedelta(days=365 * 100)

        return start, end

    async def _calculate_leaderboard_entries(
        self,
        metric: LeaderboardMetric,
        period_start: datetime,
        period_end: datetime,
        team_id: UUID | None,
        limit: int,
    ) -> list[LeaderboardEntry]:
        """Calculate leaderboard entries for a metric."""
        # In production, this would query the database
        # For now, return based on user points
        entries = []

        if metric == LeaderboardMetric.POINTS_EARNED:
            # Rank by points earned in period
            for user_id, points in self._user_points.items():
                if points.weekly_points > 0:  # Simple filter
                    entries.append(
                        {
                            "user_id": user_id,
                            "value": points.weekly_points,
                        }
                    )

        # Sort by value descending
        entries.sort(key=lambda x: x["value"], reverse=True)
        entries = entries[:limit]

        # Convert to LeaderboardEntry
        result = []
        for rank, entry in enumerate(entries, start=1):
            result.append(
                LeaderboardEntry(
                    rank=rank,
                    user_id=entry["user_id"],
                    user_name=f"User {entry['user_id']}",  # Would lookup name
                    value=entry["value"],
                    formatted_value=str(int(entry["value"])),
                )
            )

        return result

    # ==================== Action Handlers ====================

    async def on_incident_acknowledged(
        self,
        user_id: UUID,
        incident_id: UUID,
        acknowledgment_time_seconds: int,
    ) -> dict:
        """
        Handle incident acknowledgment event.

        Awards points and checks achievements.
        """
        # Award base points
        await self.award_points(
            user_id=user_id,
            points=POINT_VALUES["incident_acknowledged"],
            reason="Acknowledged incident",
            source_type="incident",
            source_id=incident_id,
        )

        # Check for fast acknowledgment bonus
        if acknowledgment_time_seconds <= 60:
            await self.award_points(
                user_id=user_id,
                points=10,  # Bonus for fast response
                reason="Fast acknowledgment (under 1 minute)",
                source_type="incident",
                source_id=incident_id,
            )

        return {"points_awarded": POINT_VALUES["incident_acknowledged"]}

    async def on_incident_resolved(
        self,
        user_id: UUID,
        incident_id: UUID,
        resolution_time_minutes: int,
        severity: str,
    ) -> dict:
        """
        Handle incident resolution event.

        Awards points based on speed and severity.
        """
        points = POINT_VALUES["incident_resolved"]

        # Bonus for fast resolution
        if resolution_time_minutes <= 15:
            points = POINT_VALUES["incident_resolved_fast"]

        # Bonus for critical incidents
        if severity in ["P1", "critical", "high"]:
            points = POINT_VALUES["incident_resolved_critical"]

        await self.award_points(
            user_id=user_id,
            points=points,
            reason=f"Resolved {severity} incident",
            source_type="incident",
            source_id=incident_id,
        )

        return {"points_awarded": points}

    async def on_postmortem_written(
        self,
        user_id: UUID,
        postmortem_id: UUID,
    ) -> dict:
        """Handle postmortem written event."""
        points = POINT_VALUES["postmortem_written"]

        await self.award_points(
            user_id=user_id,
            points=points,
            reason="Wrote postmortem",
            source_type="postmortem",
            source_id=postmortem_id,
        )

        return {"points_awarded": points}

    # ==================== Settings ====================

    async def get_settings(self, organization_id: UUID) -> GamificationSettings:
        """Get gamification settings for an organization."""
        if organization_id not in self._settings:
            self._settings[organization_id] = GamificationSettings(
                organization_id=organization_id,
            )
        return self._settings[organization_id]

    async def update_settings(
        self,
        organization_id: UUID,
        settings: GamificationSettings,
    ) -> GamificationSettings:
        """Update gamification settings."""
        settings.updated_at = datetime.now(UTC)
        self._settings[organization_id] = settings
        return settings


# Singleton instance
gamification_service = GamificationService()
