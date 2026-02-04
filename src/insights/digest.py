"""Digest generation with AI summaries."""

import hashlib
import json
from datetime import datetime, timedelta

import structlog
from openai import AsyncOpenAI

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


DIGEST_PROMPT = """You are an SRE team lead preparing a {period} incident digest for your team.

## Incident Summary for {start_date} to {end_date}

**Total Incidents:** {total_incidents}
**Resolved:** {resolved_incidents}
**Average MTTR:** {avg_mttr} minutes

### Severity Breakdown:
- Critical: {critical_count}
- High: {high_count}
- Medium: {medium_count}
- Low: {low_count}

### Top Affected Services:
{top_services}

### Detected Patterns:
{patterns}

### Anomalies:
{anomalies}

### Severity Trend:
{severity_trend}

Based on this data, provide a concise digest in JSON format:
{{
    "executive_summary": "2-3 sentence high-level summary for leadership",
    "key_findings": ["finding1", "finding2", "finding3"],
    "recommendations": ["recommendation1", "recommendation2"],
    "risk_assessment": "Brief assessment of current risk level and concerns"
}}

Be specific, actionable, and data-driven. Focus on patterns and trends, not individual incidents."""


class DigestGenerator:
    """Generates AI-powered incident digests."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            AsyncOpenAI(api_key=settings.openai_api_key)
            if settings.openai_api_key
            else None
        )
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
            i for i in incidents
            if period_start <= i.triggered_at <= period_end
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

        top_services = sorted(
            service_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Detect patterns
        patterns = await self.pattern_detector.detect_recurring_patterns(
            period_incidents
        )
        anomalies = await self.anomaly_detector.detect_all_anomalies(period_incidents)
        severity_trend = await self.pattern_detector.detect_severity_trends(
            period_incidents, period_days=(period_end - period_start).days
        )

        # Generate AI summary if enabled and API key available
        ai_data = {}
        if generate_ai_summary and self.client:
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
        """Generate AI summary using OpenAI."""
        if not self.client:
            return {}

        try:
            # Format data for prompt
            top_services_str = "\n".join(
                f"- {service}: {count} incidents" for service, count in top_services
            )

            patterns_str = "\n".join(
                f"- {p.title_pattern}: {p.incident_count} occurrences"
                for p in patterns[:5]
            ) or "No significant patterns detected"

            anomalies_str = "\n".join(
                f"- {a.description}" for a in anomalies[:5]
            ) or "No anomalies detected"

            severity_trend_str = "Not enough data" if not severity_trend else (
                f"{severity_trend.trend_direction} ({severity_trend.change_percent:+.1f}% change)"
            )

            prompt = DIGEST_PROMPT.format(
                period=period.value,
                start_date=period_start.strftime("%Y-%m-%d"),
                end_date=period_end.strftime("%Y-%m-%d"),
                total_incidents=total_incidents,
                resolved_incidents=resolved_incidents,
                avg_mttr=f"{avg_mttr:.1f}" if avg_mttr else "N/A",
                critical_count=severity_counts["critical"],
                high_count=severity_counts["high"],
                medium_count=severity_counts["medium"],
                low_count=severity_counts["low"],
                top_services=top_services_str,
                patterns=patterns_str,
                anomalies=anomalies_str,
                severity_trend=severity_trend_str,
            )

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.7,
            )

            content = response.choices[0].message.content
            # Parse JSON from response
            data = json.loads(content)
            return data

        except json.JSONDecodeError as e:
            logger.error("ai_digest_json_error", error=str(e))
            return {}
        except Exception as e:
            logger.error("ai_digest_generation_failed", error=str(e))
            return {}

    def _generate_digest_id(self, period: DigestPeriod, start: datetime) -> str:
        """Generate a deterministic digest ID."""
        base = f"{period.value}_{start.isoformat()}"
        return hashlib.md5(base.encode()).hexdigest()[:12]

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
