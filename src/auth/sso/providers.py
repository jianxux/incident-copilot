"""Base provider classes and utilities for SSO authentication."""

import base64
import hashlib
import secrets
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import structlog

from .models import IdentityProvider, SSOSession, SSOUserInfo

logger = structlog.get_logger()


class BaseProvider(ABC):
    """Base class for SSO identity providers."""

    def __init__(self, idp: IdentityProvider, app_url: str):
        """Initialize the provider.
        
        Args:
            idp: Identity provider configuration
            app_url: Base URL of the application (e.g., https://app.example.com)
        """
        self.idp = idp
        self.app_url = app_url.rstrip("/")

    @abstractmethod
    async def generate_auth_url(self, session: SSOSession) -> str:
        """Generate the authentication URL to redirect the user.
        
        Args:
            session: SSO session containing state, nonce, etc.
            
        Returns:
            URL to redirect the user to for authentication
        """
        pass

    @abstractmethod
    async def process_response(
        self, response_data: dict[str, Any], session: SSOSession
    ) -> SSOUserInfo:
        """Process the authentication response from the IdP.
        
        Args:
            response_data: Response data from the IdP (SAML response, OIDC tokens, etc.)
            session: SSO session for validation
            
        Returns:
            User information extracted from the response
        """
        pass

    def _generate_state(self) -> str:
        """Generate a secure random state parameter."""
        return secrets.token_urlsafe(32)

    def _generate_nonce(self) -> str:
        """Generate a secure random nonce."""
        return secrets.token_urlsafe(32)


def generate_pkce_verifier() -> str:
    """Generate a PKCE code verifier (43-128 characters).
    
    Returns:
        A URL-safe random string for use as a code verifier.
    """
    return secrets.token_urlsafe(64)[:96]


def generate_pkce_challenge(verifier: str, method: str = "S256") -> str:
    """Generate a PKCE code challenge from a verifier.
    
    Args:
        verifier: The code verifier string
        method: Challenge method ('S256' or 'plain')
        
    Returns:
        The code challenge string
    """
    if method == "plain":
        return verifier
    
    # S256: BASE64URL(SHA256(verifier))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return challenge


def create_sso_session(
    tenant_id: str,
    idp_id: str,
    redirect_uri: str | None = None,
    relay_state: str | None = None,
    use_pkce: bool = True,
) -> SSOSession:
    """Create an SSO session for authentication.
    
    Args:
        tenant_id: Tenant ID
        idp_id: Identity provider ID
        redirect_uri: OAuth redirect URI
        relay_state: URL to return to after authentication
        use_pkce: Whether to generate PKCE parameters
        
    Returns:
        A new SSO session with all required parameters
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
        "sso_session_created",
        session_id=session.id,
        tenant_id=tenant_id,
        idp_id=idp_id,
    )
    
    return session
