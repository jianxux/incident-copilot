"""Tests for the CLI tools."""

from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import CheckStatus, app, check_config

runner = CliRunner()


class TestCheckConfig:
    """Tests for the check_config helper function."""

    def test_missing_required_value(self):
        """Test that missing required values return ERROR."""
        status, name, detail = check_config("Test", None, required=True)
        assert status == CheckStatus.ERROR
        assert "Missing" in detail

    def test_missing_optional_value(self):
        """Test that missing optional values return SKIP."""
        status, name, detail = check_config("Test", None, required=False)
        assert status == CheckStatus.SKIP
        assert "Optional" in detail

    def test_valid_value(self):
        """Test that valid values return OK."""
        status, name, detail = check_config("Test", "valid-value-here")
        assert status == CheckStatus.OK
        assert "Configured" in detail

    def test_invalid_format(self):
        """Test that invalid format returns WARN."""
        status, name, detail = check_config(
            "Test",
            "invalid",
            validator=lambda x: x.startswith("valid-"),
        )
        assert status == CheckStatus.WARN
        assert "invalid" in detail.lower()

    def test_valid_format(self):
        """Test that valid format passes validator."""
        status, name, detail = check_config(
            "Test",
            "valid-value",
            validator=lambda x: x.startswith("valid-"),
        )
        assert status == CheckStatus.OK


class TestValidateCommand:
    """Tests for the validate command."""

    @patch("src.cli.main.get_settings")
    def test_validate_missing_required(self, mock_settings):
        """Test validate fails with missing required config."""
        mock_settings.return_value = MockSettings(
            github_token=None,  # Missing required
        )

        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 1
        assert "missing" in result.output.lower() or "error" in result.output.lower()

    @patch("src.cli.main.get_settings")
    def test_validate_all_configured(self, mock_settings):
        """Test validate passes with all config present."""
        mock_settings.return_value = MockSettings()

        result = runner.invoke(app, ["validate"])
        # May have warnings but should not error
        assert "passed" in result.output.lower() or result.exit_code == 0


class TestVersionCommand:
    """Tests for the version command."""

    def test_version(self):
        """Test version command output."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Incident Copilot" in result.output
        assert "0.1.0" in result.output


class TestTestIntegration:
    """Tests for the test-integration command."""

    @patch("src.cli.main._test_github")
    @patch("src.cli.main.get_settings")
    def test_github_integration_success(self, mock_settings, mock_test):
        """Test successful GitHub integration test."""
        mock_settings.return_value = MockSettings()
        mock_test.return_value = {
            "success": True,
            "details": {"Authenticated as": "testuser"},
        }

        result = runner.invoke(app, ["test-integration", "github"])
        assert result.exit_code == 0
        assert "working" in result.output.lower()

    @patch("src.cli.main._test_github")
    @patch("src.cli.main.get_settings")
    def test_github_integration_failure(self, mock_settings, mock_test):
        """Test failed GitHub integration test."""
        mock_settings.return_value = MockSettings()
        mock_test.return_value = {"success": False, "error": "Invalid token"}

        result = runner.invoke(app, ["test-integration", "github"])
        assert result.exit_code == 1
        assert "failed" in result.output.lower()

    def test_unknown_integration(self):
        """Test unknown integration name."""
        result = runner.invoke(app, ["test-integration", "unknown"])
        assert result.exit_code == 1


class MockSettings:
    """Mock settings object for testing."""

    def __init__(
        self,
        pagerduty_api_key: str = "test-pd-key",
        pagerduty_webhook_secret: str = "test-webhook-secret-32chars-long",
        github_token: str = "ghp_testaccesstoken12345",
        github_org: str = "test-org",
        datadog_api_key: str = "12345678901234567890123456789012",
        datadog_app_key: str = "1234567890123456789012345678901234567890",
        datadog_site: str = "datadoghq.com",
        slack_bot_token: str = "xoxb-test-token",
        slack_default_channel: str = "#incidents",
        anthropic_api_key: str = "sk-ant-test-key",
        ai_model: str = "claude-3-haiku-20240307",
        debug: bool = False,
    ):
        self.pagerduty_api_key = pagerduty_api_key
        self.pagerduty_webhook_secret = pagerduty_webhook_secret
        self.github_token = github_token
        self.github_org = github_org
        self.datadog_api_key = datadog_api_key
        self.datadog_app_key = datadog_app_key
        self.datadog_site = datadog_site
        self.slack_bot_token = slack_bot_token
        self.slack_default_channel = slack_default_channel
        self.anthropic_api_key = anthropic_api_key
        self.ai_model = ai_model
        self.debug = debug
        self.log_provider = "datadog"
        self.opsgenie_api_key = None
        self.openai_api_key = None
        self.aws_region = "us-east-1"
