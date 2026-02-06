"""Generate visualization data for service dependency graphs."""

from datetime import datetime
from enum import Enum

import structlog
from pydantic import BaseModel, Field

from .graph import DependencyGraph
from .models import (
    DependencyType,
    HealthStatus,
    ServiceTier,
)
from .store import DependencyStore

logger = structlog.get_logger()


class NodeType(str, Enum):
    """Types of nodes in the visualization."""

    SERVICE = "service"
    DATABASE = "database"
    QUEUE = "queue"
    CACHE = "cache"
    STORAGE = "storage"
    EXTERNAL = "external"


class VisualizationNode(BaseModel):
    """A node in the visualization graph."""

    id: str
    label: str
    type: NodeType = NodeType.SERVICE
    tier: str | None = None
    team: str | None = None
    health: str = "unknown"

    # Visual properties
    size: float = 1.0  # Relative size
    color: str | None = None
    icon: str | None = None

    # Metadata
    metadata: dict = Field(default_factory=dict)

    # Position hints (for layouts that support it)
    x: float | None = None
    y: float | None = None
    group: str | None = None


class VisualizationEdge(BaseModel):
    """An edge in the visualization graph."""

    id: str
    source: str
    target: str
    type: str = "api"
    is_critical: bool = False

    # Visual properties
    width: float = 1.0
    color: str | None = None
    style: str = "solid"  # solid, dashed, dotted
    animated: bool = False  # For highlighting active flows

    # Labels
    label: str | None = None


class GraphVisualization(BaseModel):
    """Complete graph visualization data."""

    nodes: list[VisualizationNode] = Field(default_factory=list)
    edges: list[VisualizationEdge] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class DependencyVisualizer:
    """
    Generate visualization data for dependency graphs.

    Outputs data suitable for various visualization libraries:
    - D3.js force-directed graphs
    - Cytoscape.js
    - vis.js
    - Mermaid diagrams
    """

    # Color schemes
    TIER_COLORS = {
        ServiceTier.TIER_1: "#e53e3e",  # Red
        ServiceTier.TIER_2: "#ed8936",  # Orange
        ServiceTier.TIER_3: "#3182ce",  # Blue
        ServiceTier.TIER_4: "#718096",  # Gray
    }

    HEALTH_COLORS = {
        HealthStatus.HEALTHY: "#48bb78",  # Green
        HealthStatus.DEGRADED: "#ed8936",  # Orange
        HealthStatus.UNHEALTHY: "#e53e3e",  # Red
        HealthStatus.UNKNOWN: "#718096",  # Gray
    }

    DEP_TYPE_COLORS = {
        DependencyType.API: "#3182ce",  # Blue
        DependencyType.DATABASE: "#805ad5",  # Purple
        DependencyType.QUEUE: "#38a169",  # Green
        DependencyType.CACHE: "#d69e2e",  # Yellow
        DependencyType.STORAGE: "#718096",  # Gray
        DependencyType.EXTERNAL: "#e53e3e",  # Red
    }

    def __init__(self, store: DependencyStore):
        """Initialize with a dependency store."""
        self.store = store
        self.graph = DependencyGraph(store)

    def _get_node_type(self, service_name: str, dep_type: DependencyType | None) -> NodeType:
        """Determine node type based on service name and dependency type."""
        name_lower = service_name.lower()

        if dep_type == DependencyType.DATABASE or any(
            db in name_lower for db in ["postgres", "mysql", "mongo", "redis", "elastic"]
        ):
            return NodeType.DATABASE
        if dep_type == DependencyType.QUEUE or any(
            q in name_lower for q in ["kafka", "rabbitmq", "sqs"]
        ):
            return NodeType.QUEUE
        if dep_type == DependencyType.CACHE or "cache" in name_lower:
            return NodeType.CACHE
        if dep_type == DependencyType.STORAGE or any(
            s in name_lower for s in ["s3", "storage", "blob"]
        ):
            return NodeType.STORAGE
        if dep_type == DependencyType.EXTERNAL:
            return NodeType.EXTERNAL

        return NodeType.SERVICE

    async def generate_full_graph(
        self,
        highlight_service: str | None = None,
        show_health: bool = True,
        group_by_team: bool = False,
    ) -> GraphVisualization:
        """
        Generate visualization data for the entire dependency graph.

        Args:
            highlight_service: Optional service to highlight with blast radius
            show_health: Whether to color nodes by health status
            group_by_team: Whether to group nodes by team

        Returns:
            GraphVisualization with nodes and edges
        """
        services = await self.store.get_all_services(limit=10000)
        dependencies = await self.store.get_all_dependencies(limit=10000)

        # Build highlighted services set if needed
        highlighted: set[str] = set()
        if highlight_service:
            blast_radius = await self.graph.calculate_blast_radius(highlight_service)
            highlighted = set(blast_radius.affected_services)
            highlighted.add(highlight_service)

        # Create nodes
        nodes: list[VisualizationNode] = []
        for service in services:
            # Determine color
            if show_health:
                color = self.HEALTH_COLORS.get(service.health_status)
            else:
                color = self.TIER_COLORS.get(service.tier)

            # Calculate size based on importance
            size = 1.0
            if service.tier == ServiceTier.TIER_1:
                size = 2.0
            elif service.tier == ServiceTier.TIER_2:
                size = 1.5

            # Determine node type
            node_type = self._get_node_type(service.name, None)

            node = VisualizationNode(
                id=service.id,
                label=service.name,
                type=node_type,
                tier=service.tier.value,
                team=service.team_owner,
                health=service.health_status.value,
                size=size,
                color=color,
                group=service.team_owner if group_by_team else None,
                metadata={
                    "description": service.description,
                    "sla_availability": service.sla_availability,
                    "incident_count_30d": service.incident_count_30d,
                    "highlighted": service.id in highlighted,
                },
            )
            nodes.append(node)

        # Create edges
        edges: list[VisualizationEdge] = []
        for dep in dependencies:
            # Determine edge style
            style = "solid"
            if not dep.is_synchronous:
                style = "dashed"

            # Determine color
            color = self.DEP_TYPE_COLORS.get(dep.dependency_type, "#718096")

            # Width based on criticality
            width = 2.0 if dep.is_critical else 1.0

            # Animated if part of blast radius
            animated = (
                dep.source_service_id in highlighted
                or dep.target_service_id in highlighted
            )

            edge = VisualizationEdge(
                id=dep.id,
                source=dep.source_service_id,
                target=dep.target_service_id,
                type=dep.dependency_type.value,
                is_critical=dep.is_critical,
                width=width,
                color=color,
                style=style,
                animated=animated,
                label=dep.dependency_type.value if dep.is_critical else None,
            )
            edges.append(edge)

        return GraphVisualization(
            nodes=nodes,
            edges=edges,
            metadata={
                "highlight_service": highlight_service,
                "show_health": show_health,
                "group_by_team": group_by_team,
                "total_services": len(nodes),
                "total_dependencies": len(edges),
            },
        )

    async def generate_service_subgraph(
        self,
        service_id: str,
        depth: int = 2,
        include_upstream: bool = True,
        include_downstream: bool = True,
    ) -> GraphVisualization:
        """
        Generate visualization for a specific service and its neighborhood.

        Args:
            service_id: The central service
            depth: How many levels to include
            include_upstream: Include services this depends on
            include_downstream: Include services that depend on this

        Returns:
            GraphVisualization focused on the service
        """
        relevant_services: set[str] = {service_id}

        if include_upstream:
            upstream = await self.graph.get_upstream_services(service_id, max_depth=depth)
            for services in upstream.values():
                relevant_services.update(services)

        if include_downstream:
            downstream = await self.graph.get_downstream_services(
                service_id, max_depth=depth
            )
            for services in downstream.values():
                relevant_services.update(services)

        # Get full graph and filter
        full_graph = await self.generate_full_graph(highlight_service=service_id)

        filtered_nodes = [n for n in full_graph.nodes if n.id in relevant_services]
        filtered_edges = [
            e
            for e in full_graph.edges
            if e.source in relevant_services and e.target in relevant_services
        ]

        return GraphVisualization(
            nodes=filtered_nodes,
            edges=filtered_edges,
            metadata={
                "center_service": service_id,
                "depth": depth,
                "include_upstream": include_upstream,
                "include_downstream": include_downstream,
            },
        )

    async def generate_mermaid_diagram(
        self,
        service_id: str | None = None,
        max_nodes: int = 50,
    ) -> str:
        """
        Generate a Mermaid diagram definition.

        Args:
            service_id: Optional service to focus on
            max_nodes: Maximum number of nodes to include

        Returns:
            Mermaid diagram definition string
        """
        if service_id:
            graph = await self.generate_service_subgraph(service_id, depth=2)
        else:
            graph = await self.generate_full_graph()

        # Limit nodes
        nodes = graph.nodes[:max_nodes]
        node_ids = {n.id for n in nodes}
        edges = [e for e in graph.edges if e.source in node_ids and e.target in node_ids]

        lines = ["graph TD"]

        # Add nodes with styling
        for node in nodes:
            shape_start, shape_end = "(", ")"
            if node.type == NodeType.DATABASE:
                shape_start, shape_end = "[(", ")]"
            elif node.type == NodeType.QUEUE:
                shape_start, shape_end = "{{", "}}"
            elif node.type == NodeType.CACHE:
                shape_start, shape_end = "([", "])"

            # Escape special characters in label
            safe_label = node.label.replace('"', "'")
            lines.append(f"    {node.id}{shape_start}\"{safe_label}\"{shape_end}")

        # Add edges
        for edge in edges:
            arrow = "-->" if edge.style == "solid" else "-.->"
            if edge.is_critical:
                arrow = "==>"

            if edge.label:
                lines.append(f"    {edge.source} {arrow}|{edge.label}| {edge.target}")
            else:
                lines.append(f"    {edge.source} {arrow} {edge.target}")

        # Add styling based on tiers
        for node in nodes:
            if node.tier == "tier_1":
                lines.append(f"    style {node.id} fill:#fed7d7,stroke:#c53030")
            elif node.tier == "tier_2":
                lines.append(f"    style {node.id} fill:#feebc8,stroke:#c05621")

        return "\n".join(lines)

    async def generate_d3_data(
        self,
        service_id: str | None = None,
    ) -> dict:
        """
        Generate data in D3.js force-directed graph format.

        Args:
            service_id: Optional service to focus on

        Returns:
            Dict with nodes and links arrays for D3
        """
        if service_id:
            graph = await self.generate_service_subgraph(service_id, depth=3)
        else:
            graph = await self.generate_full_graph()

        # D3 format
        d3_nodes = [
            {
                "id": n.id,
                "name": n.label,
                "group": n.group or n.tier or "default",
                "tier": n.tier,
                "health": n.health,
                "type": n.type.value,
                "size": n.size * 10,  # Scale for D3
                "color": n.color,
                **n.metadata,
            }
            for n in graph.nodes
        ]

        d3_links = [
            {
                "source": e.source,
                "target": e.target,
                "type": e.type,
                "critical": e.is_critical,
                "width": e.width,
                "color": e.color,
            }
            for e in graph.edges
        ]

        return {
            "nodes": d3_nodes,
            "links": d3_links,
            "metadata": graph.metadata,
        }

    async def generate_cytoscape_data(
        self,
        service_id: str | None = None,
    ) -> dict:
        """
        Generate data in Cytoscape.js format.

        Args:
            service_id: Optional service to focus on

        Returns:
            Dict with elements array for Cytoscape
        """
        if service_id:
            graph = await self.generate_service_subgraph(service_id, depth=3)
        else:
            graph = await self.generate_full_graph()

        elements = []

        # Add nodes
        for n in graph.nodes:
            elements.append(
                {
                    "data": {
                        "id": n.id,
                        "label": n.label,
                        "type": n.type.value,
                        "tier": n.tier,
                        "team": n.team,
                        "health": n.health,
                        "parent": n.group,  # For compound nodes
                    },
                    "classes": f"{n.type.value} tier-{n.tier} health-{n.health}",
                }
            )

        # Add edges
        for e in graph.edges:
            elements.append(
                {
                    "data": {
                        "id": e.id,
                        "source": e.source,
                        "target": e.target,
                        "type": e.type,
                        "critical": e.is_critical,
                    },
                    "classes": f"{e.type} {'critical' if e.is_critical else ''}",
                }
            )

        return {
            "elements": elements,
            "metadata": graph.metadata,
        }
