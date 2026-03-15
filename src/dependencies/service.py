"""Dependency service for managing service dependencies."""

from __future__ import annotations

import uuid
from datetime import datetime, UTC

from ..services.models import (
    ServiceCreate as CatalogServiceCreate,
)
from ..services.models import (
    ServiceDependencyCreate as CatalogDependencyCreate,
)
from ..services.models import (
    ServiceDependencyUpdate as CatalogDependencyUpdate,
)
from ..services.models import (
    ServiceUpdate as CatalogServiceUpdate,
)
from ..services.store import ServiceCatalogStore, get_service_catalog_store
from .graph import DependencyGraphAnalyzer
from .models import (
    BlastRadius,
    CriticalityLevel,
    Dependency,
    DependencyCreate,
    DependencyGraph,
    DependencyPath,
    DependencyType,
    GraphStats,
    HealthStatus,
    Service,
    ServiceCreate,
)


class DependencyService:
    """Service layer for dependency management."""

    def __init__(self, tenant_slug: str = "default") -> None:
        self._analyzer = DependencyGraphAnalyzer()
        self._tenant_slug = tenant_slug
        self._store: ServiceCatalogStore = get_service_catalog_store()

    async def _refresh_graph(self) -> None:
        """Rebuild in-memory analyzer from persistent service catalog."""
        if not self._store.enabled:
            return

        self._analyzer = DependencyGraphAnalyzer()
        services = await self._store.list_services(tenant_slug=self._tenant_slug)
        for svc in services:
            self._analyzer.add_service(
                Service(
                    id=svc.id,
                    name=svc.name,
                    description=svc.description,
                    team=svc.team,
                    criticality=CriticalityLevel(svc.criticality.value),
                    health=HealthStatus(svc.health.value),
                    tags=svc.tags,
                    metadata=svc.metadata,
                    created_at=svc.created_at or datetime.now(UTC),
                    updated_at=svc.updated_at or datetime.now(UTC),
                )
            )

        deps = await self._store.list_dependencies(tenant_slug=self._tenant_slug)
        for dep in deps:
            self._analyzer.add_dependency(
                Dependency(
                    id=dep.id or str(uuid.uuid4()),
                    source_id=dep.source_service_id,
                    target_id=dep.target_service_id,
                    dependency_type=DependencyType(dep.dependency_type.value),
                    is_critical=dep.is_critical,
                    latency_p99_ms=dep.latency_p99_ms,
                    error_rate=dep.error_rate,
                    requests_per_min=dep.requests_per_min,
                    health=HealthStatus(dep.health.value),
                    discovered_at=dep.discovered_at or datetime.now(UTC),
                    last_seen=dep.last_seen_at or datetime.now(UTC),
                    metadata=dep.metadata,
                )
            )

    # --- Service Management ---

    async def create_service(self, request: ServiceCreate) -> Service:
        """Create a new service."""
        if self._store.enabled:
            svc = await self._store.create_service(
                CatalogServiceCreate(
                    id=request.id,
                    name=request.name,
                    description=request.description,
                    team=request.team,
                    criticality=request.criticality.value,
                    health=HealthStatus.UNKNOWN.value,
                    tags=request.tags,
                    metadata=request.metadata,
                ),
                tenant_slug=self._tenant_slug,
            )
            created = Service(
                id=svc.id,
                name=svc.name,
                description=svc.description,
                team=svc.team,
                criticality=CriticalityLevel(svc.criticality.value),
                health=HealthStatus(svc.health.value),
                tags=svc.tags,
                metadata=svc.metadata,
                created_at=svc.created_at or datetime.now(UTC),
                updated_at=svc.updated_at or datetime.now(UTC),
            )
            await self._refresh_graph()
            return created

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
        if self._store.enabled:
            svc = await self._store.get_service(
                service_id, tenant_slug=self._tenant_slug
            )
            if not svc:
                return None
            return Service(
                id=svc.id,
                name=svc.name,
                description=svc.description,
                team=svc.team,
                criticality=CriticalityLevel(svc.criticality.value),
                health=HealthStatus(svc.health.value),
                tags=svc.tags,
                metadata=svc.metadata,
                created_at=svc.created_at or datetime.now(UTC),
                updated_at=svc.updated_at or datetime.now(UTC),
            )

        return self._analyzer.get_service(service_id)

    async def get_service_by_name(self, service_name: str) -> Service | None:
        """Get a service by name (for orchestrator context lookup)."""
        if self._store.enabled:
            svc = await self._store.get_service_by_name(
                service_name,
                tenant_slug=self._tenant_slug,
            )
            if not svc:
                return None
            return Service(
                id=svc.id,
                name=svc.name,
                description=svc.description,
                team=svc.team,
                criticality=CriticalityLevel(svc.criticality.value),
                health=HealthStatus(svc.health.value),
                tags=svc.tags,
                metadata=svc.metadata,
                created_at=svc.created_at or datetime.now(UTC),
                updated_at=svc.updated_at or datetime.now(UTC),
            )

        return next(
            (s for s in self._analyzer.get_all_services() if s.name == service_name),
            None,
        )

    async def list_services(
        self,
        criticality: CriticalityLevel | None = None,
        health: HealthStatus | None = None,
        team: str | None = None,
    ) -> list[Service]:
        """List services with optional filters."""
        if self._store.enabled:
            services = await self._store.list_services(
                tenant_slug=self._tenant_slug,
                team=team,
                criticality=criticality.value if criticality else None,
            )
            result = [
                Service(
                    id=s.id,
                    name=s.name,
                    description=s.description,
                    team=s.team,
                    criticality=CriticalityLevel(s.criticality.value),
                    health=HealthStatus(s.health.value),
                    tags=s.tags,
                    metadata=s.metadata,
                    created_at=s.created_at or datetime.now(UTC),
                    updated_at=s.updated_at or datetime.now(UTC),
                )
                for s in services
            ]
            if health:
                result = [s for s in result if s.health == health]
            return result

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
        if self._store.enabled:
            svc = await self._store.update_service(
                service_id,
                CatalogServiceUpdate(health=health.value),
                tenant_slug=self._tenant_slug,
            )
            if not svc:
                return None
            await self._refresh_graph()
            return Service(
                id=svc.id,
                name=svc.name,
                description=svc.description,
                team=svc.team,
                criticality=CriticalityLevel(svc.criticality.value),
                health=HealthStatus(svc.health.value),
                tags=svc.tags,
                metadata=svc.metadata,
                created_at=svc.created_at or datetime.now(UTC),
                updated_at=svc.updated_at or datetime.now(UTC),
            )

        service = self._analyzer.get_service(service_id)
        if not service:
            return None

        service.health = health
        service.updated_at = datetime.now(UTC)
        return service

    async def delete_service(self, service_id: str) -> bool:
        """Delete a service and its dependencies."""
        if self._store.enabled:
            deleted = await self._store.delete_service(
                service_id,
                tenant_slug=self._tenant_slug,
            )
            if deleted:
                await self._refresh_graph()
            return deleted

        return self._analyzer.remove_service(service_id)

    # --- Dependency Management ---

    async def create_dependency(self, request: DependencyCreate) -> Dependency | None:
        """Create a new dependency between services."""
        if self._store.enabled:
            dep = await self._store.create_dependency(
                source_service_id=request.source_id,
                request=CatalogDependencyCreate(
                    target_service_id=request.target_id,
                    dependency_type=request.dependency_type.value,
                    is_critical=request.is_critical,
                    metadata=request.metadata,
                ),
                tenant_slug=self._tenant_slug,
            )
            if not dep:
                return None
            await self._refresh_graph()
            return Dependency(
                id=dep.id or str(uuid.uuid4()),
                source_id=dep.source_service_id,
                target_id=dep.target_service_id,
                dependency_type=DependencyType(dep.dependency_type.value),
                is_critical=dep.is_critical,
                latency_p99_ms=dep.latency_p99_ms,
                error_rate=dep.error_rate,
                requests_per_min=dep.requests_per_min,
                health=HealthStatus(dep.health.value),
                discovered_at=dep.discovered_at or datetime.now(UTC),
                last_seen=dep.last_seen_at or datetime.now(UTC),
                metadata=dep.metadata,
            )

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
        if self._store.enabled:
            dep = await self._store.get_dependency(
                dependency_id,
                tenant_slug=self._tenant_slug,
            )
            if not dep:
                return None
            return Dependency(
                id=dep.id or dependency_id,
                source_id=dep.source_service_id,
                target_id=dep.target_service_id,
                dependency_type=DependencyType(dep.dependency_type.value),
                is_critical=dep.is_critical,
                latency_p99_ms=dep.latency_p99_ms,
                error_rate=dep.error_rate,
                requests_per_min=dep.requests_per_min,
                health=HealthStatus(dep.health.value),
                discovered_at=dep.discovered_at or datetime.now(UTC),
                last_seen=dep.last_seen_at or datetime.now(UTC),
                metadata=dep.metadata,
            )

        return self._analyzer.get_dependency(dependency_id)

    async def list_dependencies(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> list[Dependency]:
        """List dependencies with optional filters."""
        if self._store.enabled:
            deps = await self._store.list_dependencies(
                tenant_slug=self._tenant_slug,
                source_service_id=source_id,
                target_service_id=target_id,
            )
            return [
                Dependency(
                    id=d.id or str(uuid.uuid4()),
                    source_id=d.source_service_id,
                    target_id=d.target_service_id,
                    dependency_type=DependencyType(d.dependency_type.value),
                    is_critical=d.is_critical,
                    latency_p99_ms=d.latency_p99_ms,
                    error_rate=d.error_rate,
                    requests_per_min=d.requests_per_min,
                    health=HealthStatus(d.health.value),
                    discovered_at=d.discovered_at or datetime.now(UTC),
                    last_seen=d.last_seen_at or datetime.now(UTC),
                    metadata=d.metadata,
                )
                for d in deps
            ]

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
        if self._store.enabled:
            health = None
            if error_rate is not None:
                if error_rate > 0.1:
                    health = HealthStatus.UNHEALTHY.value
                elif error_rate > 0.01:
                    health = HealthStatus.DEGRADED.value
                else:
                    health = HealthStatus.HEALTHY.value

            dep = await self._store.update_dependency(
                dependency_id,
                CatalogDependencyUpdate(
                    latency_p99_ms=latency_p99_ms,
                    error_rate=error_rate,
                    requests_per_min=requests_per_min,
                    health=health,
                ),
                tenant_slug=self._tenant_slug,
            )
            if not dep:
                return None
            await self._refresh_graph()
            return Dependency(
                id=dep.id or dependency_id,
                source_id=dep.source_service_id,
                target_id=dep.target_service_id,
                dependency_type=DependencyType(dep.dependency_type.value),
                is_critical=dep.is_critical,
                latency_p99_ms=dep.latency_p99_ms,
                error_rate=dep.error_rate,
                requests_per_min=dep.requests_per_min,
                health=HealthStatus(dep.health.value),
                discovered_at=dep.discovered_at or datetime.now(UTC),
                last_seen=dep.last_seen_at or datetime.now(UTC),
                metadata=dep.metadata,
            )

        dependency = self._analyzer.get_dependency(dependency_id)
        if not dependency:
            return None

        if latency_p99_ms is not None:
            dependency.latency_p99_ms = latency_p99_ms
        if error_rate is not None:
            dependency.error_rate = error_rate
            if error_rate > 0.1:
                dependency.health = HealthStatus.UNHEALTHY
            elif error_rate > 0.01:
                dependency.health = HealthStatus.DEGRADED
            else:
                dependency.health = HealthStatus.HEALTHY
        if requests_per_min is not None:
            dependency.requests_per_min = requests_per_min

        dependency.last_seen = datetime.now(UTC)
        return dependency

    async def delete_dependency(self, dependency_id: str) -> bool:
        """Delete a dependency."""
        if self._store.enabled:
            deleted = await self._store.delete_dependency(
                dependency_id,
                tenant_slug=self._tenant_slug,
            )
            if deleted:
                await self._refresh_graph()
            return deleted

        return self._analyzer.remove_dependency(dependency_id)

    # --- Analysis ---

    async def calculate_blast_radius(
        self,
        service_id: str,
        max_depth: int | None = None,
    ) -> BlastRadius | None:
        """Calculate the blast radius if a service fails."""
        if self._store.enabled:
            await self._refresh_graph()

        service = self._analyzer.get_service(service_id)
        if not service:
            return None

        affected = self._analyzer.get_downstream(service_id, max_depth)

        critical_affected = [
            svc_id
            for svc_id in affected
            if (svc := self._analyzer.get_service(svc_id))
            and svc.criticality == CriticalityLevel.CRITICAL
        ]

        impact_paths = []
        for affected_id in affected:
            path = self._analyzer.find_path(affected_id, service_id)
            if path:
                impact_paths.append(path)

        max_impact_depth = max((p.length for p in impact_paths), default=0)
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
        if self._store.enabled:
            await self._refresh_graph()
        return {
            "upstream": list(self._analyzer.get_upstream(service_id)),
            "downstream": list(self._analyzer.get_downstream(service_id)),
        }

    async def find_path(self, source_id: str, target_id: str) -> DependencyPath | None:
        """Find the shortest path between two services."""
        if self._store.enabled:
            await self._refresh_graph()
        return self._analyzer.find_path(source_id, target_id)

    async def get_deployment_order(self) -> list[str] | None:
        """Get the recommended deployment order (topological sort)."""
        if self._store.enabled:
            await self._refresh_graph()
        return self._analyzer.topological_sort()

    # --- Graph Operations ---

    async def get_full_graph(self) -> DependencyGraph:
        """Get the complete dependency graph."""
        if self._store.enabled:
            await self._refresh_graph()

        services = self._analyzer.get_all_services()
        dependencies = self._analyzer.get_all_dependencies()
        cycles = self._analyzer.detect_cycles()

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
        if self._store.enabled:
            await self._refresh_graph()

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
        if self._store.enabled:
            await self._refresh_graph()

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


_dependency_service: DependencyService | None = None


def get_dependency_service() -> DependencyService:
    """Get the dependency service singleton."""
    global _dependency_service
    if _dependency_service is None:
        _dependency_service = DependencyService()
    return _dependency_service
