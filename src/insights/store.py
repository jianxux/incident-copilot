"""In-memory store for insights data."""

import asyncio
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import structlog

from ..supabase_client import is_supabase_db_enabled
from .models import (
    AnomalyDetection,
    CascadingFailure,
    IncidentDigest,
    IncidentSpike,
    Insight,
    InsightType,
    RecurringPattern,
    ServiceDependency,
    Severity,
    TimeBasedPattern,
)

logger = structlog.get_logger()


class InsightsStore:
    """
    Thread-safe in-memory store for insights data.

    Designed to be replaced with a database backend later.
    """

    def __init__(self, max_items: int = 10000):
        self._insights: dict[str, Insight] = {}
        self._patterns: dict[str, RecurringPattern] = {}
        self._time_patterns: dict[str, TimeBasedPattern] = {}
        self._anomalies: dict[str, AnomalyDetection] = {}
        self._spikes: dict[str, IncidentSpike] = {}
        self._cascades: dict[str, CascadingFailure] = {}
        self._dependencies: dict[str, ServiceDependency] = {}
        self._digests: dict[str, IncidentDigest] = {}
        self._max_items = max_items
        self._lock = asyncio.Lock()
        self._tenant_id: str | None = None
        self._supabase_loaded: set[str] = set()

    _KIND_INSIGHT = "insight"
    _KIND_PATTERN = "pattern"
    _KIND_TIME_PATTERN = "time_pattern"
    _KIND_ANOMALY = "anomaly"
    _KIND_SPIKE = "spike"
    _KIND_CASCADE = "cascade"
    _KIND_DEPENDENCY = "dependency"
    _KIND_DIGEST = "digest"

    # --- Supabase Persistence Helpers ---

    async def _get_db(self):
        from ..db.supabase_db import get_db

        return get_db(use_admin=True)

    async def _ensure_tenant_id(self) -> str | None:
        if self._tenant_id:
            return self._tenant_id
        if not is_supabase_db_enabled():
            return None
        try:
            db = await self._get_db()
            tenant = await db.ensure_tenant(slug="default", name="Default Tenant")
            tenant_id = str(tenant.get("id") or "")
            if tenant_id:
                self._tenant_id = tenant_id
                return tenant_id
        except Exception as exc:
            logger.warning("insights_tenant_resolution_failed", error=str(exc))
        return None

    @classmethod
    def _to_json_dict(cls, model: Any) -> dict[str, Any]:
        payload = model.model_dump(mode="json")
        if isinstance(payload, dict):
            return payload
        return {}

    @staticmethod
    def _stable_uuid(record_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"incident-copilot-insights:{record_id}"))

    async def _upsert_row(self, row: dict[str, Any]) -> None:
        if not is_supabase_db_enabled():
            return
        try:
            db = await self._get_db()
            await db._to_thread(lambda: db.client.table("insights").upsert(row).execute())
        except Exception as exc:
            logger.warning("insights_supabase_upsert_failed", error=str(exc))

    async def _save_record(
        self,
        *,
        record_id: str,
        insight_type: str,
        severity: str,
        title: str,
        description: str | None,
        service_name: str | None,
        affected_incident_ids: list[str],
        data: dict[str, Any],
    ) -> None:
        tenant_id = await self._ensure_tenant_id()
        if not tenant_id:
            return
        now_iso = datetime.utcnow().isoformat()
        row = {
            "id": self._stable_uuid(record_id),
            "tenant_id": tenant_id,
            "insight_type": insight_type,
            "severity": severity,
            "title": title,
            "description": description,
            "service_name": service_name,
            "data": data,
            "affected_incident_ids": affected_incident_ids,
            "is_active": True,
            "updated_at": now_iso,
            "created_at": data.get("created_at") or data.get("detected_at") or data.get("generated_at") or now_iso,
        }
        await self._upsert_row(row)

    async def _fetch_rows(self, insight_type: str | None = None, limit: int = 5000) -> list[dict[str, Any]]:
        if not is_supabase_db_enabled():
            return []
        tenant_id = await self._ensure_tenant_id()
        if not tenant_id:
            return []
        try:
            db = await self._get_db()

            def _query():
                query = db.client.table("insights").select("*").eq("tenant_id", tenant_id)
                if insight_type:
                    query = query.eq("insight_type", insight_type)
                return query.order("created_at", desc=True).limit(limit).execute()

            res = await db._to_thread(_query)
            return res.data or []
        except Exception as exc:
            logger.warning(
                "insights_supabase_load_failed",
                error=str(exc),
                insight_type=insight_type,
            )
            return []

    async def _ensure_loaded(self, kind: str) -> None:
        if not is_supabase_db_enabled() or kind in self._supabase_loaded:
            return
        async with self._lock:
            if kind in self._supabase_loaded:
                return
            await self._load_from_supabase(kind)
            self._supabase_loaded.add(kind)

    async def _load_from_supabase(self, kind: str) -> None:
        if kind == self._KIND_INSIGHT:
            rows = await self._fetch_rows(limit=self._max_items)
            insight_types = {t.value for t in InsightType}
            for row in rows:
                row_type = str(row.get("insight_type") or "")
                if row_type not in insight_types:
                    continue
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                payload = {
                    **payload,
                    "insight_id": payload.get("insight_id") or row.get("id"),
                    "insight_type": row_type,
                    "severity": row.get("severity") or "info",
                    "title": row.get("title") or "",
                    "description": row.get("description") or "",
                    "affected_incident_ids": row.get("affected_incident_ids") or [],
                    "affected_services": payload.get("affected_services") or (
                        [row.get("service_name")] if row.get("service_name") else []
                    ),
                    "created_at": row.get("created_at"),
                }
                try:
                    insight = Insight.model_validate(payload)
                    if insight.insight_id not in self._insights:
                        self._insights[insight.insight_id] = insight
                except Exception:
                    continue
            self._trim_dict(self._insights)
            return

        if kind == self._KIND_PATTERN:
            rows = await self._fetch_rows(self._KIND_PATTERN, self._max_items)
            for row in rows:
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                if not payload:
                    continue
                try:
                    pattern = RecurringPattern.model_validate(payload)
                    if pattern.pattern_id not in self._patterns:
                        self._patterns[pattern.pattern_id] = pattern
                except Exception:
                    continue
            self._trim_dict(self._patterns)
            return

        if kind == self._KIND_TIME_PATTERN:
            rows = await self._fetch_rows(self._KIND_TIME_PATTERN, self._max_items)
            for row in rows:
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                if not payload:
                    continue
                try:
                    pattern = TimeBasedPattern.model_validate(payload)
                    if pattern.pattern_id not in self._time_patterns:
                        self._time_patterns[pattern.pattern_id] = pattern
                except Exception:
                    continue
            self._trim_dict(self._time_patterns)
            return

        if kind == self._KIND_ANOMALY:
            rows = await self._fetch_rows(self._KIND_ANOMALY, self._max_items)
            for row in rows:
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                if not payload:
                    continue
                try:
                    anomaly = AnomalyDetection.model_validate(payload)
                    if anomaly.anomaly_id not in self._anomalies:
                        self._anomalies[anomaly.anomaly_id] = anomaly
                except Exception:
                    continue
            self._trim_dict(self._anomalies)
            return

        if kind == self._KIND_SPIKE:
            rows = await self._fetch_rows(self._KIND_SPIKE, self._max_items)
            for row in rows:
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                if not payload:
                    continue
                try:
                    spike = IncidentSpike.model_validate(payload)
                    if spike.spike_id not in self._spikes:
                        self._spikes[spike.spike_id] = spike
                except Exception:
                    continue
            self._trim_dict(self._spikes)
            return

        if kind == self._KIND_CASCADE:
            rows = await self._fetch_rows(self._KIND_CASCADE, self._max_items)
            for row in rows:
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                if not payload:
                    continue
                try:
                    cascade = CascadingFailure.model_validate(payload)
                    if cascade.cascade_id not in self._cascades:
                        self._cascades[cascade.cascade_id] = cascade
                except Exception:
                    continue
            self._trim_dict(self._cascades)
            return

        if kind == self._KIND_DEPENDENCY:
            rows = await self._fetch_rows(self._KIND_DEPENDENCY, self._max_items)
            for row in rows:
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                if not payload:
                    continue
                try:
                    dep = ServiceDependency.model_validate(payload)
                    key = f"{dep.source_service}:{dep.target_service}"
                    if key not in self._dependencies:
                        self._dependencies[key] = dep
                except Exception:
                    continue
            self._trim_dict(self._dependencies)
            return

        if kind == self._KIND_DIGEST:
            rows = await self._fetch_rows(self._KIND_DIGEST, self._max_items)
            for row in rows:
                payload = row.get("data") if isinstance(row.get("data"), dict) else {}
                if not payload:
                    continue
                try:
                    digest = IncidentDigest.model_validate(payload)
                    if digest.digest_id not in self._digests:
                        self._digests[digest.digest_id] = digest
                except Exception:
                    continue
            self._trim_dict(self._digests)
            return

    # --- Insight Operations ---

    async def save_insight(self, insight: Insight) -> Insight:
        """Save or update an insight."""
        async with self._lock:
            self._insights[insight.insight_id] = insight
            self._trim_dict(self._insights)
        await self._save_record(
            record_id=insight.insight_id,
            insight_type=insight.insight_type.value,
            severity=insight.severity.value,
            title=insight.title,
            description=insight.description,
            service_name=(insight.affected_services[0] if insight.affected_services else None),
            affected_incident_ids=insight.affected_incident_ids,
            data=self._to_json_dict(insight),
        )
        return insight

    async def get_insight(self, insight_id: str) -> Insight | None:
        """Get an insight by ID."""
        return self._insights.get(insight_id)

    async def get_all_insights(
        self,
        insight_type: InsightType | None = None,
        severity: Severity | None = None,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[Insight]:
        """Get all insights with optional filtering."""
        if not self._insights:
            await self._ensure_loaded(self._KIND_INSIGHT)
        results = []
        for insight in self._insights.values():
            if insight_type and insight.insight_type != insight_type:
                continue
            if severity and insight.severity != severity:
                continue
            if service_name and service_name not in insight.affected_services:
                continue
            results.append(insight)

        # Sort by created_at descending
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]

    async def acknowledge_insight(
        self, insight_id: str, acknowledged_by: str
    ) -> Insight | None:
        """Acknowledge an insight."""
        acked: Insight | None = None
        async with self._lock:
            if insight_id in self._insights:
                insight = self._insights[insight_id]
                insight.is_acknowledged = True
                insight.acknowledged_at = datetime.utcnow()
                insight.acknowledged_by = acknowledged_by
                acked = insight
        if acked:
            await self._save_record(
                record_id=acked.insight_id,
                insight_type=acked.insight_type.value,
                severity=acked.severity.value,
                title=acked.title,
                description=acked.description,
                service_name=(
                    acked.affected_services[0] if acked.affected_services else None
                ),
                affected_incident_ids=acked.affected_incident_ids,
                data=self._to_json_dict(acked),
            )
        return acked

    # --- Pattern Operations ---

    async def save_pattern(self, pattern: RecurringPattern) -> RecurringPattern:
        """Save or update a recurring pattern."""
        async with self._lock:
            self._patterns[pattern.pattern_id] = pattern
            self._trim_dict(self._patterns)
        await self._save_record(
            record_id=pattern.pattern_id,
            insight_type=self._KIND_PATTERN,
            severity=Severity.INFO.value,
            title=f"Recurring pattern: {pattern.service_name}",
            description=pattern.title_pattern,
            service_name=pattern.service_name,
            affected_incident_ids=pattern.affected_incident_ids,
            data=self._to_json_dict(pattern),
        )
        return pattern

    async def get_pattern(self, pattern_id: str) -> RecurringPattern | None:
        """Get a pattern by ID."""
        return self._patterns.get(pattern_id)

    async def get_all_patterns(
        self,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[RecurringPattern]:
        """Get all recurring patterns."""
        if not self._patterns:
            await self._ensure_loaded(self._KIND_PATTERN)
        results = []
        for pattern in self._patterns.values():
            if service_name and pattern.service_name != service_name:
                continue
            results.append(pattern)

        results.sort(key=lambda x: x.last_seen, reverse=True)
        return results[:limit]

    async def save_time_pattern(self, pattern: TimeBasedPattern) -> TimeBasedPattern:
        """Save or update a time-based pattern."""
        async with self._lock:
            self._time_patterns[pattern.pattern_id] = pattern
            self._trim_dict(self._time_patterns)
        await self._save_record(
            record_id=pattern.pattern_id,
            insight_type=self._KIND_TIME_PATTERN,
            severity=Severity.INFO.value,
            title="Time-based pattern",
            description=pattern.pattern_description,
            service_name=pattern.service_name,
            affected_incident_ids=pattern.affected_incident_ids,
            data=self._to_json_dict(pattern),
        )
        return pattern

    async def get_all_time_patterns(
        self,
        service_name: str | None = None,
        limit: int = 100,
    ) -> list[TimeBasedPattern]:
        """Get all time-based patterns."""
        if not self._time_patterns:
            await self._ensure_loaded(self._KIND_TIME_PATTERN)
        results = []
        for pattern in self._time_patterns.values():
            if service_name and pattern.service_name != service_name:
                continue
            results.append(pattern)

        results.sort(key=lambda x: x.confidence, reverse=True)
        return results[:limit]

    # --- Anomaly Operations ---

    async def save_anomaly(self, anomaly: AnomalyDetection) -> AnomalyDetection:
        """Save or update an anomaly."""
        async with self._lock:
            self._anomalies[anomaly.anomaly_id] = anomaly
            self._trim_dict(self._anomalies)
        await self._save_record(
            record_id=anomaly.anomaly_id,
            insight_type=self._KIND_ANOMALY,
            severity=anomaly.severity.value,
            title=f"Anomaly: {anomaly.anomaly_type.value}",
            description=anomaly.description,
            service_name=(anomaly.affected_services[0] if anomaly.affected_services else None),
            affected_incident_ids=anomaly.affected_incident_ids,
            data=self._to_json_dict(anomaly),
        )
        return anomaly

    async def get_anomaly(self, anomaly_id: str) -> AnomalyDetection | None:
        """Get an anomaly by ID."""
        return self._anomalies.get(anomaly_id)

    async def get_all_anomalies(
        self,
        service_name: str | None = None,
        severity: Severity | None = None,
        limit: int = 100,
    ) -> list[AnomalyDetection]:
        """Get all anomalies with optional filtering."""
        if not self._anomalies:
            await self._ensure_loaded(self._KIND_ANOMALY)
        results = []
        for anomaly in self._anomalies.values():
            if severity and anomaly.severity != severity:
                continue
            if service_name and service_name not in anomaly.affected_services:
                continue
            results.append(anomaly)

        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    async def save_spike(self, spike: IncidentSpike) -> IncidentSpike:
        """Save or update a spike detection."""
        async with self._lock:
            self._spikes[spike.spike_id] = spike
            self._trim_dict(self._spikes)
        await self._save_record(
            record_id=spike.spike_id,
            insight_type=self._KIND_SPIKE,
            severity=Severity.HIGH.value,
            title="Incident spike detected",
            description=f"{spike.incident_count} incidents in {spike.window_hours}h window",
            service_name=(spike.affected_services[0] if spike.affected_services else None),
            affected_incident_ids=spike.affected_incident_ids,
            data=self._to_json_dict(spike),
        )
        return spike

    async def get_all_spikes(self, limit: int = 100) -> list[IncidentSpike]:
        """Get all detected spikes."""
        if not self._spikes:
            await self._ensure_loaded(self._KIND_SPIKE)
        results = list(self._spikes.values())
        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    async def save_cascade(self, cascade: CascadingFailure) -> CascadingFailure:
        """Save or update a cascading failure."""
        async with self._lock:
            self._cascades[cascade.cascade_id] = cascade
            self._trim_dict(self._cascades)
        await self._save_record(
            record_id=cascade.cascade_id,
            insight_type=self._KIND_CASCADE,
            severity=Severity.HIGH.value,
            title="Cascading failure detected",
            description=f"Trigger: {cascade.trigger_service}",
            service_name=cascade.trigger_service,
            affected_incident_ids=cascade.affected_incident_ids,
            data=self._to_json_dict(cascade),
        )
        return cascade

    async def get_all_cascades(self, limit: int = 100) -> list[CascadingFailure]:
        """Get all cascading failures."""
        if not self._cascades:
            await self._ensure_loaded(self._KIND_CASCADE)
        results = list(self._cascades.values())
        results.sort(key=lambda x: x.detected_at, reverse=True)
        return results[:limit]

    # --- Dependency Operations ---

    async def save_dependency(self, dependency: ServiceDependency) -> ServiceDependency:
        """Save or update a service dependency."""
        key = f"{dependency.source_service}:{dependency.target_service}"
        async with self._lock:
            self._dependencies[key] = dependency
            self._trim_dict(self._dependencies)
        await self._save_record(
            record_id=f"dependency-{key}",
            insight_type=self._KIND_DEPENDENCY,
            severity=Severity.INFO.value,
            title=f"Dependency: {dependency.source_service} -> {dependency.target_service}",
            description=f"Correlation: {dependency.correlation_strength:.2f}",
            service_name=dependency.source_service,
            affected_incident_ids=[],
            data=self._to_json_dict(dependency),
        )
        return dependency

    async def get_all_dependencies(
        self, service_name: str | None = None
    ) -> list[ServiceDependency]:
        """Get all service dependencies."""
        if not self._dependencies:
            await self._ensure_loaded(self._KIND_DEPENDENCY)
        results = []
        for dep in self._dependencies.values():
            if service_name and (
                dep.source_service != service_name
                and dep.target_service != service_name
            ):
                continue
            results.append(dep)

        results.sort(key=lambda x: x.correlation_strength, reverse=True)
        return results

    # --- Digest Operations ---

    async def save_digest(self, digest: IncidentDigest) -> IncidentDigest:
        """Save or update a digest."""
        async with self._lock:
            self._digests[digest.digest_id] = digest
            self._trim_dict(self._digests)
        await self._save_record(
            record_id=digest.digest_id,
            insight_type=self._KIND_DIGEST,
            severity=Severity.INFO.value,
            title=f"{digest.period.value.title()} incident digest",
            description=f"{digest.period_start.date()} to {digest.period_end.date()}",
            service_name=None,
            affected_incident_ids=[],
            data=self._to_json_dict(digest),
        )
        return digest

    async def get_digest(self, digest_id: str) -> IncidentDigest | None:
        """Get a digest by ID."""
        return self._digests.get(digest_id)

    async def get_latest_digest(
        self, period: str | None = None
    ) -> IncidentDigest | None:
        """Get the latest digest, optionally filtered by period."""
        if not self._digests:
            await self._ensure_loaded(self._KIND_DIGEST)
        digests = list(self._digests.values())
        if period:
            digests = [d for d in digests if d.period.value == period]

        if not digests:
            return None

        return max(digests, key=lambda x: x.generated_at)

    async def get_all_digests(self, limit: int = 50) -> list[IncidentDigest]:
        """Get all digests."""
        if not self._digests:
            await self._ensure_loaded(self._KIND_DIGEST)
        results = list(self._digests.values())
        results.sort(key=lambda x: x.generated_at, reverse=True)
        return results[:limit]

    # --- Utility Methods ---

    def _trim_dict(self, d: dict) -> None:
        """Trim dictionary to max size by removing oldest items."""
        if len(d) > self._max_items:
            # For now, remove first items (oldest by insertion order in Python 3.7+)
            items_to_remove = len(d) - self._max_items
            keys_to_remove = list(d.keys())[:items_to_remove]
            for key in keys_to_remove:
                del d[key]

    async def clear(self) -> None:
        """Clear all stored data (for testing)."""
        async with self._lock:
            self._insights.clear()
            self._patterns.clear()
            self._time_patterns.clear()
            self._anomalies.clear()
            self._spikes.clear()
            self._cascades.clear()
            self._dependencies.clear()
            self._digests.clear()
            self._supabase_loaded.clear()
            self._tenant_id = None

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        return {
            "insights_count": len(self._insights),
            "patterns_count": len(self._patterns),
            "time_patterns_count": len(self._time_patterns),
            "anomalies_count": len(self._anomalies),
            "spikes_count": len(self._spikes),
            "cascades_count": len(self._cascades),
            "dependencies_count": len(self._dependencies),
            "digests_count": len(self._digests),
        }


# Global insights store instance
insights_store = InsightsStore()
