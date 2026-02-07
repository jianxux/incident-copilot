"""Graph algorithms for dependency analysis using NetworkX."""

from typing import Any

import networkx as nx

from .models import (
    CriticalityLevel,
    CycleInfo,
    Dependency,
    DependencyPath,
    Service,
)


class DependencyGraphAnalyzer:
    """Analyzer for service dependency graphs using NetworkX."""

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()
        self._services: dict[str, Service] = {}
        self._dependencies: dict[str, Dependency] = {}

    def add_service(self, service: Service) -> None:
        """Add a service node to the graph."""
        self._services[service.id] = service
        self._graph.add_node(
            service.id,
            name=service.name,
            criticality=service.criticality.value,
            health=service.health.value,
            team=service.team,
        )

    def remove_service(self, service_id: str) -> bool:
        """Remove a service and all its dependencies."""
        if service_id not in self._services:
            return False

        # Remove related dependencies
        to_remove = [
            dep_id
            for dep_id, dep in self._dependencies.items()
            if dep.source_id == service_id or dep.target_id == service_id
        ]
        for dep_id in to_remove:
            del self._dependencies[dep_id]

        self._graph.remove_node(service_id)
        del self._services[service_id]
        return True

    def add_dependency(self, dependency: Dependency) -> None:
        """Add a dependency edge to the graph."""
        self._dependencies[dependency.id] = dependency
        self._graph.add_edge(
            dependency.source_id,
            dependency.target_id,
            id=dependency.id,
            type=dependency.dependency_type.value,
            is_critical=dependency.is_critical,
            latency=dependency.latency_p99_ms,
            error_rate=dependency.error_rate,
        )

    def remove_dependency(self, dependency_id: str) -> bool:
        """Remove a dependency edge."""
        if dependency_id not in self._dependencies:
            return False

        dep = self._dependencies[dependency_id]
        if self._graph.has_edge(dep.source_id, dep.target_id):
            self._graph.remove_edge(dep.source_id, dep.target_id)
        del self._dependencies[dependency_id]
        return True

    def get_downstream(self, service_id: str, max_depth: int | None = None) -> set[str]:
        """Get all services that depend on this service (upstream perspective).

        If service X fails, which services are affected?
        Returns services that call this service (predecessors in call graph).
        """
        if service_id not in self._graph:
            return set()

        # In a call graph, edges go from caller to callee
        # So predecessors are the ones that depend on us
        affected = set()
        to_visit = [(service_id, 0)]
        visited = {service_id}

        while to_visit:
            current, depth = to_visit.pop(0)
            if max_depth is not None and depth >= max_depth:
                continue

            for pred in self._graph.predecessors(current):
                if pred not in visited:
                    visited.add(pred)
                    affected.add(pred)
                    to_visit.append((pred, depth + 1))

        return affected

    def get_upstream(self, service_id: str, max_depth: int | None = None) -> set[str]:
        """Get all services this service depends on.

        What does service X need to function?
        Returns services this service calls (successors in call graph).
        """
        if service_id not in self._graph:
            return set()

        dependencies = set()
        to_visit = [(service_id, 0)]
        visited = {service_id}

        while to_visit:
            current, depth = to_visit.pop(0)
            if max_depth is not None and depth >= max_depth:
                continue

            for succ in self._graph.successors(current):
                if succ not in visited:
                    visited.add(succ)
                    dependencies.add(succ)
                    to_visit.append((succ, depth + 1))

        return dependencies

    def detect_cycles(self) -> list[CycleInfo]:
        """Detect all cycles in the dependency graph."""
        try:
            cycles = list(nx.simple_cycles(self._graph))
        except nx.NetworkXError:
            return []

        result = []
        for cycle in cycles:
            involves_critical = any(
                self._services.get(svc_id, Service(id=svc_id, name=svc_id)).criticality
                == CriticalityLevel.CRITICAL
                for svc_id in cycle
            )
            result.append(
                CycleInfo(
                    cycle=cycle,
                    length=len(cycle),
                    involves_critical=involves_critical,
                )
            )

        return result

    def has_cycles(self) -> bool:
        """Check if the graph has any cycles."""
        try:
            nx.find_cycle(self._graph)
            return True
        except nx.NetworkXNoCycle:
            return False

    def topological_sort(self) -> list[str] | None:
        """Return topological ordering of services (for deployment order).

        Returns None if graph has cycles.
        """
        try:
            return list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible:
            return None

    def find_path(self, source_id: str, target_id: str) -> DependencyPath | None:
        """Find shortest path between two services."""
        if source_id not in self._graph or target_id not in self._graph:
            return None

        try:
            path = nx.shortest_path(self._graph, source_id, target_id)
            has_critical = self._path_has_critical_hop(path)
            return DependencyPath(
                source_id=source_id,
                target_id=target_id,
                path=path,
                length=len(path) - 1,
                has_critical_hop=has_critical,
            )
        except nx.NetworkXNoPath:
            return None

    def find_all_paths(
        self, source_id: str, target_id: str, max_length: int = 10
    ) -> list[DependencyPath]:
        """Find all paths between two services up to max_length."""
        if source_id not in self._graph or target_id not in self._graph:
            return []

        try:
            paths = list(
                nx.all_simple_paths(
                    self._graph, source_id, target_id, cutoff=max_length
                )
            )
        except nx.NetworkXError:
            return []

        return [
            DependencyPath(
                source_id=source_id,
                target_id=target_id,
                path=path,
                length=len(path) - 1,
                has_critical_hop=self._path_has_critical_hop(path),
            )
            for path in paths
        ]

    def _path_has_critical_hop(self, path: list[str]) -> bool:
        """Check if a path contains a critical dependency."""
        for i in range(len(path) - 1):
            edge_data = self._graph.get_edge_data(path[i], path[i + 1])
            if edge_data and edge_data.get("is_critical"):
                return True
        return False

    def calculate_risk_score(self, service_id: str) -> float:
        """Calculate risk score for a service failure (0-100).

        Factors:
        - Number of dependent services
        - Criticality of dependent services
        - Depth of impact
        - Fan-out (how many services this one calls)
        """
        if service_id not in self._graph:
            return 0.0

        affected = self.get_downstream(service_id)
        if not affected:
            return 0.0

        base_score = min(len(affected) * 5, 30)  # Up to 30 points for count

        # Criticality bonus
        critical_count = sum(
            1
            for svc_id in affected
            if self._services.get(svc_id, Service(id=svc_id, name=svc_id)).criticality
            == CriticalityLevel.CRITICAL
        )
        high_count = sum(
            1
            for svc_id in affected
            if self._services.get(svc_id, Service(id=svc_id, name=svc_id)).criticality
            == CriticalityLevel.HIGH
        )
        criticality_score = min(critical_count * 15 + high_count * 8, 40)

        # Depth score
        max_depth = self._calculate_max_depth(service_id, affected)
        depth_score = min(max_depth * 5, 20)

        # Self criticality bonus
        self_criticality = self._services.get(
            service_id, Service(id=service_id, name=service_id)
        ).criticality
        self_score = {
            CriticalityLevel.CRITICAL: 10,
            CriticalityLevel.HIGH: 5,
            CriticalityLevel.MEDIUM: 2,
            CriticalityLevel.LOW: 0,
        }.get(self_criticality, 0)

        return min(base_score + criticality_score + depth_score + self_score, 100.0)

    def _calculate_max_depth(self, service_id: str, affected: set[str]) -> int:
        """Calculate maximum depth of impact."""
        if not affected:
            return 0

        max_depth = 0
        for target in affected:
            path = self.find_path(target, service_id)
            if path:
                max_depth = max(max_depth, path.length)
        return max_depth

    def get_fan_out(self, service_id: str) -> int:
        """Get number of services this service depends on."""
        if service_id not in self._graph:
            return 0
        return self._graph.out_degree(service_id)

    def get_fan_in(self, service_id: str) -> int:
        """Get number of services depending on this service."""
        if service_id not in self._graph:
            return 0
        return self._graph.in_degree(service_id)

    def get_isolated_services(self) -> list[str]:
        """Get services with no dependencies (in or out)."""
        return [node for node in self._graph.nodes() if self._graph.degree(node) == 0]

    def get_leaf_services(self) -> list[str]:
        """Get services that don't depend on anything else."""
        return [
            node
            for node in self._graph.nodes()
            if self._graph.out_degree(node) == 0 and self._graph.in_degree(node) > 0
        ]

    def get_root_services(self) -> list[str]:
        """Get services that nothing depends on (entry points)."""
        return [
            node
            for node in self._graph.nodes()
            if self._graph.in_degree(node) == 0 and self._graph.out_degree(node) > 0
        ]

    def get_strongly_connected_components(self) -> list[list[str]]:
        """Get strongly connected components (tightly coupled service groups)."""
        return [list(comp) for comp in nx.strongly_connected_components(self._graph)]

    def get_graph_stats(self) -> dict[str, Any]:
        """Get statistics about the graph."""
        nodes = list(self._graph.nodes())

        return {
            "total_services": len(nodes),
            "total_dependencies": self._graph.number_of_edges(),
            "max_fan_out": max((self._graph.out_degree(n) for n in nodes), default=0),
            "max_fan_in": max((self._graph.in_degree(n) for n in nodes), default=0),
            "isolated_count": len(self.get_isolated_services()),
            "has_cycles": self.has_cycles(),
            "cycle_count": len(self.detect_cycles()),
            "density": nx.density(self._graph) if nodes else 0,
        }

    def get_service(self, service_id: str) -> Service | None:
        """Get a service by ID."""
        return self._services.get(service_id)

    def get_dependency(self, dependency_id: str) -> Dependency | None:
        """Get a dependency by ID."""
        return self._dependencies.get(dependency_id)

    def get_all_services(self) -> list[Service]:
        """Get all services."""
        return list(self._services.values())

    def get_all_dependencies(self) -> list[Dependency]:
        """Get all dependencies."""
        return list(self._dependencies.values())

    def get_networkx_graph(self) -> nx.DiGraph:
        """Get the underlying NetworkX graph."""
        return self._graph.copy()
