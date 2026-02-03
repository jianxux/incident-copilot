"""Tests for SSO (SAML and OIDC) authentication."""

import base64
import secrets
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.sso.models import (
    OIDC_PROVIDER_PRESETS,
    IdentityProvider,
    IdentityProviderType,
    OIDCSettings,
    SAMLSettings,
    SSOConfig,
    SSOSession,
    SSOUserInfo,
)
from src.auth.sso.oidc import OIDCProvider
from src.auth.sso.routes import (
    _sso_configs,
    _sso_sessions,
    get_or_create_sso_config,
    get_sso_session,
    save_sso_session,
)

# --- Model Tests ---


class TestSSOModels:
    """Test SSO data models."""

    def test_identity_provider_creation(self):
        """Test creating an identity provider."""
        idp = IdentityProvider(
            tenant_id="tenant-123",
            name="Okta Production",
            slug="okta-prod",
            provider_type=IdentityProviderType.OIDC,
            email_domains=["example.com", "example.org"],
        )

        assert idp.id is not None
        assert idp.tenant_id == "tenant-123"
        assert idp.provider_type == IdentityProviderType.OIDC
        assert idp.is_active is True
        assert idp.is_default is False

    def test_identity_provider_email_domain_matching(self):
        """Test email domain matching for IdP."""
        idp = IdentityProvider(
            tenant_id="tenant-123",
            name="Corporate IdP",
            slug="corp-idp",
            provider_type=IdentityProviderType.SAML,
            email_domains=["company.com", "company.org"],
        )

        assert idp.matches_email_domain("user@company.com") is True
        assert idp.matches_email_domain("user@COMPANY.COM") is True  # Case insensitive
        assert idp.matches_email_domain("user@other.com") is False
        assert idp.matches_email_domain("invalid") is False

    def test_identity_provider_no_domains(self):
        """Test IdP with no email domains."""
        idp = IdentityProvider(
            tenant_id="tenant-123",
            name="Open IdP",
            slug="open-idp",
            provider_type=IdentityProviderType.OIDC,
        )

        assert idp.matches_email_domain("anyone@anywhere.com") is False

    def test_sso_config_get_idp_methods(self):
        """Test SSO config IdP lookup methods."""
        idp1 = IdentityProvider(
            id="idp-1",
            tenant_id="tenant-123",
            name="Primary IdP",
            slug="primary",
            provider_type=IdentityProviderType.SAML,
            is_default=True,
            email_domains=["primary.com"],
        )
        idp2 = IdentityProvider(
            id="idp-2",
            tenant_id="tenant-123",
            name="Secondary IdP",
            slug="secondary",
            provider_type=IdentityProviderType.OIDC,
            email_domains=["secondary.com"],
        )

        config = SSOConfig(
            tenant_id="tenant-123",
            sso_enabled=True,
            identity_providers=[idp1, idp2],
        )

        # Test get by ID
        assert config.get_idp_by_id("idp-1") == idp1
        assert config.get_idp_by_id("idp-2") == idp2
        assert config.get_idp_by_id("nonexistent") is None

        # Test get by slug
        assert config.get_idp_by_slug("primary") == idp1
        assert config.get_idp_by_slug("secondary") == idp2
        assert config.get_idp_by_slug("nonexistent") is None

        # Test get default
        assert config.get_default_idp() == idp1

        # Test get by email
        assert config.get_idp_for_email("user@primary.com") == idp1
        assert config.get_idp_for_email("user@secondary.com") == idp2
        assert config.get_idp_for_email("user@unknown.com") is None

    def test_sso_session_expiry(self):
        """Test SSO session expiry."""
        # Non-expired session
        session = SSOSession(
            tenant_id="tenant-123",
            idp_id="idp-1",
        )
        assert session.is_expired() is False

        # Expired session
        expired_session = SSOSession(
            tenant_id="tenant-123",
            idp_id="idp-1",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        assert expired_session.is_expired() is True

    def test_sso_user_info_display_name(self):
        """Test SSOUserInfo display name logic."""
        # With full name
        user1 = SSOUserInfo(
            subject_id="sub-1",
            email="user@example.com",
            name="John Doe",
        )
        assert user1.display_name == "John Doe"

        # With first and last name
        user2 = SSOUserInfo(
            subject_id="sub-2",
            email="user@example.com",
            first_name="Jane",
            last_name="Doe",
        )
        assert user2.display_name == "Jane Doe"

        # With only first name
        user3 = SSOUserInfo(
            subject_id="sub-3",
            email="user@example.com",
            first_name="Alice",
        )
        assert user3.display_name == "Alice"

        # With only email
        user4 = SSOUserInfo(
            subject_id="sub-4",
            email="bob@example.com",
        )
        assert user4.display_name == "bob"

    def test_saml_settings_defaults(self):
        """Test SAML settings default values."""
        settings = SAMLSettings(
            idp_entity_id="https://idp.example.com",
            idp_sso_url="https://idp.example.com/sso",
            idp_x509_cert="CERT_DATA",
        )

        assert settings.want_assertions_signed is True
        assert settings.want_messages_signed is True
        assert settings.authn_requests_signed is True
        assert "email" in settings.attribute_mapping

    def test_oidc_settings_defaults(self):
        """Test OIDC settings default values."""
        settings = OIDCSettings(
            issuer="https://idp.example.com",
            client_id="client-123",
            client_secret="secret-456",
        )

        assert settings.use_pkce is True
        assert settings.pkce_method == "S256"
        assert "openid" in settings.scopes
        assert "email" in settings.scopes

    def test_oidc_provider_presets(self):
        """Test OIDC provider presets are defined."""
        assert "google" in OIDC_PROVIDER_PRESETS
        assert "okta" in OIDC_PROVIDER_PRESETS
        assert "azure_ad" in OIDC_PROVIDER_PRESETS
        assert "auth0" in OIDC_PROVIDER_PRESETS

        # Google preset should have issuer
        assert (
            OIDC_PROVIDER_PRESETS["google"]["issuer"] == "https://accounts.google.com"
        )


# --- Session Management Tests ---


class TestSSOSessionManagement:
    """Test SSO session storage and retrieval."""

    def setup_method(self):
        """Clear session storage before each test."""
        _sso_sessions.clear()
        _sso_configs.clear()

    def test_save_and_get_session(self):
        """Test saving and retrieving an SSO session."""
        session = SSOSession(
            tenant_id="tenant-123",
            idp_id="idp-1",
        )

        save_sso_session(session)

        # Retrieve session
        retrieved = get_sso_session(session.state)

        assert retrieved is not None
        assert retrieved.id == session.id
        assert retrieved.tenant_id == session.tenant_id

        # Session should be removed after retrieval
        assert get_sso_session(session.state) is None

    def test_get_expired_session(self):
        """Test that expired sessions are not returned."""
        session = SSOSession(
            tenant_id="tenant-123",
            idp_id="idp-1",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )

        save_sso_session(session)

        # Should return None for expired session
        assert get_sso_session(session.state) is None

    def test_get_nonexistent_session(self):
        """Test getting a non-existent session."""
        assert get_sso_session("nonexistent-state") is None

    def test_get_or_create_sso_config(self):
        """Test getting or creating SSO config."""
        # First call should create
        config1 = get_or_create_sso_config("tenant-123")
        assert config1.tenant_id == "tenant-123"
        assert config1.sso_enabled is False

        # Second call should return same config
        config2 = get_or_create_sso_config("tenant-123")
        assert config1 is config2


# --- OIDC Provider Tests ---


class TestOIDCProvider:
    """Test OIDC provider functionality."""

    def get_test_idp(self) -> IdentityProvider:
        """Create a test OIDC IdP."""
        return IdentityProvider(
            tenant_id="tenant-123",
            name="Test OIDC",
            slug="test-oidc",
            provider_type=IdentityProviderType.OIDC,
            oidc_settings=OIDCSettings(
                issuer="https://idp.example.com",
                client_id="test-client",
                client_secret="test-secret",
            ),
        )

    def test_generate_pkce_pair(self):
        """Test PKCE code verifier and challenge generation."""
        idp = self.get_test_idp()
        provider = OIDCProvider(idp, "https://app.example.com")

        verifier, challenge = provider.generate_pkce_pair()

        # Verifier should be URL-safe
        assert len(verifier) > 40
        assert len(verifier) <= 128

        # Challenge should be base64url encoded
        assert challenge != verifier  # S256 method
        assert "=" not in challenge  # No padding

    def test_create_session_for_auth(self):
        """Test creating an SSO session for OIDC auth."""
        session = OIDCProvider.create_session_for_auth(
            tenant_id="tenant-123",
            idp_id="idp-1",
            redirect_uri="https://app.example.com/callback",
            relay_state="https://app.example.com/dashboard",
            use_pkce=True,
        )

        assert session.tenant_id == "tenant-123"
        assert session.idp_id == "idp-1"
        assert session.nonce is not None
        assert session.code_verifier is not None
        assert session.relay_state == "https://app.example.com/dashboard"
        assert not session.is_expired()

    def test_create_session_without_pkce(self):
        """Test creating an SSO session without PKCE."""
        session = OIDCProvider.create_session_for_auth(
            tenant_id="tenant-123",
            idp_id="idp-1",
            redirect_uri="https://app.example.com/callback",
            use_pkce=False,
        )

        assert session.code_verifier is None
        assert session.nonce is not None

    @pytest.mark.asyncio
    async def test_discover_configuration(self):
        """Test OIDC configuration discovery."""
        idp = self.get_test_idp()
        provider = OIDCProvider(idp, "https://app.example.com")

        mock_config = {
            "issuer": "https://idp.example.com",
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "userinfo_endpoint": "https://idp.example.com/userinfo",
            "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        }

        with patch("src.auth.sso.oidc.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_config
            mock_response.raise_for_status = MagicMock()

            async_context = AsyncMock()
            async_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = async_context

            config = await provider.discover_configuration()

            assert config["issuer"] == "https://idp.example.com"
            assert "authorization_endpoint" in config

    def test_map_claims_to_user(self):
        """Test mapping OIDC claims to SSOUserInfo."""
        idp = self.get_test_idp()
        provider = OIDCProvider(idp, "https://app.example.com")

        claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "picture": "https://example.com/avatar.jpg",
            "groups": ["admin", "users"],
        }

        user_info = provider._map_claims_to_user(claims)

        assert user_info.subject_id == "user-123"
        assert user_info.email == "user@example.com"
        assert user_info.email_verified is True
        assert user_info.name == "Test User"
        assert user_info.first_name == "Test"
        assert user_info.last_name == "User"
        assert user_info.avatar_url == "https://example.com/avatar.jpg"
        assert "admin" in user_info.groups

    def test_map_claims_missing_email(self):
        """Test that missing email raises error."""
        idp = self.get_test_idp()
        provider = OIDCProvider(idp, "https://app.example.com")

        claims = {"sub": "user-123"}

        with pytest.raises(ValueError, match="No email claim"):
            provider._map_claims_to_user(claims)

    def test_map_claims_missing_subject(self):
        """Test that missing subject raises error."""
        idp = self.get_test_idp()
        provider = OIDCProvider(idp, "https://app.example.com")

        claims = {"email": "user@example.com"}

        with pytest.raises(ValueError, match="No subject claim"):
            provider._map_claims_to_user(claims)


# --- SAML Provider Tests ---


class TestSAMLProvider:
    """Test SAML provider functionality."""

    def get_test_idp(self) -> IdentityProvider:
        """Create a test SAML IdP."""
        return IdentityProvider(
            tenant_id="tenant-123",
            name="Test SAML",
            slug="test-saml",
            provider_type=IdentityProviderType.SAML,
            saml_settings=SAMLSettings(
                idp_entity_id="https://idp.example.com",
                idp_sso_url="https://idp.example.com/sso",
                idp_x509_cert="MIIDEjCCAfqgAwIBAgI...",  # Fake cert
            ),
        )

    def test_saml_provider_initialization(self):
        """Test SAML provider requires SAML settings."""
        idp_no_saml = IdentityProvider(
            tenant_id="tenant-123",
            name="No SAML",
            slug="no-saml",
            provider_type=IdentityProviderType.SAML,
        )

        with pytest.raises(ValueError, match="SAML settings"):
            from src.auth.sso.saml import SAMLProvider

            SAMLProvider(idp_no_saml, "https://app.example.com")

    def test_saml_attribute_mapping(self):
        """Test SAML attribute mapping defaults."""
        idp = self.get_test_idp()
        mapping = idp.saml_settings.attribute_mapping

        # Should have standard mappings
        assert "email" in mapping
        assert "name" in mapping
        assert "first_name" in mapping
        assert "last_name" in mapping
        assert "groups" in mapping


# --- Route Tests ---


class TestSSORoutes:
    """Test SSO API routes."""

    def setup_method(self):
        """Set up test client and clear state."""
        from src.main import app

        self.client = TestClient(app)
        _sso_configs.clear()
        _sso_sessions.clear()

    def test_get_sso_config_not_configured(self):
        """Test getting SSO config for unconfigured tenant."""
        response = self.client.get("/auth/sso/config/tenant-123")

        assert response.status_code == 200
        data = response.json()
        assert data["sso_enabled"] is False
        assert data["identity_providers"] == []

    def test_enable_sso_without_idp(self):
        """Test enabling SSO without any IdP fails."""
        response = self.client.post("/auth/sso/config/nonexistent/enable")

        # Should fail because tenant doesn't exist
        assert response.status_code == 404

    def test_discover_idp_not_found(self):
        """Test IdP discovery for unknown domain."""
        response = self.client.get(
            "/auth/sso/discover",
            params={"email": "user@unknown-domain.com"},
        )

        assert response.status_code == 404
        assert "No SSO configured" in response.json()["detail"]

    def test_saml_login_sso_not_enabled(self):
        """Test SAML login when SSO not enabled."""
        response = self.client.get(
            "/auth/sso/saml/login/tenant-123",
            follow_redirects=False,
        )

        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]

    def test_oidc_login_sso_not_enabled(self):
        """Test OIDC login when SSO not enabled."""
        response = self.client.get(
            "/auth/sso/oidc/login/tenant-123",
            follow_redirects=False,
        )

        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]

    def test_saml_acs_no_session(self):
        """Test SAML ACS with no session."""
        response = self.client.post(
            "/auth/sso/saml/acs/tenant-123",
            data={
                "SAMLResponse": base64.b64encode(b"<fake/>").decode(),
                "RelayState": "nonexistent-state",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "sso_session_expired" in response.headers["location"]

    def test_oidc_callback_error(self):
        """Test OIDC callback with error."""
        response = self.client.get(
            "/auth/sso/oidc/callback/tenant-123",
            params={
                "error": "access_denied",
                "error_description": "User denied access",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "sso_denied" in response.headers["location"]

    def test_oidc_callback_no_session(self):
        """Test OIDC callback with no session."""
        response = self.client.get(
            "/auth/sso/oidc/callback/tenant-123",
            params={
                "code": "auth-code",
                "state": "nonexistent-state",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "sso_session_expired" in response.headers["location"]


# --- Integration Tests ---


class TestSSOIntegration:
    """Integration tests for SSO flow."""

    def setup_method(self):
        """Set up test state."""
        _sso_configs.clear()
        _sso_sessions.clear()

    @pytest.mark.asyncio
    async def test_full_oidc_session_flow(self):
        """Test complete OIDC session creation and retrieval."""
        # Create SSO config with OIDC IdP
        config = get_or_create_sso_config("tenant-123")
        config.sso_enabled = True

        idp = IdentityProvider(
            tenant_id="tenant-123",
            name="Test OIDC",
            slug="test-oidc",
            provider_type=IdentityProviderType.OIDC,
            is_default=True,
            oidc_settings=OIDCSettings(
                issuer="https://idp.example.com",
                client_id="test-client",
                client_secret="test-secret",
            ),
        )
        config.identity_providers.append(idp)

        # Create session
        session = OIDCProvider.create_session_for_auth(
            tenant_id="tenant-123",
            idp_id=idp.id,
            redirect_uri="https://app.example.com/callback",
        )
        save_sso_session(session)

        # Verify session can be retrieved
        retrieved = get_sso_session(session.state)
        assert retrieved is not None
        assert retrieved.tenant_id == "tenant-123"
        assert retrieved.idp_id == idp.id

        # Session should be removed
        assert get_sso_session(session.state) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
