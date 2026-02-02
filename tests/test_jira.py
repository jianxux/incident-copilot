"""Tests for Jira integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.jira import (
    JiraClient,
    JiraCreateIssueRequest,
    JiraIssue,
    JiraTransition,
    create_incident_ticket,
    get_jira_client,
    update_incident_resolved,
)


@pytest.fixture
def mock_settings():
    """Create mock settings with Jira config."""
    settings = MagicMock()
    settings.jira_base_url = "https://test.atlassian.net"
    settings.jira_email = "test@example.com"
    settings.jira_api_token = "test-token"
    settings.jira_default_project = "INCIDENT"
    return settings


@pytest.fixture
def jira_client(mock_settings):
    """Create a Jira client with mocked settings."""
    with patch("src.integrations.jira.get_settings", return_value=mock_settings):
        client = JiraClient()
        yield client


class TestJiraClient:
    """Tests for JiraClient class."""

    def test_is_configured_true(self, jira_client):
        """Client should be configured when all settings present."""
        assert jira_client.is_configured is True

    def test_is_configured_false_missing_url(self, mock_settings):
        """Client should not be configured without base URL."""
        mock_settings.jira_base_url = ""
        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            client = JiraClient()
            assert client.is_configured is False

    def test_is_configured_false_missing_token(self, mock_settings):
        """Client should not be configured without API token."""
        mock_settings.jira_api_token = ""
        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            client = JiraClient()
            assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_create_issue_success(self, jira_client):
        """Should create issue successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "key": "INCIDENT-123",
            "id": "10001",
            "self": "https://test.atlassian.net/rest/api/3/issue/10001",
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(jira_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            request = JiraCreateIssueRequest(
                project_key="INCIDENT",
                summary="Test incident",
                description="Test description",
            )

            issue = await jira_client.create_issue(request)

            assert issue.key == "INCIDENT-123"
            assert issue.id == "10001"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_issue_with_priority(self, jira_client):
        """Should include priority when specified."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "key": "INCIDENT-124",
            "id": "10002",
            "self": "https://test.atlassian.net/rest/api/3/issue/10002",
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(jira_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            request = JiraCreateIssueRequest(
                project_key="INCIDENT",
                summary="High priority incident",
                description="Urgent issue",
                priority="High",
            )

            await jira_client.create_issue(request)

            # Verify priority was included in the payload
            call_args = mock_client.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["fields"]["priority"] == {"name": "High"}

    @pytest.mark.asyncio
    async def test_create_issue_not_configured(self):
        """Should raise error when not configured."""
        mock_settings = MagicMock()
        mock_settings.jira_base_url = ""
        mock_settings.jira_email = ""
        mock_settings.jira_api_token = ""
        mock_settings.jira_default_project = ""

        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            client = JiraClient()

            request = JiraCreateIssueRequest(
                project_key="TEST",
                summary="Test",
                description="Test",
            )

            with pytest.raises(ValueError, match="not configured"):
                await client.create_issue(request)

    @pytest.mark.asyncio
    async def test_get_issue(self, jira_client):
        """Should fetch issue details."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "key": "INCIDENT-123",
            "id": "10001",
            "self": "https://test.atlassian.net/rest/api/3/issue/10001",
            "fields": {
                "summary": "Test incident",
                "status": {"name": "In Progress"},
            },
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(jira_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            issue = await jira_client.get_issue("INCIDENT-123")

            assert issue.key == "INCIDENT-123"
            assert issue.summary == "Test incident"
            assert issue.status == "In Progress"

    @pytest.mark.asyncio
    async def test_add_comment(self, jira_client):
        """Should add comment to issue."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "comment-1"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(jira_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await jira_client.add_comment("INCIDENT-123", "Test comment")

            assert result["id"] == "comment-1"
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transitions(self, jira_client):
        """Should fetch available transitions."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "transitions": [
                {"id": "1", "name": "In Progress"},
                {"id": "2", "name": "Done"},
                {"id": "3", "name": "Closed"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(jira_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            transitions = await jira_client.get_transitions("INCIDENT-123")

            assert len(transitions) == 3
            assert transitions[0].name == "In Progress"
            assert transitions[1].name == "Done"

    @pytest.mark.asyncio
    async def test_transition_issue(self, jira_client):
        """Should transition issue to new status."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch.object(jira_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            await jira_client.transition_issue("INCIDENT-123", "2")

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_issues(self, jira_client):
        """Should search issues using JQL."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "issues": [
                {
                    "key": "INCIDENT-1",
                    "id": "1",
                    "self": "url1",
                    "fields": {"summary": "Issue 1", "status": {"name": "Open"}},
                },
                {
                    "key": "INCIDENT-2",
                    "id": "2",
                    "self": "url2",
                    "fields": {"summary": "Issue 2", "status": {"name": "Done"}},
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(jira_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            issues = await jira_client.search_issues(
                'project = INCIDENT AND status = "Open"'
            )

            assert len(issues) == 2
            assert issues[0].key == "INCIDENT-1"


class TestCreateIncidentTicket:
    """Tests for create_incident_ticket function."""

    @pytest.mark.asyncio
    async def test_creates_ticket_with_full_context(self, mock_settings):
        """Should create ticket with all context."""
        mock_issue = JiraIssue(
            key="INCIDENT-100",
            id="100",
            self_url="https://test.atlassian.net/rest/api/3/issue/100",
        )

        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            with patch("src.integrations.jira.get_jira_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_project = "INCIDENT"
                mock_client.create_issue = AsyncMock(return_value=mock_issue)
                mock_get_client.return_value = mock_client

                issue = await create_incident_ticket(
                    service_name="payments-api",
                    alert_summary="High error rate",
                    severity="HIGH",
                    context_card_url="https://slack.com/card/123",
                    deployments=[
                        {"sha": "abc1234", "author": "dev", "message": "Fix bug"}
                    ],
                    log_summary="Multiple timeout errors detected",
                    similar_incidents=[{"title": "Past incident", "score": 0.85}],
                    runbook_url="https://wiki.example.com/runbook",
                )

                assert issue is not None
                assert issue.key == "INCIDENT-100"
                mock_client.create_issue.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_configured(self):
        """Should return None when Jira is not configured."""
        mock_settings = MagicMock()
        mock_settings.jira_base_url = ""
        mock_settings.jira_email = ""
        mock_settings.jira_api_token = ""
        mock_settings.jira_default_project = ""

        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            with patch("src.integrations.jira.get_jira_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = False
                mock_get_client.return_value = mock_client

                issue = await create_incident_ticket(
                    service_name="test",
                    alert_summary="test",
                    severity="LOW",
                )

                assert issue is None

    @pytest.mark.asyncio
    async def test_severity_to_priority_mapping(self, mock_settings):
        """Should map severity to Jira priority correctly."""
        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            with patch("src.integrations.jira.get_jira_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_project = "INCIDENT"
                mock_client.create_issue = AsyncMock(
                    return_value=JiraIssue(key="TEST-1", id="1", self_url="url")
                )
                mock_get_client.return_value = mock_client

                # Test SEV1 -> Highest
                await create_incident_ticket(
                    service_name="test",
                    alert_summary="test",
                    severity="SEV1",
                )

                call_args = mock_client.create_issue.call_args
                request = call_args[0][0]
                assert request.priority == "Highest"


class TestUpdateIncidentResolved:
    """Tests for update_incident_resolved function."""

    @pytest.mark.asyncio
    async def test_adds_comment_and_transitions(self, mock_settings):
        """Should add comment and transition issue."""
        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            with patch("src.integrations.jira.get_jira_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.add_comment = AsyncMock()
                mock_client.get_transitions = AsyncMock(
                    return_value=[
                        JiraTransition(id="1", name="In Progress"),
                        JiraTransition(id="2", name="Done"),
                    ]
                )
                mock_client.transition_issue = AsyncMock()
                mock_get_client.return_value = mock_client

                await update_incident_resolved(
                    issue_key="INCIDENT-123",
                    resolution_summary="Fixed the bug",
                    resolved_by="engineer@example.com",
                )

                mock_client.add_comment.assert_called_once()
                mock_client.transition_issue.assert_called_once_with(
                    "INCIDENT-123", "2"
                )

    @pytest.mark.asyncio
    async def test_skips_when_not_configured(self):
        """Should skip when Jira is not configured."""
        mock_settings = MagicMock()
        mock_settings.jira_base_url = ""
        mock_settings.jira_email = ""
        mock_settings.jira_api_token = ""
        mock_settings.jira_default_project = ""

        with patch("src.integrations.jira.get_settings", return_value=mock_settings):
            with patch("src.integrations.jira.get_jira_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = False
                mock_get_client.return_value = mock_client

                # Should not raise, just return
                await update_incident_resolved(
                    issue_key="TEST-1",
                    resolution_summary="Fixed",
                )
