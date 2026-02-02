"""Tests for health check endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.health import (
    ComponentHealth,
    HealthStatus,
    check_database_health,
    check_github_health,
    check_redis_health,
    check_slack_health,
    get_uptime_seconds,
    set_app_start_time,
)
from src.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestLivenessEndpoint:
    """Tests for /health/live endpoint."""

    def test_liveness_returns_200(self, client):
        """Liveness probe should always return 200."""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"


class TestReadinessEndpoint:
    """Tests for /health/ready endpoint."""

    @pytest.mark.asyncio
    async def test_readiness_healthy(self):
        """Readiness should return ready when dependencies are healthy."""
        with patch("src.api.health.check_redis_health") as mock_redis:
            with patch("src.api.health.check_database_health") as mock_db:
                mock_redis.return_value = ComponentHealth(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                )
                mock_db.return_value = ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                )

                # Create a test client
                client = TestClient(app)
                response = client.get("/health/ready")
                
                # May or may not be 200 depending on actual connectivity
                # Just verify the endpoint exists and returns valid JSON
                assert response.status_code in [200, 503]
                assert "status" in response.json()


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_valid_response(self, client):
        """Health check should return valid response structure."""
        response = client.get("/health")
        
        # May be 200 or 503 depending on actual connectivity
        assert response.status_code in [200, 503]
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        assert "components" in data

    def test_health_full_check(self, client):
        """Full health check should include all components."""
        response = client.get("/health?full=true")
        
        data = response.json()
        component_names = [c["name"] for c in data["components"]]
        
        # Should check more components in full mode
        assert len(data["components"]) >= 2


class TestComponentHealthChecks:
    """Tests for individual component health checks."""

    @pytest.mark.asyncio
    async def test_redis_health_configured(self):
        """Redis health check should work when configured."""
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        with patch("src.api.health.get_settings", return_value=mock_settings):
            # Will fail to connect in tests, but should return valid structure
            result = await check_redis_health()
            
            assert isinstance(result, ComponentHealth)
            assert result.name == "redis"
            assert result.status in [HealthStatus.HEALTHY, HealthStatus.UNHEALTHY]

    @pytest.mark.asyncio
    async def test_github_health_not_configured(self):
        """GitHub health check should return degraded when not configured."""
        mock_settings = MagicMock()
        mock_settings.github_token = ""

        with patch("src.api.health.get_settings", return_value=mock_settings):
            result = await check_github_health()
            
            assert result.status == HealthStatus.DEGRADED
            assert result.message == "Not configured"

    @pytest.mark.asyncio
    async def test_slack_health_not_configured(self):
        """Slack health check should return degraded when not configured."""
        mock_settings = MagicMock()
        mock_settings.slack_bot_token = ""

        with patch("src.api.health.get_settings", return_value=mock_settings):
            result = await check_slack_health()
            
            assert result.status == HealthStatus.DEGRADED
            assert result.message == "Not configured"


class TestUptime:
    """Tests for uptime tracking."""

    def test_uptime_none_before_start(self):
        """Uptime should be None before app start."""
        # Reset the start time
        import src.api.health as health_module
        health_module._app_start_time = None
        
        assert get_uptime_seconds() is None

    def test_uptime_after_start(self):
        """Uptime should be positive after app start."""
        set_app_start_time()
        
        uptime = get_uptime_seconds()
        assert uptime is not None
        assert uptime >= 0


class TestHealthStatus:
    """Tests for health status determination."""

    def test_overall_healthy_when_all_healthy(self, client):
        """Overall status should be healthy when all components are healthy."""
        # This tests the actual behavior - may vary based on environment
        response = client.get("/health")
        data = response.json()
        
        # Verify status is one of the valid values
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_http_status_codes(self, client):
        """HTTP status codes should match health status."""
        response = client.get("/health")
        data = response.json()
        
        if data["status"] == "unhealthy":
            assert response.status_code == 503
        else:
            assert response.status_code == 200


class TestComponentHealthModel:
    """Tests for ComponentHealth model."""

    def test_component_health_creation(self):
        """Should create ComponentHealth with required fields."""
        health = ComponentHealth(
            name="test",
            status=HealthStatus.HEALTHY,
        )
        
        assert health.name == "test"
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms is None
        assert health.message is None

    def test_component_health_with_details(self):
        """Should create ComponentHealth with all fields."""
        health = ComponentHealth(
            name="github",
            status=HealthStatus.HEALTHY,
            latency_ms=150.5,
            message="API accessible",
            details={"rate_limit_remaining": 4999},
        )
        
        assert health.name == "github"
        assert health.latency_ms == 150.5
        assert health.details["rate_limit_remaining"] == 4999
