"""FastAPI routes for performance dashboard."""

from datetime import datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .calculator import PerformanceCalculator
from .leaderboard import Leaderboard, LeaderboardGenerator, LeaderboardType
from .models import (
    BurnoutIndicator,
    IncidentVolume,
    LeaderboardRequest,
    MetricsRequest,
    OnCallStats,
    PerformanceReport,
    PerformanceSummary,
    PerformanceTrend,
    ReportRequest,
    SLACompliance,
    TeamMetrics,
    TimeDistribution,
    WorkloadDistribution,
)
from .reports import ReportFormat, ReportGenerator
from .trends import TrendAnalyzer

logger = structlog.get_logger()
router = APIRouter(prefix="/api/performance", tags=["performance"])

# Initialize components
calculator = PerformanceCalculator()
trend_analyzer = TrendAnalyzer(calculator)
leaderboard_generator = LeaderboardGenerator(calculator)
report_generator = ReportGenerator(calculator, trend_analyzer, leaderboard_generator)

# In-memory storage for demo purposes
# In production, this would be backed by a database
_incidents_store: list[dict] = []
_oncall_store: list[dict] = []


# --- Response Models ---


class TeamMetricsResponse(BaseModel):
    """Response for team metrics endpoint."""

    metrics: TeamMetrics
    message: str = "Metrics calculated successfully"


class TrendsResponse(BaseModel):
    """Response for trends endpoint."""

    trends: list[PerformanceTrend]
    anomalies: list[dict] = []
    message: str = "Trends calculated successfully"


class LeaderboardResponse(BaseModel):
    """Response for leaderboard endpoint."""

    leaderboard: Leaderboard
    message: str = "Leaderboard generated successfully"


class ReportResponse(BaseModel):
    """Response for report generation."""

    report: PerformanceReport
    message: str = "Report generated successfully"


class ExportResponse(BaseModel):
    """Response for report export."""

    format: ReportFormat
    content: str
    report_id: str


class OnCallStatsResponse(BaseModel):
    """Response for on-call stats."""

    stats: list[OnCallStats]
    total_responders: int
    message: str = "On-call stats calculated successfully"


class BurnoutResponse(BaseModel):
    """Response for burnout indicators."""

    indicators: list[BurnoutIndicator]
    high_risk_count: int
    message: str = "Burnout indicators calculated successfully"


class VolumeResponse(BaseModel):
    """Response for incident volume."""

    volume: IncidentVolume
    time_distribution: TimeDistribution
    message: str = "Volume analysis complete"


class SLAResponse(BaseModel):
    """Response for SLA compliance."""

    compliance: SLACompliance
    message: str = "SLA compliance calculated successfully"


class WorkloadResponse(BaseModel):
    """Response for workload distribution."""

    distribution: WorkloadDistribution
    message: str = "Workload distribution calculated successfully"


# --- Data Management Endpoints ---


@router.post("/incidents")
async def add_incidents(incidents: list[dict]) -> dict:
    """
    Add incidents for analysis.

    This endpoint allows adding incident data for performance analysis.
    In production, this would typically be pulled from PagerDuty/Opsgenie.

    Example incident:
    ```json
    {
        "id": "INC-123",
        "title": "High error rate",
        "severity": "high",
        "service_name": "payments-api",
        "team_name": "payments-team",
        "triggered_at": "2024-01-15T10:00:00Z",
        "acknowledged_at": "2024-01-15T10:05:00Z",
        "resolved_at": "2024-01-15T11:00:00Z",
        "assigned_to": ["user-1", "user-2"],
        "responder_id": "user-1"
    }
    ```
    """
    _incidents_store.extend(incidents)
    logger.info("incidents_added", count=len(incidents), total=len(_incidents_store))
    return {"message": f"Added {len(incidents)} incidents", "total": len(_incidents_store)}


@router.post("/oncall")
async def add_oncall_data(oncall_data: list[dict]) -> dict:
    """
    Add on-call roster data.

    Example on-call entry:
    ```json
    {
        "id": "user-1",
        "name": "Jane Doe",
        "email": "jane@example.com",
        "team_name": "payments-team",
        "oncall_hours": 168
    }
    ```
    """
    _oncall_store.extend(oncall_data)
    logger.info("oncall_added", count=len(oncall_data), total=len(_oncall_store))
    return {"message": f"Added {len(oncall_data)} on-call entries", "total": len(_oncall_store)}


@router.delete("/data")
async def clear_data() -> dict:
    """Clear all stored data (for testing)."""
    _incidents_store.clear()
    _oncall_store.clear()
    return {"message": "All data cleared"}


# --- Metrics Endpoints ---


@router.get("/metrics", response_model=TeamMetricsResponse)
async def get_team_metrics(
    start_date: Annotated[
        datetime | None,
        Query(description="Start date for metrics period"),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(description="End date for metrics period"),
    ] = None,
    team_name: Annotated[
        str | None,
        Query(description="Filter by team name"),
    ] = None,
    service_name: Annotated[
        str | None,
        Query(description="Filter by service name"),
    ] = None,
) -> TeamMetricsResponse:
    """
    Get team performance metrics.

    Returns MTTR, MTTA, incident counts, and SLA compliance for the specified period.
    Defaults to the last 7 days if no dates provided.
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    metrics = calculator.calculate_team_metrics(
        incidents=_incidents_store,
        period_start=start_date,
        period_end=end_date,
        team_name=team_name,
        service_name=service_name,
    )

    return TeamMetricsResponse(metrics=metrics)


@router.post("/metrics/calculate", response_model=TeamMetricsResponse)
async def calculate_metrics(request: MetricsRequest) -> TeamMetricsResponse:
    """
    Calculate team metrics with custom parameters.

    Allows specifying all calculation options including comparison to previous period.
    """
    end_date = request.end_date or datetime.utcnow()
    start_date = request.start_date or (end_date - timedelta(days=7))

    previous_metrics = None
    if request.compare_to_previous:
        period_duration = end_date - start_date
        prev_start = start_date - period_duration
        prev_end = start_date
        previous_metrics = calculator.calculate_team_metrics(
            incidents=_incidents_store,
            period_start=prev_start,
            period_end=prev_end,
            team_name=request.team_name,
            service_name=request.service_name,
        )

    metrics = calculator.calculate_team_metrics(
        incidents=_incidents_store,
        period_start=start_date,
        period_end=end_date,
        team_name=request.team_name,
        service_name=request.service_name,
        previous_metrics=previous_metrics,
    )

    return TeamMetricsResponse(metrics=metrics)


# --- Trends Endpoints ---


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
    service_name: Annotated[str | None, Query()] = None,
    include_anomalies: Annotated[bool, Query()] = True,
) -> TrendsResponse:
    """
    Get performance trends.

    Returns MTTR, MTTA, incident count, and SLA compliance trends
    compared to the previous period.
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    trends = trend_analyzer.calculate_all_trends(
        incidents=_incidents_store,
        period_start=start_date,
        period_end=end_date,
        team_name=team_name,
        service_name=service_name,
    )

    anomalies = []
    if include_anomalies:
        anomalies = trend_analyzer.detect_anomalies(
            incidents=_incidents_store,
            period_start=start_date,
            period_end=end_date,
            team_name=team_name,
            service_name=service_name,
        )

    return TrendsResponse(trends=trends, anomalies=anomalies)


@router.get("/trends/week-over-week", response_model=TrendsResponse)
async def get_week_over_week(
    reference_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
    service_name: Annotated[str | None, Query()] = None,
) -> TrendsResponse:
    """Get week-over-week performance trends."""
    trends = trend_analyzer.week_over_week(
        incidents=_incidents_store,
        reference_date=reference_date,
        team_name=team_name,
        service_name=service_name,
    )
    return TrendsResponse(trends=trends)


@router.get("/trends/month-over-month", response_model=TrendsResponse)
async def get_month_over_month(
    reference_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
    service_name: Annotated[str | None, Query()] = None,
) -> TrendsResponse:
    """Get month-over-month performance trends."""
    trends = trend_analyzer.month_over_month(
        incidents=_incidents_store,
        reference_date=reference_date,
        team_name=team_name,
        service_name=service_name,
    )
    return TrendsResponse(trends=trends)


# --- Leaderboard Endpoints ---


@router.get("/leaderboard/{leaderboard_type}", response_model=LeaderboardResponse)
async def get_leaderboard(
    leaderboard_type: LeaderboardType,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> LeaderboardResponse:
    """
    Get a specific leaderboard.

    Available types:
    - top_responders: Overall performance score
    - fastest_response: Fastest acknowledgment times
    - most_resolved: Most incidents resolved
    - best_sla: Highest SLA compliance
    - team_rankings: Team-level rankings
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    # Build on-call stats for each responder
    oncall_stats = _build_oncall_stats(start_date, end_date, team_name)

    if leaderboard_type == LeaderboardType.TOP_RESPONDERS:
        leaderboard = leaderboard_generator.generate_top_responders(
            oncall_stats=oncall_stats,
            period_start=start_date,
            period_end=end_date,
            team_name=team_name,
            limit=limit,
        )
    elif leaderboard_type == LeaderboardType.FASTEST_RESPONSE:
        leaderboard = leaderboard_generator.generate_fastest_response(
            oncall_stats=oncall_stats,
            period_start=start_date,
            period_end=end_date,
            team_name=team_name,
            limit=limit,
        )
    elif leaderboard_type == LeaderboardType.MOST_RESOLVED:
        leaderboard = leaderboard_generator.generate_most_resolved(
            oncall_stats=oncall_stats,
            incidents=_incidents_store,
            period_start=start_date,
            period_end=end_date,
            team_name=team_name,
            limit=limit,
        )
    elif leaderboard_type == LeaderboardType.BEST_SLA:
        leaderboard = leaderboard_generator.generate_best_sla(
            oncall_stats=oncall_stats,
            incidents=_incidents_store,
            period_start=start_date,
            period_end=end_date,
            team_name=team_name,
            limit=limit,
        )
    elif leaderboard_type == LeaderboardType.TEAM_RANKINGS:
        leaderboard = leaderboard_generator.generate_team_rankings(
            oncall_stats=oncall_stats,
            period_start=start_date,
            period_end=end_date,
            limit=limit,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown leaderboard type: {leaderboard_type}")

    return LeaderboardResponse(leaderboard=leaderboard)


@router.post("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard_custom(request: LeaderboardRequest) -> LeaderboardResponse:
    """Get leaderboard with custom parameters."""
    end_date = request.end_date or datetime.utcnow()
    start_date = request.start_date or (end_date - timedelta(days=7))

    oncall_stats = _build_oncall_stats(start_date, end_date, request.team_name)

    leaderboard = leaderboard_generator.generate_top_responders(
        oncall_stats=oncall_stats,
        period_start=start_date,
        period_end=end_date,
        team_name=request.team_name,
        limit=request.limit,
    )

    return LeaderboardResponse(leaderboard=leaderboard)


# --- On-Call Stats Endpoints ---


@router.get("/oncall-stats", response_model=OnCallStatsResponse)
async def get_oncall_stats(
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
    responder_id: Annotated[str | None, Query()] = None,
) -> OnCallStatsResponse:
    """
    Get on-call statistics for responders.

    Returns page counts, response times, and workload distribution.
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    stats = _build_oncall_stats(start_date, end_date, team_name)

    if responder_id:
        stats = [s for s in stats if s.responder_id == responder_id]

    return OnCallStatsResponse(
        stats=stats,
        total_responders=len(stats),
    )


# --- Burnout Endpoints ---


@router.get("/burnout", response_model=BurnoutResponse)
async def get_burnout_indicators(
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
) -> BurnoutResponse:
    """
    Get burnout risk indicators for all responders.

    Returns risk scores and recommendations for each responder.
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    oncall_stats = _build_oncall_stats(start_date, end_date, team_name)
    indicators = [calculator.calculate_burnout_indicator(s) for s in oncall_stats]

    high_risk = [i for i in indicators if i.risk_level in ("high", "critical")]

    return BurnoutResponse(
        indicators=indicators,
        high_risk_count=len(high_risk),
    )


# --- Volume Endpoints ---


@router.get("/volume", response_model=VolumeResponse)
async def get_incident_volume(
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
) -> VolumeResponse:
    """
    Get incident volume analysis.

    Returns distribution by hour, day, severity, and service.
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    volume = calculator.calculate_incident_volume(
        incidents=_incidents_store,
        period_start=start_date,
        period_end=end_date,
    )

    time_dist = calculator.calculate_time_distribution(
        incidents=_incidents_store,
        period_start=start_date,
        period_end=end_date,
    )

    return VolumeResponse(volume=volume, time_distribution=time_dist)


# --- SLA Endpoints ---


@router.get("/sla", response_model=SLAResponse)
async def get_sla_compliance(
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
    service_name: Annotated[str | None, Query()] = None,
) -> SLAResponse:
    """
    Get SLA compliance metrics.

    Returns overall and per-severity SLA compliance percentages.
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    compliance = calculator.calculate_sla_compliance(
        incidents=_incidents_store,
        period_start=start_date,
        period_end=end_date,
        team_name=team_name,
        service_name=service_name,
    )

    return SLAResponse(compliance=compliance)


# --- Workload Endpoints ---


@router.get("/workload", response_model=WorkloadResponse)
async def get_workload_distribution(
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
) -> WorkloadResponse:
    """
    Get workload distribution across responders.

    Returns fairness metrics including Gini coefficient.
    """
    if end_date is None:
        end_date = datetime.utcnow()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    oncall_stats = _build_oncall_stats(start_date, end_date, team_name)

    distribution = calculator.calculate_workload_distribution(
        oncall_stats=oncall_stats,
        period_start=start_date,
        period_end=end_date,
        team_name=team_name,
    )

    return WorkloadResponse(distribution=distribution)


# --- Report Endpoints ---


@router.post("/reports/generate", response_model=ReportResponse)
async def generate_report(request: ReportRequest) -> ReportResponse:
    """
    Generate a comprehensive performance report.

    Returns full metrics, trends, leaderboards, and insights.
    """
    end_date = request.end_date or datetime.utcnow()
    start_date = request.start_date or (end_date - timedelta(days=7))

    report = await report_generator.generate_report(
        incidents=_incidents_store,
        oncall_data=_oncall_store,
        period_start=start_date,
        period_end=end_date,
        team_name=request.team_name,
        service_name=request.service_name,
        include_ai_summary=request.include_ai_summary,
    )

    return ReportResponse(report=report)


@router.get("/reports/weekly", response_model=ReportResponse)
async def get_weekly_digest(
    reference_date: Annotated[datetime | None, Query()] = None,
    team_name: Annotated[str | None, Query()] = None,
    service_name: Annotated[str | None, Query()] = None,
) -> ReportResponse:
    """
    Generate a weekly performance digest.

    Automatically calculates the current week boundaries.
    """
    report = await report_generator.generate_weekly_digest(
        incidents=_incidents_store,
        oncall_data=_oncall_store,
        reference_date=reference_date,
        team_name=team_name,
        service_name=service_name,
    )

    return ReportResponse(report=report)


@router.post("/reports/{report_id}/export", response_model=ExportResponse)
async def export_report(
    report_id: str,
    format: ReportFormat = ReportFormat.MARKDOWN,
) -> ExportResponse:
    """
    Export a report in the specified format.

    Supported formats: json, markdown, slack, html
    """
    # For demo, regenerate the report
    # In production, would fetch from storage
    report = await report_generator.generate_weekly_digest(
        incidents=_incidents_store,
        oncall_data=_oncall_store,
    )

    content = report_generator.export_report(report, format)

    return ExportResponse(
        format=format,
        content=content,
        report_id=report.report_id,
    )


@router.get("/reports/{report_id}/export/{format}")
async def export_report_raw(
    report_id: str,
    format: ReportFormat,
) -> PlainTextResponse:
    """
    Export a report and return raw content.

    Returns the exported content directly without JSON wrapping.
    """
    report = await report_generator.generate_weekly_digest(
        incidents=_incidents_store,
        oncall_data=_oncall_store,
    )

    content = report_generator.export_report(report, format)

    content_types = {
        ReportFormat.JSON: "application/json",
        ReportFormat.MARKDOWN: "text/markdown",
        ReportFormat.SLACK: "application/json",
        ReportFormat.HTML: "text/html",
    }

    return PlainTextResponse(
        content=content,
        media_type=content_types.get(format, "text/plain"),
    )


# --- Helper Functions ---


def _build_oncall_stats(
    start_date: datetime,
    end_date: datetime,
    team_name: str | None = None,
) -> list[OnCallStats]:
    """Build OnCallStats for each responder."""
    # Extract unique responders
    responders: dict[str, dict] = {}

    for data in _oncall_store:
        responder_id = data.get("id") or data.get("user_id")
        if responder_id:
            responders[responder_id] = {
                "id": responder_id,
                "name": data.get("name", responder_id),
                "email": data.get("email"),
                "team": data.get("team_name") or data.get("team"),
                "oncall_hours": data.get("oncall_hours"),
            }

    # Also extract from incidents
    for inc in _incidents_store:
        for assigned in inc.get("assigned_to", []):
            if assigned and assigned not in responders:
                responders[assigned] = {
                    "id": assigned,
                    "name": assigned,
                    "email": None,
                    "team": inc.get("team_name"),
                    "oncall_hours": None,
                }

    # Filter by team
    if team_name:
        responders = {
            k: v for k, v in responders.items() if v.get("team") == team_name
        }

    # Build stats for each responder
    stats = []
    for responder_id, data in responders.items():
        stat = calculator.calculate_oncall_stats(
            incidents=_incidents_store,
            responder_id=responder_id,
            responder_name=data["name"],
            period_start=start_date,
            period_end=end_date,
            responder_email=data.get("email"),
            team_name=data.get("team"),
            oncall_hours=data.get("oncall_hours"),
        )
        if stat.total_pages > 0:
            stats.append(stat)

    return stats
