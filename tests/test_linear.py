"""Tests for Linear integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.linear import (
    LinearClient,
    LinearCreateIssueRequest,
    LinearIssue,
    LinearPriority,
    LinearWorkflowState,
    _severity_to_priority,
    create_incident_ticket,
    transition_issue_status,
    update_incident_resolved,
)


@pytest.fixture
def mock_settings():
    """Create mock settings with Linear config."""
    settings = MagicMock()
    settings.linear_api_key = "lin_api_test123"
    settings.linear_team_id = "team-123"
    settings.linear_label_ids = ["label-1", "label-2"]
    return settings


@pytest.fixture
def linear_client(mock_settings):
    """Create a Linear client with mocked settings."""
    with patch("src.integrations.linear.get_settings", return_value=mock_settings):
        client = LinearClient()
        yield client


class TestLinearClient:
    """Tests for LinearClient class."""

    def test_is_configured_true(self, linear_client):
        """Client should be configured when API key is present."""
        assert linear_client.is_configured is True

    def test_is_configured_false_missing_key(self, mock_settings):
        """Client should not be configured without API key."""
        mock_settings.linear_api_key = ""
        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            client = LinearClient()
            assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_create_issue_success(self, linear_client):
        """Should create issue successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "issue-123",
                        "identifier": "ENG-456",
                        "title": "Test incident",
                        "url": "https://linear.app/team/issue/ENG-456",
                        "state": {"name": "Triage"},
                        "priority": 2,
                    },
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            request = LinearCreateIssueRequest(
                team_id="team-123",
                title="Test incident",
                description="Test description",
            )

            issue = await linear_client.create_issue(request)

            assert issue.id == "issue-123"
            assert issue.identifier == "ENG-456"
            assert issue.state == "Triage"
            mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_issue_with_priority(self, linear_client):
        """Should include priority when specified."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issueCreate": {
                    "success": True,
                    "issue": {
                        "id": "issue-124",
                        "identifier": "ENG-457",
                        "title": "High priority incident",
                        "url": "https://linear.app/team/issue/ENG-457",
                        "state": {"name": "Triage"},
                        "priority": 1,
                    },
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            request = LinearCreateIssueRequest(
                team_id="team-123",
                title="High priority incident",
                description="Urgent issue",
                priority=LinearPriority.URGENT.value,
            )

            await linear_client.create_issue(request)

            call_args = mock_http_client.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["variables"]["input"]["priority"] == 1

    @pytest.mark.asyncio
    async def test_create_issue_not_configured(self):
        """Should raise error when not configured."""
        mock_settings = MagicMock()
        mock_settings.linear_api_key = ""
        mock_settings.linear_team_id = ""
        mock_settings.linear_label_ids = []

        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            client = LinearClient()

            request = LinearCreateIssueRequest(
                team_id="test-team",
                title="Test",
                description="Test",
            )

            with pytest.raises(ValueError, match="not configured"):
                await client.create_issue(request)

    @pytest.mark.asyncio
    async def test_create_issue_graphql_error(self, linear_client):
        """Should raise error on GraphQL errors."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"errors": [{"message": "Team not found"}]}
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            request = LinearCreateIssueRequest(team_id="invalid-team", title="Test")

            with pytest.raises(ValueError, match="Team not found"):
                await linear_client.create_issue(request)

    @pytest.mark.asyncio
    async def test_get_issue(self, linear_client):
        """Should fetch issue details."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issue": {
                    "id": "issue-123",
                    "identifier": "ENG-456",
                    "title": "Test incident",
                    "url": "https://linear.app/team/issue/ENG-456",
                    "state": {"name": "In Progress"},
                    "priority": 2,
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            issue = await linear_client.get_issue("ENG-456")

            assert issue.identifier == "ENG-456"
            assert issue.state == "In Progress"

    @pytest.mark.asyncio
    async def test_update_issue(self, linear_client):
        """Should update issue successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issueUpdate": {
                    "success": True,
                    "issue": {
                        "id": "issue-123",
                        "identifier": "ENG-456",
                        "title": "Test incident",
                        "url": "https://linear.app/team/issue/ENG-456",
                        "state": {"name": "Done"},
                        "priority": 2,
                    },
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            issue = await linear_client.update_issue("issue-123", state_id="state-done")

            assert issue.state == "Done"

    @pytest.mark.asyncio
    async def test_add_comment(self, linear_client):
        """Should add comment to issue."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "commentCreate": {
                    "success": True,
                    "comment": {
                        "id": "comment-1",
                        "body": "Test comment",
                        "createdAt": "2024-01-01T00:00:00Z",
                    },
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            comment = await linear_client.add_comment("issue-123", "Test comment")

            assert comment.id == "comment-1"
            assert comment.body == "Test comment"

    @pytest.mark.asyncio
    async def test_get_workflow_states(self, linear_client):
        """Should fetch workflow states for team."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "team": {
                    "states": {
                        "nodes": [
                            {"id": "state-1", "name": "Triage", "type": "triage"},
                            {"id": "state-2", "name": "In Progress", "type": "started"},
                            {"id": "state-3", "name": "Done", "type": "completed"},
                        ]
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            states = await linear_client.get_workflow_states("team-123")

            assert len(states) == 3
            assert states[0].name == "Triage"
            assert states[2].type == "completed"

    @pytest.mark.asyncio
    async def test_get_workflow_states_no_team_id(self):
        """Should raise error when no team ID provided."""
        mock_settings = MagicMock()
        mock_settings.linear_api_key = "test-key"
        mock_settings.linear_team_id = ""
        mock_settings.linear_label_ids = []

        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            client = LinearClient()

            with pytest.raises(ValueError, match="Team ID required"):
                await client.get_workflow_states()

    @pytest.mark.asyncio
    async def test_link_issues(self, linear_client):
        """Should link two issues together."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"issueRelationCreate": {"success": True}}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            await linear_client.link_issues("issue-1", "issue-2")

            mock_http_client.post.assert_called_once()
            call_args = mock_http_client.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["variables"]["input"]["issueId"] == "issue-1"
            assert payload["variables"]["input"]["relatedIssueId"] == "issue-2"

    @pytest.mark.asyncio
    async def test_search_issues(self, linear_client):
        """Should search issues."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-1",
                            "identifier": "ENG-1",
                            "title": "Test issue 1",
                            "url": "https://linear.app/team/issue/ENG-1",
                            "state": {"name": "Open"},
                            "priority": 3,
                        },
                        {
                            "id": "issue-2",
                            "identifier": "ENG-2",
                            "title": "Test issue 2",
                            "url": "https://linear.app/team/issue/ENG-2",
                            "state": {"name": "Done"},
                            "priority": 4,
                        },
                    ]
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            issues = await linear_client.search_issues("Test")

            assert len(issues) == 2
            assert issues[0].identifier == "ENG-1"

    @pytest.mark.asyncio
    async def test_get_labels(self, linear_client):
        """Should fetch labels for team."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "team": {
                    "labels": {
                        "nodes": [
                            {"id": "label-1", "name": "bug", "color": "#FF0000"},
                            {"id": "label-2", "name": "incident", "color": "#FFA500"},
                        ]
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(linear_client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post.return_value = mock_response
            mock_get_client.return_value = mock_http_client

            labels = await linear_client.get_labels("team-123")

            assert len(labels) == 2
            assert labels[0].name == "bug"
            assert labels[1].color == "#FFA500"


class TestSeverityToPriority:
    """Tests for severity to priority mapping."""

    def test_sev1_maps_to_urgent(self):
        assert _severity_to_priority("SEV1") == LinearPriority.URGENT.value

    def test_critical_maps_to_urgent(self):
        assert _severity_to_priority("CRITICAL") == LinearPriority.URGENT.value

    def test_high_maps_to_high(self):
        assert _severity_to_priority("HIGH") == LinearPriority.HIGH.value

    def test_sev2_maps_to_high(self):
        assert _severity_to_priority("SEV2") == LinearPriority.HIGH.value

    def test_medium_maps_to_normal(self):
        assert _severity_to_priority("MEDIUM") == LinearPriority.NORMAL.value

    def test_low_maps_to_low(self):
        assert _severity_to_priority("LOW") == LinearPriority.LOW.value

    def test_unknown_maps_to_normal(self):
        assert _severity_to_priority("UNKNOWN") == LinearPriority.NORMAL.value

    def test_case_insensitive(self):
        assert _severity_to_priority("high") == LinearPriority.HIGH.value
        assert _severity_to_priority("High") == LinearPriority.HIGH.value


class TestCreateIncidentTicket:
    """Tests for create_incident_ticket function."""

    @pytest.mark.asyncio
    async def test_creates_ticket_with_full_context(self, mock_settings):
        """Should create ticket with all context."""
        mock_issue = LinearIssue(
            id="issue-100",
            identifier="ENG-100",
            title="Test incident",
            url="https://linear.app/team/issue/ENG-100",
        )

        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_team_id = "team-123"
                mock_client.default_label_ids = ["label-1"]
                mock_client.create_issue = AsyncMock(return_value=mock_issue)
                mock_get_client.return_value = mock_client

                issue = await create_incident_ticket(
                    service_name="payments-api",
                    alert_summary="High error rate",
                    severity="HIGH",
                    context_card_url="https://slack.com/card/123",
                    deployments=[{"sha": "abc1234", "author": "dev", "message": "Fix bug"}],
                    log_summary="Multiple timeout errors detected",
                    similar_incidents=[{"title": "Past incident", "score": 0.85}],
                    runbook_url="https://wiki.example.com/runbook",
                )

                assert issue is not None
                assert issue.identifier == "ENG-100"
                mock_client.create_issue.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_configured(self):
        """Should return None when Linear is not configured."""
        mock_settings = MagicMock()
        mock_settings.linear_api_key = ""
        mock_settings.linear_team_id = ""
        mock_settings.linear_label_ids = []

        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
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
    async def test_returns_none_when_no_team_id(self, mock_settings):
        """Should return None when no team ID configured."""
        mock_settings.linear_team_id = ""

        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_team_id = ""
                mock_get_client.return_value = mock_client

                issue = await create_incident_ticket(
                    service_name="test",
                    alert_summary="test",
                    severity="LOW",
                )

                assert issue is None

    @pytest.mark.asyncio
    async def test_severity_to_priority_mapping(self, mock_settings):
        """Should map severity to Linear priority correctly."""
        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_team_id = "team-123"
                mock_client.default_label_ids = []
                mock_client.create_issue = AsyncMock(
                    return_value=LinearIssue(
                        id="test-1",
                        identifier="ENG-1",
                        title="Test",
                        url="https://linear.app/test",
                    )
                )
                mock_get_client.return_value = mock_client

                await create_incident_ticket(
                    service_name="test",
                    alert_summary="test",
                    severity="SEV1",
                )

                call_args = mock_client.create_issue.call_args
                request = call_args[0][0]
                assert request.priority == LinearPriority.URGENT.value


class TestUpdateIncidentResolved:
    """Tests for update_incident_resolved function."""

    @pytest.mark.asyncio
    async def test_adds_comment_and_transitions(self, mock_settings):
        """Should add comment and transition issue."""
        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_team_id = "team-123"
                mock_client.add_comment = AsyncMock()
                mock_client.get_workflow_states = AsyncMock(
                    return_value=[
                        LinearWorkflowState(id="1", name="In Progress", type="started"),
                        LinearWorkflowState(id="2", name="Done", type="completed"),
                    ]
                )
                mock_client.update_issue = AsyncMock()
                mock_get_client.return_value = mock_client

                await update_incident_resolved(
                    issue_id="issue-123",
                    resolution_summary="Fixed the bug",
                    resolved_by="engineer@example.com",
                )

                mock_client.add_comment.assert_called_once()
                mock_client.update_issue.assert_called_once_with("issue-123", state_id="2")

    @pytest.mark.asyncio
    async def test_skips_when_not_configured(self):
        """Should skip when Linear is not configured."""
        mock_settings = MagicMock()
        mock_settings.linear_api_key = ""
        mock_settings.linear_team_id = ""
        mock_settings.linear_label_ids = []

        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = False
                mock_get_client.return_value = mock_client

                await update_incident_resolved(
                    issue_id="TEST-1",
                    resolution_summary="Fixed",
                )


class TestTransitionIssueStatus:
    """Tests for transition_issue_status function."""

    @pytest.mark.asyncio
    async def test_transitions_to_target_status(self, mock_settings):
        """Should transition issue to target status."""
        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_team_id = "team-123"
                mock_client.get_workflow_states = AsyncMock(
                    return_value=[
                        LinearWorkflowState(id="1", name="Triage", type="triage"),
                        LinearWorkflowState(id="2", name="In Progress", type="started"),
                        LinearWorkflowState(id="3", name="Done", type="completed"),
                    ]
                )
                mock_client.update_issue = AsyncMock(
                    return_value=LinearIssue(
                        id="issue-123",
                        identifier="ENG-123",
                        title="Test",
                        url="https://linear.app/test",
                        state="In Progress",
                    )
                )
                mock_client.add_comment = AsyncMock()
                mock_get_client.return_value = mock_client

                issue = await transition_issue_status(
                    issue_id="issue-123",
                    status="In Progress",
                    comment="Starting work on this",
                )

                assert issue is not None
                assert issue.state == "In Progress"
                mock_client.update_issue.assert_called_once_with("issue-123", state_id="2")
                mock_client.add_comment.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_status_not_found(self, mock_settings):
        """Should return None when target status not found."""
        with patch("src.integrations.linear.get_settings", return_value=mock_settings):
            with patch("src.integrations.linear.get_linear_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.is_configured = True
                mock_client.default_team_id = "team-123"
                mock_client.get_workflow_states = AsyncMock(
                    return_value=[
                        LinearWorkflowState(id="1", name="Triage", type="triage"),
                        LinearWorkflowState(id="2", name="Done", type="completed"),
                    ]
                )
                mock_get_client.return_value = mock_client

                issue = await transition_issue_status(
                    issue_id="issue-123",
                    status="Non-Existent Status",
                )

                assert issue is None
