"""Pydantic models for service dependencies."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CriticalityLevel(str, Enum):
    """Service criticality levels."""

    CRITICAL = "critical"  # Core infrastructure, payment, auth
    HIGH = "high"  # Customer-facing primary features
    MEDIUM = "medium"  # Secondary features, internal tools
    LOW = "low"  # Nice-to-have, experimental


class DependencyType(str, Enum):
    """Type of dependency relationship."""

    SYNC = "sync"  # Synchronous call (HTTP, gRPC)
    ASYNC = "async"  # Async messaging (Kafka, RabbitMQ)
    DATABASE = "database"  # Database dependency
    CACHE = "cache"  # Cache dependency (Redis, Memcached)
    STORAGE = "storage"  # Object storage (S3, GCS)


class HealthStatus(str, Enum):
    """Health status of a service or dependency."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class Service(BaseModel):
    """A service in the dependency graph."""

    id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Human-readable service name")
    description: str | None = Field(None, description="Service description")
    team: str | None = Field(None, description="Owning team")
    criticality: CriticalityLevel = Field(
        default=CriticalityLevel.MEDIUM, description="Service criticality level"
    )
    health: HealthStatus = Field(
        default=HealthStatus.UNKNOWN, description="Current health status"
    )
    tags: list[str] = Field(default_factory=list, description="Service tags")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ServiceCreate(BaseModel):
    """Request to create a service."""

    id: str
    name: str
    description: str | None = None
    team: str | None = None
    criticality: CriticalityLevel = CriticalityLevel.MEDIUM
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Dependency(BaseModel):
    """A dependency relationship between two services."""

    id: str = Field(..., description="Unique dependency ID")
    source_id: str = Field(..., description="Source service (caller)")
    target_id: str = Field(..., description="Target service (callee)")
    dependency_type: DependencyType = Field(
        default=DependencyType.SYNC, description="Type of dependency"
    )
    is_critical: bool = Field(
        default=False, description="Whether this dependency is critical for source"
    )
    latency_p99_ms: float | None = Field(None, description="P99 latency in ms")
    error_rate: float | None = Field(None, description="Error rate (0-1)")
    requests_per_min: float | None = Field(None, description="Request rate")
    health: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DependencyCreate(BaseModel):
    """Request to create a dependency."""

    source_id: str
    target_id: str
    dependency_type: DependencyType = DependencyType.SYNC
    is_critical: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class DependencyPath(BaseModel):
    """A path between two services in the dependency graph."""

    source_id: str
    target_id: str
    path: list[str] = Field(..., description="Ordered list of service IDs")
    length: int
    has_critical_hop: bool = Field(
        default=False, description="Whether path includes critical dependency"
    )


class BlastRadius(BaseModel):
    """Blast radius analysis for a service failure."""

    failed_service_id: str
    affected_services: list[str] = Field(
        default_factory=list, description="Services affected by failure (downstream)"
    )
    affected_count: int = 0
    critical_affected: list[str] = Field(
        default_factory=list, description="Critical services affected"
    )
    risk_score: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Risk score (0-100)"
    )
    impact_paths: list[DependencyPath] = Field(
        default_factory=list, description="Paths to affected services"
    )
    max_depth: int = Field(default=0, description="Max impact depth")
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class CycleInfo(BaseModel):
    """Information about a dependency cycle."""

    cycle: list[str] = Field(..., description="Service IDs forming cycle")
    length: int
    involves_critical: bool = Field(
        default=False, description="Whether cycle involves critical services"
    )


class DependencyGraph(BaseModel):
    """Complete dependency graph representation."""

    services: list[Service] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    cycles: list[CycleInfo] = Field(default_factory=list)
    service_count: int = 0
    dependency_count: int = 0
    has_cycles: bool = False
    max_depth: int = 0
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class GraphStats(BaseModel):
    """Statistics about the dependency graph."""

    total_services: int = 0
    total_dependencies: int = 0
    critical_services: int = 0
    healthy_services: int = 0
    unhealthy_services: int = 0
    avg_dependencies_per_service: float = 0.0
    max_fan_out: int = 0  # Most dependencies from a single service
    max_fan_in: int = 0  # Most dependents on a single service
    cycle_count: int = 0
    isolated_services: int = 0  # Services with no dependencies


class TraceSpan(BaseModel):
    """A span from distributed tracing for discovery."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    service_name: str
    operation_name: str
    duration_ms: float
    timestamp: datetime
    tags: dict[str, str] = Field(default_factory=dict)
    error: bool = False
