"""Performance report generation."""

from datetime import datetime
from typing import Any
from .models import (
    PerformanceReport, PerformancePeriod, TeamMetrics, EngineerMetrics,
    PeriodComparison, PerformanceTier, BurnoutRisk
)
from .service import PerformanceService
from .benchmarks import classify_team, compare_to_industry


class ReportGenerator:
    """Generate comprehensive performance reports."""
    
    def __init__(self, service: PerformanceService):
        self.service = service
    
    async def generate_team_report(
        self,
        team_id: str,
        team_name: str,
        period: PerformancePeriod,
        include_engineers: bool = True,
        anonymize_engineers: bool = False,
        include_comparison: bool = True
    ) -> PerformanceReport:
        """Generate comprehensive team performance report."""
        # Get team metrics
        team_metrics = await self.service.calculate_team_metrics(team_id, team_name, period)
        
        # Get engineer metrics
        engineer_metrics = []
        if include_engineers:
            incidents = await self.service.incident_repo.get_incidents(team_id, period.start, period.end)
            engineer_ids = set(getattr(i, 'assignee_id', None) for i in incidents if getattr(i, 'assignee_id', None))
            for eng_id in engineer_ids:
                metrics = await self.service.calculate_engineer_metrics(
                    eng_id, f"Engineer {eng_id[:6]}", team_id, period,
                    include_burnout=True, anonymize=anonymize_engineers
                )
                engineer_metrics.append(metrics)
        
        # Period comparison
        comparison = None
        if include_comparison:
            previous = PerformancePeriod(
                start=period.start - (period.end - period.start),
                end=period.start,
                label="Previous period"
            )
            comparison = await self.service.compare_periods(team_id, team_name, period, previous)
        
        # Benchmark classifications
        benchmarks = {k: v.value for k, v in classify_team(team_metrics).items()}
        
        # Generate insights
        highlights = self._generate_highlights(team_metrics, engineer_metrics, comparison)
        concerns = self._generate_concerns(team_metrics, engineer_metrics)
        recommendations = self._generate_recommendations(team_metrics, engineer_metrics, comparison)
        
        return PerformanceReport(
            period=period,
            team_metrics=team_metrics,
            engineer_metrics=engineer_metrics,
            comparison=comparison,
            benchmarks=benchmarks,
            highlights=highlights,
            concerns=concerns,
            recommendations=recommendations
        )
    
    def _generate_highlights(
        self,
        team: TeamMetrics,
        engineers: list[EngineerMetrics],
        comparison: PeriodComparison | None
    ) -> list[str]:
        """Generate performance highlights."""
        highlights = []
        
        if team.tier == PerformanceTier.ELITE:
            highlights.append(f"🏆 Team performing at ELITE level ({team.industry_percentile}th percentile)")
        elif team.tier == PerformanceTier.HIGH:
            highlights.append(f"⭐ Team performing above industry average")
        
        if team.sla_compliance_rate >= 99:
            highlights.append(f"✅ Excellent SLA compliance: {team.sla_compliance_rate}%")
        
        if team.mttr_minutes < 60:
            highlights.append(f"⚡ Outstanding MTTR: {team.mttr_minutes:.0f} minutes")
        
        if team.workload_distribution and team.workload_distribution.is_balanced:
            highlights.append("⚖️ Workload well-distributed across team")
        
        if comparison and comparison.improved:
            highlights.append(f"📈 Improvements in: {', '.join(comparison.improved)}")
        
        top_performers = [e for e in engineers if e.resolution_rate >= 95]
        if top_performers:
            highlights.append(f"🌟 {len(top_performers)} engineers with 95%+ resolution rate")
        
        return highlights[:5]
    
    def _generate_concerns(
        self,
        team: TeamMetrics,
        engineers: list[EngineerMetrics]
    ) -> list[str]:
        """Generate areas of concern."""
        concerns = []
        
        if team.tier == PerformanceTier.LOW:
            concerns.append("⚠️ Team performance below industry average")
        
        if team.mttr_minutes > 240:
            concerns.append(f"🕐 MTTR ({team.mttr_minutes:.0f}min) exceeds 4-hour target")
        
        if team.escalation_rate > 20:
            concerns.append(f"📤 High escalation rate: {team.escalation_rate}%")
        
        if team.reopen_rate > 10:
            concerns.append(f"🔄 Elevated reopen rate: {team.reopen_rate}%")
        
        if team.workload_distribution and not team.workload_distribution.is_balanced:
            gini = team.workload_distribution.gini_coefficient
            concerns.append(f"⚖️ Uneven workload distribution (Gini: {gini:.2f})")
        
        at_risk = [e for e in engineers if e.burnout and e.burnout.risk_level in (BurnoutRisk.HIGH, BurnoutRisk.CRITICAL)]
        if at_risk:
            concerns.append(f"🔥 {len(at_risk)} team members at burnout risk")
        
        return concerns[:5]
    
    def _generate_recommendations(
        self,
        team: TeamMetrics,
        engineers: list[EngineerMetrics],
        comparison: PeriodComparison | None
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs = []
        
        if team.mttr_minutes > 120:
            recs.append("Consider implementing runbooks or automation to reduce resolution time")
        
        if team.mtta_minutes > 15:
            recs.append("Review alerting configuration to improve acknowledgment time")
        
        if team.escalation_rate > 15:
            recs.append("Increase L1 training or documentation to reduce escalations")
        
        if team.workload_distribution and team.workload_distribution.gini_coefficient > 0.3:
            recs.append("Rebalance oncall rotation to distribute workload more evenly")
        
        at_risk = [e for e in engineers if e.burnout and e.burnout.risk_level != BurnoutRisk.LOW]
        if at_risk:
            recs.append("Schedule check-ins with engineers showing burnout indicators")
        
        if comparison and comparison.degraded:
            recs.append(f"Investigate regression in: {', '.join(comparison.degraded)}")
        
        if team.reopen_rate > 5:
            recs.append("Implement better resolution verification before closing incidents")
        
        return recs[:5]
    
    def export_markdown(self, report: PerformanceReport) -> str:
        """Export report as Markdown."""
        lines = [
            f"# Performance Report: {report.team_metrics.team_name}",
            f"**Period:** {report.period.label} ({report.period.start.date()} to {report.period.end.date()})",
            f"**Generated:** {report.generated_at.isoformat()}",
            "",
            "## Summary",
            f"- **Performance Tier:** {report.team_metrics.tier.value.upper()}",
            f"- **Industry Percentile:** {report.team_metrics.industry_percentile}th",
            f"- **Total Incidents:** {report.team_metrics.total_incidents}",
            "",
            "## Key Metrics",
            f"| Metric | Value | Benchmark |",
            f"|--------|-------|-----------|",
            f"| MTTR | {report.team_metrics.mttr_minutes:.0f} min | {report.benchmarks.get('mttr', 'N/A')} |",
            f"| MTTA | {report.team_metrics.mtta_minutes:.0f} min | {report.benchmarks.get('mtta', 'N/A')} |",
            f"| SLA Compliance | {report.team_metrics.sla_compliance_rate}% | {report.benchmarks.get('sla_compliance', 'N/A')} |",
            f"| Escalation Rate | {report.team_metrics.escalation_rate}% | {report.benchmarks.get('escalation_rate', 'N/A')} |",
            "",
        ]
        
        if report.highlights:
            lines.extend(["## Highlights", ""])
            for h in report.highlights:
                lines.append(f"- {h}")
            lines.append("")
        
        if report.concerns:
            lines.extend(["## Concerns", ""])
            for c in report.concerns:
                lines.append(f"- {c}")
            lines.append("")
        
        if report.recommendations:
            lines.extend(["## Recommendations", ""])
            for r in report.recommendations:
                lines.append(f"- {r}")
            lines.append("")
        
        if report.comparison:
            lines.extend([
                "## Period Comparison",
                report.comparison.summary,
                ""
            ])
        
        return "\n".join(lines)
    
    def export_json(self, report: PerformanceReport) -> dict:
        """Export report as JSON-serializable dict."""
        return report.model_dump(mode="json")
    
    def export_csv_metrics(self, report: PerformanceReport) -> str:
        """Export key metrics as CSV."""
        lines = ["metric,value,unit,benchmark_tier"]
        m = report.team_metrics
        rows = [
            ("mttr_minutes", m.mttr_minutes, "min", report.benchmarks.get("mttr", "")),
            ("mtta_minutes", m.mtta_minutes, "min", report.benchmarks.get("mtta", "")),
            ("total_incidents", m.total_incidents, "", ""),
            ("sla_compliance_rate", m.sla_compliance_rate, "%", report.benchmarks.get("sla_compliance", "")),
            ("escalation_rate", m.escalation_rate, "%", report.benchmarks.get("escalation_rate", "")),
            ("reopen_rate", m.reopen_rate, "%", report.benchmarks.get("reopen_rate", "")),
        ]
        for name, val, unit, tier in rows:
            lines.append(f"{name},{val},{unit},{tier}")
        return "\n".join(lines)
