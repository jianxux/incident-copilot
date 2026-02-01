"""API routes for analytics and MTTR metrics."""

from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Query

from ..analytics import AnalyticsTracker, analytics_store
from ..analytics.models import IncidentMetrics, MTTRStats, PeriodComparison

logger = structlog.get_logger()

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

tracker = AnalyticsTracker()


@router.get("/mttr", response_model=MTTRStats)
async def get_mttr_stats(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
):
    """
    Get MTTR statistics for a time period.
    
    Returns mean, median, and p90 MTTR values along with incident counts.
    """
    logger.info("api_get_mttr_stats", days=days, service=service, severity=severity)
    
    stats = await tracker.get_stats_for_days(
        days=days,
        service_name=service,
        severity=severity,
    )
    return stats


@router.get("/incidents", response_model=list[IncidentMetrics])
async def get_incident_metrics(
    days: int = Query(7, ge=1, le=365, description="Number of days to fetch"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
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
    service: Optional[str] = Query(None, description="Filter by service name"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
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


@router.get("/summary")
async def get_analytics_summary(
    service: Optional[str] = Query(None, description="Filter by service name"),
):
    """
    Get a high-level analytics summary.
    
    Returns stats for 7d, 30d, and 90d periods with comparisons.
    """
    logger.info("api_get_analytics_summary", service=service)
    
    periods = [7, 30, 90]
    summary = {}
    
    for days in periods:
        stats = await tracker.get_stats_for_days(days=days, service_name=service)
        comparison = await tracker.compare_to_previous(days=days, service_name=service)
        
        summary[f"{days}d"] = {
            "stats": stats.model_dump(),
            "comparison": comparison.model_dump(),
        }
    
    return summary


@router.post("/record/triggered")
async def record_incident_triggered(
    incident_id: str,
    service_name: str,
    severity: str,
    triggered_at: Optional[datetime] = None,
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
    acknowledged_at: Optional[datetime] = None,
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
    resolved_at: Optional[datetime] = None,
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
    delivered_at: Optional[datetime] = None,
):
    """Record context card delivery event."""
    if delivered_at is None:
        delivered_at = datetime.utcnow()
        
    metrics = await tracker.record_context_card_delivered(
        incident_id=incident_id,
        delivered_at=delivered_at,
    )
    return {"status": "recorded", "metrics": metrics.model_dump()}
