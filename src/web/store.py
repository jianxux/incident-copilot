"""Incident store.

The app historically used an in-memory store for the web dashboard. When
SUPABASE_DB_ENABLED=true, we persist incidents and context cards to Supabase
Postgres while keeping the same in-process SSE subscriber behavior.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from ..config import get_settings
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
    ) -> StoredIncident:
        async with self._lock:
            incident = StoredIncident(
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity,
                status="processing",
                triggered_at=triggered_at,
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
                }
            )

            return incident

    async def complete_incident(self, incident_id: str, context_card: ContextCard):
        async with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                return None

            incident.status = "completed"
            incident.processed_at = datetime.now(UTC)
            incident.context_card = context_card

            await self._notify_subscribers(
                {
                    "type": "incident_completed",
                    "incident_id": incident_id,
                    "status": "completed",
                    "assembly_time_ms": context_card.assembly_time_ms,
                }
            )
            return incident

    async def fail_incident(self, incident_id: str, error_message: str):
        async with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                return None

            incident.status = "error"
            incident.processed_at = datetime.now(UTC)
            incident.error_message = error_message

            await self._notify_subscribers(
                {
                    "type": "incident_error",
                    "incident_id": incident_id,
                    "status": "error",
                    "error": error_message,
                }
            )
            return incident

    async def get_incident(self, incident_id: str) -> StoredIncident | None:
        return self._incidents.get(incident_id)

    async def get_all_incidents(self) -> list[StoredIncident]:
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

    async def _ensure_tenant(self) -> str:
        if self._tenant_id:
            return self._tenant_id

        # Server-side usage: use admin client and a default tenant.
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        tenant = await db.ensure_tenant(slug="default", name="Default Tenant")
        self._tenant_id = tenant["id"]
        return self._tenant_id

    @staticmethod
    def _row_to_stored(row: dict, card_row: dict | None = None) -> StoredIncident:
        ctx = None
        if card_row and card_row.get("data"):
            try:
                ctx = ContextCard.model_validate(card_row["data"])
            except Exception:
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
        except Exception:
            severity = Severity.MEDIUM

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
        )

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
    ) -> StoredIncident:
        from ..db.supabase_db import get_db

        async with self._lock:
            tenant_id = await self._ensure_tenant()
            db = get_db(use_admin=True)

            await db.upsert_processing_incident(
                tenant_id=tenant_id,
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity.value,
                status="processing",
                triggered_at=triggered_at.astimezone(UTC).isoformat(),
            )

            await self._notify_subscribers(
                {
                    "type": "new_incident",
                    "incident_id": incident_id,
                    "title": title,
                    "service": service_name,
                    "severity": severity.value,
                    "status": "processing",
                }
            )

            return StoredIncident(
                incident_id=incident_id,
                title=title,
                service_name=service_name,
                severity=severity,
                status="processing",
                triggered_at=triggered_at,
            )

    async def complete_incident(self, incident_id: str, context_card: ContextCard):
        from ..db.supabase_db import get_db

        async with self._lock:
            tenant_id = await self._ensure_tenant()
            db = get_db(use_admin=True)

            now = datetime.now(UTC)
            # Update incident row
            row = await db.get_processing_incident(
                tenant_id=tenant_id, incident_id=incident_id
            )
            if not row:
                # Create minimal row if missing
                row = await db.upsert_processing_incident(
                    tenant_id=tenant_id,
                    incident_id=incident_id,
                    title=context_card.title,
                    service_name=context_card.service_name,
                    severity=context_card.severity.value,
                    status="completed",
                    processed_at=now.isoformat(),
                    triggered_at=context_card.triggered_at.astimezone(UTC).isoformat(),
                )
            else:
                await db.upsert_processing_incident(
                    tenant_id=tenant_id,
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
                )

            # Insert context card row
            card_payload = context_card.model_dump(mode="json")
            await db.create_context_card(
                incident_id=incident_id,
                tenant_id=tenant_id,
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

            return await self.get_incident(incident_id)

    async def fail_incident(self, incident_id: str, error_message: str):
        from ..db.supabase_db import get_db

        async with self._lock:
            tenant_id = await self._ensure_tenant()
            db = get_db(use_admin=True)

            row = await db.get_processing_incident(
                tenant_id=tenant_id, incident_id=incident_id
            )
            title = row.get("title") if row else incident_id
            service = row.get("service") if row else "unknown"
            sev = row.get("severity") if row else Severity.MEDIUM.value

            await db.upsert_processing_incident(
                tenant_id=tenant_id,
                incident_id=incident_id,
                title=title,
                service_name=service,
                severity=sev,
                status="error",
                triggered_at=row.get("triggered_at") if row else None,
                processed_at=datetime.now(UTC).isoformat(),
                error_message=error_message,
            )

            await self._notify_subscribers(
                {
                    "type": "incident_error",
                    "incident_id": incident_id,
                    "status": "error",
                    "error": error_message,
                }
            )

            return await self.get_incident(incident_id)

    async def get_incident(self, incident_id: str) -> StoredIncident | None:
        from ..db.supabase_db import get_db

        tenant_id = await self._ensure_tenant()
        db = get_db(use_admin=True)

        row = await db.get_processing_incident(tenant_id=tenant_id, incident_id=incident_id)
        if not row:
            return None

        card_row = None
        try:
            card_row = await db.get_context_card(incident_id)
        except Exception:
            card_row = None

        return self._row_to_stored(row, card_row)

    async def get_all_incidents(self) -> list[StoredIncident]:
        from ..db.supabase_db import get_db

        tenant_id = await self._ensure_tenant()
        db = get_db(use_admin=True)

        rows = await db.list_processing_incidents(
            tenant_id=tenant_id, limit=self._max_incidents, offset=0
        )

        # Avoid N+1 for context cards for now; dashboard list doesn’t render full card.
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


def get_incident_store() -> _BaseIncidentStore:
    settings = get_settings()

    if is_supabase_db_enabled():
        logger.info("incident_store_backend", backend="supabase")
        return SupabaseIncidentStore(max_incidents=100)

    logger.info("incident_store_backend", backend="memory")
    return InMemoryIncidentStore(max_incidents=100)


# Global incident store instance
incident_store = get_incident_store()
