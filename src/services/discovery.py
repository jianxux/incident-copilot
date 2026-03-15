"""External discovery sources for service catalog ingestion."""

from __future__ import annotations

import os
from datetime import datetime, UTC
from typing import Any

import httpx
import structlog

from ..config import Settings
from .models import ServiceCreate, ServiceEnvironment
from .store import ServiceCatalogStore

logger = structlog.get_logger()


class ServiceCatalogDiscovery:
    """Discover services from PagerDuty, Datadog APM, and Kubernetes."""

    def __init__(self, settings: Settings, store: ServiceCatalogStore):
        self.settings = settings
        self.store = store

    async def discover_from_pagerduty(
        self, tenant_slug: str = "default"
    ) -> dict[str, int]:
        """Ingest PagerDuty service catalog into the local catalog."""
        if not self.settings.pagerduty_api_key:
            return {"discovered": 0, "created": 0, "skipped": 0}

        headers = {
            "Authorization": f"Token token={self.settings.pagerduty_api_key}",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }
        created = 0
        skipped = 0

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    "https://api.pagerduty.com/services",
                    headers=headers,
                    params={"limit": 100},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("service_discovery_pagerduty_failed", error=str(exc))
            return {"discovered": 0, "created": 0, "skipped": 0}

        services = payload.get("services", [])
        for svc in services:
            name = svc.get("name")
            if not name:
                skipped += 1
                continue
            request = ServiceCreate(
                id=svc.get("id") or name,
                name=name,
                description=svc.get("description"),
                team=(svc.get("teams") or [{}])[0].get("summary"),
                metadata={
                    "pagerduty": {
                        "id": svc.get("id"),
                        "html_url": svc.get("html_url"),
                        "status": svc.get("status"),
                        "auto_discovered": True,
                    }
                },
            )
            await self.store.create_service(request, tenant_slug=tenant_slug)
            created += 1

        return {
            "discovered": len(services),
            "created": created,
            "skipped": skipped,
        }

    async def discover_from_datadog_apm(
        self, tenant_slug: str = "default"
    ) -> dict[str, int]:
        """Ingest Datadog APM service inventory."""
        if not self.settings.datadog_api_key or not self.settings.datadog_app_key:
            return {"discovered": 0, "created": 0, "skipped": 0}

        headers = {
            "DD-API-KEY": self.settings.datadog_api_key,
            "DD-APPLICATION-KEY": self.settings.datadog_app_key,
        }
        url = f"https://api.{self.settings.datadog_site}/api/v2/apm/services"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("service_discovery_datadog_failed", error=str(exc))
            return {"discovered": 0, "created": 0, "skipped": 0}

        created = 0
        skipped = 0
        data = payload.get("data", [])

        for item in data:
            attrs = item.get("attributes", {})
            name = attrs.get("service") or item.get("id")
            if not name:
                skipped += 1
                continue

            env_name = attrs.get("env") or "production"
            env = ServiceEnvironment(
                service_id=name,
                environment=env_name,
                version=attrs.get("version"),
                metadata={"source": "datadog_apm"},
                last_seen_at=datetime.now(UTC),
            )
            request = ServiceCreate(
                id=name,
                name=name,
                metadata={"datadog": attrs, "auto_discovered": True},
                environments=[env],
            )
            await self.store.create_service(request, tenant_slug=tenant_slug)
            created += 1

        return {"discovered": len(data), "created": created, "skipped": skipped}

    async def discover_from_kubernetes(
        self, tenant_slug: str = "default"
    ) -> dict[str, int]:
        """Ingest Kubernetes Services from in-cluster API."""
        api_host = os.getenv("KUBERNETES_SERVICE_HOST")
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        namespace_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"

        if not api_host or not os.path.exists(token_path):
            return {"discovered": 0, "created": 0, "skipped": 0}

        with open(token_path, encoding="utf-8") as token_file:
            token = token_file.read().strip()
        namespace = "default"
        if os.path.exists(namespace_path):
            with open(namespace_path, encoding="utf-8") as namespace_file:
                namespace = namespace_file.read().strip() or "default"

        base_url = f"https://{api_host}:443"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                verify=False,  # nosec B501
            ) as client:
                response = await client.get(
                    f"{base_url}/api/v1/services",
                    headers=headers,
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
        except Exception as exc:
            logger.warning("service_discovery_kubernetes_failed", error=str(exc))
            return {"discovered": 0, "created": 0, "skipped": 0}

        items = payload.get("items", [])
        created = 0
        skipped = 0

        for item in items:
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            name = metadata.get("name")
            if not name or name == "kubernetes":
                skipped += 1
                continue

            env = ServiceEnvironment(
                service_id=name,
                environment="production",
                region=os.getenv("KUBE_REGION"),
                cluster=os.getenv("KUBE_CLUSTER_NAME"),
                namespace=metadata.get("namespace") or namespace,
                version=(metadata.get("labels") or {}).get("app.kubernetes.io/version"),
                metadata={"type": spec.get("type")},
                last_seen_at=datetime.now(UTC),
            )
            request = ServiceCreate(
                id=name,
                name=name,
                team=(metadata.get("labels") or {}).get("team"),
                metadata={
                    "kubernetes": {
                        "labels": metadata.get("labels", {}),
                        "annotations": metadata.get("annotations", {}),
                        "cluster_ip": spec.get("clusterIP"),
                    },
                    "auto_discovered": True,
                },
                environments=[env],
            )
            await self.store.create_service(request, tenant_slug=tenant_slug)
            created += 1

        return {"discovered": len(items), "created": created, "skipped": skipped}
