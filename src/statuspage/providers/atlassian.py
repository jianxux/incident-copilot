"""Atlassian Statuspage Provider."""

from datetime import datetime

import httpx

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

STATUS_MAP = {
    ComponentStatus.OPERATIONAL: "operational",
    ComponentStatus.DEGRADED: "degraded_performance",
    ComponentStatus.PARTIAL_OUTAGE: "partial_outage",
    ComponentStatus.MAJOR_OUTAGE: "major_outage",
    ComponentStatus.MAINTENANCE: "under_maintenance",
}
STATUS_REV = {v: k for k, v in STATUS_MAP.items()}
INCIDENT_MAP = {
    IncidentStatus.INVESTIGATING: "investigating",
    IncidentStatus.IDENTIFIED: "identified",
    IncidentStatus.MONITORING: "monitoring",
    IncidentStatus.RESOLVED: "resolved",
}
IMPACT_MAP = {
    IncidentImpact.NONE: "none",
    IncidentImpact.MINOR: "minor",
    IncidentImpact.MAJOR: "major",
    IncidentImpact.CRITICAL: "critical",
}


class AtlassianProvider:
    """Atlassian Statuspage integration."""

    def __init__(self, config: StatusPageConfig):
        self.config = config
        self.page_id = config.credentials.page_id
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"OAuth {self.config.credentials.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()

    def _url(self, path: str) -> str:
        return f"https://api.statuspage.io/v1/pages/{self.page_id}{path}"

    async def validate_credentials(self) -> bool:
        try:
            r = await self.client.get(self._url(""))
            return r.is_success
        except Exception:
            return False

    async def get_components(self) -> list[Component]:
        r = await self.client.get(self._url("/components"))
        return [
            Component(
                id=c["id"],
                name=c["name"],
                status=STATUS_REV.get(c.get("status"), ComponentStatus.OPERATIONAL),
                group_id=c.get("group_id"),
                position=c.get("position", 0),
            )
            for c in r.json()
        ]

    async def update_component(
        self, component_id: str, status: ComponentStatus
    ) -> Component:
        r = await self.client.patch(
            self._url(f"/components/{component_id}"),
            json={"component": {"status": STATUS_MAP[status]}},
        )
        c = r.json()
        return Component(
            id=c["id"],
            name=c["name"],
            status=STATUS_REV.get(c.get("status"), ComponentStatus.OPERATIONAL),
        )

    async def get_incidents(
        self, unresolved_only: bool = True
    ) -> list[StatusPageIncident]:
        endpoint = "/incidents/unresolved" if unresolved_only else "/incidents"
        r = await self.client.get(self._url(endpoint))
        return [self._parse_incident(i) for i in r.json()]

    async def create_incident(self, incident: StatusPageIncident) -> StatusPageIncident:
        components = {
            cid: STATUS_MAP[incident.component_status] for cid in incident.component_ids
        }
        payload = {
            "incident": {
                "name": incident.name,
                "status": INCIDENT_MAP.get(incident.status, "investigating"),
                "impact_override": IMPACT_MAP[incident.impact],
                "body": incident.message,
                "components": components,
            }
        }
        if incident.scheduled_for:
            payload["incident"]["scheduled_for"] = incident.scheduled_for.isoformat()
        r = await self.client.post(self._url("/incidents"), json=payload)
        return self._parse_incident(r.json())

    async def update_incident(
        self, incident_id: str, update: StatusUpdate
    ) -> StatusPageIncident:
        r = await self.client.patch(
            self._url(f"/incidents/{incident_id}"),
            json={
                "incident": {
                    "status": INCIDENT_MAP.get(update.status, "investigating"),
                    "body": update.message,
                }
            },
        )
        return self._parse_incident(r.json())

    async def resolve_incident(
        self, incident_id: str, message: str
    ) -> StatusPageIncident:
        r = await self.client.patch(
            self._url(f"/incidents/{incident_id}"),
            json={"incident": {"status": "resolved", "body": message}},
        )
        return self._parse_incident(r.json())

    async def get_scheduled_maintenances(self) -> list[MaintenanceWindow]:
        r = await self.client.get(self._url("/incidents/scheduled"))
        return [
            MaintenanceWindow(
                id=m["id"],
                name=m["name"],
                description=m.get("incident_updates", [{}])[0].get("body", ""),
                scheduled_start=datetime.fromisoformat(
                    m["scheduled_for"].replace("Z", "+00:00")
                ),
                scheduled_end=datetime.fromisoformat(
                    m["scheduled_until"].replace("Z", "+00:00")
                ),
                component_ids=[c["id"] for c in m.get("components", [])],
            )
            for m in r.json()
        ]

    async def create_maintenance(self, m: MaintenanceWindow) -> MaintenanceWindow:
        payload = {
            "incident": {
                "name": m.name,
                "status": "scheduled",
                "body": m.description,
                "scheduled_for": m.scheduled_start.isoformat(),
                "scheduled_until": m.scheduled_end.isoformat(),
                "components": {cid: "under_maintenance" for cid in m.component_ids},
            }
        }
        r = await self.client.post(self._url("/incidents"), json=payload)
        d = r.json()
        return MaintenanceWindow(
            id=d["id"],
            name=d["name"],
            description=m.description,
            scheduled_start=m.scheduled_start,
            scheduled_end=m.scheduled_end,
            component_ids=m.component_ids,
        )

    def _parse_incident(self, d: dict) -> StatusPageIncident:
        return StatusPageIncident(
            id=d["id"],
            external_id=d["id"],
            name=d["name"],
            status=IncidentStatus(d.get("status", "investigating")),
            impact=IncidentImpact(d.get("impact", "minor")),
            message=d.get("incident_updates", [{}])[0].get("body", ""),
            component_ids=[c["id"] for c in d.get("components", [])],
            created_at=datetime.fromisoformat(d["created_at"].replace("Z", "+00:00")),
        )
