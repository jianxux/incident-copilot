"""Performance analytics service."""

from datetime import datetime, timedelta
from typing import Any, Protocol
from .models import (
    PerformancePeriod, TeamMetrics, EngineerMetrics, PeriodComparison,
    MetricValue, PerformanceTier, BurnoutRisk, LeaderboardEntry, WorkloadDistribution
)
from .calculators import (
    calculate_mttr, calculate_mtta, count_incidents_by_severity,
    calculate_workload_distribution, calculate_burnout_risk,
    calculate_oncall_burden, calculate_after_hours_incidents,
    create_metric_value
)
from .benchmarks import classify_team, calculate_overall_tier, estimate_percentile


class IncidentRepository(Protocol):
    """Protocol for incident data access."""
    async def get_incidents(self, team_id: str, start: datetime, end: datetime) -> list[Any]: ...
    async def get_engineer_incidents(self, engineer_id: str, start: datetime, end: datetime) -> list[Any]: ...


class OncallRepository(Protocol):
    """Protocol for oncall data access."""
    async def get_shifts(self, team_id: str, start: datetime, end: datetime) -> list[dict]: ...


class PerformanceService:
    """Service for calculating and comparing performance metrics."""
    
    def __init__(
        self,
        incident_repo: IncidentRepository,
        oncall_repo: OncallRepository | None = None
    ):
        self.incident_repo = incident_repo
        self.oncall_repo = oncall_repo
    
    async def calculate_team_metrics(
        self,
        team_id: str,
        team_name: str,
        period: PerformancePeriod
    ) -> TeamMetrics:
        """Calculate comprehensive team metrics for a period."""
        incidents = await self.incident_repo.get_incidents(team_id, period.start, period.end)
        oncall_shifts = []
        if self.oncall_repo:
            oncall_shifts = await self.oncall_repo.get_shifts(team_id, period.start, period.end)
        
        # Core metrics
        mttr = calculate_mttr(incidents, period)
        mtta = calculate_mtta(incidents, period)
        severity_counts = count_incidents_by_severity(incidents, period)
        total = sum(severity_counts.values())
        
        # Workload
        workload_dist = calculate_workload_distribution(incidents, period)
        unique_engineers = set(getattr(i, 'assignee_id', None) for i in incidents if getattr(i, 'assignee_id', None))
        avg_per_engineer = total / len(unique_engineers) if unique_engineers else 0
        
        # Oncall burden
        total_oncall_hours = sum(
            (s.get('end', period.end) - s.get('start', period.start)).total_seconds() / 3600
            for s in oncall_shifts
        )
        
        # Rates
        resolved = sum(1 for i in incidents if i.resolved_at and period.start <= i.created_at <= period.end)
        reopened = sum(1 for i in incidents if getattr(i, 'reopened', False))
        escalated = sum(1 for i in incidents if getattr(i, 'escalated', False))
        
        reopen_rate = (reopened / resolved * 100) if resolved else 0
        escalation_rate = (escalated / total * 100) if total else 0
        
        # SLA compliance (example: 95% acknowledged within SLA)
        sla_compliant = sum(
            1 for i in incidents
            if i.acknowledged_at and 
            (i.acknowledged_at - i.created_at).total_seconds() < 900  # 15 min SLA
        )
        sla_rate = (sla_compliant / total * 100) if total else 100
        
        metrics = TeamMetrics(
            team_id=team_id,
            team_name=team_name,
            period=period,
            total_incidents=total,
            incidents_by_severity=severity_counts,
            mttr_minutes=mttr,
            mtta_minutes=mtta,
            sla_compliance_rate=round(sla_rate, 1),
            escalation_rate=round(escalation_rate, 1),
            reopen_rate=round(reopen_rate, 1),
            workload_distribution=workload_dist,
            oncall_burden_hours=round(total_oncall_hours, 1),
            avg_incidents_per_engineer=round(avg_per_engineer, 1)
        )
        
        # Classify against benchmarks
        classifications = classify_team(metrics)
        metrics.tier = calculate_overall_tier(classifications)
        metrics.industry_percentile = estimate_percentile("mttr", mttr)
        
        return metrics
    
    async def calculate_engineer_metrics(
        self,
        engineer_id: str,
        engineer_name: str,
        team_id: str,
        period: PerformancePeriod,
        include_burnout: bool = True,
        anonymize: bool = False
    ) -> EngineerMetrics:
        """Calculate metrics for individual engineer."""
        incidents = await self.incident_repo.get_engineer_incidents(engineer_id, period.start, period.end)
        oncall_shifts = []
        if self.oncall_repo:
            oncall_shifts = await self.oncall_repo.get_shifts(team_id, period.start, period.end)
        
        handled = len(incidents)
        resolved = sum(1 for i in incidents if i.resolved_at)
        reopened = sum(1 for i in incidents if getattr(i, 'reopened', False))
        
        # Response times
        ack_times = [
            (i.acknowledged_at - i.created_at).total_seconds() / 60
            for i in incidents if i.acknowledged_at
        ]
        resolve_times = [
            (i.resolved_at - i.created_at).total_seconds() / 60
            for i in incidents if i.resolved_at
        ]
        
        metrics = EngineerMetrics(
            engineer_id=engineer_id,
            engineer_name=engineer_name,
            period=period,
            incidents_handled=handled,
            incidents_resolved=resolved,
            avg_response_time_min=round(sum(ack_times) / len(ack_times), 2) if ack_times else 0,
            avg_resolution_time_min=round(sum(resolve_times) / len(resolve_times), 2) if resolve_times else 0,
            oncall_hours=calculate_oncall_burden(oncall_shifts, engineer_id, period),
            after_hours_pages=calculate_after_hours_incidents(incidents, engineer_id, period),
            escalations_made=sum(1 for i in incidents if getattr(i, 'escalated_by', None) == engineer_id),
            escalations_received=sum(1 for i in incidents if getattr(i, 'escalated_to', None) == engineer_id),
            reopen_rate=round(reopened / resolved * 100, 1) if resolved else 0
        )
        
        if include_burnout:
            all_incidents = await self.incident_repo.get_incidents(team_id, period.start, period.end)
            metrics.burnout = calculate_burnout_risk(engineer_id, all_incidents, oncall_shifts, period)
        
        return metrics.anonymize() if anonymize else metrics
    
    async def compare_periods(
        self,
        team_id: str,
        team_name: str,
        current: PerformancePeriod,
        previous: PerformancePeriod
    ) -> PeriodComparison:
        """Compare metrics between two periods."""
        current_metrics = await self.calculate_team_metrics(team_id, team_name, current)
        previous_metrics = await self.calculate_team_metrics(team_id, team_name, previous)
        
        # Compare key metrics
        comparisons = {}
        improved = []
        degraded = []
        stable = []
        
        metrics_config = [
            ("mttr", "mttr_minutes", "min", True),
            ("mtta", "mtta_minutes", "min", True),
            ("incidents", "total_incidents", "", True),
            ("sla_compliance", "sla_compliance_rate", "%", False),
            ("escalation_rate", "escalation_rate", "%", True),
            ("reopen_rate", "reopen_rate", "%", True),
        ]
        
        for name, attr, unit, lower_is_better in metrics_config:
            curr_val = getattr(current_metrics, attr, 0)
            prev_val = getattr(previous_metrics, attr, 0)
            
            metric = create_metric_value(name, curr_val, prev_val, unit, lower_is_better)
            comparisons[name] = metric
            
            if metric.trend is not None:
                if metric.trend > 10:
                    improved.append(name)
                elif metric.trend < -10:
                    degraded.append(name)
                else:
                    stable.append(name)
        
        summary = self._generate_comparison_summary(improved, degraded, stable)
        
        return PeriodComparison(
            current=current,
            previous=previous,
            metrics=comparisons,
            improved=improved,
            degraded=degraded,
            stable=stable,
            summary=summary
        )
    
    def _generate_comparison_summary(
        self,
        improved: list[str],
        degraded: list[str],
        stable: list[str]
    ) -> str:
        """Generate human-readable comparison summary."""
        parts = []
        if improved:
            parts.append(f"Improved: {', '.join(improved)}")
        if degraded:
            parts.append(f"Needs attention: {', '.join(degraded)}")
        if stable and not (improved or degraded):
            parts.append("Performance stable across all metrics")
        return ". ".join(parts) if parts else "No significant changes"
    
    async def get_team_burnout_summary(
        self,
        team_id: str,
        period: PerformancePeriod
    ) -> dict:
        """Get burnout risk summary for the team."""
        incidents = await self.incident_repo.get_incidents(team_id, period.start, period.end)
        oncall_shifts = []
        if self.oncall_repo:
            oncall_shifts = await self.oncall_repo.get_shifts(team_id, period.start, period.end)
        
        engineer_ids = set(
            getattr(i, 'assignee_id', None) for i in incidents 
            if getattr(i, 'assignee_id', None)
        )
        
        risk_counts = {level: 0 for level in BurnoutRisk}
        high_risk_engineers = []
        
        for eng_id in engineer_ids:
            risk = calculate_burnout_risk(eng_id, incidents, oncall_shifts, period)
            risk_counts[risk.risk_level] += 1
            if risk.risk_level in (BurnoutRisk.HIGH, BurnoutRisk.CRITICAL):
                high_risk_engineers.append({
                    "id": eng_id,
                    "risk_level": risk.risk_level.value,
                    "score": risk.risk_score,
                    "top_factor": risk.factors[0] if risk.factors else None
                })
        
        return {
            "total_engineers": len(engineer_ids),
            "risk_distribution": {k.value: v for k, v in risk_counts.items()},
            "engineers_at_risk": len(high_risk_engineers),
            "high_risk_details": high_risk_engineers[:5],  # Top 5
            "team_health": "healthy" if not high_risk_engineers else "at_risk"
        }
    
    async def generate_leaderboard(
        self,
        team_id: str,
        period: PerformancePeriod,
        metric: str = "resolution_rate",
        top_n: int = 10,
        anonymize: bool = False
    ) -> list[LeaderboardEntry]:
        """Generate performance leaderboard."""
        incidents = await self.incident_repo.get_incidents(team_id, period.start, period.end)
        
        engineer_scores: dict[str, dict] = {}
        for incident in incidents:
            eng_id = getattr(incident, 'assignee_id', None)
            if not eng_id:
                continue
            
            if eng_id not in engineer_scores:
                engineer_scores[eng_id] = {
                    "id": eng_id,
                    "name": getattr(incident, 'assignee_name', f"Engineer {eng_id[:6]}"),
                    "handled": 0,
                    "resolved": 0,
                    "total_response_time": 0,
                    "response_count": 0
                }
            
            stats = engineer_scores[eng_id]
            stats["handled"] += 1
            if incident.resolved_at:
                stats["resolved"] += 1
            if incident.acknowledged_at:
                stats["total_response_time"] += (incident.acknowledged_at - incident.created_at).total_seconds()
                stats["response_count"] += 1
        
        # Calculate scores based on metric
        scored = []
        for eng_id, stats in engineer_scores.items():
            if metric == "resolution_rate":
                score = (stats["resolved"] / stats["handled"] * 100) if stats["handled"] else 0
            elif metric == "response_time":
                score = (stats["total_response_time"] / stats["response_count"] / 60) if stats["response_count"] else float('inf')
            elif metric == "incidents_resolved":
                score = stats["resolved"]
            else:
                score = stats["handled"]
            
            scored.append((eng_id, stats["name"], score))
        
        # Sort (lower is better for response_time)
        reverse = metric != "response_time"
        scored.sort(key=lambda x: x[2], reverse=reverse)
        
        # Build leaderboard
        badges = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        entries = []
        for i, (eng_id, name, score) in enumerate(scored[:top_n]):
            entry = LeaderboardEntry(
                rank=i + 1,
                engineer_id=eng_id if not anonymize else f"eng_{hash(eng_id) % 10000:04d}",
                engineer_name=name if not anonymize else f"Engineer #{i+1}",
                score=round(score, 2),
                metric_name=metric,
                badge=badges[i] if i < len(badges) else None,
                is_anonymized=anonymize
            )
            entries.append(entry)
        
        return entries
