"""FastAPI routes for performance analytics."""

from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .benchmarks import DORA_BENCHMARKS, compare_to_industry, get_benchmark_context
from .models import (
    EngineerMetrics,
    LeaderboardEntry,
    PerformancePeriod,
    PerformanceReport,
    PeriodComparison,
    TeamMetrics,
)
from .reports import ReportGenerator
from .service import PerformanceService

router = APIRouter(prefix="/performance", tags=["performance"])


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
    format: str = "json"


async def get_service() -> PerformanceService:
    raise HTTPException(503, "Service not configured")


@router.get("/health")
async def health():
    return {"status": "ok", "service": "performance-analytics"}


@router.post("/team/metrics", response_model=TeamMetrics)
async def get_team_metrics(
    request: TeamMetricsRequest, service: PerformanceService = Depends(get_service)
):
    period = PerformancePeriod(
        start=request.period.start, end=request.period.end, label=request.period.label
    )
    return await service.calculate_team_metrics(
        request.team_id, request.team_name, period
    )


@router.get("/team/{team_id}/metrics")
async def get_team_metrics_simple(
    team_id: str,
    team_name: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    service: PerformanceService = Depends(get_service),
):
    return await service.calculate_team_metrics(
        team_id, team_name, PerformancePeriod.last_n_days(days)
    )


@router.get("/team/{team_id}/trends")
async def get_team_trends(
    team_id: str,
    team_name: str = Query(...),
    periods: int = Query(4, ge=2, le=12),
    period_days: int = Query(7, ge=1, le=90),
    service: PerformanceService = Depends(get_service),
):
    trends = []
    for i in range(periods):
        p = PerformancePeriod(
            start=datetime.now(UTC) - timedelta(days=(i + 1) * period_days),
            end=datetime.now(UTC) - timedelta(days=i * period_days),
            label=f"P{periods - i}",
        )
        m = await service.calculate_team_metrics(team_id, team_name, p)
        trends.append(
            {
                "period": p.model_dump(),
                "mttr": m.mttr_minutes,
                "mtta": m.mtta_minutes,
                "incidents": m.total_incidents,
                "tier": m.tier.value,
            }
        )
    return {"team_id": team_id, "trends": list(reversed(trends))}


@router.post("/compare", response_model=PeriodComparison)
async def compare_periods(
    request: CompareRequest, service: PerformanceService = Depends(get_service)
):
    curr = PerformancePeriod(
        start=request.current.start,
        end=request.current.end,
        label=request.current.label or "Current",
    )
    prev = PerformancePeriod(
        start=request.previous.start,
        end=request.previous.end,
        label=request.previous.label or "Previous",
    )
    return await service.compare_periods(request.team_id, request.team_name, curr, prev)


@router.get("/engineer/{engineer_id}/metrics", response_model=EngineerMetrics)
async def get_engineer_metrics(
    engineer_id: str,
    team_id: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    include_burnout: bool = Query(True),
    anonymize: bool = Query(False),
    service: PerformanceService = Depends(get_service),
):
    return await service.calculate_engineer_metrics(
        engineer_id,
        f"Eng {engineer_id[:6]}",
        team_id,
        PerformancePeriod.last_n_days(days),
        include_burnout,
        anonymize,
    )


@router.get("/team/{team_id}/burnout")
async def get_burnout_summary(
    team_id: str,
    days: int = Query(30, ge=1, le=90),
    service: PerformanceService = Depends(get_service),
):
    return await service.get_team_burnout_summary(
        team_id, PerformancePeriod.last_n_days(days)
    )


@router.get("/team/{team_id}/workload")
async def get_workload_distribution(
    team_id: str,
    team_name: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    service: PerformanceService = Depends(get_service),
):
    m = await service.calculate_team_metrics(
        team_id, team_name, PerformancePeriod.last_n_days(days)
    )
    return {
        "team_id": team_id,
        "distribution": (
            m.workload_distribution.model_dump() if m.workload_distribution else None
        ),
        "avg_per_engineer": m.avg_incidents_per_engineer,
    }


@router.get("/team/{team_id}/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    team_id: str,
    metric: str = Query("resolution_rate"),
    days: int = Query(30, ge=1, le=365),
    top_n: int = Query(10, ge=1, le=50),
    anonymize: bool = Query(False),
    service: PerformanceService = Depends(get_service),
):
    if metric not in [
        "resolution_rate",
        "response_time",
        "incidents_resolved",
        "incidents_handled",
    ]:
        raise HTTPException(400, "Invalid metric")
    return await service.generate_leaderboard(
        team_id, PerformancePeriod.last_n_days(days), metric, top_n, anonymize
    )


@router.post("/report", response_model=PerformanceReport)
async def generate_report(
    request: ReportRequest, service: PerformanceService = Depends(get_service)
):
    period = PerformancePeriod(
        start=request.period.start, end=request.period.end, label=request.period.label
    )
    gen = ReportGenerator(service)
    report = await gen.generate_team_report(
        request.team_id,
        request.team_name,
        period,
        request.include_engineers,
        request.anonymize_engineers,
        request.include_comparison,
    )
    if request.format == "markdown":
        return {"markdown": gen.export_markdown(report)}
    if request.format == "csv":
        return {"csv": gen.export_csv_metrics(report)}
    return report


@router.get("/benchmarks")
async def get_benchmarks():
    return {
        k: {
            "name": b.name,
            "thresholds": {
                "elite": b.elite_threshold,
                "high": b.high_threshold,
                "medium": b.medium_threshold,
            },
            "unit": b.unit,
            "lower_is_better": b.lower_is_better,
        }
        for k, b in DORA_BENCHMARKS.items()
    }


@router.get("/benchmarks/{metric}")
async def get_benchmark_detail(metric: str):
    ctx = get_benchmark_context(metric)
    if not ctx.get("available"):
        raise HTTPException(404, f"No benchmark: {metric}")
    return ctx


@router.post("/team/{team_id}/industry-comparison")
async def get_industry_comparison(
    team_id: str,
    team_name: str = Query(...),
    days: int = Query(30, ge=1, le=365),
    service: PerformanceService = Depends(get_service),
):
    return compare_to_industry(
        await service.calculate_team_metrics(
            team_id, team_name, PerformancePeriod.last_n_days(days)
        )
    )
