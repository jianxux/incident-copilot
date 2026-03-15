"""Status.io Provider."""

from datetime import UTC, datetime

import httpx

from ..models import (
    Component,
    ComponentStatus,
    IncidentStatus,
    MaintenanceWindow,
    StatusPageConfig,
    StatusPageIncident,
    StatusUpdate,
)

STATUS_CODES = {
    ComponentStatus.OPERATIONAL: 100,
    ComponentStatus.DEGRADED: 300,
    ComponentStatus.PARTIAL_OUTAGE: 400,
    ComponentStatus.MAJOR_OUTAGE: 500,
    ComponentStatus.MAINTENANCE: 600,
}
STATUS_REV = {v: k for k, v in STATUS_CODES.items()}
STATE_CODES = {
    IncidentStatus.INVESTIGATING: 100,
    IncidentStatus.IDENTIFIED: 200,
    IncidentStatus.MONITORING: 300,
    IncidentStatus.RESOLVED: 400,
}


class StatusIOProvider:
    """Status.io integration."""

    def __init__(self, config: StatusPageConfig):
        self.config = config
        self.page_id = config.credentials.page_id
        self.api_id = config.credentials.extra.get("api_id", "")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "x-api-id": self.api_id,
                    "x-api-key": self.config.credentials.api_key,
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def validate_credentials(self) -> bool:
        try:
            r = await self.client.get(
                f"https://api.status.io/v2/statuspage/{self.page_id}"
            )
            return r.is_success
        except Exception:
            return False

    async def get_components(self) -> list[Component]:
        r = await self.client.get(
            f"https://api.status.io/v2/component/list/{self.page_id}"
        )
        components = []
        for comp in r.json().get("result", []):
            for c in comp.get("containers", []):
                components.append(
                    Component(
                        id=c["_id"],
                        name=c["name"],
                        status=STATUS_REV.get(
                            c.get("status_code", 100), ComponentStatus.OPERATIONAL
                        ),
                        group_id=comp["_id"],
                    )
                )
        return components

    async def update_component(
        self, component_id: str, status: ComponentStatus
    ) -> Component:
        await self.client.post(
            "https://api.status.io/v2/component/status/update",
            json={
                "statuspage_id": self.page_id,
                "component": component_id,
                "container": component_id,
                "current_status": STATUS_CODES[status],
            },
        )
        return Component(id=component_id, name="Updated", status=status)

    async def get_incidents(
        self, unresolved_only: bool = True
    ) -> list[StatusPageIncident]:
        r = await self.client.get(
            f"https://api.status.io/v2/incident/list/{self.page_id}"
        )
        return [
            StatusPageIncident(
                id=i["_id"],
                external_id=i["_id"],
                name=i.get("name", ""),
                message=(
                    i.get("messages", [{}])[0].get("details", "")
                    if i.get("messages")
                    else ""
                ),
                status=IncidentStatus.INVESTIGATING,
            )
            for i in r.json().get("result", {}).get("active_incidents", [])
        ]

    async def create_incident(self, incident: StatusPageIncident) -> StatusPageIncident:
        payload = {
            "statuspage_id": self.page_id,
            "incident_name": incident.name,
            "incident_details": incident.message,
            "notify_email": "1",
            "notify_webhook": "1",
            "current_status": STATUS_CODES[incident.component_status],
            "current_state": STATE_CODES.get(incident.status, 100),
        }
        if incident.component_ids:
            payload["infrastructure_affected"] = [
                {"component": cid} for cid in incident.component_ids
            ]
        r = await self.client.post(
            "https://api.status.io/v2/incident/create", json=payload
        )
        incident.external_id = r.json().get("result", "")
        incident.id = incident.external_id
        return incident

    async def update_incident(
        self, incident_id: str, update: StatusUpdate
    ) -> StatusPageIncident:
        await self.client.post(
            "https://api.status.io/v2/incident/update",
            json={
                "statuspage_id": self.page_id,
                "incident_id": incident_id,
                "incident_details": update.message,
                "current_state": STATE_CODES.get(update.status, 100),
            },
        )
        return StatusPageIncident(
            id=incident_id,
            external_id=incident_id,
            name="",
            status=update.status,
            message=update.message,
        )

    async def resolve_incident(
        self, incident_id: str, message: str
    ) -> StatusPageIncident:
        await self.client.post(
            "https://api.status.io/v2/incident/resolve",
            json={
                "statuspage_id": self.page_id,
                "incident_id": incident_id,
                "incident_details": message,
            },
        )
        return StatusPageIncident(
            id=incident_id,
            external_id=incident_id,
            name="",
            status=IncidentStatus.RESOLVED,
            message=message,
        )

    async def get_scheduled_maintenances(self) -> list[MaintenanceWindow]:
        r = await self.client.get(
            f"https://api.status.io/v2/maintenance/list/{self.page_id}"
        )
        return [
            MaintenanceWindow(
                id=m["_id"],
                name=m.get("name", ""),
                description=m.get("details", ""),
                scheduled_start=(
                    datetime.fromisoformat(
                        m["datetime_planned_start"].replace("Z", "+00:00")
                    )
                    if m.get("datetime_planned_start")
                    else datetime.now(UTC)
                ),
                scheduled_end=(
                    datetime.fromisoformat(
                        m["datetime_planned_end"].replace("Z", "+00:00")
                    )
                    if m.get("datetime_planned_end")
                    else datetime.now(UTC)
                ),
                component_ids=[],
            )
            for m in r.json().get("result", {}).get("upcoming_maintenances", [])
        ]

    async def create_maintenance(self, m: MaintenanceWindow) -> MaintenanceWindow:
        payload = {
            "statuspage_id": self.page_id,
            "maintenance_name": m.name,
            "maintenance_details": m.description,
            "date_planned_start": m.scheduled_start.strftime("%m/%d/%Y"),
            "time_planned_start": m.scheduled_start.strftime("%H:%M"),
            "date_planned_end": m.scheduled_end.strftime("%m/%d/%Y"),
            "time_planned_end": m.scheduled_end.strftime("%H:%M"),
            "notify_email": "1" if m.notify_subscribers else "0",
        }
        r = await self.client.post(
            "https://api.status.io/v2/maintenance/schedule", json=payload
        )
        m.id = r.json().get("result", m.id)
        return m
