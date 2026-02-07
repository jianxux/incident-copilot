"""Tests for Splunk integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.integrations.splunk import SplunkAdapter


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        splunk_url="https://splunk.example.com:8089",
        splunk_token="test-token",
        splunk_index_map={
            "payments-api": "payments",
            "auth-service": "security",
        },
    )


@pytest.fixture
def adapter(settings):
    """Create Splunk adapter."""
    return SplunkAdapter(settings)


class TestSplunkAdapter:
    """Tests for SplunkAdapter."""

    def test_get_headers_with_token(self, adapter):
        """Test headers with token auth."""
        headers = adapter._get_headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Accept"] == "application/json"

    def test_get_headers_with_basic_auth(self):
        """Test headers with basic auth."""
        settings = Settings(
            splunk_url="https://splunk.example.com:8089",
            splunk_username="admin",
            splunk_password="password123",
        )
        adapter = SplunkAdapter(settings)
        headers = adapter._get_headers()

        # Should use Basic auth
        assert headers["Authorization"].startswith("Basic ")

    def test_get_index_for_service_direct_match(self, adapter):
        """Test index mapping with direct match."""
        index = adapter._get_index_for_service("payments-api")
        assert index == "payments"

    def test_get_index_for_service_normalized(self, adapter):
        """Test index mapping with normalized name."""
        index = adapter._get_index_for_service("payments_api")
        assert index == "payments"

    def test_get_index_for_service_not_found(self, adapter):
        """Test index mapping when not found."""
        index = adapter._get_index_for_service("unknown-service")
        assert index is None


class TestFetchLogs:
    """Tests for log fetching."""

    @pytest.mark.asyncio
    async def test_fetch_logs_success(self, adapter):
        """Test successful log fetch."""
        mock_results = [
            {
                "_time": "2026-02-02T04:00:00.000+00:00",
                "_raw": "ERROR: Payment processing failed",
                "level": "ERROR",
                "host": "payments-1",
                "source": "/var/log/payments.log",
                "sourcetype": "json",
            },
            {
                "_time": "2026-02-02T03:59:00.000+00:00",
                "_raw": "Connection timeout to database",
                "level": "ERROR",
                "host": "payments-2",
                "source": "/var/log/payments.log",
                "sourcetype": "json",
            },
        ]

        with patch.object(
            adapter, "_create_search_job", new_callable=AsyncMock
        ) as mock_create:
            with patch.object(
                adapter, "_wait_for_job", new_callable=AsyncMock
            ) as mock_wait:
                with patch.object(
                    adapter, "_get_job_results", new_callable=AsyncMock
                ) as mock_results_fn:
                    mock_create.return_value = "test-sid-123"
                    mock_wait.return_value = True
                    mock_results_fn.return_value = mock_results

                    entries = await adapter.fetch_logs(
                        service_name="payments-api",
                        minutes_back=60,
                        max_results=100,
                    )

        assert len(entries) == 2
        assert entries[0].level == "ERROR"
        assert "Payment processing failed" in entries[0].message
        assert entries[0].service == "payments-api"

    @pytest.mark.asyncio
    async def test_fetch_logs_unconfigured(self):
        """Test fetch when Splunk is not configured."""
        settings = Settings(splunk_url="")
        adapter = SplunkAdapter(settings)

        entries = await adapter.fetch_logs("payments-api")
        assert entries == []

    @pytest.mark.asyncio
    async def test_fetch_logs_job_timeout(self, adapter):
        """Test when search job times out."""
        with patch.object(
            adapter, "_create_search_job", new_callable=AsyncMock
        ) as mock_create:
            with patch.object(
                adapter, "_wait_for_job", new_callable=AsyncMock
            ) as mock_wait:
                mock_create.return_value = "test-sid-123"
                mock_wait.return_value = False  # Timeout

                entries = await adapter.fetch_logs("payments-api")

        assert entries == []

    @pytest.mark.asyncio
    async def test_fetch_logs_with_severity_filter(self, adapter):
        """Test log fetch with severity filter."""
        with patch.object(
            adapter, "_create_search_job", new_callable=AsyncMock
        ) as mock_create:
            with patch.object(
                adapter, "_wait_for_job", new_callable=AsyncMock
            ) as mock_wait:
                with patch.object(
                    adapter, "_get_job_results", new_callable=AsyncMock
                ) as mock_results:
                    mock_create.return_value = "test-sid"
                    mock_wait.return_value = True
                    mock_results.return_value = []

                    await adapter.fetch_logs(
                        service_name="payments-api",
                        severity="ERROR",
                    )

                    # Verify the query includes error severity
                    call_args = mock_create.call_args
                    query = call_args.kwargs.get(
                        "search_query", call_args.args[0] if call_args.args else ""
                    )
                    assert "ERROR" in query or "error" in query


class TestTimestampParsing:
    """Tests for timestamp parsing."""

    def test_parse_iso_with_microseconds(self, adapter):
        """Test parsing ISO format with microseconds."""
        result = adapter._parse_timestamp("2026-02-02T04:00:00.123456+0000")
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 2

    def test_parse_iso_without_microseconds(self, adapter):
        """Test parsing ISO format without microseconds."""
        result = adapter._parse_timestamp("2026-02-02T04:00:00+0000")
        assert result is not None

    def test_parse_epoch(self, adapter):
        """Test parsing epoch timestamp."""
        result = adapter._parse_timestamp("1738476000.0")
        assert result is not None

    def test_parse_invalid(self, adapter):
        """Test parsing invalid timestamp."""
        result = adapter._parse_timestamp("not-a-timestamp")
        assert result is None

    def test_parse_empty(self, adapter):
        """Test parsing empty string."""
        result = adapter._parse_timestamp("")
        assert result is None


class TestSavedSearch:
    """Tests for saved search functionality."""

    @pytest.mark.asyncio
    async def test_run_saved_search_success(self, adapter):
        """Test running a saved search."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock dispatch response
            mock_dispatch_response = MagicMock()
            mock_dispatch_response.status_code = 200
            mock_dispatch_response.json.return_value = {"sid": "saved-search-sid"}
            mock_dispatch_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_dispatch_response

            with patch.object(
                adapter, "_wait_for_job", new_callable=AsyncMock
            ) as mock_wait:
                with patch.object(
                    adapter, "_get_job_results", new_callable=AsyncMock
                ) as mock_results:
                    mock_wait.return_value = True
                    mock_results.return_value = [{"result": "data"}]

                    results = await adapter.run_saved_search("my_saved_search")

        assert len(results) == 1
        assert results[0]["result"] == "data"

    @pytest.mark.asyncio
    async def test_run_saved_search_unconfigured(self):
        """Test saved search when not configured."""
        settings = Settings(splunk_url="")
        adapter = SplunkAdapter(settings)

        results = await adapter.run_saved_search("my_saved_search")
        assert results == []


class TestHealth:
    """Tests for health check."""

    @pytest.mark.asyncio
    async def test_health_success(self, adapter):
        """Test successful health check."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "entry": [
                    {
                        "content": {
                            "version": "9.0.0",
                            "serverName": "splunk-prod",
                            "os_name": "Linux",
                        }
                    }
                ]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            health = await adapter.get_health()

        assert health["status"] == "healthy"
        assert health["version"] == "9.0.0"
        assert health["server_name"] == "splunk-prod"

    @pytest.mark.asyncio
    async def test_health_unconfigured(self):
        """Test health when not configured."""
        settings = Settings(splunk_url="")
        adapter = SplunkAdapter(settings)

        health = await adapter.get_health()
        assert health["status"] == "unconfigured"

    @pytest.mark.asyncio
    async def test_health_connection_error(self, adapter):
        """Test health when connection fails."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.side_effect = Exception("Connection refused")

            health = await adapter.get_health()

        assert health["status"] == "unhealthy"
        assert "Connection refused" in health["error"]


class TestAlertSearch:
    """Tests for alert searching."""

    @pytest.mark.asyncio
    async def test_search_alerts_success(self, adapter):
        """Test searching for triggered alerts."""
        with patch.object(
            adapter, "_create_search_job", new_callable=AsyncMock
        ) as mock_create:
            with patch.object(
                adapter, "_wait_for_job", new_callable=AsyncMock
            ) as mock_wait:
                with patch.object(
                    adapter, "_get_job_results", new_callable=AsyncMock
                ) as mock_results:
                    mock_create.return_value = "alert-search-sid"
                    mock_wait.return_value = True
                    mock_results.return_value = [
                        {
                            "ss_name": "payments-api-error-rate",
                            "trigger_time": "1738476000",
                        },
                    ]

                    alerts = await adapter.search_alerts("payments-api")

        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_search_alerts_unconfigured(self):
        """Test alert search when not configured."""
        settings = Settings(splunk_url="")
        adapter = SplunkAdapter(settings)

        alerts = await adapter.search_alerts("payments-api")
        assert alerts == []
