"""Integration health checks for services in the catalog."""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC

import structlog

from ..config import Settings
from .models import ServiceUpdate
from .store import ServiceCatalogStore

logger = structlog.get_logger()


class ServiceIntegrationHealthChecker:
    """Periodic checker for PagerDuty/Datadog/Kubernetes integration health."""

    def __init__(
        self,
        settings: Settings,
        store: ServiceCatalogStore,
        interval_seconds: int = 300,
    ):
        self.settings = settings
        self.store = store
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start periodic health checks."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("service_integration_health_checker_started")

    async def stop(self) -> None:
        """Stop periodic health checks."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("service_integration_health_checker_stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.check_once()
            except Exception as exc:
                logger.warning(
                    "service_integration_health_checker_failed", error=str(exc)
                )
            await asyncio.sleep(self.interval_seconds)

    async def check_once(self, tenant_slug: str = "default") -> int:
        """Run one full integration health pass. Returns services checked."""
        services = await self.store.list_services(tenant_slug=tenant_slug)
        checked = 0

        for service in services:
            integration_state = self._evaluate_service_integrations(
                service.metadata or {}
            )
            health_block = {
                "checked_at": datetime.now(UTC).isoformat(),
                "integrations": integration_state,
            }
            metadata = dict(service.metadata or {})
            metadata["integration_health"] = health_block

            await self.store.update_service(
                service.id,
                request=ServiceUpdate(metadata=metadata),
                tenant_slug=tenant_slug,
            )
            checked += 1

        logger.info("service_integration_health_checked", checked=checked)
        return checked

    def _evaluate_service_integrations(self, metadata: dict) -> dict[str, str]:
        integrations = {}

        pagerduty_meta = metadata.get("pagerduty")
        if pagerduty_meta:
            integrations["pagerduty"] = (
                "ok" if bool(self.settings.pagerduty_api_key) else "missing_credentials"
            )

        datadog_meta = metadata.get("datadog")
        if datadog_meta:
            integrations["datadog"] = (
                "ok"
                if bool(self.settings.datadog_api_key and self.settings.datadog_app_key)
                else "missing_credentials"
            )

        kubernetes_meta = metadata.get("kubernetes")
        if kubernetes_meta:
            integrations["kubernetes"] = "ok"

        if not integrations:
            integrations["catalog"] = "ok"

        return integrations


_service_health_checker: ServiceIntegrationHealthChecker | None = None


def get_service_health_checker(
    settings: Settings,
    store: ServiceCatalogStore,
    interval_seconds: int = 300,
) -> ServiceIntegrationHealthChecker:
    """Get singleton integration health checker."""
    global _service_health_checker
    if _service_health_checker is None:
        _service_health_checker = ServiceIntegrationHealthChecker(
            settings=settings,
            store=store,
            interval_seconds=interval_seconds,
        )
    return _service_health_checker


async def start_service_health_checker(
    settings: Settings,
    store: ServiceCatalogStore,
    interval_seconds: int = 300,
) -> ServiceIntegrationHealthChecker:
    """Start singleton integration health checker."""
    checker = get_service_health_checker(
        settings=settings,
        store=store,
        interval_seconds=interval_seconds,
    )
    await checker.start()
    return checker


async def stop_service_health_checker() -> None:
    """Stop singleton integration health checker."""
    global _service_health_checker
    if _service_health_checker:
        await _service_health_checker.stop()
        _service_health_checker = None
