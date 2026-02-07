"""Tests for dependency graph and blast radius module."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.dependencies.models import (
    BlastRadius,
    CriticalityLevel,
    CycleInfo,
    Dependency,
    DependencyCreate,
    DependencyGraph,
    DependencyPath,
    DependencyType,
    GraphStats,
    HealthStatus,
    Service,
    ServiceCreate,
    TraceSpan,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_services() -> list[Service]:
    """Create sample services for testing."""
    return [
        Service(
            id="api-gateway",
            name="API Gateway",
            team="platform",
            criticality=CriticalityLevel.CRITICAL,
            health=HealthStatus.HEALTHY,
        ),
        Service(
            id="user-service",
            name="User Service",
            team="identity",
            criticality=CriticalityLevel.HIGH,
            health=HealthStatus.HEALTHY,
        ),
        Service(
            id="payments",
            name="Payments Service",
            team="payments",
            criticality=CriticalityLevel.CRITICAL,
            health=HealthStatus.DEGRADED,
        ),
        Service(
            id="notifications",
            name="Notification Service",
            team="platform",
            criticality=CriticalityLevel.MEDIUM,
            health=HealthStatus.HEALTHY,
        ),
    ]


@pytest.fixture
def sample_dependencies() -> list[Dependency]:
    """Create sample dependencies for testing."""
    return [
        Dependency(
            id="dep-1",
            source_id="api-gateway",
            target_id="user-service",
            dependency_type=DependencyType.SYNC,
            is_critical=True,
        ),
        Dependency(
            id="dep-2",
            source_id="api-gateway",
            target_id="payments",
            dependency_type=DependencyType.SYNC,
            is_critical=True,
        ),
        Dependency(
            id="dep-3",
            source_id="payments",
            target_id="notifications",
            dependency_type=DependencyType.ASYNC,
            is_critical=False,
        ),
    ]


class TestCriticalityLevel:
    """Tests for CriticalityLevel enum."""

    def test_criticality_values(self):
        """Test all criticality levels exist."""
        assert CriticalityLevel.CRITICAL.value == "critical"
        assert CriticalityLevel.HIGH.value == "high"
        assert CriticalityLevel.MEDIUM.value == "medium"
        assert CriticalityLevel.LOW.value == "low"


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_dependency_type_values(self):
        """Test all dependency types exist."""
        assert DependencyType.SYNC.value == "sync"
        assert DependencyType.ASYNC.value == "async"
        assert DependencyType.DATABASE.value == "database"
        assert DependencyType.CACHE.value == "cache"
        assert DependencyType.STORAGE.value == "storage"


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """Test all health statuses exist."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestService:
    """Tests for Service model."""

    def test_service_creation(self, sample_services):
        """Test creating a service."""
        svc = sample_services[0]
        assert svc.id == "api-gateway"
        assert svc.criticality == CriticalityLevel.CRITICAL
        assert svc.health == HealthStatus.HEALTHY

    def test_service_defaults(self):
        """Test service default values."""
        svc = Service(id="new-svc", name="New Service")
        assert svc.criticality == CriticalityLevel.MEDIUM
        assert svc.health == HealthStatus.UNKNOWN
        assert svc.tags == []

    def test_service_with_tags(self):
        """Test service with tags."""
        svc = Service(
            id="tagged",
            name="Tagged Service",
            tags=["production", "core"],
        )
        assert len(svc.tags) == 2


class TestServiceCreate:
    """Tests for ServiceCreate request model."""

    def test_service_create_request(self):
        """Test creating a service create request."""
        request = ServiceCreate(
            id="new-service",
            name="New Service",
            team="platform",
            criticality=CriticalityLevel.HIGH,
        )
        assert request.id == "new-service"


class TestDependency:
    """Tests for Dependency model."""

    def test_dependency_creation(self, sample_dependencies):
        """Test creating a dependency."""
        dep = sample_dependencies[0]
        assert dep.source_id == "api-gateway"
        assert dep.target_id == "user-service"
        assert dep.is_critical

    def test_dependency_with_metrics(self):
        """Test dependency with performance metrics."""
        dep = Dependency(
            id="dep-metrics",
            source_id="svc-a",
            target_id="svc-b",
            latency_p99_ms=150.0,
            error_rate=0.01,
            requests_per_min=1000.0,
        )
        assert dep.latency_p99_ms == 150.0
        assert dep.error_rate == 0.01

    def test_dependency_defaults(self):
        """Test dependency default values."""
        dep = Dependency(
            id="dep-default",
            source_id="a",
            target_id="b",
        )
        assert dep.dependency_type == DependencyType.SYNC
        assert not dep.is_critical
        assert dep.health == HealthStatus.UNKNOWN


class TestDependencyCreate:
    """Tests for DependencyCreate request model."""

    def test_dependency_create_request(self):
        """Test creating a dependency create request."""
        request = DependencyCreate(
            source_id="svc-a",
            target_id="svc-b",
            dependency_type=DependencyType.ASYNC,
            is_critical=True,
        )
        assert request.source_id == "svc-a"
        assert request.is_critical


class TestDependencyPath:
    """Tests for DependencyPath model."""

    def test_path_creation(self):
        """Test creating a dependency path."""
        path = DependencyPath(
            source_id="api-gateway",
            target_id="database",
            path=["api-gateway", "user-service", "database"],
            length=2,
            has_critical_hop=True,
        )
        assert path.length == 2
        assert len(path.path) == 3
        assert path.has_critical_hop


class TestBlastRadius:
    """Tests for BlastRadius model."""

    def test_blast_radius_creation(self):
        """Test creating a blast radius analysis."""
        blast = BlastRadius(
            failed_service_id="database",
            affected_services=["user-service", "payments", "api-gateway"],
            affected_count=3,
            critical_affected=["payments"],
            risk_score=85.0,
            max_depth=2,
        )
        assert blast.affected_count == 3
        assert len(blast.critical_affected) == 1
        assert blast.risk_score == 85.0

    def test_blast_radius_empty(self):
        """Test blast radius with no affected services."""
        blast = BlastRadius(
            failed_service_id="isolated-service",
            risk_score=0.0,
        )
        assert blast.affected_count == 0
        assert blast.risk_score == 0.0


class TestCycleInfo:
    """Tests for CycleInfo model."""

    def test_cycle_creation(self):
        """Test creating cycle info."""
        cycle = CycleInfo(
            cycle=["svc-a", "svc-b", "svc-c", "svc-a"],
            length=3,
            involves_critical=True,
        )
        assert cycle.length == 3
        assert cycle.involves_critical


class TestDependencyGraph:
    """Tests for DependencyGraph model."""

    def test_graph_creation(self, sample_services, sample_dependencies):
        """Test creating a dependency graph."""
        graph = DependencyGraph(
            services=sample_services,
            dependencies=sample_dependencies,
            service_count=len(sample_services),
            dependency_count=len(sample_dependencies),
            has_cycles=False,
            max_depth=2,
        )
        assert graph.service_count == 4
        assert graph.dependency_count == 3
        assert not graph.has_cycles

    def test_graph_with_cycles(self):
        """Test graph with cycles."""
        graph = DependencyGraph(
            has_cycles=True,
            cycles=[
                CycleInfo(
                    cycle=["a", "b", "c", "a"],
                    length=3,
                    involves_critical=False,
                )
            ],
        )
        assert graph.has_cycles
        assert len(graph.cycles) == 1


class TestGraphStats:
    """Tests for GraphStats model."""

    def test_stats_creation(self):
        """Test creating graph statistics."""
        stats = GraphStats(
            total_services=50,
            total_dependencies=120,
            critical_services=8,
            healthy_services=45,
            unhealthy_services=2,
            avg_dependencies_per_service=2.4,
            max_fan_out=12,
            max_fan_in=8,
            cycle_count=1,
            isolated_services=3,
        )
        assert stats.total_services == 50
        assert stats.max_fan_out == 12


class TestTraceSpan:
    """Tests for TraceSpan model."""

    def test_span_creation(self):
        """Test creating a trace span."""
        span = TraceSpan(
            trace_id="trace-123",
            span_id="span-456",
            parent_span_id="span-000",
            service_name="user-service",
            operation_name="getUser",
            duration_ms=25.5,
            timestamp=datetime.utcnow(),
        )
        assert span.service_name == "user-service"
        assert span.duration_ms == 25.5
        assert not span.error


class TestDependenciesAPI:
    """Tests for Dependencies API endpoints."""

    def test_list_services(self, client):
        """Test GET /api/dependencies/services endpoint."""
        response = client.get("/api/dependencies/services")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_service(self, client):
        """Test POST /api/dependencies/services endpoint."""
        response = client.post(
            "/api/dependencies/services",
            json={
                "id": "new-svc",
                "name": "New Service",
                "team": "platform",
            },
        )
        assert response.status_code in (200, 201)

    def test_get_service(self, client):
        """Test GET /api/dependencies/services/{id} endpoint."""
        response = client.get("/api/dependencies/services/api-gateway")
        assert response.status_code in (200, 404)

    def test_list_dependencies(self, client):
        """Test GET /api/dependencies endpoint."""
        response = client.get("/api/dependencies")
        assert response.status_code == 200

    def test_create_dependency(self, client):
        """Test POST /api/dependencies endpoint."""
        response = client.post(
            "/api/dependencies",
            json={
                "source_id": "svc-a",
                "target_id": "svc-b",
                "dependency_type": "sync",
            },
        )
        assert response.status_code in (200, 201)

    def test_get_graph(self, client):
        """Test GET /api/dependencies/graph endpoint."""
        response = client.get("/api/dependencies/graph")
        assert response.status_code == 200

    def test_get_blast_radius(self, client):
        """Test GET /api/dependencies/blast-radius/{service_id} endpoint."""
        response = client.get("/api/dependencies/blast-radius/database")
        assert response.status_code in (200, 404)

    def test_find_path(self, client):
        """Test GET /api/dependencies/path endpoint."""
        response = client.get(
            "/api/dependencies/path?source=api-gateway&target=database"
        )
        assert response.status_code in (200, 404)

    def test_get_graph_stats(self, client):
        """Test GET /api/dependencies/stats endpoint."""
        response = client.get("/api/dependencies/stats")
        assert response.status_code == 200

    def test_discover_from_traces(self, client):
        """Test POST /api/dependencies/discover endpoint."""
        response = client.post(
            "/api/dependencies/discover",
            json={
                "spans": [
                    {
                        "trace_id": "t1",
                        "span_id": "s1",
                        "service_name": "api",
                        "operation_name": "handleRequest",
                        "duration_ms": 100,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ]
            },
        )
        assert response.status_code in (200, 202)

    def test_get_service_dependencies(self, client):
        """Test GET /api/dependencies/services/{id}/dependencies endpoint."""
        response = client.get("/api/dependencies/services/api-gateway/dependencies")
        assert response.status_code in (200, 404)

    def test_get_service_dependents(self, client):
        """Test GET /api/dependencies/services/{id}/dependents endpoint."""
        response = client.get("/api/dependencies/services/database/dependents")
        assert response.status_code in (200, 404)
