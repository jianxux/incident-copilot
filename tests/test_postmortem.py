"""Tests for postmortem generation."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import Settings
from src.postmortem.models import (
    PostmortemFormat,
    PostmortemStatus,
    TimelineEventType,
    TimelineEvent,
    PostmortemData,
)
from src.postmortem.generator import PostmortemGenerator
from src.postmortem.templates import (
    MarkdownTemplate,
    ConfluenceTemplate,
    SlackTemplate,
    JSONTemplate,
)
from src.postmortem.store import PostmortemStore


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        anthropic_api_key="test-api-key",
        database_url="postgresql+asyncpg://test@localhost/test",
    )


@pytest.fixture
def sample_postmortem():
    """Create a sample postmortem for testing."""
    return PostmortemData(
        id="pm-123",
        incident_id="inc-456",
        title="Payment Service Outage - 2026-02-02",
        status=PostmortemStatus.DRAFT,
        summary="Payment processing was down for 45 minutes due to database connection exhaustion.",
        timeline=[
            TimelineEvent(
                timestamp=datetime(2026, 2, 2, 3, 0, tzinfo=timezone.utc),
                event_type=TimelineEventType.ALERT_TRIGGERED,
                title="High error rate alert",
                description="Error rate exceeded 5% threshold",
            ),
            TimelineEvent(
                timestamp=datetime(2026, 2, 2, 3, 5, tzinfo=timezone.utc),
                event_type=TimelineEventType.ALERT_ACKNOWLEDGED,
                title="On-call acknowledged",
                actor="John Smith",
            ),
            TimelineEvent(
                timestamp=datetime(2026, 2, 2, 3, 15, tzinfo=timezone.utc),
                event_type=TimelineEventType.ROOT_CAUSE_IDENTIFIED,
                title="Database connection pool exhausted",
                description="Found max_connections limit reached",
            ),
            TimelineEvent(
                timestamp=datetime(2026, 2, 2, 3, 30, tzinfo=timezone.utc),
                event_type=TimelineEventType.MITIGATION_STARTED,
                title="Increased connection pool size",
                actor="John Smith",
            ),
            TimelineEvent(
                timestamp=datetime(2026, 2, 2, 3, 45, tzinfo=timezone.utc),
                event_type=TimelineEventType.INCIDENT_RESOLVED,
                title="Service recovered",
                description="Error rate back to normal",
            ),
        ],
        root_cause="Database connection pool was exhausted due to a connection leak in the new payment flow introduced in v2.1.0.",
        impact="45 minutes of degraded service. Approximately 1,200 payment attempts failed.",
        affected_services=["payments-api", "checkout-service"],
        action_items=[
            {"title": "Fix connection leak", "assignee": "payments-team", "priority": "high"},
            {"title": "Add connection pool monitoring", "assignee": "platform-team", "priority": "medium"},
            {"title": "Review deployment checklist", "assignee": "sre-team", "priority": "low"},
        ],
        created_at=datetime(2026, 2, 2, 4, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 2, 4, 0, tzinfo=timezone.utc),
    )


class TestPostmortemModels:
    """Tests for postmortem data models."""

    def test_postmortem_format_values(self):
        """Test PostmortemFormat enum values."""
        assert PostmortemFormat.MARKDOWN == "markdown"
        assert PostmortemFormat.CONFLUENCE == "confluence"
        assert PostmortemFormat.SLACK == "slack"
        assert PostmortemFormat.JSON == "json"

    def test_postmortem_status_values(self):
        """Test PostmortemStatus enum values."""
        assert PostmortemStatus.DRAFT == "draft"
        assert PostmortemStatus.IN_REVIEW == "in_review"
        assert PostmortemStatus.APPROVED == "approved"
        assert PostmortemStatus.PUBLISHED == "published"

    def test_timeline_event(self):
        """Test TimelineEvent creation."""
        event = TimelineEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="Test alert",
            description="Alert description",
            actor="system",
        )
        assert event.title == "Test alert"
        assert event.event_type == TimelineEventType.ALERT_TRIGGERED

    def test_postmortem_data(self, sample_postmortem):
        """Test PostmortemData structure."""
        assert sample_postmortem.id == "pm-123"
        assert sample_postmortem.incident_id == "inc-456"
        assert len(sample_postmortem.timeline) == 5
        assert len(sample_postmortem.action_items) == 3
        assert sample_postmortem.status == PostmortemStatus.DRAFT


class TestPostmortemGenerator:
    """Tests for PostmortemGenerator."""

    @pytest.mark.asyncio
    async def test_generate_postmortem(self, settings):
        """Test postmortem generation."""
        generator = PostmortemGenerator(settings)
        
        # Mock the AI response
        with patch.object(generator, "_call_ai", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = {
                "summary": "Service outage due to database issues",
                "root_cause": "Connection pool exhausted",
                "impact": "Users unable to complete payments",
                "action_items": [
                    {"title": "Fix connection leak", "priority": "high"},
                ],
            }
            
            # Create mock context
            context = {
                "incident_id": "inc-123",
                "alert": {"title": "High Error Rate", "severity": "high"},
                "logs": ["Error: connection refused", "Error: timeout"],
                "deployments": [{"version": "v2.1.0", "timestamp": "2026-02-02T02:30:00Z"}],
            }
            
            postmortem = await generator.generate(
                incident_id="inc-123",
                context=context,
            )
        
        assert postmortem is not None
        assert postmortem.incident_id == "inc-123"

    @pytest.mark.asyncio
    async def test_generate_timeline(self, settings):
        """Test timeline generation from context."""
        generator = PostmortemGenerator(settings)
        
        context = {
            "alert": {
                "triggered_at": "2026-02-02T03:00:00Z",
                "acknowledged_at": "2026-02-02T03:05:00Z",
                "resolved_at": "2026-02-02T03:45:00Z",
            },
            "deployments": [
                {"version": "v2.1.0", "timestamp": "2026-02-02T02:30:00Z"},
            ],
        }
        
        timeline = generator._build_timeline_from_context(context)
        
        assert len(timeline) >= 2  # At least alert triggered and resolved


class TestMarkdownTemplate:
    """Tests for Markdown template."""

    def test_render_markdown(self, sample_postmortem):
        """Test Markdown rendering."""
        template = MarkdownTemplate()
        output = template.render(sample_postmortem)
        
        assert "# Payment Service Outage" in output
        assert "## Summary" in output
        assert "## Timeline" in output
        assert "## Root Cause" in output
        assert "## Impact" in output
        assert "## Action Items" in output
        assert "connection pool" in output.lower()

    def test_render_timeline_events(self, sample_postmortem):
        """Test timeline event rendering."""
        template = MarkdownTemplate()
        output = template.render(sample_postmortem)
        
        assert "High error rate alert" in output
        assert "On-call acknowledged" in output
        assert "Service recovered" in output


class TestConfluenceTemplate:
    """Tests for Confluence template."""

    def test_render_confluence(self, sample_postmortem):
        """Test Confluence wiki markup rendering."""
        template = ConfluenceTemplate()
        output = template.render(sample_postmortem)
        
        # Check for Confluence-specific markup
        assert "h1." in output or "{panel}" in output
        assert sample_postmortem.title in output

    def test_confluence_table_format(self, sample_postmortem):
        """Test Confluence table formatting."""
        template = ConfluenceTemplate()
        output = template.render(sample_postmortem)
        
        # Should contain table markup
        assert "||" in output or "|" in output


class TestSlackTemplate:
    """Tests for Slack Block Kit template."""

    def test_render_slack_blocks(self, sample_postmortem):
        """Test Slack Block Kit JSON rendering."""
        template = SlackTemplate()
        output = template.render(sample_postmortem)
        
        # Should be valid JSON-like structure
        assert "blocks" in output or "header" in output.lower()

    def test_slack_contains_key_sections(self, sample_postmortem):
        """Test Slack output contains key sections."""
        template = SlackTemplate()
        output = template.render(sample_postmortem)
        
        assert sample_postmortem.title in output
        # Summary should be present
        assert "Summary" in output or "summary" in output.lower()


class TestJSONTemplate:
    """Tests for JSON template."""

    def test_render_json(self, sample_postmortem):
        """Test JSON rendering."""
        import json
        
        template = JSONTemplate()
        output = template.render(sample_postmortem)
        
        # Should be valid JSON
        data = json.loads(output)
        assert data["id"] == sample_postmortem.id
        assert data["incident_id"] == sample_postmortem.incident_id
        assert "timeline" in data
        assert len(data["timeline"]) == 5


class TestPostmortemStore:
    """Tests for PostmortemStore."""

    @pytest.fixture
    def store(self, settings):
        """Create a store instance."""
        return PostmortemStore(settings)

    @pytest.mark.asyncio
    async def test_create_postmortem(self, store, sample_postmortem):
        """Test creating a postmortem."""
        # Use in-memory storage for testing
        with patch.object(store, "_use_database", False):
            result = await store.create(sample_postmortem)
            assert result.id == sample_postmortem.id

    @pytest.mark.asyncio
    async def test_get_postmortem(self, store, sample_postmortem):
        """Test getting a postmortem by ID."""
        with patch.object(store, "_use_database", False):
            await store.create(sample_postmortem)
            result = await store.get(sample_postmortem.id)
            assert result is not None
            assert result.id == sample_postmortem.id

    @pytest.mark.asyncio
    async def test_list_postmortems(self, store, sample_postmortem):
        """Test listing postmortems."""
        with patch.object(store, "_use_database", False):
            await store.create(sample_postmortem)
            results = await store.list()
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_update_postmortem(self, store, sample_postmortem):
        """Test updating a postmortem."""
        with patch.object(store, "_use_database", False):
            await store.create(sample_postmortem)
            
            sample_postmortem.status = PostmortemStatus.IN_REVIEW
            result = await store.update(sample_postmortem)
            
            assert result.status == PostmortemStatus.IN_REVIEW

    @pytest.mark.asyncio
    async def test_delete_postmortem(self, store, sample_postmortem):
        """Test deleting a postmortem."""
        with patch.object(store, "_use_database", False):
            await store.create(sample_postmortem)
            success = await store.delete(sample_postmortem.id)
            assert success is True
            
            result = await store.get(sample_postmortem.id)
            assert result is None


class TestPostmortemIntegration:
    """Integration tests for postmortem workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, settings, sample_postmortem):
        """Test full postmortem generation and export workflow."""
        store = PostmortemStore(settings)
        
        with patch.object(store, "_use_database", False):
            # Create
            await store.create(sample_postmortem)
            
            # Get
            pm = await store.get(sample_postmortem.id)
            assert pm is not None
            
            # Export to different formats
            md_template = MarkdownTemplate()
            md_output = md_template.render(pm)
            assert len(md_output) > 0
            
            json_template = JSONTemplate()
            json_output = json_template.render(pm)
            assert len(json_output) > 0
            
            # Update status
            pm.status = PostmortemStatus.APPROVED
            await store.update(pm)
            
            updated = await store.get(pm.id)
            assert updated.status == PostmortemStatus.APPROVED
