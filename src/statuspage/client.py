"""Atlassian Statuspage API client.

Provides async client for interacting with the Statuspage.io API
for managing components, incidents, and status updates.
"""

from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from ..config import get_settings
from .models import (
    ComponentImpact,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    StatusComponent,
    StatusIncident,
    StatusPage,
    StatusUpdate,
    UptimeMetrics,
)

logger = structlog.get_logger()


class StatuspageClient:
    """Async client for Atlassian Statuspage API."""

    BASE_URL = "https://api.statuspage.io/v1"

    def __init__(
        self,
        api_key: str | None = None,
        page_id: str | None = None,
    ):
        """Initialize Statuspage client.

        Args:
            api_key: Statuspage API key (OAuth or API token)
            page_id: Default page ID for operations
        """
        settings = get_settings()

        self.api_key = api_key or getattr(settings, "statuspage_api_key", "")
        self.default_page_id = page_id or getattr(
            settings, "statuspage_default_page_id", ""
        )

        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Check if Statuspage integration is properly configured."""
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"OAuth {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_page_id(self, page_id: str | None) -> str:
        """Get page ID with fallback to default."""
        pid = page_id or self.default_page_id
        if not pid:
            raise ValueError("page_id is required when no default is configured")
        return pid

    # ==================== Page Operations ====================

    async def list_pages(self) -> list[StatusPage]:
        """List all status pages accessible with this API key.

        Returns:
            List of status pages
        """
        if not self.is_configured:
            raise ValueError("Statuspage integration not configured")

        client = await self._get_client()
        response = await client.get("/pages")
        response.raise_for_status()

        pages = []
        for page_data in response.json():
            pages.append(
                StatusPage(
                    id=page_data["id"],
                    name=page_data["name"],
                    subdomain=page_data["subdomain"],
                    domain=page_data.get("domain"),
                    url=page_data.get("url"),
                    time_zone=page_data.get("time_zone", "UTC"),
                )
            )

        logger.debug("statuspage_pages_listed", count=len(pages))
        return pages

    async def get_page(self, page_id: str | None = None) -> StatusPage:
        """Get details of a status page.

        Args:
            page_id: Page ID (uses default if not specified)

        Returns:
            Status page details
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        response = await client.get(f"/pages/{pid}")
        response.raise_for_status()

        data = response.json()
        return StatusPage(
            id=data["id"],
            name=data["name"],
            subdomain=data["subdomain"],
            domain=data.get("domain"),
            url=data.get("url"),
            time_zone=data.get("time_zone", "UTC"),
        )

    # ==================== Component Operations ====================

    async def list_components(
        self, page_id: str | None = None
    ) -> list[StatusComponent]:
        """List all components on a status page.

        Args:
            page_id: Page ID (uses default if not specified)

        Returns:
            List of components
        """
        if not self.is_configured:
            raise ValueError("Statuspage integration not configured")

        client = await self._get_client()
        pid = self._get_page_id(page_id)

        response = await client.get(f"/pages/{pid}/components")
        response.raise_for_status()

        components = []
        for comp_data in response.json():
            components.append(self._parse_component(comp_data, pid))

        logger.debug("statuspage_components_listed", page_id=pid, count=len(components))
        return components

    async def get_component(
        self, component_id: str, page_id: str | None = None
    ) -> StatusComponent:
        """Get a specific component.

        Args:
            component_id: Component ID
            page_id: Page ID (uses default if not specified)

        Returns:
            Component details
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        response = await client.get(f"/pages/{pid}/components/{component_id}")
        response.raise_for_status()

        return self._parse_component(response.json(), pid)

    async def update_component_status(
        self,
        component_id: str,
        status: ComponentStatus,
        page_id: str | None = None,
    ) -> StatusComponent:
        """Update a component's status.

        Args:
            component_id: Component ID
            status: New status
            page_id: Page ID (uses default if not specified)

        Returns:
            Updated component
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        payload = {"component": {"status": status.value}}

        logger.info(
            "statuspage_updating_component",
            component_id=component_id,
            status=status.value,
        )

        response = await client.patch(
            f"/pages/{pid}/components/{component_id}",
            json=payload,
        )
        response.raise_for_status()

        return self._parse_component(response.json(), pid)

    async def create_component(
        self,
        name: str,
        description: str | None = None,
        status: ComponentStatus = ComponentStatus.OPERATIONAL,
        group_id: str | None = None,
        page_id: str | None = None,
    ) -> StatusComponent:
        """Create a new component.

        Args:
            name: Component name
            description: Component description
            status: Initial status
            group_id: Optional component group ID
            page_id: Page ID (uses default if not specified)

        Returns:
            Created component
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        payload: dict[str, Any] = {
            "component": {
                "name": name,
                "status": status.value,
            }
        }

        if description:
            payload["component"]["description"] = description
        if group_id:
            payload["component"]["group_id"] = group_id

        logger.info("statuspage_creating_component", name=name, page_id=pid)

        response = await client.post(f"/pages/{pid}/components", json=payload)
        response.raise_for_status()

        return self._parse_component(response.json(), pid)

    def _parse_component(self, data: dict, page_id: str) -> StatusComponent:
        """Parse component data from API response."""
        return StatusComponent(
            id=data["id"],
            page_id=page_id,
            name=data["name"],
            description=data.get("description"),
            status=ComponentStatus(data.get("status", "operational")),
            position=data.get("position", 0),
            showcase=data.get("showcase", True),
            only_show_if_degraded=data.get("only_show_if_degraded", False),
            group_id=data.get("group_id"),
            created_at=self._parse_datetime(data.get("created_at")),
            updated_at=self._parse_datetime(data.get("updated_at")),
            automation_email=data.get("automation_email"),
        )

    # ==================== Incident Operations ====================

    async def list_incidents(
        self,
        page_id: str | None = None,
        status: IncidentStatus | None = None,
        limit: int = 100,
    ) -> list[StatusIncident]:
        """List incidents on a status page.

        Args:
            page_id: Page ID (uses default if not specified)
            status: Filter by status
            limit: Maximum number of incidents to return

        Returns:
            List of incidents
        """
        if not self.is_configured:
            raise ValueError("Statuspage integration not configured")

        client = await self._get_client()
        pid = self._get_page_id(page_id)

        params: dict[str, Any] = {"limit": limit}
        if status:
            params["q"] = f"status:{status.value}"

        response = await client.get(f"/pages/{pid}/incidents", params=params)
        response.raise_for_status()

        incidents = []
        for inc_data in response.json():
            incidents.append(self._parse_incident(inc_data, pid))

        return incidents

    async def list_unresolved_incidents(
        self, page_id: str | None = None
    ) -> list[StatusIncident]:
        """List all unresolved incidents.

        Args:
            page_id: Page ID (uses default if not specified)

        Returns:
            List of unresolved incidents
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        response = await client.get(f"/pages/{pid}/incidents/unresolved")
        response.raise_for_status()

        return [self._parse_incident(inc, pid) for inc in response.json()]

    async def get_incident(
        self, incident_id: str, page_id: str | None = None
    ) -> StatusIncident:
        """Get a specific incident.

        Args:
            incident_id: Incident ID
            page_id: Page ID (uses default if not specified)

        Returns:
            Incident details
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        response = await client.get(f"/pages/{pid}/incidents/{incident_id}")
        response.raise_for_status()

        return self._parse_incident(response.json(), pid)

    async def create_incident(
        self,
        name: str,
        status: IncidentStatus = IncidentStatus.INVESTIGATING,
        impact: IncidentImpact = IncidentImpact.NONE,
        body: str | None = None,
        component_ids: list[str] | None = None,
        component_statuses: dict[str, ComponentStatus] | None = None,
        deliver_notifications: bool = True,
        page_id: str | None = None,
    ) -> StatusIncident:
        """Create a new incident.

        Args:
            name: Incident name/title
            status: Initial status
            impact: Impact level
            body: Initial update body
            component_ids: List of affected component IDs
            component_statuses: Component ID to status mapping
            deliver_notifications: Whether to send notifications
            page_id: Page ID (uses default if not specified)

        Returns:
            Created incident
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        payload: dict[str, Any] = {
            "incident": {
                "name": name,
                "status": status.value,
                "impact_override": impact.value,
                "deliver_notifications": deliver_notifications,
            }
        }

        if body:
            payload["incident"]["body"] = body

        if component_ids:
            payload["incident"]["component_ids"] = component_ids

        if component_statuses:
            payload["incident"]["components"] = {
                cid: status.value for cid, status in component_statuses.items()
            }

        logger.info(
            "statuspage_creating_incident",
            name=name,
            status=status.value,
            page_id=pid,
        )

        response = await client.post(f"/pages/{pid}/incidents", json=payload)
        response.raise_for_status()

        incident = self._parse_incident(response.json(), pid)

        logger.info(
            "statuspage_incident_created",
            incident_id=incident.id,
            name=name,
            shortlink=incident.shortlink,
        )

        return incident

    async def update_incident(
        self,
        incident_id: str,
        status: IncidentStatus | None = None,
        impact: IncidentImpact | None = None,
        body: str | None = None,
        component_statuses: dict[str, ComponentStatus] | None = None,
        deliver_notifications: bool = True,
        page_id: str | None = None,
    ) -> StatusIncident:
        """Update an existing incident.

        Args:
            incident_id: Incident ID to update
            status: New status (if changing)
            impact: New impact level (if changing)
            body: Update message body
            component_statuses: Updated component statuses
            deliver_notifications: Whether to send notifications
            page_id: Page ID (uses default if not specified)

        Returns:
            Updated incident
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        payload: dict[str, Any] = {
            "incident": {"deliver_notifications": deliver_notifications}
        }

        if status:
            payload["incident"]["status"] = status.value
        if impact:
            payload["incident"]["impact_override"] = impact.value
        if body:
            payload["incident"]["body"] = body
        if component_statuses:
            payload["incident"]["components"] = {
                cid: s.value for cid, s in component_statuses.items()
            }

        logger.info(
            "statuspage_updating_incident",
            incident_id=incident_id,
            status=status.value if status else None,
        )

        response = await client.patch(
            f"/pages/{pid}/incidents/{incident_id}",
            json=payload,
        )
        response.raise_for_status()

        return self._parse_incident(response.json(), pid)

    async def resolve_incident(
        self,
        incident_id: str,
        body: str | None = None,
        deliver_notifications: bool = True,
        page_id: str | None = None,
    ) -> StatusIncident:
        """Resolve an incident.

        Args:
            incident_id: Incident ID to resolve
            body: Resolution message
            deliver_notifications: Whether to send notifications
            page_id: Page ID (uses default if not specified)

        Returns:
            Resolved incident
        """
        return await self.update_incident(
            incident_id=incident_id,
            status=IncidentStatus.RESOLVED,
            body=body,
            deliver_notifications=deliver_notifications,
            page_id=page_id,
        )

    async def delete_incident(
        self, incident_id: str, page_id: str | None = None
    ) -> bool:
        """Delete an incident.

        Args:
            incident_id: Incident ID to delete
            page_id: Page ID (uses default if not specified)

        Returns:
            True if deleted successfully
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        response = await client.delete(f"/pages/{pid}/incidents/{incident_id}")
        response.raise_for_status()

        logger.info("statuspage_incident_deleted", incident_id=incident_id)
        return True

    def _parse_incident(self, data: dict, page_id: str) -> StatusIncident:
        """Parse incident data from API response."""
        # Parse component statuses
        components = {}
        for comp in data.get("components", []):
            components[comp["id"]] = ComponentStatus(
                comp.get("status", "operational")
            )

        # Parse updates
        updates = []
        for update_data in data.get("incident_updates", []):
            updates.append(
                StatusUpdate(
                    id=update_data["id"],
                    incident_id=data["id"],
                    status=IncidentStatus(update_data["status"]),
                    body=update_data.get("body", ""),
                    created_at=self._parse_datetime(update_data.get("created_at")),
                    updated_at=self._parse_datetime(update_data.get("updated_at")),
                )
            )

        return StatusIncident(
            id=data["id"],
            page_id=page_id,
            name=data["name"],
            status=IncidentStatus(data.get("status", "investigating")),
            impact=IncidentImpact(data.get("impact", "none")),
            shortlink=data.get("shortlink"),
            created_at=self._parse_datetime(data.get("created_at")),
            updated_at=self._parse_datetime(data.get("updated_at")),
            resolved_at=self._parse_datetime(data.get("resolved_at")),
            monitoring_at=self._parse_datetime(data.get("monitoring_at")),
            component_ids=[c["id"] for c in data.get("components", [])],
            components=components,
            incident_updates=updates,
        )

    # ==================== Metrics Operations ====================

    async def get_component_uptime(
        self,
        component_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page_id: str | None = None,
    ) -> UptimeMetrics:
        """Get uptime metrics for a component.

        Args:
            component_id: Component ID
            start_date: Start of period (default: 30 days ago)
            end_date: End of period (default: now)
            page_id: Page ID (uses default if not specified)

        Returns:
            Uptime metrics for the component
        """
        client = await self._get_client()
        pid = self._get_page_id(page_id)

        # Default to last 30 days
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Get component details for name
        component = await self.get_component(component_id, pid)

        # Get historical incidents affecting this component
        all_incidents = await self.list_incidents(pid, limit=500)
        component_incidents = [
            inc for inc in all_incidents if component_id in inc.component_ids
        ]

        # Calculate downtime from incidents
        total_downtime_minutes = 0.0
        incident_count = 0
        resolution_times = []

        for incident in component_incidents:
            if not incident.created_at:
                continue

            # Check if incident is within our date range
            if incident.created_at < start_date:
                continue
            if incident.created_at > end_date:
                continue

            incident_count += 1

            if incident.resolved_at:
                duration = (incident.resolved_at - incident.created_at).total_seconds()
                total_downtime_minutes += duration / 60
                resolution_times.append(duration / 60)

        # Calculate uptime percentage
        total_period_minutes = (end_date - start_date).total_seconds() / 60
        uptime_percentage = 100.0
        if total_period_minutes > 0:
            uptime_percentage = max(
                0.0,
                100.0 - (total_downtime_minutes / total_period_minutes * 100),
            )

        avg_resolution = None
        if resolution_times:
            avg_resolution = sum(resolution_times) / len(resolution_times)

        return UptimeMetrics(
            component_id=component_id,
            component_name=component.name,
            uptime_percentage=round(uptime_percentage, 4),
            downtime_minutes=round(total_downtime_minutes, 2),
            total_incidents=incident_count,
            avg_resolution_minutes=round(avg_resolution, 2) if avg_resolution else None,
            period_start=start_date,
            period_end=end_date,
        )

    # ==================== Helpers ====================

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        """Parse ISO datetime string."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None


# Module-level client instance
_statuspage_client: StatuspageClient | None = None


def get_statuspage_client() -> StatuspageClient:
    """Get the Statuspage client singleton."""
    global _statuspage_client
    if _statuspage_client is None:
        _statuspage_client = StatuspageClient()
    return _statuspage_client
