"""FastAPI routes for predictive insights, deployment risk, and reliability feed."""

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..analytics.models import IncidentMetrics
from ..analytics.store import analytics_store
from .deployment_risk import DeploymentRiskScorer
from .models import (
    DeploymentInfo,
    DeploymentRiskScore,
    EarlyWarning,
    MetricDataPoint,
    MetricTrend,
    ReliabilityDigest,
    ServiceHealthScore,
    ShiftLeftReport,
)
from .predictive import PredictiveEngine
from .reliability_feed import ReliabilityFeedGenerator

logger = structlog.get_logger()
router = APIRouter(prefix="/api/insights", tags=["predictive-insights"])

# Singletons
_predictive_engine = PredictiveEngine()
_risk_scorer = DeploymentRiskScorer()
_reliability_feed = ReliabilityFeedGenerator()


# --- Request/Response Models ---


class MetricTrendRequest(BaseModel):
    """Request for metric trend analysis."""

    metrics: list[MetricDataPoint]
    window_hours: int = 24
    breach_threshold: float | None = None


class MetricTrendResponse(BaseModel):
    trends: list[MetricTrend]


class HealthScoreRequest(BaseModel):
    service_name: str
    lookback_days: int = 30


class EarlyWarningsResponse(BaseModel):
    warnings: list[EarlyWarning]
    services_assessed: int


class DeploymentRiskRequest(BaseModel):
    deployment: DeploymentInfo
    lookback_days: int = 30


class ShiftLeftRequest(BaseModel):
    service_name: str
    lookback_days: int = 30


class ReliabilityDigestRequest(BaseModel):
    service_name: str | None = None
    lookback_days: int = 7


# --- Predictive Routes ---


@router.post("/predict/metric-trends", response_model=MetricTrendResponse)
async def analyze_metric_trends(request: MetricTrendRequest):
    """Analyze metric time series for trends and predict threshold breaches."""
    trends = await _predictive_engine.analyze_metric_trends(
        metrics=request.metrics,
        window_hours=request.window_hours,
        breach_threshold=request.breach_threshold,
    )
    return MetricTrendResponse(trends=trends)


@router.post("/predict/health-score", response_model=ServiceHealthScore)
async def get_service_health_score(request: HealthScoreRequest):
    """Calculate composite health score for a service."""
    incidents = await _get_recent_incidents(request.lookback_days)
    score = await _predictive_engine.calculate_service_health_score(
        service_name=request.service_name,
        incidents=incidents,
        lookback_days=request.lookback_days,
    )
    return score


@router.get("/predict/health-scores", response_model=dict[str, ServiceHealthScore])
async def get_all_health_scores(
    lookback_days: int = Query(default=30, ge=1, le=365),
):
    """Calculate health scores for all known services."""
    incidents = await _get_recent_incidents(lookback_days)
    services = {i.service_name for i in incidents}

    scores = {}
    for svc in services:
        scores[svc] = await _predictive_engine.calculate_service_health_score(
            service_name=svc,
            incidents=incidents,
            lookback_days=lookback_days,
        )
    return scores


@router.get("/predict/early-warnings", response_model=EarlyWarningsResponse)
async def get_early_warnings(
    lookback_days: int = Query(default=30, ge=1, le=365),
):
    """Generate early warnings based on current service health."""
    incidents = await _get_recent_incidents(lookback_days)
    services = {i.service_name for i in incidents}

    scores = {}
    for svc in services:
        scores[svc] = await _predictive_engine.calculate_service_health_score(
            service_name=svc,
            incidents=incidents,
            lookback_days=lookback_days,
        )

    warnings = await _predictive_engine.generate_early_warnings(incidents, scores)
    return EarlyWarningsResponse(warnings=warnings, services_assessed=len(scores))


# --- Deployment Risk Routes ---


@router.post("/deployments/risk", response_model=DeploymentRiskScore)
async def score_deployment_risk(request: DeploymentRiskRequest):
    """Score the risk of a planned deployment."""
    incidents = await _get_recent_incidents(request.lookback_days)
    score = await _risk_scorer.score_deployment(
        deployment=request.deployment,
        incidents=incidents,
        lookback_days=request.lookback_days,
    )
    return score


# --- Reliability Feed Routes ---


@router.post("/reliability/shift-left", response_model=ShiftLeftReport)
async def get_shift_left_report(request: ShiftLeftRequest):
    """Generate a shift-left report for a service."""
    incidents = await _get_recent_incidents(request.lookback_days)
    report = await _reliability_feed.generate_shift_left_report(
        service_name=request.service_name,
        incidents=incidents,
        lookback_days=request.lookback_days,
    )
    return report


@router.post("/reliability/digest", response_model=ReliabilityDigest)
async def get_reliability_digest(request: ReliabilityDigestRequest):
    """Generate an exportable reliability digest."""
    incidents = await _get_recent_incidents(request.lookback_days)

    health_score = None
    if request.service_name:
        health_score = await _predictive_engine.calculate_service_health_score(
            service_name=request.service_name,
            incidents=incidents,
            lookback_days=request.lookback_days,
        )

    digest = await _reliability_feed.generate_reliability_digest(
        service_name=request.service_name,
        incidents=incidents,
        health_score=health_score,
        lookback_days=request.lookback_days,
    )
    return digest


# --- Helpers ---


async def _get_recent_incidents(lookback_days: int) -> list[IncidentMetrics]:
    """Fetch recent incidents from the analytics store."""
    try:
        return await analytics_store.get_all_metrics()
    except Exception:
        logger.warning("failed_to_fetch_incidents_from_store")
        return []
