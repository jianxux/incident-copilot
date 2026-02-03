"""Tests for ServiceNow integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.integrations.servicenow import (
    IncidentImpact,
    IncidentState,
    IncidentUrgency,
    ServiceNowAdapter,
)


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        servicenow_instance="https://instance.service-now.com",
        servicenow_username="admin",
        servicenow_password="password",
        servicenow_assignment_group="Incident Management",
        servicenow_caller_id="system",
    )


@pytest.fixture
def adapter(settings):
    """Create ServiceNow adapter."""
    return ServiceNowAdapter(settings)


class TestServiceNowAdapter:
    """Tests for ServiceNowAdapter."""

    def test_api_url(self, adapter):
        """Test API URL construction."""
        assert adapter.api_url == "https://instance.service-now.com/api/now"

    def test_get_headers_with_basic_auth(self, adapter):
        """Test headers with basic auth."""
        headers = adapter._get_headers()
        assert headers["Authorization"].startswith("Basic ")
        assert headers["Accept"] == "application/json"

    def test_get_headers_with_api_key(self):
        """Test headers with API key."""
        settings = Settings(
            servicenow_instance="https://instance.service-now.com",
            servicenow_api_key="test-api-key",
        )
        adapter = ServiceNowAdapter(settings)
        headers = adapter._get_headers()
        assert headers["Authorization"] == "Bearer test-api-key"

    def test_severity_to_impact(self, adapter):
        """Test severity to impact mapping."""
        assert adapter._severity_to_impact("critical") == IncidentImpact.HIGH
        assert adapter._severity_to_impact("high") == IncidentImpact.HIGH
        assert adapter._severity_to_impact("warning") == IncidentImpact.MEDIUM
        assert adapter._severity_to_impact("low") == IncidentImpact.LOW
        assert adapter._severity_to_impact("unknown") == IncidentImpact.MEDIUM

    def test_severity_to_urgency(self, adapter):
        """Test severity to urgency mapping."""
        assert adapter._severity_to_urgency("critical") == IncidentUrgency.HIGH
        assert adapter._severity_to_urgency("medium") == IncidentUrgency.MEDIUM
        assert adapter._severity_to_urgency("info") == IncidentUrgency.LOW


class TestCreateIncident:
    """Tests for incident creation."""

    @pytest.mark.asyncio
    async def test_create_incident_success(self, adapter):
        """Test successful incident creation."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.json.return_value = {
                "result": {
                    "sys_id": "abc123",
                    "number": "INC0001234",
                    "short_description": "Test incident",
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response

            incident = await adapter.create_incident(
                short_description="Payment processing failed",
                description="Users unable to complete payments",
                severity="high",
                service_name="payments-api",
                alert_id="PD-12345",
            )

        assert incident["sys_id"] == "abc123"
        assert incident["number"] == "INC0001234"

    @pytest.mark.asyncio
    async def test_create_incident_with_context(self, adapter):
        """Test incident creation with AI context summary."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {"result": {"sys_id": "abc123"}}
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response

            await adapter.create_incident(
                short_description="Test",
                description="Test description",
                context_summary="AI analysis shows database timeout",
            )

            # Verify description includes context
            call_args = mock_client.post.call_args
            json_data = call_args.kwargs.get("json", {})
            assert "AI Context Summary" in json_data.get("description", "")

    @pytest.mark.asyncio
    async def test_create_incident_unconfigured(self):
        """Test incident creation when not configured."""
        settings = Settings(servicenow_instance="")
        adapter = ServiceNowAdapter(settings)

        incident = await adapter.create_incident(
            short_description="Test",
            description="Test",
        )
        assert incident == {}


class TestUpdateIncident:
    """Tests for incident updates."""

    @pytest.mark.asyncio
    async def test_update_incident_success(self, adapter):
        """Test successful incident update."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "result": {
                    "sys_id": "abc123",
                    "state": "2",
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.patch.return_value = mock_response

            incident = await adapter.update_incident(
                sys_id="abc123",
                updates={"state": IncidentState.IN_PROGRESS.value},
            )

        assert incident["sys_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_resolve_incident(self, adapter):
        """Test resolving an incident."""
        with patch.object(
            adapter, "update_incident", new_callable=AsyncMock
        ) as mock_update:
            mock_update.return_value = {"sys_id": "abc123", "state": "6"}

            _ = await adapter.resolve_incident(
                sys_id="abc123",
                resolution_code="Solved (Permanently)",
                resolution_notes="Fixed database connection pool",
            )

        # Verify update was called with correct state
        call_args = mock_update.call_args
        updates = (
            call_args.args[1]
            if len(call_args.args) > 1
            else call_args.kwargs.get("updates", {})
        )
        assert updates.get("state") == IncidentState.RESOLVED.value

    @pytest.mark.asyncio
    async def test_add_work_note(self, adapter):
        """Test adding a work note."""
        with patch.object(
            adapter, "update_incident", new_callable=AsyncMock
        ) as mock_update:
            mock_update.return_value = {"sys_id": "abc123"}

            await adapter.add_work_note("abc123", "Investigation in progress")

        call_args = mock_update.call_args
        updates = (
            call_args.args[1]
            if len(call_args.args) > 1
            else call_args.kwargs.get("updates", {})
        )
        assert updates.get("work_notes") == "Investigation in progress"


class TestSearchIncidents:
    """Tests for incident search."""

    @pytest.mark.asyncio
    async def test_search_incidents_success(self, adapter):
        """Test successful incident search."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "result": [
                    {"sys_id": "1", "number": "INC001"},
                    {"sys_id": "2", "number": "INC002"},
                ]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            incidents = await adapter.search_incidents(
                query="payment",
                state=IncidentState.NEW,
                limit=10,
            )

        assert len(incidents) == 2
        assert incidents[0]["number"] == "INC001"

    @pytest.mark.asyncio
    async def test_search_incidents_unconfigured(self):
        """Test search when not configured."""
        settings = Settings(servicenow_instance="")
        adapter = ServiceNowAdapter(settings)

        incidents = await adapter.search_incidents(query="test")
        assert incidents == []

    @pytest.mark.asyncio
    async def test_get_similar_incidents(self, adapter):
        """Test finding similar incidents."""
        with patch.object(
            adapter, "search_incidents", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = [
                {"sys_id": "1", "short_description": "Payment failure"}
            ]

            similar = await adapter.get_similar_incidents(
                short_description="Payment processing failed for user",
                service_name="payments-api",
            )

        assert len(similar) == 1


class TestGetIncident:
    """Tests for getting incidents."""

    @pytest.mark.asyncio
    async def test_get_incident_success(self, adapter):
        """Test getting an incident."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "result": {"sys_id": "abc123", "number": "INC001"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            incident = await adapter.get_incident("abc123")

        assert incident["sys_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_incident_not_found(self, adapter):
        """Test getting a non-existent incident."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            import httpx

            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "Not found", request=MagicMock(), response=mock_response
            )

            incident = await adapter.get_incident("nonexistent")

        assert incident == {}


class TestCMDB:
    """Tests for CMDB operations."""

    @pytest.mark.asyncio
    async def test_get_cmdb_ci_success(self, adapter):
        """Test looking up a configuration item."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "result": [{"sys_id": "ci123", "name": "payments-api"}]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            ci = await adapter.get_cmdb_ci("payments-api")

        assert ci["sys_id"] == "ci123"
        assert ci["name"] == "payments-api"

    @pytest.mark.asyncio
    async def test_get_cmdb_ci_not_found(self, adapter):
        """Test looking up a non-existent CI."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {"result": []}
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            ci = await adapter.get_cmdb_ci("nonexistent")

        assert ci is None


class TestChangeRequest:
    """Tests for change request operations."""

    @pytest.mark.asyncio
    async def test_create_change_request(self, adapter):
        """Test creating a change request."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "result": {"sys_id": "chg123", "number": "CHG001"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.post.return_value = mock_response

            change = await adapter.create_change_request(
                short_description="Deploy payments-api v2.1",
                description="Production deployment of new payment features",
                service_name="payments-api",
                change_type="Normal",
            )

        assert change["sys_id"] == "chg123"
        assert change["number"] == "CHG001"

    @pytest.mark.asyncio
    async def test_get_recent_changes(self, adapter):
        """Test getting recent changes."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "result": [
                    {"sys_id": "1", "number": "CHG001"},
                    {"sys_id": "2", "number": "CHG002"},
                ]
            }
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            changes = await adapter.get_recent_changes(
                service_name="payments-api",
                hours_back=24,
            )

        assert len(changes) == 2


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
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            health = await adapter.get_health()

        assert health["status"] == "healthy"
        assert "instance.service-now.com" in health["instance"]

    @pytest.mark.asyncio
    async def test_health_unconfigured(self):
        """Test health when not configured."""
        settings = Settings(servicenow_instance="")
        adapter = ServiceNowAdapter(settings)

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


class TestAlertLinking:
    """Tests for alert linking."""

    @pytest.mark.asyncio
    async def test_link_incident_to_alert(self, adapter):
        """Test linking an incident to an external alert."""
        with patch.object(
            adapter, "add_work_note", new_callable=AsyncMock
        ) as mock_note:
            mock_note.return_value = {"sys_id": "abc123"}

            result = await adapter.link_incident_to_alert(
                incident_sys_id="abc123",
                alert_id="PD-12345",
                alert_source="PagerDuty",
                alert_url="https://pagerduty.com/incidents/12345",
            )

        assert result is True
        call_args = mock_note.call_args
        note = (
            call_args.args[1]
            if len(call_args.args) > 1
            else call_args.kwargs.get("note", "")
        )
        assert "PagerDuty" in note
        assert "PD-12345" in note
        assert "https://pagerduty.com" in note
