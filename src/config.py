"""Configuration management for Incident Copilot."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "incident-copilot"
    debug: bool = False

    # PagerDuty
    pagerduty_api_key: str = Field(default="", description="PagerDuty API key")
    pagerduty_webhook_secret: str = Field(
        default="", description="PagerDuty webhook signing secret"
    )

    # Opsgenie
    opsgenie_api_key: str = Field(default="", description="Opsgenie API key")
    opsgenie_webhook_secret: str = Field(
        default="", description="Opsgenie webhook signing secret"
    )
    opsgenie_region: str = Field(default="us", description="Opsgenie region (us or eu)")

    # On-Call Roster
    oncall_provider: str = Field(
        default="auto",
        description="On-call provider: 'pagerduty', 'opsgenie', or 'auto' (detect from credentials)",
    )
    oncall_schedule_id: str = Field(
        default="",
        description="Default on-call schedule ID to fetch",
    )
    oncall_schedule_map: dict[str, str] = Field(
        default_factory=dict,
        description="Service to schedule ID mapping (e.g., payments-api=SCHEDULE123)",
    )
    oncall_enabled: bool = Field(
        default=True,
        description="Enable on-call roster fetching",
    )

    # GitHub
    github_token: str = Field(default="", description="GitHub personal access token")
    github_org: str = Field(default="", description="GitHub organization name")

    # GitLab
    gitlab_token: str = Field(default="", description="GitLab personal access token")
    gitlab_url: str = Field(
        default="https://gitlab.com",
        description="GitLab instance URL (for self-hosted)",
    )
    gitlab_project_map: dict[str, str] = Field(
        default_factory=dict,
        description="Service to GitLab project path mapping (e.g., payments-api=mygroup/payments)",
    )

    # Datadog
    datadog_api_key: str = Field(default="", description="Datadog API key")
    datadog_app_key: str = Field(default="", description="Datadog application key")
    datadog_site: str = Field(default="datadoghq.com", description="Datadog site")

    # AWS CloudWatch
    aws_region: str = Field(default="", description="AWS region for CloudWatch")
    aws_access_key_id: str = Field(
        default="", description="AWS access key ID (optional, uses boto3 defaults)"
    )
    aws_secret_access_key: str = Field(
        default="", description="AWS secret access key (optional)"
    )
    cloudwatch_log_group_map: dict[str, str] = Field(
        default_factory=dict,
        description="Service to CloudWatch Log Group mapping (e.g., payments-api=/aws/lambda/payments)",
    )

    # Grafana Loki
    loki_url: str = Field(
        default="",
        description="Loki base URL (e.g., http://loki:3100 or https://logs-prod-us-central1.grafana.net)",
    )
    loki_auth_type: str = Field(
        default="none",
        description="Loki authentication type: 'none', 'basic', or 'bearer'",
    )
    loki_username: str = Field(
        default="", description="Loki username for basic auth (e.g., Grafana Cloud user ID)"
    )
    loki_password: str = Field(
        default="", description="Loki password for basic auth (e.g., Grafana Cloud API key)"
    )
    loki_token: str = Field(
        default="", description="Loki bearer token for token-based auth"
    )
    loki_org_id: str = Field(
        default="",
        description="Loki tenant ID for multi-tenant deployments (X-Scope-OrgID header)",
    )
    loki_service_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Service to Loki label selector mapping (e.g., payments-api=service=\"payments\")",
    )

    # Splunk
    splunk_url: str = Field(
        default="",
        description="Splunk REST API URL (e.g., https://splunk.example.com:8089)",
    )
    splunk_token: str = Field(
        default="",
        description="Splunk authentication token (recommended for automation)",
    )
    splunk_username: str = Field(
        default="",
        description="Splunk username for basic auth (alternative to token)",
    )
    splunk_password: str = Field(
        default="",
        description="Splunk password for basic auth",
    )
    splunk_index_map: dict[str, str] = Field(
        default_factory=dict,
        description="Service to Splunk index mapping (e.g., payments-api=payments_logs)",
    )

    # Log Provider
    log_provider: str = Field(
        default="datadog",
        description="Log provider to use: 'datadog', 'cloudwatch', 'loki', or 'splunk'",
    )

    # Slack
    slack_bot_token: str = Field(default="", description="Slack bot OAuth token")
    slack_signing_secret: str = Field(
        default="", description="Slack app signing secret for request verification"
    )
    slack_default_channel: str = Field(
        default="#incidents", description="Default Slack channel"
    )

    # Microsoft Teams
    teams_webhook_url: str = Field(default="", description="Teams Incoming Webhook URL")

    # Notification Provider (slack | teams | both)
    notification_provider: str = Field(
        default="slack",
        description="Notification provider: 'slack', 'teams', or 'both'",
    )

    # AI (Anthropic)
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    ai_model: str = Field(
        default="claude-3-haiku-20240307", description="AI model for summarization"
    )

    # OpenAI (for embeddings)
    openai_api_key: str = Field(default="", description="OpenAI API key for embeddings")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/incident_copilot",
        description="PostgreSQL connection URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )

    # Service mapping (simple key=value pairs, e.g., "payments-api=mycompany/payments")
    service_repo_map: dict[str, str] = Field(default_factory=dict)

    # OAuth - GitHub
    github_oauth_client_id: str = Field(
        default="", description="GitHub OAuth App Client ID"
    )
    github_oauth_client_secret: str = Field(
        default="", description="GitHub OAuth App Client Secret"
    )

    # OAuth - Google
    google_oauth_client_id: str = Field(
        default="", description="Google OAuth Client ID"
    )
    google_oauth_client_secret: str = Field(
        default="", description="Google OAuth Client Secret"
    )

    # Auth
    secret_key: str = Field(
        default="change-me-in-production", description="Secret key for signing tokens"
    )
    app_url: str = Field(
        default="http://localhost:8000", description="Public URL of the application"
    )

    # Jira
    jira_base_url: str = Field(
        default="",
        description="Jira Cloud URL (e.g., https://yourcompany.atlassian.net)",
    )
    jira_email: str = Field(default="", description="Jira user email for API auth")
    jira_api_token: str = Field(default="", description="Jira API token")
    jira_default_project: str = Field(
        default="INCIDENT", description="Default Jira project key for incidents"
    )

    # ServiceNow
    servicenow_instance: str = Field(
        default="",
        description="ServiceNow instance URL (e.g., https://yourcompany.service-now.com)",
    )
    servicenow_username: str = Field(
        default="",
        description="ServiceNow username for basic auth",
    )
    servicenow_password: str = Field(
        default="",
        description="ServiceNow password for basic auth",
    )
    servicenow_api_key: str = Field(
        default="",
        description="ServiceNow OAuth token or API key (alternative to basic auth)",
    )
    servicenow_assignment_group: str = Field(
        default="",
        description="Default assignment group for new incidents",
    )
    servicenow_caller_id: str = Field(
        default="",
        description="Default caller ID for incidents created by the copilot",
    )

    # Linear
    linear_api_key: str = Field(
        default="",
        description="Linear API key (from https://linear.app/settings/api)",
    )
    linear_team_id: str = Field(
        default="",
        description="Default Linear team ID for incidents",
    )
    linear_label_ids: list[str] = Field(
        default_factory=list,
        description="Optional label IDs to apply to incident issues",
    )

    # Stripe
    stripe_api_key: str = Field(default="", description="Stripe API secret key")
    stripe_publishable_key: str = Field(
        default="", description="Stripe publishable key"
    )
    stripe_webhook_secret: str = Field(
        default="", description="Stripe webhook signing secret"
    )
    stripe_price_starter: str = Field(
        default="", description="Stripe Price ID for Starter plan"
    )
    stripe_price_pro: str = Field(
        default="", description="Stripe Price ID for Pro plan"
    )
    stripe_price_enterprise: str = Field(
        default="", description="Stripe Price ID for Enterprise plan"
    )

    # SSO - General Settings
    sso_session_lifetime_minutes: int = Field(
        default=10,
        description="SSO session state lifetime in minutes (for in-flight auth)",
    )
    sso_jit_provisioning_default: bool = Field(
        default=True,
        description="Enable JIT (Just-In-Time) user provisioning by default",
    )

    # SSO - SAML Settings
    saml_sp_private_key: str = Field(
        default="",
        description="SP private key for SAML signing/decryption (PEM format)",
    )
    saml_sp_certificate: str = Field(
        default="",
        description="SP certificate for SAML signing (PEM format)",
    )
    saml_want_assertions_signed: bool = Field(
        default=True,
        description="Require signed SAML assertions",
    )
    saml_want_messages_signed: bool = Field(
        default=True,
        description="Require signed SAML messages",
    )

    # SSO - OIDC Settings
    oidc_default_scopes: str = Field(
        default="openid email profile",
        description="Default OIDC scopes (space-separated)",
    )
    oidc_use_pkce_default: bool = Field(
        default=True,
        description="Use PKCE by default for OIDC flows",
    )

    # Rate Limiting
    ratelimit_enabled: bool = Field(
        default=True, description="Enable API rate limiting"
    )
    ratelimit_exclude_paths: list[str] = Field(
        default_factory=lambda: [
            "/health",
            "/healthz",
            "/ready",
            "/metrics",
            "/favicon.ico",
            "/static/*",
            "/docs",
            "/redoc",
            "/openapi.json",
        ],
        description="Paths to exclude from rate limiting",
    )
    
    # Rate limits per scope (token bucket: capacity = burst, refill_rate = sustained rate/sec)
    ratelimit_ip_capacity: int = Field(
        default=100, description="Max requests per IP (burst capacity)"
    )
    ratelimit_ip_refill_rate: float = Field(
        default=10.0, description="IP rate limit refill rate (tokens/second)"
    )
    ratelimit_api_key_capacity: int = Field(
        default=1000, description="Max requests per API key (burst capacity)"
    )
    ratelimit_api_key_refill_rate: float = Field(
        default=50.0, description="API key rate limit refill rate (tokens/second)"
    )
    ratelimit_tenant_capacity: int = Field(
        default=5000, description="Max requests per tenant (burst capacity)"
    )
    ratelimit_tenant_refill_rate: float = Field(
        default=100.0, description="Tenant rate limit refill rate (tokens/second)"
    )
    ratelimit_user_capacity: int = Field(
        default=200, description="Max requests per user (burst capacity)"
    )
    ratelimit_user_refill_rate: float = Field(
        default=20.0, description="User rate limit refill rate (tokens/second)"
    )
    ratelimit_global_capacity: int = Field(
        default=10000, description="Global API rate limit (burst capacity)"
    )
    ratelimit_global_refill_rate: float = Field(
        default=500.0, description="Global rate limit refill rate (tokens/second)"
    )

    # Alert Correlation
    correlation_enabled: bool = Field(
        default=True, description="Enable alert correlation engine"
    )
    correlation_default_rules: bool = Field(
        default=True, description="Setup default correlation rules on startup"
    )
    correlation_time_window_seconds: int = Field(
        default=300, description="Default time window for grouping alerts (5 min)"
    )
    correlation_similarity_threshold: float = Field(
        default=0.7, description="Default fuzzy match threshold for pattern matching"
    )
    correlation_group_ttl: int = Field(
        default=86400, description="TTL for correlation groups in seconds (24h)"
    )
    correlation_stale_after_seconds: int = Field(
        default=3600, description="Mark groups stale after N seconds without activity (1h)"
    )
    correlation_max_alerts_per_group: int = Field(
        default=1000, description="Maximum alerts in a single group"
    )
    correlation_suppress_duplicates: bool = Field(
        default=True, description="Suppress duplicate notifications by default"
    )
    correlation_re_notify_after_seconds: int = Field(
        default=1800, description="Re-notify if group still active after N seconds (30 min)"
    )

    # Audit Logging
    audit_enabled: bool = Field(
        default=True, description="Enable audit logging for compliance"
    )
    audit_retention_days: int = Field(
        default=90, description="Number of days to retain audit logs"
    )
    audit_log_all_requests: bool = Field(
        default=False, description="Log all API requests (verbose, for debugging)"
    )
    audit_exclude_paths: list[str] = Field(
        default_factory=lambda: [
            "/health",
            "/healthz",
            "/ready",
            "/metrics",
            "/favicon.ico",
            "/static",
            "/docs",
            "/redoc",
            "/openapi.json",
        ],
        description="Paths to exclude from audit logging",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
