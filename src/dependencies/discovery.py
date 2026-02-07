"""Auto-discovery of service dependencies from traces and logs."""

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from .models import (
    CriticalityLevel,
    Dependency,
    DependencyType,
    Service,
    ServiceCreate,
    TraceSpan,
)
from .service import DependencyService


class DependencyDiscovery:
    """Discovers service dependencies from distributed tracing and logs."""

    def __init__(self, dependency_service: DependencyService) -> None:
        self._service = dependency_service
        self._seen_edges: dict[tuple[str, str], dict] = {}
        self._span_buffer: list[TraceSpan] = []
        self._service_patterns: dict[str, re.Pattern] = {}

    async def process_trace_spans(self, spans: list[TraceSpan]) -> dict[str, int]:
        """Process trace spans to discover dependencies.

        Returns counts of discovered services and dependencies.
        """
        # Group spans by trace_id
        traces: dict[str, list[TraceSpan]] = defaultdict(list)
        for span in spans:
            traces[span.trace_id].append(span)

        discovered_services = set()
        discovered_deps = 0

        for trace_id, trace_spans in traces.items():
            # Sort by timestamp to reconstruct call order
            trace_spans.sort(key=lambda s: s.timestamp)

            # Build parent-child relationships
            span_map = {s.span_id: s for s in trace_spans}

            for span in trace_spans:
                # Ensure service exists
                await self._ensure_service(span.service_name)
                discovered_services.add(span.service_name)

                # Find parent and create dependency
                if span.parent_span_id and span.parent_span_id in span_map:
                    parent = span_map[span.parent_span_id]
                    if parent.service_name != span.service_name:
                        created = await self._record_dependency(
                            source=parent.service_name,
                            target=span.service_name,
                            span=span,
                        )
                        if created:
                            discovered_deps += 1

        return {
            "services_discovered": len(discovered_services),
            "dependencies_discovered": discovered_deps,
            "traces_processed": len(traces),
        }

    async def _ensure_service(self, service_name: str) -> Service:
        """Ensure a service exists, creating it if necessary."""
        existing = await self._service.get_service(service_name)
        if existing:
            return existing

        # Infer criticality from naming patterns
        criticality = self._infer_criticality(service_name)

        return await self._service.create_service(
            ServiceCreate(
                id=service_name,
                name=service_name,
                description=f"Auto-discovered from tracing",
                criticality=criticality,
                metadata={"auto_discovered": True},
            )
        )

    def _infer_criticality(self, service_name: str) -> CriticalityLevel:
        """Infer criticality level from service name patterns."""
        name_lower = service_name.lower()

        critical_patterns = ["payment", "auth", "identity", "gateway", "api-gateway"]
        high_patterns = ["order", "user", "account", "checkout", "cart"]
        low_patterns = ["test", "dev", "staging", "demo", "mock"]

        for pattern in critical_patterns:
            if pattern in name_lower:
                return CriticalityLevel.CRITICAL

        for pattern in high_patterns:
            if pattern in name_lower:
                return CriticalityLevel.HIGH

        for pattern in low_patterns:
            if pattern in name_lower:
                return CriticalityLevel.LOW

        return CriticalityLevel.MEDIUM

    async def _record_dependency(
        self,
        source: str,
        target: str,
        span: TraceSpan,
    ) -> bool:
        """Record a discovered dependency, updating metrics if it exists."""
        edge_key = (source, target)

        if edge_key in self._seen_edges:
            # Update existing edge metrics
            edge_data = self._seen_edges[edge_key]
            edge_data["call_count"] += 1
            edge_data["total_latency"] += span.duration_ms
            edge_data["error_count"] += 1 if span.error else 0
            edge_data["last_seen"] = span.timestamp

            # Update dependency metrics
            dep = await self._service.get_dependency(edge_data["dependency_id"])
            if dep:
                avg_latency = edge_data["total_latency"] / edge_data["call_count"]
                error_rate = edge_data["error_count"] / edge_data["call_count"]
                requests_per_min = edge_data["call_count"]  # Simplified

                await self._service.update_dependency_metrics(
                    dep.id,
                    latency_p99_ms=avg_latency * 1.5,  # Rough p99 estimate
                    error_rate=error_rate,
                    requests_per_min=requests_per_min,
                )
            return False

        # Create new dependency
        dep_type = self._infer_dependency_type(span)
        from .models import DependencyCreate

        dep = await self._service.create_dependency(
            DependencyCreate(
                source_id=source,
                target_id=target,
                dependency_type=dep_type,
                metadata={
                    "discovered_from": "tracing",
                    "first_trace_id": span.trace_id,
                },
            )
        )

        if dep:
            self._seen_edges[edge_key] = {
                "dependency_id": dep.id,
                "call_count": 1,
                "total_latency": span.duration_ms,
                "error_count": 1 if span.error else 0,
                "last_seen": span.timestamp,
            }
            return True

        return False

    def _infer_dependency_type(self, span: TraceSpan) -> DependencyType:
        """Infer dependency type from span attributes."""
        operation = span.operation_name.lower()
        tags = {k.lower(): v.lower() for k, v in span.tags.items()}

        # Check for async messaging
        if any(x in operation for x in ["kafka", "rabbit", "pubsub", "sqs"]):
            return DependencyType.ASYNC
        if tags.get("messaging.system"):
            return DependencyType.ASYNC

        # Check for database
        if any(x in operation for x in ["query", "select", "insert", "update"]):
            return DependencyType.DATABASE
        if tags.get("db.system"):
            return DependencyType.DATABASE

        # Check for cache
        if any(x in operation for x in ["redis", "memcache", "cache"]):
            return DependencyType.CACHE

        # Check for storage
        if any(x in operation for x in ["s3", "gcs", "blob", "storage"]):
            return DependencyType.STORAGE

        return DependencyType.SYNC

    async def process_log_entries(self, logs: list[dict[str, Any]]) -> dict[str, int]:
        """Discover dependencies from structured log entries.

        Expected log format:
        {
            "timestamp": "...",
            "service": "service-a",
            "message": "...",
            "caller": "service-b",  # optional
            "target_service": "service-c",  # optional
            "http.url": "http://service-c/api/...",  # optional
        }
        """
        discovered_deps = 0
        services_seen = set()

        for log in logs:
            service = log.get("service")
            if not service:
                continue

            services_seen.add(service)
            await self._ensure_service(service)

            # Method 1: Explicit caller field
            caller = log.get("caller")
            if caller and caller != service:
                services_seen.add(caller)
                await self._ensure_service(caller)
                # Caller -> service dependency
                await self._create_log_dependency(caller, service, log)
                discovered_deps += 1

            # Method 2: Explicit target_service field
            target = log.get("target_service")
            if target and target != service:
                services_seen.add(target)
                await self._ensure_service(target)
                # service -> target dependency
                await self._create_log_dependency(service, target, log)
                discovered_deps += 1

            # Method 3: Parse URLs for service names
            url = log.get("http.url") or log.get("url")
            if url:
                target_from_url = self._extract_service_from_url(url)
                if target_from_url and target_from_url != service:
                    services_seen.add(target_from_url)
                    await self._ensure_service(target_from_url)
                    await self._create_log_dependency(service, target_from_url, log)
                    discovered_deps += 1

        return {
            "services_seen": len(services_seen),
            "dependencies_discovered": discovered_deps,
            "logs_processed": len(logs),
        }

    async def _create_log_dependency(
        self,
        source: str,
        target: str,
        log: dict[str, Any],
    ) -> None:
        """Create dependency from log entry."""
        edge_key = (source, target)
        if edge_key in self._seen_edges:
            return

        from .models import DependencyCreate

        dep = await self._service.create_dependency(
            DependencyCreate(
                source_id=source,
                target_id=target,
                dependency_type=DependencyType.SYNC,
                metadata={
                    "discovered_from": "logs",
                    "first_log_timestamp": log.get("timestamp"),
                },
            )
        )

        if dep:
            self._seen_edges[edge_key] = {
                "dependency_id": dep.id,
                "call_count": 1,
                "last_seen": datetime.utcnow(),
            }

    def _extract_service_from_url(self, url: str) -> str | None:
        """Extract service name from URL (internal service discovery)."""
        # Match patterns like http://service-name:port/... or http://service-name/...
        patterns = [
            r"https?://([a-z0-9-]+)(?::\d+)?/",  # http://service-name:8080/
            r"https?://([a-z0-9-]+)\.[a-z]+/",  # http://service-name.svc/
        ]

        for pattern in patterns:
            match = re.search(pattern, url.lower())
            if match:
                service = match.group(1)
                # Filter out common non-service hosts
                if service not in ["localhost", "127", "0"]:
                    return service

        return None

    def register_service_pattern(self, name: str, pattern: str) -> None:
        """Register a regex pattern for identifying services in logs."""
        self._service_patterns[name] = re.compile(pattern)

    async def cleanup_stale_dependencies(
        self,
        max_age: timedelta = timedelta(days=7),
    ) -> int:
        """Remove dependencies not seen within max_age."""
        now = datetime.utcnow()
        removed = 0

        stale_keys = []
        for edge_key, edge_data in self._seen_edges.items():
            last_seen = edge_data.get("last_seen")
            if last_seen and (now - last_seen) > max_age:
                dep_id = edge_data.get("dependency_id")
                if dep_id and await self._service.delete_dependency(dep_id):
                    removed += 1
                stale_keys.append(edge_key)

        for key in stale_keys:
            del self._seen_edges[key]

        return removed

    def get_discovery_stats(self) -> dict[str, Any]:
        """Get statistics about discovered dependencies."""
        return {
            "tracked_edges": len(self._seen_edges),
            "registered_patterns": len(self._service_patterns),
            "edges_by_source": self._count_by_source(),
        }

    def _count_by_source(self) -> dict[str, int]:
        """Count discovered edges by source service."""
        counts: dict[str, int] = defaultdict(int)
        for source, _ in self._seen_edges.keys():
            counts[source] += 1
        return dict(counts)
