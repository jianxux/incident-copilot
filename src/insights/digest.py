"""Digest generation with AI summaries.

Note: AI-powered digest generation routes through src.ai (AI service boundary).
"""

import hashlib
from datetime import datetime, timedelta

import structlog

from ..ai import ai_client
from ..analytics.models import IncidentMetrics
from ..config import Settings
from .analyzer import IncidentAnalyzer
from .anomaly import AnomalyDetector
from .detector import PatternDetector
from .models import (
    AnomalyDetection,
    DigestPeriod,
    IncidentDigest,
    RecurringPattern,
    SeverityTrend,
)

logger = structlog.get_logger()


class DigestGenerator:
    """Generates AI-powered incident digests."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pattern_detector = PatternDetector()
        self.anomaly_detector = AnomalyDetector()
        self.analyzer = IncidentAnalyzer()

    async def generate_digest(
        self,
        incidents: list[IncidentMetrics],
        period: DigestPeriod = DigestPeriod.WEEKLY,
        generate_ai_summary: bool = True,
    ) -> IncidentDigest:
        """
        Generate a comprehensive incident digest.

        Combines statistics, patterns, anomalies, and AI-generated insights.
        """
        now = datetime.utcnow()

        # Determine period boundaries
        if period == DigestPeriod.DAILY:
            period_start = now - timedelta(days=1)
        elif period == DigestPeriod.WEEKLY:
            period_start = now - timedelta(days=7)
        else:  # MONTHLY
            period_start = now - timedelta(days=30)

        period_end = now

        # Filter incidents to period
        period_incidents = [
            i for i in incidents if period_start <= i.triggered_at <= period_end
        ]

        # Calculate basic stats
        total = len(period_incidents)
        resolved = len([i for i in period_incidents if i.resolved_at])

        # Calculate MTTR
        mttr_values = [
            i.time_to_resolve_seconds / 60
            for i in period_incidents
            if i.time_to_resolve_seconds
        ]
        avg_mttr = sum(mttr_values) / len(mttr_values) if mttr_values else None

        # Count by severity
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
        }
        for i in period_incidents:
            sev = i.severity.lower()
            if sev in severity_counts:
                severity_counts[sev] += 1

        # Get top services
        service_counts: dict[str, int] = {}
        for i in period_incidents:
            service_counts[i.service_name] = service_counts.get(i.service_name, 0) + 1

        top_services = sorted(service_counts.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]

        # Detect patterns
        patterns = await self.pattern_detector.detect_recurring_patterns(
            period_incidents
        )
        anomalies = await self.anomaly_detector.detect_all_anomalies(period_incidents)
        severity_trend = await self.pattern_detector.detect_severity_trends(
            period_incidents, period_days=(period_end - period_start).days
        )

        # Generate AI summary (routes through AI service boundary)
        ai_data: dict = {}
        if generate_ai_summary:
            ai_data = await self._generate_ai_summary(
                period=period,
                incidents=period_incidents,
            )

        # Build digest
        digest = IncidentDigest(
            digest_id=self._generate_digest_id(period, period_start),
            period=period,
            period_start=period_start,
            period_end=period_end,
            total_incidents=total,
            resolved_incidents=resolved,
            avg_mttr_minutes=avg_mttr,
            critical_count=severity_counts["critical"],
            high_count=severity_counts["high"],
            medium_count=severity_counts["medium"],
            low_count=severity_counts["low"],
            top_services=top_services,
            new_patterns=patterns[:5],  # Top 5 patterns
            active_anomalies=anomalies[:5],  # Top 5 anomalies
            severity_trend=severity_trend,
            executive_summary=ai_data.get("executive_summary"),
            key_findings=ai_data.get("key_findings", []),
            recommendations=ai_data.get("recommendations", []),
            risk_assessment=ai_data.get("risk_assessment"),
        )

        logger.info(
            "digest_generated",
            period=period.value,
            total_incidents=total,
            patterns_found=len(patterns),
            anomalies_found=len(anomalies),
        )

        return digest

    async def _generate_ai_summary(
        self,
        period: DigestPeriod,
        incidents: list[IncidentMetrics],
    ) -> dict:
        """Generate AI summary via the proprietary AI service (if configured).

        Falls back to stub responses when AI_SERVICE_URL is not set.
        """
        try:
            incident_dicts: list[dict] = []
            for inc in incidents:
                if hasattr(inc, "model_dump"):
                    incident_dicts.append(inc.model_dump())  # pydantic v2
                elif hasattr(inc, "dict"):
                    incident_dicts.append(inc.dict())  # pydantic v1
                else:
                    incident_dicts.append({"service_name": getattr(inc, "service_name", "")})

            return await ai_client.generate_digest(
                incidents=incident_dicts,
                period=period.value,
            )
        except Exception as e:
            logger.error("ai_digest_generation_failed", error=str(e))
            return {}

    def _generate_digest_id(self, period: DigestPeriod, start: datetime) -> str:
        """Generate a deterministic digest ID."""
        base = f"{period.value}_{start.isoformat()}"
        return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()[:12]

    async def generate_quick_summary(
        self,
        incidents: list[IncidentMetrics],
        hours: int = 24,
    ) -> str:
        """
        Generate a quick text summary for the last N hours.

        Useful for Slack/Teams notifications.
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent = [i for i in incidents if i.triggered_at >= cutoff]

        if not recent:
            return f"✅ No incidents in the last {hours} hours"

        # Group by service
        by_service: dict[str, list[IncidentMetrics]] = {}
        for inc in recent:
            by_service.setdefault(inc.service_name, []).append(inc)

        # Count by severity
        critical = sum(1 for i in recent if i.severity == "critical")
        high = sum(1 for i in recent if i.severity == "high")

        # Build summary
        lines = [f"📊 **Last {hours}h Summary**"]
        lines.append(f"Total: {len(recent)} incidents")

        if critical or high:
            lines.append(f"🔴 Critical: {critical} | 🟠 High: {high}")

        lines.append("\n**By Service:**")
        for service, incs in sorted(
            by_service.items(), key=lambda x: len(x[1]), reverse=True
        )[:5]:
            lines.append(f"- {service}: {len(incs)}")

        return "\n".join(lines)
