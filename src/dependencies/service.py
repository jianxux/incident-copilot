"""Dependency service for managing service dependencies."""

import uuid
from datetime import datetime
from typing import Any

from .graph import DependencyGraphAnalyzer
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
)


class DependencyService:
    """Service layer for dependency management."""

    def __init__(self) -> None:
        self._analyzer = DependencyGraphAnalyzer()

    # --- Service Management ---

    async def create_service(self, request: ServiceCreate) -> Service:
        """Create a new service."""
        service = Service(
            id=request.id,
            name=request.name,
            description=request.description,
            team=request.team,
            criticality=request.criticality,
            tags=request.tags,
            metadata=request.metadata,
        )
        self._analyzer.add_service(service)
        return service

    async def get_service(self, service_id: str) -> Service | None:
        """Get a service by ID."""
        return self._analyzer.get_service(service_id)

    async def list_services(
        self,
        criticality: CriticalityLevel | None = None,
        health: HealthStatus | None = None,
        team: str | None = None,
    ) -> list[Service]:
        """List services with optional filters."""
        services = self._analyzer.get_all_services()

        if criticality:
            services = [s for s in services if s.criticality == criticality]
        if health:
            services = [s for s in services if s.health == health]
        if team:
            services = [s for s in services if s.team == team]

        return services

    async def update_service_health(
        self, service_id: str, health: HealthStatus
    ) -> Service | None:
        """Update a service's health status."""
        service = self._analyzer.get_service(service_id)
        if not service:
            return None

        service.health = health
        service.updated_at = datetime.utcnow()
        return service

    async def delete_service(self, service_id: str) -> bool:
        """Delete a service and its dependencies."""
        return self._analyzer.remove_service(service_id)

    # --- Dependency Management ---

    async def create_dependency(self, request: DependencyCreate) -> Dependency | None:
        """Create a new dependency between services."""
        # Validate services exist
        if not self._analyzer.get_service(request.source_id):
            return None
        if not self._analyzer.get_service(request.target_id):
            return None

        dependency = Dependency(
            id=str(uuid.uuid4()),
            source_id=request.source_id,
            target_id=request.target_id,
            dependency_type=request.dependency_type,
            is_critical=request.is_critical,
            metadata=request.metadata,
        )
        self._analyzer.add_dependency(dependency)
        return dependency

    async def get_dependency(self, dependency_id: str) -> Dependency | None:
        """Get a dependency by ID."""
        return self._analyzer.get_dependency(dependency_id)

    async def list_dependencies(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> list[Dependency]:
        """List dependencies with optional filters."""
        dependencies = self._analyzer.get_all_dependencies()

        if source_id:
            dependencies = [d for d in dependencies if d.source_id == source_id]
        if target_id:
            dependencies = [d for d in dependencies if d.target_id == target_id]

        return dependencies

    async def update_dependency_metrics(
        self,
        dependency_id: str,
        latency_p99_ms: float | None = None,
        error_rate: float | None = None,
        requests_per_min: float | None = None,
    ) -> Dependency | None:
        """Update dependency metrics."""
        dependency = self._analyzer.get_dependency(dependency_id)
        if not dependency:
            return None

        if latency_p99_ms is not None:
            dependency.latency_p99_ms = latency_p99_ms
        if error_rate is not None:
            dependency.error_rate = error_rate
            # Auto-update health based on error rate
            if error_rate > 0.1:
                dependency.health = HealthStatus.UNHEALTHY
            elif error_rate > 0.01:
                dependency.health = HealthStatus.DEGRADED
            else:
                dependency.health = HealthStatus.HEALTHY
        if requests_per_min is not None:
            dependency.requests_per_min = requests_per_min

        dependency.last_seen = datetime.utcnow()
        return dependency

    async def delete_dependency(self, dependency_id: str) -> bool:
        """Delete a dependency."""
        return self._analyzer.remove_dependency(dependency_id)

    # --- Analysis ---

    async def calculate_blast_radius(
        self,
        service_id: str,
        max_depth: int | None = None,
    ) -> BlastRadius | None:
        """Calculate the blast radius if a service fails."""
        service = self._analyzer.get_service(service_id)
        if not service:
            return None

        affected = self._analyzer.get_downstream(service_id, max_depth)

        # Get critical services affected
        critical_affected = [
            svc_id
            for svc_id in affected
            if (svc := self._analyzer.get_service(svc_id))
            and svc.criticality == CriticalityLevel.CRITICAL
        ]

        # Build impact paths
        impact_paths = []
        for affected_id in affected:
            path = self._analyzer.find_path(affected_id, service_id)
            if path:
                impact_paths.append(path)

        # Calculate max depth
        max_impact_depth = max((p.length for p in impact_paths), default=0)

        # Calculate risk score
        risk_score = self._analyzer.calculate_risk_score(service_id)

        return BlastRadius(
            failed_service_id=service_id,
            affected_services=list(affected),
            affected_count=len(affected),
            critical_affected=critical_affected,
            risk_score=risk_score,
            impact_paths=impact_paths,
            max_depth=max_impact_depth,
        )

    async def get_service_dependencies(self, service_id: str) -> dict[str, list[str]]:
        """Get upstream and downstream dependencies for a service."""
        return {
            "upstream": list(self._analyzer.get_upstream(service_id)),
            "downstream": list(self._analyzer.get_downstream(service_id)),
        }

    async def find_path(self, source_id: str, target_id: str) -> DependencyPath | None:
        """Find the shortest path between two services."""
        return self._analyzer.find_path(source_id, target_id)

    async def get_deployment_order(self) -> list[str] | None:
        """Get the recommended deployment order (topological sort)."""
        return self._analyzer.topological_sort()

    # --- Graph Operations ---

    async def get_full_graph(self) -> DependencyGraph:
        """Get the complete dependency graph."""
        services = self._analyzer.get_all_services()
        dependencies = self._analyzer.get_all_dependencies()
        cycles = self._analyzer.detect_cycles()

        # Calculate max depth
        max_depth = 0
        for service in services:
            affected = self._analyzer.get_downstream(service.id)
            for affected_id in affected:
                path = self._analyzer.find_path(affected_id, service.id)
                if path:
                    max_depth = max(max_depth, path.length)

        return DependencyGraph(
            services=services,
            dependencies=dependencies,
            cycles=cycles,
            service_count=len(services),
            dependency_count=len(dependencies),
            has_cycles=len(cycles) > 0,
            max_depth=max_depth,
        )

    async def get_graph_stats(self) -> GraphStats:
        """Get statistics about the dependency graph."""
        services = self._analyzer.get_all_services()
        stats = self._analyzer.get_graph_stats()

        critical_count = sum(
            1 for s in services if s.criticality == CriticalityLevel.CRITICAL
        )
        healthy_count = sum(1 for s in services if s.health == HealthStatus.HEALTHY)
        unhealthy_count = sum(1 for s in services if s.health == HealthStatus.UNHEALTHY)

        avg_deps = (
            stats["total_dependencies"] / stats["total_services"]
            if stats["total_services"] > 0
            else 0
        )

        return GraphStats(
            total_services=stats["total_services"],
            total_dependencies=stats["total_dependencies"],
            critical_services=critical_count,
            healthy_services=healthy_count,
            unhealthy_services=unhealthy_count,
            avg_dependencies_per_service=round(avg_deps, 2),
            max_fan_out=stats["max_fan_out"],
            max_fan_in=stats["max_fan_in"],
            cycle_count=stats["cycle_count"],
            isolated_services=stats["isolated_count"],
        )

    async def get_high_risk_services(self, threshold: float = 50.0) -> list[dict]:
        """Get services with risk score above threshold."""
        result = []
        for service in self._analyzer.get_all_services():
            score = self._analyzer.calculate_risk_score(service.id)
            if score >= threshold:
                result.append(
                    {
                        "service": service,
                        "risk_score": score,
                        "fan_in": self._analyzer.get_fan_in(service.id),
                        "fan_out": self._analyzer.get_fan_out(service.id),
                    }
                )

        return sorted(result, key=lambda x: x["risk_score"], reverse=True)

    def get_analyzer(self) -> DependencyGraphAnalyzer:
        """Get the underlying graph analyzer."""
        return self._analyzer


# Singleton instance
_dependency_service: DependencyService | None = None


def get_dependency_service() -> DependencyService:
    """Get the dependency service singleton."""
    global _dependency_service
    if _dependency_service is None:
        _dependency_service = DependencyService()
    return _dependency_service
