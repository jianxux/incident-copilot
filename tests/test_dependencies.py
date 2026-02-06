"""Comprehensive tests for the Service Dependency Mapping system."""

import pytest

from src.dependencies.discovery import DependencyDiscovery
from src.dependencies.graph import DependencyGraph
from src.dependencies.models import (
    BlastRadiusResult,
    Dependency,
    DependencyCreateRequest,
    DependencyType,
    HealthStatus,
    Service,
    ServiceCreateRequest,
    ServiceTier,
    ServiceUpdateRequest,
)
from src.dependencies.store import DependencyStore
from src.dependencies.visualizer import DependencyVisualizer, NodeType


class TestService:
    """Tests for Service model."""

    def test_service_creation(self):
        """Test creating a service with required fields."""
        service = Service(
            id="payments-api",
            name="Payments API",
        )
        assert service.id == "payments-api"
        assert service.name == "Payments API"
        assert service.tier == ServiceTier.TIER_3  # Default
        assert service.health_status == HealthStatus.UNKNOWN

    def test_service_with_full_metadata(self):
        """Test creating a service with all metadata."""
        service = Service(
            id="payments-api",
            name="Payments API",
            description="Handles payment processing",
            team_owner="payments-team",
            tier=ServiceTier.TIER_1,
            sla_availability=99.99,
            sla_latency_p99_ms=200,
            repository_url="https://github.com/company/payments-api",
            tags=["payments", "critical"],
        )
        assert service.tier == ServiceTier.TIER_1
        assert service.sla_availability == 99.99
        assert "payments" in service.tags

    def test_impact_weight_by_tier(self):
        """Test that impact weight varies by tier."""
        tier_1 = Service(id="t1", name="T1", tier=ServiceTier.TIER_1)
        tier_2 = Service(id="t2", name="T2", tier=ServiceTier.TIER_2)
        tier_3 = Service(id="t3", name="T3", tier=ServiceTier.TIER_3)
        tier_4 = Service(id="t4", name="T4", tier=ServiceTier.TIER_4)

        assert tier_1.impact_weight() == 1.0
        assert tier_2.impact_weight() == 0.7
        assert tier_3.impact_weight() == 0.4
        assert tier_4.impact_weight() == 0.1


class TestDependency:
    """Tests for Dependency model."""

    def test_dependency_creation(self):
        """Test creating a dependency."""
        dep = Dependency(
            id="dep-1",
            source_service_id="payments-api",
            target_service_id="user-service",
        )
        assert dep.source_service_id == "payments-api"
        assert dep.target_service_id == "user-service"
        assert dep.dependency_type == DependencyType.API
        assert dep.is_synchronous is True

    def test_dependency_with_metadata(self):
        """Test dependency with full metadata."""
        dep = Dependency(
            id="dep-1",
            source_service_id="payments-api",
            target_service_id="postgres",
            dependency_type=DependencyType.DATABASE,
            is_critical=True,
            has_circuit_breaker=True,
            timeout_ms=5000,
            database_name="payments_db",
        )
        assert dep.dependency_type == DependencyType.DATABASE
        assert dep.is_critical is True
        assert dep.timeout_ms == 5000


class TestDependencyStore:
    """Tests for DependencyStore."""

    @pytest.fixture
    def store(self):
        """Create a fresh store for each test."""
        return DependencyStore()

    @pytest.fixture
    async def populated_store(self, store):
        """Create a store with sample data."""
        # Create services
        services = [
            Service(id="api-gateway", name="API Gateway", tier=ServiceTier.TIER_1),
            Service(id="payments-api", name="Payments API", tier=ServiceTier.TIER_1),
            Service(id="user-service", name="User Service", tier=ServiceTier.TIER_2),
            Service(id="notification-service", name="Notification Service", tier=ServiceTier.TIER_3),
            Service(id="postgres", name="PostgreSQL", tier=ServiceTier.TIER_1),
            Service(id="redis", name="Redis Cache", tier=ServiceTier.TIER_2),
        ]
        for s in services:
            await store.save_service(s)

        # Create dependencies
        dependencies = [
            Dependency(
                id="dep-1",
                source_service_id="api-gateway",
                target_service_id="payments-api",
                is_critical=True,
            ),
            Dependency(
                id="dep-2",
                source_service_id="api-gateway",
                target_service_id="user-service",
            ),
            Dependency(
                id="dep-3",
                source_service_id="payments-api",
                target_service_id="postgres",
                dependency_type=DependencyType.DATABASE,
                is_critical=True,
            ),
            Dependency(
                id="dep-4",
                source_service_id="payments-api",
                target_service_id="redis",
                dependency_type=DependencyType.CACHE,
            ),
            Dependency(
                id="dep-5",
                source_service_id="user-service",
                target_service_id="postgres",
                dependency_type=DependencyType.DATABASE,
            ),
            Dependency(
                id="dep-6",
                source_service_id="payments-api",
                target_service_id="notification-service",
                is_synchronous=False,
            ),
        ]
        for d in dependencies:
            await store.save_dependency(d)

        return store

    @pytest.mark.asyncio
    async def test_save_and_get_service(self, store):
        """Test saving and retrieving a service."""
        service = Service(id="test-svc", name="Test Service")
        await store.save_service(service)

        retrieved = await store.get_service("test-svc")
        assert retrieved is not None
        assert retrieved.id == "test-svc"
        assert retrieved.name == "Test Service"

    @pytest.mark.asyncio
    async def test_get_service_by_name(self, store):
        """Test retrieving a service by name."""
        service = Service(id="test-svc", name="Test Service")
        await store.save_service(service)

        retrieved = await store.get_service_by_name("test service")  # Case insensitive
        assert retrieved is not None
        assert retrieved.id == "test-svc"

    @pytest.mark.asyncio
    async def test_update_service(self, store):
        """Test updating a service."""
        service = Service(id="test-svc", name="Test Service", tier=ServiceTier.TIER_3)
        await store.save_service(service)

        updates = ServiceUpdateRequest(tier=ServiceTier.TIER_1, team_owner="platform-team")
        updated = await store.update_service("test-svc", updates)

        assert updated is not None
        assert updated.tier == ServiceTier.TIER_1
        assert updated.team_owner == "platform-team"

    @pytest.mark.asyncio
    async def test_delete_service_removes_dependencies(self, populated_store):
        """Test that deleting a service removes its dependencies."""
        # Get initial counts
        initial_deps = await populated_store.get_all_dependencies()
        initial_count = len(initial_deps)

        # Delete payments-api (has multiple dependencies)
        deleted = await populated_store.delete_service("payments-api")
        assert deleted is True

        # Verify service is gone
        service = await populated_store.get_service("payments-api")
        assert service is None

        # Verify dependencies are removed
        remaining_deps = await populated_store.get_all_dependencies()
        assert len(remaining_deps) < initial_count

        # No dependency should reference payments-api
        for dep in remaining_deps:
            assert dep.source_service_id != "payments-api"
            assert dep.target_service_id != "payments-api"

    @pytest.mark.asyncio
    async def test_filter_services_by_tier(self, populated_store):
        """Test filtering services by tier."""
        tier_1_services = await populated_store.get_all_services(tier=ServiceTier.TIER_1)
        assert len(tier_1_services) == 3  # api-gateway, payments-api, postgres

        tier_2_services = await populated_store.get_all_services(tier=ServiceTier.TIER_2)
        assert len(tier_2_services) == 2  # user-service, redis

    @pytest.mark.asyncio
    async def test_filter_dependencies_by_type(self, populated_store):
        """Test filtering dependencies by type."""
        db_deps = await populated_store.get_all_dependencies(
            dependency_type=DependencyType.DATABASE
        )
        assert len(db_deps) == 2  # payments->postgres, user->postgres

    @pytest.mark.asyncio
    async def test_get_upstream_downstream_dependencies(self, populated_store):
        """Test getting upstream and downstream dependencies."""
        # payments-api depends on postgres, redis, notification-service
        upstream = await populated_store.get_upstream_dependencies("payments-api")
        assert len(upstream) == 3

        # postgres is depended upon by payments-api and user-service
        downstream = await populated_store.get_downstream_dependencies("postgres")
        assert len(downstream) == 2

    @pytest.mark.asyncio
    async def test_get_stats(self, populated_store):
        """Test getting catalog statistics."""
        stats = await populated_store.get_stats()

        assert stats.total_services == 6
        assert stats.total_dependencies == 6
        assert stats.services_by_tier.get("tier_1") == 3
        assert stats.avg_dependencies_per_service == 1.0


class TestDependencyGraph:
    """Tests for DependencyGraph operations."""

    @pytest.fixture
    async def graph(self):
        """Create a graph with test data."""
        store = DependencyStore()

        # Create a dependency chain:
        # frontend -> api-gateway -> payments-api -> postgres
        #                         -> user-service -> postgres
        #                                         -> redis
        services = [
            Service(id="frontend", name="Frontend", tier=ServiceTier.TIER_1),
            Service(id="api-gateway", name="API Gateway", tier=ServiceTier.TIER_1),
            Service(id="payments-api", name="Payments API", tier=ServiceTier.TIER_1),
            Service(id="user-service", name="User Service", tier=ServiceTier.TIER_2),
            Service(id="postgres", name="PostgreSQL", tier=ServiceTier.TIER_1),
            Service(id="redis", name="Redis", tier=ServiceTier.TIER_3),
        ]
        for s in services:
            await store.save_service(s)

        dependencies = [
            Dependency(id="d1", source_service_id="frontend", target_service_id="api-gateway", is_critical=True),
            Dependency(id="d2", source_service_id="api-gateway", target_service_id="payments-api", is_critical=True),
            Dependency(id="d3", source_service_id="api-gateway", target_service_id="user-service"),
            Dependency(id="d4", source_service_id="payments-api", target_service_id="postgres", is_critical=True),
            Dependency(id="d5", source_service_id="user-service", target_service_id="postgres"),
            Dependency(id="d6", source_service_id="user-service", target_service_id="redis"),
        ]
        for d in dependencies:
            await store.save_dependency(d)

        return DependencyGraph(store)

    @pytest.mark.asyncio
    async def test_blast_radius_for_database(self, graph):
        """Test blast radius calculation for a critical database."""
        result = await graph.calculate_blast_radius("postgres")

        # postgres failure affects: payments-api, user-service, api-gateway, frontend
        assert len(result.affected_services) == 4
        assert "payments-api" in result.affected_services
        assert "user-service" in result.affected_services
        assert "api-gateway" in result.affected_services
        assert "frontend" in result.affected_services

        # Check depth mapping
        assert "payments-api" in result.affected_services_by_depth[1]
        assert "user-service" in result.affected_services_by_depth[1]
        assert "api-gateway" in result.affected_services_by_depth[2]
        assert "frontend" in result.affected_services_by_depth[3]

    @pytest.mark.asyncio
    async def test_blast_radius_for_leaf_service(self, graph):
        """Test blast radius for a leaf service (no dependents)."""
        result = await graph.calculate_blast_radius("frontend")

        # frontend has no dependents
        assert len(result.affected_services) == 0

    @pytest.mark.asyncio
    async def test_blast_radius_impact_score(self, graph):
        """Test that impact score reflects tier weights."""
        result = await graph.calculate_blast_radius("postgres")

        # Should have significant impact score due to Tier 1/2 services
        assert result.total_impact_score > 0
        assert result.tier_1_affected >= 2  # payments-api, api-gateway, frontend

    @pytest.mark.asyncio
    async def test_upstream_services(self, graph):
        """Test getting upstream services."""
        upstream = await graph.get_upstream_services("frontend")

        # frontend depends on api-gateway (depth 1)
        # which depends on payments-api, user-service (depth 2)
        # which depend on postgres, redis (depth 3)
        all_upstream = [s for services in upstream.values() for s in services]
        assert "api-gateway" in all_upstream
        assert "payments-api" in all_upstream
        assert "postgres" in all_upstream

    @pytest.mark.asyncio
    async def test_downstream_services(self, graph):
        """Test getting downstream services."""
        downstream = await graph.get_downstream_services("api-gateway")

        # Services that depend on api-gateway: frontend
        all_downstream = [s for services in downstream.values() for s in services]
        assert "frontend" in all_downstream

    @pytest.mark.asyncio
    async def test_service_risk_score(self, graph):
        """Test risk score calculation."""
        risk = await graph.calculate_service_risk_score("postgres")

        assert risk["risk_score"] > 0
        assert "factors" in risk
        assert risk["tier_1_affected"] >= 2

    @pytest.mark.asyncio
    async def test_shared_dependencies(self, graph):
        """Test finding shared dependencies."""
        shared = await graph.get_shared_dependencies(["payments-api", "user-service"])

        # Both depend on postgres
        assert "postgres" in shared


class TestDependencyGraphCycles:
    """Tests for cycle detection."""

    @pytest.fixture
    async def graph_with_cycle(self):
        """Create a graph with a circular dependency."""
        store = DependencyStore()

        services = [
            Service(id="service-a", name="Service A"),
            Service(id="service-b", name="Service B"),
            Service(id="service-c", name="Service C"),
        ]
        for s in services:
            await store.save_service(s)

        # Create a cycle: A -> B -> C -> A
        dependencies = [
            Dependency(id="d1", source_service_id="service-a", target_service_id="service-b"),
            Dependency(id="d2", source_service_id="service-b", target_service_id="service-c"),
            Dependency(id="d3", source_service_id="service-c", target_service_id="service-a"),
        ]
        for d in dependencies:
            await store.save_dependency(d)

        return DependencyGraph(store)

    @pytest.mark.asyncio
    async def test_detect_cycle(self, graph_with_cycle):
        """Test that cycles are detected."""
        cycles = await graph_with_cycle.detect_cycles()

        assert len(cycles) > 0
        # The cycle should contain all three services
        cycle = cycles[0]
        cycle_services = set(cycle[:-1])  # Last element repeats first
        assert "service-a" in cycle_services or "service-b" in cycle_services


class TestDependencyDiscovery:
    """Tests for dependency auto-discovery."""

    @pytest.fixture
    def discovery(self):
        """Create a discovery instance."""
        return DependencyDiscovery()

    @pytest.mark.asyncio
    async def test_discover_from_docker_compose(self, discovery):
        """Test discovery from Docker Compose file."""
        compose_content = """
version: '3.8'
services:
  api:
    image: myapp/api:latest
    depends_on:
      - postgres
      - redis
    environment:
      - DATABASE_URL=postgres://postgres:5432/mydb
    labels:
      tier: "1"
      team: "platform"

  postgres:
    image: postgres:15
    labels:
      tier: "1"

  redis:
    image: redis:7
    labels:
      tier: "2"

  worker:
    image: myapp/worker:latest
    depends_on:
      - redis
      - postgres
"""
        result = await discovery.discover_from_docker_compose(
            compose_content, "docker-compose.yml"
        )

        # Should discover 4 services
        assert len(result.services_discovered) == 4
        service_ids = [s.id for s in result.services_discovered]
        assert "api" in service_ids
        assert "postgres" in service_ids
        assert "redis" in service_ids
        assert "worker" in service_ids

        # Should discover dependencies
        assert len(result.dependencies_discovered) >= 4
        
        # Check that api->postgres dependency exists
        deps = [(d.source_service_id, d.target_service_id) for d in result.dependencies_discovered]
        assert ("api", "postgres") in deps
        assert ("api", "redis") in deps

    @pytest.mark.asyncio
    async def test_discover_from_kubernetes(self, discovery):
        """Test discovery from Kubernetes manifests."""
        k8s_manifest = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments-api
  namespace: production
  labels:
    tier: "1"
    team: platform
spec:
  template:
    spec:
      containers:
        - name: api
          image: myapp/payments:v1
          env:
            - name: DB_HOST
              value: postgres-service
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: production
spec:
  ports:
    - port: 5432
"""
        result = await discovery.discover_from_kubernetes([k8s_manifest])

        # Should discover services
        assert len(result.services_discovered) >= 1
        service_ids = [s.id for s in result.services_discovered]
        assert "payments-api" in service_ids

    @pytest.mark.asyncio
    async def test_infer_dependency_type(self, discovery):
        """Test dependency type inference from names."""
        assert discovery._infer_dependency_type("postgres-db") == DependencyType.DATABASE
        assert discovery._infer_dependency_type("redis-cache") == DependencyType.CACHE
        assert discovery._infer_dependency_type("kafka-broker") == DependencyType.QUEUE
        assert discovery._infer_dependency_type("user-service") == DependencyType.API

    @pytest.mark.asyncio
    async def test_normalize_service_name(self, discovery):
        """Test service name normalization."""
        assert discovery._normalize_service_name("PaymentsService") == "payments"
        assert discovery._normalize_service_name("user_api_service") == "user-api"
        assert discovery._normalize_service_name("my-service-api") == "my-service"


class TestDependencyVisualizer:
    """Tests for visualization generation."""

    @pytest.fixture
    async def visualizer(self):
        """Create a visualizer with test data."""
        store = DependencyStore()

        services = [
            Service(id="api", name="API", tier=ServiceTier.TIER_1, team_owner="platform"),
            Service(id="postgres", name="PostgreSQL", tier=ServiceTier.TIER_1),
            Service(id="redis", name="Redis", tier=ServiceTier.TIER_2),
        ]
        for s in services:
            await store.save_service(s)

        dependencies = [
            Dependency(id="d1", source_service_id="api", target_service_id="postgres", dependency_type=DependencyType.DATABASE, is_critical=True),
            Dependency(id="d2", source_service_id="api", target_service_id="redis", dependency_type=DependencyType.CACHE),
        ]
        for d in dependencies:
            await store.save_dependency(d)

        return DependencyVisualizer(store)

    @pytest.mark.asyncio
    async def test_generate_full_graph(self, visualizer):
        """Test generating full graph visualization."""
        graph = await visualizer.generate_full_graph()

        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

        # Check node properties
        api_node = next(n for n in graph.nodes if n.id == "api")
        assert api_node.label == "API"
        assert api_node.tier == "tier_1"

    @pytest.mark.asyncio
    async def test_generate_service_subgraph(self, visualizer):
        """Test generating subgraph for a service."""
        graph = await visualizer.generate_service_subgraph("api", depth=1)

        # Should include api and its direct dependencies
        assert len(graph.nodes) >= 1
        node_ids = [n.id for n in graph.nodes]
        assert "api" in node_ids

    @pytest.mark.asyncio
    async def test_generate_mermaid_diagram(self, visualizer):
        """Test Mermaid diagram generation."""
        diagram = await visualizer.generate_mermaid_diagram()

        assert "graph TD" in diagram
        assert "api" in diagram
        assert "postgres" in diagram
        assert "-->" in diagram  # Has edges

    @pytest.mark.asyncio
    async def test_generate_d3_data(self, visualizer):
        """Test D3.js data generation."""
        data = await visualizer.generate_d3_data()

        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) == 3
        assert len(data["links"]) == 2

        # Check D3 node format
        node = data["nodes"][0]
        assert "id" in node
        assert "name" in node
        assert "group" in node

    @pytest.mark.asyncio
    async def test_generate_cytoscape_data(self, visualizer):
        """Test Cytoscape.js data generation."""
        data = await visualizer.generate_cytoscape_data()

        assert "elements" in data
        # Should have 3 nodes + 2 edges = 5 elements
        assert len(data["elements"]) == 5

    @pytest.mark.asyncio
    async def test_node_type_inference(self, visualizer):
        """Test that node types are correctly inferred."""
        graph = await visualizer.generate_full_graph()

        postgres_node = next(n for n in graph.nodes if n.id == "postgres")
        assert postgres_node.type == NodeType.DATABASE

        redis_node = next(n for n in graph.nodes if n.id == "redis")
        # Redis is typically classified as cache
        assert redis_node.type in [NodeType.CACHE, NodeType.DATABASE]

    @pytest.mark.asyncio
    async def test_blast_radius_highlighting(self, visualizer):
        """Test that blast radius highlighting works."""
        # postgres failure affects api
        graph = await visualizer.generate_full_graph(highlight_service="postgres")

        # Check that affected services are marked
        api_node = next(n for n in graph.nodes if n.id == "api")
        assert api_node.metadata.get("highlighted") is True


class TestStorePeristence:
    """Tests for store persistence functionality."""

    @pytest.fixture
    def temp_path(self, tmp_path):
        """Create a temporary file path."""
        return tmp_path / "test_catalog.json"

    @pytest.mark.asyncio
    async def test_save_and_load(self, temp_path):
        """Test saving and loading from file."""
        # Create and populate store
        store1 = DependencyStore(persistence_path=temp_path, auto_save=True)
        await store1.save_service(Service(id="svc1", name="Service 1"))
        await store1.save_service(Service(id="svc2", name="Service 2"))
        await store1.save_dependency(
            Dependency(id="dep1", source_service_id="svc1", target_service_id="svc2")
        )

        # Create new store and load
        store2 = DependencyStore(persistence_path=temp_path)
        loaded = await store2.load()

        assert loaded is True
        assert await store2.get_service("svc1") is not None
        assert await store2.get_service("svc2") is not None
        assert await store2.get_dependency("dep1") is not None

    @pytest.mark.asyncio
    async def test_export_import(self, temp_path):
        """Test export and import functionality."""
        store1 = DependencyStore()
        await store1.save_service(Service(id="svc1", name="Service 1", tier=ServiceTier.TIER_1))
        await store1.save_dependency(
            Dependency(id="dep1", source_service_id="svc1", target_service_id="svc1")
        )

        # Export
        exported = await store1.export_json()
        assert "services" in exported
        assert "dependencies" in exported
        assert len(exported["services"]) == 1

        # Import into new store
        store2 = DependencyStore()
        services, deps = await store2.import_json(exported)

        assert services == 1
        assert deps == 1

    @pytest.mark.asyncio
    async def test_import_merge(self):
        """Test merge import mode."""
        store = DependencyStore()
        await store.save_service(Service(id="existing", name="Existing Service"))

        new_data = {
            "services": [{"id": "new", "name": "New Service"}],
            "dependencies": [],
        }

        services, deps = await store.import_json(new_data, merge=True)

        # Should have both services
        assert await store.get_service("existing") is not None
        assert await store.get_service("new") is not None
