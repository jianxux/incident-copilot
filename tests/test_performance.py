"""Tests for performance module."""

import pytest
from datetime import datetime, UTC

from src.performance.models import (
    TeamMetrics,
    PerformanceTier,
    EngineerMetrics,
    BurnoutRisk,
    LeaderboardEntry,
    PerformancePeriod,
)


class TestPerformanceModels:
    def test_performance_period(self):
        p = PerformancePeriod(
            start=datetime(2026, 2, 1, tzinfo=UTC),
            end=datetime(2026, 2, 28, tzinfo=UTC),
        )
        assert p.start.month == 2

    def test_team_metrics_creation(self):
        period = PerformancePeriod(
            start=datetime(2026, 2, 1, tzinfo=UTC),
            end=datetime(2026, 2, 28, tzinfo=UTC),
        )
        m = TeamMetrics(
            team_id="team-1",
            team_name="SRE",
            period=period,
            total_incidents=50,
            mttr_minutes=30.5,
            mtta_minutes=5.2,
        )
        assert m.team_name == "SRE"
        assert m.mttr_minutes == 30.5

    def test_performance_tier_values(self):
        assert PerformanceTier.ELITE
        assert PerformanceTier.HIGH

    def test_burnout_risk_values(self):
        assert BurnoutRisk.LOW
        assert BurnoutRisk.HIGH

    def test_engineer_metrics(self):
        period = PerformancePeriod(
            start=datetime(2026, 2, 1, tzinfo=UTC),
            end=datetime(2026, 2, 7, tzinfo=UTC),
        )
        e = EngineerMetrics(
            engineer_id="eng-1",
            engineer_name="Alice",
            period=period,
            incidents_handled=20,
            avg_mttr_minutes=15.0,
        )
        assert e.incidents_handled == 20

    def test_leaderboard_entry(self):
        entry = LeaderboardEntry(
            rank=1,
            engineer_id="eng-1",
            engineer_name="Alice",
            score=95.5,
            metric_name="mttr",
        )
        assert entry.rank == 1
