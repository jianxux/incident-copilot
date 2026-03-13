"""REST API routes for persistent service catalog."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..config import get_settings
from .discovery import ServiceCatalogDiscovery
from .importer import ServiceCatalogImporter
from .models import (
    Service,
    ServiceCreate,
    ServiceDependency,
    ServiceDependencyCreate,
    ServiceDependencyUpdate,
    ServiceUpdate,
)
from .store import ServiceCatalogStore, get_service_catalog_store

router = APIRouter(prefix="/api/services", tags=["services"])


def get_store() -> ServiceCatalogStore:
    """Dependency injection for service catalog store."""
    return get_service_catalog_store()


StoreDep = Annotated[ServiceCatalogStore, Depends(get_store)]


@router.get("", response_model=list[Service])
async def list_services(
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
    team: str | None = None,
    criticality: str | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> list[Service]:
    """List services in the catalog."""
    return await store.list_services(
        tenant_slug=tenant,
        team=team,
        criticality=criticality,
        environment=environment,
        region=region,
    )


@router.post("", response_model=Service, status_code=201)
async def create_service(
    request: ServiceCreate,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> Service:
    """Create a service in the catalog."""
    return await store.create_service(request, tenant_slug=tenant)


@router.get("/{service_id}", response_model=Service)
async def get_service(
    service_id: str,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> Service:
    """Get one service by id, key, or name."""
    result = await store.get_service(service_id, tenant_slug=tenant)
    if not result:
        raise HTTPException(status_code=404, detail=f"Service {service_id} not found")
    return result


@router.put("/{service_id}", response_model=Service)
async def update_service(
    service_id: str,
    request: ServiceUpdate,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> Service:
    """Update service metadata and environments."""
    result = await store.update_service(service_id, request, tenant_slug=tenant)
    if not result:
        raise HTTPException(status_code=404, detail=f"Service {service_id} not found")
    return result


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    service_id: str,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> None:
    """Delete a service and its dependency edges."""
    deleted = await store.delete_service(service_id, tenant_slug=tenant)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Service {service_id} not found")


@router.get("/{service_id}/dependencies", response_model=list[ServiceDependency])
async def list_service_dependencies(
    service_id: str,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
    direction: str = Query("all", pattern="^(all|upstream|downstream)$"),
) -> list[ServiceDependency]:
    """List dependencies for a service."""
    if direction == "upstream":
        return await store.list_dependencies(
            tenant_slug=tenant,
            target_service_id=service_id,
        )
    if direction == "downstream":
        return await store.list_dependencies(
            tenant_slug=tenant,
            source_service_id=service_id,
        )

    upstream = await store.list_dependencies(
        tenant_slug=tenant,
        target_service_id=service_id,
    )
    downstream = await store.list_dependencies(
        tenant_slug=tenant,
        source_service_id=service_id,
    )

    edges = {dep.id: dep for dep in upstream + downstream if dep.id}
    return list(edges.values())


@router.post(
    "/{service_id}/dependencies", response_model=ServiceDependency, status_code=201
)
async def create_service_dependency(
    service_id: str,
    request: ServiceDependencyCreate,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> ServiceDependency:
    """Create a dependency from source service to target service."""
    result = await store.create_dependency(
        source_service_id=service_id,
        request=request,
        tenant_slug=tenant,
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Could not create dependency. Ensure both services exist.",
        )
    return result


@router.put(
    "/{service_id}/dependencies/{dependency_id}",
    response_model=ServiceDependency,
)
async def update_service_dependency(
    service_id: str,
    dependency_id: str,
    request: ServiceDependencyUpdate,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> ServiceDependency:
    """Update dependency edge metrics and metadata."""
    dep = await store.get_dependency(dependency_id, tenant_slug=tenant)
    if not dep or dep.source_service_id != service_id:
        raise HTTPException(status_code=404, detail="Dependency not found")

    updated = await store.update_dependency(
        dependency_id,
        request=request,
        tenant_slug=tenant,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Dependency not found")
    return updated


@router.delete("/{service_id}/dependencies/{dependency_id}", status_code=204)
async def delete_service_dependency(
    service_id: str,
    dependency_id: str,
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> None:
    """Delete one dependency edge for a source service."""
    dep = await store.get_dependency(dependency_id, tenant_slug=tenant)
    if not dep or dep.source_service_id != service_id:
        raise HTTPException(status_code=404, detail="Dependency not found")

    deleted = await store.delete_dependency(dependency_id, tenant_slug=tenant)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dependency not found")


@router.post("/import/json")
async def import_services_json(
    payload: dict[str, Any] | list[dict[str, Any]],
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> dict[str, int]:
    """Bulk import services from JSON payload."""
    importer = ServiceCatalogImporter(store)
    return await importer.import_json(json.dumps(payload), tenant_slug=tenant)


@router.post("/import/csv")
async def import_services_csv(
    file: UploadFile = File(...),
    store: ServiceCatalogStore = Depends(get_store),
    tenant: str = Query("default", description="Tenant slug"),
) -> dict[str, int]:
    """Bulk import services from CSV upload."""
    payload = (await file.read()).decode("utf-8")
    importer = ServiceCatalogImporter(store)
    return await importer.import_csv(payload, tenant_slug=tenant)


@router.post("/discovery/pagerduty")
async def discover_pagerduty(
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> dict[str, int]:
    """Auto-discover services from PagerDuty service catalog."""
    discovery = ServiceCatalogDiscovery(get_settings(), store)
    return await discovery.discover_from_pagerduty(tenant_slug=tenant)


@router.post("/discovery/datadog")
async def discover_datadog(
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> dict[str, int]:
    """Auto-discover services from Datadog APM inventory."""
    discovery = ServiceCatalogDiscovery(get_settings(), store)
    return await discovery.discover_from_datadog_apm(tenant_slug=tenant)


@router.post("/discovery/kubernetes")
async def discover_kubernetes(
    store: StoreDep,
    tenant: str = Query("default", description="Tenant slug"),
) -> dict[str, int]:
    """Auto-discover services from Kubernetes API."""
    discovery = ServiceCatalogDiscovery(get_settings(), store)
    return await discovery.discover_from_kubernetes(tenant_slug=tenant)
