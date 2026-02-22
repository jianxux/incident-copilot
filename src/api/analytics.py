"""API routes for analytics and MTTR metrics."""

from datetime import datetime, timedelta, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, Query

from ..analytics import AnalyticsTracker, analytics_store
from ..analytics.models import (
    AnalyticsIncidentSummary,
    AnalyticsSummaryResponse,
    HeatmapData,
    IncidentMetrics,
    MTTRStats,
    PeriodComparison,
    ServiceHealth,
    TeamPerformance,
    TrendData,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

tracker = AnalyticsTracker()


def _demo_team_performance() -> list[TeamPerformance]:
    return [
        TeamPerformance(
            team_id="team-platform",
            team_name="Platform",
            incidents_handled=42,
            avg_response_time_minutes=7.5,
            avg_resolution_time_hours=1.8,
            on_call_hours=216,
            escalation_rate=0.12,
        ),
        TeamPerformance(
            team_id="team-api",
            team_name="API",
            incidents_handled=31,
            avg_response_time_minutes=9.2,
            avg_resolution_time_hours=2.4,
            on_call_hours=192,
            escalation_rate=0.16,
        ),
        TeamPerformance(
            team_id="team-infra",
            team_name="Infrastructure",
            incidents_handled=18,
            avg_response_time_minutes=6.1,
            avg_resolution_time_hours=2.9,
            on_call_hours=168,
            escalation_rate=0.08,
        ),
    ]


def _demo_service_health() -> list[ServiceHealth]:
    return [
        ServiceHealth(
            service_id="svc-auth",
            service_name="Authentication",
            incident_count=9,
            critical_count=1,
            uptime_percentage=99.93,
            last_incident="2026-02-20T14:00:00Z",
            trend="stable",
        ),
        ServiceHealth(
            service_id="svc-payments",
            service_name="Payments",
            incident_count=6,
            critical_count=0,
            uptime_percentage=99.97,
            last_incident="2026-02-18T22:30:00Z",
            trend="improving",
        ),
        ServiceHealth(
            service_id="svc-search",
            service_name="Search",
            incident_count=12,
            critical_count=2,
            uptime_percentage=99.82,
            last_incident="2026-02-21T07:15:00Z",
            trend="degrading",
        ),
    ]


def _demo_trends(period: Literal["day", "week", "month", "quarter"]) -> list[TrendData]:
    if period == "day":
        points = 1
    elif period == "week":
        points = 7
    elif period == "month":
        points = 30
    else:
        points = 12

    end = datetime.now(timezone.utc).date()
    trends: list[TrendData] = []

    for idx in range(points):
        d = end - timedelta(days=points - idx - 1)
        incidents = 2 + (idx % 4)
        resolved = max(0, incidents - (idx % 2))
        trends.append(
            TrendData(
                date=d.isoformat(),
                incidents=incidents,
                resolved=resolved,
                mttr_hours=1.2 + (idx % 5) * 0.3,
                mtta_minutes=8 + (idx % 4) * 2,
            )
        )

    return trends


@router.get("/mttr", response_model=MTTRStats)
async def get_mttr_stats(
    period: Literal["day", "week", "month"] = Query(
        "week", description="Aggregation period: day, week, or month"
    ),
    service: str | None = Query(None, description="Filter by service name"),
    severity: str | None = Query(None, description="Filter by severity level"),
):
    """
    Get MTTR statistics for a period.

    Maps period to day-count windows: day->1, week->7, month->30.
    """
    period_to_days = {"day": 1, "week": 7, "month": 30}
    days = period_to_days[period]

    logger.info("api_get_mttr_stats", period=period, days=days, service=service, severity=severity)

    stats = await tracker.get_stats_for_days(
        days=days,
        service_name=service,
        severity=severity,
    )
    stats.period = period
    return stats


@router.get("/incidents", response_model=list[IncidentMetrics])
async def get_incident_metrics(
    days: int = Query(7, ge=1, le=365, description="Number of days to fetch"),
    service: str | None = Query(None, description="Filter by service name"),
    severity: str | None = Query(None, description="Filter by severity level"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum incidents to return"),
):
    """
    Get incident metrics for a time period.

    Returns detailed metrics for each incident including lifecycle timestamps.
    """
    logger.info(
        "api_get_incident_metrics",
        days=days,
        service=service,
        severity=severity,
        limit=limit,
    )

    end = datetime.utcnow()
    start = end - timedelta(days=days)

    metrics = await analytics_store.get_metrics_for_period(
        start=start,
        end=end,
        service_name=service,
        severity=severity,
    )

    return metrics[:limit]


@router.get("/comparison", response_model=PeriodComparison)
async def compare_periods(
    days: int = Query(7, ge=1, le=180, description="Period length in days"),
    service: str | None = Query(None, description="Filter by service name"),
    severity: str | None = Query(None, description="Filter by severity level"),
):
    """
    Compare current period to the previous equivalent period.

    For example, if days=7, compares this week to last week.
    Returns trend analysis and improvement percentage.
    """
    logger.info(
        "api_compare_periods",
        days=days,
        service=service,
        severity=severity,
    )

    comparison = await tracker.compare_to_previous(
        days=days,
        service_name=service,
        severity=severity,
    )
    return comparison


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    period: Literal["day", "week", "month", "quarter"] = Query(
        "week", description="Summary period: day, week, month, or quarter"
    ),
):
    """Get a high-level analytics summary as demo data for dashboard views."""
    logger.info("api_get_analytics_summary", period=period)

    incidents = AnalyticsIncidentSummary(
        total_incidents=97,
        resolved_incidents=84,
        open_incidents=13,
        mttr_hours=2.3,
        mtta_minutes=9.4,
        by_severity={
            "critical": 5,
            "high": 18,
            "medium": 33,
            "low": 28,
            "info": 13,
        },
        by_source={
            "pagerduty": 38,
            "datadog": 26,
            "sentry": 19,
            "manual": 14,
        },
        change_from_previous={
            "incidents": -7.1,
            "mttr": -11.3,
            "mtta": -5.6,
        },
    )

    return AnalyticsSummaryResponse(
        period=period,
        incidents=incidents,
        team_performance=_demo_team_performance(),
        service_health=_demo_service_health(),
        trends=_demo_trends(period),
    )


@router.get("/teams", response_model=list[TeamPerformance])
async def get_team_performance():
    """Get team-level performance metrics (demo data)."""
    return _demo_team_performance()


@router.get("/services", response_model=list[ServiceHealth])
async def get_service_health():
    """Get service health metrics (demo data)."""
    return _demo_service_health()


@router.get("/heatmap", response_model=list[HeatmapData])
async def get_heatmap_data():
    """Get weekly incident heatmap data (7 days x 24 hours = 168 entries)."""
    data: list[HeatmapData] = []
    for day in range(7):
        for hour in range(24):
            # Simple deterministic pattern for demo visualization.
            count = (day * 3 + hour) % 9
            data.append(
                HeatmapData(
                    day_of_week=day,
                    hour_of_day=hour,
                    incident_count=count,
                )
            )
    return data


@router.post("/record/triggered")
async def record_incident_triggered(
    incident_id: str,
    service_name: str,
    severity: str,
    triggered_at: datetime | None = None,
):
    """Record an incident trigger event (for testing/manual entry)."""
    if triggered_at is None:
        triggered_at = datetime.utcnow()

    metrics = await tracker.record_incident_triggered(
        incident_id=incident_id,
        triggered_at=triggered_at,
        service_name=service_name,
        severity=severity,
    )
    return {"status": "recorded", "metrics": metrics.model_dump()}


@router.post("/record/acknowledged")
async def record_incident_acknowledged(
    incident_id: str,
    acknowledged_at: datetime | None = None,
):
    """Record an incident acknowledgement event."""
    if acknowledged_at is None:
        acknowledged_at = datetime.utcnow()

    metrics = await tracker.record_incident_acknowledged(
        incident_id=incident_id,
        acknowledged_at=acknowledged_at,
    )
    return {"status": "recorded", "metrics": metrics.model_dump()}


@router.post("/record/resolved")
async def record_incident_resolved(
    incident_id: str,
    resolved_at: datetime | None = None,
):
    """Record an incident resolution event."""
    if resolved_at is None:
        resolved_at = datetime.utcnow()

    metrics = await tracker.record_incident_resolved(
        incident_id=incident_id,
        resolved_at=resolved_at,
    )
    return {"status": "recorded", "metrics": metrics.model_dump()}


@router.post("/record/context-card")
async def record_context_card_delivered(
    incident_id: str,
    delivered_at: datetime | None = None,
):
    """Record context card delivery event."""
    if delivered_at is None:
        delivered_at = datetime.utcnow()

    metrics = await tracker.record_context_card_delivered(
        incident_id=incident_id,
        delivered_at=delivered_at,
    )
    return {"status": "recorded", "metrics": metrics.model_dump()}
