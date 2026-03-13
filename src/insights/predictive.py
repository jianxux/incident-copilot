"""Predictive alerting engine for proactive incident prevention."""

import hashlib
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import structlog

from ..analytics.models import IncidentMetrics
from .models import (
    EarlyWarning,
    MetricDataPoint,
    MetricTrend,
    Severity,
    ServiceHealthScore,
)

logger = structlog.get_logger()


class PredictiveEngine:
    """
    Predictive alerting engine that analyzes metric trends,
    calculates service health scores, and generates early warnings.
    """

    def __init__(
        self,
        trend_threshold: float = 0.3,
        health_weights: dict[str, float] | None = None,
    ):
        self.trend_threshold = trend_threshold
        self.health_weights = health_weights or {
            "frequency": 0.30,
            "severity": 0.25,
            "mttr": 0.25,
            "trend": 0.20,
        }

    # --- Linear Regression Helpers ---

    @staticmethod
    def _linear_regression(
        xs: list[float], ys: list[float]
    ) -> tuple[float, float, float]:
        """Return (slope, intercept, r_squared) using ordinary least squares."""
        n = len(xs)
        if n < 2:
            return 0.0, (ys[0] if ys else 0.0), 0.0

        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_x2 = sum(x * x for x in xs)
        sum_y2 = sum(y * y for y in ys)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return 0.0, sum_y / n, 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

        # R-squared
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        mean_y = sum_y / n
        ss_tot = sum((y - mean_y) ** 2 for y in ys)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return slope, intercept, max(0.0, min(1.0, r_squared))

    # --- Metric Trend Analysis ---

    async def analyze_metric_trends(
        self,
        metrics: list[MetricDataPoint],
        window_hours: int = 24,
        breach_threshold: float | None = None,
    ) -> list[MetricTrend]:
        """
        Analyze metric time series data for trends using linear regression.

        Groups metrics by (metric_name, service_name), fits a line,
        and extrapolates to predict future values and threshold breaches.
        """
        if not metrics:
            return []

        # Group by (metric_name, service_name)
        groups: dict[tuple[str, str], list[MetricDataPoint]] = defaultdict(list)
        for dp in metrics:
            groups[(dp.metric_name, dp.service_name)].append(dp)

        trends: list[MetricTrend] = []
        for (metric_name, service_name), points in groups.items():
            if len(points) < 2:
                continue

            points.sort(key=lambda p: p.timestamp)
            t0 = points[0].timestamp.timestamp()

            xs = [(p.timestamp.timestamp() - t0) / 3600.0 for p in points]  # hours
            ys = [p.value for p in points]

            slope, intercept, r_squared = self._linear_regression(xs, ys)

            current_x = xs[-1]
            current_value = ys[-1]
            predicted_1h = slope * (current_x + 1) + intercept
            predicted_24h = slope * (current_x + 24) + intercept

            # Determine direction
            if abs(slope) < self.trend_threshold:
                direction = "stable"
            elif slope > 0:
                direction = "increasing"
            else:
                direction = "decreasing"

            # Estimate breach time
            estimated_breach: datetime | None = None
            if breach_threshold is not None and slope != 0:
                hours_to_breach = (breach_threshold - current_value) / slope
                if hours_to_breach > 0:
                    estimated_breach = points[-1].timestamp + timedelta(
                        hours=hours_to_breach
                    )

            confidence = r_squared * min(1.0, len(points) / 10.0)

            trends.append(
                MetricTrend(
                    metric_name=metric_name,
                    service_name=service_name,
                    direction=direction,
                    slope=round(slope, 6),
                    r_squared=round(r_squared, 4),
                    current_value=round(current_value, 4),
                    predicted_value_1h=round(predicted_1h, 4),
                    predicted_value_24h=round(predicted_24h, 4),
                    breach_threshold=breach_threshold,
                    estimated_breach_time=estimated_breach,
                    confidence=round(confidence, 4),
                )
            )

        logger.info("metric_trends_analyzed", count=len(trends))
        return trends

    # --- Service Health Scoring ---

    async def calculate_service_health_score(
        self,
        service_name: str,
        incidents: list[IncidentMetrics],
        lookback_days: int = 30,
    ) -> ServiceHealthScore:
        """
        Calculate a composite health score (0-100, higher is healthier).

        Components:
        - Incident frequency score: fewer incidents = higher score
        - Severity score: lower average severity = higher score
        - MTTR score: faster resolution = higher score
        - Trend score: improving trend = higher score
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=lookback_days)

        service_incidents = [
            i
            for i in incidents
            if i.service_name == service_name and i.triggered_at >= cutoff
        ]

        # Frequency score: 100 if 0 incidents, drops by 10 per incident, min 0
        freq_score = max(0.0, 100.0 - len(service_incidents) * 10.0)

        # Severity score
        severity_map = {"critical": 0, "high": 25, "medium": 50, "low": 75, "info": 100}
        if service_incidents:
            sev_scores = [severity_map.get(i.severity, 50) for i in service_incidents]
            sev_score = sum(sev_scores) / len(sev_scores)
        else:
            sev_score = 100.0

        # MTTR score: 100 if avg MTTR < 5min, 0 if > 4 hours
        if service_incidents:
            mttrs = []
            for inc in service_incidents:
                if inc.resolved_at:
                    mttr = (inc.resolved_at - inc.triggered_at).total_seconds() / 60.0
                    mttrs.append(mttr)
            if mttrs:
                avg_mttr = sum(mttrs) / len(mttrs)
                mttr_score = max(0.0, min(100.0, 100.0 - (avg_mttr / 240.0) * 100.0))
            else:
                mttr_score = 50.0  # Unknown
        else:
            mttr_score = 100.0

        # Trend score: compare first half vs second half incident count
        if len(service_incidents) >= 4:
            sorted_incs = sorted(service_incidents, key=lambda x: x.triggered_at)
            mid = len(sorted_incs) // 2
            first_count = mid
            second_count = len(sorted_incs) - mid
            if first_count > 0:
                ratio = second_count / first_count
                # ratio < 1 means improving, ratio > 1 means worsening
                trend_score = max(0.0, min(100.0, 100.0 - (ratio - 1.0) * 50.0))
            else:
                trend_score = 50.0
        else:
            trend_score = 75.0  # Neutral-ish with limited data

        w = self.health_weights
        overall = (
            freq_score * w["frequency"]
            + sev_score * w["severity"]
            + mttr_score * w["mttr"]
            + trend_score * w["trend"]
        )

        return ServiceHealthScore(
            service_name=service_name,
            overall_score=round(overall, 2),
            incident_frequency_score=round(freq_score, 2),
            severity_score=round(sev_score, 2),
            mttr_score=round(mttr_score, 2),
            trend_score=round(trend_score, 2),
            recent_incidents=len(service_incidents),
            assessed_at=now,
        )

    # --- Early Warnings ---

    async def generate_early_warnings(
        self,
        incidents: list[IncidentMetrics],
        service_health_scores: dict[str, ServiceHealthScore],
    ) -> list[EarlyWarning]:
        """
        Generate early warnings based on health scores and incident patterns.
        """
        warnings: list[EarlyWarning] = []
        now = datetime.now(UTC)

        for service_name, score in service_health_scores.items():
            # Warn on low health scores
            if score.overall_score < 30:
                warnings.append(
                    EarlyWarning(
                        warning_id=self._gen_id(
                            f"health_{service_name}_{now.isoformat()}"
                        ),
                        warning_type="health_degradation",
                        severity=(
                            Severity.HIGH
                            if score.overall_score < 15
                            else Severity.MEDIUM
                        ),
                        title=f"Service health critical: {service_name}",
                        description=(
                            f"{service_name} health score is {score.overall_score}/100. "
                            f"Frequency={score.incident_frequency_score}, "
                            f"Severity={score.severity_score}, "
                            f"MTTR={score.mttr_score}, Trend={score.trend_score}."
                        ),
                        service_name=service_name,
                        predicted_impact="Increased likelihood of incidents in the next 24-48 hours",
                        recommended_actions=[
                            "Review recent changes to this service",
                            "Check monitoring dashboards for anomalies",
                            "Consider adding capacity or reducing load",
                        ],
                        confidence=min(1.0, score.recent_incidents / 5.0),
                        generated_at=now,
                        expires_at=now + timedelta(hours=24),
                        metadata={"health_score": score.overall_score},
                    )
                )

            # Warn on poor trend
            if score.trend_score < 25 and score.recent_incidents >= 3:
                warnings.append(
                    EarlyWarning(
                        warning_id=self._gen_id(
                            f"trend_{service_name}_{now.isoformat()}"
                        ),
                        warning_type="pattern_acceleration",
                        severity=Severity.MEDIUM,
                        title=f"Incident rate accelerating: {service_name}",
                        description=(
                            f"Incident frequency for {service_name} is increasing. "
                            f"Trend score: {score.trend_score}/100."
                        ),
                        service_name=service_name,
                        predicted_impact="Continued increase in incident volume expected",
                        recommended_actions=[
                            "Investigate root causes of recent incidents",
                            "Review deployment history for correlations",
                            "Schedule reliability review with the team",
                        ],
                        confidence=0.6,
                        generated_at=now,
                        expires_at=now + timedelta(hours=48),
                    )
                )

        logger.info("early_warnings_generated", count=len(warnings))
        return warnings

    @staticmethod
    def _gen_id(base: str) -> str:
        return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()[:12]
