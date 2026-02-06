"""Team and individual performance rankings (gamification)."""

from datetime import datetime, timedelta
from enum import Enum

import structlog
from pydantic import BaseModel, Field

from .calculator import PerformanceCalculator
from .models import OnCallStats, ResponderStats

logger = structlog.get_logger()


class LeaderboardType(str, Enum):
    """Types of leaderboards."""

    TOP_RESPONDERS = "top_responders"
    FASTEST_RESPONSE = "fastest_response"
    MOST_RESOLVED = "most_resolved"
    BEST_SLA = "best_sla"
    RISING_STARS = "rising_stars"
    TEAM_RANKINGS = "team_rankings"


class LeaderboardEntry(BaseModel):
    """Single entry in a leaderboard."""

    rank: int
    responder_id: str
    responder_name: str
    team_name: str | None = None
    avatar_url: str | None = None

    # Primary metric for this leaderboard
    primary_value: float
    primary_label: str

    # Secondary metrics
    secondary_metrics: dict[str, float] = Field(default_factory=dict)

    # Score and change
    total_score: int = 0
    rank_change: int | None = None  # Positive = improved, negative = dropped

    # Badges/achievements
    badges: list[str] = Field(default_factory=list)


class Leaderboard(BaseModel):
    """A complete leaderboard."""

    leaderboard_type: LeaderboardType
    title: str
    description: str

    period_start: datetime
    period_end: datetime
    team_name: str | None = None

    entries: list[LeaderboardEntry] = Field(default_factory=list)
    total_participants: int = 0

    generated_at: datetime = Field(default_factory=datetime.utcnow)


class LeaderboardGenerator:
    """Generate various performance leaderboards."""

    # Scoring weights
    SCORE_PER_INCIDENT = 10
    SCORE_PER_RESOLUTION = 25
    SCORE_FAST_ACK_BONUS = 15  # <5 min ack
    SCORE_SLA_COMPLIANCE_BONUS = 20  # Per SLA met
    SCORE_OFF_HOURS_BONUS = 5  # Per off-hours incident

    def __init__(self, calculator: PerformanceCalculator | None = None):
        """Initialize with optional calculator."""
        self.calculator = calculator or PerformanceCalculator()

    def generate_top_responders(
        self,
        oncall_stats: list[OnCallStats],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        limit: int = 10,
        previous_stats: list[OnCallStats] | None = None,
    ) -> Leaderboard:
        """
        Generate top responders leaderboard by total score.

        Args:
            oncall_stats: List of OnCallStats for each responder
            period_start: Start of period
            period_end: End of period
            team_name: Optional team filter
            limit: Maximum entries to return
            previous_stats: Previous period stats for rank change

        Returns:
            Leaderboard with top responders by total score
        """
        # Filter by team if specified
        stats = oncall_stats
        if team_name:
            stats = [s for s in stats if s.team_name == team_name]

        # Calculate scores for each responder
        scored_responders = []
        for stat in stats:
            score = self._calculate_responder_score(stat)
            badges = self._calculate_badges(stat)

            scored_responders.append({
                "stat": stat,
                "score": score,
                "badges": badges,
            })

        # Sort by score descending
        scored_responders.sort(key=lambda x: x["score"], reverse=True)

        # Build previous period lookup for rank change
        prev_ranks = {}
        if previous_stats:
            prev_scored = [
                (s, self._calculate_responder_score(s)) for s in previous_stats
            ]
            prev_scored.sort(key=lambda x: x[1], reverse=True)
            for i, (s, _) in enumerate(prev_scored, 1):
                prev_ranks[s.responder_id] = i

        # Build entries
        entries = []
        for i, item in enumerate(scored_responders[:limit], 1):
            stat = item["stat"]
            prev_rank = prev_ranks.get(stat.responder_id)
            rank_change = (prev_rank - i) if prev_rank else None

            entries.append(
                LeaderboardEntry(
                    rank=i,
                    responder_id=stat.responder_id,
                    responder_name=stat.responder_name,
                    team_name=stat.team_name,
                    primary_value=float(item["score"]),
                    primary_label="Total Score",
                    secondary_metrics={
                        "incidents_handled": float(stat.total_pages),
                        "avg_ack_time_min": stat.avg_ack_time_minutes or 0,
                    },
                    total_score=item["score"],
                    rank_change=rank_change,
                    badges=item["badges"],
                )
            )

        logger.info(
            "top_responders_generated",
            team=team_name,
            entries=len(entries),
        )

        return Leaderboard(
            leaderboard_type=LeaderboardType.TOP_RESPONDERS,
            title="Top Responders",
            description="Responders ranked by total performance score",
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            entries=entries,
            total_participants=len(stats),
        )

    def generate_fastest_response(
        self,
        oncall_stats: list[OnCallStats],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        limit: int = 10,
    ) -> Leaderboard:
        """
        Generate fastest response time leaderboard.

        Args:
            oncall_stats: List of OnCallStats for each responder
            period_start: Start of period
            period_end: End of period
            team_name: Optional team filter
            limit: Maximum entries to return

        Returns:
            Leaderboard with fastest average acknowledgment times
        """
        stats = oncall_stats
        if team_name:
            stats = [s for s in stats if s.team_name == team_name]

        # Filter to responders with ack time data
        stats_with_ack = [s for s in stats if s.avg_ack_time_minutes is not None]

        # Sort by ack time ascending (faster is better)
        stats_with_ack.sort(key=lambda x: x.avg_ack_time_minutes or float("inf"))

        entries = []
        for i, stat in enumerate(stats_with_ack[:limit], 1):
            entries.append(
                LeaderboardEntry(
                    rank=i,
                    responder_id=stat.responder_id,
                    responder_name=stat.responder_name,
                    team_name=stat.team_name,
                    primary_value=stat.avg_ack_time_minutes or 0,
                    primary_label="Avg Ack Time (min)",
                    secondary_metrics={
                        "incidents_handled": float(stat.total_pages),
                        "pages_acknowledged": float(stat.pages_acknowledged),
                    },
                    total_score=self._calculate_responder_score(stat),
                    badges=["⚡ Speed Demon"] if stat.avg_ack_time_minutes and stat.avg_ack_time_minutes < 2 else [],
                )
            )

        return Leaderboard(
            leaderboard_type=LeaderboardType.FASTEST_RESPONSE,
            title="Fastest Response Times",
            description="Responders with the quickest acknowledgment times",
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            entries=entries,
            total_participants=len(stats_with_ack),
        )

    def generate_most_resolved(
        self,
        oncall_stats: list[OnCallStats],
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        limit: int = 10,
    ) -> Leaderboard:
        """
        Generate most incidents resolved leaderboard.

        Args:
            oncall_stats: List of OnCallStats for each responder
            incidents: List of incident dicts to count resolutions
            period_start: Start of period
            period_end: End of period
            team_name: Optional team filter
            limit: Maximum entries to return

        Returns:
            Leaderboard with most incident resolutions
        """
        # Count resolutions per responder
        resolution_counts: dict[str, int] = {}
        for inc in incidents:
            resolved_by = inc.get("resolved_by") or inc.get("responder_id")
            if resolved_by and inc.get("resolved_at"):
                resolved_at = self._parse_datetime(inc.get("resolved_at"))
                if resolved_at and period_start <= resolved_at <= period_end:
                    resolution_counts[resolved_by] = (
                        resolution_counts.get(resolved_by, 0) + 1
                    )

        # Map to stats
        stats_lookup = {s.responder_id: s for s in oncall_stats}
        stats_lookup.update({s.responder_name: s for s in oncall_stats})

        # Filter by team
        if team_name:
            resolution_counts = {
                k: v
                for k, v in resolution_counts.items()
                if stats_lookup.get(k) and stats_lookup[k].team_name == team_name
            }

        # Sort by resolution count
        sorted_responders = sorted(
            resolution_counts.items(), key=lambda x: x[1], reverse=True
        )

        entries = []
        for i, (responder_id, count) in enumerate(sorted_responders[:limit], 1):
            stat = stats_lookup.get(responder_id)
            entries.append(
                LeaderboardEntry(
                    rank=i,
                    responder_id=responder_id,
                    responder_name=stat.responder_name if stat else responder_id,
                    team_name=stat.team_name if stat else None,
                    primary_value=float(count),
                    primary_label="Incidents Resolved",
                    secondary_metrics={
                        "incidents_handled": float(stat.total_pages) if stat else 0,
                        "resolution_rate": (
                            count / stat.total_pages * 100
                            if stat and stat.total_pages > 0
                            else 0
                        ),
                    },
                    total_score=count * self.SCORE_PER_RESOLUTION,
                    badges=["🏆 Problem Solver"] if count >= 10 else [],
                )
            )

        return Leaderboard(
            leaderboard_type=LeaderboardType.MOST_RESOLVED,
            title="Most Incidents Resolved",
            description="Responders who resolved the most incidents",
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            entries=entries,
            total_participants=len(sorted_responders),
        )

    def generate_best_sla(
        self,
        oncall_stats: list[OnCallStats],
        incidents: list[dict],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        limit: int = 10,
    ) -> Leaderboard:
        """
        Generate best SLA compliance leaderboard.

        Args:
            oncall_stats: List of OnCallStats for each responder
            incidents: List of incident dicts
            period_start: Start of period
            period_end: End of period
            team_name: Optional team filter
            limit: Maximum entries to return

        Returns:
            Leaderboard with best SLA compliance rates
        """
        # Calculate SLA compliance per responder
        responder_sla: dict[str, dict] = {}

        for stat in oncall_stats:
            if team_name and stat.team_name != team_name:
                continue

            # Get incidents for this responder
            responder_incidents = [
                inc
                for inc in incidents
                if stat.responder_id in inc.get("assigned_to", [])
                or stat.responder_id == inc.get("responder_id")
                or stat.responder_name in inc.get("assigned_to", [])
            ]

            # Filter by period
            responder_incidents = [
                inc
                for inc in responder_incidents
                if self._in_period(inc, period_start, period_end)
            ]

            if not responder_incidents:
                continue

            # Count SLA met/breached
            sla_met = sum(
                1 for inc in responder_incidents if self._is_sla_met(inc)
            )
            total = len(responder_incidents)
            compliance = sla_met / total * 100

            responder_sla[stat.responder_id] = {
                "stat": stat,
                "sla_met": sla_met,
                "total": total,
                "compliance": compliance,
            }

        # Sort by compliance rate
        sorted_responders = sorted(
            responder_sla.values(), key=lambda x: x["compliance"], reverse=True
        )

        entries = []
        for i, item in enumerate(sorted_responders[:limit], 1):
            stat = item["stat"]
            entries.append(
                LeaderboardEntry(
                    rank=i,
                    responder_id=stat.responder_id,
                    responder_name=stat.responder_name,
                    team_name=stat.team_name,
                    primary_value=item["compliance"],
                    primary_label="SLA Compliance %",
                    secondary_metrics={
                        "sla_met": float(item["sla_met"]),
                        "total_incidents": float(item["total"]),
                    },
                    total_score=int(item["compliance"]),
                    badges=["✅ SLA Champion"] if item["compliance"] >= 95 else [],
                )
            )

        return Leaderboard(
            leaderboard_type=LeaderboardType.BEST_SLA,
            title="Best SLA Compliance",
            description="Responders with the highest SLA compliance rates",
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            entries=entries,
            total_participants=len(sorted_responders),
        )

    def generate_rising_stars(
        self,
        current_stats: list[OnCallStats],
        previous_stats: list[OnCallStats],
        period_start: datetime,
        period_end: datetime,
        team_name: str | None = None,
        limit: int = 10,
    ) -> Leaderboard:
        """
        Generate rising stars leaderboard (most improved).

        Args:
            current_stats: Current period OnCallStats
            previous_stats: Previous period OnCallStats
            period_start: Start of current period
            period_end: End of current period
            team_name: Optional team filter
            limit: Maximum entries to return

        Returns:
            Leaderboard with most improved responders
        """
        # Build previous scores lookup
        prev_scores = {
            s.responder_id: self._calculate_responder_score(s) for s in previous_stats
        }

        # Calculate improvement
        improvements = []
        for stat in current_stats:
            if team_name and stat.team_name != team_name:
                continue

            current_score = self._calculate_responder_score(stat)
            prev_score = prev_scores.get(stat.responder_id, 0)

            if prev_score > 0:
                improvement = (current_score - prev_score) / prev_score * 100
            elif current_score > 0:
                improvement = 100  # New responder with score
            else:
                improvement = 0

            improvements.append({
                "stat": stat,
                "current_score": current_score,
                "prev_score": prev_score,
                "improvement": improvement,
            })

        # Sort by improvement
        improvements.sort(key=lambda x: x["improvement"], reverse=True)

        entries = []
        for i, item in enumerate(improvements[:limit], 1):
            stat = item["stat"]
            if item["improvement"] <= 0:
                continue

            entries.append(
                LeaderboardEntry(
                    rank=i,
                    responder_id=stat.responder_id,
                    responder_name=stat.responder_name,
                    team_name=stat.team_name,
                    primary_value=item["improvement"],
                    primary_label="Score Improvement %",
                    secondary_metrics={
                        "current_score": float(item["current_score"]),
                        "previous_score": float(item["prev_score"]),
                    },
                    total_score=item["current_score"],
                    badges=["🌟 Rising Star"] if item["improvement"] >= 50 else [],
                )
            )

        return Leaderboard(
            leaderboard_type=LeaderboardType.RISING_STARS,
            title="Rising Stars",
            description="Responders with the biggest improvement",
            period_start=period_start,
            period_end=period_end,
            team_name=team_name,
            entries=entries,
            total_participants=len([i for i in improvements if i["improvement"] > 0]),
        )

    def generate_team_rankings(
        self,
        oncall_stats: list[OnCallStats],
        period_start: datetime,
        period_end: datetime,
        limit: int = 10,
    ) -> Leaderboard:
        """
        Generate team rankings leaderboard.

        Args:
            oncall_stats: List of OnCallStats for all responders
            period_start: Start of period
            period_end: End of period
            limit: Maximum entries to return

        Returns:
            Leaderboard with team rankings
        """
        # Group by team
        team_stats: dict[str, list[OnCallStats]] = {}
        for stat in oncall_stats:
            team = stat.team_name or "Unknown"
            if team not in team_stats:
                team_stats[team] = []
            team_stats[team].append(stat)

        # Calculate team scores
        team_scores = []
        for team_name, stats in team_stats.items():
            total_score = sum(self._calculate_responder_score(s) for s in stats)
            avg_score = total_score / len(stats) if stats else 0
            total_incidents = sum(s.total_pages for s in stats)
            avg_ack = (
                sum(s.avg_ack_time_minutes or 0 for s in stats) / len(stats)
                if stats
                else 0
            )

            team_scores.append({
                "team": team_name,
                "total_score": total_score,
                "avg_score": avg_score,
                "total_incidents": total_incidents,
                "avg_ack_time": avg_ack,
                "member_count": len(stats),
            })

        # Sort by total score
        team_scores.sort(key=lambda x: x["total_score"], reverse=True)

        entries = []
        for i, item in enumerate(team_scores[:limit], 1):
            entries.append(
                LeaderboardEntry(
                    rank=i,
                    responder_id=item["team"],
                    responder_name=item["team"],
                    team_name=item["team"],
                    primary_value=float(item["total_score"]),
                    primary_label="Total Team Score",
                    secondary_metrics={
                        "avg_score": item["avg_score"],
                        "total_incidents": float(item["total_incidents"]),
                        "avg_ack_time_min": item["avg_ack_time"],
                        "members": float(item["member_count"]),
                    },
                    total_score=int(item["total_score"]),
                    badges=["🏅 Top Team"] if i == 1 else [],
                )
            )

        return Leaderboard(
            leaderboard_type=LeaderboardType.TEAM_RANKINGS,
            title="Team Rankings",
            description="Teams ranked by total performance score",
            period_start=period_start,
            period_end=period_end,
            entries=entries,
            total_participants=len(team_scores),
        )

    def build_responder_stats(
        self,
        oncall_stat: OnCallStats,
        incidents: list[dict],
        previous_stat: OnCallStats | None = None,
    ) -> ResponderStats:
        """
        Build full ResponderStats from OnCallStats and incidents.

        Args:
            oncall_stat: OnCallStats for the responder
            incidents: All incidents to calculate additional metrics
            previous_stat: Previous period stats for rank change

        Returns:
            ResponderStats with full metrics and scores
        """
        # Get incidents for this responder
        responder_incidents = [
            inc
            for inc in incidents
            if oncall_stat.responder_id in inc.get("assigned_to", [])
            or oncall_stat.responder_id == inc.get("responder_id")
            or oncall_stat.responder_name in inc.get("assigned_to", [])
        ]

        # Filter by period
        responder_incidents = [
            inc
            for inc in responder_incidents
            if self._in_period(inc, oncall_stat.period_start, oncall_stat.period_end)
        ]

        # Count resolutions
        resolved = sum(1 for inc in responder_incidents if inc.get("resolved_at"))

        # First response rate (how often they responded first)
        first_responses = sum(
            1 for inc in responder_incidents if inc.get("first_responder") == oncall_stat.responder_id
        )
        first_response_rate = (
            first_responses / len(responder_incidents) * 100
            if responder_incidents
            else 0
        )

        # Resolution rate
        resolution_rate = (
            resolved / oncall_stat.total_pages * 100
            if oncall_stat.total_pages > 0
            else 0
        )

        # SLA compliance
        sla_met = sum(1 for inc in responder_incidents if self._is_sla_met(inc))
        sla_rate = sla_met / len(responder_incidents) * 100 if responder_incidents else 0

        # Calculate scores
        score = self._calculate_responder_score(oncall_stat)

        # Rank change from previous period
        rank_change = None
        if previous_stat:
            prev_score = self._calculate_responder_score(previous_stat)
            if prev_score > 0:
                rank_change = 1 if score > prev_score else (-1 if score < prev_score else 0)

        return ResponderStats(
            responder_id=oncall_stat.responder_id,
            responder_name=oncall_stat.responder_name,
            responder_email=oncall_stat.responder_email,
            team_name=oncall_stat.team_name,
            period_start=oncall_stat.period_start,
            period_end=oncall_stat.period_end,
            incidents_handled=oncall_stat.total_pages,
            incidents_resolved=resolved,
            avg_resolution_time_minutes=oncall_stat.avg_resolution_time_minutes,
            avg_ack_time_minutes=oncall_stat.avg_ack_time_minutes,
            first_response_rate=first_response_rate,
            resolution_rate=resolution_rate,
            sla_compliance_rate=sla_rate,
            response_score=int(oncall_stat.total_pages * self.SCORE_PER_INCIDENT),
            resolution_score=resolved * self.SCORE_PER_RESOLUTION,
            quality_score=int(sla_rate),
            total_score=score,
            rank_change=rank_change,
        )

    def _calculate_responder_score(self, stat: OnCallStats) -> int:
        """Calculate total score for a responder."""
        score = 0

        # Base score for incidents handled
        score += stat.total_pages * self.SCORE_PER_INCIDENT

        # Bonus for fast acknowledgments
        if stat.avg_ack_time_minutes and stat.avg_ack_time_minutes < 5:
            score += stat.pages_acknowledged * self.SCORE_FAST_ACK_BONUS

        # Off-hours bonus
        score += stat.off_hours_pages * self.SCORE_OFF_HOURS_BONUS

        return score

    def _calculate_badges(self, stat: OnCallStats) -> list[str]:
        """Calculate badges/achievements for a responder."""
        badges = []

        # Speed demon: avg ack < 2 min
        if stat.avg_ack_time_minutes and stat.avg_ack_time_minutes < 2:
            badges.append("⚡ Speed Demon")

        # Night owl: >50% off-hours
        if stat.total_pages > 0:
            off_hours_ratio = stat.off_hours_pages / stat.total_pages
            if off_hours_ratio > 0.5:
                badges.append("🦉 Night Owl")

        # High volume: >50 incidents
        if stat.total_pages >= 50:
            badges.append("💪 High Volume Hero")

        # Weekend warrior
        if stat.weekend_pages >= 10:
            badges.append("🎯 Weekend Warrior")

        return badges

    def _is_sla_met(self, incident: dict) -> bool:
        """Check if SLA was met for an incident."""
        triggered = self._parse_datetime(incident.get("triggered_at"))
        resolved = self._parse_datetime(incident.get("resolved_at"))

        if not triggered or not resolved:
            return False

        resolution_minutes = (resolved - triggered).total_seconds() / 60
        severity = incident.get("severity", "medium").lower()
        target = self.calculator.sla_targets.get(severity, 60)

        return resolution_minutes <= target

    def _in_period(
        self, incident: dict, period_start: datetime, period_end: datetime
    ) -> bool:
        """Check if incident is within period."""
        triggered = self._parse_datetime(incident.get("triggered_at"))
        if not triggered:
            return False
        return period_start <= triggered <= period_end

    def _parse_datetime(self, value) -> datetime | None:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return None
