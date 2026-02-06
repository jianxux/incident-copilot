"""API routes for AI Insights and Pattern Detection."""

import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..insights import (
    AnalysisRequest,
    AnalysisResult,
    AnomalyDetection,
    DigestPeriod,
    IncidentDigest,
    Insight,
    InsightSummary,
    InsightType,
    RecurringPattern,
    ServiceDependency,
    Severity,
    insights_service,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/insights", tags=["insights"])


# --- Response Models ---


class InsightsListResponse(BaseModel):
    """Response for listing insights."""

    total: int
    insights: list[Insight]


class PatternsListResponse(BaseModel):
    """Response for listing patterns."""

    total: int
    patterns: list[RecurringPattern]


class AnomaliesListResponse(BaseModel):
    """Response for listing anomalies."""

    total: int
    anomalies: list[AnomalyDetection]


class DependenciesListResponse(BaseModel):
    """Response for listing dependencies."""

    total: int
    dependencies: list[ServiceDependency]


class AcknowledgeRequest(BaseModel):
    """Request to acknowledge an insight."""

    acknowledged_by: str


# --- Endpoints ---


@router.get("", response_model=InsightsListResponse)
async def list_insights(
    insight_type: InsightType | None = Query(
        None, description="Filter by insight type"
    ),
    severity: Severity | None = Query(None, description="Filter by severity"),
    service: str | None = Query(None, description="Filter by service name"),
    limit: int = Query(50, ge=1, le=200, description="Maximum insights to return"),
):
    """
    List all insights with optional filtering.

    Returns AI-generated insights about incident patterns, anomalies,
    and trends detected in your incident data.
    """
    logger.info(
        "api_list_insights",
        insight_type=insight_type,
        severity=severity,
        service=service,
        limit=limit,
    )

    insights = await insights_service.get_insights(
        insight_type=insight_type,
        severity=severity,
        service_name=service,
        limit=limit,
    )

    return InsightsListResponse(total=len(insights), insights=insights)


@router.get("/summary", response_model=InsightSummary)
async def get_insights_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
):
    """
    Get a summary of insights for a time period.

    Returns aggregated statistics about insights including counts by severity
    and the top affected services.
    """
    logger.info("api_get_insights_summary", days=days)

    summary = await insights_service.get_insight_summary(days=days)
    return summary


@router.get("/patterns", response_model=PatternsListResponse)
async def list_patterns(
    service: str | None = Query(None, description="Filter by service name"),
    limit: int = Query(50, ge=1, le=200, description="Maximum patterns to return"),
):
    """
    List detected incident patterns.

    Returns recurring incident patterns including frequency,
    time between occurrences, and suggested actions.
    """
    logger.info("api_list_patterns", service=service, limit=limit)

    patterns = await insights_service.get_patterns(service_name=service, limit=limit)

    return PatternsListResponse(total=len(patterns), patterns=patterns)


@router.get("/anomalies", response_model=AnomaliesListResponse)
async def list_anomalies(
    service: str | None = Query(None, description="Filter by service name"),
    severity: Severity | None = Query(None, description="Filter by severity"),
    limit: int = Query(50, ge=1, le=200, description="Maximum anomalies to return"),
):
    """
    List detected anomalies.

    Returns detected anomalies including incident spikes,
    cascading failures, and unusual time patterns.
    """
    logger.info("api_list_anomalies", service=service, severity=severity, limit=limit)

    anomalies = await insights_service.get_anomalies(
        service_name=service, severity=severity, limit=limit
    )

    return AnomaliesListResponse(total=len(anomalies), anomalies=anomalies)


@router.get("/dependencies", response_model=DependenciesListResponse)
async def list_dependencies(
    service: str | None = Query(None, description="Filter by service name"),
):
    """
    List detected service dependencies.

    Returns inferred service dependencies based on incident correlation analysis.
    """
    logger.info("api_list_dependencies", service=service)

    dependencies = await insights_service.get_service_dependencies(service_name=service)

    return DependenciesListResponse(total=len(dependencies), dependencies=dependencies)


@router.get("/digest", response_model=IncidentDigest | None)
async def get_digest(
    period: DigestPeriod = Query(
        DigestPeriod.WEEKLY, description="Digest period (daily, weekly, monthly)"
    ),
    generate: bool = Query(False, description="Generate new digest if none exists"),
    include_ai: bool = Query(True, description="Include AI-generated summary"),
):
    """
    Get the latest incident digest.

    Returns a comprehensive digest including statistics, patterns,
    anomalies, and AI-generated insights.
    """
    logger.info(
        "api_get_digest", period=period, generate=generate, include_ai=include_ai
    )

    # Try to get existing digest
    digest = await insights_service.get_latest_digest(period=period.value)

    # Generate if requested and none exists
    if not digest and generate:
        digest = await insights_service.generate_digest(
            period=period, generate_ai=include_ai
        )

    return digest


@router.post("/digest/generate", response_model=IncidentDigest)
async def generate_digest(
    period: DigestPeriod = Query(
        DigestPeriod.WEEKLY, description="Digest period (daily, weekly, monthly)"
    ),
    include_ai: bool = Query(True, description="Include AI-generated summary"),
):
    """
    Generate a new incident digest.

    Creates a fresh digest with current data including AI-generated insights.
    """
    logger.info("api_generate_digest", period=period, include_ai=include_ai)

    digest = await insights_service.generate_digest(
        period=period, generate_ai=include_ai
    )

    return digest


@router.post("/analyze", response_model=AnalysisResult)
async def trigger_analysis(
    service: str | None = Query(
        None, description="Service to analyze (all if not specified)"
    ),
    days: int = Query(30, ge=1, le=365, description="Days of data to analyze"),
    include_patterns: bool = Query(True, description="Detect patterns"),
    include_anomalies: bool = Query(True, description="Detect anomalies"),
    include_dependencies: bool = Query(True, description="Analyze dependencies"),
    generate_ai: bool = Query(True, description="Generate AI summaries"),
):
    """
    Trigger a comprehensive analysis of incident data.

    Runs pattern detection, anomaly detection, and dependency analysis.
    Returns detailed results including all detected insights.
    """
    logger.info(
        "api_trigger_analysis",
        service=service,
        days=days,
        include_patterns=include_patterns,
        include_anomalies=include_anomalies,
        include_dependencies=include_dependencies,
    )

    request = AnalysisRequest(
        service_name=service,
        lookback_days=days,
        include_patterns=include_patterns,
        include_anomalies=include_anomalies,
        include_dependencies=include_dependencies,
        generate_ai_summary=generate_ai,
    )

    result = await insights_service.run_analysis(request)
    return result


@router.post("/{insight_id}/acknowledge", response_model=Insight | None)
async def acknowledge_insight(
    insight_id: str,
    request: AcknowledgeRequest,
):
    """
    Acknowledge an insight.

    Marks the insight as acknowledged by the specified user.
    """
    logger.info(
        "api_acknowledge_insight",
        insight_id=insight_id,
        acknowledged_by=request.acknowledged_by,
    )

    insight = await insights_service.acknowledge_insight(
        insight_id=insight_id,
        acknowledged_by=request.acknowledged_by,
    )

    return insight


@router.get("/{insight_id}", response_model=Insight | None)
async def get_insight(insight_id: str):
    """Get a specific insight by ID."""
    logger.info("api_get_insight", insight_id=insight_id)

    insights = await insights_service.get_insights(limit=1000)
    for insight in insights:
        if insight.insight_id == insight_id:
            return insight

    return None
