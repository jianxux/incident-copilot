"""Deployment risk scoring engine."""

import hashlib
from datetime import UTC, datetime, timedelta

import structlog

from ..analytics.models import IncidentMetrics
from .models import (
    DeploymentInfo,
    DeploymentRiskScore,
    RiskFactor,
    Severity,
)

logger = structlog.get_logger()

# High-risk deployment hours (outside business hours or Friday afternoon+)
HIGH_RISK_HOURS = set(range(0, 6)) | set(range(22, 24))  # Late night / early morning
FRIDAY_RISK_HOURS = set(range(14, 24))  # Friday afternoon onwards


class DeploymentRiskScorer:
    """
    Scores deployment risk based on multiple factors:
    - Services touched (blast radius)
    - Recent incident history for affected services
    - Time of day / day of week
    - Change size (files, lines)
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
    ):
        self.weights = weights or {
            "blast_radius": 0.25,
            "incident_history": 0.30,
            "timing": 0.20,
            "change_size": 0.25,
        }

    async def score_deployment(
        self,
        deployment: DeploymentInfo,
        incidents: list[IncidentMetrics],
        lookback_days: int = 30,
    ) -> DeploymentRiskScore:
        """Score the risk of a deployment."""
        factors: list[RiskFactor] = []

        # Factor 1: Blast radius
        blast_factor = self._score_blast_radius(deployment)
        factors.append(blast_factor)

        # Factor 2: Recent incident history
        history_factor = self._score_incident_history(
            deployment, incidents, lookback_days
        )
        factors.append(history_factor)

        # Factor 3: Timing
        timing_factor = self._score_timing(deployment)
        factors.append(timing_factor)

        # Factor 4: Change size
        size_factor = self._score_change_size(deployment)
        factors.append(size_factor)

        # Calculate weighted overall score
        overall = sum(f.score * f.weight for f in factors)

        # Determine risk level
        if overall >= 75:
            risk_level = "critical"
        elif overall >= 50:
            risk_level = "high"
        elif overall >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Build recommendations
        recommendations = self._build_recommendations(factors, risk_level, deployment)

        score = DeploymentRiskScore(
            deployment_id=deployment.deployment_id,
            service_name=deployment.service_name,
            overall_risk=round(overall, 2),
            risk_level=risk_level,
            factors=factors,
            recommended_actions=recommendations,
            assessed_at=datetime.now(UTC),
        )

        logger.info(
            "deployment_risk_scored",
            deployment_id=deployment.deployment_id,
            risk_level=risk_level,
            overall_risk=overall,
        )
        return score

    def _score_blast_radius(self, deployment: DeploymentInfo) -> RiskFactor:
        """Score based on number of services affected."""
        count = max(1, len(deployment.services_touched))
        # 1 service = 10, 2 = 30, 3+ = escalating
        score = min(100.0, count * 20.0)
        if deployment.is_rollback:
            score = max(0.0, score - 20.0)  # Rollbacks are safer

        return RiskFactor(
            name="blast_radius",
            score=round(score, 2),
            weight=self.weights["blast_radius"],
            description=f"Deployment touches {count} service(s)",
            details={"services_touched": deployment.services_touched},
        )

    def _score_incident_history(
        self,
        deployment: DeploymentInfo,
        incidents: list[IncidentMetrics],
        lookback_days: int,
    ) -> RiskFactor:
        """Score based on recent incidents for affected services."""
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        affected = set(deployment.services_touched) | {deployment.service_name}

        recent = [
            i
            for i in incidents
            if i.service_name in affected and i.triggered_at >= cutoff
        ]

        # Score: 0 incidents = 0 risk, 10+ = 100
        score = min(100.0, len(recent) * 10.0)

        # Boost if there were critical/high incidents
        critical_count = sum(1 for i in recent if i.severity in ("critical", "high"))
        if critical_count > 0:
            score = min(100.0, score + critical_count * 15.0)

        return RiskFactor(
            name="incident_history",
            score=round(score, 2),
            weight=self.weights["incident_history"],
            description=f"{len(recent)} recent incidents ({critical_count} critical/high)",
            details={
                "recent_incidents": len(recent),
                "critical_high": critical_count,
            },
        )

    def _score_timing(self, deployment: DeploymentInfo) -> RiskFactor:
        """Score based on deployment time."""
        dt = deployment.deploy_time
        hour = dt.hour
        weekday = dt.weekday()

        score = 0.0
        reasons = []

        if weekday == 4 and hour in FRIDAY_RISK_HOURS:
            score = 80.0
            reasons.append("Friday afternoon/evening deployment")
        elif weekday in (5, 6):
            score = 70.0
            reasons.append("Weekend deployment")
        elif hour in HIGH_RISK_HOURS:
            score = 60.0
            reasons.append("Late night / early morning deployment")
        else:
            score = 10.0
            reasons.append("Standard business hours")

        return RiskFactor(
            name="timing",
            score=round(score, 2),
            weight=self.weights["timing"],
            description="; ".join(reasons),
            details={"hour": hour, "weekday": weekday},
        )

    def _score_change_size(self, deployment: DeploymentInfo) -> RiskFactor:
        """Score based on the size of code changes."""
        total_lines = deployment.lines_added + deployment.lines_removed
        files = deployment.files_changed

        # Small change = low risk, large change = high risk
        line_score = min(100.0, total_lines / 10.0)  # 1000 lines = 100
        file_score = min(100.0, files * 5.0)  # 20 files = 100
        score = (line_score + file_score) / 2.0

        return RiskFactor(
            name="change_size",
            score=round(score, 2),
            weight=self.weights["change_size"],
            description=f"{files} files changed, {total_lines} lines modified",
            details={
                "files_changed": files,
                "lines_added": deployment.lines_added,
                "lines_removed": deployment.lines_removed,
            },
        )

    def _build_recommendations(
        self,
        factors: list[RiskFactor],
        risk_level: str,
        deployment: DeploymentInfo,
    ) -> list[str]:
        """Build actionable recommendations."""
        recs = []

        factor_map = {f.name: f for f in factors}

        if factor_map["timing"].score >= 60:
            recs.append("Consider delaying deployment to business hours")

        if factor_map["incident_history"].score >= 50:
            recs.append(
                "Review recent incidents for affected services before deploying"
            )

        if factor_map["change_size"].score >= 50:
            recs.append("Consider breaking this into smaller deployments")

        if factor_map["blast_radius"].score >= 50:
            recs.append("Use canary deployment strategy for wide-reaching changes")

        if risk_level in ("high", "critical"):
            recs.append("Ensure rollback plan is ready before deploying")
            recs.append("Have on-call engineer actively monitoring during deploy")

        if not recs:
            recs.append("Low risk deployment — proceed with standard monitoring")

        return recs
