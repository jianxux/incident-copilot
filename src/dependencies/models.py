"""Data models for Service Dependency Mapping."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ServiceTier(str, Enum):
    """Service criticality tiers."""

    TIER_1 = "tier_1"  # Mission critical - customer-facing, revenue-impacting
    TIER_2 = "tier_2"  # Important - internal services, supporting critical flows
    TIER_3 = "tier_3"  # Standard - non-critical services
    TIER_4 = "tier_4"  # Low priority - development/test services


class DependencyType(str, Enum):
    """Types of service dependencies."""

    API = "api"  # REST/gRPC API calls
    DATABASE = "database"  # Database connections
    QUEUE = "queue"  # Message queue (Kafka, RabbitMQ, SQS)
    CACHE = "cache"  # Cache services (Redis, Memcached)
    STORAGE = "storage"  # Object storage (S3, GCS)
    EVENT = "event"  # Event-driven (pub/sub)
    STREAM = "stream"  # Streaming data
    FILE = "file"  # File system dependencies
    EXTERNAL = "external"  # External third-party services
    INTERNAL = "internal"  # Internal library/SDK
    UNKNOWN = "unknown"


class HealthStatus(str, Enum):
    """Service health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class Service(BaseModel):
    """A service in the dependency graph."""

    id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Human-readable service name")
    description: str | None = Field(default=None, description="Service description")

    # Ownership
    team_owner: str | None = Field(default=None, description="Owning team name")
    team_slack_channel: str | None = Field(
        default=None, description="Team's Slack channel"
    )
    pagerduty_service_id: str | None = Field(
        default=None, description="PagerDuty service ID"
    )
    oncall_schedule_id: str | None = Field(
        default=None, description="On-call schedule ID"
    )

    # Classification
    tier: ServiceTier = Field(
        default=ServiceTier.TIER_3, description="Service criticality tier"
    )
    sla_availability: float | None = Field(
        default=None, description="SLA availability target (e.g., 99.9)"
    )
    sla_latency_p99_ms: int | None = Field(
        default=None, description="SLA P99 latency target in milliseconds"
    )

    # Technical metadata
    repository_url: str | None = Field(
        default=None, description="Source code repository URL"
    )
    documentation_url: str | None = Field(
        default=None, description="Documentation URL"
    )
    runbook_url: str | None = Field(default=None, description="Runbook URL")
    dashboard_url: str | None = Field(
        default=None, description="Monitoring dashboard URL"
    )

    # Runtime info
    environment: str = Field(
        default="production", description="Environment (production, staging, etc.)"
    )
    region: str | None = Field(default=None, description="Deployment region")
    kubernetes_namespace: str | None = Field(
        default=None, description="Kubernetes namespace"
    )

    # Current status (for live data)
    health_status: HealthStatus = Field(
        default=HealthStatus.UNKNOWN, description="Current health status"
    )
    last_incident_at: datetime | None = Field(
        default=None, description="Last incident timestamp"
    )
    incident_count_30d: int = Field(
        default=0, description="Incident count in last 30 days"
    )

    # Metadata
    tags: list[str] = Field(default_factory=list, description="Service tags")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def impact_weight(self) -> float:
        """Calculate impact weight based on tier and SLA."""
        tier_weights = {
            ServiceTier.TIER_1: 1.0,
            ServiceTier.TIER_2: 0.7,
            ServiceTier.TIER_3: 0.4,
            ServiceTier.TIER_4: 0.1,
        }
        return tier_weights.get(self.tier, 0.4)


class Dependency(BaseModel):
    """A dependency between two services."""

    id: str = Field(..., description="Unique dependency identifier")
    source_service_id: str = Field(
        ..., description="Service that depends on another (caller)"
    )
    target_service_id: str = Field(
        ..., description="Service being depended upon (dependency)"
    )

    # Dependency characteristics
    dependency_type: DependencyType = Field(
        default=DependencyType.API, description="Type of dependency"
    )
    is_critical: bool = Field(
        default=False,
        description="Whether this is a critical dependency (failure causes outage)",
    )
    is_synchronous: bool = Field(
        default=True, description="Whether the dependency is synchronous"
    )
    has_circuit_breaker: bool = Field(
        default=False, description="Whether a circuit breaker is configured"
    )
    has_fallback: bool = Field(
        default=False, description="Whether a fallback mechanism exists"
    )
    timeout_ms: int | None = Field(
        default=None, description="Configured timeout in milliseconds"
    )
    retry_count: int | None = Field(
        default=None, description="Configured retry count"
    )

    # Discovery metadata
    discovered_via: str | None = Field(
        default=None,
        description="How this dependency was discovered (manual, k8s, docker-compose, etc.)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for auto-discovered dependencies",
    )
    last_observed_at: datetime | None = Field(
        default=None, description="Last time this dependency was observed active"
    )

    # Additional context
    description: str | None = Field(default=None, description="Dependency description")
    api_endpoint: str | None = Field(
        default=None, description="API endpoint if applicable"
    )
    database_name: str | None = Field(
        default=None, description="Database name if applicable"
    )
    queue_name: str | None = Field(
        default=None, description="Queue/topic name if applicable"
    )

    # Metadata
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BlastRadiusResult(BaseModel):
    """Result of a blast radius calculation."""

    source_service_id: str = Field(..., description="Service that's the origin of impact")
    affected_services: list[str] = Field(
        default_factory=list, description="List of affected service IDs"
    )
    affected_services_by_depth: dict[int, list[str]] = Field(
        default_factory=dict,
        description="Services grouped by dependency depth (1=direct, 2=indirect, etc.)",
    )
    total_impact_score: float = Field(
        default=0.0, description="Total calculated impact score"
    )
    critical_path_services: list[str] = Field(
        default_factory=list,
        description="Services on critical paths (highest impact)",
    )
    tier_1_affected: int = Field(default=0, description="Number of Tier 1 services affected")
    tier_2_affected: int = Field(default=0, description="Number of Tier 2 services affected")
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


class ServiceCatalogStats(BaseModel):
    """Statistics about the service catalog."""

    total_services: int = Field(default=0)
    total_dependencies: int = Field(default=0)
    services_by_tier: dict[str, int] = Field(default_factory=dict)
    services_by_team: dict[str, int] = Field(default_factory=dict)
    dependency_types: dict[str, int] = Field(default_factory=dict)
    avg_dependencies_per_service: float = Field(default=0.0)
    most_depended_upon: list[tuple[str, int]] = Field(default_factory=list)
    most_dependencies: list[tuple[str, int]] = Field(default_factory=list)
    orphan_services: list[str] = Field(
        default_factory=list,
        description="Services with no dependencies in either direction",
    )
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


# --- Request/Response Models ---


class ServiceCreateRequest(BaseModel):
    """Request to create a new service."""

    id: str
    name: str
    description: str | None = None
    team_owner: str | None = None
    tier: ServiceTier = ServiceTier.TIER_3
    sla_availability: float | None = None
    repository_url: str | None = None
    documentation_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ServiceUpdateRequest(BaseModel):
    """Request to update an existing service."""

    name: str | None = None
    description: str | None = None
    team_owner: str | None = None
    team_slack_channel: str | None = None
    tier: ServiceTier | None = None
    sla_availability: float | None = None
    sla_latency_p99_ms: int | None = None
    repository_url: str | None = None
    documentation_url: str | None = None
    runbook_url: str | None = None
    dashboard_url: str | None = None
    health_status: HealthStatus | None = None
    tags: list[str] | None = None
    metadata: dict | None = None


class DependencyCreateRequest(BaseModel):
    """Request to create a new dependency."""

    source_service_id: str
    target_service_id: str
    dependency_type: DependencyType = DependencyType.API
    is_critical: bool = False
    is_synchronous: bool = True
    has_circuit_breaker: bool = False
    has_fallback: bool = False
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class DependencyUpdateRequest(BaseModel):
    """Request to update an existing dependency."""

    dependency_type: DependencyType | None = None
    is_critical: bool | None = None
    is_synchronous: bool | None = None
    has_circuit_breaker: bool | None = None
    has_fallback: bool | None = None
    timeout_ms: int | None = None
    retry_count: int | None = None
    description: str | None = None
    metadata: dict | None = None


class DiscoveryRequest(BaseModel):
    """Request to trigger dependency discovery."""

    source_type: str = Field(
        ...,
        description="Source type: github, docker_compose, kubernetes, terraform",
    )
    repository_url: str | None = Field(
        default=None, description="Repository URL for GitHub-based discovery"
    )
    file_path: str | None = Field(
        default=None, description="Path to config file for local discovery"
    )
    namespace: str | None = Field(
        default=None, description="Kubernetes namespace for k8s discovery"
    )
    dry_run: bool = Field(
        default=True,
        description="If true, returns discovered dependencies without saving",
    )


class DiscoveryResult(BaseModel):
    """Result of dependency discovery."""

    source_type: str
    services_discovered: list[Service] = Field(default_factory=list)
    dependencies_discovered: list[Dependency] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
