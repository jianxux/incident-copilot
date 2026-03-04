"""Incident store.

The app historically used an in-memory store for the web dashboard. When
SUPABASE_DB_ENABLED=true, we persist incidents and context cards to Supabase
Postgres while keeping the same in-process SSE subscriber behavior.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from ..models import ContextCard, Severity
from ..supabase_client import is_supabase_db_enabled

logger = structlog.get_logger()


@dataclass
class StoredIncident:
    """Wrapper for stored incidents with additional metadata."""

    incident_id: str
    title: str
    service_name: str
    severity: Severity
    status: str  # "processing", "completed", "error"
    triggered_at: datetime
    processed_at: datetime | None = None
    context_card: ContextCard | None = None
    error_message: str | None = None
    source: str = "manual"
    source_url: str | None = None
    source_id: str | None = None
    description: str | None = None
    metadata: dict = field(default_factory=dict)


class _BaseIncidentStore:
    """Base store with shared SSE subscriber behavior."""

    def __init__(self, max_incidents: int = 100):
        self._max_incidents = max_incidents
        self._subscribers: list[asyncio.Queue] = []

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def _notify_subscribers(self, event: dict):
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
        source: str = "manual",
        source_url: str | None = None,
        source_id: str | None = None,
        metadata: dict | None = None,
        tenant_id: str | None = None,
        description: str | None = None,
    ) -> StoredIncident:
        raise NotImplementedError

    async def complete_incident(
        self,
        incident_id: str,
        context_card: ContextCard,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        raise NotImplementedError

    async def fail_incident(
        self,
        incident_id: str,
        error_message: str,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        raise NotImplementedError

    async def get_incident(
        self,
        incident_id: str,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        raise NotImplementedError

    async def get_all_incidents(
        self,
        tenant_id: str | None = None,
    ) -> list[StoredIncident]:
        raise NotImplementedError

    async def get_stats(self) -> dict:
        raise NotImplementedError


class InMemoryIncidentStore(_BaseIncidentStore):
    """Thread-safe in-memory store for incidents."""

    def __init__(self, max_incidents: int = 100):
        super().__init__(max_incidents=max_incidents)
        self._incidents: dict[str, StoredIncident] = {}
        self._order: list[str] = []  # Track insertion order (newest first)
        self._lock = asyncio.Lock()

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
        source: str = "manual",
        source_url: str | None = None,
        source_id: str | None = None,
        metadata: dict | None = None,
        tenant_id: str | None = None,
        description: str | None = None,
    ) -> StoredIncident:
        _ = tenant_id
        async with self._lock:
            incident = StoredIncident(
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity,
                status="processing",
                triggered_at=triggered_at,
                source=source,
                source_url=source_url,
                source_id=source_id or incident_id,
                description=description,
                metadata=metadata or {},
            )
            self._incidents[incident_id] = incident
            self._order.insert(0, incident_id)

            while len(self._order) > self._max_incidents:
                old_id = self._order.pop()
                self._incidents.pop(old_id, None)

            await self._notify_subscribers(
                {
                    "type": "new_incident",
                    "incident_id": incident_id,
                    "title": title,
                    "service": service_name,
                    "severity": severity.value,
                    "status": "processing",
                    "source": source,
                    "source_url": source_url,
                }
            )

            return incident

    async def complete_incident(
        self,
        incident_id: str,
        context_card: ContextCard,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        _ = tenant_id
        async with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                return None

            incident.status = "completed"
            incident.processed_at = datetime.now(UTC)
            incident.context_card = context_card
            if metadata:
                incident.metadata = {**incident.metadata, **metadata}

            await self._notify_subscribers(
                {
                    "type": "incident_completed",
                    "incident_id": incident_id,
                    "status": "completed",
                    "assembly_time_ms": context_card.assembly_time_ms,
                }
            )
            return incident

    async def fail_incident(
        self,
        incident_id: str,
        error_message: str,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        _ = tenant_id
        async with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                return None

            incident.status = "error"
            incident.processed_at = datetime.now(UTC)
            incident.error_message = error_message
            merged_metadata = dict(incident.metadata)
            if metadata:
                merged_metadata.update(metadata)
            if "error" not in merged_metadata:
                merged_metadata["error"] = error_message
            incident.metadata = merged_metadata

            await self._notify_subscribers(
                {
                    "type": "incident_error",
                    "incident_id": incident_id,
                    "status": "error",
                    "error": error_message,
                }
            )
            return incident

    async def get_incident(
        self,
        incident_id: str,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        _ = tenant_id
        return self._incidents.get(incident_id)

    async def get_all_incidents(
        self,
        tenant_id: str | None = None,
    ) -> list[StoredIncident]:
        _ = tenant_id
        return [self._incidents[iid] for iid in self._order if iid in self._incidents]

    async def get_stats(self) -> dict:
        total = len(self._incidents)
        by_status = {"processing": 0, "completed": 0, "error": 0}
        by_severity = {s.value: 0 for s in Severity}

        for incident in self._incidents.values():
            by_status[incident.status] = by_status.get(incident.status, 0) + 1
            by_severity[incident.severity.value] = (
                by_severity.get(incident.severity.value, 0) + 1
            )

        return {"total": total, "by_status": by_status, "by_severity": by_severity}


class SupabaseIncidentStore(_BaseIncidentStore):
    """Supabase-backed incident store.

    We still keep SSE subscribers in-process; persistence is via Supabase.
    """

    def __init__(self, max_incidents: int = 100):
        super().__init__(max_incidents=max_incidents)
        self._lock = asyncio.Lock()
        self._tenant_id: str | None = None
        self._incident_tenants: dict[str, str] = {}

    async def _ensure_tenant(self) -> str:
        if self._tenant_id:
            return self._tenant_id

        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        tenant = await db.ensure_tenant(slug="default", name="Default Tenant")
        self._tenant_id = tenant["id"]
        return self._tenant_id

    async def _resolve_tenant(
        self,
        *,
        incident_id: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        if tenant_id:
            return tenant_id
        if incident_id and incident_id in self._incident_tenants:
            return self._incident_tenants[incident_id]
        return await self._ensure_tenant()

    @staticmethod
    def _row_to_stored(row: dict, card_row: dict | None = None) -> StoredIncident:
        ctx = None
        if card_row and card_row.get("data"):
            try:
                ctx = ContextCard.model_validate(card_row["data"])
            except Exception as e:
                logger.warning(
                    "context_card_validation_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    incident_id=row.get("id"),
                )
                ctx = None

        triggered_at = row.get("triggered_at")
        if isinstance(triggered_at, str):
            triggered_at = datetime.fromisoformat(triggered_at.replace("Z", "+00:00"))

        processed_at = row.get("processed_at")
        if isinstance(processed_at, str):
            processed_at = datetime.fromisoformat(processed_at.replace("Z", "+00:00"))

        sev = row.get("severity") or "medium"
        try:
            severity = Severity(sev)
        except Exception as e:
            logger.warning(
                "incident_severity_parse_failed",
                error=str(e),
                error_type=type(e).__name__,
                severity=sev,
                incident_id=row.get("id"),
            )
            severity = Severity.MEDIUM

        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        return StoredIncident(
            incident_id=row["id"],
            title=row.get("title") or "",
            service_name=row.get("service") or "",
            severity=severity,
            status=row.get("status") or "processing",
            triggered_at=triggered_at or datetime.now(UTC),
            processed_at=processed_at,
            context_card=ctx,
            error_message=row.get("error_message"),
            source=row.get("source") or "manual",
            source_url=row.get("source_url"),
            source_id=row.get("source_id"),
            description=row.get("description"),
            metadata=metadata,
        )

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
        source: str = "manual",
        source_url: str | None = None,
        source_id: str | None = None,
        metadata: dict | None = None,
        tenant_id: str | None = None,
        description: str | None = None,
    ) -> StoredIncident:
        from ..db.supabase_db import get_db

        async with self._lock:
            resolved_tenant_id = await self._resolve_tenant(
                incident_id=incident_id, tenant_id=tenant_id
            )
            self._incident_tenants[incident_id] = resolved_tenant_id
            db = get_db(use_admin=True)

            await db.upsert_processing_incident(
                tenant_id=resolved_tenant_id,
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity.value,
                status="processing",
                triggered_at=triggered_at.astimezone(UTC).isoformat(),
                source=source,
                source_url=source_url,
                source_id=source_id or incident_id,
                metadata=metadata or {},
                description=description,
            )

            await self._notify_subscribers(
                {
                    "type": "new_incident",
                    "incident_id": incident_id,
                    "title": title,
                    "service": service_name,
                    "severity": severity.value,
                    "status": "processing",
                    "source": source,
                    "source_url": source_url,
                }
            )

            return StoredIncident(
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity,
                status="processing",
                triggered_at=triggered_at,
                source=source,
                source_url=source_url,
                source_id=source_id or incident_id,
                description=description,
                metadata=metadata or {},
            )

    async def complete_incident(
        self,
        incident_id: str,
        context_card: ContextCard,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        from ..db.supabase_db import get_db

        async with self._lock:
            resolved_tenant_id = await self._resolve_tenant(
                incident_id=incident_id, tenant_id=tenant_id
            )
            db = get_db(use_admin=True)

            now = datetime.now(UTC)
            row = await db.get_processing_incident(
                tenant_id=resolved_tenant_id,
                incident_id=incident_id,
            )
            if not row:
                await db.upsert_processing_incident(
                    tenant_id=resolved_tenant_id,
                    incident_id=incident_id,
                    title=context_card.title,
                    service_name=context_card.service_name,
                    severity=context_card.severity.value,
                    status="completed",
                    processed_at=now.isoformat(),
                    triggered_at=context_card.triggered_at.astimezone(UTC).isoformat(),
                    source="manual",
                    source_id=incident_id,
                    metadata=metadata or {},
                )
            else:
                existing_metadata = row.get("metadata") or {}
                if not isinstance(existing_metadata, dict):
                    existing_metadata = {}
                merged_metadata = {**existing_metadata}
                if metadata:
                    merged_metadata.update(metadata)

                await db.upsert_processing_incident(
                    tenant_id=resolved_tenant_id,
                    incident_id=incident_id,
                    title=row.get("title") or context_card.title,
                    service_name=row.get("service") or context_card.service_name,
                    severity=row.get("severity") or context_card.severity.value,
                    status="completed",
                    triggered_at=(
                        row.get("triggered_at")
                        or context_card.triggered_at.astimezone(UTC).isoformat()
                    ),
                    processed_at=now.isoformat(),
                    source=row.get("source") or "manual",
                    source_url=row.get("source_url"),
                    source_id=row.get("source_id") or incident_id,
                    metadata=merged_metadata,
                )

            card_payload = context_card.model_dump(mode="json")
            await db.create_context_card(
                incident_id=incident_id,
                tenant_id=resolved_tenant_id,
                data=card_payload,
                assembly_time_ms=context_card.assembly_time_ms,
            )

            await self._notify_subscribers(
                {
                    "type": "incident_completed",
                    "incident_id": incident_id,
                    "status": "completed",
                    "assembly_time_ms": context_card.assembly_time_ms,
                }
            )

            return await self.get_incident(incident_id, tenant_id=resolved_tenant_id)

    async def fail_incident(
        self,
        incident_id: str,
        error_message: str,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        from ..db.supabase_db import get_db

        async with self._lock:
            resolved_tenant_id = await self._resolve_tenant(
                incident_id=incident_id, tenant_id=tenant_id
            )
            db = get_db(use_admin=True)

            row = await db.get_processing_incident(
                tenant_id=resolved_tenant_id,
                incident_id=incident_id,
            )
            title = row.get("title") if row else incident_id
            service = row.get("service") if row else "unknown"
            sev = row.get("severity") if row else Severity.MEDIUM.value

            existing_metadata = row.get("metadata") if row else {}
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}
            merged_metadata = {**existing_metadata}
            if metadata:
                merged_metadata.update(metadata)
            if "error" not in merged_metadata:
                merged_metadata["error"] = error_message

            await db.upsert_processing_incident(
                tenant_id=resolved_tenant_id,
                incident_id=incident_id,
                title=title,
                service_name=service,
                severity=sev,
                status="error",
                triggered_at=row.get("triggered_at") if row else None,
                processed_at=datetime.now(UTC).isoformat(),
                error_message=error_message,
                source=row.get("source") if row else "manual",
                source_url=row.get("source_url") if row else None,
                source_id=row.get("source_id") if row else incident_id,
                metadata=merged_metadata,
            )

            await self._notify_subscribers(
                {
                    "type": "incident_error",
                    "incident_id": incident_id,
                    "status": "error",
                    "error": error_message,
                }
            )

            return await self.get_incident(incident_id, tenant_id=resolved_tenant_id)

    async def get_incident(
        self,
        incident_id: str,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        from ..db.supabase_db import get_db

        resolved_tenant_id = await self._resolve_tenant(
            incident_id=incident_id, tenant_id=tenant_id
        )
        db = get_db(use_admin=True)

        row = await db.get_processing_incident(
            tenant_id=resolved_tenant_id,
            incident_id=incident_id,
        )
        if not row:
            return None

        card_row = None
        try:
            card_row = await db.get_context_card(incident_id)
        except Exception as e:
            logger.warning(
                "context_card_fetch_failed",
                error=str(e),
                error_type=type(e).__name__,
                incident_id=incident_id,
            )
            card_row = None

        return self._row_to_stored(row, card_row)

    async def get_all_incidents(
        self,
        tenant_id: str | None = None,
    ) -> list[StoredIncident]:
        from ..db.supabase_db import get_db

        resolved_tenant_id = await self._resolve_tenant(tenant_id=tenant_id)
        db = get_db(use_admin=True)

        rows = await db.list_processing_incidents(
            tenant_id=resolved_tenant_id,
            limit=self._max_incidents,
            offset=0,
        )
        return [self._row_to_stored(r, None) for r in rows]

    async def get_stats(self) -> dict:
        incidents = await self.get_all_incidents()
        total = len(incidents)
        by_status = {"processing": 0, "completed": 0, "error": 0}
        by_severity = {s.value: 0 for s in Severity}

        for incident in incidents:
            by_status[incident.status] = by_status.get(incident.status, 0) + 1
            by_severity[incident.severity.value] = (
                by_severity.get(incident.severity.value, 0) + 1
            )

        return {"total": total, "by_status": by_status, "by_severity": by_severity}


class HybridIncidentStore(_BaseIncidentStore):
    """Hybrid store that keeps in-memory state with best-effort Supabase persistence."""

    def __init__(self, max_incidents: int = 100):
        super().__init__(max_incidents=max_incidents)
        self._memory = InMemoryIncidentStore(max_incidents=max_incidents)
        self._supabase = SupabaseIncidentStore(max_incidents=max_incidents)

    async def subscribe(self) -> asyncio.Queue:
        return await self._memory.subscribe()

    async def unsubscribe(self, queue: asyncio.Queue):
        await self._memory.unsubscribe(queue)

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
        source: str = "manual",
        source_url: str | None = None,
        source_id: str | None = None,
        metadata: dict | None = None,
        tenant_id: str | None = None,
        description: str | None = None,
    ) -> StoredIncident:
        incident = await self._memory.add_incident(
            incident_id=incident_id,
            title=title,
            service_name=service_name,
            severity=severity,
            triggered_at=triggered_at,
            source=source,
            source_url=source_url,
            source_id=source_id,
            metadata=metadata,
            tenant_id=tenant_id,
            description=description,
        )
        try:
            await self._supabase.add_incident(
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity,
                triggered_at=triggered_at,
                source=source,
                source_url=source_url,
                source_id=source_id,
                metadata=metadata,
                tenant_id=tenant_id,
                description=description,
            )
        except Exception as e:
            logger.warning(
                "hybrid_store_supabase_add_failed",
                incident_id=incident_id,
                error=str(e),
                error_type=type(e).__name__,
            )
        return incident

    async def complete_incident(
        self,
        incident_id: str,
        context_card: ContextCard,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        memory_result = await self._memory.complete_incident(
            incident_id=incident_id,
            context_card=context_card,
            metadata=metadata,
            tenant_id=tenant_id,
        )
        try:
            supabase_result = await self._supabase.complete_incident(
                incident_id=incident_id,
                context_card=context_card,
                metadata=metadata,
                tenant_id=tenant_id,
            )
            return supabase_result or memory_result
        except Exception as e:
            logger.warning(
                "hybrid_store_supabase_complete_failed",
                incident_id=incident_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return memory_result

    async def fail_incident(
        self,
        incident_id: str,
        error_message: str,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        memory_result = await self._memory.fail_incident(
            incident_id=incident_id,
            error_message=error_message,
            metadata=metadata,
            tenant_id=tenant_id,
        )
        try:
            supabase_result = await self._supabase.fail_incident(
                incident_id=incident_id,
                error_message=error_message,
                metadata=metadata,
                tenant_id=tenant_id,
            )
            return supabase_result or memory_result
        except Exception as e:
            logger.warning(
                "hybrid_store_supabase_fail_failed",
                incident_id=incident_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return memory_result

    async def get_incident(
        self,
        incident_id: str,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        memory_incident = await self._memory.get_incident(incident_id, tenant_id=tenant_id)
        try:
            supabase_incident = await self._supabase.get_incident(incident_id, tenant_id=tenant_id)
            return supabase_incident or memory_incident
        except Exception as e:
            logger.warning(
                "hybrid_store_supabase_get_failed",
                incident_id=incident_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return memory_incident

    async def get_all_incidents(
        self,
        tenant_id: str | None = None,
    ) -> list[StoredIncident]:
        memory_incidents = await self._memory.get_all_incidents(tenant_id=tenant_id)
        merged_by_id: dict[str, StoredIncident] = {
            incident.incident_id: incident for incident in memory_incidents
        }

        try:
            supabase_incidents = await self._supabase.get_all_incidents(tenant_id=tenant_id)
            for incident in supabase_incidents:
                merged_by_id[incident.incident_id] = incident
        except Exception as e:
            logger.warning(
                "hybrid_store_supabase_list_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return memory_incidents

        return sorted(
            merged_by_id.values(),
            key=lambda incident: incident.triggered_at,
            reverse=True,
        )

    async def get_stats(self) -> dict:
        incidents = await self.get_all_incidents()
        total = len(incidents)
        by_status = {"processing": 0, "completed": 0, "error": 0}
        by_severity = {s.value: 0 for s in Severity}

        for incident in incidents:
            by_status[incident.status] = by_status.get(incident.status, 0) + 1
            by_severity[incident.severity.value] = (
                by_severity.get(incident.severity.value, 0) + 1
            )

        return {"total": total, "by_status": by_status, "by_severity": by_severity}



class DatabaseIncidentStore(_BaseIncidentStore):
    """SQLAlchemy/asyncpg-backed incident store.

    Persists incidents to PostgreSQL using async SQLAlchemy while keeping
    the same in-process SSE subscriber behavior.
    """

    def __init__(self, database_url: str, max_incidents: int = 100):
        super().__init__(max_incidents=max_incidents)
        from .models import create_engine_and_session

        self._engine, self._session_factory = create_engine_and_session(database_url)
        self._lock = asyncio.Lock()

    async def init_db(self) -> None:
        """Create tables if they don't exist."""
        from .models import Base

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
        source: str = "manual",
        source_url: str | None = None,
        source_id: str | None = None,
        metadata: dict | None = None,
        tenant_id: str | None = None,
        description: str | None = None,
    ) -> StoredIncident:
        from .models import IncidentRow

        async with self._lock:
            async with self._session_factory() as session:
                row = IncidentRow(
                    incident_id=incident_id,
                    title=title,
                    service_name=service_name,
                    severity=severity.value,
                    status="processing",
                    triggered_at=triggered_at,
                )
                session.add(row)
                await session.commit()

            incident = StoredIncident(
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity,
                status="processing",
                triggered_at=triggered_at,
                source=source,
                source_url=source_url,
                source_id=source_id or incident_id,
                description=description,
                metadata=metadata or {},
            )

            await self._notify_subscribers(
                {
                    "type": "new_incident",
                    "incident_id": incident_id,
                    "title": title,
                    "service": service_name,
                    "severity": severity.value,
                    "status": "processing",
                    "source": source,
                    "source_url": source_url,
                }
            )
            return incident

    async def complete_incident(
        self,
        incident_id: str,
        context_card: ContextCard,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        from .models import IncidentRow
        from sqlalchemy import select

        async with self._lock:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(IncidentRow).where(IncidentRow.incident_id == incident_id)
                )
                row = result.scalar_one_or_none()
                if not row:
                    return None

                now = datetime.now(UTC)
                row.status = "completed"
                row.processed_at = now
                row.context_card = context_card.model_dump(mode="json")
                await session.commit()

                incident = StoredIncident(
                    incident_id=row.incident_id,
                    title=row.title,
                    service_name=row.service_name,
                    severity=Severity(row.severity),
                    status="completed",
                    triggered_at=row.triggered_at,
                    processed_at=now,
                    context_card=context_card,
                    metadata=metadata or {},
                )

            await self._notify_subscribers(
                {
                    "type": "incident_completed",
                    "incident_id": incident_id,
                    "status": "completed",
                    "assembly_time_ms": context_card.assembly_time_ms,
                }
            )
            return incident

    async def fail_incident(
        self,
        incident_id: str,
        error_message: str,
        metadata: dict | None = None,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        from .models import IncidentRow
        from sqlalchemy import select

        async with self._lock:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(IncidentRow).where(IncidentRow.incident_id == incident_id)
                )
                row = result.scalar_one_or_none()
                if not row:
                    return None

                now = datetime.now(UTC)
                row.status = "error"
                row.processed_at = now
                row.error_message = error_message
                await session.commit()

                incident = StoredIncident(
                    incident_id=row.incident_id,
                    title=row.title,
                    service_name=row.service_name,
                    severity=Severity(row.severity),
                    status="error",
                    triggered_at=row.triggered_at,
                    processed_at=now,
                    error_message=error_message,
                    metadata=metadata or {},
                )

            await self._notify_subscribers(
                {
                    "type": "incident_error",
                    "incident_id": incident_id,
                    "status": "error",
                    "error": error_message,
                }
            )
            return incident

    async def get_incident(
        self,
        incident_id: str,
        tenant_id: str | None = None,
    ) -> StoredIncident | None:
        from .models import IncidentRow
        from sqlalchemy import select

        async with self._session_factory() as session:
            result = await session.execute(
                select(IncidentRow).where(IncidentRow.incident_id == incident_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            ctx = None
            if row.context_card:
                try:
                    ctx = ContextCard.model_validate(row.context_card)
                except Exception:
                    ctx = None

            return StoredIncident(
                incident_id=row.incident_id,
                title=row.title,
                service_name=row.service_name,
                severity=Severity(row.severity),
                status=row.status,
                triggered_at=row.triggered_at,
                processed_at=row.processed_at,
                context_card=ctx,
                error_message=row.error_message,
            )

    async def get_all_incidents(
        self,
        tenant_id: str | None = None,
    ) -> list[StoredIncident]:
        from .models import IncidentRow
        from sqlalchemy import select

        async with self._session_factory() as session:
            result = await session.execute(
                select(IncidentRow).order_by(IncidentRow.triggered_at.desc()).limit(self._max_incidents)
            )
            rows = result.scalars().all()

            incidents = []
            for row in rows:
                ctx = None
                if row.context_card:
                    try:
                        ctx = ContextCard.model_validate(row.context_card)
                    except Exception:
                        ctx = None

                incidents.append(
                    StoredIncident(
                        incident_id=row.incident_id,
                        title=row.title,
                        service_name=row.service_name,
                        severity=Severity(row.severity),
                        status=row.status,
                        triggered_at=row.triggered_at,
                        processed_at=row.processed_at,
                        context_card=ctx,
                        error_message=row.error_message,
                    )
                )
            return incidents

    async def get_stats(self) -> dict:
        incidents = await self.get_all_incidents()
        total = len(incidents)
        by_status = {"processing": 0, "completed": 0, "error": 0}
        by_severity = {s.value: 0 for s in Severity}

        for incident in incidents:
            by_status[incident.status] = by_status.get(incident.status, 0) + 1
            by_severity[incident.severity.value] = (
                by_severity.get(incident.severity.value, 0) + 1
            )

        return {"total": total, "by_status": by_status, "by_severity": by_severity}


def get_incident_store() -> _BaseIncidentStore:
    """Create the appropriate incident store based on configuration.

    Priority:
    1. Supabase DB if SUPABASE_DB_ENABLED=true -> HybridIncidentStore
    2. DATABASE_URL if set and non-empty -> DatabaseIncidentStore (SQLAlchemy + asyncpg)
    3. Fallback -> InMemoryIncidentStore
    """
    if is_supabase_db_enabled():
        logger.info("incident_store_backend", backend="hybrid")
        return HybridIncidentStore(max_incidents=100)

    # Check for DATABASE_URL via config
    try:
        from ..config import get_settings

        settings = get_settings()
        database_url = settings.database_url
        if database_url:
            logger.info("incident_store_backend", backend="database")
            return DatabaseIncidentStore(database_url=database_url, max_incidents=100)
    except Exception as exc:
        logger.warning(
            "database_store_init_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )

    logger.info("incident_store_backend", backend="memory")
    return InMemoryIncidentStore(max_incidents=100)


incident_store = get_incident_store()
