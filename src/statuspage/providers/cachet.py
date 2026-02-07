"""Cachet (Self-Hosted) Provider."""

from datetime import datetime

from ..models import (
    Component,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    MaintenanceWindow,
    StatusPageConfig,
    StatusPageIncident,
    StatusUpdate,
)
from .base import BaseStatusPageProvider


# Cachet status codes
CACHET_COMPONENT_STATUS = {
    ComponentStatus.OPERATIONAL: 1,
    ComponentStatus.DEGRADED: 2,
    ComponentStatus.PARTIAL_OUTAGE: 3,
    ComponentStatus.MAJOR_OUTAGE: 4,
    ComponentStatus.MAINTENANCE: 0,
}

CACHET_STATUS_REVERSE = {v: k for k, v in CACHET_COMPONENT_STATUS.items()}

CACHET_INCIDENT_STATUS = {
    IncidentStatus.INVESTIGATING: 1,
    IncidentStatus.IDENTIFIED: 2,
    IncidentStatus.MONITORING: 3,
    IncidentStatus.RESOLVED: 4,
    IncidentStatus.SCHEDULED: 0,
}

CACHET_STATUS_REVERSE_INC = {v: k for k, v in CACHET_INCIDENT_STATUS.items()}


class CachetProvider(BaseStatusPageProvider):
    """Cachet (self-hosted) integration."""

    def __init__(self, config: StatusPageConfig):
        super().__init__(config)
        self.base_url = (config.credentials.api_url or "").rstrip("/")
        if not self.base_url.endswith("/api/v1"):
            self.base_url = f"{self.base_url}/api/v1"

    def _build_headers(self) -> dict[str, str]:
        return {
            "X-Cachet-Token": self.config.credentials.api_key,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def validate_credentials(self) -> bool:
        """Validate API credentials."""
        try:
            await self._request("GET", self._url("/ping"))
            return True
        except Exception:
            return False

    async def get_components(self) -> list[Component]:
        """Fetch all components."""
        data = await self._request("GET", self._url("/components"))
        return [self._parse_component(c) for c in data.get("data", [])]

    async def update_component(self, component_id: str, status: ComponentStatus) -> Component:
        """Update component status."""
        payload = {"status": CACHET_COMPONENT_STATUS[status]}
        data = await self._request(
            "PUT", self._url(f"/components/{component_id}"), json=payload
        )
        return self._parse_component(data.get("data", {}))

    async def get_incidents(self, unresolved_only: bool = True) -> list[StatusPageIncident]:
        """Fetch incidents."""
        params = {}
        if unresolved_only:
            params["status"] = "1,2,3"  # Not resolved
        data = await self._request("GET", self._url("/incidents"), params=params)
        return [self._parse_incident(i) for i in data.get("data", [])]

    async def create_incident(self, incident: StatusPageIncident) -> StatusPageIncident:
        """Create a new incident."""
        payload = {
            "name": incident.name,
            "message": incident.message,
            "status": CACHET_INCIDENT_STATUS.get(incident.status, 1),
            "visible": 1,
            "notify": True,
        }

        if incident.component_ids:
            payload["component_id"] = incident.component_ids[0]
            payload["component_status"] = CACHET_COMPONENT_STATUS[incident.component_status]

        # Handle scheduled maintenance
        if incident.scheduled_for:
            payload["status"] = 0  # Scheduled
            payload["scheduled_at"] = incident.scheduled_for.isoformat()

        data = await self._request("POST", self._url("/incidents"), json=payload)
        return self._parse_incident(data.get("data", {}))

    async def update_incident(
        self, incident_id: str, update: StatusUpdate
    ) -> StatusPageIncident:
        """Update an incident."""
        # Create incident update
        payload = {
            "status": CACHET_INCIDENT_STATUS.get(update.status, 1),
            "message": update.message,
        }
        await self._request(
            "POST", self._url(f"/incidents/{incident_id}/updates"), json=payload
        )

        # Update incident status
        await self._request(
            "PUT",
            self._url(f"/incidents/{incident_id}"),
            json={"status": CACHET_INCIDENT_STATUS.get(update.status, 1)},
        )

        # Fetch and return updated incident
        data = await self._request("GET", self._url(f"/incidents/{incident_id}"))
        return self._parse_incident(data.get("data", {}))

    async def resolve_incident(self, incident_id: str, message: str) -> StatusPageIncident:
        """Resolve an incident."""
        # Create resolution update
        payload = {
            "status": 4,  # Resolved
            "message": message,
        }
        await self._request(
            "POST", self._url(f"/incidents/{incident_id}/updates"), json=payload
        )

        # Update incident status
        await self._request(
            "PUT", self._url(f"/incidents/{incident_id}"), json={"status": 4}
        )

        data = await self._request("GET", self._url(f"/incidents/{incident_id}"))
        return self._parse_incident(data.get("data", {}))

    async def get_scheduled_maintenances(self) -> list[MaintenanceWindow]:
        """Fetch scheduled maintenances."""
        data = await self._request("GET", self._url("/schedules"))
        return [self._parse_maintenance(m) for m in data.get("data", [])]

    async def create_maintenance(self, maintenance: MaintenanceWindow) -> MaintenanceWindow:
        """Create scheduled maintenance."""
        payload = {
            "name": maintenance.name,
            "message": maintenance.description,
            "status": 0,  # Scheduled
            "scheduled_at": maintenance.scheduled_start.isoformat(),
            "notify": maintenance.notify_subscribers,
        }

        if maintenance.component_ids:
            payload["component_id"] = maintenance.component_ids[0]
            payload["component_status"] = CACHET_COMPONENT_STATUS[ComponentStatus.MAINTENANCE]

        data = await self._request("POST", self._url("/schedules"), json=payload)
        return self._parse_maintenance(data.get("data", {}))

    async def get_component_groups(self) -> list[dict]:
        """Fetch component groups."""
        data = await self._request("GET", self._url("/components/groups"))
        return data.get("data", [])

    async def get_metrics(self) -> list[dict]:
        """Fetch metrics."""
        data = await self._request("GET", self._url("/metrics"))
        return data.get("data", [])

    async def add_metric_point(self, metric_id: str, value: float) -> dict:
        """Add a metric data point."""
        payload = {"value": value, "timestamp": int(datetime.utcnow().timestamp())}
        data = await self._request(
            "POST", self._url(f"/metrics/{metric_id}/points"), json=payload
        )
        return data.get("data", {})

    def _parse_component(self, data: dict) -> Component:
        """Parse API response to Component."""
        return Component(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            description=data.get("description"),
            status=CACHET_STATUS_REVERSE.get(
                data.get("status", 1), ComponentStatus.OPERATIONAL
            ),
            group_id=str(data.get("group_id", "")) if data.get("group_id") else None,
            position=data.get("order", 0),
        )

    def _parse_incident(self, data: dict) -> StatusPageIncident:
        """Parse API response to StatusPageIncident."""
        updates = []
        for u in data.get("updates", []):
            updates.append(
                StatusUpdate(
                    id=str(u.get("id", "")),
                    incident_id=str(data.get("id", "")),
                    status=CACHET_STATUS_REVERSE_INC.get(
                        u.get("status", 1), IncidentStatus.INVESTIGATING
                    ),
                    message=u.get("message", ""),
                    created_at=datetime.fromisoformat(u["created_at"].replace("Z", "+00:00"))
                    if u.get("created_at")
                    else datetime.utcnow(),
                )
            )

        created = data.get("created_at", "")
        updated = data.get("updated_at", "")

        return StatusPageIncident(
            id=str(data.get("id", "")),
            external_id=str(data.get("id", "")),
            name=data.get("name", ""),
            status=CACHET_STATUS_REVERSE_INC.get(
                data.get("status", 1), IncidentStatus.INVESTIGATING
            ),
            message=data.get("message", ""),
            component_ids=[str(data["component_id"])] if data.get("component_id") else [],
            updates=updates,
            created_at=datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created
            else datetime.utcnow(),
            updated_at=datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if updated
            else datetime.utcnow(),
        )

    def _parse_maintenance(self, data: dict) -> MaintenanceWindow:
        """Parse API response to MaintenanceWindow."""
        scheduled = data.get("scheduled_at", "")
        return MaintenanceWindow(
            id=str(data.get("id", "")),
            name=data.get("name", "Maintenance"),
            description=data.get("message", ""),
            scheduled_start=datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
            if scheduled
            else datetime.utcnow(),
            scheduled_end=datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
            if scheduled
            else datetime.utcnow(),
            component_ids=[str(data["component_id"])] if data.get("component_id") else [],
            status=IncidentStatus.SCHEDULED,
        )
