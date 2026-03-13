"""Tests for gamification module."""

import uuid
import pytest

from src.gamification.models import (
    Achievement,
    AchievementCategory,
    Badge,
    LeaderboardEntry,
    LeaderboardMetric,
    LeaderboardPeriod,
    UserPoints,
    POINT_VALUES,
    LEVEL_THRESHOLDS,
)
from src.gamification.service import GamificationService


class TestGamificationModels:
    def test_achievement_creation(self):
        a = Achievement(
            name="Fast Resolver",
            description="Resolve an incident in under 5 minutes",
            metric="mttr",
            target_value=300,
            category=AchievementCategory.RESPONSE,
            points=100,
        )
        assert a.name == "Fast Resolver"
        assert a.points == 100

    def test_badge_creation(self):
        b = Badge(name="Gold Responder", icon="🥇", description="Top responder")
        assert b.icon == "🥇"

    def test_user_points_defaults(self):
        uid = uuid.uuid4()
        pts = UserPoints(user_id=uid)
        assert pts.user_id == uid
        assert pts.total_points == 0

    def test_leaderboard_entry(self):
        uid = uuid.uuid4()
        entry = LeaderboardEntry(
            rank=1,
            user_id=uid,
            user_name="Alice",
            value=500.0,
            formatted_value="500",
        )
        assert entry.rank == 1

    def test_point_values_exist(self):
        assert isinstance(POINT_VALUES, dict)
        assert len(POINT_VALUES) > 0

    def test_level_thresholds_exist(self):
        assert isinstance(LEVEL_THRESHOLDS, (list, dict))


class TestGamificationService:
    @pytest.fixture
    def service(self):
        return GamificationService()

    def test_service_instantiation(self, service):
        assert service is not None

    @pytest.mark.asyncio
    async def test_get_user_points(self, service):
        pts = await service.get_user_points(uuid.uuid4())
        assert pts is not None

    @pytest.mark.asyncio
    async def test_get_leaderboard(self, service):
        board = await service.get_leaderboard(LeaderboardMetric.POINTS_EARNED)
        assert board is not None
