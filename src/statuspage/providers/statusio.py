"""Status.io Provider."""

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


# Status.io status codes
STATUSIO_STATUS_CODES = {
    ComponentStatus.OPERATIONAL: 100,
    ComponentStatus.DEGRADED: 300,
    ComponentStatus.PARTIAL_OUTAGE: 400,
    ComponentStatus.MAJOR_OUTAGE: 500,
    ComponentStatus.MAINTENANCE: 600,
}

STATUSIO_STATUS_REVERSE = {v: k for k, v in STATUSIO_STATUS_CODES.items()}

STATUSIO_INCIDENT_STATE = {
    IncidentStatus.INVESTIGATING: 100,
    IncidentStatus.IDENTIFIED: 200,
    IncidentStatus.MONITORING: 300,
    IncidentStatus.RESOLVED: 400,
}


class StatusIOProvider(BaseStatusPageProvider):
    """Status.io integration."""

    BASE_URL = "https://api.status.io/v2"

    def __init__(self, config: StatusPageConfig):
        super().__init__(config)
        self.page_id = config.credentials.page_id
        self.api_id = config.credentials.extra.get("api_id", "")

    def _build_headers(self) -> dict[str, str]:
        return {
            "x-api-id": self.api_id,
            "x-api-key": self.config.credentials.api_key,
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.BASE_URL}{path}"

    async def validate_credentials(self) -> bool:
        """Validate API credentials."""
        try:
            await self._request("GET", self._url(f"/statuspage/{self.page_id}"))
            return True
        except Exception:
            return False

    async def get_components(self) -> list[Component]:
        """Fetch all components."""
        data = await self._request("GET", self._url(f"/component/list/{self.page_id}"))
        components = []
        for comp in data.get("result", []):
            for container in comp.get("containers", []):
                components.append(self._parse_component(container, comp["_id"]))
        return components

    async def update_component(self, component_id: str, status: ComponentStatus) -> Component:
        """Update component status."""
        payload = {
            "statuspage_id": self.page_id,
            "component": component_id,
            "container": component_id,  # Status.io uses containers
            "details": "Status updated via API",
            "current_status": STATUSIO_STATUS_CODES[status],
        }
        await self._request("POST", self._url("/component/status/update"), json=payload)
        # Return updated component
        components = await self.get_components()
        return next((c for c in components if c.id == component_id), Component(
            id=component_id, name="Unknown", status=status
        ))

    async def get_incidents(self, unresolved_only: bool = True) -> list[StatusPageIncident]:
        """Fetch incidents."""
        endpoint = "/incident/list" if unresolved_only else "/incident/list/all"
        data = await self._request("GET", self._url(f"{endpoint}/{self.page_id}"))
        incidents = []
        for inc in data.get("result", {}).get("active_incidents", []):
            incidents.append(self._parse_incident(inc))
        return incidents

    async def create_incident(self, incident: StatusPageIncident) -> StatusPageIncident:
        """Create a new incident."""
        payload = {
            "statuspage_id": self.page_id,
            "incident_name": incident.name,
            "incident_details": incident.message,
            "notify_email": "1",
            "notify_sms": "0",
            "notify_webhook": "1",
            "social": "0",
            "irc": "0",
            "hipchat": "0",
            "slack": "0",
            "current_status": STATUSIO_STATUS_CODES[incident.component_status],
            "current_state": STATUSIO_INCIDENT_STATE.get(incident.status, 100),
            "all_infrastructure_affected": "0",
        }

        if incident.component_ids:
            # Status.io requires infrastructure arrays
            payload["infrastructure_affected"] = [
                {"component": cid} for cid in incident.component_ids
            ]

        data = await self._request("POST", self._url("/incident/create"), json=payload)
        incident.external_id = data.get("result", "")
        incident.id = incident.external_id
        return incident

    async def update_incident(
        self, incident_id: str, update: StatusUpdate
    ) -> StatusPageIncident:
        """Update an incident."""
        payload = {
            "statuspage_id": self.page_id,
            "incident_id": incident_id,
            "incident_details": update.message,
            "current_state": STATUSIO_INCIDENT_STATE.get(update.status, 100),
            "notify_email": "1",
            "notify_sms": "0",
            "notify_webhook": "1",
        }
        await self._request("POST", self._url("/incident/update"), json=payload)
        return StatusPageIncident(
            id=incident_id,
            external_id=incident_id,
            name="",
            status=update.status,
            message=update.message,
        )

    async def resolve_incident(self, incident_id: str, message: str) -> StatusPageIncident:
        """Resolve an incident."""
        payload = {
            "statuspage_id": self.page_id,
            "incident_id": incident_id,
            "incident_details": message,
            "notify_email": "1",
            "notify_sms": "0",
            "notify_webhook": "1",
        }
        await self._request("POST", self._url("/incident/resolve"), json=payload)
        return StatusPageIncident(
            id=incident_id,
            external_id=incident_id,
            name="",
            status=IncidentStatus.RESOLVED,
            message=message,
        )

    async def get_scheduled_maintenances(self) -> list[MaintenanceWindow]:
        """Fetch scheduled maintenances."""
        data = await self._request("GET", self._url(f"/maintenance/list/{self.page_id}"))
        maintenances = []
        for maint in data.get("result", {}).get("upcoming_maintenances", []):
            maintenances.append(self._parse_maintenance(maint))
        return maintenances

    async def create_maintenance(self, maintenance: MaintenanceWindow) -> MaintenanceWindow:
        """Create scheduled maintenance."""
        payload = {
            "statuspage_id": self.page_id,
            "maintenance_name": maintenance.name,
            "maintenance_details": maintenance.description,
            "date_planned_start": maintenance.scheduled_start.strftime("%m/%d/%Y"),
            "time_planned_start": maintenance.scheduled_start.strftime("%H:%M"),
            "date_planned_end": maintenance.scheduled_end.strftime("%m/%d/%Y"),
            "time_planned_end": maintenance.scheduled_end.strftime("%H:%M"),
            "notify_email": "1" if maintenance.notify_subscribers else "0",
            "notify_sms": "0",
            "notify_webhook": "1",
            "automation": "1",
        }

        if maintenance.component_ids:
            payload["infrastructure_affected"] = [
                {"component": cid} for cid in maintenance.component_ids
            ]

        data = await self._request("POST", self._url("/maintenance/schedule"), json=payload)
        maintenance.id = data.get("result", maintenance.id)
        return maintenance

    def _parse_component(self, data: dict, group_id: str | None = None) -> Component:
        """Parse API response to Component."""
        status_code = data.get("status_code", 100)
        return Component(
            id=data["_id"],
            name=data["name"],
            description=None,
            status=STATUSIO_STATUS_REVERSE.get(status_code, ComponentStatus.OPERATIONAL),
            group_id=group_id,
            position=data.get("position", 0),
        )

    def _parse_incident(self, data: dict) -> StatusPageIncident:
        """Parse API response to StatusPageIncident."""
        updates = []
        for msg in data.get("messages", []):
            updates.append(
                StatusUpdate(
                    id=msg.get("_id", ""),
                    incident_id=data["_id"],
                    status=IncidentStatus.INVESTIGATING,
                    message=msg.get("details", ""),
                    created_at=datetime.fromisoformat(msg["datetime"].replace("Z", "+00:00"))
                    if msg.get("datetime")
                    else datetime.utcnow(),
                )
            )

        return StatusPageIncident(
            id=data["_id"],
            external_id=data["_id"],
            name=data.get("name", ""),
            status=IncidentStatus.INVESTIGATING,
            message=data.get("messages", [{}])[0].get("details", "") if data.get("messages") else "",
            component_ids=[],
            updates=updates,
            created_at=datetime.fromisoformat(data["datetime"].replace("Z", "+00:00"))
            if data.get("datetime")
            else datetime.utcnow(),
        )

    def _parse_maintenance(self, data: dict) -> MaintenanceWindow:
        """Parse API response to MaintenanceWindow."""
        return MaintenanceWindow(
            id=data["_id"],
            name=data.get("name", "Maintenance"),
            description=data.get("details", ""),
            scheduled_start=datetime.fromisoformat(
                data["datetime_planned_start"].replace("Z", "+00:00")
            )
            if data.get("datetime_planned_start")
            else datetime.utcnow(),
            scheduled_end=datetime.fromisoformat(
                data["datetime_planned_end"].replace("Z", "+00:00")
            )
            if data.get("datetime_planned_end")
            else datetime.utcnow(),
            component_ids=[],
            status=IncidentStatus.SCHEDULED,
        )
