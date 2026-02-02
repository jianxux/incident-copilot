"""Authentication and multi-tenant support for Incident Copilot."""

from .middleware import AuthMiddleware, get_current_user, require_auth
from .models import APIKey, Session, Tenant, User
from .oauth import GitHubOAuth, GoogleOAuth, OAuthProvider
from .service import AuthService
from .sso import (
    IdentityProvider,
    IdentityProviderType,
    OIDCProvider,
    SAMLProvider,
    SSOConfig,
    SSOSession,
)

__all__ = [
    "Tenant",
    "User",
    "APIKey",
    "Session",
    "AuthService",
    "AuthMiddleware",
    "require_auth",
    "get_current_user",
    "OAuthProvider",
    "GitHubOAuth",
    "GoogleOAuth",
    # SSO
    "SSOConfig",
    "IdentityProvider",
    "IdentityProviderType",
    "SSOSession",
    "SAMLProvider",
    "OIDCProvider",
]
