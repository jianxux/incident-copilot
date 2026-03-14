"""Tests for GitHub credential resolution from DB integration_configs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.integrations.github import GitHubAdapter, resolve_github_credentials


@pytest.fixture
def settings_no_github():
    """Settings with no GitHub env vars configured."""
    settings = MagicMock(spec=Settings)
    settings.github_token = ""
    settings.github_org = ""
    settings.service_repo_map = {}
    return settings


@pytest.fixture
def settings_with_github():
    """Settings with GitHub env vars configured."""
    settings = MagicMock(spec=Settings)
    settings.github_token = "ghp_env_token"
    settings.github_org = "my-org"
    settings.service_repo_map = {}
    return settings


def _mock_supabase_db(result_data):
    """Create a mock DB that returns the given data from _to_thread."""
    mock_result = MagicMock()
    mock_result.data = result_data
    mock_db = MagicMock()
    mock_db._to_thread = AsyncMock(return_value=mock_result)
    return mock_db


class TestResolveGitHubCredentials:
    """Test resolve_github_credentials helper."""

    @pytest.mark.asyncio
    async def test_returns_env_vars_when_set(self, settings_with_github):
        token, org = await resolve_github_credentials(
            settings_with_github, tenant_id="t1"
        )
        assert token == "ghp_env_token"
        assert org == "my-org"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tenant(self, settings_no_github):
        token, org = await resolve_github_credentials(
            settings_no_github, tenant_id=None
        )
        assert token == ""
        assert org == ""

    @pytest.mark.asyncio
    async def test_reads_from_db_when_no_env_vars(self, settings_no_github):
        mock_db = _mock_supabase_db([{"config": {"encrypted": "encrypted_blob"}}])

        mock_get_db = MagicMock(return_value=mock_db)
        mock_decrypt = MagicMock(
            return_value={"token": "ghp_db_token", "org": "db-org"}
        )

        with (
            patch(
                "src.integrations.github.get_settings", return_value=settings_no_github
            ),
            patch("src.integrations.github.is_supabase_db_enabled", return_value=True),
            patch("src.integrations.github.get_db", mock_get_db),
            patch("src.integrations.github.decrypt_json", mock_decrypt),
        ):
            token, org = await resolve_github_credentials(
                settings_no_github, tenant_id="tenant-1"
            )

        assert token == "ghp_db_token"
        assert org == "db-org"
        mock_get_db.assert_called_once_with(use_admin=True)
        mock_decrypt.assert_called_once_with("encrypted_blob")

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_db_config(self, settings_no_github):
        mock_db = _mock_supabase_db([])

        with (
            patch(
                "src.integrations.github.get_settings", return_value=settings_no_github
            ),
            patch("src.integrations.github.is_supabase_db_enabled", return_value=True),
            patch("src.integrations.github.get_db", return_value=mock_db),
        ):
            token, org = await resolve_github_credentials(
                settings_no_github, tenant_id="tenant-1"
            )
            assert token == ""
            assert org == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_supabase_disabled(self, settings_no_github):
        with (
            patch(
                "src.integrations.github.get_settings", return_value=settings_no_github
            ),
            patch("src.integrations.github.is_supabase_db_enabled", return_value=False),
        ):
            token, org = await resolve_github_credentials(
                settings_no_github, tenant_id="tenant-1"
            )
            assert token == ""
            assert org == ""

    @pytest.mark.asyncio
    async def test_handles_db_exception_gracefully(self, settings_no_github):
        with (
            patch(
                "src.integrations.github.get_settings", return_value=settings_no_github
            ),
            patch("src.integrations.github.is_supabase_db_enabled", return_value=True),
            patch("src.integrations.github.get_db", side_effect=Exception("DB down")),
        ):
            token, org = await resolve_github_credentials(
                settings_no_github, tenant_id="tenant-1"
            )
            assert token == ""
            assert org == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_encrypted_field(self, settings_no_github):
        mock_db = _mock_supabase_db([{"config": {}}])

        with (
            patch(
                "src.integrations.github.get_settings", return_value=settings_no_github
            ),
            patch("src.integrations.github.is_supabase_db_enabled", return_value=True),
            patch("src.integrations.github.get_db", return_value=mock_db),
        ):
            token, org = await resolve_github_credentials(
                settings_no_github, tenant_id="tenant-1"
            )
            assert token == ""
            assert org == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_tenant_id_empty(self, settings_no_github):
        mock_get_db = MagicMock()

        with (
            patch(
                "src.integrations.github.get_settings", return_value=settings_no_github
            ),
            patch("src.integrations.github.is_supabase_db_enabled", return_value=True),
            patch("src.integrations.github.get_db", mock_get_db),
        ):
            token, org = await resolve_github_credentials(
                settings_no_github, tenant_id=""
            )

        assert token == ""
        assert org == ""
        mock_get_db.assert_not_called()


class TestGitHubAdapterInit:
    """Test GitHubAdapter accepts override token/org."""

    def test_uses_settings_by_default(self, settings_with_github):
        adapter = GitHubAdapter(settings_with_github)
        assert adapter.token == "ghp_env_token"
        assert adapter.org == "my-org"

    def test_override_token_and_org(self, settings_with_github):
        adapter = GitHubAdapter(
            settings_with_github, token="override_token", org="override_org"
        )
        assert adapter.token == "override_token"
        assert adapter.org == "override_org"

    def test_override_with_empty_string(self, settings_with_github):
        adapter = GitHubAdapter(settings_with_github, token="", org="")
        assert adapter.token == ""
        assert adapter.org == ""
