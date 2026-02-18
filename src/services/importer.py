"""Bulk import utilities for service catalog."""

from __future__ import annotations

import csv
import io
import json

from .models import ServiceCreate, ServiceEnvironment
from .store import ServiceCatalogStore


class ServiceCatalogImporter:
    """Import service catalog entries from JSON, CSV, and integrations."""

    def __init__(self, store: ServiceCatalogStore):
        self._store = store

    async def import_json(self, payload: str, tenant_slug: str = "default") -> dict[str, int]:
        """Import list of services from JSON payload."""
        data = json.loads(payload)
        if isinstance(data, dict):
            services = data.get("services", [])
        else:
            services = data

        created = 0
        failed = 0
        for item in services:
            try:
                envs = [ServiceEnvironment(service_id=item.get("id") or item["name"], **e) for e in item.get("environments", [])]
                request = ServiceCreate(
                    id=item.get("id"),
                    name=item["name"],
                    description=item.get("description"),
                    team=item.get("team"),
                    owner_email=item.get("owner_email"),
                    criticality=item.get("criticality", "medium"),
                    health=item.get("health", "unknown"),
                    tags=item.get("tags", []),
                    critical_user_journey=item.get("critical_user_journey", False),
                    repo_url=item.get("repo_url"),
                    dashboard_url=item.get("dashboard_url"),
                    runbook_url=item.get("runbook_url"),
                    metadata=item.get("metadata", {}),
                    environments=envs,
                )
                await self._store.create_service(request, tenant_slug=tenant_slug)
                created += 1
            except Exception:
                failed += 1

        return {"created": created, "failed": failed, "total": len(services)}

    async def import_csv(self, payload: str, tenant_slug: str = "default") -> dict[str, int]:
        """Import services from CSV payload."""
        reader = csv.DictReader(io.StringIO(payload))
        created = 0
        failed = 0
        total = 0

        for row in reader:
            total += 1
            try:
                tags = [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]
                environments: list[ServiceEnvironment] = []
                if row.get("environment"):
                    environments.append(
                        ServiceEnvironment(
                            service_id=row.get("id") or row["name"],
                            environment=row.get("environment") or "production",
                            region=row.get("region") or None,
                            cluster=row.get("cluster") or None,
                            namespace=row.get("namespace") or None,
                            version=row.get("version") or None,
                            is_primary=True,
                        )
                    )

                request = ServiceCreate(
                    id=row.get("id") or None,
                    name=row["name"],
                    description=row.get("description") or None,
                    team=row.get("team") or None,
                    owner_email=row.get("owner_email") or None,
                    criticality=(row.get("criticality") or "medium"),
                    health=(row.get("health") or "unknown"),
                    tags=tags,
                    critical_user_journey=(row.get("critical_user_journey") or "false").lower()
                    in {"1", "true", "yes"},
                    repo_url=row.get("repo_url") or None,
                    dashboard_url=row.get("dashboard_url") or None,
                    runbook_url=row.get("runbook_url") or None,
                    metadata={},
                    environments=environments,
                )
                await self._store.create_service(request, tenant_slug=tenant_slug)
                created += 1
            except Exception:
                failed += 1

        return {"created": created, "failed": failed, "total": total}
