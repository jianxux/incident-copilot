"""Status Page Service - Core business logic."""

import logging
from datetime import datetime
from typing import Any

from .models import (
    Component,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    MaintenanceWindow,
    SEVERITY_TO_COMPONENT_STATUS,
    SEVERITY_TO_IMPACT,
    StatusPageConfig,
    StatusPageIncident,
    StatusPageMetrics,
    StatusPageProvider,
    StatusUpdate,
    SyncResult,
)
from .providers.atlassian import AtlassianProvider
from .providers.cachet import CachetProvider
from .providers.base import BaseStatusPageProvider
from .providers.statusio import StatusIOProvider

logger = logging.getLogger(__name__)


class StatusPageService:
    """Central service for status page operations."""

    def __init__(self):
        self._configs: dict[str, StatusPageConfig] = {}
        self._providers: dict[str, BaseStatusPageProvider] = {}
        self._incident_mapping: dict[str, dict[str, str]] = {}  # incident_id -> {config_id: external_id}

    def _get_provider(self, config: StatusPageConfig) -> BaseStatusPageProvider:
        """Get or create provider for config."""
        if config.id not in self._providers:
            if config.provider == StatusPageProvider.ATLASSIAN:
                self._providers[config.id] = AtlassianProvider(config)
            elif config.provider == StatusPageProvider.STATUSIO:
                self._providers[config.id] = StatusIOProvider(config)
            elif config.provider == StatusPageProvider.CACHET:
                self._providers[config.id] = CachetProvider(config)
            else:
                raise ValueError(f"Unknown provider: {config.provider}")
        return self._providers[config.id]

    async def add_config(self, config: StatusPageConfig) -> bool:
        """Add and validate a status page configuration."""
        provider = self._get_provider(config)
        if await provider.validate_credentials():
            self._configs[config.id] = config
            logger.info(f"Added status page config: {config.name}")
            return True
        logger.warning(f"Failed to validate credentials for: {config.name}")
        return False

    async def remove_config(self, config_id: str) -> bool:
        """Remove a status page configuration."""
        if config_id in self._configs:
            if config_id in self._providers:
                await self._providers[config_id].close()
                del self._providers[config_id]
            del self._configs[config_id]
            return True
        return False

    def get_config(self, config_id: str) -> StatusPageConfig | None:
        """Get configuration by ID."""
        return self._configs.get(config_id)

    def list_configs(self) -> list[StatusPageConfig]:
        """List all configurations."""
        return list(self._configs.values())

    async def sync_components(self, config_id: str) -> SyncResult:
        """Sync components from status page."""
        config = self._configs.get(config_id)
        if not config:
            return SyncResult(success=False, errors=["Config not found"])

        try:
            provider = self._get_provider(config)
            components = await provider.get_components()
            return SyncResult(success=True, synced_components=len(components))
        except Exception as e:
            logger.error(f"Failed to sync components: {e}")
            return SyncResult(success=False, errors=[str(e)])

    async def get_components(self, config_id: str) -> list[Component]:
        """Get components for a status page."""
        config = self._configs.get(config_id)
        if not config:
            return []
        provider = self._get_provider(config)
        return await provider.get_components()

    async def update_component_status(
        self,
        config_id: str,
        component_id: str,
        status: ComponentStatus,
    ) -> Component | None:
        """Update a component's status."""
        config = self._configs.get(config_id)
        if not config:
            return None
        provider = self._get_provider(config)
        return await provider.update_component(component_id, status)

    async def update_service_status(
        self,
        service_id: str,
        status: ComponentStatus,
    ) -> dict[str, Component]:
        """Update status for a service across all configured status pages."""
        results = {}
        for config_id, config in self._configs.items():
            if not config.enabled:
                continue
            component_id = config.component_mapping.get(service_id)
            if component_id:
                try:
                    provider = self._get_provider(config)
                    component = await provider.update_component(component_id, status)
                    results[config_id] = component
                except Exception as e:
                    logger.error(f"Failed to update {service_id} on {config_id}: {e}")
        return results

    async def create_incident(
        self,
        config_id: str,
        incident: StatusPageIncident,
    ) -> StatusPageIncident | None:
        """Create an incident on a status page."""
        config = self._configs.get(config_id)
        if not config:
            return None
        provider = self._get_provider(config)
        return await provider.create_incident(incident)

    async def create_incident_all(
        self,
        incident: StatusPageIncident,
        internal_incident_id: str,
    ) -> dict[str, StatusPageIncident]:
        """Create incident on all enabled status pages."""
        results = {}
        self._incident_mapping[internal_incident_id] = {}

        for config_id, config in self._configs.items():
            if not config.enabled or not config.auto_sync:
                continue
            try:
                # Map service IDs to component IDs
                mapped_incident = incident.model_copy()
                mapped_component_ids = []
                for service_id in incident.component_ids:
                    if service_id in config.component_mapping:
                        mapped_component_ids.append(config.component_mapping[service_id])
                mapped_incident.component_ids = mapped_component_ids

                provider = self._get_provider(config)
                created = await provider.create_incident(mapped_incident)
                results[config_id] = created
                self._incident_mapping[internal_incident_id][config_id] = created.external_id or created.id
            except Exception as e:
                logger.error(f"Failed to create incident on {config_id}: {e}")
        return results

    async def update_incident(
        self,
        config_id: str,
        incident_id: str,
        update: StatusUpdate,
    ) -> StatusPageIncident | None:
        """Update an incident on a status page."""
        config = self._configs.get(config_id)
        if not config:
            return None
        provider = self._get_provider(config)
        return await provider.update_incident(incident_id, update)

    async def update_incident_all(
        self,
        internal_incident_id: str,
        update: StatusUpdate,
    ) -> dict[str, StatusPageIncident]:
        """Update incident on all status pages where it exists."""
        results = {}
        mapping = self._incident_mapping.get(internal_incident_id, {})

        for config_id, external_id in mapping.items():
            config = self._configs.get(config_id)
            if not config or not config.enabled:
                continue
            try:
                provider = self._get_provider(config)
                updated = await provider.update_incident(external_id, update)
                results[config_id] = updated
            except Exception as e:
                logger.error(f"Failed to update incident on {config_id}: {e}")
        return results

    async def resolve_incident(
        self,
        config_id: str,
        incident_id: str,
        message: str,
    ) -> StatusPageIncident | None:
        """Resolve an incident on a status page."""
        config = self._configs.get(config_id)
        if not config:
            return None
        provider = self._get_provider(config)
        return await provider.resolve_incident(incident_id, message)

    async def resolve_incident_all(
        self,
        internal_incident_id: str,
        message: str,
    ) -> dict[str, StatusPageIncident]:
        """Resolve incident on all status pages."""
        results = {}
        mapping = self._incident_mapping.get(internal_incident_id, {})

        for config_id, external_id in mapping.items():
            config = self._configs.get(config_id)
            if not config or not config.enabled:
                continue
            try:
                provider = self._get_provider(config)
                resolved = await provider.resolve_incident(external_id, message)
                results[config_id] = resolved
            except Exception as e:
                logger.error(f"Failed to resolve incident on {config_id}: {e}")

        # Clean up mapping
        if internal_incident_id in self._incident_mapping:
            del self._incident_mapping[internal_incident_id]

        return results

    async def get_active_incidents(self, config_id: str) -> list[StatusPageIncident]:
        """Get active incidents from a status page."""
        config = self._configs.get(config_id)
        if not config:
            return []
        provider = self._get_provider(config)
        return await provider.get_incidents(unresolved_only=True)

    async def create_maintenance(
        self,
        config_id: str,
        maintenance: MaintenanceWindow,
    ) -> MaintenanceWindow | None:
        """Create scheduled maintenance."""
        config = self._configs.get(config_id)
        if not config:
            return None
        provider = self._get_provider(config)
        return await provider.create_maintenance(maintenance)

    async def get_scheduled_maintenances(self, config_id: str) -> list[MaintenanceWindow]:
        """Get scheduled maintenances."""
        config = self._configs.get(config_id)
        if not config:
            return []
        provider = self._get_provider(config)
        return await provider.get_scheduled_maintenances()

    async def get_metrics(self, config_id: str) -> StatusPageMetrics:
        """Get metrics for a status page."""
        config = self._configs.get(config_id)
        if not config:
            return StatusPageMetrics(config_id=config_id)

        try:
            provider = self._get_provider(config)
            components = await provider.get_components()
            incidents = await provider.get_incidents(unresolved_only=True)
            maintenances = await provider.get_scheduled_maintenances()

            operational = sum(1 for c in components if c.status == ComponentStatus.OPERATIONAL)
            degraded = sum(1 for c in components if c.status == ComponentStatus.DEGRADED)
            outage = sum(
                1 for c in components
                if c.status in (ComponentStatus.PARTIAL_OUTAGE, ComponentStatus.MAJOR_OUTAGE)
            )

            return StatusPageMetrics(
                config_id=config_id,
                total_components=len(components),
                operational_components=operational,
                degraded_components=degraded,
                outage_components=outage,
                active_incidents=len(incidents),
                scheduled_maintenances=len(maintenances),
                last_sync=datetime.utcnow(),
            )
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return StatusPageMetrics(config_id=config_id)

    def get_incident_external_id(self, internal_id: str, config_id: str) -> str | None:
        """Get external incident ID for a config."""
        return self._incident_mapping.get(internal_id, {}).get(config_id)

    def map_severity_to_impact(self, severity: str) -> IncidentImpact:
        """Map internal severity to status page impact."""
        return SEVERITY_TO_IMPACT.get(severity.lower(), IncidentImpact.MINOR)

    def map_severity_to_component_status(self, severity: str) -> ComponentStatus:
        """Map internal severity to component status."""
        return SEVERITY_TO_COMPONENT_STATUS.get(severity.lower(), ComponentStatus.DEGRADED)

    async def close(self) -> None:
        """Close all providers."""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()


# Singleton instance
_service: StatusPageService | None = None


def get_statuspage_service() -> StatusPageService:
    """Get or create the status page service singleton."""
    global _service
    if _service is None:
        _service = StatusPageService()
    return _service
