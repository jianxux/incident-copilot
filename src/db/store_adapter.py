"""Adapter that wraps SupabaseDB to match the in-memory IncidentStore interface.

When supabase_db_enabled=True, routes can use this instead of the in-memory store.
The adapter preserves the SSE subscriber mechanism from the in-memory store while
persisting data to Supabase PostgreSQL.
"""

from datetime import UTC, datetime

import structlog

from ..models import ContextCard, Severity
from ..supabase_client import is_supabase_db_enabled
from ..web.store import IncidentStore, StoredIncident
from .supabase_db import get_db

logger = structlog.get_logger()


class SupabaseIncidentStore(IncidentStore):
    """IncidentStore backed by Supabase, with in-memory SSE fanout.

    Inherits from IncidentStore so it's a drop-in replacement.
    DB writes go to Supabase; SSE subscribers still work via in-memory queues.
    """

    def __init__(self, tenant_id: str, max_incidents: int = 100):
        super().__init__(max_incidents=max_incidents)
        self.tenant_id = tenant_id
        self._db = get_db(use_admin=True)

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
    ) -> StoredIncident:
        """Add incident to both Supabase and in-memory (for SSE)."""
        # Persist to DB
        try:
            await self._db.create_incident(
                tenant_id=self.tenant_id,
                title=title,
                source="webhook",
                source_id=incident_id,
                severity=severity.value,
                status="triggered",
                service=service_name,
            )
        except Exception as e:
            logger.error("supabase_create_incident_failed", error=str(e))

        # Also maintain in-memory for SSE
        return await super().add_incident(
            incident_id, title, service_name, severity, triggered_at
        )

    async def complete_incident(
        self,
        incident_id: str,
        context_card: ContextCard,
    ) -> StoredIncident | None:
        """Mark completed in both DB and memory."""
        try:
            # Find the DB incident by source_id
            incidents = await self._db.list_incidents(self.tenant_id, limit=1)
            # Update status
            for inc in incidents:
                if inc.get("source_id") == incident_id:
                    await self._db.update_incident(
                        inc["id"],
                        status="resolved",
                        resolved_at=datetime.now(UTC).isoformat(),
                    )
                    # Store context card
                    await self._db.create_context_card(
                        incident_id=inc["id"],
                        tenant_id=self.tenant_id,
                        data=context_card.model_dump(mode="json"),
                        generation_time_ms=context_card.assembly_time_ms,
                    )
                    break
        except Exception as e:
            logger.error("supabase_complete_incident_failed", error=str(e))

        return await super().complete_incident(incident_id, context_card)

    async def fail_incident(
        self,
        incident_id: str,
        error_message: str,
    ) -> StoredIncident | None:
        """Mark failed in DB and memory."""
        try:
            incidents = await self._db.list_incidents(self.tenant_id, limit=50)
            for inc in incidents:
                if inc.get("source_id") == incident_id:
                    await self._db.update_incident(
                        inc["id"],
                        status="resolved",
                        metadata={"error": error_message},
                    )
                    break
        except Exception as e:
            logger.error("supabase_fail_incident_failed", error=str(e))

        return await super().fail_incident(incident_id, error_message)


def get_incident_store(tenant_id: str | None = None) -> IncidentStore:
    """Get the appropriate incident store based on configuration.

    Returns SupabaseIncidentStore if DB is enabled, else the global in-memory store.
    """
    if is_supabase_db_enabled() and tenant_id:
        return SupabaseIncidentStore(tenant_id=tenant_id)

    # Fall back to the global in-memory store
    from ..web.store import incident_store

    return incident_store
