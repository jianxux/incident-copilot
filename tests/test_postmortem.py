"""Comprehensive tests for postmortem generation module."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import Settings
from src.models import (
    AILogSummary,
    ContextCard,
    DatadogContext,
    Deployment,
    GitHubContext,
    LogSummary,
    MetricSnapshot,
    Severity,
)
from src.postmortem import (
    ActionItem,
    ActionItemPriority,
    ActionItemStatus,
    ConfluenceTemplate,
    ImpactAssessment,
    JSONTemplate,
    MarkdownTemplate,
    Postmortem,
    PostmortemFormat,
    PostmortemGenerator,
    PostmortemStatus,
    PostmortemStore,
    PostmortemUpdateRequest,
    RootCauseAnalysis,
    SlackTemplate,
    TimelineEvent,
    TimelineEventType,
    get_template,
    postmortem_router,
    postmortem_store,
    render_postmortem,
)

# --- Fixtures ---


@pytest.fixture
def sample_context_card() -> ContextCard:
    """Create a sample context card for testing."""
    return ContextCard(
        incident_id="INC-12345",
        title="High error rate on payments-api",
        severity=Severity.HIGH,
        service_name="payments-api",
        triggered_at=datetime(2024, 1, 15, 10, 0, 0),
        alert_url="https://pagerduty.com/incidents/12345",
        dashboard_url="https://datadog.com/dashboard/payments",
        github=GitHubContext(
            repo="mycompany/payments-api",
            recent_deploys=[
                Deployment(
                    sha="abc123def456",
                    short_sha="abc123d",
                    author="jane.doe",
                    message="Fix: Update payment processor timeout",
                    timestamp=datetime(2024, 1, 15, 9, 45, 0),
                    files_changed=["src/processor.py"],
                    additions=10,
                    deletions=2,
                ),
                Deployment(
                    sha="def456abc789",
                    short_sha="def456a",
                    author="john.smith",
                    message="Feat: Add new payment method",
                    timestamp=datetime(2024, 1, 15, 8, 30, 0),
                    files_changed=["src/methods.py", "tests/test_methods.py"],
                    additions=150,
                    deletions=10,
                ),
            ],
            codeowners=["@payments-team"],
        ),
        datadog=DatadogContext(
            service="payments-api",
            log_summaries=[
                LogSummary(
                    pattern="Connection timeout to payment processor",
                    count=150,
                    level="ERROR",
                    sample_message="Timeout after 30s connecting to processor.example.com",
                ),
                LogSummary(
                    pattern="Retry attempt failed",
                    count=75,
                    level="WARN",
                    sample_message="Retry 3/3 failed for transaction tx-12345",
                ),
            ],
            metrics=MetricSnapshot(
                error_rate=15.5,
                error_rate_baseline=0.5,
                latency_p99_ms=5000,
                request_count=10000,
                time_range_minutes=15,
            ),
        ),
        ai_summary=AILogSummary(
            top_issues=[
                "Connection timeouts to payment processor",
                "Increased retry failures",
                "Transaction queue backlog",
            ],
            explanation="The payment processor is experiencing connectivity issues causing timeouts and retry failures.",
            likely_cause="Network connectivity issue with upstream payment processor",
            suggested_actions=[
                "Check payment processor status page",
                "Review recent network changes",
                "Consider enabling circuit breaker",
            ],
        ),
        owners=["@payments-team", "jane.doe@company.com"],
    )


@pytest.fixture
def sample_postmortem() -> Postmortem:
    """Create a sample postmortem for testing."""
    return Postmortem(
        id="pm-abc123",
        incident_id="INC-12345",
        title="Postmortem: High error rate on payments-api",
        status=PostmortemStatus.DRAFT,
        service_name="payments-api",
        severity="high",
        executive_summary="On January 15, 2024, the payments-api service experienced elevated error rates due to connectivity issues with the upstream payment processor.",
        incident_started_at=datetime(2024, 1, 15, 10, 0, 0),
        incident_resolved_at=datetime(2024, 1, 15, 11, 30, 0),
        incident_duration_minutes=90,
        timeline=[
            TimelineEvent(
                timestamp=datetime(2024, 1, 15, 9, 45, 0),
                event_type=TimelineEventType.DEPLOYMENT,
                title="Deployment: abc123d",
                description="Fix: Update payment processor timeout",
                actor="jane.doe",
                source="github",
            ),
            TimelineEvent(
                timestamp=datetime(2024, 1, 15, 10, 0, 0),
                event_type=TimelineEventType.ALERT_TRIGGERED,
                title="High error rate alert fired",
                source="pagerduty",
            ),
            TimelineEvent(
                timestamp=datetime(2024, 1, 15, 10, 5, 0),
                event_type=TimelineEventType.INVESTIGATION_STARTED,
                title="On-call engineer started investigation",
                actor="john.smith",
            ),
            TimelineEvent(
                timestamp=datetime(2024, 1, 15, 10, 30, 0),
                event_type=TimelineEventType.ROOT_CAUSE_IDENTIFIED,
                title="Identified payment processor connectivity issue",
                actor="john.smith",
            ),
            TimelineEvent(
                timestamp=datetime(2024, 1, 15, 11, 30, 0),
                event_type=TimelineEventType.INCIDENT_RESOLVED,
                title="Incident resolved after processor recovered",
            ),
        ],
        root_cause=RootCauseAnalysis(
            primary_cause="Upstream payment processor experienced network issues",
            contributing_factors=[
                "No circuit breaker configured",
                "Timeout values were too long",
            ],
            trigger="Payment processor network maintenance",
            detection_method="Automated error rate alerting",
            why_not_prevented="Lack of circuit breaker pattern",
            confidence_level="high",
        ),
        impact=ImpactAssessment(
            severity="high",
            duration_minutes=90,
            users_affected=5000,
            users_affected_description="Users unable to complete payments",
            revenue_impact="Estimated $50,000 in failed transactions",
            sla_breach=True,
            sla_breach_description="Payment success rate dropped below 95% SLA",
            services_affected=["payments-api", "checkout-service"],
            regions_affected=["us-east-1"],
            summary="5000 users affected, estimated $50k revenue impact",
        ),
        action_items=[
            ActionItem(
                id="ai-001",
                title="Implement circuit breaker",
                description="Add circuit breaker pattern for payment processor calls",
                priority=ActionItemPriority.HIGH,
                status=ActionItemStatus.TODO,
                category="prevention",
            ),
            ActionItem(
                id="ai-002",
                title="Reduce timeout values",
                description="Lower timeout from 30s to 10s with retries",
                priority=ActionItemPriority.MEDIUM,
                status=ActionItemStatus.TODO,
                category="prevention",
            ),
            ActionItem(
                id="ai-003",
                title="Add processor health check",
                description="Implement health check endpoint monitoring",
                priority=ActionItemPriority.MEDIUM,
                status=ActionItemStatus.TODO,
                category="detection",
            ),
        ],
        lessons_learned=[
            "Circuit breakers are essential for external dependencies",
            "Need better timeout configuration management",
        ],
        what_went_well=[
            "Alert fired promptly",
            "On-call response was quick",
        ],
        what_went_poorly=[
            "No fallback for payment processing",
            "Communication to customers was delayed",
        ],
        lucky_factors=[
            "Incident occurred during low-traffic hours",
        ],
        alert_url="https://pagerduty.com/incidents/12345",
        dashboard_url="https://datadog.com/dashboard/payments",
        ai_generated=True,
        ai_model="claude-3-haiku-20240307",
        ai_confidence=0.85,
    )


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        anthropic_api_key="test-api-key",
        ai_model="claude-3-haiku-20240307",
    )


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(postmortem_router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
async def clean_store():
    """Clean the postmortem store before and after tests."""
    await postmortem_store.clear()
    yield
    await postmortem_store.clear()


# --- Store Tests ---


class TestPostmortemStore:
    """Tests for PostmortemStore."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, sample_postmortem):
        """Test saving and retrieving a postmortem."""
        store = PostmortemStore()

        saved = await store.save(sample_postmortem)
        assert saved.id == sample_postmortem.id

        retrieved = await store.get(sample_postmortem.id)
        assert retrieved is not None
        assert retrieved.id == sample_postmortem.id
        assert retrieved.incident_id == sample_postmortem.incident_id

    @pytest.mark.asyncio
    async def test_get_by_incident(self, sample_postmortem):
        """Test retrieving by incident ID."""
        store = PostmortemStore()
        await store.save(sample_postmortem)

        retrieved = await store.get_by_incident(sample_postmortem.incident_id)
        assert retrieved is not None
        assert retrieved.id == sample_postmortem.id

    @pytest.mark.asyncio
    async def test_update(self, sample_postmortem):
        """Test updating a postmortem."""
        store = PostmortemStore()
        original_version = sample_postmortem.version
        await store.save(sample_postmortem)

        updates = PostmortemUpdateRequest(
            status=PostmortemStatus.IN_REVIEW,
            executive_summary="Updated summary",
        )

        updated = await store.update(sample_postmortem.incident_id, updates)
        assert updated is not None
        assert updated.status == PostmortemStatus.IN_REVIEW
        assert updated.executive_summary == "Updated summary"
        assert updated.version == original_version + 1

    @pytest.mark.asyncio
    async def test_delete(self, sample_postmortem):
        """Test deleting a postmortem."""
        store = PostmortemStore()
        await store.save(sample_postmortem)

        deleted = await store.delete(sample_postmortem.incident_id)
        assert deleted is True

        retrieved = await store.get(sample_postmortem.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_list_with_filters(self):
        """Test listing postmortems with filters."""
        store = PostmortemStore()

        pm1 = Postmortem(
            id="pm-1",
            incident_id="INC-1",
            title="Test 1",
            service_name="service-a",
            severity="high",
            executive_summary="Summary 1",
            status=PostmortemStatus.DRAFT,
        )
        pm2 = Postmortem(
            id="pm-2",
            incident_id="INC-2",
            title="Test 2",
            service_name="service-b",
            severity="medium",
            executive_summary="Summary 2",
            status=PostmortemStatus.APPROVED,
        )

        await store.save(pm1)
        await store.save(pm2)

        # Test status filter
        drafts = await store.list(status=PostmortemStatus.DRAFT)
        assert len(drafts) == 1
        assert drafts[0].id == "pm-1"

        # Test service filter
        service_a = await store.list(service_name="service-a")
        assert len(service_a) == 1
        assert service_a[0].service_name == "service-a"

        # Test limit
        limited = await store.list(limit=1)
        assert len(limited) == 1


# --- Generator Tests ---


class TestPostmortemGenerator:
    """Tests for PostmortemGenerator."""

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        settings = Settings(anthropic_api_key="")
        generator = PostmortemGenerator(settings)
        assert generator.client is None

    def test_init_with_api_key(self, test_settings):
        """Test initialization with API key."""
        generator = PostmortemGenerator(test_settings)
        assert generator.client is not None

    def test_build_context_string(self, test_settings, sample_context_card):
        """Test building context string from context card."""
        generator = PostmortemGenerator(test_settings)
        context_str = generator._build_context_string(sample_context_card)

        assert "Recent Deployments" in context_str
        assert "abc123d" in context_str
        assert "jane.doe" in context_str
        assert "Datadog Metrics" in context_str
        assert "AI Log Analysis" in context_str

    def test_create_basic_timeline(self, test_settings, sample_context_card):
        """Test creating basic timeline without AI."""
        generator = PostmortemGenerator(test_settings)
        timeline = generator._create_basic_timeline(sample_context_card)

        assert len(timeline) >= 1
        # Should have alert triggered event
        alert_event = next(
            (e for e in timeline if e.event_type == TimelineEventType.ALERT_TRIGGERED),
            None,
        )
        assert alert_event is not None
        assert alert_event.title == sample_context_card.title

    @pytest.mark.asyncio
    async def test_generate_without_ai(self, sample_context_card):
        """Test generating postmortem without AI."""
        settings = Settings(anthropic_api_key="")
        generator = PostmortemGenerator(settings)

        postmortem = await generator.generate(
            incident_id="INC-12345",
            context_card=sample_context_card,
            include_ai_analysis=False,
        )

        assert postmortem.incident_id == "INC-12345"
        assert postmortem.service_name == "payments-api"
        assert postmortem.ai_generated is False
        assert len(postmortem.timeline) >= 1

    @pytest.mark.asyncio
    async def test_generate_with_mocked_ai(self, test_settings, sample_context_card):
        """Test generating postmortem with mocked AI responses."""
        generator = PostmortemGenerator(test_settings)

        # Mock the AI client
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps([
                    {
                        "timestamp": "2024-01-15T10:00:00Z",
                        "event_type": "alert_triggered",
                        "title": "High error rate alert fired",
                        "source": "pagerduty",
                    }
                ])
            )
        ]

        with patch.object(
            generator.client.messages, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response

            postmortem = await generator.generate(
                incident_id="INC-12345",
                context_card=sample_context_card,
                include_ai_analysis=True,
            )

            assert postmortem.incident_id == "INC-12345"
            assert postmortem.ai_generated is True


# --- Template Tests ---


class TestMarkdownTemplate:
    """Tests for MarkdownTemplate."""

    def test_render_basic(self, sample_postmortem):
        """Test basic markdown rendering."""
        template = MarkdownTemplate()
        output = template.render(sample_postmortem)

        assert f"# {sample_postmortem.title}" in output
        assert "## Executive Summary" in output
        assert sample_postmortem.executive_summary in output
        assert "## Timeline" in output
        assert "## Root Cause Analysis" in output
        assert "## Impact Assessment" in output
        assert "## Action Items" in output

    def test_render_timeline(self, sample_postmortem):
        """Test timeline rendering."""
        template = MarkdownTemplate()
        output = template.render(sample_postmortem)

        for event in sample_postmortem.timeline:
            assert event.title in output

    def test_render_action_items_table(self, sample_postmortem):
        """Test action items table rendering."""
        template = MarkdownTemplate()
        output = template.render(sample_postmortem)

        assert "| Priority | Title | Status | Owner |" in output
        for item in sample_postmortem.action_items:
            assert item.title in output

    def test_format_duration(self):
        """Test duration formatting."""
        template = MarkdownTemplate()

        assert template._format_duration(30) == "30 minutes"
        assert template._format_duration(60) == "1 hour"
        assert template._format_duration(90) == "1h 30m"
        assert template._format_duration(120) == "2 hours"


class TestConfluenceTemplate:
    """Tests for ConfluenceTemplate."""

    def test_render_basic(self, sample_postmortem):
        """Test basic Confluence rendering."""
        template = ConfluenceTemplate()
        output = template.render(sample_postmortem)

        assert f"h1. {sample_postmortem.title}" in output
        assert "{info}" in output
        assert "{toc}" in output
        assert "h2. Executive Summary" in output

    def test_render_timeline_table(self, sample_postmortem):
        """Test timeline table rendering."""
        template = ConfluenceTemplate()
        output = template.render(sample_postmortem)

        assert "||Time||Event||Actor||" in output

    def test_render_status_macro(self, sample_postmortem):
        """Test status macro rendering."""
        template = ConfluenceTemplate()
        output = template.render(sample_postmortem)

        # Should have a status macro with color
        assert "{status:colour=" in output


class TestSlackTemplate:
    """Tests for SlackTemplate."""

    def test_render_basic(self, sample_postmortem):
        """Test basic Slack Block Kit rendering."""
        template = SlackTemplate()
        output = template.render(sample_postmortem)

        data = json.loads(output)
        assert "blocks" in data

        # Should have a header block
        header = next((b for b in data["blocks"] if b.get("type") == "header"), None)
        assert header is not None

    def test_render_has_sections(self, sample_postmortem):
        """Test that all sections are present."""
        template = SlackTemplate()
        output = template.render(sample_postmortem)

        data = json.loads(output)
        block_texts = []
        for block in data["blocks"]:
            if block.get("type") == "section" and block.get("text"):
                block_texts.append(block["text"].get("text", ""))

        full_text = " ".join(block_texts)
        assert (
            "Executive Summary" in full_text
            or sample_postmortem.executive_summary[:50] in full_text
        )

    def test_render_has_action_buttons(self, sample_postmortem):
        """Test that action buttons are present."""
        template = SlackTemplate()
        output = template.render(sample_postmortem)

        data = json.loads(output)
        actions = next((b for b in data["blocks"] if b.get("type") == "actions"), None)
        assert actions is not None


class TestJSONTemplate:
    """Tests for JSONTemplate."""

    def test_render_valid_json(self, sample_postmortem):
        """Test that output is valid JSON."""
        template = JSONTemplate()
        output = template.render(sample_postmortem)

        data = json.loads(output)
        assert data["id"] == sample_postmortem.id
        assert data["incident_id"] == sample_postmortem.incident_id

    def test_render_all_fields(self, sample_postmortem):
        """Test that all fields are included."""
        template = JSONTemplate()
        output = template.render(sample_postmortem)

        data = json.loads(output)
        assert "timeline" in data
        assert "root_cause" in data
        assert "impact" in data
        assert "action_items" in data


class TestTemplateRegistry:
    """Tests for template registry functions."""

    def test_get_template(self):
        """Test getting templates by format."""
        assert isinstance(get_template(PostmortemFormat.MARKDOWN), MarkdownTemplate)
        assert isinstance(get_template(PostmortemFormat.CONFLUENCE), ConfluenceTemplate)
        assert isinstance(get_template(PostmortemFormat.SLACK), SlackTemplate)
        assert isinstance(get_template(PostmortemFormat.JSON), JSONTemplate)

    def test_render_postmortem(self, sample_postmortem):
        """Test render_postmortem helper."""
        for fmt in PostmortemFormat:
            output = render_postmortem(sample_postmortem, fmt)
            assert output is not None
            assert len(output) > 0


# --- API Route Tests ---


class TestPostmortemRoutes:
    """Tests for postmortem API routes."""

    @pytest.mark.asyncio
    async def test_generate_postmortem(self, client, clean_store):
        """Test POST /api/postmortems/generate."""
        response = client.post(
            "/api/postmortems/generate",
            json={
                "incident_id": "INC-99999",
                "format": "markdown",
                "include_ai_analysis": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "postmortem" in data
        assert data["postmortem"]["incident_id"] == "INC-99999"

    @pytest.mark.asyncio
    async def test_generate_returns_existing(self, client, clean_store, sample_postmortem):
        """Test that generate returns existing postmortem."""
        # First save a postmortem
        await postmortem_store.save(sample_postmortem)

        response = client.post(
            "/api/postmortems/generate",
            json={
                "incident_id": sample_postmortem.incident_id,
                "include_ai_analysis": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["postmortem"]["id"] == sample_postmortem.id
        assert "already exists" in data["message"]

    @pytest.mark.asyncio
    async def test_get_postmortem(self, client, clean_store, sample_postmortem):
        """Test GET /api/postmortems/{id}."""
        await postmortem_store.save(sample_postmortem)

        response = client.get(f"/api/postmortems/{sample_postmortem.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_postmortem.id

    @pytest.mark.asyncio
    async def test_get_postmortem_not_found(self, client, clean_store):
        """Test GET /api/postmortems/{id} with non-existent ID."""
        response = client.get("/api/postmortems/pm-nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_by_incident(self, client, clean_store, sample_postmortem):
        """Test GET /api/postmortems/by-incident/{incident_id}."""
        await postmortem_store.save(sample_postmortem)

        response = client.get(f"/api/postmortems/by-incident/{sample_postmortem.incident_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["incident_id"] == sample_postmortem.incident_id

    @pytest.mark.asyncio
    async def test_update_postmortem(self, client, clean_store, sample_postmortem):
        """Test PUT /api/postmortems/{id}."""
        await postmortem_store.save(sample_postmortem)

        response = client.put(
            f"/api/postmortems/{sample_postmortem.id}",
            json={
                "status": "in_review",
                "executive_summary": "Updated summary text",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_review"
        assert data["executive_summary"] == "Updated summary text"

    @pytest.mark.asyncio
    async def test_delete_postmortem(self, client, clean_store, sample_postmortem):
        """Test DELETE /api/postmortems/{id}."""
        await postmortem_store.save(sample_postmortem)

        response = client.delete(f"/api/postmortems/{sample_postmortem.id}")

        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # Verify it's gone
        get_response = client.get(f"/api/postmortems/{sample_postmortem.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_postmortems(self, client, clean_store, sample_postmortem):
        """Test GET /api/postmortems."""
        await postmortem_store.save(sample_postmortem)

        response = client.get("/api/postmortems")

        assert response.status_code == 200
        data = response.json()
        assert "postmortems" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_with_filters(self, client, clean_store, sample_postmortem):
        """Test GET /api/postmortems with filters."""
        await postmortem_store.save(sample_postmortem)

        # Filter by status
        response = client.get("/api/postmortems?status=draft")
        assert response.status_code == 200

        # Filter by service
        response = client.get("/api/postmortems?service=payments-api")
        assert response.status_code == 200
        data = response.json()
        assert all(p["service_name"] == "payments-api" for p in data["postmortems"])

    @pytest.mark.asyncio
    async def test_export_postmortem(self, client, clean_store, sample_postmortem):
        """Test POST /api/postmortems/{id}/export."""
        await postmortem_store.save(sample_postmortem)

        for fmt in ["markdown", "confluence", "slack", "json"]:
            response = client.post(
                f"/api/postmortems/{sample_postmortem.id}/export",
                json={"format": fmt},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["format"] == fmt
            assert len(data["content"]) > 0

    @pytest.mark.asyncio
    async def test_export_raw(self, client, clean_store, sample_postmortem):
        """Test GET /api/postmortems/{id}/export/{format}."""
        await postmortem_store.save(sample_postmortem)

        response = client.get(f"/api/postmortems/{sample_postmortem.id}/export/markdown")

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert sample_postmortem.title in response.text

    @pytest.mark.asyncio
    async def test_status_transitions(self, client, clean_store, sample_postmortem):
        """Test POST /api/postmortems/{id}/status transitions."""
        await postmortem_store.save(sample_postmortem)

        # Valid transition: draft -> in_review
        response = client.post(f"/api/postmortems/{sample_postmortem.id}/status?status=in_review")
        assert response.status_code == 200
        assert response.json()["status"] == "in_review"

        # Valid transition: in_review -> approved
        response = client.post(
            f"/api/postmortems/{sample_postmortem.id}/status?status=approved&approved_by=admin"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_invalid_status_transition(self, client, clean_store, sample_postmortem):
        """Test invalid status transitions are rejected."""
        await postmortem_store.save(sample_postmortem)

        # Invalid: draft -> published (must go through in_review and approved)
        response = client.post(f"/api/postmortems/{sample_postmortem.id}/status?status=published")
        assert response.status_code == 400
        assert "Invalid status transition" in response.json()["detail"]


# --- Model Tests ---


class TestModels:
    """Tests for postmortem models."""

    def test_timeline_event_creation(self):
        """Test TimelineEvent model."""
        event = TimelineEvent(
            timestamp=datetime.utcnow(),
            event_type=TimelineEventType.ALERT_TRIGGERED,
            title="Test alert",
            description="Test description",
            actor="test.user",
            source="pagerduty",
        )

        assert event.title == "Test alert"
        assert event.event_type == TimelineEventType.ALERT_TRIGGERED

    def test_action_item_defaults(self):
        """Test ActionItem default values."""
        item = ActionItem(
            id="test-1",
            title="Test action",
        )

        assert item.priority == ActionItemPriority.MEDIUM
        assert item.status == ActionItemStatus.TODO
        assert item.owner is None

    def test_postmortem_serialization(self, sample_postmortem):
        """Test Postmortem JSON serialization."""
        json_str = sample_postmortem.model_dump_json()
        data = json.loads(json_str)

        assert data["id"] == sample_postmortem.id
        assert "timeline" in data
        assert "root_cause" in data

    def test_postmortem_update_request_partial(self):
        """Test PostmortemUpdateRequest with partial data."""
        request = PostmortemUpdateRequest(
            title="New title",
        )

        dump = request.model_dump(exclude_unset=True)
        assert "title" in dump
        assert "status" not in dump
