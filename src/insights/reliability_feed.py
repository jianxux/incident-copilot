"""Reliability insights feed for dev teams."""

import hashlib
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

import structlog

from ..analytics.models import IncidentMetrics
from .models import (
    ReliabilityDigest,
    ReliabilityLesson,
    ServiceHealthScore,
    ShiftLeftReport,
    Severity,
    EarlyWarning,
)

logger = structlog.get_logger()

# Mapping of incident patterns to preventive categories
CATEGORY_KEYWORDS = {
    "prevention": ["timeout", "capacity", "scaling", "memory", "disk", "cpu"],
    "detection": ["alert", "monitor", "threshold", "silent", "undetected"],
    "response": ["runbook", "escalation", "communication", "delay"],
    "recovery": ["rollback", "failover", "backup", "restore", "redundancy"],
}


class ReliabilityFeedGenerator:
    """
    Generates reliability insights for dev teams including:
    - Aggregated lessons learned from incidents
    - Shift-left reports with preventive measures
    - Exportable reliability digests
    """

    async def extract_lessons(
        self,
        incidents: list[IncidentMetrics],
        service_name: str | None = None,
    ) -> list[ReliabilityLesson]:
        """
        Extract lessons learned from incident history.

        Groups incidents by patterns and generates actionable lessons.
        """
        if not incidents:
            return []

        if service_name:
            incidents = [i for i in incidents if i.service_name == service_name]

        # Group by service
        by_service: dict[str, list[IncidentMetrics]] = defaultdict(list)
        for inc in incidents:
            by_service[inc.service_name].append(inc)

        lessons: list[ReliabilityLesson] = []

        for svc, svc_incidents in by_service.items():
            # Lesson: High severity incidents
            critical = [i for i in svc_incidents if i.severity in ("critical", "high")]
            if len(critical) >= 2:
                lessons.append(
                    ReliabilityLesson(
                        lesson_id=self._gen_id(f"critical_{svc}"),
                        service_name=svc,
                        title=f"Recurring high-severity incidents in {svc}",
                        description=(
                            f"{len(critical)} critical/high incidents in the period. "
                            "Investigate common root causes and add preventive measures."
                        ),
                        source_incident_ids=[i.incident_id for i in critical],
                        category="prevention",
                        impact_level=Severity.HIGH,
                    )
                )

            # Lesson: Slow resolution
            slow = []
            for inc in svc_incidents:
                if inc.resolved_at:
                    mttr = (inc.resolved_at - inc.triggered_at).total_seconds() / 60.0
                    if mttr > 120:  # > 2 hours
                        slow.append(inc)
            if len(slow) >= 2:
                lessons.append(
                    ReliabilityLesson(
                        lesson_id=self._gen_id(f"slow_mttr_{svc}"),
                        service_name=svc,
                        title=f"Slow incident resolution for {svc}",
                        description=(
                            f"{len(slow)} incidents took over 2 hours to resolve. "
                            "Consider creating runbooks or improving alerting."
                        ),
                        source_incident_ids=[i.incident_id for i in slow],
                        category="response",
                        impact_level=Severity.MEDIUM,
                    )
                )

            # Lesson: Frequent incidents
            if len(svc_incidents) >= 5:
                lessons.append(
                    ReliabilityLesson(
                        lesson_id=self._gen_id(f"frequent_{svc}"),
                        service_name=svc,
                        title=f"High incident volume for {svc}",
                        description=(
                            f"{len(svc_incidents)} incidents in the period suggests "
                            "systemic reliability issues. Prioritize a reliability review."
                        ),
                        source_incident_ids=[i.incident_id for i in svc_incidents[:10]],
                        category="prevention",
                        impact_level=Severity.HIGH,
                    )
                )

        logger.info("lessons_extracted", count=len(lessons))
        return lessons

    async def generate_shift_left_report(
        self,
        service_name: str,
        incidents: list[IncidentMetrics],
        lookback_days: int = 30,
    ) -> ShiftLeftReport:
        """
        Generate a shift-left report suggesting how to prevent incidents
        earlier in the development lifecycle.
        """
        cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
        service_incidents = [
            i
            for i in incidents
            if i.service_name == service_name and i.triggered_at >= cutoff
        ]

        # Categorize incidents
        categories: Counter[str] = Counter()
        for inc in service_incidents:
            cat = self._categorize_incident(inc)
            categories[cat] += 1

        # Estimate preventable incidents (prevention + detection categories)
        preventable = categories.get("prevention", 0) + categories.get("detection", 0)

        recommendations = []
        if categories.get("prevention", 0) > 0:
            recommendations.append(
                "Add capacity planning alerts and auto-scaling policies"
            )
            recommendations.append(
                "Implement chaos engineering to test failure modes"
            )
        if categories.get("detection", 0) > 0:
            recommendations.append(
                "Review and tune alerting thresholds"
            )
            recommendations.append(
                "Add synthetic monitoring for critical paths"
            )
        if categories.get("response", 0) > 0:
            recommendations.append(
                "Create or update runbooks for common incident types"
            )
        if categories.get("recovery", 0) > 0:
            recommendations.append(
                "Test rollback procedures and failover mechanisms regularly"
            )
        if not recommendations:
            recommendations.append("Continue current reliability practices")

        lessons = await self.extract_lessons(service_incidents, service_name)

        return ShiftLeftReport(
            report_id=self._gen_id(f"shift_left_{service_name}_{lookback_days}"),
            service_name=service_name,
            period_days=lookback_days,
            total_incidents=len(service_incidents),
            preventable_incidents=preventable,
            top_categories=categories.most_common(5),
            lessons=lessons,
            recommendations=recommendations,
        )

    async def generate_reliability_digest(
        self,
        service_name: str | None,
        incidents: list[IncidentMetrics],
        health_score: ServiceHealthScore | None = None,
        early_warnings: list[EarlyWarning] | None = None,
        lookback_days: int = 7,
    ) -> ReliabilityDigest:
        """Generate an exportable reliability digest."""
        now = datetime.now(UTC)
        period_start = now - timedelta(days=lookback_days)

        lessons = await self.extract_lessons(incidents, service_name)

        shift_left = None
        if service_name:
            shift_left = await self.generate_shift_left_report(
                service_name, incidents, lookback_days
            )

        # Build summary
        svc_label = service_name or "all services"
        total = len(
            [i for i in incidents if i.triggered_at >= period_start]
            if service_name is None
            else [
                i
                for i in incidents
                if i.service_name == service_name and i.triggered_at >= period_start
            ]
        )
        summary = (
            f"Reliability digest for {svc_label} over the past {lookback_days} days: "
            f"{total} incidents, {len(lessons)} lessons learned."
        )
        if health_score:
            summary += f" Health score: {health_score.overall_score}/100."

        return ReliabilityDigest(
            digest_id=self._gen_id(
                f"digest_{service_name}_{period_start.isoformat()}"
            ),
            service_name=service_name,
            period_start=period_start,
            period_end=now,
            health_score=health_score,
            shift_left_report=shift_left,
            early_warnings=early_warnings or [],
            lessons=lessons,
            summary=summary,
        )

    def _categorize_incident(self, incident: IncidentMetrics) -> str:
        """Categorize an incident into prevention/detection/response/recovery."""
        # Use incident_id as a proxy for title-based categorization
        text = incident.incident_id.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return category
        # Default based on severity
        if incident.severity in ("critical", "high"):
            return "prevention"
        return "detection"

    @staticmethod
    def _gen_id(base: str) -> str:
        return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()[:12]
