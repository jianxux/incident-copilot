"""FastAPI routes for service dependencies."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .discovery import DependencyDiscovery
from .models import (
    BlastRadius,
    CriticalityLevel,
    Dependency,
    DependencyCreate,
    DependencyGraph,
    DependencyPath,
    GraphStats,
    HealthStatus,
    Service,
    ServiceCreate,
    TraceSpan,
)
from .service import DependencyService, get_dependency_service
from .visualization import GraphVisualizer

router = APIRouter(prefix="/dependencies", tags=["dependencies"])


def get_service() -> DependencyService:
    """Dependency injection for DependencyService."""
    return get_dependency_service()


ServiceDep = Annotated[DependencyService, Depends(get_service)]


# --- Service Endpoints ---


@router.post("/services", response_model=Service, status_code=201)
async def create_service(
    request: ServiceCreate,
    service: ServiceDep,
) -> Service:
    """Create a new service in the dependency graph."""
    existing = await service.get_service(request.id)
    if existing:
        raise HTTPException(400, f"Service {request.id} already exists")
    return await service.create_service(request)


@router.get("/services", response_model=list[Service])
async def list_services(
    service: ServiceDep,
    criticality: CriticalityLevel | None = None,
    health: HealthStatus | None = None,
    team: str | None = None,
) -> list[Service]:
    """List all services with optional filters."""
    return await service.list_services(criticality, health, team)


@router.get("/services/{service_id}", response_model=Service)
async def get_service_by_id(
    service_id: str,
    service: ServiceDep,
) -> Service:
    """Get a service by ID."""
    result = await service.get_service(service_id)
    if not result:
        raise HTTPException(404, f"Service {service_id} not found")
    return result


@router.patch("/services/{service_id}/health", response_model=Service)
async def update_service_health(
    service_id: str,
    health: HealthStatus,
    service: ServiceDep,
) -> Service:
    """Update a service's health status."""
    result = await service.update_service_health(service_id, health)
    if not result:
        raise HTTPException(404, f"Service {service_id} not found")
    return result


@router.delete("/services/{service_id}", status_code=204)
async def delete_service(
    service_id: str,
    service: ServiceDep,
) -> None:
    """Delete a service and all its dependencies."""
    if not await service.delete_service(service_id):
        raise HTTPException(404, f"Service {service_id} not found")


@router.get("/services/{service_id}/dependencies")
async def get_service_dependencies(
    service_id: str,
    service: ServiceDep,
) -> dict[str, list[str]]:
    """Get upstream and downstream dependencies for a service."""
    svc = await service.get_service(service_id)
    if not svc:
        raise HTTPException(404, f"Service {service_id} not found")
    return await service.get_service_dependencies(service_id)


# --- Dependency Endpoints ---


@router.post("/edges", response_model=Dependency, status_code=201)
async def create_dependency(
    request: DependencyCreate,
    service: ServiceDep,
) -> Dependency:
    """Create a dependency between two services."""
    result = await service.create_dependency(request)
    if not result:
        raise HTTPException(400, f"Could not create dependency: ensure both services exist")
    return result


@router.get("/edges", response_model=list[Dependency])
async def list_dependencies(
    service: ServiceDep,
    source_id: str | None = None,
    target_id: str | None = None,
) -> list[Dependency]:
    """List dependencies with optional filters."""
    return await service.list_dependencies(source_id, target_id)


@router.get("/edges/{dependency_id}", response_model=Dependency)
async def get_dependency(
    dependency_id: str,
    service: ServiceDep,
) -> Dependency:
    """Get a dependency by ID."""
    result = await service.get_dependency(dependency_id)
    if not result:
        raise HTTPException(404, f"Dependency {dependency_id} not found")
    return result


@router.patch("/edges/{dependency_id}/metrics", response_model=Dependency)
async def update_dependency_metrics(
    dependency_id: str,
    service: ServiceDep,
    latency_p99_ms: float | None = None,
    error_rate: float | None = None,
    requests_per_min: float | None = None,
) -> Dependency:
    """Update metrics for a dependency."""
    result = await service.update_dependency_metrics(
        dependency_id, latency_p99_ms, error_rate, requests_per_min
    )
    if not result:
        raise HTTPException(404, f"Dependency {dependency_id} not found")
    return result


@router.delete("/edges/{dependency_id}", status_code=204)
async def delete_dependency(
    dependency_id: str,
    service: ServiceDep,
) -> None:
    """Delete a dependency."""
    if not await service.delete_dependency(dependency_id):
        raise HTTPException(404, f"Dependency {dependency_id} not found")


# --- Analysis Endpoints ---


@router.get("/blast-radius/{service_id}", response_model=BlastRadius)
async def get_blast_radius(
    service_id: str,
    service: ServiceDep,
    max_depth: int | None = Query(None, ge=1, le=20),
) -> BlastRadius:
    """Calculate the blast radius if a service fails."""
    result = await service.calculate_blast_radius(service_id, max_depth)
    if not result:
        raise HTTPException(404, f"Service {service_id} not found")
    return result


@router.get("/path", response_model=DependencyPath | None)
async def find_path(
    source_id: str,
    target_id: str,
    service: ServiceDep,
) -> DependencyPath | None:
    """Find the shortest dependency path between two services."""
    return await service.find_path(source_id, target_id)


@router.get("/deployment-order", response_model=list[str] | None)
async def get_deployment_order(service: ServiceDep) -> list[str] | None:
    """Get recommended deployment order (topological sort).

    Returns None if the graph has cycles.
    """
    return await service.get_deployment_order()


@router.get("/high-risk")
async def get_high_risk_services(
    service: ServiceDep,
    threshold: float = Query(50.0, ge=0, le=100),
) -> list[dict[str, Any]]:
    """Get services with risk score above threshold."""
    return await service.get_high_risk_services(threshold)


# --- Graph Endpoints ---


@router.get("/graph", response_model=DependencyGraph)
async def get_full_graph(service: ServiceDep) -> DependencyGraph:
    """Get the complete dependency graph."""
    return await service.get_full_graph()


@router.get("/graph/stats", response_model=GraphStats)
async def get_graph_stats(service: ServiceDep) -> GraphStats:
    """Get statistics about the dependency graph."""
    return await service.get_graph_stats()


# --- Visualization Endpoints ---


@router.get("/visualization/dot")
async def export_dot(
    service: ServiceDep,
    highlight: str | None = None,
    show_health: bool = True,
    show_metrics: bool = False,
) -> Response:
    """Export graph as DOT format for Graphviz."""
    visualizer = GraphVisualizer(service.get_analyzer())
    dot = visualizer.to_dot(highlight, show_health, show_metrics)
    return Response(content=dot, media_type="text/vnd.graphviz")


@router.get("/visualization/d3")
async def export_d3_json(
    service: ServiceDep,
    highlight: str | None = None,
) -> dict[str, Any]:
    """Export graph as D3.js force-directed graph JSON."""
    visualizer = GraphVisualizer(service.get_analyzer())
    return visualizer.to_d3_json(highlight)


@router.get("/visualization/cytoscape")
async def export_cytoscape(service: ServiceDep) -> dict[str, Any]:
    """Export graph as Cytoscape.js format."""
    visualizer = GraphVisualizer(service.get_analyzer())
    return visualizer.to_cytoscape_json()


@router.get("/visualization/mermaid")
async def export_mermaid(
    service: ServiceDep,
    highlight: str | None = None,
) -> Response:
    """Export graph as Mermaid diagram."""
    visualizer = GraphVisualizer(service.get_analyzer())
    mermaid = visualizer.to_mermaid(highlight)
    return Response(content=mermaid, media_type="text/plain")


@router.get("/visualization/matrix")
async def export_adjacency_matrix(service: ServiceDep) -> dict[str, Any]:
    """Export graph as adjacency matrix."""
    visualizer = GraphVisualizer(service.get_analyzer())
    return visualizer.to_adjacency_matrix()


# --- Discovery Endpoints ---


@router.post("/discovery/traces")
async def discover_from_traces(
    spans: list[TraceSpan],
    service: ServiceDep,
) -> dict[str, int]:
    """Discover dependencies from distributed trace spans."""
    discovery = DependencyDiscovery(service)
    return await discovery.process_trace_spans(spans)


@router.post("/discovery/logs")
async def discover_from_logs(
    logs: list[dict[str, Any]],
    service: ServiceDep,
) -> dict[str, int]:
    """Discover dependencies from structured log entries."""
    discovery = DependencyDiscovery(service)
    return await discovery.process_log_entries(logs)
