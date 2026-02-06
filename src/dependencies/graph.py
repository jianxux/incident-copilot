"""Graph operations for dependency analysis."""

from collections import defaultdict, deque
from datetime import datetime

import structlog

from .models import (
    BlastRadiusResult,
    Dependency,
    Service,
    ServiceTier,
)
from .store import DependencyStore

logger = structlog.get_logger()


class DependencyGraph:
    """
    Graph operations for service dependency analysis.

    Provides algorithms for:
    - Blast radius calculation (downstream impact)
    - Upstream dependency analysis
    - Critical path identification
    - Cycle detection
    - Impact scoring
    """

    def __init__(self, store: DependencyStore):
        """Initialize with a dependency store."""
        self.store = store

    async def _build_adjacency_lists(
        self,
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """
        Build adjacency lists for graph traversal.

        Returns:
            Tuple of (downstream_graph, upstream_graph)
            - downstream_graph[A] = [B, C] means A's failure affects B and C
            - upstream_graph[A] = [B, C] means A depends on B and C
        """
        # downstream_graph: source -> targets (who depends on source)
        # If source fails, targets are affected
        downstream: dict[str, list[str]] = defaultdict(list)
        # upstream_graph: source -> dependencies (what source depends on)
        upstream: dict[str, list[str]] = defaultdict(list)

        dependencies = await self.store.get_all_dependencies(limit=10000)

        for dep in dependencies:
            # source depends on target
            # So if target fails, source is affected
            downstream[dep.target_service_id].append(dep.source_service_id)
            upstream[dep.source_service_id].append(dep.target_service_id)

        return dict(downstream), dict(upstream)

    async def calculate_blast_radius(
        self,
        service_id: str,
        max_depth: int = 10,
        include_indirect: bool = True,
    ) -> BlastRadiusResult:
        """
        Calculate the blast radius of a service failure.

        The blast radius includes all services that would be affected
        if the given service fails (i.e., all downstream dependents).

        Args:
            service_id: The service experiencing failure
            max_depth: Maximum depth to traverse
            include_indirect: Whether to include indirect dependencies

        Returns:
            BlastRadiusResult with affected services and impact metrics
        """
        downstream, _ = await self._build_adjacency_lists()
        services = {s.id: s for s in await self.store.get_all_services(limit=10000)}

        if service_id not in services:
            logger.warning("service_not_found", service_id=service_id)
            return BlastRadiusResult(
                source_service_id=service_id,
                affected_services=[],
            )

        # BFS to find all affected services
        visited: set[str] = set()
        affected_by_depth: dict[int, list[str]] = defaultdict(list)
        queue: deque[tuple[str, int]] = deque([(service_id, 0)])

        while queue:
            current, depth = queue.popleft()

            if current in visited:
                continue
            visited.add(current)

            # Add to depth map (skip the source service itself at depth 0)
            if depth > 0:
                affected_by_depth[depth].append(current)

            # Stop if we've reached max depth or if not including indirect
            if depth >= max_depth:
                continue
            if depth > 0 and not include_indirect:
                continue

            # Add downstream services (those that depend on current)
            for downstream_id in downstream.get(current, []):
                if downstream_id not in visited:
                    queue.append((downstream_id, depth + 1))

        # Calculate impact score and tier counts
        all_affected = [sid for sids in affected_by_depth.values() for sid in sids]
        total_impact = 0.0
        tier_1_count = 0
        tier_2_count = 0
        critical_path: list[str] = []

        for sid in all_affected:
            service = services.get(sid)
            if service:
                impact = service.impact_weight()
                total_impact += impact
                if service.tier == ServiceTier.TIER_1:
                    tier_1_count += 1
                    critical_path.append(sid)
                elif service.tier == ServiceTier.TIER_2:
                    tier_2_count += 1

        logger.info(
            "blast_radius_calculated",
            source_service=service_id,
            affected_count=len(all_affected),
            total_impact=round(total_impact, 2),
            tier_1_affected=tier_1_count,
        )

        return BlastRadiusResult(
            source_service_id=service_id,
            affected_services=all_affected,
            affected_services_by_depth=dict(affected_by_depth),
            total_impact_score=round(total_impact, 2),
            critical_path_services=critical_path,
            tier_1_affected=tier_1_count,
            tier_2_affected=tier_2_count,
        )

    async def get_upstream_services(
        self,
        service_id: str,
        max_depth: int = 10,
    ) -> dict[int, list[str]]:
        """
        Get all services that this service depends on (upstream).

        Args:
            service_id: The service to analyze
            max_depth: Maximum depth to traverse

        Returns:
            Dict mapping depth level to list of service IDs
        """
        _, upstream = await self._build_adjacency_lists()

        visited: set[str] = set()
        by_depth: dict[int, list[str]] = defaultdict(list)
        queue: deque[tuple[str, int]] = deque([(service_id, 0)])

        while queue:
            current, depth = queue.popleft()

            if current in visited:
                continue
            visited.add(current)

            if depth > 0:
                by_depth[depth].append(current)

            if depth >= max_depth:
                continue

            for upstream_id in upstream.get(current, []):
                if upstream_id not in visited:
                    queue.append((upstream_id, depth + 1))

        return dict(by_depth)

    async def get_downstream_services(
        self,
        service_id: str,
        max_depth: int = 10,
    ) -> dict[int, list[str]]:
        """
        Get all services that depend on this service (downstream).

        Args:
            service_id: The service to analyze
            max_depth: Maximum depth to traverse

        Returns:
            Dict mapping depth level to list of service IDs
        """
        downstream, _ = await self._build_adjacency_lists()

        visited: set[str] = set()
        by_depth: dict[int, list[str]] = defaultdict(list)
        queue: deque[tuple[str, int]] = deque([(service_id, 0)])

        while queue:
            current, depth = queue.popleft()

            if current in visited:
                continue
            visited.add(current)

            if depth > 0:
                by_depth[depth].append(current)

            if depth >= max_depth:
                continue

            for downstream_id in downstream.get(current, []):
                if downstream_id not in visited:
                    queue.append((downstream_id, depth + 1))

        return dict(by_depth)

    async def detect_cycles(self) -> list[list[str]]:
        """
        Detect circular dependencies in the service graph.

        Returns:
            List of cycles, where each cycle is a list of service IDs
        """
        _, upstream = await self._build_adjacency_lists()
        all_services = await self.store.get_all_services(limit=10000)
        service_ids = {s.id for s in all_services}

        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in upstream.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for service_id in service_ids:
            if service_id not in visited:
                dfs(service_id, [])

        if cycles:
            logger.warning("cycles_detected", count=len(cycles))

        return cycles

    async def find_critical_paths(self) -> list[dict]:
        """
        Find critical paths in the dependency graph.

        Critical paths are chains of dependencies where all services
        are Tier 1 or Tier 2, representing high-risk dependency chains.

        Returns:
            List of critical path information
        """
        _, upstream = await self._build_adjacency_lists()
        services = {s.id: s for s in await self.store.get_all_services(limit=10000)}

        critical_paths: list[dict] = []

        # Find Tier 1 services as starting points
        tier_1_services = [
            s for s in services.values() if s.tier == ServiceTier.TIER_1
        ]

        def get_critical_chain(start_id: str, path: list[str]) -> list[str]:
            """Recursively build critical dependency chain."""
            current = services.get(start_id)
            if not current or current.tier not in [ServiceTier.TIER_1, ServiceTier.TIER_2]:
                return path

            path.append(start_id)

            # Check dependencies
            for dep_id in upstream.get(start_id, []):
                if dep_id not in path:  # Avoid cycles
                    dep_service = services.get(dep_id)
                    if dep_service and dep_service.tier in [
                        ServiceTier.TIER_1,
                        ServiceTier.TIER_2,
                    ]:
                        return get_critical_chain(dep_id, path)

            return path

        for t1_service in tier_1_services:
            chain = get_critical_chain(t1_service.id, [])
            if len(chain) > 1:
                # Calculate aggregate risk
                total_weight = sum(services[s].impact_weight() for s in chain)
                critical_paths.append(
                    {
                        "path": chain,
                        "length": len(chain),
                        "total_impact_weight": round(total_weight, 2),
                        "start_service": chain[0],
                        "end_service": chain[-1],
                    }
                )

        # Sort by length and impact weight
        critical_paths.sort(
            key=lambda x: (x["length"], x["total_impact_weight"]), reverse=True
        )

        return critical_paths[:20]  # Return top 20

    async def calculate_service_risk_score(self, service_id: str) -> dict:
        """
        Calculate a risk score for a service based on its position in the graph.

        Factors:
        - Service tier
        - Number of downstream dependents
        - Number of Tier 1/2 services that depend on it
        - Whether it's a single point of failure

        Returns:
            Dict with risk score and contributing factors
        """
        service = await self.store.get_service(service_id)
        if not service:
            return {"error": "Service not found", "risk_score": 0}

        blast_radius = await self.calculate_blast_radius(service_id)
        upstream = await self.get_upstream_services(service_id)
        services = {s.id: s for s in await self.store.get_all_services(limit=10000)}

        # Base score from tier
        tier_scores = {
            ServiceTier.TIER_1: 40,
            ServiceTier.TIER_2: 25,
            ServiceTier.TIER_3: 10,
            ServiceTier.TIER_4: 5,
        }
        base_score = tier_scores.get(service.tier, 10)

        # Score from blast radius
        blast_score = min(
            blast_radius.tier_1_affected * 10 + blast_radius.tier_2_affected * 5, 30
        )

        # Score from being a critical dependency
        critical_count = sum(
            1
            for deps in upstream.values()
            for dep_id in deps
            if services.get(dep_id, Service(id="", name="")).tier
            in [ServiceTier.TIER_1, ServiceTier.TIER_2]
        )
        critical_dep_score = min(critical_count * 5, 20)

        # Single point of failure detection
        spof_score = 0
        if blast_radius.tier_1_affected > 0:
            # Check if this is the only path to Tier 1 services
            # Simplified: if it affects Tier 1 and has high blast radius
            if len(blast_radius.affected_services) > 5:
                spof_score = 10

        total_score = min(base_score + blast_score + critical_dep_score + spof_score, 100)

        return {
            "service_id": service_id,
            "risk_score": total_score,
            "factors": {
                "tier_score": base_score,
                "blast_radius_score": blast_score,
                "critical_dependency_score": critical_dep_score,
                "spof_score": spof_score,
            },
            "blast_radius": len(blast_radius.affected_services),
            "tier_1_affected": blast_radius.tier_1_affected,
            "tier_2_affected": blast_radius.tier_2_affected,
            "calculated_at": datetime.utcnow().isoformat(),
        }

    async def get_dependency_depth(
        self, source_id: str, target_id: str
    ) -> int | None:
        """
        Find the shortest dependency path depth between two services.

        Returns:
            Depth (1 = direct dependency), or None if no path exists
        """
        _, upstream = await self._build_adjacency_lists()

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(source_id, 0)])

        while queue:
            current, depth = queue.popleft()

            if current == target_id and depth > 0:
                return depth

            if current in visited:
                continue
            visited.add(current)

            for upstream_id in upstream.get(current, []):
                if upstream_id not in visited:
                    queue.append((upstream_id, depth + 1))

        return None

    async def get_shared_dependencies(
        self, service_ids: list[str]
    ) -> list[str]:
        """
        Find services that all given services depend on (common dependencies).

        Args:
            service_ids: List of service IDs to analyze

        Returns:
            List of service IDs that are dependencies of all input services
        """
        if not service_ids:
            return []

        # Get upstream dependencies for each service
        all_upstreams: list[set[str]] = []
        for sid in service_ids:
            upstream_by_depth = await self.get_upstream_services(sid)
            upstream_set = {
                s for depths in upstream_by_depth.values() for s in depths
            }
            all_upstreams.append(upstream_set)

        # Find intersection
        if not all_upstreams:
            return []

        shared = all_upstreams[0]
        for upstream_set in all_upstreams[1:]:
            shared &= upstream_set

        return list(shared)
