"""Cachet (Self-Hosted) Provider."""

from datetime import datetime
import httpx
from ..models import Component, ComponentStatus, IncidentStatus, MaintenanceWindow, StatusPageConfig, StatusPageIncident, StatusUpdate

STATUS_MAP = {ComponentStatus.OPERATIONAL: 1, ComponentStatus.DEGRADED: 2, ComponentStatus.PARTIAL_OUTAGE: 3, ComponentStatus.MAJOR_OUTAGE: 4, ComponentStatus.MAINTENANCE: 0}
STATUS_REV = {v: k for k, v in STATUS_MAP.items()}
INC_STATUS = {IncidentStatus.INVESTIGATING: 1, IncidentStatus.IDENTIFIED: 2, IncidentStatus.MONITORING: 3, IncidentStatus.RESOLVED: 4, IncidentStatus.SCHEDULED: 0}
INC_REV = {v: k for k, v in INC_STATUS.items()}


class CachetProvider:
    """Cachet (self-hosted) integration."""

    def __init__(self, config: StatusPageConfig):
        self.config = config
        base = (config.credentials.api_url or "").rstrip("/")
        self.base_url = f"{base}/api/v1" if not base.endswith("/api/v1") else base
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0, headers={"X-Cachet-Token": self.config.credentials.api_key, "Content-Type": "application/json"})
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def validate_credentials(self) -> bool:
        try:
            r = await self.client.get(f"{self.base_url}/ping")
            return r.is_success
        except Exception:
            return False

    async def get_components(self) -> list[Component]:
        r = await self.client.get(f"{self.base_url}/components")
        return [Component(id=str(c["id"]), name=c["name"], description=c.get("description"), status=STATUS_REV.get(c.get("status", 1), ComponentStatus.OPERATIONAL), group_id=str(c.get("group_id", "")) if c.get("group_id") else None, position=c.get("order", 0)) for c in r.json().get("data", [])]

    async def update_component(self, component_id: str, status: ComponentStatus) -> Component:
        r = await self.client.put(f"{self.base_url}/components/{component_id}", json={"status": STATUS_MAP[status]})
        c = r.json().get("data", {})
        return Component(id=str(c.get("id", component_id)), name=c.get("name", ""), status=status)

    async def get_incidents(self, unresolved_only: bool = True) -> list[StatusPageIncident]:
        params = {"status": "1,2,3"} if unresolved_only else {}
        r = await self.client.get(f"{self.base_url}/incidents", params=params)
        return [StatusPageIncident(id=str(i["id"]), external_id=str(i["id"]), name=i.get("name", ""), status=INC_REV.get(i.get("status", 1), IncidentStatus.INVESTIGATING), message=i.get("message", ""), component_ids=[str(i["component_id"])] if i.get("component_id") else [], created_at=datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")) if i.get("created_at") else datetime.utcnow()) for i in r.json().get("data", [])]

    async def create_incident(self, incident: StatusPageIncident) -> StatusPageIncident:
        payload = {"name": incident.name, "message": incident.message, "status": INC_STATUS.get(incident.status, 1), "visible": 1, "notify": True}
        if incident.component_ids:
            payload["component_id"] = incident.component_ids[0]
            payload["component_status"] = STATUS_MAP[incident.component_status]
        if incident.scheduled_for:
            payload["status"] = 0
            payload["scheduled_at"] = incident.scheduled_for.isoformat()
        r = await self.client.post(f"{self.base_url}/incidents", json=payload)
        d = r.json().get("data", {})
        incident.id = str(d.get("id", ""))
        incident.external_id = incident.id
        return incident

    async def update_incident(self, incident_id: str, update: StatusUpdate) -> StatusPageIncident:
        await self.client.post(f"{self.base_url}/incidents/{incident_id}/updates", json={"status": INC_STATUS.get(update.status, 1), "message": update.message})
        await self.client.put(f"{self.base_url}/incidents/{incident_id}", json={"status": INC_STATUS.get(update.status, 1)})
        r = await self.client.get(f"{self.base_url}/incidents/{incident_id}")
        d = r.json().get("data", {})
        return StatusPageIncident(id=str(d.get("id", incident_id)), external_id=str(d.get("id", incident_id)), name=d.get("name", ""), status=update.status, message=update.message)

    async def resolve_incident(self, incident_id: str, message: str) -> StatusPageIncident:
        await self.client.post(f"{self.base_url}/incidents/{incident_id}/updates", json={"status": 4, "message": message})
        await self.client.put(f"{self.base_url}/incidents/{incident_id}", json={"status": 4})
        return StatusPageIncident(id=incident_id, external_id=incident_id, name="", status=IncidentStatus.RESOLVED, message=message)

    async def get_scheduled_maintenances(self) -> list[MaintenanceWindow]:
        r = await self.client.get(f"{self.base_url}/schedules")
        return [MaintenanceWindow(id=str(m["id"]), name=m.get("name", ""), description=m.get("message", ""), scheduled_start=datetime.fromisoformat(m["scheduled_at"].replace("Z", "+00:00")) if m.get("scheduled_at") else datetime.utcnow(), scheduled_end=datetime.fromisoformat(m["scheduled_at"].replace("Z", "+00:00")) if m.get("scheduled_at") else datetime.utcnow(), component_ids=[str(m["component_id"])] if m.get("component_id") else []) for m in r.json().get("data", [])]

    async def create_maintenance(self, m: MaintenanceWindow) -> MaintenanceWindow:
        payload = {"name": m.name, "message": m.description, "status": 0, "scheduled_at": m.scheduled_start.isoformat(), "notify": m.notify_subscribers}
        if m.component_ids:
            payload["component_id"] = m.component_ids[0]
            payload["component_status"] = STATUS_MAP[ComponentStatus.MAINTENANCE]
        r = await self.client.post(f"{self.base_url}/schedules", json=payload)
        d = r.json().get("data", {})
        m.id = str(d.get("id", m.id))
        return m
