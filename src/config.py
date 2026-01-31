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

    # Slack
    slack_bot_token: str = Field(default="", description="Slack bot OAuth token")
    slack_default_channel: str = Field(default="#incidents", description="Default Slack channel")

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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
