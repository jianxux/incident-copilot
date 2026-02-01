"""API routes for authentication."""

import secrets
from typing import Optional

import structlog
from fastapi import (APIRouter, Depends, HTTPException, Request, Response,
                     status)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from ..config import get_settings
from .middleware import AuthContext, get_auth_context, get_current_user
from .models import Session, Tenant, User, UserRole
from .oauth import OAuthProvider, get_available_providers, get_oauth_provider
from .service import auth_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory OAuth state storage (use Redis in production)
_oauth_states: dict[str, dict] = {}


class SignupRequest(BaseModel):
    """Request to create a new account."""

    email: EmailStr
    password: str
    name: str
    company: Optional[str] = None


class LoginRequest(BaseModel):
    """Request to login with email/password."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Authentication token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours
    user: dict
    tenant: dict


class RefreshRequest(BaseModel):
    """Request to refresh access token."""

    refresh_token: str


@router.get("/providers")
async def list_providers():
    """List available OAuth providers."""
    return {
        "providers": get_available_providers(),
    }


@router.post("/signup")
async def signup(request: SignupRequest):
    """Create a new account with email/password."""
    # Check if user exists
    existing = await auth_service.get_user_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    # Create tenant
    slug = request.email.split("@")[0].lower().replace(".", "-")
    base_slug = slug
    counter = 1
    while await auth_service.get_tenant_by_slug(slug):
        slug = f"{base_slug}-{counter}"
        counter += 1

    tenant_name = request.company or f"{request.name}'s Team"
    tenant = await auth_service.create_tenant(
        name=tenant_name,
        slug=slug,
    )

    # Create user
    user = await auth_service.create_user(
        email=request.email,
        name=request.name,
        tenant_id=tenant.id,
        role=UserRole.OWNER,
        password=request.password,
    )

    # Create session
    session = await auth_service.create_session(user.id)

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
        },
        tenant={
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan.value,
        },
    )


@router.post("/login")
async def login(request: LoginRequest, req: Request):
    """Login with email/password."""
    user = await auth_service.verify_password(request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    tenant = await auth_service.get_tenant(user.tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant not found",
        )

    # Create session
    session = await auth_service.create_session(
        user.id,
        user_agent=req.headers.get("user-agent"),
        ip_address=req.client.host if req.client else None,
    )

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "avatar_url": user.avatar_url,
        },
        tenant={
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan.value,
        },
    )


@router.post("/refresh")
async def refresh_token(request: RefreshRequest):
    """Refresh access token using refresh token."""
    session = await auth_service.refresh_session(request.refresh_token)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await auth_service.get_user(session.user_id)
    tenant = await auth_service.get_tenant(session.tenant_id)

    return TokenResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "avatar_url": user.avatar_url,
        },
        tenant={
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan.value,
        },
    )


@router.post("/logout")
async def logout(auth: AuthContext = Depends(get_auth_context)):
    """Logout and invalidate session."""
    if auth.session:
        await auth_service.invalidate_session(auth.session.id)
    return {"status": "ok"}


@router.get("/me")
async def get_me(
    auth: AuthContext = Depends(get_auth_context),
    user: User = Depends(get_current_user),
):
    """Get current user info."""
    tenant = await auth_service.get_tenant(user.tenant_id)

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "avatar_url": user.avatar_url,
        },
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan.value,
        },
    }


# --- OAuth Routes ---


@router.get("/oauth/{provider}")
async def oauth_start(provider: str, request: Request):
    """Start OAuth flow by redirecting to provider."""
    oauth = get_oauth_provider(provider)
    if not oauth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{provider}' not configured",
        )

    settings = get_settings()
    state = OAuthProvider.generate_state()
    redirect_uri = f"{settings.app_url}/api/auth/oauth/{provider}/callback"

    # Store state for verification
    _oauth_states[state] = {
        "provider": provider,
        "redirect_uri": redirect_uri,
    }

    auth_url = oauth.get_authorization_url(state, redirect_uri)
    return RedirectResponse(url=auth_url)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle OAuth callback from provider."""
    settings = get_settings()

    if error:
        logger.warning("oauth_callback_error", provider=provider, error=error)
        return RedirectResponse(url=f"{settings.app_url}/login?error=oauth_denied")

    if not code or not state:
        return RedirectResponse(url=f"{settings.app_url}/login?error=oauth_invalid")

    # Verify state
    state_data = _oauth_states.pop(state, None)
    if not state_data or state_data["provider"] != provider:
        return RedirectResponse(
            url=f"{settings.app_url}/login?error=oauth_invalid_state"
        )

    oauth = get_oauth_provider(provider)
    if not oauth:
        return RedirectResponse(
            url=f"{settings.app_url}/login?error=oauth_not_configured"
        )

    # Exchange code for token
    access_token = await oauth.exchange_code(code, state_data["redirect_uri"])
    if not access_token:
        return RedirectResponse(
            url=f"{settings.app_url}/login?error=oauth_token_failed"
        )

    # Get user info
    oauth_user = await oauth.get_user_info(access_token)
    if not oauth_user:
        return RedirectResponse(url=f"{settings.app_url}/login?error=oauth_user_failed")

    # Get or create user
    user, tenant, is_new = await auth_service.get_or_create_oauth_user(
        email=oauth_user.email,
        name=oauth_user.name,
        oauth_provider=oauth_user.provider,
        oauth_id=oauth_user.id,
        avatar_url=oauth_user.avatar_url,
    )

    # Create session
    session = await auth_service.create_session(
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    # Redirect to dashboard with token in URL fragment (for SPA)
    # In production, use httpOnly cookies instead
    redirect_url = (
        f"{settings.app_url}/dashboard"
        f"#access_token={session.access_token}"
        f"&refresh_token={session.refresh_token}"
        f"&is_new={str(is_new).lower()}"
    )

    return RedirectResponse(url=redirect_url)
