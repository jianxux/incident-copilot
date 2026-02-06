"""In-memory store for service dependency data with file persistence."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import structlog

from .models import (
    Dependency,
    DependencyType,
    Service,
    ServiceCatalogStats,
    ServiceTier,
    ServiceUpdateRequest,
    DependencyUpdateRequest,
)

logger = structlog.get_logger()


class DependencyStore:
    """
    Thread-safe in-memory store for service dependency data.

    Supports optional file persistence for durability across restarts.
    """

    def __init__(
        self,
        persistence_path: str | Path | None = None,
        auto_save: bool = True,
    ):
        """
        Initialize the dependency store.

        Args:
            persistence_path: Path to JSON file for persistence (optional)
            auto_save: Whether to automatically save on writes
        """
        self._services: dict[str, Service] = {}
        self._dependencies: dict[str, Dependency] = {}
        self._lock = asyncio.Lock()
        self._persistence_path = Path(persistence_path) if persistence_path else None
        self._auto_save = auto_save

    # --- Service Operations ---

    async def save_service(self, service: Service) -> Service:
        """Save or update a service."""
        async with self._lock:
            service.updated_at = datetime.utcnow()
            self._services[service.id] = service
            logger.debug("service_saved", service_id=service.id, name=service.name)

            if self._auto_save and self._persistence_path:
                await self._persist()

            return service

    async def get_service(self, service_id: str) -> Service | None:
        """Get a service by ID."""
        return self._services.get(service_id)

    async def get_service_by_name(self, name: str) -> Service | None:
        """Get a service by name (case-insensitive)."""
        name_lower = name.lower()
        for service in self._services.values():
            if service.name.lower() == name_lower:
                return service
        return None

    async def get_all_services(
        self,
        tier: ServiceTier | None = None,
        team_owner: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Service]:
        """Get all services with optional filtering."""
        results = []
        for service in self._services.values():
            if tier and service.tier != tier:
                continue
            if team_owner and service.team_owner != team_owner:
                continue
            if tags and not any(tag in service.tags for tag in tags):
                continue
            results.append(service)

        # Sort by tier (most critical first), then name
        tier_order = {
            ServiceTier.TIER_1: 0,
            ServiceTier.TIER_2: 1,
            ServiceTier.TIER_3: 2,
            ServiceTier.TIER_4: 3,
        }
        results.sort(key=lambda s: (tier_order.get(s.tier, 99), s.name))
        return results[:limit]

    async def update_service(
        self, service_id: str, updates: ServiceUpdateRequest
    ) -> Service | None:
        """Update an existing service."""
        async with self._lock:
            if service_id not in self._services:
                return None

            service = self._services[service_id]
            update_data = updates.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if value is not None:
                    setattr(service, field, value)

            service.updated_at = datetime.utcnow()
            self._services[service_id] = service

            if self._auto_save and self._persistence_path:
                await self._persist()

            logger.info("service_updated", service_id=service_id)
            return service

    async def delete_service(self, service_id: str) -> bool:
        """Delete a service and all its dependencies."""
        async with self._lock:
            if service_id not in self._services:
                return False

            del self._services[service_id]

            # Remove dependencies involving this service
            deps_to_remove = [
                dep_id
                for dep_id, dep in self._dependencies.items()
                if dep.source_service_id == service_id
                or dep.target_service_id == service_id
            ]
            for dep_id in deps_to_remove:
                del self._dependencies[dep_id]

            if self._auto_save and self._persistence_path:
                await self._persist()

            logger.info(
                "service_deleted",
                service_id=service_id,
                dependencies_removed=len(deps_to_remove),
            )
            return True

    # --- Dependency Operations ---

    async def save_dependency(self, dependency: Dependency) -> Dependency:
        """Save or update a dependency."""
        async with self._lock:
            dependency.updated_at = datetime.utcnow()
            self._dependencies[dependency.id] = dependency
            logger.debug(
                "dependency_saved",
                dependency_id=dependency.id,
                source=dependency.source_service_id,
                target=dependency.target_service_id,
            )

            if self._auto_save and self._persistence_path:
                await self._persist()

            return dependency

    async def get_dependency(self, dependency_id: str) -> Dependency | None:
        """Get a dependency by ID."""
        return self._dependencies.get(dependency_id)

    async def get_dependency_by_services(
        self, source_id: str, target_id: str
    ) -> Dependency | None:
        """Get a dependency by source and target service IDs."""
        for dep in self._dependencies.values():
            if dep.source_service_id == source_id and dep.target_service_id == target_id:
                return dep
        return None

    async def get_all_dependencies(
        self,
        service_id: str | None = None,
        dependency_type: DependencyType | None = None,
        is_critical: bool | None = None,
        limit: int = 1000,
    ) -> list[Dependency]:
        """Get all dependencies with optional filtering."""
        results = []
        for dep in self._dependencies.values():
            if service_id and (
                dep.source_service_id != service_id
                and dep.target_service_id != service_id
            ):
                continue
            if dependency_type and dep.dependency_type != dependency_type:
                continue
            if is_critical is not None and dep.is_critical != is_critical:
                continue
            results.append(dep)

        # Sort by criticality, then by source service
        results.sort(key=lambda d: (not d.is_critical, d.source_service_id))
        return results[:limit]

    async def get_upstream_dependencies(self, service_id: str) -> list[Dependency]:
        """Get dependencies where this service depends on others (outgoing)."""
        return [
            dep
            for dep in self._dependencies.values()
            if dep.source_service_id == service_id
        ]

    async def get_downstream_dependencies(self, service_id: str) -> list[Dependency]:
        """Get dependencies where others depend on this service (incoming)."""
        return [
            dep
            for dep in self._dependencies.values()
            if dep.target_service_id == service_id
        ]

    async def update_dependency(
        self, dependency_id: str, updates: DependencyUpdateRequest
    ) -> Dependency | None:
        """Update an existing dependency."""
        async with self._lock:
            if dependency_id not in self._dependencies:
                return None

            dep = self._dependencies[dependency_id]
            update_data = updates.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if value is not None:
                    setattr(dep, field, value)

            dep.updated_at = datetime.utcnow()
            self._dependencies[dependency_id] = dep

            if self._auto_save and self._persistence_path:
                await self._persist()

            logger.info("dependency_updated", dependency_id=dependency_id)
            return dep

    async def delete_dependency(self, dependency_id: str) -> bool:
        """Delete a dependency."""
        async with self._lock:
            if dependency_id not in self._dependencies:
                return False

            del self._dependencies[dependency_id]

            if self._auto_save and self._persistence_path:
                await self._persist()

            logger.info("dependency_deleted", dependency_id=dependency_id)
            return True

    # --- Statistics ---

    async def get_stats(self) -> ServiceCatalogStats:
        """Get statistics about the service catalog."""
        services = list(self._services.values())
        dependencies = list(self._dependencies.values())

        # Count by tier
        services_by_tier: dict[str, int] = {}
        for s in services:
            tier_str = s.tier.value
            services_by_tier[tier_str] = services_by_tier.get(tier_str, 0) + 1

        # Count by team
        services_by_team: dict[str, int] = {}
        for s in services:
            team = s.team_owner or "unassigned"
            services_by_team[team] = services_by_team.get(team, 0) + 1

        # Count dependency types
        dependency_types: dict[str, int] = {}
        for d in dependencies:
            dtype = d.dependency_type.value
            dependency_types[dtype] = dependency_types.get(dtype, 0) + 1

        # Count incoming dependencies per service
        incoming_counts: dict[str, int] = {}
        outgoing_counts: dict[str, int] = {}
        for d in dependencies:
            incoming_counts[d.target_service_id] = (
                incoming_counts.get(d.target_service_id, 0) + 1
            )
            outgoing_counts[d.source_service_id] = (
                outgoing_counts.get(d.source_service_id, 0) + 1
            )

        # Most depended upon (highest incoming)
        most_depended = sorted(
            incoming_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        # Most dependencies (highest outgoing)
        most_deps = sorted(
            outgoing_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        # Find orphan services (no dependencies either way)
        all_in_deps = set(incoming_counts.keys()) | set(outgoing_counts.keys())
        orphans = [s.id for s in services if s.id not in all_in_deps]

        # Average dependencies per service
        total_services = len(services)
        avg_deps = (
            len(dependencies) / total_services if total_services > 0 else 0
        )

        return ServiceCatalogStats(
            total_services=len(services),
            total_dependencies=len(dependencies),
            services_by_tier=services_by_tier,
            services_by_team=services_by_team,
            dependency_types=dependency_types,
            avg_dependencies_per_service=round(avg_deps, 2),
            most_depended_upon=most_depended,
            most_dependencies=most_deps,
            orphan_services=orphans,
        )

    # --- Persistence ---

    async def _persist(self) -> None:
        """Save data to the persistence file."""
        if not self._persistence_path:
            return

        try:
            data = {
                "version": "1.0",
                "exported_at": datetime.utcnow().isoformat(),
                "services": [s.model_dump(mode="json") for s in self._services.values()],
                "dependencies": [
                    d.model_dump(mode="json") for d in self._dependencies.values()
                ],
            }

            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            self._persistence_path.write_text(json.dumps(data, indent=2, default=str))
            logger.debug("store_persisted", path=str(self._persistence_path))
        except Exception as e:
            logger.error("persistence_failed", error=str(e))

    async def load(self) -> bool:
        """Load data from the persistence file."""
        if not self._persistence_path or not self._persistence_path.exists():
            return False

        try:
            async with self._lock:
                data = json.loads(self._persistence_path.read_text())

                self._services.clear()
                self._dependencies.clear()

                for s_data in data.get("services", []):
                    service = Service(**s_data)
                    self._services[service.id] = service

                for d_data in data.get("dependencies", []):
                    dep = Dependency(**d_data)
                    self._dependencies[dep.id] = dep

            logger.info(
                "store_loaded",
                services=len(self._services),
                dependencies=len(self._dependencies),
            )
            return True
        except Exception as e:
            logger.error("load_failed", error=str(e))
            return False

    async def export_json(self) -> dict:
        """Export the entire catalog as JSON."""
        return {
            "version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "stats": (await self.get_stats()).model_dump(),
            "services": [s.model_dump(mode="json") for s in self._services.values()],
            "dependencies": [
                d.model_dump(mode="json") for d in self._dependencies.values()
            ],
        }

    async def import_json(self, data: dict, merge: bool = False) -> tuple[int, int]:
        """
        Import catalog data from JSON.

        Args:
            data: JSON data with services and dependencies
            merge: If True, merge with existing data; if False, replace

        Returns:
            Tuple of (services_imported, dependencies_imported)
        """
        async with self._lock:
            if not merge:
                self._services.clear()
                self._dependencies.clear()

            services_count = 0
            deps_count = 0

            for s_data in data.get("services", []):
                service = Service(**s_data)
                self._services[service.id] = service
                services_count += 1

            for d_data in data.get("dependencies", []):
                dep = Dependency(**d_data)
                self._dependencies[dep.id] = dep
                deps_count += 1

            if self._auto_save and self._persistence_path:
                await self._persist()

            logger.info(
                "catalog_imported",
                services=services_count,
                dependencies=deps_count,
                merge=merge,
            )

            return services_count, deps_count

    async def clear(self) -> None:
        """Clear all stored data (for testing)."""
        async with self._lock:
            self._services.clear()
            self._dependencies.clear()
            logger.info("store_cleared")


# Global dependency store instance
dependency_store = DependencyStore()
