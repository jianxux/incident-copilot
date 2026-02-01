"""Tests for Microsoft Teams integration."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.config import Settings
from src.integrations.teams import TeamsAdapter
from src.models import (
    AILogSummary,
    ContextCard,
    DatadogContext,
    Deployment,
    GitHubContext,
    LogSummary,
    PastIncident,
    RunbookLink,
    Severity,
)


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        teams_webhook_url="https://outlook.office.com/webhook/test-webhook-url",
    )


@pytest.fixture
def teams_adapter(settings):
    """Create Teams adapter with test settings."""
    return TeamsAdapter(settings)


@pytest.fixture
def sample_context_card():
    """Create a sample context card for testing."""
    return ContextCard(
        incident_id="INC-123",
        title="High Error Rate on payments-api",
        severity=Severity.HIGH,
        service_name="payments-api",
        triggered_at=datetime(2024, 1, 15, 14, 30, 0),
        alert_url="https://pagerduty.com/incidents/INC-123",
        github=GitHubContext(
            repo="myorg/payments-api",
            recent_deploys=[
                Deployment(
                    sha="abc1234567890",
                    short_sha="abc1234",
                    author="sarah",
                    message="Fix retry logic for payment processing",
                    timestamp=datetime(2024, 1, 15, 14, 0, 0),
                    url="https://github.com/myorg/payments-api/commit/abc1234",
                ),
                Deployment(
                    sha="def5678901234",
                    short_sha="def5678",
                    author="mike",
                    message="Add timeout configuration",
                    timestamp=datetime(2024, 1, 15, 13, 30, 0),
                    url="https://github.com/myorg/payments-api/commit/def5678",
                ),
            ],
            codeowners=["@sarah", "@mike"],
        ),
        ai_summary=AILogSummary(
            top_issues=[
                "ConnectionTimeout to stripe-api (847 occurrences)",
                "Retry limit exceeded for payment requests (612 occurrences)",
                "Circuit breaker opened for external calls (89 occurrences)",
            ],
            explanation="The service is experiencing connection timeouts when calling Stripe's API, leading to retry exhaustion and circuit breaker activation.",
            likely_cause="Network latency or Stripe API degradation",
            suggested_actions=["Check Stripe status page", "Increase timeout values"],
        ),
        owners=["@sarah", "@mike"],
        dashboard_url="https://grafana.example.com/d/payments",
        runbook_url="https://docs.example.com/runbooks/payments-errors",
        assembly_time_ms=1234,
    )


@pytest.fixture
def minimal_context_card():
    """Create a minimal context card for testing."""
    return ContextCard(
        incident_id="INC-456",
        title="Service degradation",
        severity=Severity.MEDIUM,
        service_name="api-gateway",
        triggered_at=datetime(2024, 1, 15, 10, 0, 0),
    )


class TestTeamsAdapterCardFormatting:
    """Test Adaptive Card formatting."""

    def test_build_adaptive_card_structure(self, teams_adapter, sample_context_card):
        """Test that the adaptive card has correct structure."""
        card = teams_adapter._build_adaptive_card(sample_context_card)

        assert card["type"] == "message"
        assert "attachments" in card
        assert len(card["attachments"]) == 1

        attachment = card["attachments"][0]
        assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"

        content = attachment["content"]
        assert content["type"] == "AdaptiveCard"
        assert content["version"] == "1.4"
        assert "body" in content
        assert "actions" in content

    def test_header_contains_severity_emoji(self, teams_adapter, sample_context_card):
        """Test that header contains correct severity emoji."""
        card = teams_adapter._build_adaptive_card(sample_context_card)
        content = card["attachments"][0]["content"]

        # First element should be the header
        header = content["body"][0]
        assert header["type"] == "TextBlock"
        assert "🟠" in header["text"]  # High severity = orange
        assert "payments-api" in header["text"]
        assert "High Error Rate" in header["text"]

    def test_severity_colors(self, teams_adapter):
        """Test all severity levels map to correct colors."""
        for severity, expected_color, expected_emoji in [
            (Severity.CRITICAL, "attention", "🔴"),
            (Severity.HIGH, "warning", "🟠"),
            (Severity.MEDIUM, "accent", "🟡"),
            (Severity.LOW, "good", "🟢"),
            (Severity.INFO, "default", "🔵"),
        ]:
            card = ContextCard(
                incident_id="test",
                title="Test",
                severity=severity,
                service_name="test-service",
                triggered_at=datetime.now(),
            )
            result = teams_adapter._build_adaptive_card(card)
            content = result["attachments"][0]["content"]
            header = content["body"][0]

            assert header["color"] == expected_color
            assert expected_emoji in header["text"]

    def test_deployments_section(self, teams_adapter, sample_context_card):
        """Test that deployments are included in the card."""
        card = teams_adapter._build_adaptive_card(sample_context_card)
        content = card["attachments"][0]["content"]

        # Find deployment section
        deployment_found = False
        for element in content["body"]:
            if element.get(
                "type"
            ) == "TextBlock" and "Recent Deployments" in element.get("text", ""):
                deployment_found = True
                assert "abc1234" in element["text"]
                assert "sarah" in element["text"]
                break

        assert deployment_found, "Deployments section not found"

    def test_ai_summary_section(self, teams_adapter, sample_context_card):
        """Test that AI summary is included in the card."""
        card = teams_adapter._build_adaptive_card(sample_context_card)
        content = card["attachments"][0]["content"]

        # Find AI summary section
        ai_found = False
        for element in content["body"]:
            if element.get("type") == "TextBlock" and "AI Analysis" in element.get(
                "text", ""
            ):
                ai_found = True
                assert "ConnectionTimeout" in element["text"]
                break

        assert ai_found, "AI summary section not found"

    def test_log_summary_fallback(self, teams_adapter):
        """Test log summary is used when AI summary is not available."""
        card = ContextCard(
            incident_id="test",
            title="Test",
            severity=Severity.MEDIUM,
            service_name="test-service",
            triggered_at=datetime.now(),
            datadog=DatadogContext(
                service="test-service",
                log_summaries=[
                    LogSummary(
                        pattern="NullPointerException in UserService",
                        count=42,
                        level="ERROR",
                        sample_message="NPE at line 123",
                    ),
                ],
            ),
        )

        result = teams_adapter._build_adaptive_card(card)
        content = result["attachments"][0]["content"]

        # Find log summary section
        log_found = False
        for element in content["body"]:
            if element.get("type") == "TextBlock" and "Error Patterns" in element.get(
                "text", ""
            ):
                log_found = True
                assert "NullPointerException" in element["text"]
                assert "(42x)" in element["text"]
                break

        assert log_found, "Log summary section not found"

    def test_action_buttons(self, teams_adapter, sample_context_card):
        """Test that action buttons are correctly generated."""
        card = teams_adapter._build_adaptive_card(sample_context_card)
        content = card["attachments"][0]["content"]
        actions = content["actions"]

        # Should have 3 actions: PagerDuty, Runbook, Dashboard
        assert len(actions) == 3

        action_titles = [a["title"] for a in actions]
        assert "View in PagerDuty" in action_titles
        assert "📖 View Runbook" in action_titles
        assert "📊 Open Dashboard" in action_titles

        # Verify URLs
        for action in actions:
            assert action["type"] == "Action.OpenUrl"
            assert "url" in action

    def test_minimal_card(self, teams_adapter, minimal_context_card):
        """Test card generation with minimal data."""
        card = teams_adapter._build_adaptive_card(minimal_context_card)
        content = card["attachments"][0]["content"]

        # Should still have basic structure
        assert len(content["body"]) >= 2  # At least header and severity info
        assert content["actions"] == []  # No actions without URLs

    def test_similar_incidents_section(self, teams_adapter):
        """Test that similar incidents are included when available."""
        card = ContextCard(
            incident_id="test",
            title="Test",
            severity=Severity.MEDIUM,
            service_name="test-service",
            triggered_at=datetime.now(),
            similar_incidents=[
                PastIncident(
                    incident_id="INC-100",
                    title="Previous payment failure",
                    service="payments-api",
                    occurred_at=datetime(2024, 1, 10, 12, 0, 0),
                    resolution="Increased connection pool size",
                ),
            ],
        )

        result = teams_adapter._build_adaptive_card(card)
        content = result["attachments"][0]["content"]

        # Find similar incidents section
        incidents_found = False
        for element in content["body"]:
            if element.get(
                "type"
            ) == "TextBlock" and "Similar Past Incidents" in element.get("text", ""):
                incidents_found = True
                assert "Previous payment failure" in element["text"]
                assert "Increased connection pool" in element["text"]
                break

        assert incidents_found, "Similar incidents section not found"

    def test_runbooks_list_fallback(self, teams_adapter):
        """Test that runbooks list is used when runbook_url is not set."""
        card = ContextCard(
            incident_id="test",
            title="Test",
            severity=Severity.MEDIUM,
            service_name="test-service",
            triggered_at=datetime.now(),
            alert_url="https://pagerduty.com/test",
            runbooks=[
                RunbookLink(
                    title="Payment Errors Runbook",
                    url="https://docs.example.com/runbooks/payments",
                    source="github:main-docs",
                    relevance_score=0.95,
                    matched_terms=["payment", "error"],
                ),
            ],
        )

        result = teams_adapter._build_adaptive_card(card)
        content = result["attachments"][0]["content"]
        actions = content["actions"]

        # Should have 2 actions: PagerDuty, Runbook (from list)
        assert len(actions) == 2
        runbook_action = next((a for a in actions if "Runbook" in a["title"]), None)
        assert runbook_action is not None
        assert runbook_action["url"] == "https://docs.example.com/runbooks/payments"


class TestTeamsAdapterWebhook:
    """Test webhook sending functionality."""

    @pytest.mark.asyncio
    async def test_send_context_card_success(self, teams_adapter, sample_context_card):
        """Test successful webhook delivery."""
        with patch("src.integrations.teams.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = AsyncMock()
            mock_response.raise_for_status = lambda: None
            mock_client.post.return_value = mock_response

            result = await teams_adapter.send_context_card(sample_context_card)

            assert result is True
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[1]["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_send_context_card_http_error(
        self, teams_adapter, sample_context_card
    ):
        """Test handling of HTTP errors."""
        with patch("src.integrations.teams.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = AsyncMock()
            mock_response.status_code = 400
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Bad Request", request=AsyncMock(), response=mock_response
            )
            mock_client.post.return_value = mock_response

            result = await teams_adapter.send_context_card(sample_context_card)

            assert result is False

    @pytest.mark.asyncio
    async def test_send_without_webhook_url(self, sample_context_card):
        """Test that sending fails gracefully without webhook URL."""
        settings = Settings(teams_webhook_url="")
        adapter = TeamsAdapter(settings)

        result = await adapter.send_context_card(sample_context_card)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_with_custom_webhook_url(
        self, teams_adapter, sample_context_card
    ):
        """Test sending to a custom webhook URL."""
        custom_url = "https://outlook.office.com/webhook/custom-url"

        with patch("src.integrations.teams.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = AsyncMock()
            mock_response.raise_for_status = lambda: None
            mock_client.post.return_value = mock_response

            result = await teams_adapter.send_context_card(
                sample_context_card, webhook_url=custom_url
            )

            assert result is True
            call_args = mock_client.post.call_args
            assert call_args[0][0] == custom_url

    @pytest.mark.asyncio
    async def test_send_timeout_handling(self, teams_adapter, sample_context_card):
        """Test handling of timeout errors."""
        with patch("src.integrations.teams.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.TimeoutException(
                "Connection timed out"
            )

            result = await teams_adapter.send_context_card(sample_context_card)

            assert result is False


class TestTeamsAdapterEdgeCases:
    """Test edge cases and error handling."""

    def test_long_title_truncation(self, teams_adapter):
        """Test that long titles are truncated."""
        long_title = "A" * 200
        card = ContextCard(
            incident_id="test",
            title=long_title,
            severity=Severity.MEDIUM,
            service_name="test-service",
            triggered_at=datetime.now(),
        )

        result = teams_adapter._build_adaptive_card(card)
        content = result["attachments"][0]["content"]
        header = content["body"][0]

        # Title should be truncated to 100 chars
        assert len(header["text"]) < 200

    def test_long_explanation_truncation(self, teams_adapter):
        """Test that long explanations are truncated."""
        long_explanation = "X" * 500
        card = ContextCard(
            incident_id="test",
            title="Test",
            severity=Severity.MEDIUM,
            service_name="test-service",
            triggered_at=datetime.now(),
            ai_summary=AILogSummary(
                top_issues=["Issue 1"],
                explanation=long_explanation,
            ),
        )

        result = teams_adapter._build_adaptive_card(card)
        content = result["attachments"][0]["content"]

        # Find AI section and verify truncation
        for element in content["body"]:
            if element.get("type") == "TextBlock" and "AI Analysis" in element.get(
                "text", ""
            ):
                assert "..." in element["text"]
                assert len(element["text"]) < 500
                break

    def test_empty_owners_list(self, teams_adapter, minimal_context_card):
        """Test handling of empty owners list."""
        card = teams_adapter._build_adaptive_card(minimal_context_card)
        content = card["attachments"][0]["content"]

        # Should not have owners section
        for element in content["body"]:
            if element.get("type") == "TextBlock":
                assert (
                    "Owners:" not in element.get("text", "")
                    or minimal_context_card.owners
                )

    def test_unicode_handling(self, teams_adapter):
        """Test that unicode characters are handled correctly."""
        card = ContextCard(
            incident_id="test",
            title="Service failure 🔥 très importante",
            severity=Severity.HIGH,
            service_name="test-service",
            triggered_at=datetime.now(),
        )

        result = teams_adapter._build_adaptive_card(card)
        content = result["attachments"][0]["content"]
        header = content["body"][0]

        assert "🔥" in header["text"]
        assert "très" in header["text"]
