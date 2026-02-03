"""Tests for Loki integration adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.integrations.loki import LokiAdapter


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        loki_url="http://loki:3100",
        loki_auth_type="none",
    )


@pytest.fixture
def adapter(settings):
    """Create LokiAdapter instance."""
    return LokiAdapter(settings)


class TestLokiAdapterInit:
    """Test LokiAdapter initialization."""

    def test_init_basic(self, adapter):
        """Test basic initialization."""
        assert adapter.base_url == "http://loki:3100"
        assert adapter.auth_type == "none"
        assert adapter.org_id == ""


class TestLokiAdapterAuth:
    """Test authentication header generation."""

    def test_no_auth_headers(self, adapter):
        """Test headers with no auth."""
        headers = adapter._get_auth_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_basic_auth_headers(self):
        """Test headers with basic auth."""
        settings = Settings(
            loki_url="https://logs-prod.grafana.net",
            loki_auth_type="basic",
            loki_username="12345",
            loki_password="glc_secret_key",
        )
        adapter = LokiAdapter(settings)
        headers = adapter._get_auth_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_bearer_auth_headers(self):
        """Test headers with bearer token."""
        settings = Settings(
            loki_url="http://loki:3100",
            loki_auth_type="bearer",
            loki_token="my-bearer-token",
            loki_org_id="tenant-1",
        )
        adapter = LokiAdapter(settings)
        headers = adapter._get_auth_headers()
        assert headers["Authorization"] == "Bearer my-bearer-token"
        assert headers["X-Scope-OrgID"] == "tenant-1"


class TestLokiAdapterLogLevel:
    """Test log level inference."""

    def test_infer_critical(self, adapter):
        """Test critical level detection."""
        assert adapter._infer_log_level("CRITICAL: system failure") == "critical"
        assert adapter._infer_log_level("fatal error occurred") == "critical"

    def test_infer_error(self, adapter):
        """Test error level detection."""
        assert adapter._infer_log_level("ERROR: connection failed") == "error"
        assert adapter._infer_log_level("Exception in thread") == "error"

    def test_infer_warn(self, adapter):
        """Test warning level detection."""
        assert adapter._infer_log_level("WARNING: high memory usage") == "warn"

    def test_infer_unknown(self, adapter):
        """Test unknown level fallback."""
        assert adapter._infer_log_level("some random message") == "unknown"


class TestLokiAdapterGetContext:
    """Test the main get_context method."""

    @pytest.mark.asyncio
    async def test_get_context_no_url(self):
        """Test get_context returns None when URL not configured."""
        settings = Settings(loki_url="")
        adapter = LokiAdapter(settings)
        result = await adapter.get_context("my-service")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_context_success(self, adapter):
        """Test successful context retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "result": [
                    {
                        "stream": {"service": "my-service"},
                        "values": [
                            ["1704067200000000000", "ERROR: test error"],
                        ],
                    }
                ]
            }
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance

            result = await adapter.get_context("my-service")

            assert result is not None
            assert result.service == "my-service"
            assert len(result.logs) == 1
            assert result.logs[0].level == "error"


class TestLokiAdapterHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_no_url(self):
        """Test health check when URL not configured."""
        settings = Settings(loki_url="")
        adapter = LokiAdapter(settings)
        result = await adapter.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter):
        """Test successful health check."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()
            mock_client.return_value = mock_instance

            result = await adapter.health_check()
            assert result is True
