"""Tests for GitLab integration."""

import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.gitlab import GitLabAdapter
from src.models import Deployment, GitLabContext, MergeRequest, Pipeline


@pytest.fixture
def mock_settings():
    """Create mock settings with GitLab config."""
    settings = MagicMock()
    settings.gitlab_token = "test-token"
    settings.gitlab_url = "https://gitlab.example.com"
    settings.gitlab_project_map = {
        "payments-api": "mygroup/payments",
        "auth-service": "mygroup/subgroup/auth",
    }
    return settings


@pytest.fixture
def gitlab_adapter(mock_settings):
    """Create a GitLab adapter with mocked settings."""
    return GitLabAdapter(mock_settings)


class TestGitLabAdapter:
    """Tests for GitLabAdapter class."""

    def test_init_with_settings(self, gitlab_adapter, mock_settings):
        """Adapter should initialize with settings."""
        assert gitlab_adapter.token == "test-token"
        assert gitlab_adapter.base_url == "https://gitlab.example.com"
        assert gitlab_adapter.project_map == mock_settings.gitlab_project_map

    def test_init_with_default_url(self):
        """Adapter should use gitlab.com by default."""
        settings = MagicMock()
        settings.gitlab_token = "token"
        settings.gitlab_url = ""
        settings.gitlab_project_map = {}

        adapter = GitLabAdapter(settings)
        assert adapter.base_url == "https://gitlab.com"

    def test_api_url(self, gitlab_adapter):
        """API URL should be correctly constructed."""
        assert gitlab_adapter.api_url == "https://gitlab.example.com/api/v4"

    def test_get_headers(self, gitlab_adapter):
        """Headers should include auth token."""
        headers = gitlab_adapter._get_headers()
        assert headers["PRIVATE-TOKEN"] == "test-token"
        assert headers["Accept"] == "application/json"

    def test_get_project_for_service_with_mapping(self, gitlab_adapter):
        """Should return mapped project for known service."""
        project = gitlab_adapter._get_project_for_service("payments-api")
        assert project == "mygroup/payments"

    def test_get_project_for_service_subgroup(self, gitlab_adapter):
        """Should handle subgroups in project path."""
        project = gitlab_adapter._get_project_for_service("auth-service")
        assert project == "mygroup/subgroup/auth"

    def test_get_project_for_service_unknown(self, gitlab_adapter):
        """Should return None for unknown service."""
        project = gitlab_adapter._get_project_for_service("unknown-service")
        assert project is None

    def test_encode_project_path(self, gitlab_adapter):
        """Should URL-encode project path."""
        encoded = gitlab_adapter._encode_project_path("group/subgroup/project")
        assert encoded == "group%2Fsubgroup%2Fproject"

    def test_parse_codeowners(self, gitlab_adapter):
        """Should parse CODEOWNERS file."""
        content = """
# Global owners
* @global-team

# Frontend
/frontend/ @frontend-team @designer

# Backend
/backend/ @backend-team
"""
        owners = gitlab_adapter._parse_codeowners(content)
        assert "@global-team" in owners
        assert "@frontend-team" in owners
        assert "@designer" in owners
        assert "@backend-team" in owners
        assert len(owners) == 4


class TestGitLabAdapterFetchCommits:
    """Tests for fetching commits."""

    @pytest.mark.asyncio
    async def test_fetch_recent_commits_success(self, gitlab_adapter):
        """Should fetch and parse commits."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "abc123def456",
                "author_name": "Developer",
                "title": "Fix payment processing bug",
                "committed_date": "2025-01-15T10:30:00Z",
                "web_url": "https://gitlab.example.com/mygroup/payments/-/commit/abc123",
            },
            {
                "id": "def456abc789",
                "author_name": "Another Dev",
                "title": "Update dependencies",
                "committed_date": "2025-01-15T09:00:00Z",
                "web_url": "https://gitlab.example.com/mygroup/payments/-/commit/def456",
            },
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            deploys = await gitlab_adapter._fetch_recent_commits(
                mock_client, "mygroup/payments", 24
            )

            assert len(deploys) == 2
            assert deploys[0].short_sha == "abc123d"
            assert deploys[0].author == "Developer"
            assert deploys[0].message == "Fix payment processing bug"

    @pytest.mark.asyncio
    async def test_fetch_recent_commits_not_found(self, gitlab_adapter):
        """Should return empty list for missing project."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            deploys = await gitlab_adapter._fetch_recent_commits(
                mock_client, "nonexistent/project", 24
            )

            assert deploys == []


class TestGitLabAdapterFetchMergeRequests:
    """Tests for fetching merge requests."""

    @pytest.mark.asyncio
    async def test_fetch_recent_mrs_success(self, gitlab_adapter):
        """Should fetch and parse merge requests."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "iid": 123,
                "title": "Add new payment method",
                "author": {"username": "dev1"},
                "merged_at": "2025-01-15T11:00:00Z",
                "web_url": "https://gitlab.example.com/mygroup/payments/-/merge_requests/123",
                "labels": ["feature", "payments"],
            },
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mrs = await gitlab_adapter._fetch_recent_merge_requests(
                mock_client, "mygroup/payments", 24
            )

            assert len(mrs) == 1
            assert mrs[0].iid == 123
            assert mrs[0].title == "Add new payment method"
            assert mrs[0].author == "dev1"
            assert "feature" in mrs[0].labels


class TestGitLabAdapterFetchPipelines:
    """Tests for fetching pipelines."""

    @pytest.mark.asyncio
    async def test_fetch_recent_pipelines_success(self, gitlab_adapter):
        """Should fetch and parse pipelines."""
        now = datetime.now(timezone.utc)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 456,
                "status": "success",
                "ref": "main",
                "sha": "abc123def456",
                "created_at": now.isoformat(),
                "web_url": "https://gitlab.example.com/mygroup/payments/-/pipelines/456",
            },
            {
                "id": 455,
                "status": "failed",
                "ref": "feature-branch",
                "sha": "def456abc789",
                "created_at": (now - timedelta(hours=1)).isoformat(),
                "web_url": "https://gitlab.example.com/mygroup/payments/-/pipelines/455",
            },
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            pipelines = await gitlab_adapter._fetch_recent_pipelines(
                mock_client, "mygroup/payments", 24
            )

            assert len(pipelines) == 2
            assert pipelines[0].id == 456
            assert pipelines[0].status == "success"
            assert pipelines[0].ref == "main"
            assert pipelines[1].status == "failed"


class TestGitLabAdapterFetchCodeowners:
    """Tests for fetching CODEOWNERS."""

    @pytest.mark.asyncio
    async def test_fetch_codeowners_success(self, gitlab_adapter):
        """Should fetch and parse CODEOWNERS."""
        content = "* @team-leads\n/src/ @dev-team"
        encoded_content = base64.b64encode(content.encode()).decode()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": encoded_content}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            owners = await gitlab_adapter._fetch_codeowners(
                mock_client, "mygroup/payments"
            )

            assert "@team-leads" in owners
            assert "@dev-team" in owners

    @pytest.mark.asyncio
    async def test_fetch_codeowners_not_found(self, gitlab_adapter):
        """Should return empty list if CODEOWNERS not found."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            owners = await gitlab_adapter._fetch_codeowners(
                mock_client, "mygroup/payments"
            )

            assert owners == []


class TestGitLabAdapterGetContext:
    """Tests for the main get_context method."""

    @pytest.mark.asyncio
    async def test_get_context_success(self, gitlab_adapter):
        """Should return full GitLab context."""
        now = datetime.now(timezone.utc)

        with patch.object(gitlab_adapter, "_fetch_recent_commits") as mock_commits:
            with patch.object(
                gitlab_adapter, "_fetch_recent_merge_requests"
            ) as mock_mrs:
                with patch.object(
                    gitlab_adapter, "_fetch_recent_pipelines"
                ) as mock_pipelines:
                    with patch.object(
                        gitlab_adapter, "_fetch_codeowners"
                    ) as mock_owners:
                        mock_commits.return_value = [
                            Deployment(
                                sha="abc123",
                                short_sha="abc123",
                                author="dev",
                                message="Fix bug",
                                timestamp=now,
                            )
                        ]
                        mock_mrs.return_value = [
                            MergeRequest(
                                iid=1,
                                title="Add feature",
                                author="dev",
                                merged_at=now,
                            )
                        ]
                        mock_pipelines.return_value = [
                            Pipeline(
                                id=1,
                                status="success",
                                ref="main",
                                sha="abc123",
                                created_at=now,
                            )
                        ]
                        mock_owners.return_value = ["@team"]

                        ctx = await gitlab_adapter.get_context("payments-api")

                        assert ctx is not None
                        assert ctx.project == "mygroup/payments"
                        assert len(ctx.recent_deploys) == 1
                        assert len(ctx.merge_requests) == 1
                        assert len(ctx.pipelines) == 1
                        assert "@team" in ctx.codeowners

    @pytest.mark.asyncio
    async def test_get_context_no_token(self):
        """Should return None if token not configured."""
        settings = MagicMock()
        settings.gitlab_token = ""
        settings.gitlab_url = "https://gitlab.com"
        settings.gitlab_project_map = {}

        adapter = GitLabAdapter(settings)
        ctx = await adapter.get_context("some-service")

        assert ctx is None

    @pytest.mark.asyncio
    async def test_get_context_no_mapping(self, gitlab_adapter):
        """Should return None if service not mapped."""
        ctx = await gitlab_adapter.get_context("unmapped-service")

        assert ctx is None

    @pytest.mark.asyncio
    async def test_get_context_handles_errors(self, gitlab_adapter):
        """Should return None on API errors."""
        with patch.object(gitlab_adapter, "_fetch_recent_commits") as mock_commits:
            mock_commits.side_effect = httpx.RequestError("Connection failed")

            ctx = await gitlab_adapter.get_context("payments-api")

            assert ctx is None


class TestGitLabAdapterGetProjectInfo:
    """Tests for get_project_info method."""

    @pytest.mark.asyncio
    async def test_get_project_info_success(self, gitlab_adapter):
        """Should return project info."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 123,
            "name": "payments",
            "path_with_namespace": "mygroup/payments",
            "default_branch": "main",
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            info = await gitlab_adapter.get_project_info("mygroup/payments")

            assert info is not None
            assert info["name"] == "payments"
            assert info["default_branch"] == "main"

    @pytest.mark.asyncio
    async def test_get_project_info_no_token(self):
        """Should return None if token not configured."""
        settings = MagicMock()
        settings.gitlab_token = ""
        settings.gitlab_url = "https://gitlab.com"
        settings.gitlab_project_map = {}

        adapter = GitLabAdapter(settings)
        info = await adapter.get_project_info("mygroup/payments")

        assert info is None


class TestSelfHostedGitLab:
    """Tests for self-hosted GitLab instances."""

    def test_custom_url_handling(self):
        """Should handle custom GitLab URLs."""
        settings = MagicMock()
        settings.gitlab_token = "token"
        settings.gitlab_url = "https://gitlab.company.internal/"
        settings.gitlab_project_map = {}

        adapter = GitLabAdapter(settings)

        assert adapter.base_url == "https://gitlab.company.internal"
        assert adapter.api_url == "https://gitlab.company.internal/api/v4"

    def test_url_without_trailing_slash(self):
        """Should handle URLs without trailing slash."""
        settings = MagicMock()
        settings.gitlab_token = "token"
        settings.gitlab_url = "https://git.example.com"
        settings.gitlab_project_map = {}

        adapter = GitLabAdapter(settings)

        assert adapter.base_url == "https://git.example.com"
        assert adapter.api_url == "https://git.example.com/api/v4"
