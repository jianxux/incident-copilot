"""Supabase Auth integration for Incident Copilot.

This module provides Google SSO and other OAuth flows via Supabase Auth,
which handles token management, session refresh, and user management.
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from ..config import get_settings
from ..supabase_client import (
    get_supabase_client,
    is_supabase_auth_enabled,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/auth/supabase", tags=["supabase-auth"])


class SignupRequest(BaseModel):
    """Email/password signup request."""

    email: EmailStr
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    """Email/password login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Supabase auth token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


def _check_supabase_auth():
    """Check if Supabase Auth is enabled."""
    if not is_supabase_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Supabase Auth is not enabled. Set SUPABASE_AUTH_ENABLED=true",
        )


@router.get("/providers")
async def list_providers():
    """List available Supabase OAuth providers."""
    _check_supabase_auth()

    # These are the providers we support via Supabase
    # Actual availability depends on Supabase project configuration
    return {
        "providers": ["google", "github", "microsoft", "slack"],
        "backend": "supabase",
    }


@router.post("/signup")
async def signup(request: SignupRequest):
    """Create a new account with email/password via Supabase."""
    _check_supabase_auth()

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase client not available",
        )

    try:
        response = client.auth.sign_up(
            {
                "email": request.email,
                "password": request.password,
                "options": {
                    "data": {
                        "name": request.name,
                    }
                },
            }
        )

        if response.user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signup failed - check if email confirmation is required",
            )

        session = response.session
        if session is None:
            # Email confirmation required
            return {
                "status": "confirmation_required",
                "message": "Please check your email to confirm your account",
                "user": {
                    "id": response.user.id,
                    "email": response.user.email,
                },
            }

        return TokenResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            expires_in=session.expires_in or 3600,
            user={
                "id": response.user.id,
                "email": response.user.email,
                "name": response.user.user_metadata.get("name"),
            },
        )

    except Exception as e:
        logger.error("supabase_signup_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login")
async def login(request: LoginRequest):
    """Login with email/password via Supabase."""
    _check_supabase_auth()

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase client not available",
        )

    try:
        response = client.auth.sign_in_with_password(
            {
                "email": request.email,
                "password": request.password,
            }
        )

        if response.user is None or response.session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in or 3600,
            user={
                "id": response.user.id,
                "email": response.user.email,
                "name": response.user.user_metadata.get("name"),
                "avatar_url": response.user.user_metadata.get("avatar_url"),
            },
        )

    except Exception as e:
        logger.error("supabase_login_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )


@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    """Refresh the access token using a refresh token."""
    _check_supabase_auth()

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase client not available",
        )

    try:
        response = client.auth.refresh_session(request.refresh_token)

        if response.user is None or response.session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )

        return TokenResponse(
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token,
            expires_in=response.session.expires_in or 3600,
            user={
                "id": response.user.id,
                "email": response.user.email,
                "name": response.user.user_metadata.get("name"),
                "avatar_url": response.user.user_metadata.get("avatar_url"),
            },
        )

    except Exception as e:
        logger.error("supabase_refresh_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )


@router.post("/logout")
async def logout():
    """Logout the current user."""
    _check_supabase_auth()

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase client not available",
        )

    try:
        client.auth.sign_out()
        return {"status": "ok"}
    except Exception as e:
        logger.warning("supabase_logout_error", error=str(e))
        # Logout errors are non-critical
        return {"status": "ok"}


@router.get("/oauth/{provider}")
async def oauth_start(provider: str, request: Request):
    """Start OAuth flow via Supabase (Google, GitHub, etc.)."""
    _check_supabase_auth()

    settings = get_settings()
    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase client not available",
        )

    # Validate provider
    valid_providers = ["google", "github", "azure", "microsoft", "slack", "gitlab"]
    if provider not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OAuth provider: {provider}. Valid: {valid_providers}",
        )

    redirect_uri = f"{settings.app_url}/api/auth/supabase/callback"

    try:
        response = client.auth.sign_in_with_oauth(
            {
                "provider": provider,
                "options": {
                    "redirect_to": redirect_uri,
                },
            }
        )

        if response.url:
            return RedirectResponse(url=response.url)
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate OAuth URL",
            )

    except Exception as e:
        logger.error("supabase_oauth_start_error", provider=provider, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth initialization failed: {str(e)}",
        )


@router.get("/callback")
async def oauth_callback(
    request: Request,
    access_token: str | None = None,
    refresh_token: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Handle OAuth callback from Supabase.

    Supabase redirects here with tokens in URL fragment (#) for implicit flow,
    or with code for PKCE flow. This endpoint handles the server-side processing.
    """
    _check_supabase_auth()

    settings = get_settings()

    if error:
        logger.warning(
            "supabase_oauth_callback_error",
            error=error,
            description=error_description,
        )
        return RedirectResponse(url=f"{settings.app_url}/login?error={error}")

    # For token-based callback (implicit flow)
    if access_token and refresh_token:
        # Redirect to dashboard with tokens
        # The frontend will store these and use them
        redirect_url = (
            f"{settings.app_url}/dashboard"
            f"#access_token={access_token}"
            f"&refresh_token={refresh_token}"
        )
        return RedirectResponse(url=redirect_url)

    # For PKCE flow, Supabase handles the code exchange
    # and returns tokens in the URL fragment
    # Redirect to a page that can handle the fragment
    return RedirectResponse(
        url=f"{settings.app_url}/auth/callback{request.url.fragment or ''}"
    )


@router.get("/user")
async def get_current_user(request: Request):
    """Get the current authenticated user from Supabase."""
    _check_supabase_auth()

    # Get token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth_header.split(" ")[1]

    client = get_supabase_client()
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase client not available",
        )

    try:
        response = client.auth.get_user(token)

        if response.user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        return {
            "user": {
                "id": response.user.id,
                "email": response.user.email,
                "name": response.user.user_metadata.get("name"),
                "avatar_url": response.user.user_metadata.get("avatar_url"),
                "provider": response.user.app_metadata.get("provider"),
            },
        }

    except Exception as e:
        logger.error("supabase_get_user_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
