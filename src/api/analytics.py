"""API routes for analytics and MTTR metrics."""

import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, Query

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
from ..auth.middleware import AuthContext, get_auth_context
from ..db.supabase_db import get_db
from ..supabase_client import is_supabase_db_enabled

logger = structlog.get_logger()

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

tracker = AnalyticsTracker()

_RESOLVED_STATUSES = {"resolved", "completed"}
_ACKNOWLEDGED_STATUS_VALUES = {"acknowledged"}
_SEVERITY_KEYS = ("critical", "high", "medium", "low", "info")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_utc(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except ValueError:
            return None
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _period_to_days(period: Literal["day", "week", "month", "quarter"]) -> int:
    return {"day": 1, "week": 7, "month": 30, "quarter": 90}[period]


def _is_resolved_status(status: str | None) -> bool:
    return str(status or "").lower() in _RESOLVED_STATUSES


def _is_acknowledged_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type") or "").lower()
    if event_type == "acknowledged":
        return True
    if event_type != "status_change":
        return False

    metadata = _as_dict(event.get("metadata"))
    data = _as_dict(event.get("data"))
    status_values = [
        metadata.get("status"),
        metadata.get("to_status"),
        metadata.get("new_status"),
        data.get("status"),
        data.get("to_status"),
        data.get("new_status"),
    ]
    return any(
        str(v or "").lower() in _ACKNOWLEDGED_STATUS_VALUES for v in status_values
    )


def _row_to_metric(
    row: dict[str, Any],
    ack_by_incident: dict[str, datetime],
) -> IncidentMetrics:
    metadata = _as_dict(row.get("metadata"))
    incident_id = str(row.get("id", ""))

    triggered_at = (
        _parse_dt(row.get("triggered_at"))
        or _parse_dt(row.get("created_at"))
        or _utc_now()
    )
    acknowledged_at = (
        _parse_dt(row.get("acknowledged_at"))
        or _parse_dt(metadata.get("acknowledged_at"))
        or ack_by_incident.get(incident_id)
    )
    resolved_at = (
        _parse_dt(row.get("resolved_at"))
        or _parse_dt(row.get("processed_at"))
        or _parse_dt(metadata.get("resolved_at"))
    )
    if resolved_at is None and _is_resolved_status(str(row.get("status") or "")):
        resolved_at = _parse_dt(row.get("updated_at"))

    return IncidentMetrics(
        incident_id=incident_id,
        triggered_at=triggered_at,
        acknowledged_at=acknowledged_at,
        resolved_at=resolved_at,
        service_name=(row.get("service") or "unknown"),
        severity=str(row.get("severity") or "medium").lower(),
    )


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (percentile / 100)
    floor = int(k)
    ceil = floor + 1
    if ceil >= len(sorted_values):
        return sorted_values[floor]
    return sorted_values[floor] * (ceil - k) + sorted_values[ceil] * (k - floor)


def _stats_from_metrics(
    metrics: list[IncidentMetrics],
    *,
    period_label: str,
    start: datetime,
    end: datetime,
) -> MTTRStats:
    mttr_values = [
        m.time_to_resolve_seconds
        for m in metrics
        if m.time_to_resolve_seconds is not None
    ]
    mtta_values = [
        m.time_to_acknowledge_seconds
        for m in metrics
        if m.time_to_acknowledge_seconds is not None
    ]

    return MTTRStats(
        period=period_label,
        period_start=start,
        period_end=end,
        mean_mttr_seconds=statistics.mean(mttr_values) if mttr_values else None,
        median_mttr_seconds=statistics.median(mttr_values) if mttr_values else None,
        p90_mttr_seconds=_percentile(mttr_values, 90) if mttr_values else None,
        incidents_count=len(metrics),
        resolved_count=len(mttr_values),
        mean_time_to_acknowledge_seconds=(
            statistics.mean(mtta_values) if mtta_values else None
        ),
        mean_time_to_context_card_seconds=None,
    )


async def _query_incidents(
    *,
    start: datetime,
    end: datetime,
    tenant_id: str | None,
    service: str | None = None,
    severity: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    db = get_db(use_admin=True)

    def _query():
        query = (
            db.client.table("incidents")
            .select("*")
            .gte("created_at", start.isoformat())
            .lte("created_at", end.isoformat())
            .order("created_at", desc=True)
        )
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        if service:
            query = query.eq("service", service)
        if severity:
            query = query.eq("severity", severity)
        if limit:
            query = query.limit(limit)
        return query.execute()

    result = await db._to_thread(_query)
    return result.data or []


async def _query_ack_map(
    *,
    incident_ids: list[str],
    tenant_id: str | None,
) -> dict[str, datetime]:
    if not incident_ids:
        return {}

    db = get_db(use_admin=True)

    def _query():
        query = (
            db.client.table("incident_events")
            .select("incident_id,event_type,occurred_at,created_at,metadata,data")
            .in_("incident_id", incident_ids)
            .in_("event_type", ["acknowledged", "status_change"])
            .order("created_at", desc=False)
        )
        if tenant_id:
            query = query.eq("tenant_id", tenant_id)
        return query.execute()

    try:
        result = await db._to_thread(_query)
    except Exception:
        return {}

    ack_by_incident: dict[str, datetime] = {}
    for event in result.data or []:
        incident_id = str(event.get("incident_id", ""))
        if not incident_id or incident_id in ack_by_incident:
            continue
        if not _is_acknowledged_event(event):
            continue
        ack_at = _parse_dt(event.get("occurred_at")) or _parse_dt(
            event.get("created_at")
        )
        if ack_at:
            ack_by_incident[incident_id] = ack_at

    return ack_by_incident


async def _load_supabase_metrics(
    *,
    start: datetime,
    end: datetime,
    tenant_id: str | None,
    service: str | None = None,
    severity: str | None = None,
    limit: int | None = None,
) -> list[IncidentMetrics]:
    rows = await _query_incidents(
        start=start,
        end=end,
        tenant_id=tenant_id,
        service=service,
        severity=severity,
        limit=limit,
    )
    incident_ids = [str(row.get("id", "")) for row in rows if row.get("id")]
    ack_by_incident = await _query_ack_map(
        incident_ids=incident_ids, tenant_id=tenant_id
    )
    return [_row_to_metric(row, ack_by_incident) for row in rows]


def _change_percent(current: float | None, previous: float | None) -> float:
    if previous is None or previous == 0:
        return 0.0
    if current is None:
        return 0.0
    return ((current - previous) / previous) * 100


def _build_service_health(metrics: list[IncidentMetrics]) -> list[ServiceHealth]:
    grouped: dict[str, list[IncidentMetrics]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.service_name].append(metric)

    rows: list[ServiceHealth] = []
    for service_name, service_metrics in grouped.items():
        critical_count = sum(1 for m in service_metrics if m.severity == "critical")
        last_incident = max(
            service_metrics, key=lambda m: m.triggered_at
        ).triggered_at.isoformat()
        rows.append(
            ServiceHealth(
                service_id=service_name,
                service_name=service_name,
                incident_count=len(service_metrics),
                critical_count=critical_count,
                uptime_percentage=max(95.0, 100.0 - (len(service_metrics) * 0.05)),
                last_incident=last_incident,
                trend="stable",
            )
        )
    rows.sort(key=lambda x: x.incident_count, reverse=True)
    return rows[:10]


def _build_team_performance(metrics: list[IncidentMetrics]) -> list[TeamPerformance]:
    groups: dict[str, list[IncidentMetrics]] = defaultdict(list)
    for metric in metrics:
        team_name = (metric.service_name or "unknown").split("-")[0] or "unknown"
        groups[team_name].append(metric)

    teams: list[TeamPerformance] = []
    for team_name, team_metrics in groups.items():
        response_values = [
            m.time_to_acknowledge_seconds
            for m in team_metrics
            if m.time_to_acknowledge_seconds is not None
        ]
        resolve_values = [
            m.time_to_resolve_seconds
            for m in team_metrics
            if m.time_to_resolve_seconds is not None
        ]
        teams.append(
            TeamPerformance(
                team_id=f"team-{team_name}",
                team_name=team_name.capitalize(),
                incidents_handled=len(team_metrics),
                avg_response_time_minutes=(
                    (statistics.mean(response_values) / 60) if response_values else 0.0
                ),
                avg_resolution_time_hours=(
                    (statistics.mean(resolve_values) / 3600) if resolve_values else 0.0
                ),
                on_call_hours=float(len(team_metrics) * 8),
                escalation_rate=0.0,
            )
        )

    teams.sort(key=lambda x: x.incidents_handled, reverse=True)
    return teams[:10]


def _build_trends(
    *,
    period: Literal["day", "week", "month", "quarter"],
    start: datetime,
    metrics: list[IncidentMetrics],
) -> list[TrendData]:
    if period == "quarter":
        points = 12
        step_days = 7
    else:
        points = _period_to_days(period)
        step_days = 1

    grouped: dict[str, list[IncidentMetrics]] = defaultdict(list)
    for metric in metrics:
        date_key = metric.triggered_at.date().isoformat()
        grouped[date_key].append(metric)

    trends: list[TrendData] = []
    for idx in range(points):
        d = (start + timedelta(days=idx * step_days)).date()
        if d > _utc_now().date():
            break
        day_metrics = grouped.get(d.isoformat(), [])
        mttr_values = [
            m.time_to_resolve_seconds
            for m in day_metrics
            if m.time_to_resolve_seconds is not None
        ]
        mtta_values = [
            m.time_to_acknowledge_seconds
            for m in day_metrics
            if m.time_to_acknowledge_seconds is not None
        ]
        trends.append(
            TrendData(
                date=d.isoformat(),
                incidents=len(day_metrics),
                resolved=len(mttr_values),
                mttr_hours=(
                    (statistics.mean(mttr_values) / 3600) if mttr_values else 0.0
                ),
                mtta_minutes=(
                    (statistics.mean(mtta_values) / 60) if mtta_values else 0.0
                ),
            )
        )

    return trends


def _build_heatmap(metrics: list[IncidentMetrics]) -> list[HeatmapData]:
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for metric in metrics:
        key = (metric.triggered_at.weekday(), metric.triggered_at.hour)
        counts[key] += 1

    data: list[HeatmapData] = []
    for day in range(7):
        for hour in range(24):
            data.append(
                HeatmapData(
                    day_of_week=day,
                    hour_of_day=hour,
                    incident_count=counts[(day, hour)],
                )
            )
    return data


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
    days: int | None = Query(
        None,
        ge=1,
        le=365,
        description="Alternative to period: explicit day window",
    ),
    service: str | None = Query(None, description="Filter by service name"),
    severity: str | None = Query(None, description="Filter by severity level"),
    auth: AuthContext = Depends(get_auth_context),
):
    """
    Get MTTR statistics for a period.

    Maps period to day-count windows: day->1, week->7, month->30.
    """
    period_to_days = {"day": 1, "week": 7, "month": 30}
    day_window = days if days is not None else period_to_days[period]

    logger.info(
        "api_get_mttr_stats",
        period=period,
        days=day_window,
        service=service,
        severity=severity,
        tenant_id=auth.tenant_id if auth else None,
    )

    if is_supabase_db_enabled():
        try:
            end = _utc_now()
            start = end - timedelta(days=day_window)
            metrics = await _load_supabase_metrics(
                start=start,
                end=end,
                tenant_id=auth.tenant_id if auth else None,
                service=service,
                severity=severity,
            )
            stats = _stats_from_metrics(
                metrics,
                period_label=period,
                start=start,
                end=end,
            )
            stats.period = period
            return stats
        except Exception as exc:
            logger.warning("analytics_mttr_supabase_failed_fallback", error=str(exc))

    stats = await tracker.get_stats_for_days(
        days=day_window,
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
    auth: AuthContext = Depends(get_auth_context),
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

    end = _utc_now()
    start = end - timedelta(days=days)

    if is_supabase_db_enabled():
        try:
            return await _load_supabase_metrics(
                start=start,
                end=end,
                tenant_id=auth.tenant_id if auth else None,
                service=service,
                severity=severity,
                limit=limit,
            )
        except Exception as exc:
            logger.warning(
                "analytics_incidents_supabase_failed_fallback", error=str(exc)
            )

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
    auth: AuthContext = Depends(get_auth_context),
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

    if is_supabase_db_enabled():
        try:
            current_end = _utc_now()
            current_start = current_end - timedelta(days=days)
            previous_end = current_start
            previous_start = previous_end - timedelta(days=days)

            current_metrics = await _load_supabase_metrics(
                start=current_start,
                end=current_end,
                tenant_id=auth.tenant_id if auth else None,
                service=service,
                severity=severity,
            )
            previous_metrics = await _load_supabase_metrics(
                start=previous_start,
                end=previous_end,
                tenant_id=auth.tenant_id if auth else None,
                service=service,
                severity=severity,
            )
            current_stats = _stats_from_metrics(
                current_metrics,
                period_label="Current Period",
                start=current_start,
                end=current_end,
            )
            previous_stats = _stats_from_metrics(
                previous_metrics,
                period_label="Previous Period",
                start=previous_start,
                end=previous_end,
            )
            return PeriodComparison.from_stats(current_stats, previous_stats)
        except Exception as exc:
            logger.warning(
                "analytics_comparison_supabase_failed_fallback", error=str(exc)
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
    auth: AuthContext = Depends(get_auth_context),
):
    """Get a high-level analytics summary for dashboard views."""
    logger.info("api_get_analytics_summary", period=period)

    if is_supabase_db_enabled():
        try:
            days = _period_to_days(period)
            current_end = _utc_now()
            current_start = current_end - timedelta(days=days)
            previous_end = current_start
            previous_start = previous_end - timedelta(days=days)

            current_rows = await _query_incidents(
                start=current_start,
                end=current_end,
                tenant_id=auth.tenant_id if auth else None,
                limit=5000,
            )
            previous_rows = await _query_incidents(
                start=previous_start,
                end=previous_end,
                tenant_id=auth.tenant_id if auth else None,
                limit=5000,
            )

            current_incident_ids = [
                str(row.get("id", "")) for row in current_rows if row.get("id")
            ]
            previous_incident_ids = [
                str(row.get("id", "")) for row in previous_rows if row.get("id")
            ]
            ack_current = await _query_ack_map(
                incident_ids=current_incident_ids,
                tenant_id=auth.tenant_id if auth else None,
            )
            ack_previous = await _query_ack_map(
                incident_ids=previous_incident_ids,
                tenant_id=auth.tenant_id if auth else None,
            )
            current_metrics = [_row_to_metric(row, ack_current) for row in current_rows]
            previous_metrics = [
                _row_to_metric(row, ack_previous) for row in previous_rows
            ]

            current_stats = _stats_from_metrics(
                current_metrics,
                period_label=period,
                start=current_start,
                end=current_end,
            )
            previous_stats = _stats_from_metrics(
                previous_metrics,
                period_label="previous",
                start=previous_start,
                end=previous_end,
            )

            by_severity = {key: 0 for key in _SEVERITY_KEYS}
            by_source: dict[str, int] = defaultdict(int)
            resolved_incidents = 0
            for row in current_rows:
                severity = str(row.get("severity") or "").lower()
                if severity in by_severity:
                    by_severity[severity] += 1
                source = str(row.get("source") or "unknown")
                by_source[source] += 1
                if _is_resolved_status(str(row.get("status") or "")):
                    resolved_incidents += 1

            incidents = AnalyticsIncidentSummary(
                total_incidents=len(current_rows),
                resolved_incidents=resolved_incidents,
                open_incidents=max(0, len(current_rows) - resolved_incidents),
                mttr_hours=(current_stats.mean_mttr_seconds or 0) / 3600,
                mtta_minutes=(current_stats.mean_time_to_acknowledge_seconds or 0) / 60,
                by_severity=by_severity,
                by_source=dict(by_source),
                change_from_previous={
                    "incidents": _change_percent(
                        float(len(current_rows)),
                        float(len(previous_rows)),
                    ),
                    "mttr": _change_percent(
                        current_stats.mean_mttr_seconds,
                        previous_stats.mean_mttr_seconds,
                    ),
                    "mtta": _change_percent(
                        current_stats.mean_time_to_acknowledge_seconds,
                        previous_stats.mean_time_to_acknowledge_seconds,
                    ),
                },
            )

            team_performance = _build_team_performance(current_metrics)
            service_health = _build_service_health(current_metrics)

            return AnalyticsSummaryResponse(
                period=period,
                incidents=incidents,
                team_performance=team_performance,
                service_health=service_health,
                trends=_build_trends(
                    period=period,
                    start=current_start,
                    metrics=current_metrics,
                ),
            )
        except Exception as exc:
            logger.warning("analytics_summary_supabase_failed_fallback", error=str(exc))

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
async def get_heatmap_data(auth: AuthContext = Depends(get_auth_context)):
    """Get weekly incident heatmap data (7 days x 24 hours = 168 entries)."""
    if is_supabase_db_enabled():
        try:
            end = _utc_now()
            start = end - timedelta(days=30)
            metrics = await _load_supabase_metrics(
                start=start,
                end=end,
                tenant_id=auth.tenant_id if auth else None,
                limit=5000,
            )
            return _build_heatmap(metrics)
        except Exception as exc:
            logger.warning("analytics_heatmap_supabase_failed_fallback", error=str(exc))

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
        triggered_at = datetime.now(UTC)

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
        acknowledged_at = datetime.now(UTC)

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
        resolved_at = datetime.now(UTC)

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
        delivered_at = datetime.now(UTC)

    metrics = await tracker.record_context_card_delivered(
        incident_id=incident_id,
        delivered_at=delivered_at,
    )
    return {"status": "recorded", "metrics": metrics.model_dump()}
