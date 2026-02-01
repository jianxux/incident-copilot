"""In-memory incident store for tracking processed incidents."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..models import ContextCard, Severity


@dataclass
class StoredIncident:
    """Wrapper for stored incidents with additional metadata."""

    incident_id: str
    title: str
    service_name: str
    severity: Severity
    status: str  # "processing", "completed", "error"
    triggered_at: datetime
    processed_at: Optional[datetime] = None
    context_card: Optional[ContextCard] = None
    error_message: Optional[str] = None


class IncidentStore:
    """
    Thread-safe in-memory store for incidents.

    Supports real-time updates via SSE subscribers.
    """

    def __init__(self, max_incidents: int = 100):
        self._incidents: dict[str, StoredIncident] = {}
        self._order: list[str] = []  # Track insertion order
        self._max_incidents = max_incidents
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def add_incident(
        self,
        incident_id: str,
        title: str,
        service_name: str,
        severity: Severity,
        triggered_at: datetime,
    ) -> StoredIncident:
        """Add a new incident in 'processing' state."""
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
            self._order.insert(0, incident_id)  # Newest first

            # Trim if over max
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

    async def complete_incident(
        self,
        incident_id: str,
        context_card: ContextCard,
    ) -> Optional[StoredIncident]:
        """Mark incident as completed with context card."""
        async with self._lock:
            if incident_id not in self._incidents:
                return None

            incident = self._incidents[incident_id]
            incident.status = "completed"
            incident.processed_at = datetime.utcnow()
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

    async def fail_incident(
        self,
        incident_id: str,
        error_message: str,
    ) -> Optional[StoredIncident]:
        """Mark incident as failed."""
        async with self._lock:
            if incident_id not in self._incidents:
                return None

            incident = self._incidents[incident_id]
            incident.status = "error"
            incident.processed_at = datetime.utcnow()
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

    async def get_incident(self, incident_id: str) -> Optional[StoredIncident]:
        """Get a single incident by ID."""
        return self._incidents.get(incident_id)

    async def get_all_incidents(self) -> list[StoredIncident]:
        """Get all incidents, newest first."""
        return [self._incidents[id] for id in self._order if id in self._incidents]

    async def get_stats(self) -> dict:
        """Get summary statistics."""
        total = len(self._incidents)
        by_status = {"processing": 0, "completed": 0, "error": 0}
        by_severity = {s.value: 0 for s in Severity}

        for incident in self._incidents.values():
            by_status[incident.status] = by_status.get(incident.status, 0) + 1
            by_severity[incident.severity.value] = (
                by_severity.get(incident.severity.value, 0) + 1
            )

        return {
            "total": total,
            "by_status": by_status,
            "by_severity": by_severity,
        }

    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to real-time updates."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from updates."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def _notify_subscribers(self, event: dict):
        """Notify all subscribers of an event."""
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Skip slow consumers


# Global incident store instance
incident_store = IncidentStore()
