"""Status Page Service - Core business logic."""

import logging
from datetime import UTC, datetime
from typing import Any

from .models import (
    Component,
    ComponentStatus,
    MaintenanceWindow,
    StatusPageConfig,
    StatusPageIncident,
    StatusPageMetrics,
    StatusPageProvider,
    StatusUpdate,
    SyncResult,
)
from .providers.atlassian import AtlassianProvider
from .providers.cachet import CachetProvider
from .providers.statusio import StatusIOProvider

logger = logging.getLogger(__name__)


class StatusPageService:
    """Central service for status page operations."""

    def __init__(self):
        self._configs: dict[str, StatusPageConfig] = {}
        self._providers: dict[str, Any] = {}
        self._incident_mapping: dict[str, dict[str, str]] = {}

    def _get_provider(self, config: StatusPageConfig):
        if config.id not in self._providers:
            providers = {
                StatusPageProvider.ATLASSIAN: AtlassianProvider,
                StatusPageProvider.STATUSIO: StatusIOProvider,
                StatusPageProvider.CACHET: CachetProvider,
            }
            self._providers[config.id] = providers[config.provider](config)
        return self._providers[config.id]

    async def add_config(self, config: StatusPageConfig) -> bool:
        provider = self._get_provider(config)
        if await provider.validate_credentials():
            self._configs[config.id] = config
            return True
        return False

    async def remove_config(self, config_id: str) -> bool:
        if config_id in self._configs:
            if config_id in self._providers:
                await self._providers[config_id].close()
                del self._providers[config_id]
            del self._configs[config_id]
            return True
        return False

    def get_config(self, config_id: str) -> StatusPageConfig | None:
        return self._configs.get(config_id)

    def list_configs(self) -> list[StatusPageConfig]:
        return list(self._configs.values())

    async def sync_components(self, config_id: str) -> SyncResult:
        config = self._configs.get(config_id)
        if not config:
            return SyncResult(success=False, errors=["Config not found"])
        try:
            components = await self._get_provider(config).get_components()
            return SyncResult(success=True, synced_components=len(components))
        except Exception as e:
            return SyncResult(success=False, errors=[str(e)])

    async def get_components(self, config_id: str) -> list[Component]:
        config = self._configs.get(config_id)
        return await self._get_provider(config).get_components() if config else []

    async def update_component_status(
        self, config_id: str, component_id: str, status: ComponentStatus
    ) -> Component | None:
        config = self._configs.get(config_id)
        return (
            await self._get_provider(config).update_component(component_id, status)
            if config
            else None
        )

    async def update_service_status(
        self, service_id: str, status: ComponentStatus
    ) -> dict[str, Component]:
        results = {}
        for config_id, config in self._configs.items():
            if config.enabled and (
                component_id := config.component_mapping.get(service_id)
            ):
                try:
                    results[config_id] = await self._get_provider(
                        config
                    ).update_component(component_id, status)
                except Exception as e:
                    logger.error(f"Failed to update {service_id} on {config_id}: {e}")
        return results

    async def create_incident(
        self, config_id: str, incident: StatusPageIncident
    ) -> StatusPageIncident | None:
        config = self._configs.get(config_id)
        return (
            await self._get_provider(config).create_incident(incident)
            if config
            else None
        )

    async def create_incident_all(
        self, incident: StatusPageIncident, internal_id: str
    ) -> dict[str, StatusPageIncident]:
        results = {}
        self._incident_mapping[internal_id] = {}
        for config_id, config in self._configs.items():
            if not config.enabled or not config.auto_sync:
                continue
            try:
                mapped = incident.model_copy()
                mapped.component_ids = [
                    config.component_mapping[sid]
                    for sid in incident.component_ids
                    if sid in config.component_mapping
                ]
                created = await self._get_provider(config).create_incident(mapped)
                results[config_id] = created
                self._incident_mapping[internal_id][config_id] = (
                    created.external_id or created.id
                )
            except Exception as e:
                logger.error(f"Failed to create incident on {config_id}: {e}")
        return results

    async def update_incident(
        self, config_id: str, incident_id: str, update: StatusUpdate
    ) -> StatusPageIncident | None:
        config = self._configs.get(config_id)
        return (
            await self._get_provider(config).update_incident(incident_id, update)
            if config
            else None
        )

    async def update_incident_all(
        self, internal_id: str, update: StatusUpdate
    ) -> dict[str, StatusPageIncident]:
        results = {}
        for config_id, external_id in self._incident_mapping.get(
            internal_id, {}
        ).items():
            config = self._configs.get(config_id)
            if config and config.enabled:
                try:
                    results[config_id] = await self._get_provider(
                        config
                    ).update_incident(external_id, update)
                except Exception as e:
                    logger.error(f"Failed to update on {config_id}: {e}")
        return results

    async def resolve_incident(
        self, config_id: str, incident_id: str, message: str
    ) -> StatusPageIncident | None:
        config = self._configs.get(config_id)
        return (
            await self._get_provider(config).resolve_incident(incident_id, message)
            if config
            else None
        )

    async def resolve_incident_all(
        self, internal_id: str, message: str
    ) -> dict[str, StatusPageIncident]:
        results = {}
        for config_id, external_id in self._incident_mapping.get(
            internal_id, {}
        ).items():
            config = self._configs.get(config_id)
            if config and config.enabled:
                try:
                    results[config_id] = await self._get_provider(
                        config
                    ).resolve_incident(external_id, message)
                except Exception as e:
                    logger.error(f"Failed to resolve on {config_id}: {e}")
        self._incident_mapping.pop(internal_id, None)
        return results

    async def get_active_incidents(self, config_id: str) -> list[StatusPageIncident]:
        config = self._configs.get(config_id)
        return await self._get_provider(config).get_incidents(True) if config else []

    async def create_maintenance(
        self, config_id: str, maintenance: MaintenanceWindow
    ) -> MaintenanceWindow | None:
        config = self._configs.get(config_id)
        return (
            await self._get_provider(config).create_maintenance(maintenance)
            if config
            else None
        )

    async def get_scheduled_maintenances(
        self, config_id: str
    ) -> list[MaintenanceWindow]:
        config = self._configs.get(config_id)
        return (
            await self._get_provider(config).get_scheduled_maintenances()
            if config
            else []
        )

    async def get_metrics(self, config_id: str) -> StatusPageMetrics:
        config = self._configs.get(config_id)
        if not config:
            return StatusPageMetrics(config_id=config_id)
        try:
            components = await self._get_provider(config).get_components()
            incidents = await self._get_provider(config).get_incidents(True)
            return StatusPageMetrics(
                config_id=config_id,
                total_components=len(components),
                operational_components=sum(
                    1 for c in components if c.status == ComponentStatus.OPERATIONAL
                ),
                degraded_components=sum(
                    1 for c in components if c.status == ComponentStatus.DEGRADED
                ),
                outage_components=sum(
                    1
                    for c in components
                    if c.status
                    in (ComponentStatus.PARTIAL_OUTAGE, ComponentStatus.MAJOR_OUTAGE)
                ),
                active_incidents=len(incidents),
                last_sync=datetime.now(UTC),
            )
        except Exception:
            return StatusPageMetrics(config_id=config_id)

    def get_incident_external_id(self, internal_id: str, config_id: str) -> str | None:
        return self._incident_mapping.get(internal_id, {}).get(config_id)

    async def close(self):
        for p in self._providers.values():
            await p.close()
        self._providers.clear()


_service: StatusPageService | None = None


def get_statuspage_service() -> StatusPageService:
    global _service
    if _service is None:
        _service = StatusPageService()
    return _service
