"""Digest generation with AI summaries.

AI analysis is delegated to the external AI service via ai_client.
Statistics, pattern detection, and anomaly detection run locally.
"""

import hashlib
import json
from datetime import datetime, timedelta, UTC

import structlog

from ..ai.client import ai_client
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
        now = datetime.now(UTC)

        # Determine period boundaries
        if period == DigestPeriod.DAILY:
            period_start = now - timedelta(days=1)
        elif period == DigestPeriod.WEEKLY:
            period_start = now - timedelta(days=7)
        else:  # MONTHLY
            period_start = now - timedelta(days=30)

        period_end = now

        # Filter incidents to period
        period_incidents = []
        for i in incidents:
            triggered_at = self._as_utc_aware(i.triggered_at)
            if period_start <= triggered_at <= period_end:
                period_incidents.append(i)

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

        # Generate AI summary if enabled
        ai_data = {}
        if generate_ai_summary:
            ai_data = await self._generate_ai_summary(
                period=period,
                period_start=period_start,
                period_end=period_end,
                total_incidents=total,
                resolved_incidents=resolved,
                avg_mttr=avg_mttr,
                severity_counts=severity_counts,
                top_services=top_services,
                patterns=patterns,
                anomalies=anomalies,
                severity_trend=severity_trend,
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
        period_start: datetime,
        period_end: datetime,
        total_incidents: int,
        resolved_incidents: int,
        avg_mttr: float | None,
        severity_counts: dict[str, int],
        top_services: list[tuple[str, int]],
        patterns: list[RecurringPattern],
        anomalies: list[AnomalyDetection],
        severity_trend: SeverityTrend | None,
    ) -> dict:
        """Generate AI summary via the AI service."""
        try:
            # Build incident summaries for the AI service
            incident_dicts = [
                {
                    "period": period.value,
                    "start_date": period_start.isoformat(),
                    "end_date": period_end.isoformat(),
                    "total": total_incidents,
                    "resolved": resolved_incidents,
                    "avg_mttr_minutes": f"{avg_mttr:.1f}" if avg_mttr else None,
                    "severity_counts": severity_counts,
                    "top_services": [
                        {"service": s, "count": c} for s, c in top_services
                    ],
                    "patterns": [
                        {"title": p.title_pattern, "count": p.incident_count}
                        for p in patterns[:5]
                    ],
                    "anomalies": [a.description for a in anomalies[:5]],
                    "severity_trend": (
                        f"{severity_trend.trend_direction} ({severity_trend.change_percent:+.1f}%)"
                        if severity_trend
                        else None
                    ),
                }
            ]

            result = await ai_client.generate_digest(incident_dicts, period.value)

            return {
                "executive_summary": result.get("summary", ""),
                "key_findings": result.get("insights", []),
                "recommendations": result.get("recommendations", []),
                "risk_assessment": result.get("risk_assessment"),
            }

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
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        recent = [
            i for i in incidents if self._as_utc_aware(i.triggered_at) >= cutoff
        ]

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

    @staticmethod
    def _as_utc_aware(value: datetime) -> datetime:
        """Normalize datetime to UTC-aware; treat naive values as UTC."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
