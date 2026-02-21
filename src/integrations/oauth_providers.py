"""OAuth provider configuration for integration connections."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OAuthProviderConfig:
    """Configuration needed to run OAuth for an integration provider."""

    name: str
    client_id_env: str
    client_secret_env: str
    authorize_url: str
    token_url: str
    default_scopes: list[str]
    revoke_url: str | None = None
    auth_params: dict[str, str] = field(default_factory=dict)


PROVIDER_CONFIGS: dict[str, OAuthProviderConfig] = {
    "slack": OAuthProviderConfig(
        name="slack",
        client_id_env="SLACK_CLIENT_ID",
        client_secret_env="SLACK_CLIENT_SECRET",
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        default_scopes=["channels:read", "chat:write", "users:read", "team:read"],
        revoke_url="https://slack.com/api/auth.revoke",
    ),
    "pagerduty": OAuthProviderConfig(
        name="pagerduty",
        client_id_env="PAGERDUTY_CLIENT_ID",
        client_secret_env="PAGERDUTY_CLIENT_SECRET",
        authorize_url="https://identity.pagerduty.com/oauth/authorize",
        token_url="https://identity.pagerduty.com/oauth/token",
        default_scopes=[],
    ),
    "github": OAuthProviderConfig(
        name="github",
        client_id_env="GITHUB_CLIENT_ID",
        client_secret_env="GITHUB_CLIENT_SECRET",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        default_scopes=["repo", "read:org"],
    ),
    "gitlab": OAuthProviderConfig(
        name="gitlab",
        client_id_env="GITLAB_CLIENT_ID",
        client_secret_env="GITLAB_CLIENT_SECRET",
        authorize_url="https://gitlab.com/oauth/authorize",
        token_url="https://gitlab.com/oauth/token",
        default_scopes=["api", "read_user"],
        revoke_url="https://gitlab.com/oauth/revoke",
    ),
    "jira": OAuthProviderConfig(
        name="jira",
        client_id_env="ATLASSIAN_CLIENT_ID",
        client_secret_env="ATLASSIAN_CLIENT_SECRET",
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        default_scopes=["read:jira-work", "write:jira-work"],
        revoke_url="https://auth.atlassian.com/oauth/revoke",
        auth_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),
}

ALIASES = {
    "atlassian": "jira",
}


def normalize_provider(provider: str) -> str:
    """Normalize aliases to canonical provider keys."""
    key = provider.strip().lower()
    return ALIASES.get(key, key)


def get_provider_config(provider: str) -> OAuthProviderConfig | None:
    """Get provider config by name or alias."""
    return PROVIDER_CONFIGS.get(normalize_provider(provider))


def get_provider_credentials(provider: str) -> tuple[str, str] | tuple[None, None]:
    """Resolve provider OAuth client credentials from env vars."""
    config = get_provider_config(provider)
    if not config:
        return None, None

    client_id = os.getenv(config.client_id_env, "")
    client_secret = os.getenv(config.client_secret_env, "")

    if client_id and client_secret:
        return client_id, client_secret

    # Backward-compatible fallbacks for previously used variable names.
    fallback_map = {
        "slack": ("SLACK_OAUTH_CLIENT_ID", "SLACK_OAUTH_CLIENT_SECRET"),
        "pagerduty": ("PAGERDUTY_OAUTH_CLIENT_ID", "PAGERDUTY_OAUTH_CLIENT_SECRET"),
    }
    fb = fallback_map.get(normalize_provider(provider))
    if fb:
        client_id = client_id or os.getenv(fb[0], "")
        client_secret = client_secret or os.getenv(fb[1], "")

    if not client_id or not client_secret:
        return None, None

    return client_id, client_secret
