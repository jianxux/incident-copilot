"""FastAPI routes for service dependency management."""

from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from .discovery import dependency_discovery
from .graph import DependencyGraph
from .models import (
    BlastRadiusResult,
    Dependency,
    DependencyCreateRequest,
    DependencyType,
    DependencyUpdateRequest,
    DiscoveryRequest,
    DiscoveryResult,
    Service,
    ServiceCatalogStats,
    ServiceCreateRequest,
    ServiceTier,
    ServiceUpdateRequest,
)
from .store import dependency_store
from .visualizer import DependencyVisualizer, GraphVisualization

logger = structlog.get_logger()
router = APIRouter(prefix="/api/dependencies", tags=["dependencies"])


# --- Response Models ---


class ServiceListResponse(BaseModel):
    """Response for listing services."""

    services: list[Service]
    total: int


class DependencyListResponse(BaseModel):
    """Response for listing dependencies."""

    dependencies: list[Dependency]
    total: int


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str


class ImportResponse(BaseModel):
    """Response for import operations."""

    services_imported: int
    dependencies_imported: int
    message: str


# --- Service Routes ---


@router.post("/services", response_model=Service)
async def create_service(request: ServiceCreateRequest) -> Service:
    """
    Create a new service in the catalog.

    Example request:
    ```json
    {
        "id": "payments-api",
        "name": "Payments API",
        "description": "Handles payment processing",
        "team_owner": "payments-team",
        "tier": "tier_1",
        "sla_availability": 99.99
    }
    ```
    """
    # Check if service already exists
    existing = await dependency_store.get_service(request.id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Service {request.id} already exists",
        )

    service = Service(
        id=request.id,
        name=request.name,
        description=request.description,
        team_owner=request.team_owner,
        tier=request.tier,
        sla_availability=request.sla_availability,
        repository_url=request.repository_url,
        documentation_url=request.documentation_url,
        tags=request.tags,
        metadata=request.metadata,
    )

    saved = await dependency_store.save_service(service)
    logger.info("service_created", service_id=saved.id, name=saved.name)

    return saved


@router.get("/services", response_model=ServiceListResponse)
async def list_services(
    tier: Annotated[
        ServiceTier | None,
        Query(description="Filter by service tier"),
    ] = None,
    team: Annotated[
        str | None,
        Query(description="Filter by team owner"),
    ] = None,
    tags: Annotated[
        list[str] | None,
        Query(description="Filter by tags (any match)"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=500, description="Maximum number of results"),
    ] = 100,
) -> ServiceListResponse:
    """
    List services in the catalog with optional filters.

    Services are sorted by tier (most critical first) then name.
    """
    services = await dependency_store.get_all_services(
        tier=tier,
        team_owner=team,
        tags=tags,
        limit=limit,
    )

    return ServiceListResponse(services=services, total=len(services))


@router.get("/services/{service_id}", response_model=Service)
async def get_service(service_id: str) -> Service:
    """Get a service by its ID."""
    service = await dependency_store.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_id} not found",
        )
    return service


@router.put("/services/{service_id}", response_model=Service)
async def update_service(
    service_id: str,
    updates: ServiceUpdateRequest,
) -> Service:
    """
    Update an existing service.

    Only provided fields will be updated.
    """
    updated = await dependency_store.update_service(service_id, updates)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_id} not found",
        )

    logger.info("service_updated", service_id=service_id)
    return updated


@router.delete("/services/{service_id}", response_model=MessageResponse)
async def delete_service(service_id: str) -> MessageResponse:
    """
    Delete a service and all its dependencies.

    This is a destructive operation that also removes all dependencies
    involving this service.
    """
    deleted = await dependency_store.delete_service(service_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_id} not found",
        )

    logger.info("service_deleted", service_id=service_id)
    return MessageResponse(message=f"Service {service_id} deleted successfully")


# --- Dependency Routes ---


@router.post("/edges", response_model=Dependency)
async def create_dependency(request: DependencyCreateRequest) -> Dependency:
    """
    Create a new dependency between services.

    The source_service_id is the service that depends on target_service_id.
    For example, if payments-api calls user-service, then:
    - source_service_id: payments-api
    - target_service_id: user-service

    Example request:
    ```json
    {
        "source_service_id": "payments-api",
        "target_service_id": "user-service",
        "dependency_type": "api",
        "is_critical": true,
        "is_synchronous": true
    }
    ```
    """
    # Verify both services exist
    source = await dependency_store.get_service(request.source_service_id)
    target = await dependency_store.get_service(request.target_service_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail=f"Source service {request.source_service_id} not found",
        )
    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Target service {request.target_service_id} not found",
        )

    # Check if dependency already exists
    existing = await dependency_store.get_dependency_by_services(
        request.source_service_id, request.target_service_id
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Dependency from {request.source_service_id} to {request.target_service_id} already exists",
        )

    import uuid

    dependency = Dependency(
        id=f"dep-{uuid.uuid4().hex[:8]}",
        source_service_id=request.source_service_id,
        target_service_id=request.target_service_id,
        dependency_type=request.dependency_type,
        is_critical=request.is_critical,
        is_synchronous=request.is_synchronous,
        has_circuit_breaker=request.has_circuit_breaker,
        has_fallback=request.has_fallback,
        description=request.description,
        metadata=request.metadata,
    )

    saved = await dependency_store.save_dependency(dependency)
    logger.info(
        "dependency_created",
        dependency_id=saved.id,
        source=saved.source_service_id,
        target=saved.target_service_id,
    )

    return saved


@router.get("/edges", response_model=DependencyListResponse)
async def list_dependencies(
    service_id: Annotated[
        str | None,
        Query(description="Filter by service ID (source or target)"),
    ] = None,
    dependency_type: Annotated[
        DependencyType | None,
        Query(description="Filter by dependency type"),
    ] = None,
    is_critical: Annotated[
        bool | None,
        Query(description="Filter by criticality"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=1000, description="Maximum number of results"),
    ] = 100,
) -> DependencyListResponse:
    """List dependencies with optional filters."""
    dependencies = await dependency_store.get_all_dependencies(
        service_id=service_id,
        dependency_type=dependency_type,
        is_critical=is_critical,
        limit=limit,
    )

    return DependencyListResponse(dependencies=dependencies, total=len(dependencies))


@router.get("/edges/{dependency_id}", response_model=Dependency)
async def get_dependency(dependency_id: str) -> Dependency:
    """Get a dependency by its ID."""
    dependency = await dependency_store.get_dependency(dependency_id)
    if not dependency:
        raise HTTPException(
            status_code=404,
            detail=f"Dependency {dependency_id} not found",
        )
    return dependency


@router.put("/edges/{dependency_id}", response_model=Dependency)
async def update_dependency(
    dependency_id: str,
    updates: DependencyUpdateRequest,
) -> Dependency:
    """Update an existing dependency."""
    updated = await dependency_store.update_dependency(dependency_id, updates)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Dependency {dependency_id} not found",
        )

    logger.info("dependency_updated", dependency_id=dependency_id)
    return updated


@router.delete("/edges/{dependency_id}", response_model=MessageResponse)
async def delete_dependency(dependency_id: str) -> MessageResponse:
    """Delete a dependency."""
    deleted = await dependency_store.delete_dependency(dependency_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Dependency {dependency_id} not found",
        )

    logger.info("dependency_deleted", dependency_id=dependency_id)
    return MessageResponse(message=f"Dependency {dependency_id} deleted successfully")


# --- Analysis Routes ---


@router.get("/services/{service_id}/blast-radius", response_model=BlastRadiusResult)
async def get_blast_radius(
    service_id: str,
    max_depth: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum traversal depth"),
    ] = 10,
    include_indirect: Annotated[
        bool,
        Query(description="Include indirect dependencies"),
    ] = True,
) -> BlastRadiusResult:
    """
    Calculate the blast radius for a service.

    Returns all services that would be affected if the given service fails,
    along with impact metrics.
    """
    service = await dependency_store.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_id} not found",
        )

    graph = DependencyGraph(dependency_store)
    result = await graph.calculate_blast_radius(
        service_id,
        max_depth=max_depth,
        include_indirect=include_indirect,
    )

    logger.info(
        "blast_radius_calculated",
        service_id=service_id,
        affected_count=len(result.affected_services),
        total_impact=result.total_impact_score,
    )

    return result


@router.get("/services/{service_id}/upstream")
async def get_upstream_dependencies(
    service_id: str,
    max_depth: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum traversal depth"),
    ] = 10,
) -> dict:
    """
    Get all services that this service depends on (upstream).

    Returns services grouped by depth level.
    """
    service = await dependency_store.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_id} not found",
        )

    graph = DependencyGraph(dependency_store)
    upstream = await graph.get_upstream_services(service_id, max_depth=max_depth)

    return {
        "service_id": service_id,
        "upstream_by_depth": upstream,
        "total_upstream": sum(len(s) for s in upstream.values()),
    }


@router.get("/services/{service_id}/downstream")
async def get_downstream_dependencies(
    service_id: str,
    max_depth: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum traversal depth"),
    ] = 10,
) -> dict:
    """
    Get all services that depend on this service (downstream).

    Returns services grouped by depth level.
    """
    service = await dependency_store.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_id} not found",
        )

    graph = DependencyGraph(dependency_store)
    downstream = await graph.get_downstream_services(service_id, max_depth=max_depth)

    return {
        "service_id": service_id,
        "downstream_by_depth": downstream,
        "total_downstream": sum(len(s) for s in downstream.values()),
    }


@router.get("/services/{service_id}/risk-score")
async def get_service_risk_score(service_id: str) -> dict:
    """
    Calculate a risk score for a service.

    The risk score considers:
    - Service tier
    - Number of dependent services
    - Tier of dependent services
    - Single point of failure status
    """
    graph = DependencyGraph(dependency_store)
    result = await graph.calculate_service_risk_score(service_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/analysis/cycles")
async def detect_cycles() -> dict:
    """
    Detect circular dependencies in the service graph.

    Circular dependencies can cause cascading failures and should be
    eliminated or carefully managed.
    """
    graph = DependencyGraph(dependency_store)
    cycles = await graph.detect_cycles()

    return {
        "cycles_found": len(cycles),
        "cycles": cycles,
        "recommendation": "Consider breaking these cycles by introducing async communication or removing redundant dependencies."
        if cycles
        else "No circular dependencies detected.",
    }


@router.get("/analysis/critical-paths")
async def get_critical_paths() -> dict:
    """
    Find critical paths in the dependency graph.

    Critical paths are chains of Tier 1/2 service dependencies
    that represent high-risk areas.
    """
    graph = DependencyGraph(dependency_store)
    paths = await graph.find_critical_paths()

    return {
        "critical_paths_found": len(paths),
        "paths": paths,
    }


@router.get("/stats", response_model=ServiceCatalogStats)
async def get_catalog_stats() -> ServiceCatalogStats:
    """Get statistics about the service catalog."""
    return await dependency_store.get_stats()


# --- Discovery Routes ---


@router.post("/discover", response_model=DiscoveryResult)
async def discover_dependencies(request: DiscoveryRequest) -> DiscoveryResult:
    """
    Trigger auto-discovery of services and dependencies.

    Supports discovery from:
    - docker_compose: Docker Compose files
    - kubernetes: Kubernetes manifests
    - terraform: Terraform configurations

    Use dry_run=true to preview without saving.
    """
    if request.file_path:
        result = await dependency_discovery.discover_from_file(request.file_path)
    elif request.source_type == "kubernetes" and request.namespace:
        # Would need to connect to k8s API
        result = DiscoveryResult(
            source_type="kubernetes",
            errors=["Kubernetes API discovery not yet implemented. Provide manifests via file."],
        )
    else:
        result = DiscoveryResult(
            source_type=request.source_type,
            errors=["Please provide a file_path for discovery"],
        )

    # Save if not dry run
    if not request.dry_run and not result.errors:
        for service in result.services_discovered:
            existing = await dependency_store.get_service(service.id)
            if not existing:
                await dependency_store.save_service(service)

        for dep in result.dependencies_discovered:
            existing = await dependency_store.get_dependency_by_services(
                dep.source_service_id, dep.target_service_id
            )
            if not existing:
                await dependency_store.save_dependency(dep)

        logger.info(
            "discovery_saved",
            services=len(result.services_discovered),
            dependencies=len(result.dependencies_discovered),
        )

    return result


@router.post("/discover/upload", response_model=DiscoveryResult)
async def discover_from_upload(
    file: UploadFile = File(...),
    dry_run: Annotated[
        bool,
        Query(description="If true, returns discovered data without saving"),
    ] = True,
) -> DiscoveryResult:
    """
    Upload a configuration file for dependency discovery.

    Supports:
    - docker-compose.yml
    - Kubernetes manifests (.yaml, .yml)
    - Terraform files (.tf)
    """
    content = await file.read()
    content_str = content.decode("utf-8")
    filename = file.filename or "unknown"

    # Detect file type
    if "docker-compose" in filename.lower() or filename in ["compose.yml", "compose.yaml"]:
        result = await dependency_discovery.discover_from_docker_compose(
            content_str, filename
        )
    elif filename.endswith(".tf"):
        result = await dependency_discovery.discover_from_terraform(content_str, filename)
    elif filename.endswith((".yml", ".yaml")):
        if "apiVersion:" in content_str and "kind:" in content_str:
            result = await dependency_discovery.discover_from_kubernetes([content_str])
        else:
            result = await dependency_discovery.discover_from_docker_compose(
                content_str, filename
            )
    else:
        result = DiscoveryResult(
            source_type="unknown",
            errors=[f"Unsupported file type: {filename}"],
        )

    # Save if not dry run
    if not dry_run and not result.errors:
        for service in result.services_discovered:
            existing = await dependency_store.get_service(service.id)
            if not existing:
                await dependency_store.save_service(service)

        for dep in result.dependencies_discovered:
            existing = await dependency_store.get_dependency_by_services(
                dep.source_service_id, dep.target_service_id
            )
            if not existing:
                await dependency_store.save_dependency(dep)

    return result


# --- Visualization Routes ---


@router.get("/visualize/graph", response_model=GraphVisualization)
async def get_visualization_graph(
    highlight: Annotated[
        str | None,
        Query(description="Service ID to highlight with blast radius"),
    ] = None,
    show_health: Annotated[
        bool,
        Query(description="Color nodes by health status"),
    ] = True,
    group_by_team: Annotated[
        bool,
        Query(description="Group nodes by team"),
    ] = False,
) -> GraphVisualization:
    """
    Get visualization data for the full dependency graph.

    Returns nodes and edges suitable for rendering with D3.js,
    Cytoscape.js, or similar visualization libraries.
    """
    visualizer = DependencyVisualizer(dependency_store)
    return await visualizer.generate_full_graph(
        highlight_service=highlight,
        show_health=show_health,
        group_by_team=group_by_team,
    )


@router.get("/visualize/service/{service_id}", response_model=GraphVisualization)
async def get_service_visualization(
    service_id: str,
    depth: Annotated[
        int,
        Query(ge=1, le=5, description="Depth of neighbors to include"),
    ] = 2,
    include_upstream: Annotated[
        bool,
        Query(description="Include upstream dependencies"),
    ] = True,
    include_downstream: Annotated[
        bool,
        Query(description="Include downstream dependencies"),
    ] = True,
) -> GraphVisualization:
    """
    Get visualization data focused on a specific service.

    Returns the service and its neighborhood up to the specified depth.
    """
    service = await dependency_store.get_service(service_id)
    if not service:
        raise HTTPException(
            status_code=404,
            detail=f"Service {service_id} not found",
        )

    visualizer = DependencyVisualizer(dependency_store)
    return await visualizer.generate_service_subgraph(
        service_id,
        depth=depth,
        include_upstream=include_upstream,
        include_downstream=include_downstream,
    )


@router.get("/visualize/mermaid")
async def get_mermaid_diagram(
    service_id: Annotated[
        str | None,
        Query(description="Optional service to focus on"),
    ] = None,
    max_nodes: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum nodes to include"),
    ] = 50,
) -> dict:
    """
    Generate a Mermaid diagram definition.

    The returned diagram can be rendered using Mermaid.js.
    """
    visualizer = DependencyVisualizer(dependency_store)
    diagram = await visualizer.generate_mermaid_diagram(
        service_id=service_id,
        max_nodes=max_nodes,
    )

    return {
        "diagram": diagram,
        "render_url": f"https://mermaid.live/edit#pako:{__import__('base64').b64encode(diagram.encode()).decode()}",
    }


@router.get("/visualize/d3")
async def get_d3_data(
    service_id: Annotated[
        str | None,
        Query(description="Optional service to focus on"),
    ] = None,
) -> dict:
    """
    Get visualization data in D3.js force-directed graph format.

    Returns nodes and links arrays compatible with D3's force simulation.
    """
    visualizer = DependencyVisualizer(dependency_store)
    return await visualizer.generate_d3_data(service_id=service_id)


@router.get("/visualize/cytoscape")
async def get_cytoscape_data(
    service_id: Annotated[
        str | None,
        Query(description="Optional service to focus on"),
    ] = None,
) -> dict:
    """
    Get visualization data in Cytoscape.js format.

    Returns elements array compatible with Cytoscape.js.
    """
    visualizer = DependencyVisualizer(dependency_store)
    return await visualizer.generate_cytoscape_data(service_id=service_id)


# --- Import/Export Routes ---


@router.get("/export")
async def export_catalog() -> dict:
    """
    Export the entire service catalog as JSON.

    The exported data can be used for backup or migration.
    """
    return await dependency_store.export_json()


@router.post("/import", response_model=ImportResponse)
async def import_catalog(
    data: dict,
    merge: Annotated[
        bool,
        Query(description="Merge with existing data instead of replacing"),
    ] = False,
) -> ImportResponse:
    """
    Import service catalog from JSON.

    If merge=true, new services and dependencies will be added to existing data.
    If merge=false (default), existing data will be replaced.
    """
    services_count, deps_count = await dependency_store.import_json(data, merge=merge)

    return ImportResponse(
        services_imported=services_count,
        dependencies_imported=deps_count,
        message=f"Imported {services_count} services and {deps_count} dependencies"
        + (" (merged)" if merge else " (replaced)"),
    )
