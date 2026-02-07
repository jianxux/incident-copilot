"""FastAPI routes for performance analytics."""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel

from .models import (
    PerformancePeriod, TeamMetrics, EngineerMetrics, PeriodComparison,
    LeaderboardEntry, PerformanceReport
)
from .service import PerformanceService
from .reports import ReportGenerator
from .benchmarks import get_benchmark_context, compare_to_industry, DORA_BENCHMARKS

router = APIRouter(prefix="/performance", tags=["performance"])


# Request/Response models
class PeriodRequest(BaseModel):
    start: datetime
    end: datetime
    label: str = ""


class TeamMetricsRequest(BaseModel):
    team_id: str
    team_name: str
    period: PeriodRequest


class CompareRequest(BaseModel):
    team_id: str
    team_name: str
    current: PeriodRequest
    previous: PeriodRequest


class ReportRequest(BaseModel):
    team_id: str
    team_name: str
    period: PeriodRequest
    include_engineers: bool = True
    anonymize_engineers: bool = False
    include_comparison: bool = True
    format: str = "json"  # json, markdown, csv


# Dependency for service (would be injected in real app)
async def get_service() -> PerformanceService:
    """Get performance service instance."""
    # In real app, this would be dependency-injected with actual repos
    raise HTTPException(503, "Service not configured")


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "performance-analytics"}


@router.post("/team/metrics", response_model=TeamMetrics)
async def get_team_metrics(
    request: TeamMetricsRequest,
    service: PerformanceService = Depends(get_service)
):
    """Get comprehensive team metrics for a period."""
    period = PerformancePeriod(
        start=request.period.start,
        end=request.period.end,
        label=request.period.label
    )
    return await service.calculate_team_metrics(request.team_id, request.team_name, period)


@router.get("/team/{team_id}/metrics")
async def get_team_metrics_simple(
    team_id: str,
    team_name: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    service: PerformanceService = Depends(get_service)
):
    """Get team metrics for last N days."""
    period = PerformancePeriod.last_n_days(days)
    return await service.calculate_team_metrics(team_id, team_name, period)


@router.get("/team/{team_id}/trends")
async def get_team_trends(
    team_id: str,
    team_name: str = Query(...),
    periods: int = Query(4, ge=2, le=12, description="Number of periods to compare"),
    period_days: int = Query(7, ge=1, le=90, description="Days per period"),
    service: PerformanceService = Depends(get_service)
):
    """Get metric trends over multiple periods."""
    trends = []
    for i in range(periods):
        end_offset = i * period_days
        start_offset = (i + 1) * period_days
        period = PerformancePeriod.last_n_days(period_days)
        period.start = datetime.utcnow() - __import__('datetime').timedelta(days=start_offset)
        period.end = datetime.utcnow() - __import__('datetime').timedelta(days=end_offset)
        period.label = f"Period {periods - i}"
        
        metrics = await service.calculate_team_metrics(team_id, team_name, period)
        trends.append({
            "period": period.model_dump(),
            "mttr": metrics.mttr_minutes,
            "mtta": metrics.mtta_minutes,
            "incidents": metrics.total_incidents,
            "sla_compliance": metrics.sla_compliance_rate,
            "tier": metrics.tier.value
        })
    
    return {"team_id": team_id, "trends": list(reversed(trends))}


@router.post("/compare", response_model=PeriodComparison)
async def compare_periods(
    request: CompareRequest,
    service: PerformanceService = Depends(get_service)
):
    """Compare metrics between two periods."""
    current = PerformancePeriod(
        start=request.current.start,
        end=request.current.end,
        label=request.current.label or "Current"
    )
    previous = PerformancePeriod(
        start=request.previous.start,
        end=request.previous.end,
        label=request.previous.label or "Previous"
    )
    return await service.compare_periods(request.team_id, request.team_name, current, previous)


@router.get("/engineer/{engineer_id}/metrics", response_model=EngineerMetrics)
async def get_engineer_metrics(
    engineer_id: str,
    team_id: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    include_burnout: bool = Query(True),
    anonymize: bool = Query(False),
    service: PerformanceService = Depends(get_service)
):
    """Get individual engineer metrics."""
    period = PerformancePeriod.last_n_days(days)
    return await service.calculate_engineer_metrics(
        engineer_id, f"Engineer {engineer_id[:6]}", team_id, period,
        include_burnout=include_burnout, anonymize=anonymize
    )


@router.get("/team/{team_id}/burnout")
async def get_burnout_summary(
    team_id: str,
    days: int = Query(30, ge=1, le=90),
    service: PerformanceService = Depends(get_service)
):
    """Get team burnout risk summary."""
    period = PerformancePeriod.last_n_days(days)
    return await service.get_team_burnout_summary(team_id, period)


@router.get("/team/{team_id}/workload")
async def get_workload_distribution(
    team_id: str,
    team_name: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    service: PerformanceService = Depends(get_service)
):
    """Get team workload distribution analysis."""
    period = PerformancePeriod.last_n_days(days)
    metrics = await service.calculate_team_metrics(team_id, team_name, period)
    
    return {
        "team_id": team_id,
        "period": period.model_dump(),
        "distribution": metrics.workload_distribution.model_dump() if metrics.workload_distribution else None,
        "avg_per_engineer": metrics.avg_incidents_per_engineer,
        "oncall_burden_hours": metrics.oncall_burden_hours
    }


@router.get("/team/{team_id}/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    team_id: str,
    metric: str = Query("resolution_rate", description="Metric to rank by"),
    days: int = Query(30, ge=1, le=365),
    top_n: int = Query(10, ge=1, le=50),
    anonymize: bool = Query(False),
    service: PerformanceService = Depends(get_service)
):
    """Get performance leaderboard (gamification)."""
    valid_metrics = ["resolution_rate", "response_time", "incidents_resolved", "incidents_handled"]
    if metric not in valid_metrics:
        raise HTTPException(400, f"Invalid metric. Choose from: {valid_metrics}")
    
    period = PerformancePeriod.last_n_days(days)
    return await service.generate_leaderboard(team_id, period, metric, top_n, anonymize)


@router.post("/report", response_model=PerformanceReport)
async def generate_report(
    request: ReportRequest,
    service: PerformanceService = Depends(get_service)
):
    """Generate comprehensive performance report."""
    period = PerformancePeriod(
        start=request.period.start,
        end=request.period.end,
        label=request.period.label
    )
    generator = ReportGenerator(service)
    report = await generator.generate_team_report(
        request.team_id, request.team_name, period,
        include_engineers=request.include_engineers,
        anonymize_engineers=request.anonymize_engineers,
        include_comparison=request.include_comparison
    )
    
    if request.format == "markdown":
        return {"markdown": generator.export_markdown(report)}
    elif request.format == "csv":
        return {"csv": generator.export_csv_metrics(report)}
    
    return report


@router.get("/benchmarks")
async def get_benchmarks():
    """Get available industry benchmarks."""
    return {
        name: {
            "name": b.name,
            "thresholds": {
                "elite": b.elite_threshold,
                "high": b.high_threshold,
                "medium": b.medium_threshold
            },
            "unit": b.unit,
            "lower_is_better": b.lower_is_better,
            "source": b.source
        }
        for name, b in DORA_BENCHMARKS.items()
    }


@router.get("/benchmarks/{metric}")
async def get_benchmark_detail(metric: str):
    """Get detailed benchmark info for a metric."""
    context = get_benchmark_context(metric)
    if not context.get("available"):
        raise HTTPException(404, f"No benchmark found for metric: {metric}")
    return context


@router.post("/team/{team_id}/industry-comparison")
async def get_industry_comparison(
    team_id: str,
    team_name: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    service: PerformanceService = Depends(get_service)
):
    """Compare team against industry benchmarks."""
    period = PerformancePeriod.last_n_days(days)
    metrics = await service.calculate_team_metrics(team_id, team_name, period)
    return compare_to_industry(metrics)
