"""Visualization exports for dependency graphs (DOT, D3 JSON)."""

from typing import Any

from .graph import DependencyGraphAnalyzer
from .models import CriticalityLevel, HealthStatus


class GraphVisualizer:
    """Export dependency graphs in various visualization formats."""

    # Color schemes
    CRITICALITY_COLORS = {
        CriticalityLevel.CRITICAL: "#dc2626",  # Red
        CriticalityLevel.HIGH: "#f97316",  # Orange
        CriticalityLevel.MEDIUM: "#eab308",  # Yellow
        CriticalityLevel.LOW: "#22c55e",  # Green
    }

    HEALTH_COLORS = {
        HealthStatus.HEALTHY: "#22c55e",  # Green
        HealthStatus.DEGRADED: "#f97316",  # Orange
        HealthStatus.UNHEALTHY: "#dc2626",  # Red
        HealthStatus.UNKNOWN: "#6b7280",  # Gray
    }

    def __init__(self, analyzer: DependencyGraphAnalyzer) -> None:
        self._analyzer = analyzer

    def to_dot(
        self,
        highlight_service: str | None = None,
        show_health: bool = True,
        show_metrics: bool = False,
    ) -> str:
        """Export graph to DOT format for Graphviz.

        Args:
            highlight_service: Service ID to highlight (shows blast radius)
            show_health: Color nodes by health status
            show_metrics: Show latency/error rate on edges
        """
        lines = [
            "digraph ServiceDependencies {",
            "    rankdir=LR;",
            '    node [shape=box, style="rounded,filled", fontname="Arial"];',
            '    edge [fontname="Arial", fontsize=10];',
            "",
        ]

        # Get affected services for highlighting
        affected = set()
        if highlight_service:
            affected = self._analyzer.get_downstream(highlight_service)
            affected.add(highlight_service)

        # Add nodes
        for service in self._analyzer.get_all_services():
            attrs = self._get_node_attrs(service, affected, show_health)
            attr_str = ", ".join(f'{k}="{v}"' for k, v in attrs.items())
            lines.append(f'    "{service.id}" [{attr_str}];')

        lines.append("")

        # Add edges
        for dep in self._analyzer.get_all_dependencies():
            attrs = self._get_edge_attrs(dep, affected, show_metrics)
            attr_str = ", ".join(f'{k}="{v}"' for k, v in attrs.items())
            lines.append(f'    "{dep.source_id}" -> "{dep.target_id}" [{attr_str}];')

        lines.append("}")
        return "\n".join(lines)

    def _get_node_attrs(
        self,
        service: Any,
        affected: set[str],
        show_health: bool,
    ) -> dict[str, str]:
        """Get DOT attributes for a node."""
        attrs = {
            "label": f"{service.name}\\n({service.criticality.value})",
        }

        # Determine fill color
        if service.id in affected and affected:
            if show_health:
                attrs["fillcolor"] = self.HEALTH_COLORS.get(service.health, "#ffffff")
            else:
                attrs["fillcolor"] = self.CRITICALITY_COLORS.get(service.criticality, "#ffffff")
            attrs["penwidth"] = "3"
            attrs["color"] = "#1e40af"  # Blue border for affected
        elif show_health:
            attrs["fillcolor"] = self.HEALTH_COLORS.get(service.health, "#ffffff")
        else:
            attrs["fillcolor"] = self.CRITICALITY_COLORS.get(service.criticality, "#ffffff")

        return attrs

    def _get_edge_attrs(
        self,
        dep: Any,
        affected: set[str],
        show_metrics: bool,
    ) -> dict[str, str]:
        """Get DOT attributes for an edge."""
        attrs = {}

        # Style based on dependency type
        if dep.dependency_type.value == "async":
            attrs["style"] = "dashed"
        elif dep.dependency_type.value == "database":
            attrs["style"] = "dotted"

        # Highlight critical edges
        if dep.is_critical:
            attrs["color"] = "#dc2626"
            attrs["penwidth"] = "2"

        # Highlight affected path
        if dep.source_id in affected and dep.target_id in affected:
            attrs["color"] = attrs.get("color", "#1e40af")
            attrs["penwidth"] = "2.5"

        # Add metrics label
        if show_metrics and (dep.latency_p99_ms or dep.error_rate):
            labels = []
            if dep.latency_p99_ms:
                labels.append(f"{dep.latency_p99_ms:.0f}ms")
            if dep.error_rate:
                labels.append(f"{dep.error_rate * 100:.1f}%")
            attrs["label"] = " / ".join(labels)

        return attrs

    def to_d3_json(
        self,
        highlight_service: str | None = None,
    ) -> dict[str, Any]:
        """Export graph to D3.js force-directed graph format.

        Returns:
            {
                "nodes": [{"id": "...", "name": "...", ...}],
                "links": [{"source": "...", "target": "...", ...}]
            }
        """
        affected = set()
        if highlight_service:
            affected = self._analyzer.get_downstream(highlight_service)
            affected.add(highlight_service)

        nodes = []
        for service in self._analyzer.get_all_services():
            risk_score = self._analyzer.calculate_risk_score(service.id)
            nodes.append({
                "id": service.id,
                "name": service.name,
                "team": service.team,
                "criticality": service.criticality.value,
                "health": service.health.value,
                "riskScore": risk_score,
                "fanIn": self._analyzer.get_fan_in(service.id),
                "fanOut": self._analyzer.get_fan_out(service.id),
                "affected": service.id in affected,
                "isHighlighted": service.id == highlight_service,
                "color": self.CRITICALITY_COLORS.get(service.criticality, "#6b7280"),
                "healthColor": self.HEALTH_COLORS.get(service.health, "#6b7280"),
            })

        links = []
        for dep in self._analyzer.get_all_dependencies():
            links.append({
                "source": dep.source_id,
                "target": dep.target_id,
                "id": dep.id,
                "type": dep.dependency_type.value,
                "isCritical": dep.is_critical,
                "latencyMs": dep.latency_p99_ms,
                "errorRate": dep.error_rate,
                "health": dep.health.value,
                "affected": (dep.source_id in affected and dep.target_id in affected),
            })

        return {
            "nodes": nodes,
            "links": links,
            "metadata": {
                "highlightedService": highlight_service,
                "affectedCount": len(affected) - (1 if highlight_service else 0),
                "stats": self._analyzer.get_graph_stats(),
            },
        }

    def to_cytoscape_json(self) -> dict[str, Any]:
        """Export graph to Cytoscape.js format."""
        elements = []

        # Add nodes
        for service in self._analyzer.get_all_services():
            elements.append({
                "data": {
                    "id": service.id,
                    "label": service.name,
                    "criticality": service.criticality.value,
                    "health": service.health.value,
                    "team": service.team,
                    "riskScore": self._analyzer.calculate_risk_score(service.id),
                },
                "classes": f"{service.criticality.value} {service.health.value}",
            })

        # Add edges
        for dep in self._analyzer.get_all_dependencies():
            classes = [dep.dependency_type.value]
            if dep.is_critical:
                classes.append("critical")

            elements.append({
                "data": {
                    "id": dep.id,
                    "source": dep.source_id,
                    "target": dep.target_id,
                    "type": dep.dependency_type.value,
                    "isCritical": dep.is_critical,
                    "latency": dep.latency_p99_ms,
                    "errorRate": dep.error_rate,
                },
                "classes": " ".join(classes),
            })

        return {"elements": elements}

    def to_mermaid(self, highlight_service: str | None = None) -> str:
        """Export graph to Mermaid diagram format."""
        lines = ["graph LR"]

        affected = set()
        if highlight_service:
            affected = self._analyzer.get_downstream(highlight_service)
            affected.add(highlight_service)

        # Define node styles
        lines.append("")
        for service in self._analyzer.get_all_services():
            shape_start, shape_end = "([", "])"  # Stadium shape
            if service.criticality == CriticalityLevel.CRITICAL:
                shape_start, shape_end = "{{", "}}"  # Hexagon
            elif service.criticality == CriticalityLevel.HIGH:
                shape_start, shape_end = "[[", "]]"  # Subroutine

            lines.append(f"    {service.id}{shape_start}{service.name}{shape_end}")

        lines.append("")

        # Add edges
        for dep in self._analyzer.get_all_dependencies():
            arrow = "-->"
            if dep.dependency_type.value == "async":
                arrow = "-.->"
            elif dep.is_critical:
                arrow = "==>"

            label = dep.dependency_type.value
            if dep.latency_p99_ms:
                label = f"{dep.latency_p99_ms:.0f}ms"

            lines.append(f"    {dep.source_id} {arrow}|{label}| {dep.target_id}")

        # Add styling for affected nodes
        if affected:
            lines.append("")
            lines.append("    %% Affected by failure")
            for svc_id in affected:
                lines.append(f"    style {svc_id} fill:#fef3c7,stroke:#f59e0b")
            if highlight_service:
                lines.append(f"    style {highlight_service} fill:#fee2e2,stroke:#dc2626")

        return "\n".join(lines)

    def to_adjacency_matrix(self) -> dict[str, Any]:
        """Export graph as adjacency matrix (useful for analysis)."""
        services = [s.id for s in self._analyzer.get_all_services()]
        n = len(services)
        svc_idx = {svc: i for i, svc in enumerate(services)}

        # Initialize matrix
        matrix = [[0] * n for _ in range(n)]

        # Fill matrix
        for dep in self._analyzer.get_all_dependencies():
            if dep.source_id in svc_idx and dep.target_id in svc_idx:
                i, j = svc_idx[dep.source_id], svc_idx[dep.target_id]
                matrix[i][j] = 2 if dep.is_critical else 1

        return {
            "services": services,
            "matrix": matrix,
            "legend": {0: "no dependency", 1: "dependency", 2: "critical dependency"},
        }
