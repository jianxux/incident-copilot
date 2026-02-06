"""Tests for Status Page integration."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.statuspage.automation import (
    AutomationConfig,
    StatusPageAutomation,
    auto_create_status_incident,
)
from src.statuspage.client import StatuspageClient
from src.statuspage.models import (
    ComponentImpact,
    ComponentMapping,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
    StatusComponent,
    StatusIncident,
    StatusPage,
    StatusUpdate,
    UptimeMetrics,
)
from src.statuspage.sync import InternalIncident, StatusPageSync, SyncResult
from src.statuspage.templates import (
    StatusUpdateTemplates,
    TemplateCategory,
    UpdateTemplate,
)


# ==================== Model Tests ====================


class TestModels:
    """Tests for status page models."""

    def test_component_status_values(self):
        """Component status should have expected values."""
        assert ComponentStatus.OPERATIONAL == "operational"
        assert ComponentStatus.DEGRADED_PERFORMANCE == "degraded_performance"
        assert ComponentStatus.PARTIAL_OUTAGE == "partial_outage"
        assert ComponentStatus.MAJOR_OUTAGE == "major_outage"

    def test_incident_status_values(self):
        """Incident status should have expected values."""
        assert IncidentStatus.INVESTIGATING == "investigating"
        assert IncidentStatus.IDENTIFIED == "identified"
        assert IncidentStatus.MONITORING == "monitoring"
        assert IncidentStatus.RESOLVED == "resolved"

    def test_component_impact_values(self):
        """Component impact should have expected values."""
        assert ComponentImpact.NONE == "none"
        assert ComponentImpact.MINOR == "minor"
        assert ComponentImpact.MAJOR == "major"
        assert ComponentImpact.CRITICAL == "critical"

    def test_status_component_model(self):
        """StatusComponent should serialize correctly."""
        component = StatusComponent(
            id="comp_123",
            page_id="page_456",
            name="API Service",
            description="Main API",
            status=ComponentStatus.OPERATIONAL,
            internal_service="api-service",
        )

        assert component.id == "comp_123"
        assert component.name == "API Service"
        assert component.status == "operational"
        assert component.internal_service == "api-service"

    def test_status_incident_model(self):
        """StatusIncident should serialize correctly."""
        incident = StatusIncident(
            id="inc_789",
            page_id="page_456",
            name="API Degradation",
            status=IncidentStatus.INVESTIGATING,
            impact=IncidentImpact.MAJOR,
            component_ids=["comp_123"],
            internal_incident_id="int_001",
            auto_created=True,
        )

        assert incident.id == "inc_789"
        assert incident.status == "investigating"
        assert incident.impact == "major"
        assert incident.auto_created is True

    def test_status_update_model(self):
        """StatusUpdate should serialize correctly."""
        update = StatusUpdate(
            id="upd_001",
            incident_id="inc_789",
            status=IncidentStatus.IDENTIFIED,
            body="We have identified the issue.",
            auto_generated=True,
        )

        assert update.status == "identified"
        assert update.auto_generated is True

    def test_component_mapping_model(self):
        """ComponentMapping should have correct defaults."""
        mapping = ComponentMapping(
            internal_service="payments-api",
            component_id="comp_123",
            page_id="page_456",
        )

        assert mapping.severity_threshold == "high"
        assert mapping.auto_update is True
        assert ComponentImpact.CRITICAL in mapping.impact_mapping.values()

    def test_uptime_metrics_model(self):
        """UptimeMetrics should validate correctly."""
        now = datetime.utcnow()
        metrics = UptimeMetrics(
            component_id="comp_123",
            component_name="API",
            uptime_percentage=99.95,
            downtime_minutes=21.6,
            total_incidents=2,
            avg_resolution_minutes=10.8,
            period_start=now - timedelta(days=30),
            period_end=now,
        )

        assert metrics.uptime_percentage == 99.95
        assert metrics.total_incidents == 2


# ==================== Client Tests ====================


@pytest.fixture
def mock_settings():
    """Create mock settings with Statuspage config."""
    settings = MagicMock()
    settings.statuspage_api_key = "test-api-key"
    settings.statuspage_default_page_id = "page_123"
    return settings


@pytest.fixture
def statuspage_client(mock_settings):
    """Create a Statuspage client with mocked settings."""
    with patch("src.statuspage.client.get_settings", return_value=mock_settings):
        client = StatuspageClient(
            api_key="test-api-key",
            page_id="page_123",
        )
        yield client


class TestStatuspageClient:
    """Tests for StatuspageClient class."""

    def test_is_configured_true(self, statuspage_client):
        """Client should be configured when API key is present."""
        assert statuspage_client.is_configured is True

    def test_is_configured_false(self):
        """Client should not be configured without API key."""
        client = StatuspageClient(api_key="")
        assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_list_pages_success(self, statuspage_client):
        """Should list pages successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "page_123",
                "name": "Public Status",
                "subdomain": "status",
                "url": "https://status.example.com",
            }
        ]
        mock_response.raise_for_status = MagicMock()

        with patch.object(statuspage_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            pages = await statuspage_client.list_pages()

            assert len(pages) == 1
            assert pages[0].id == "page_123"
            assert pages[0].name == "Public Status"

    @pytest.mark.asyncio
    async def test_list_components_success(self, statuspage_client):
        """Should list components successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "comp_1",
                "name": "API",
                "status": "operational",
                "description": "Main API",
                "position": 1,
            },
            {
                "id": "comp_2",
                "name": "Website",
                "status": "degraded_performance",
                "description": "Marketing site",
                "position": 2,
            },
        ]
        mock_response.raise_for_status = MagicMock()

        with patch.object(statuspage_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            components = await statuspage_client.list_components()

            assert len(components) == 2
            assert components[0].name == "API"
            assert components[0].status == "operational"
            assert components[1].status == "degraded_performance"

    @pytest.mark.asyncio
    async def test_update_component_status(self, statuspage_client):
        """Should update component status."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "comp_1",
            "name": "API",
            "status": "partial_outage",
            "position": 1,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(statuspage_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.patch.return_value = mock_response
            mock_get_client.return_value = mock_client

            component = await statuspage_client.update_component_status(
                "comp_1", ComponentStatus.PARTIAL_OUTAGE
            )

            assert component.status == "partial_outage"
            mock_client.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_incident(self, statuspage_client):
        """Should create incident successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "inc_1",
            "name": "API Issues",
            "status": "investigating",
            "impact": "major",
            "shortlink": "https://stspg.io/abc123",
            "created_at": "2024-01-15T10:00:00Z",
            "components": [{"id": "comp_1", "status": "partial_outage"}],
            "incident_updates": [],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(statuspage_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            incident = await statuspage_client.create_incident(
                name="API Issues",
                status=IncidentStatus.INVESTIGATING,
                impact=IncidentImpact.MAJOR,
                body="We are investigating API issues.",
                component_ids=["comp_1"],
            )

            assert incident.id == "inc_1"
            assert incident.shortlink == "https://stspg.io/abc123"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_incident(self, statuspage_client):
        """Should update incident successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "inc_1",
            "name": "API Issues",
            "status": "identified",
            "impact": "major",
            "components": [],
            "incident_updates": [],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(statuspage_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.patch.return_value = mock_response
            mock_get_client.return_value = mock_client

            incident = await statuspage_client.update_incident(
                incident_id="inc_1",
                status=IncidentStatus.IDENTIFIED,
                body="We have identified the root cause.",
            )

            assert incident.status == "identified"

    @pytest.mark.asyncio
    async def test_resolve_incident(self, statuspage_client):
        """Should resolve incident successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "inc_1",
            "name": "API Issues",
            "status": "resolved",
            "impact": "none",
            "resolved_at": "2024-01-15T12:00:00Z",
            "components": [],
            "incident_updates": [],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(statuspage_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.patch.return_value = mock_response
            mock_get_client.return_value = mock_client

            incident = await statuspage_client.resolve_incident(
                incident_id="inc_1",
                body="The issue has been resolved.",
            )

            assert incident.status == "resolved"

    @pytest.mark.asyncio
    async def test_list_incidents_not_configured(self):
        """Should raise error when not configured."""
        client = StatuspageClient(api_key="")

        with pytest.raises(ValueError, match="not configured"):
            await client.list_incidents()


# ==================== Template Tests ====================


class TestStatusUpdateTemplates:
    """Tests for StatusUpdateTemplates class."""

    @pytest.fixture
    def templates(self):
        """Create templates instance."""
        return StatusUpdateTemplates()

    def test_get_templates_by_category(self, templates):
        """Should return templates for a category."""
        investigating_templates = templates.get_templates_by_category(
            TemplateCategory.INVESTIGATING
        )

        assert len(investigating_templates) >= 1
        assert all(
            t.category == TemplateCategory.INVESTIGATING
            for t in investigating_templates
        )

    def test_get_default_template(self, templates):
        """Should return default template for a category."""
        default = templates.get_default_template(TemplateCategory.INVESTIGATING)

        assert default is not None
        assert default.is_default is True
        assert default.category == TemplateCategory.INVESTIGATING

    def test_render_template_success(self, templates):
        """Should render template with variables."""
        rendered = templates.render_template(
            "investigating_default",
            {
                "issue_type": "increased error rates",
                "service_name": "payments-api",
            },
        )

        assert "increased error rates" in rendered
        assert "payments-api" in rendered

    def test_render_template_missing_variables(self, templates):
        """Should handle missing variables gracefully."""
        # Should not raise, but insert placeholders
        rendered = templates.render_template("investigating_default", {})

        assert "[issue_type]" in rendered or "issue_type" in rendered.lower()

    def test_render_template_not_found(self, templates):
        """Should raise for unknown template."""
        with pytest.raises(ValueError, match="not found"):
            templates.render_template("nonexistent_template", {})

    def test_render_for_status(self, templates):
        """Should render appropriate template for status."""
        rendered = templates.render_for_status(
            IncidentStatus.RESOLVED,
            {"service_name": "api"},
        )

        assert "resolved" in rendered.lower() or "operating normally" in rendered.lower()

    def test_suggest_issue_type(self, templates):
        """Should suggest issue type from alert title."""
        assert "error" in templates.suggest_issue_type("High error rate", [])
        assert "latency" in templates.suggest_issue_type("Slow response times", ["latency"])
        assert "availability" in templates.suggest_issue_type("Service unavailable", [])

    def test_suggest_impact(self, templates):
        """Should suggest impact from severity."""
        assert templates.suggest_impact("critical") == ComponentImpact.CRITICAL
        assert templates.suggest_impact("high") == ComponentImpact.MAJOR
        assert templates.suggest_impact("medium") == ComponentImpact.MINOR
        assert templates.suggest_impact("low") == ComponentImpact.NONE
        assert templates.suggest_impact("P1") == ComponentImpact.CRITICAL

    def test_add_custom_template(self, templates):
        """Should add custom template."""
        custom = UpdateTemplate(
            id="custom_investigating",
            name="Custom Investigating",
            category=TemplateCategory.INVESTIGATING,
            template="Custom: $service_name is having issues.",
            variables=["service_name"],
        )

        templates.add_template(custom)
        retrieved = templates.get_template("custom_investigating")

        assert retrieved is not None
        assert retrieved.name == "Custom Investigating"

    def test_remove_template(self, templates):
        """Should remove template."""
        # Add then remove
        custom = UpdateTemplate(
            id="to_remove",
            name="To Remove",
            category=TemplateCategory.INVESTIGATING,
            template="Test",
            variables=[],
        )
        templates.add_template(custom)

        assert templates.remove_template("to_remove") is True
        assert templates.get_template("to_remove") is None
        assert templates.remove_template("nonexistent") is False


# ==================== Sync Tests ====================


class TestStatusPageSync:
    """Tests for StatusPageSync class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock Statuspage client."""
        client = MagicMock()
        client.is_configured = True
        client.default_page_id = "page_123"
        client.create_incident = AsyncMock()
        client.update_incident = AsyncMock()
        client.resolve_incident = AsyncMock()
        client.get_incident = AsyncMock()
        return client

    @pytest.fixture
    def mock_templates(self):
        """Create mock templates."""
        templates = MagicMock()
        templates.suggest_issue_type.return_value = "increased error rates"
        templates.render_for_status.return_value = "We are investigating..."
        templates.render_template.return_value = "Issue has been resolved."
        return templates

    @pytest.fixture
    def sync(self, mock_client, mock_templates):
        """Create sync instance."""
        mappings = [
            ComponentMapping(
                internal_service="payments-api",
                component_id="comp_payments",
                page_id="page_123",
                severity_threshold="high",
            )
        ]
        return StatusPageSync(
            client=mock_client,
            templates=mock_templates,
            component_mappings=mappings,
        )

    def test_get_mapping_for_service(self, sync):
        """Should find mapping for service."""
        mapping = sync.get_mapping_for_service("payments-api")
        assert mapping is not None
        assert mapping.component_id == "comp_payments"

        # Case insensitive
        mapping = sync.get_mapping_for_service("PAYMENTS-API")
        assert mapping is not None

    def test_get_mapping_not_found(self, sync):
        """Should return None for unmapped service."""
        mapping = sync.get_mapping_for_service("unknown-service")
        assert mapping is None

    def test_should_sync_incident_meets_threshold(self, sync):
        """Should sync when severity meets threshold."""
        incident = InternalIncident(
            id="inc_1",
            title="High Error Rate",
            service_name="payments-api",
            severity="high",
            status="open",
            triggered_at=datetime.utcnow(),
        )

        assert sync.should_sync_incident(incident) is True

    def test_should_sync_incident_below_threshold(self, sync):
        """Should not sync when severity below threshold."""
        incident = InternalIncident(
            id="inc_1",
            title="Low Priority Issue",
            service_name="payments-api",
            severity="low",
            status="open",
            triggered_at=datetime.utcnow(),
        )

        assert sync.should_sync_incident(incident) is False

    def test_should_sync_incident_no_mapping(self, sync):
        """Should not sync when no mapping exists."""
        incident = InternalIncident(
            id="inc_1",
            title="Issue",
            service_name="unknown-service",
            severity="high",
            status="open",
            triggered_at=datetime.utcnow(),
        )

        assert sync.should_sync_incident(incident) is False

    @pytest.mark.asyncio
    async def test_sync_incident_created_success(self, sync, mock_client):
        """Should sync new incident successfully."""
        mock_client.create_incident.return_value = StatusIncident(
            id="status_inc_1",
            page_id="page_123",
            name="High Error Rate",
            shortlink="https://stspg.io/abc",
        )

        incident = InternalIncident(
            id="inc_1",
            title="High Error Rate",
            service_name="payments-api",
            severity="critical",
            status="open",
            triggered_at=datetime.utcnow(),
        )

        result = await sync.sync_incident_created(incident)

        assert result.success is True
        assert result.action == "created"
        assert result.status_incident_id == "status_inc_1"
        mock_client.create_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_incident_created_skipped_threshold(self, sync, mock_client):
        """Should skip incident below severity threshold."""
        incident = InternalIncident(
            id="inc_1",
            title="Low Priority",
            service_name="payments-api",
            severity="low",
            status="open",
            triggered_at=datetime.utcnow(),
        )

        result = await sync.sync_incident_created(incident)

        assert result.success is True
        assert result.action == "skipped"
        mock_client.create_incident.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_incident_updated(self, sync, mock_client):
        """Should update synced incident."""
        # Register a synced incident
        sync.register_synced_incident("inc_1", "status_inc_1")

        mock_client.update_incident.return_value = StatusIncident(
            id="status_inc_1",
            page_id="page_123",
            name="High Error Rate",
            status=IncidentStatus.IDENTIFIED,
        )

        incident = InternalIncident(
            id="inc_1",
            title="High Error Rate",
            service_name="payments-api",
            severity="high",
            status="identified",
            triggered_at=datetime.utcnow(),
        )

        result = await sync.sync_incident_updated(incident, IncidentStatus.IDENTIFIED)

        assert result.success is True
        assert result.action == "updated"

    @pytest.mark.asyncio
    async def test_sync_incident_resolved(self, sync, mock_client):
        """Should resolve synced incident."""
        sync.register_synced_incident("inc_1", "status_inc_1")

        mock_client.resolve_incident.return_value = StatusIncident(
            id="status_inc_1",
            page_id="page_123",
            name="High Error Rate",
            status=IncidentStatus.RESOLVED,
        )

        incident = InternalIncident(
            id="inc_1",
            title="High Error Rate",
            service_name="payments-api",
            severity="high",
            status="resolved",
            triggered_at=datetime.utcnow() - timedelta(hours=1),
            resolved_at=datetime.utcnow(),
        )

        result = await sync.sync_incident_resolved(incident)

        assert result.success is True
        assert result.action == "resolved"

    @pytest.mark.asyncio
    async def test_sync_incident_resolved_no_synced_incident(self, sync, mock_client):
        """Should skip resolve when no synced incident."""
        incident = InternalIncident(
            id="inc_unknown",
            title="Unknown",
            service_name="payments-api",
            severity="high",
            status="resolved",
            triggered_at=datetime.utcnow(),
        )

        result = await sync.sync_incident_resolved(incident)

        assert result.success is False
        assert result.action == "skipped"


# ==================== Automation Tests ====================


class TestStatusPageAutomation:
    """Tests for StatusPageAutomation class."""

    @pytest.fixture
    def mock_client(self):
        """Create mock client."""
        return MagicMock()

    @pytest.fixture
    def mock_sync(self):
        """Create mock sync service."""
        sync = MagicMock()
        sync.sync_incident_created = AsyncMock(
            return_value=SyncResult(
                success=True,
                incident_id="inc_1",
                status_incident_id="status_1",
                action="created",
            )
        )
        sync.sync_incident_updated = AsyncMock(
            return_value=SyncResult(success=True, incident_id="inc_1", action="updated")
        )
        sync.sync_incident_resolved = AsyncMock(
            return_value=SyncResult(success=True, incident_id="inc_1", action="resolved")
        )
        sync.get_synced_status_incident = AsyncMock(return_value=None)
        sync._synced_incidents = {}
        return sync

    @pytest.fixture
    def automation(self, mock_client, mock_sync):
        """Create automation instance."""
        return StatusPageAutomation(
            client=mock_client,
            sync=mock_sync,
            config=AutomationConfig(),
        )

    def test_should_auto_create_critical(self, automation):
        """Should auto-create for critical severity."""
        assert automation.should_auto_create("critical") is True
        assert automation.should_auto_create("CRITICAL") is True
        assert automation.should_auto_create("p1") is True

    def test_should_auto_create_high(self, automation):
        """Should auto-create for high severity."""
        assert automation.should_auto_create("high") is True
        assert automation.should_auto_create("p2") is True

    def test_should_not_auto_create_low(self, automation):
        """Should not auto-create for low severity."""
        assert automation.should_auto_create("low") is False
        assert automation.should_auto_create("medium") is False

    def test_manual_override(self, automation):
        """Should track manual override."""
        automation.set_manual_override("inc_1")
        assert automation.has_manual_override("inc_1") is True
        assert automation.has_manual_override("inc_2") is False

        automation.clear_manual_override("inc_1")
        assert automation.has_manual_override("inc_1") is False

    @pytest.mark.asyncio
    async def test_on_incident_created_auto_creates(self, automation, mock_sync):
        """Should auto-create status incident for P1/P2."""
        # Disable grouping for immediate creation
        automation.config.group_related_incidents = False

        result = await automation.on_incident_created(
            incident_id="inc_1",
            title="Database Down",
            service_name="payments-api",
            severity="critical",
        )

        assert result.success is True
        mock_sync.sync_incident_created.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_incident_created_skips_low_severity(self, automation, mock_sync):
        """Should skip auto-create for low severity."""
        result = await automation.on_incident_created(
            incident_id="inc_1",
            title="Minor Issue",
            service_name="payments-api",
            severity="low",
        )

        assert result.success is True
        assert result.action == "skipped"
        mock_sync.sync_incident_created.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_incident_created_groups_incidents(self, automation, mock_sync):
        """Should group related incidents within time window."""
        automation.config.group_related_incidents = True
        automation.config.notification_delay_seconds = 60

        # First incident creates pending
        result1 = await automation.on_incident_created(
            incident_id="inc_1",
            title="Error Rate High",
            service_name="payments-api",
            severity="high",
        )

        assert result1.action == "pending"

        # Second incident groups with first
        result2 = await automation.on_incident_created(
            incident_id="inc_2",
            title="Timeout Errors",
            service_name="payments-api",
            severity="high",
        )

        assert result2.action == "grouped"

    @pytest.mark.asyncio
    async def test_on_incident_updated_with_override(self, automation, mock_sync):
        """Should skip update when manual override is set."""
        automation.set_manual_override("inc_1")

        result = await automation.on_incident_updated(
            incident_id="inc_1",
            title="Issue",
            service_name="payments-api",
            severity="high",
            status="identified",
        )

        assert result.action == "skipped"
        assert "override" in result.message.lower()

    @pytest.mark.asyncio
    async def test_on_incident_resolved_clears_override(self, automation, mock_sync):
        """Should clear manual override on resolution."""
        automation.set_manual_override("inc_1")
        mock_sync._synced_incidents = {"inc_1": "status_1"}

        await automation.on_incident_resolved(
            incident_id="inc_1",
            title="Issue",
            service_name="payments-api",
            severity="high",
        )

        assert automation.has_manual_override("inc_1") is False

    @pytest.mark.asyncio
    async def test_force_create_status_incident(self, automation, mock_sync):
        """Should force create status incident."""
        result = await automation.force_create_status_incident(
            incident_id="inc_1",
            title="Forced Incident",
            service_name="any-service",
            severity="low",  # Even low severity
            body="Custom message",
        )

        assert result.success is True
        mock_sync.sync_incident_created.assert_called_once()


# ==================== Integration Tests ====================


class TestEndToEndFlow:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_full_incident_lifecycle(self):
        """Test complete incident lifecycle through status page."""
        # Setup mocks
        mock_client = MagicMock()
        mock_client.is_configured = True
        mock_client.default_page_id = "page_123"

        created_incident = StatusIncident(
            id="status_1",
            page_id="page_123",
            name="API Degradation",
            status=IncidentStatus.INVESTIGATING,
            shortlink="https://stspg.io/test",
        )

        mock_client.create_incident = AsyncMock(return_value=created_incident)
        mock_client.update_incident = AsyncMock(
            return_value=StatusIncident(
                id="status_1",
                page_id="page_123",
                name="API Degradation",
                status=IncidentStatus.IDENTIFIED,
            )
        )
        mock_client.resolve_incident = AsyncMock(
            return_value=StatusIncident(
                id="status_1",
                page_id="page_123",
                name="API Degradation",
                status=IncidentStatus.RESOLVED,
            )
        )

        # Create sync and automation
        templates = StatusUpdateTemplates()
        sync = StatusPageSync(
            client=mock_client,
            templates=templates,
            component_mappings=[
                ComponentMapping(
                    internal_service="api-service",
                    component_id="comp_api",
                    page_id="page_123",
                )
            ],
        )
        automation = StatusPageAutomation(
            client=mock_client,
            sync=sync,
            templates=templates,
            config=AutomationConfig(group_related_incidents=False),
        )

        # 1. Incident created
        result = await automation.on_incident_created(
            incident_id="int_1",
            title="API Degradation",
            service_name="api-service",
            severity="high",
        )

        assert result.success is True
        assert result.action == "created"
        assert result.status_incident_id == "status_1"

        # 2. Incident acknowledged/identified
        mock_client.get_incident = AsyncMock(return_value=created_incident)
        sync.register_synced_incident("int_1", "status_1")

        result = await automation.on_incident_updated(
            incident_id="int_1",
            title="API Degradation",
            service_name="api-service",
            severity="high",
            status="identified",
        )

        assert result.success is True
        assert result.action == "updated"

        # 3. Incident resolved
        result = await automation.on_incident_resolved(
            incident_id="int_1",
            title="API Degradation",
            service_name="api-service",
            severity="high",
            resolution_message="Fixed the issue.",
        )

        assert result.success is True
        assert result.action == "resolved"
