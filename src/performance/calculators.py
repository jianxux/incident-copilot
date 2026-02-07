"""Metric calculators for performance analytics."""
from datetime import datetime, timedelta
from typing import Any
from .models import PerformancePeriod, BurnoutIndicators, BurnoutRisk, WorkloadDistribution, MetricValue, PerformanceTier


def calculate_mttr(incidents: list[Any], period: PerformancePeriod) -> float:
    """Mean Time To Resolve in minutes."""
    resolved = [i for i in incidents if i.resolved_at and period.start <= i.created_at <= period.end]
    if not resolved: return 0.0
    return round(sum((i.resolved_at - i.created_at).total_seconds() / 60 for i in resolved) / len(resolved), 2)


def calculate_mtta(incidents: list[Any], period: PerformancePeriod) -> float:
    """Mean Time To Acknowledge in minutes."""
    acked = [i for i in incidents if i.acknowledged_at and period.start <= i.created_at <= period.end]
    if not acked: return 0.0
    return round(sum((i.acknowledged_at - i.created_at).total_seconds() / 60 for i in acked) / len(acked), 2)


def count_incidents_by_severity(incidents: list[Any], period: PerformancePeriod) -> dict[str, int]:
    counts: dict[str, int] = {}
    for i in incidents:
        if period.start <= i.created_at <= period.end:
            sev = getattr(i, 'severity', 'unknown')
            counts[sev] = counts.get(sev, 0) + 1
    return counts


def calculate_engineer_workloads(incidents: list[Any], period: PerformancePeriod) -> dict[str, float]:
    severity_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    workloads: dict[str, float] = {}
    for i in incidents:
        if period.start <= i.created_at <= period.end and (assignee := getattr(i, 'assignee_id', None)):
            workloads[assignee] = workloads.get(assignee, 0) + severity_weights.get(getattr(i, 'severity', 'medium'), 2)
    return workloads


def calculate_workload_distribution(incidents: list[Any], period: PerformancePeriod) -> WorkloadDistribution:
    return WorkloadDistribution.from_workloads(list(calculate_engineer_workloads(incidents, period).values()))


def calculate_oncall_burden(oncall_shifts: list[dict], engineer_id: str, period: PerformancePeriod) -> float:
    total = 0.0
    for s in oncall_shifts:
        if s.get('engineer_id') != engineer_id: continue
        start, end = s.get('start'), s.get('end')
        if start and end:
            eff_start, eff_end = max(start, period.start), min(end, period.end)
            if eff_end > eff_start: total += (eff_end - eff_start).total_seconds() / 3600
    return round(total, 1)


def calculate_after_hours_incidents(incidents: list[Any], engineer_id: str, period: PerformancePeriod, biz_hours: tuple[int, int] = (9, 18)) -> int:
    count = 0
    for i in incidents:
        if period.start <= i.created_at <= period.end and getattr(i, 'assignee_id', None) == engineer_id:
            if i.created_at.hour < biz_hours[0] or i.created_at.hour >= biz_hours[1] or i.created_at.weekday() >= 5:
                count += 1
    return count


def calculate_burnout_risk(engineer_id: str, incidents: list[Any], oncall_shifts: list[dict], period: PerformancePeriod) -> BurnoutIndicators:
    factors, score = [], 0.0
    eng_incidents = [i for i in incidents if getattr(i, 'assignee_id', None) == engineer_id and period.start <= i.created_at <= period.end]
    
    after_hours = calculate_after_hours_incidents(incidents, engineer_id, period)
    if after_hours > 10: score, factors = score + 25, factors + [f"High after-hours pages: {after_hours}"]
    elif after_hours > 5: score, factors = score + 15, factors + [f"Moderate after-hours pages: {after_hours}"]
    
    high_sev = sum(1 for i in eng_incidents if getattr(i, 'severity', '') in ('critical', 'high'))
    if high_sev > 5: score, factors = score + 20, factors + [f"Many high-severity incidents: {high_sev}"]
    
    consecutive = _calc_consecutive_oncall(oncall_shifts, engineer_id, period.end)
    if consecutive > 7: score, factors = score + 30, factors + [f"Extended oncall: {consecutive} days"]
    elif consecutive > 4: score, factors = score + 15, factors + [f"Long oncall: {consecutive} days"]
    
    oncall_hrs = calculate_oncall_burden(oncall_shifts, engineer_id, period)
    if oncall_hrs > period.days * 24 / 5 * 1.5: score, factors = score + 20, factors + [f"Excessive oncall: {oncall_hrs:.0f}h"]
    
    resolved = [i for i in eng_incidents if i.resolved_at]
    avg_dur = sum((i.resolved_at - i.created_at).total_seconds() / 3600 for i in resolved) / len(resolved) if resolved else 0
    if avg_dur > 4: score, factors = score + 10, factors + [f"Long avg resolution: {avg_dur:.1f}h"]
    
    risk = BurnoutRisk.CRITICAL if score >= 60 else (BurnoutRisk.HIGH if score >= 40 else (BurnoutRisk.MODERATE if score >= 20 else BurnoutRisk.LOW))
    recs = _burnout_recs(factors, risk)
    return BurnoutIndicators(risk_level=risk, risk_score=min(100, score), factors=factors, consecutive_oncall_days=consecutive,
                             after_hours_incidents=after_hours, high_severity_count=high_sev, avg_incident_duration_hours=round(avg_dur, 1), recommendations=recs)


def _calc_consecutive_oncall(shifts: list[dict], eng_id: str, ref: datetime) -> int:
    eng_shifts = sorted([s for s in shifts if s.get('engineer_id') == eng_id], key=lambda s: s.get('end', datetime.min), reverse=True)
    consecutive, current = 0, ref.date()
    for s in eng_shifts:
        start, end = s.get('start'), s.get('end')
        if start and end and end.date() >= current and start.date() <= current:
            consecutive += (min(end.date(), current) - start.date()).days + 1
            current = start.date() - timedelta(days=1)
        elif end and end.date() < current: break
    return consecutive


def _burnout_recs(factors: list[str], risk: BurnoutRisk) -> list[str]:
    recs = []
    if risk in (BurnoutRisk.HIGH, BurnoutRisk.CRITICAL):
        recs += ["Consider immediate oncall rotation adjustment", "Schedule 1:1 to discuss workload"]
    if any("after-hours" in f.lower() for f in factors): recs.append("Review paging thresholds")
    if any("oncall" in f.lower() for f in factors): recs.append("Ensure break between rotations")
    return recs or ["Continue current patterns"]


def calculate_trend(current: float, previous: float, lower_is_better: bool = True) -> float:
    if previous == 0: return 0.0 if current == 0 else (100.0 if not lower_is_better else -100.0)
    return round(((current - previous) / previous) * 100, 1)


def create_metric_value(name: str, current: float, previous: float | None, unit: str = "", lower_is_better: bool = True, tier: PerformanceTier | None = None) -> MetricValue:
    trend = None if previous is None else (-1 if lower_is_better else 1) * calculate_trend(current, previous, lower_is_better)
    return MetricValue(name=name, value=current, unit=unit, trend=trend, tier=tier)
