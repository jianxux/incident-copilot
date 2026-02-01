"""Configuration management for Incident Copilot."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "incident-copilot"
    debug: bool = False

    # PagerDuty
    pagerduty_api_key: str = Field(default="", description="PagerDuty API key")
    pagerduty_webhook_secret: str = Field(default="", description="PagerDuty webhook signing secret")

    # GitHub
    github_token: str = Field(default="", description="GitHub personal access token")
    github_org: str = Field(default="", description="GitHub organization name")

    # Datadog
    datadog_api_key: str = Field(default="", description="Datadog API key")
    datadog_app_key: str = Field(default="", description="Datadog application key")
    datadog_site: str = Field(default="datadoghq.com", description="Datadog site")

    # AWS CloudWatch
    aws_region: str = Field(default="", description="AWS region for CloudWatch")
    aws_access_key_id: str = Field(default="", description="AWS access key ID (optional, uses boto3 defaults)")
    aws_secret_access_key: str = Field(default="", description="AWS secret access key (optional)")
    cloudwatch_log_group_map: dict[str, str] = Field(
        default_factory=dict,
        description="Service to CloudWatch Log Group mapping (e.g., payments-api=/aws/lambda/payments)"
    )

    # Log Provider
    log_provider: str = Field(
        default="datadog",
        description="Log provider to use: 'datadog' or 'cloudwatch'"
    )

    # Slack
    slack_bot_token: str = Field(default="", description="Slack bot OAuth token")
    slack_default_channel: str = Field(default="#incidents", description="Default Slack channel")

    # Microsoft Teams
    teams_webhook_url: str = Field(default="", description="Teams Incoming Webhook URL")

    # Notification Provider (slack | teams | both)
    notification_provider: str = Field(
        default="slack",
        description="Notification provider: 'slack', 'teams', or 'both'"
    )

    # AI (Anthropic)
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    ai_model: str = Field(default="claude-3-haiku-20240307", description="AI model for summarization")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/incident_copilot",
        description="PostgreSQL connection URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # Service mapping (simple key=value pairs, e.g., "payments-api=mycompany/payments")
    service_repo_map: dict[str, str] = Field(default_factory=dict)

    # OAuth - GitHub
    github_oauth_client_id: str = Field(default="", description="GitHub OAuth App Client ID")
    github_oauth_client_secret: str = Field(default="", description="GitHub OAuth App Client Secret")

    # OAuth - Google
    google_oauth_client_id: str = Field(default="", description="Google OAuth Client ID")
    google_oauth_client_secret: str = Field(default="", description="Google OAuth Client Secret")

    # Auth
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for signing tokens"
    )
    app_url: str = Field(
        default="http://localhost:8000",
        description="Public URL of the application"
    )

    # Stripe
    stripe_api_key: str = Field(default="", description="Stripe API secret key")
    stripe_publishable_key: str = Field(default="", description="Stripe publishable key")
    stripe_webhook_secret: str = Field(default="", description="Stripe webhook signing secret")
    stripe_price_starter: str = Field(default="", description="Stripe Price ID for Starter plan")
    stripe_price_pro: str = Field(default="", description="Stripe Price ID for Pro plan")
    stripe_price_enterprise: str = Field(default="", description="Stripe Price ID for Enterprise plan")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
