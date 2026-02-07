"""Metric calculators for performance analytics."""

from datetime import datetime, timedelta
from typing import Protocol, Any
from .models import (
    PerformancePeriod, BurnoutIndicators, BurnoutRisk,
    WorkloadDistribution, MetricValue, PerformanceTier
)


class Incident(Protocol):
    """Protocol for incident objects."""
    id: str
    severity: str
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    assignee_id: str | None


def calculate_mttr(incidents: list[Any], period: PerformancePeriod) -> float:
    """Calculate Mean Time To Resolve in minutes."""
    resolved = [
        i for i in incidents
        if i.resolved_at and period.start <= i.created_at <= period.end
    ]
    if not resolved:
        return 0.0
    
    total_minutes = sum(
        (i.resolved_at - i.created_at).total_seconds() / 60
        for i in resolved
    )
    return round(total_minutes / len(resolved), 2)


def calculate_mtta(incidents: list[Any], period: PerformancePeriod) -> float:
    """Calculate Mean Time To Acknowledge in minutes."""
    acknowledged = [
        i for i in incidents
        if i.acknowledged_at and period.start <= i.created_at <= period.end
    ]
    if not acknowledged:
        return 0.0
    
    total_minutes = sum(
        (i.acknowledged_at - i.created_at).total_seconds() / 60
        for i in acknowledged
    )
    return round(total_minutes / len(acknowledged), 2)


def calculate_mttd(incidents: list[Any], period: PerformancePeriod) -> float:
    """Calculate Mean Time To Detect in minutes (if detection time available)."""
    detected = [
        i for i in incidents
        if hasattr(i, 'detected_at') and i.detected_at and period.start <= i.created_at <= period.end
    ]
    if not detected:
        return 0.0
    
    total_minutes = sum(
        (i.created_at - i.detected_at).total_seconds() / 60
        for i in detected
    )
    return round(total_minutes / len(detected), 2)


def count_incidents_by_severity(incidents: list[Any], period: PerformancePeriod) -> dict[str, int]:
    """Count incidents grouped by severity."""
    counts: dict[str, int] = {}
    for incident in incidents:
        if period.start <= incident.created_at <= period.end:
            sev = getattr(incident, 'severity', 'unknown')
            counts[sev] = counts.get(sev, 0) + 1
    return counts


def calculate_engineer_workloads(
    incidents: list[Any],
    period: PerformancePeriod
) -> dict[str, float]:
    """Calculate workload per engineer (incident count weighted by severity)."""
    severity_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    workloads: dict[str, float] = {}
    
    for incident in incidents:
        if not (period.start <= incident.created_at <= period.end):
            continue
        assignee = getattr(incident, 'assignee_id', None)
        if not assignee:
            continue
        weight = severity_weights.get(getattr(incident, 'severity', 'medium'), 2)
        workloads[assignee] = workloads.get(assignee, 0) + weight
    
    return workloads


def calculate_workload_distribution(
    incidents: list[Any],
    period: PerformancePeriod
) -> WorkloadDistribution:
    """Calculate workload distribution metrics."""
    workloads = calculate_engineer_workloads(incidents, period)
    return WorkloadDistribution.from_workloads(list(workloads.values()))


def calculate_oncall_burden(
    oncall_shifts: list[dict],
    engineer_id: str,
    period: PerformancePeriod
) -> float:
    """Calculate total oncall hours for an engineer."""
    total_hours = 0.0
    for shift in oncall_shifts:
        if shift.get('engineer_id') != engineer_id:
            continue
        shift_start = shift.get('start')
        shift_end = shift.get('end')
        if not (shift_start and shift_end):
            continue
        # Overlap with period
        effective_start = max(shift_start, period.start)
        effective_end = min(shift_end, period.end)
        if effective_end > effective_start:
            total_hours += (effective_end - effective_start).total_seconds() / 3600
    return round(total_hours, 1)


def calculate_after_hours_incidents(
    incidents: list[Any],
    engineer_id: str,
    period: PerformancePeriod,
    business_hours: tuple[int, int] = (9, 18)
) -> int:
    """Count incidents handled outside business hours."""
    start_hour, end_hour = business_hours
    count = 0
    for incident in incidents:
        if not (period.start <= incident.created_at <= period.end):
            continue
        if getattr(incident, 'assignee_id', None) != engineer_id:
            continue
        hour = incident.created_at.hour
        if hour < start_hour or hour >= end_hour or incident.created_at.weekday() >= 5:
            count += 1
    return count


def calculate_burnout_risk(
    engineer_id: str,
    incidents: list[Any],
    oncall_shifts: list[dict],
    period: PerformancePeriod
) -> BurnoutIndicators:
    """Calculate burnout risk indicators for an engineer."""
    factors = []
    score = 0.0
    
    # Incident load
    engineer_incidents = [
        i for i in incidents
        if getattr(i, 'assignee_id', None) == engineer_id
        and period.start <= i.created_at <= period.end
    ]
    incident_count = len(engineer_incidents)
    
    # After hours
    after_hours = calculate_after_hours_incidents(incidents, engineer_id, period)
    if after_hours > 10:
        score += 25
        factors.append(f"High after-hours pages: {after_hours}")
    elif after_hours > 5:
        score += 15
        factors.append(f"Moderate after-hours pages: {after_hours}")
    
    # High severity incidents
    high_sev = sum(1 for i in engineer_incidents if getattr(i, 'severity', '') in ('critical', 'high'))
    if high_sev > 5:
        score += 20
        factors.append(f"Many high-severity incidents: {high_sev}")
    
    # Consecutive oncall days
    consecutive = _calculate_consecutive_oncall(oncall_shifts, engineer_id, period.end)
    if consecutive > 7:
        score += 30
        factors.append(f"Extended oncall stretch: {consecutive} days")
    elif consecutive > 4:
        score += 15
        factors.append(f"Long oncall stretch: {consecutive} days")
    
    # Oncall burden
    oncall_hours = calculate_oncall_burden(oncall_shifts, engineer_id, period)
    expected_hours = period.days * 24 / 5  # Assume 5-person rotation
    if oncall_hours > expected_hours * 1.5:
        score += 20
        factors.append(f"Excessive oncall hours: {oncall_hours:.0f}h")
    
    # Average incident duration
    resolved = [i for i in engineer_incidents if i.resolved_at]
    avg_duration = 0.0
    if resolved:
        avg_duration = sum(
            (i.resolved_at - i.created_at).total_seconds() / 3600
            for i in resolved
        ) / len(resolved)
        if avg_duration > 4:
            score += 10
            factors.append(f"Long avg resolution time: {avg_duration:.1f}h")
    
    # Determine risk level
    if score >= 60:
        risk_level = BurnoutRisk.CRITICAL
    elif score >= 40:
        risk_level = BurnoutRisk.HIGH
    elif score >= 20:
        risk_level = BurnoutRisk.MODERATE
    else:
        risk_level = BurnoutRisk.LOW
    
    # Recommendations
    recommendations = _generate_burnout_recommendations(factors, risk_level)
    
    return BurnoutIndicators(
        risk_level=risk_level,
        risk_score=min(100, score),
        factors=factors,
        consecutive_oncall_days=consecutive,
        after_hours_incidents=after_hours,
        high_severity_count=high_sev,
        avg_incident_duration_hours=round(avg_duration, 1),
        recommendations=recommendations
    )


def _calculate_consecutive_oncall(
    oncall_shifts: list[dict],
    engineer_id: str,
    reference_date: datetime
) -> int:
    """Calculate consecutive oncall days ending at reference date."""
    engineer_shifts = sorted(
        [s for s in oncall_shifts if s.get('engineer_id') == engineer_id],
        key=lambda s: s.get('end', datetime.min),
        reverse=True
    )
    if not engineer_shifts:
        return 0
    
    consecutive = 0
    current = reference_date.date()
    for shift in engineer_shifts:
        shift_end = shift.get('end')
        shift_start = shift.get('start')
        if not (shift_end and shift_start):
            continue
        if shift_end.date() >= current and shift_start.date() <= current:
            days = (min(shift_end.date(), current) - shift_start.date()).days + 1
            consecutive += days
            current = shift_start.date() - timedelta(days=1)
        elif shift_end.date() < current:
            break
    return consecutive


def _generate_burnout_recommendations(factors: list[str], risk: BurnoutRisk) -> list[str]:
    """Generate recommendations based on burnout factors."""
    recs = []
    if risk in (BurnoutRisk.HIGH, BurnoutRisk.CRITICAL):
        recs.append("Consider immediate oncall rotation adjustment")
        recs.append("Schedule 1:1 with manager to discuss workload")
    if any("after-hours" in f.lower() for f in factors):
        recs.append("Review paging thresholds to reduce noise")
    if any("oncall" in f.lower() for f in factors):
        recs.append("Ensure adequate break between oncall rotations")
    if any("high-severity" in f.lower() for f in factors):
        recs.append("Pair with another engineer for critical incidents")
    if not recs:
        recs.append("Continue current workload patterns")
    return recs


def calculate_trend(current: float, previous: float, lower_is_better: bool = True) -> float:
    """Calculate percentage trend between periods."""
    if previous == 0:
        return 0.0 if current == 0 else (100.0 if not lower_is_better else -100.0)
    change = ((current - previous) / previous) * 100
    return round(change, 1)


def create_metric_value(
    name: str,
    current: float,
    previous: float | None,
    unit: str = "",
    lower_is_better: bool = True,
    tier: PerformanceTier | None = None
) -> MetricValue:
    """Create a MetricValue with trend calculation."""
    trend = None
    if previous is not None:
        raw_trend = calculate_trend(current, previous, lower_is_better)
        # Adjust sign: positive trend = improvement
        trend = -raw_trend if lower_is_better else raw_trend
    
    return MetricValue(
        name=name,
        value=current,
        unit=unit,
        trend=trend,
        tier=tier
    )
