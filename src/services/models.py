"""Pydantic models for persistent service catalog."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ServiceCriticality(StrEnum):
    """Service criticality levels for business impact."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ServiceHealth(StrEnum):
    """Service or dependency health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceDependencyType(StrEnum):
    """Dependency type for service relationships."""

    SYNC = "sync"
    ASYNC = "async"
    DATABASE = "database"
    CACHE = "cache"
    STORAGE = "storage"
    RUNTIME = "runtime"


class ServiceEnvironment(BaseModel):
    """Environment-specific service deployment metadata."""

    id: str | None = None
    service_id: str
    environment: str = "production"
    region: str | None = None
    cluster: str | None = None
    namespace: str | None = None
    version: str | None = None
    is_primary: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_seen_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Service(BaseModel):
    """Service catalog record."""

    id: str
    name: str
    tenant_id: str | None = None
    description: str | None = None
    team: str | None = None
    owner_email: str | None = None
    criticality: ServiceCriticality = ServiceCriticality.MEDIUM
    health: ServiceHealth = ServiceHealth.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    critical_user_journey: bool = False
    repo_url: str | None = None
    dashboard_url: str | None = None
    runbook_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    environments: list[ServiceEnvironment] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ServiceCreate(BaseModel):
    """Create request for service catalog records."""

    id: str | None = None
    name: str
    description: str | None = None
    team: str | None = None
    owner_email: str | None = None
    criticality: ServiceCriticality = ServiceCriticality.MEDIUM
    health: ServiceHealth = ServiceHealth.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    critical_user_journey: bool = False
    repo_url: str | None = None
    dashboard_url: str | None = None
    runbook_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    environments: list[ServiceEnvironment] = Field(default_factory=list)


class ServiceUpdate(BaseModel):
    """Update request for service catalog records."""

    name: str | None = None
    description: str | None = None
    team: str | None = None
    owner_email: str | None = None
    criticality: ServiceCriticality | None = None
    health: ServiceHealth | None = None
    tags: list[str] | None = None
    critical_user_journey: bool | None = None
    repo_url: str | None = None
    dashboard_url: str | None = None
    runbook_url: str | None = None
    metadata: dict[str, Any] | None = None
    environments: list[ServiceEnvironment] | None = None


class ServiceDependency(BaseModel):
    """Dependency edge between two services."""

    id: str | None = None
    source_service_id: str
    target_service_id: str
    tenant_id: str | None = None
    dependency_type: ServiceDependencyType = ServiceDependencyType.SYNC
    is_critical: bool = False
    latency_p99_ms: float | None = None
    error_rate: float | None = None
    requests_per_min: float | None = None
    health: ServiceHealth = ServiceHealth.UNKNOWN
    discovered_from: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    discovered_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


class ServiceDependencyCreate(BaseModel):
    """Create request for service dependency edge."""

    target_service_id: str
    dependency_type: ServiceDependencyType = ServiceDependencyType.SYNC
    is_critical: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceDependencyUpdate(BaseModel):
    """Update request for dependency edge metrics or flags."""

    dependency_type: ServiceDependencyType | None = None
    is_critical: bool | None = None
    latency_p99_ms: float | None = None
    error_rate: float | None = None
    requests_per_min: float | None = None
    health: ServiceHealth | None = None
    discovered_from: str | None = None
    metadata: dict[str, Any] | None = None
