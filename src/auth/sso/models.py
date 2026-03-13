"""Data models for SSO (SAML 2.0 and OIDC) authentication."""

import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IdentityProviderType(StrEnum):
    """Supported identity provider types."""

    SAML = "saml"
    OIDC = "oidc"


class SAMLSettings(BaseModel):
    """SAML-specific configuration for an identity provider."""

    # IdP Metadata
    idp_entity_id: str
    idp_sso_url: str  # Single Sign-On URL
    idp_slo_url: str | None = None  # Single Logout URL (optional)
    idp_x509_cert: str  # IdP's X.509 certificate for signature verification

    # SP Configuration
    sp_entity_id: str | None = None  # Auto-generated if not provided
    sp_acs_url: str | None = None  # Assertion Consumer Service URL
    sp_metadata_url: str | None = None

    # Attribute mappings (IdP attribute -> local field)
    attribute_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
            "name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
            "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
            "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
            "groups": "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
        }
    )

    # Security settings
    want_assertions_signed: bool = True
    want_messages_signed: bool = True
    want_name_id_encrypted: bool = False
    authn_requests_signed: bool = True

    # Name ID format
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"


class OIDCSettings(BaseModel):
    """OIDC-specific configuration for an identity provider."""

    # IdP Configuration
    issuer: str  # OpenID Connect issuer URL
    client_id: str
    client_secret: str

    # Well-known endpoints (auto-discovered from issuer if not provided)
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None
    end_session_endpoint: str | None = None

    # OAuth scopes
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])

    # Claim mappings (OIDC claim -> local field)
    claim_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "email": "email",
            "name": "name",
            "given_name": "given_name",
            "family_name": "family_name",
            "groups": "groups",
        }
    )

    # Security settings
    use_pkce: bool = True
    pkce_method: str = "S256"  # S256 or plain

    # Known provider presets
    provider_type: str | None = None  # google, okta, azure_ad, auth0


class IdentityProvider(BaseModel):
    """An identity provider configuration for a tenant."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    tenant_id: str
    name: str  # Human-friendly name (e.g., "Okta Production")
    slug: str  # URL-safe identifier (e.g., "okta-prod")

    # Provider type and settings
    provider_type: IdentityProviderType
    saml_settings: SAMLSettings | None = None
    oidc_settings: OIDCSettings | None = None

    # Status
    is_active: bool = True
    is_default: bool = False  # If true, auto-redirect to this IdP

    # Domain mapping (for automatic IdP selection based on email domain)
    email_domains: list[str] = Field(default_factory=list)

    # Role mapping (IdP group/role -> local role)
    role_mapping: dict[str, str] = Field(default_factory=dict)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime | None = None

    def matches_email_domain(self, email: str) -> bool:
        """Check if this IdP handles the given email domain."""
        if not self.email_domains:
            return False
        domain = email.split("@")[-1].lower()
        return domain in [d.lower() for d in self.email_domains]


class SSOConfig(BaseModel):
    """SSO configuration for a tenant."""

    tenant_id: str

    # General SSO settings
    sso_enabled: bool = False
    sso_required: bool = False  # If true, only SSO login is allowed

    # Identity providers
    identity_providers: list[IdentityProvider] = Field(default_factory=list)

    # JIT (Just-In-Time) provisioning
    jit_provisioning_enabled: bool = True
    jit_default_role: str = "member"

    # Session settings
    session_lifetime_hours: int = 24
    force_reauthentication: bool = False

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get_idp_by_id(self, idp_id: str) -> IdentityProvider | None:
        """Get an identity provider by ID."""
        for idp in self.identity_providers:
            if idp.id == idp_id:
                return idp
        return None

    def get_idp_by_slug(self, slug: str) -> IdentityProvider | None:
        """Get an identity provider by slug."""
        for idp in self.identity_providers:
            if idp.slug == slug:
                return idp
        return None

    def get_default_idp(self) -> IdentityProvider | None:
        """Get the default identity provider."""
        for idp in self.identity_providers:
            if idp.is_default and idp.is_active:
                return idp
        for idp in self.identity_providers:
            if idp.is_active:
                return idp
        return None

    def get_idp_for_email(self, email: str) -> IdentityProvider | None:
        """Get the identity provider for a given email domain."""
        for idp in self.identity_providers:
            if idp.is_active and idp.matches_email_domain(email):
                return idp
        return None


class SSOSession(BaseModel):
    """An SSO session tracking authentication state."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    tenant_id: str
    idp_id: str

    # Session state
    state: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    nonce: str | None = None  # For OIDC
    code_verifier: str | None = None  # For PKCE

    # SAML-specific
    saml_request_id: str | None = None

    # Redirect info
    relay_state: str | None = None  # Return URL after auth
    redirect_uri: str | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10)
    )

    # Result
    is_completed: bool = False
    user_id: str | None = None
    error: str | None = None

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        return datetime.now(UTC) > self.expires_at


class SSOUserInfo(BaseModel):
    """User information extracted from SSO assertion/token."""

    subject_id: str  # IdP's unique identifier for the user
    email: str
    email_verified: bool = False

    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None

    groups: list[str] = Field(default_factory=list)
    raw_attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Get the best available display name."""
        if self.name:
            return self.name
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        if self.first_name:
            return self.first_name
        return self.email.split("@")[0]


# OIDC Provider presets for common providers
OIDC_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "google": {
        "issuer": "https://accounts.google.com",
        "scopes": ["openid", "email", "profile"],
    },
    "okta": {
        "scopes": ["openid", "email", "profile", "groups"],
    },
    "azure_ad": {
        "scopes": ["openid", "email", "profile"],
        "claim_mapping": {
            "email": "preferred_username",
            "name": "name",
            "groups": "groups",
        },
    },
    "auth0": {
        "scopes": ["openid", "email", "profile"],
    },
}
