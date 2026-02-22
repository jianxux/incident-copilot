"""Main insights service orchestrating all analysis."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from ..analytics.models import IncidentMetrics
from ..analytics.store import analytics_store
from ..config import Settings, get_settings
from ..supabase_client import is_supabase_db_enabled
from .analyzer import IncidentAnalyzer
from .anomaly import AnomalyDetector
from .detector import PatternDetector
from .digest import DigestGenerator
from .models import (
    AnalysisRequest,
    AnalysisResult,
    DigestPeriod,
    IncidentDigest,
    Insight,
    InsightSummary,
    InsightType,
    RecurringPattern,
    ServiceDependencyMap,
    Severity,
    TimeBasedPattern,
)
from .store import insights_store

logger = structlog.get_logger()


class InsightsService:
    """
    Main service for AI-powered insights and pattern detection.

    Orchestrates pattern detection, anomaly detection, and AI analysis
    to provide actionable insights about incident data.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.pattern_detector = PatternDetector()
        self.anomaly_detector = AnomalyDetector()
        self.analyzer = IncidentAnalyzer()
        self.digest_generator = DigestGenerator(self.settings)
        self.store = insights_store

    # ------------------------------------------------------------------
    # Data fetching: prefer Supabase DB, fall back to in-memory store
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_metrics(row: dict[str, Any]) -> IncidentMetrics:
        """Convert a Supabase incident row to an IncidentMetrics object."""

        def _parse_dt(val: Any) -> datetime | None:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        triggered = (
            _parse_dt(row.get("triggered_at"))
            or _parse_dt(row.get("created_at"))
            or datetime.now(UTC)
        )
        acknowledged = _parse_dt(
            row.get("acknowledged_at") or metadata.get("acknowledged_at")
        )
        resolved = _parse_dt(
            row.get("resolved_at")
            or row.get("processed_at")
            or metadata.get("resolved_at")
        )

        return IncidentMetrics(
            incident_id=str(row.get("id", "")),
            triggered_at=triggered,
            acknowledged_at=acknowledged,
            resolved_at=resolved,
            service_name=row.get("service") or "unknown",
            severity=(row.get("severity") or "medium").lower(),
        )

    async def _fetch_incidents(
        self,
        start: datetime,
        end: datetime,
        service_name: str | None = None,
    ) -> list[IncidentMetrics]:
        """Fetch incidents from Supabase DB, falling back to in-memory store."""
        if is_supabase_db_enabled():
            try:
                from ..db.supabase_db import get_db

                db = get_db(use_admin=True)

                def _query():
                    q = (
                        db.client.table("incidents")
                        .select("*")
                        .gte("created_at", start.isoformat())
                        .lte("created_at", end.isoformat())
                        .order("created_at", desc=True)
                        .limit(5000)
                    )
                    if service_name:
                        q = q.eq("service", service_name)
                    return q.execute()

                result = await db._to_thread(_query)
                rows = result.data or []
                metrics = [self._row_to_metrics(r) for r in rows]
                logger.info(
                    "incidents_fetched_from_db",
                    count=len(metrics),
                    start=start.isoformat(),
                    end=end.isoformat(),
                )
                return metrics
            except Exception as e:
                logger.warning("db_fetch_failed_falling_back", error=str(e))

        # Fallback to in-memory analytics store
        return await analytics_store.get_metrics_for_period(
            start=start, end=end, service_name=service_name
        )

    async def _fetch_all_incidents(self) -> list[IncidentMetrics]:
        """Fetch all incidents from Supabase DB, falling back to in-memory store."""
        if is_supabase_db_enabled():
            try:
                from ..db.supabase_db import get_db

                db = get_db(use_admin=True)

                def _query():
                    return (
                        db.client.table("incidents")
                        .select("*")
                        .order("created_at", desc=True)
                        .limit(5000)
                        .execute()
                    )

                result = await db._to_thread(_query)
                rows = result.data or []
                return [self._row_to_metrics(r) for r in rows]
            except Exception as e:
                logger.warning("db_fetch_all_failed_falling_back", error=str(e))

        return await analytics_store.get_all_metrics()

    async def run_analysis(
        self,
        request: AnalysisRequest | None = None,
    ) -> AnalysisResult:
        """
        Run a comprehensive analysis of incident data.

        This is the main entry point for triggering analysis.
        """
        start_time = datetime.utcnow()
        request = request or AnalysisRequest()

        # Get incidents from the database (Supabase preferred, in-memory fallback)
        lookback_start = datetime.utcnow() - timedelta(days=request.lookback_days)
        incidents = await self._fetch_incidents(
            start=lookback_start,
            end=datetime.utcnow(),
            service_name=request.service_name,
        )

        errors = []
        patterns: list[RecurringPattern] = []
        time_patterns: list[TimeBasedPattern] = []
        anomalies = []
        insights: list[Insight] = []
        dependencies: ServiceDependencyMap | None = None

        # Detect patterns
        if request.include_patterns:
            try:
                patterns = await self.pattern_detector.detect_recurring_patterns(
                    incidents, service_name=request.service_name
                )
                for pattern in patterns:
                    await self.store.save_pattern(pattern)

                time_patterns = await self.pattern_detector.detect_time_patterns(
                    incidents, service_name=request.service_name
                )
                for tp in time_patterns:
                    await self.store.save_time_pattern(tp)

                # Create insights for significant patterns
                for pattern in patterns[:5]:  # Top 5
                    insight = await self._create_pattern_insight(pattern)
                    insights.append(insight)
                    await self.store.save_insight(insight)

            except Exception as e:
                logger.error("pattern_detection_failed", error=str(e))
                errors.append(f"Pattern detection failed: {str(e)}")

        # Detect anomalies
        if request.include_anomalies:
            try:
                anomalies = await self.anomaly_detector.detect_all_anomalies(incidents)
                for anomaly in anomalies:
                    await self.store.save_anomaly(anomaly)

                # Create insights for anomalies
                for anomaly in anomalies[:5]:  # Top 5
                    insight = await self._create_anomaly_insight(anomaly)
                    insights.append(insight)
                    await self.store.save_insight(insight)

            except Exception as e:
                logger.error("anomaly_detection_failed", error=str(e))
                errors.append(f"Anomaly detection failed: {str(e)}")

        # Analyze dependencies
        if request.include_dependencies:
            try:
                dependencies = await self.analyzer.analyze_service_dependencies(
                    incidents
                )
                for dep in dependencies.dependencies:
                    await self.store.save_dependency(dep)
            except Exception as e:
                logger.error("dependency_analysis_failed", error=str(e))
                errors.append(f"Dependency analysis failed: {str(e)}")

        # Calculate result
        end_time = datetime.utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        result = AnalysisResult(
            analysis_id=self._generate_id(f"analysis_{start_time}"),
            started_at=start_time,
            completed_at=end_time,
            duration_ms=duration_ms,
            lookback_days=request.lookback_days,
            incidents_analyzed=len(incidents),
            patterns_found=len(patterns) + len(time_patterns),
            anomalies_found=len(anomalies),
            insights_generated=len(insights),
            patterns=patterns,
            anomalies=anomalies,
            insights=insights,
            service_dependencies=dependencies,
            errors=errors,
        )

        logger.info(
            "analysis_completed",
            duration_ms=duration_ms,
            incidents=len(incidents),
            patterns=len(patterns),
            anomalies=len(anomalies),
            insights=len(insights),
        )

        return result

    async def get_insights(
        self,
        insight_type: InsightType | None = None,
        severity: Severity | None = None,
        service_name: str | None = None,
        limit: int = 50,
    ) -> list[Insight]:
        """Get insights with optional filtering."""
        return await self.store.get_all_insights(
            insight_type=insight_type,
            severity=severity,
            service_name=service_name,
            limit=limit,
        )

    async def get_insight_summary(
        self,
        days: int = 7,
    ) -> InsightSummary:
        """Get a summary of insights for a time period."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        all_insights = await self.store.get_all_insights(limit=1000)

        # Filter to period
        period_insights = [i for i in all_insights if i.created_at >= cutoff]

        # Count by severity
        severity_counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.MEDIUM: 0,
            Severity.LOW: 0,
            Severity.INFO: 0,
        }
        for insight in period_insights:
            severity_counts[insight.severity] += 1

        # Get top services
        service_counts: dict[str, int] = {}
        for insight in period_insights:
            for service in insight.affected_services:
                service_counts[service] = service_counts.get(service, 0) + 1

        top_services = sorted(
            service_counts.keys(), key=lambda x: service_counts[x], reverse=True
        )[:10]

        return InsightSummary(
            period_start=cutoff,
            period_end=datetime.utcnow(),
            total_insights=len(period_insights),
            critical_count=severity_counts[Severity.CRITICAL],
            high_count=severity_counts[Severity.HIGH],
            medium_count=severity_counts[Severity.MEDIUM],
            low_count=severity_counts[Severity.LOW],
            info_count=severity_counts[Severity.INFO],
            top_affected_services=top_services,
            insights=period_insights[:20],  # Return top 20
        )

    async def get_patterns(
        self,
        service_name: str | None = None,
        limit: int = 50,
    ) -> list[RecurringPattern]:
        """Get detected patterns."""
        return await self.store.get_all_patterns(service_name=service_name, limit=limit)

    async def get_anomalies(
        self,
        service_name: str | None = None,
        severity: Severity | None = None,
        limit: int = 50,
    ) -> list:
        """Get detected anomalies."""
        return await self.store.get_all_anomalies(
            service_name=service_name, severity=severity, limit=limit
        )

    async def generate_digest(
        self,
        period: DigestPeriod = DigestPeriod.WEEKLY,
        generate_ai: bool = True,
    ) -> IncidentDigest:
        """Generate an incident digest."""
        # Get all incidents from DB
        incidents = await self._fetch_all_incidents()

        digest = await self.digest_generator.generate_digest(
            incidents=incidents,
            period=period,
            generate_ai_summary=generate_ai,
        )

        # Save digest
        await self.store.save_digest(digest)

        return digest

    async def get_latest_digest(
        self,
        period: str | None = None,
    ) -> IncidentDigest | None:
        """Get the latest digest."""
        return await self.store.get_latest_digest(period=period)

    async def get_service_dependencies(
        self,
        service_name: str | None = None,
    ) -> list:
        """Get service dependencies."""
        return await self.store.get_all_dependencies(service_name=service_name)

    async def acknowledge_insight(
        self,
        insight_id: str,
        acknowledged_by: str,
    ) -> Insight | None:
        """Acknowledge an insight."""
        return await self.store.acknowledge_insight(insight_id, acknowledged_by)

    async def _create_pattern_insight(
        self,
        pattern: RecurringPattern,
    ) -> Insight:
        """Create an insight from a detected pattern."""
        severity = Severity.MEDIUM
        if pattern.incident_count >= 10:
            severity = Severity.HIGH
        elif pattern.incident_count >= 20:
            severity = Severity.CRITICAL

        return Insight(
            insight_id=self._generate_id(f"insight_pattern_{pattern.pattern_id}"),
            insight_type=InsightType.RECURRING_INCIDENT,
            severity=severity,
            title=f"Recurring incident pattern: {pattern.title_pattern[:50]}",
            description=f"This incident pattern has occurred {pattern.incident_count} times. "
            f"First seen: {pattern.first_seen.strftime('%Y-%m-%d')}, "
            f"Last seen: {pattern.last_seen.strftime('%Y-%m-%d')}.",
            affected_services=[pattern.service_name],
            affected_incident_ids=pattern.affected_incident_ids,
            recommendations=(
                [pattern.suggested_action] if pattern.suggested_action else []
            ),
            confidence=min(1.0, pattern.incident_count / 20),
            metadata={"pattern_id": pattern.pattern_id},
        )

    async def _create_anomaly_insight(
        self,
        anomaly,
    ) -> Insight:
        """Create an insight from a detected anomaly."""
        insight_type_map = {
            "spike": InsightType.SPIKE_DETECTED,
            "cascading": InsightType.CASCADING_FAILURE,
            "unusual_hour": InsightType.TIME_BASED_PATTERN,
            "unusual_day": InsightType.TIME_BASED_PATTERN,
        }

        insight_type = insight_type_map.get(
            anomaly.anomaly_type.value, InsightType.CORRELATION
        )

        return Insight(
            insight_id=self._generate_id(f"insight_anomaly_{anomaly.anomaly_id}"),
            insight_type=insight_type,
            severity=anomaly.severity,
            title=f"Anomaly detected: {anomaly.anomaly_type.value}",
            description=anomaly.description,
            affected_services=anomaly.affected_services,
            affected_incident_ids=anomaly.affected_incident_ids,
            recommendations=self._get_anomaly_recommendations(anomaly),
            confidence=0.8,
            metadata={
                "anomaly_id": anomaly.anomaly_id,
                "anomaly_type": anomaly.anomaly_type.value,
            },
        )

    def _get_anomaly_recommendations(self, anomaly) -> list[str]:
        """Get recommendations based on anomaly type."""
        recommendations = {
            "spike": [
                "Investigate recent deployments or configuration changes",
                "Check for external factors (traffic surge, dependency issues)",
                "Review monitoring alerts for correlating signals",
            ],
            "cascading": [
                "Identify the root cause in the trigger service",
                "Review service dependencies and circuit breakers",
                "Consider implementing bulkhead patterns",
            ],
            "unusual_hour": [
                "Check scheduled jobs or batch processes",
                "Review access patterns for this time period",
                "Consider on-call coverage during off-hours",
            ],
            "unusual_day": [
                "Check weekend maintenance schedules",
                "Review automated processes running on this day",
            ],
        }
        return recommendations.get(anomaly.anomaly_type.value, [])

    def _generate_id(self, base: str) -> str:
        """Generate a deterministic ID."""
        return hashlib.md5(base.encode(), usedforsecurity=False).hexdigest()[:12]


# Global service instance
insights_service = InsightsService()
