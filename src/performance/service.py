"""Performance analytics service."""

from datetime import datetime
from typing import Any, Protocol
from .models import (
    PerformancePeriod,
    TeamMetrics,
    EngineerMetrics,
    PeriodComparison,
    BurnoutRisk,
    LeaderboardEntry,
)
from .calculators import (
    calculate_mttr,
    calculate_mtta,
    count_incidents_by_severity,
    calculate_workload_distribution,
    calculate_burnout_risk,
    calculate_oncall_burden,
    calculate_after_hours_incidents,
    create_metric_value,
)
from .benchmarks import classify_team, calculate_overall_tier, estimate_percentile


class IncidentRepository(Protocol):
    async def get_incidents(
        self, team_id: str, start: datetime, end: datetime
    ) -> list[Any]: ...
    async def get_engineer_incidents(
        self, engineer_id: str, start: datetime, end: datetime
    ) -> list[Any]: ...


class OncallRepository(Protocol):
    async def get_shifts(
        self, team_id: str, start: datetime, end: datetime
    ) -> list[dict]: ...


class PerformanceService:
    def __init__(
        self,
        incident_repo: IncidentRepository,
        oncall_repo: OncallRepository | None = None,
    ):
        self.incident_repo, self.oncall_repo = incident_repo, oncall_repo

    async def calculate_team_metrics(
        self, team_id: str, team_name: str, period: PerformancePeriod
    ) -> TeamMetrics:
        incidents = await self.incident_repo.get_incidents(
            team_id, period.start, period.end
        )
        oncall_shifts = (
            await self.oncall_repo.get_shifts(team_id, period.start, period.end)
            if self.oncall_repo
            else []
        )

        severity_counts = count_incidents_by_severity(incidents, period)
        total = sum(severity_counts.values())
        unique_engs = set(
            getattr(i, "assignee_id", None)
            for i in incidents
            if getattr(i, "assignee_id", None)
        )
        resolved = sum(
            1
            for i in incidents
            if i.resolved_at and period.start <= i.created_at <= period.end
        )
        reopened = sum(1 for i in incidents if getattr(i, "reopened", False))
        escalated = sum(1 for i in incidents if getattr(i, "escalated", False))
        sla_ok = sum(
            1
            for i in incidents
            if i.acknowledged_at
            and (i.acknowledged_at - i.created_at).total_seconds() < 900
        )

        metrics = TeamMetrics(
            team_id=team_id,
            team_name=team_name,
            period=period,
            total_incidents=total,
            incidents_by_severity=severity_counts,
            mttr_minutes=calculate_mttr(incidents, period),
            mtta_minutes=calculate_mtta(incidents, period),
            sla_compliance_rate=round(sla_ok / total * 100, 1) if total else 100,
            escalation_rate=round(escalated / total * 100, 1) if total else 0,
            reopen_rate=round(reopened / resolved * 100, 1) if resolved else 0,
            workload_distribution=calculate_workload_distribution(incidents, period),
            oncall_burden_hours=round(
                sum(
                    (
                        s.get("end", period.end) - s.get("start", period.start)
                    ).total_seconds()
                    / 3600
                    for s in oncall_shifts
                ),
                1,
            ),
            avg_incidents_per_engineer=(
                round(total / len(unique_engs), 1) if unique_engs else 0
            ),
        )
        classifications = classify_team(metrics)
        metrics.tier = calculate_overall_tier(classifications)
        metrics.industry_percentile = estimate_percentile("mttr", metrics.mttr_minutes)
        return metrics

    async def calculate_engineer_metrics(
        self,
        engineer_id: str,
        engineer_name: str,
        team_id: str,
        period: PerformancePeriod,
        include_burnout: bool = True,
        anonymize: bool = False,
    ) -> EngineerMetrics:
        incidents = await self.incident_repo.get_engineer_incidents(
            engineer_id, period.start, period.end
        )
        oncall_shifts = (
            await self.oncall_repo.get_shifts(team_id, period.start, period.end)
            if self.oncall_repo
            else []
        )

        resolved_inc = [i for i in incidents if i.resolved_at]
        ack_times = [
            (i.acknowledged_at - i.created_at).total_seconds() / 60
            for i in incidents
            if i.acknowledged_at
        ]
        res_times = [
            (i.resolved_at - i.created_at).total_seconds() / 60 for i in resolved_inc
        ]

        metrics = EngineerMetrics(
            engineer_id=engineer_id,
            engineer_name=engineer_name,
            period=period,
            incidents_handled=len(incidents),
            incidents_resolved=len(resolved_inc),
            avg_response_time_min=(
                round(sum(ack_times) / len(ack_times), 2) if ack_times else 0
            ),
            avg_resolution_time_min=(
                round(sum(res_times) / len(res_times), 2) if res_times else 0
            ),
            oncall_hours=calculate_oncall_burden(oncall_shifts, engineer_id, period),
            after_hours_pages=calculate_after_hours_incidents(
                incidents, engineer_id, period
            ),
            escalations_made=sum(
                1 for i in incidents if getattr(i, "escalated_by", None) == engineer_id
            ),
            escalations_received=sum(
                1 for i in incidents if getattr(i, "escalated_to", None) == engineer_id
            ),
            reopen_rate=(
                round(
                    sum(1 for i in incidents if getattr(i, "reopened", False))
                    / len(resolved_inc)
                    * 100,
                    1,
                )
                if resolved_inc
                else 0
            ),
        )
        if include_burnout:
            all_inc = await self.incident_repo.get_incidents(
                team_id, period.start, period.end
            )
            metrics.burnout = calculate_burnout_risk(
                engineer_id, all_inc, oncall_shifts, period
            )
        return metrics.anonymize() if anonymize else metrics

    async def compare_periods(
        self,
        team_id: str,
        team_name: str,
        current: PerformancePeriod,
        previous: PerformancePeriod,
    ) -> PeriodComparison:
        curr_m, prev_m = (
            await self.calculate_team_metrics(team_id, team_name, current),
            await self.calculate_team_metrics(team_id, team_name, previous),
        )
        comparisons, improved, degraded, stable = {}, [], [], []
        for name, attr, unit, lib in [
            ("mttr", "mttr_minutes", "min", True),
            ("mtta", "mtta_minutes", "min", True),
            ("incidents", "total_incidents", "", True),
            ("sla_compliance", "sla_compliance_rate", "%", False),
        ]:
            m = create_metric_value(
                name, getattr(curr_m, attr, 0), getattr(prev_m, attr, 0), unit, lib
            )
            comparisons[name] = m
            if m.trend and m.trend > 10:
                improved.append(name)
            elif m.trend and m.trend < -10:
                degraded.append(name)
            else:
                stable.append(name)
        parts = ([f"Improved: {', '.join(improved)}"] if improved else []) + (
            [f"Needs attention: {', '.join(degraded)}"] if degraded else []
        )
        return PeriodComparison(
            current=current,
            previous=previous,
            metrics=comparisons,
            improved=improved,
            degraded=degraded,
            stable=stable,
            summary=". ".join(parts) or "Performance stable",
        )

    async def get_team_burnout_summary(
        self, team_id: str, period: PerformancePeriod
    ) -> dict:
        incidents = await self.incident_repo.get_incidents(
            team_id, period.start, period.end
        )
        oncall_shifts = (
            await self.oncall_repo.get_shifts(team_id, period.start, period.end)
            if self.oncall_repo
            else []
        )
        eng_ids = set(
            getattr(i, "assignee_id", None)
            for i in incidents
            if getattr(i, "assignee_id", None)
        )
        risk_counts, high_risk = {r: 0 for r in BurnoutRisk}, []
        for eid in eng_ids:
            risk = calculate_burnout_risk(eid, incidents, oncall_shifts, period)
            risk_counts[risk.risk_level] += 1
            if risk.risk_level in (BurnoutRisk.HIGH, BurnoutRisk.CRITICAL):
                high_risk.append(
                    {
                        "id": eid,
                        "risk_level": risk.risk_level.value,
                        "score": risk.risk_score,
                    }
                )
        return {
            "total_engineers": len(eng_ids),
            "risk_distribution": {k.value: v for k, v in risk_counts.items()},
            "engineers_at_risk": len(high_risk),
            "high_risk_details": high_risk[:5],
        }

    async def generate_leaderboard(
        self,
        team_id: str,
        period: PerformancePeriod,
        metric: str = "resolution_rate",
        top_n: int = 10,
        anonymize: bool = False,
    ) -> list[LeaderboardEntry]:
        incidents = await self.incident_repo.get_incidents(
            team_id, period.start, period.end
        )
        stats: dict[str, dict] = {}
        for i in incidents:
            if not (eid := getattr(i, "assignee_id", None)):
                continue
            if eid not in stats:
                stats[eid] = {
                    "name": getattr(i, "assignee_name", f"Eng {eid[:6]}"),
                    "handled": 0,
                    "resolved": 0,
                    "resp_time": 0,
                    "resp_cnt": 0,
                }
            s = stats[eid]
            s["handled"] += 1
            if i.resolved_at:
                s["resolved"] += 1
            if i.acknowledged_at:
                s["resp_time"] += (i.acknowledged_at - i.created_at).total_seconds()
                s["resp_cnt"] += 1

        def score(s):
            return (
                (s["resolved"] / s["handled"] * 100)
                if s["handled"] and metric == "resolution_rate"
                else (
                    (
                        s["resp_time"] / s["resp_cnt"] / 60
                        if s["resp_cnt"]
                        else float("inf")
                    )
                    if metric == "response_time"
                    else s.get("resolved", s["handled"])
                )
            )

        scored = sorted(
            [(eid, s["name"], score(s)) for eid, s in stats.items()],
            key=lambda x: x[2],
            reverse=(metric != "response_time"),
        )
        badges = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        return [
            LeaderboardEntry(
                rank=i + 1,
                engineer_id=eid if not anonymize else f"eng_{hash(eid) % 10000:04d}",
                engineer_name=name if not anonymize else f"Engineer #{i + 1}",
                score=round(sc, 2),
                metric_name=metric,
                badge=badges[i] if i < len(badges) else None,
                is_anonymized=anonymize,
            )
            for i, (eid, name, sc) in enumerate(scored[:top_n])
        ]
