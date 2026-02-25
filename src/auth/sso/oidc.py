"""OIDC (OpenID Connect) provider implementation."""

import base64
import secrets
from datetime import datetime, UTC
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from .models import (
    OIDC_PROVIDER_PRESETS,
    IdentityProvider,
    SSOSession,
    SSOUserInfo,
)
from .providers import BaseProvider, generate_pkce_challenge, generate_pkce_verifier

logger = structlog.get_logger()


class OIDCProvider(BaseProvider):
    """OIDC (OpenID Connect) identity provider implementation.

    Supports:
    - Authorization Code Flow with PKCE
    - Token exchange and validation
    - ID token validation
    - Token refresh
    - Well-known configuration discovery
    """

    def __init__(self, idp: IdentityProvider, app_url: str):
        """Initialize the OIDC provider.

        Args:
            idp: Identity provider with OIDC settings
            app_url: Base URL of the application

        Raises:
            ValueError: If OIDC settings are not configured
        """
        super().__init__(idp, app_url)

        if not idp.oidc_settings:
            raise ValueError(f"OIDC settings not configured for IdP {idp.id}")

        self.settings = idp.oidc_settings
        self._discovered_config: dict[str, Any] | None = None

    @staticmethod
    def create_session_for_auth(
        tenant_id: str,
        idp_id: str,
        redirect_uri: str,
        relay_state: str | None = None,
        use_pkce: bool = True,
    ) -> SSOSession:
        """Create an SSO session for OIDC authentication.

        Args:
            tenant_id: Tenant ID
            idp_id: Identity provider ID
            redirect_uri: OAuth redirect URI
            relay_state: URL to return to after authentication
            use_pkce: Whether to use PKCE

        Returns:
            A new SSO session ready for OIDC flow
        """
        session = SSOSession(
            tenant_id=tenant_id,
            idp_id=idp_id,
            redirect_uri=redirect_uri,
            relay_state=relay_state,
            nonce=secrets.token_urlsafe(32),
        )

        if use_pkce:
            session.code_verifier = generate_pkce_verifier()

        logger.debug(
            "oidc_session_created",
            session_id=session.id,
            tenant_id=tenant_id,
            idp_id=idp_id,
            use_pkce=use_pkce,
        )

        return session

    def generate_pkce_pair(self) -> tuple[str, str]:
        """Generate a PKCE code verifier and challenge pair.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        verifier = generate_pkce_verifier()
        challenge = generate_pkce_challenge(verifier, self.settings.pkce_method)
        return verifier, challenge

    async def discover_configuration(self) -> dict[str, Any]:
        """Discover OIDC configuration from the well-known endpoint.

        Returns:
            OIDC configuration dictionary

        Raises:
            httpx.HTTPStatusError: If discovery fails
        """
        if self._discovered_config:
            return self._discovered_config

        discovery_url = (
            f"{self.settings.issuer.rstrip('/')}/.well-known/openid-configuration"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            self._discovered_config = response.json()

        logger.debug(
            "oidc_config_discovered",
            issuer=self.settings.issuer,
            endpoints=list(self._discovered_config.keys()),
        )

        return self._discovered_config

    async def _get_authorization_endpoint(self) -> str:
        """Get the authorization endpoint URL."""
        if self.settings.authorization_endpoint:
            return self.settings.authorization_endpoint

        config = await self.discover_configuration()
        return config["authorization_endpoint"]

    async def _get_token_endpoint(self) -> str:
        """Get the token endpoint URL."""
        if self.settings.token_endpoint:
            return self.settings.token_endpoint

        config = await self.discover_configuration()
        return config["token_endpoint"]

    async def _get_userinfo_endpoint(self) -> str:
        """Get the userinfo endpoint URL."""
        if self.settings.userinfo_endpoint:
            return self.settings.userinfo_endpoint

        config = await self.discover_configuration()
        return config["userinfo_endpoint"]

    async def _get_jwks_uri(self) -> str:
        """Get the JWKS URI."""
        if self.settings.jwks_uri:
            return self.settings.jwks_uri

        config = await self.discover_configuration()
        return config["jwks_uri"]

    async def generate_auth_url(self, session: SSOSession) -> str:
        """Generate the OIDC authorization URL.

        Args:
            session: SSO session with state and nonce

        Returns:
            URL to redirect the user to for authentication
        """
        auth_endpoint = await self._get_authorization_endpoint()

        params = {
            "client_id": self.settings.client_id,
            "response_type": "code",
            "redirect_uri": session.redirect_uri,
            "scope": " ".join(self.settings.scopes),
            "state": session.state,
            "nonce": session.nonce,
        }

        # Add PKCE challenge if enabled
        if self.settings.use_pkce and session.code_verifier:
            challenge = generate_pkce_challenge(
                session.code_verifier,
                self.settings.pkce_method,
            )
            params["code_challenge"] = challenge
            params["code_challenge_method"] = self.settings.pkce_method

        auth_url = f"{auth_endpoint}?{urlencode(params)}"

        logger.debug(
            "oidc_auth_url_generated",
            idp_id=self.idp.id,
            auth_endpoint=auth_endpoint,
        )

        return auth_url

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens.

        Args:
            code: Authorization code from the callback
            redirect_uri: The redirect URI used in the auth request
            code_verifier: PKCE code verifier (if PKCE was used)

        Returns:
            Token response containing access_token, id_token, etc.
        """
        token_endpoint = await self._get_token_endpoint()

        data = {
            "grant_type": "authorization_code",
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        if code_verifier:
            data["code_verifier"] = code_verifier

        async with httpx.AsyncClient() as client:
            response = await client.post(token_endpoint, data=data)
            response.raise_for_status()
            tokens = response.json()

        logger.debug(
            "oidc_code_exchanged",
            idp_id=self.idp.id,
            has_id_token="id_token" in tokens,
            has_refresh_token="refresh_token" in tokens,
        )

        return tokens

    async def validate_id_token(
        self,
        id_token: str,
        nonce: str | None = None,
    ) -> dict[str, Any]:
        """Validate and decode an ID token.

        Args:
            id_token: The JWT ID token
            nonce: Expected nonce value for validation

        Returns:
            Decoded token claims

        Raises:
            ValueError: If token validation fails
        """
        # Decode the token (in production, use proper JWT validation with JWKS)
        # For now, we'll do basic validation
        try:
            parts = id_token.split(".")
            if len(parts) != 3:
                raise ValueError("Invalid ID token format")

            # Decode payload (base64url)
            payload = parts[1]
            # Add padding if needed
            payload += "=" * (4 - len(payload) % 4)
            claims = __import__("json").loads(
                base64.urlsafe_b64decode(payload).decode("utf-8")
            )

            # Validate issuer
            if claims.get("iss") != self.settings.issuer:
                raise ValueError(
                    f"Invalid issuer: {claims.get('iss')} != {self.settings.issuer}"
                )

            # Validate audience
            aud = claims.get("aud")
            if isinstance(aud, list):
                if self.settings.client_id not in aud:
                    raise ValueError("Client ID not in audience")
            elif aud != self.settings.client_id:
                raise ValueError(
                    f"Invalid audience: {aud} != {self.settings.client_id}"
                )

            # Validate nonce if provided
            if nonce and claims.get("nonce") != nonce:
                raise ValueError("Invalid nonce")

            # Validate expiration
            exp = claims.get("exp")
            if exp and datetime.now(UTC).timestamp() > exp:
                raise ValueError("ID token has expired")

            logger.debug(
                "oidc_id_token_validated",
                idp_id=self.idp.id,
                subject=claims.get("sub"),
            )

            return claims

        except Exception as e:
            logger.error("oidc_id_token_validation_failed", error=str(e))
            raise ValueError(f"ID token validation failed: {e}")

    async def get_userinfo(self, access_token: str) -> dict[str, Any]:
        """Fetch user information from the userinfo endpoint.

        Args:
            access_token: Access token from token exchange

        Returns:
            User information claims
        """
        userinfo_endpoint = await self._get_userinfo_endpoint()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            userinfo = response.json()

        logger.debug(
            "oidc_userinfo_fetched",
            idp_id=self.idp.id,
            claims=list(userinfo.keys()),
        )

        return userinfo

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh tokens using a refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            New token response
        """
        token_endpoint = await self._get_token_endpoint()

        data = {
            "grant_type": "refresh_token",
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "refresh_token": refresh_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_endpoint, data=data)
            response.raise_for_status()
            tokens = response.json()

        logger.debug(
            "oidc_token_refreshed",
            idp_id=self.idp.id,
        )

        return tokens

    async def process_response(
        self,
        response_data: dict[str, Any],
        session: SSOSession,
    ) -> SSOUserInfo:
        """Process the OIDC callback response.

        Args:
            response_data: Dict with 'code' from callback
            session: SSO session for validation

        Returns:
            User information extracted from tokens
        """
        code = response_data.get("code")
        if not code:
            raise ValueError("No authorization code in response")

        # Exchange code for tokens
        tokens = await self.exchange_code(
            code=code,
            redirect_uri=session.redirect_uri,
            code_verifier=session.code_verifier,
        )

        # Get claims from ID token or userinfo
        claims = {}

        if "id_token" in tokens:
            claims = await self.validate_id_token(
                tokens["id_token"],
                nonce=session.nonce,
            )

        # Optionally fetch additional info from userinfo endpoint
        if "access_token" in tokens:
            try:
                userinfo = await self.get_userinfo(tokens["access_token"])
                claims.update(userinfo)
            except Exception as e:
                logger.warning("oidc_userinfo_fetch_failed", error=str(e))

        return self._map_claims_to_user(claims)

    def _map_claims_to_user(self, claims: dict[str, Any]) -> SSOUserInfo:
        """Map OIDC claims to SSOUserInfo.

        Args:
            claims: OIDC claims from ID token and/or userinfo

        Returns:
            SSOUserInfo with mapped claims

        Raises:
            ValueError: If required claims are missing
        """
        mapping = self.settings.claim_mapping

        # Get subject (required)
        subject_id = claims.get("sub")
        if not subject_id:
            raise ValueError("No subject claim (sub) in ID token")

        # Get email (required)
        email_claim = mapping.get("email", "email")
        email = claims.get(email_claim)
        if not email:
            raise ValueError(f"No email claim ({email_claim}) in ID token")

        # Get optional claims
        name_claim = mapping.get("name", "name")
        given_name_claim = mapping.get("given_name", "given_name")
        family_name_claim = mapping.get("family_name", "family_name")
        groups_claim = mapping.get("groups", "groups")

        # Extract groups (handle both list and string)
        groups_raw = claims.get(groups_claim, [])
        if isinstance(groups_raw, str):
            groups = [groups_raw]
        else:
            groups = list(groups_raw) if groups_raw else []

        return SSOUserInfo(
            subject_id=str(subject_id),
            email=email,
            email_verified=claims.get("email_verified", False),
            name=claims.get(name_claim),
            first_name=claims.get(given_name_claim),
            last_name=claims.get(family_name_claim),
            avatar_url=claims.get("picture"),
            groups=groups,
            raw_attributes=claims,
        )


def get_oidc_preset(provider_type: str) -> dict[str, Any]:
    """Get OIDC configuration preset for a known provider.

    Args:
        provider_type: Provider type (google, okta, azure_ad, auth0)

    Returns:
        Configuration preset dictionary
    """
    return OIDC_PROVIDER_PRESETS.get(provider_type, {})
