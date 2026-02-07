"""Performance report generation."""

from .benchmarks import classify_team
from .models import (
    BurnoutRisk,
    EngineerMetrics,
    PerformancePeriod,
    PerformanceReport,
    PerformanceTier,
    PeriodComparison,
    TeamMetrics,
)
from .service import PerformanceService


class ReportGenerator:
    def __init__(self, service: PerformanceService):
        self.service = service

    async def generate_team_report(
        self,
        team_id: str,
        team_name: str,
        period: PerformancePeriod,
        include_engineers: bool = True,
        anonymize_engineers: bool = False,
        include_comparison: bool = True,
    ) -> PerformanceReport:
        team_metrics = await self.service.calculate_team_metrics(
            team_id, team_name, period
        )
        engineer_metrics = []
        if include_engineers:
            incidents = await self.service.incident_repo.get_incidents(
                team_id, period.start, period.end
            )
            for eid in set(
                getattr(i, "assignee_id", None)
                for i in incidents
                if getattr(i, "assignee_id", None)
            ):
                engineer_metrics.append(
                    await self.service.calculate_engineer_metrics(
                        eid,
                        f"Eng {eid[:6]}",
                        team_id,
                        period,
                        True,
                        anonymize_engineers,
                    )
                )

        comparison = None
        if include_comparison:
            prev = PerformancePeriod(
                start=period.start - (period.end - period.start),
                end=period.start,
                label="Previous",
            )
            comparison = await self.service.compare_periods(
                team_id, team_name, period, prev
            )

        return PerformanceReport(
            period=period,
            team_metrics=team_metrics,
            engineer_metrics=engineer_metrics,
            comparison=comparison,
            benchmarks={k: v.value for k, v in classify_team(team_metrics).items()},
            highlights=self._highlights(team_metrics, engineer_metrics, comparison),
            concerns=self._concerns(team_metrics, engineer_metrics),
            recommendations=self._recommendations(
                team_metrics, engineer_metrics, comparison
            ),
        )

    def _highlights(
        self,
        tm: TeamMetrics,
        engs: list[EngineerMetrics],
        comp: PeriodComparison | None,
    ) -> list[str]:
        h = []
        if tm.tier == PerformanceTier.ELITE:
            h.append(f"🏆 ELITE performance ({tm.industry_percentile}th percentile)")
        elif tm.tier == PerformanceTier.HIGH:
            h.append("⭐ Above industry average")
        if tm.sla_compliance_rate >= 99:
            h.append(f"✅ Excellent SLA: {tm.sla_compliance_rate}%")
        if tm.mttr_minutes < 60:
            h.append(f"⚡ Outstanding MTTR: {tm.mttr_minutes:.0f}min")
        if tm.workload_distribution and tm.workload_distribution.is_balanced:
            h.append("⚖️ Balanced workload")
        if comp and comp.improved:
            h.append(f"📈 Improved: {', '.join(comp.improved)}")
        return h[:5]

    def _concerns(self, tm: TeamMetrics, engs: list[EngineerMetrics]) -> list[str]:
        c = []
        if tm.tier == PerformanceTier.LOW:
            c.append("⚠️ Below industry average")
        if tm.mttr_minutes > 240:
            c.append(f"🕐 MTTR ({tm.mttr_minutes:.0f}min) > 4h target")
        if tm.escalation_rate > 20:
            c.append(f"📤 High escalation: {tm.escalation_rate}%")
        if tm.workload_distribution and not tm.workload_distribution.is_balanced:
            c.append(
                f"⚖️ Uneven workload (Gini: {tm.workload_distribution.gini_coefficient:.2f})"
            )
        at_risk = [
            e
            for e in engs
            if e.burnout
            and e.burnout.risk_level in (BurnoutRisk.HIGH, BurnoutRisk.CRITICAL)
        ]
        if at_risk:
            c.append(f"🔥 {len(at_risk)} at burnout risk")
        return c[:5]

    def _recommendations(
        self,
        tm: TeamMetrics,
        engs: list[EngineerMetrics],
        comp: PeriodComparison | None,
    ) -> list[str]:
        r = []
        if tm.mttr_minutes > 120:
            r.append("Add runbooks/automation to reduce resolution time")
        if tm.mtta_minutes > 15:
            r.append("Review alerting to improve ack time")
        if tm.escalation_rate > 15:
            r.append("Increase L1 training to reduce escalations")
        if tm.workload_distribution and tm.workload_distribution.gini_coefficient > 0.3:
            r.append("Rebalance oncall rotation")
        if any(e.burnout and e.burnout.risk_level != BurnoutRisk.LOW for e in engs):
            r.append("Check in with at-risk engineers")
        if comp and comp.degraded:
            r.append(f"Investigate regression in: {', '.join(comp.degraded)}")
        return r[:5]

    def export_markdown(self, report: PerformanceReport) -> str:
        m = report.team_metrics
        lines = [
            f"# Performance Report: {m.team_name}",
            f"**Period:** {report.period.label}",
            f"**Tier:** {m.tier.value.upper()} ({m.industry_percentile}th percentile)",
            "",
            "## Metrics",
            f"- MTTR: {m.mttr_minutes:.0f}min | MTTA: {m.mtta_minutes:.0f}min | SLA: {m.sla_compliance_rate}%",
            "",
        ]
        if report.highlights:
            lines += ["## Highlights"] + [f"- {h}" for h in report.highlights] + [""]
        if report.concerns:
            lines += ["## Concerns"] + [f"- {c}" for c in report.concerns] + [""]
        if report.recommendations:
            lines += ["## Recommendations"] + [f"- {r}" for r in report.recommendations]
        return "\n".join(lines)

    def export_json(self, report: PerformanceReport) -> dict:
        return report.model_dump(mode="json")

    def export_csv_metrics(self, report: PerformanceReport) -> str:
        m = report.team_metrics
        return "\n".join(
            ["metric,value,unit"]
            + [
                f"{n},{v},{u}"
                for n, v, u in [
                    ("mttr", m.mttr_minutes, "min"),
                    ("mtta", m.mtta_minutes, "min"),
                    ("incidents", m.total_incidents, ""),
                    ("sla", m.sla_compliance_rate, "%"),
                ]
            ]
        )
