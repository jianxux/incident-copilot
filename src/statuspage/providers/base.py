"""Base Status Page Provider."""

from abc import ABC, abstractmethod
from typing import Any

import httpx

from ..models import (
    Component,
    ComponentStatus,
    MaintenanceWindow,
    StatusPageConfig,
    StatusPageIncident,
    StatusUpdate,
)


class BaseStatusPageProvider(ABC):
    """Abstract base class for status page providers."""

    def __init__(self, config: StatusPageConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def get_components(self) -> list[Component]:
        """Fetch all components from the status page."""
        pass

    @abstractmethod
    async def update_component(self, component_id: str, status: ComponentStatus) -> Component:
        """Update a component's status."""
        pass

    @abstractmethod
    async def get_incidents(self, unresolved_only: bool = True) -> list[StatusPageIncident]:
        """Fetch incidents from the status page."""
        pass

    @abstractmethod
    async def create_incident(self, incident: StatusPageIncident) -> StatusPageIncident:
        """Create a new incident on the status page."""
        pass

    @abstractmethod
    async def update_incident(
        self, incident_id: str, update: StatusUpdate
    ) -> StatusPageIncident:
        """Update an existing incident."""
        pass

    @abstractmethod
    async def resolve_incident(self, incident_id: str, message: str) -> StatusPageIncident:
        """Resolve an incident."""
        pass

    @abstractmethod
    async def get_scheduled_maintenances(self) -> list[MaintenanceWindow]:
        """Fetch scheduled maintenances."""
        pass

    @abstractmethod
    async def create_maintenance(self, maintenance: MaintenanceWindow) -> MaintenanceWindow:
        """Create a scheduled maintenance."""
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Validate provider credentials."""
        pass

    def _build_headers(self) -> dict[str, str]:
        """Build request headers. Override in subclass."""
        return {"Content-Type": "application/json"}

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request."""
        headers = {**self._build_headers(), **kwargs.pop("headers", {})}
        response = await self.client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}
