"""Data models for authentication and multi-tenancy."""

import secrets
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PlanTier(str, Enum):
    """Subscription plan tiers."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Tenant(BaseModel):
    """A tenant/organization in the system."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    name: str
    slug: str  # URL-friendly identifier
    plan: PlanTier = PlanTier.FREE

    # Billing
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    # Limits based on plan
    max_incidents_per_month: int = 50  # Free tier default
    max_users: int = 5
    max_integrations: int = 3

    # Usage tracking
    incidents_this_month: int = 0
    billing_cycle_start: datetime = Field(default_factory=datetime.utcnow)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Integration configs (encrypted in production)
    integrations: dict = Field(default_factory=dict)
    # Example:
    # {
    #     "pagerduty": {"api_key": "...", "webhook_secret": "..."},
    #     "github": {"token": "...", "org": "..."},
    #     "datadog": {"api_key": "...", "app_key": "..."},
    #     "slack": {"bot_token": "...", "default_channel": "..."},
    # }

    def has_integration(self, name: str) -> bool:
        """Check if tenant has a specific integration configured."""
        return name in self.integrations and bool(self.integrations[name])

    def can_create_incident(self) -> bool:
        """Check if tenant can create more incidents this month."""
        return self.incidents_this_month < self.max_incidents_per_month

    def reset_monthly_usage(self) -> None:
        """Reset monthly usage counters."""
        self.incidents_this_month = 0
        self.billing_cycle_start = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class UserRole(str, Enum):
    """User roles within a tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(BaseModel):
    """A user in the system."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    email: str
    name: str
    avatar_url: Optional[str] = None

    # Tenant membership
    tenant_id: str
    role: UserRole = UserRole.MEMBER

    # OAuth provider info
    oauth_provider: Optional[str] = None  # "github", "google", etc.
    oauth_id: Optional[str] = None

    # Password auth (hashed, optional if using OAuth only)
    password_hash: Optional[str] = None

    # Status
    email_verified: bool = False
    is_active: bool = True

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

    def can_manage_integrations(self) -> bool:
        """Check if user can manage integrations."""
        return self.role in [UserRole.OWNER, UserRole.ADMIN]

    def can_invite_users(self) -> bool:
        """Check if user can invite other users."""
        return self.role in [UserRole.OWNER, UserRole.ADMIN]

    def can_manage_billing(self) -> bool:
        """Check if user can manage billing."""
        return self.role == UserRole.OWNER


class APIKey(BaseModel):
    """An API key for programmatic access."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    tenant_id: str
    created_by: str  # User ID

    name: str  # Human-friendly name
    key_prefix: str  # First 8 chars of key for identification
    key_hash: str  # Hashed full key

    # Permissions
    scopes: list[str] = Field(default_factory=lambda: ["read", "write"])

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True

    @classmethod
    def generate(
        cls, tenant_id: str, created_by: str, name: str, scopes: list[str] = None
    ) -> tuple["APIKey", str]:
        """Generate a new API key, returning the model and the raw key."""
        import hashlib

        raw_key = f"ic_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        api_key = cls(
            tenant_id=tenant_id,
            created_by=created_by,
            name=name,
            key_prefix=raw_key[:12],
            key_hash=key_hash,
            scopes=scopes or ["read", "write"],
        )

        return api_key, raw_key


class Session(BaseModel):
    """A user session."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    user_id: str
    tenant_id: str

    # Token info
    access_token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    refresh_token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # Expiry
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(hours=24)
    )
    refresh_expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(days=30)
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

    def is_expired(self) -> bool:
        """Check if session is expired."""
        return datetime.utcnow() > self.expires_at

    def is_refresh_expired(self) -> bool:
        """Check if refresh token is expired."""
        return datetime.utcnow() > self.refresh_expires_at

    def refresh(self) -> None:
        """Refresh the session, extending expiry."""
        self.access_token = secrets.token_urlsafe(32)
        self.expires_at = datetime.utcnow() + timedelta(hours=24)


# Plan limits configuration
PLAN_LIMITS = {
    PlanTier.FREE: {
        "max_incidents_per_month": 50,
        "max_users": 3,
        "max_integrations": 3,
        "features": ["basic_context", "slack_delivery"],
    },
    PlanTier.STARTER: {
        "max_incidents_per_month": 500,
        "max_users": 10,
        "max_integrations": 5,
        "features": [
            "basic_context",
            "slack_delivery",
            "ai_summaries",
            "past_incidents",
        ],
    },
    PlanTier.PRO: {
        "max_incidents_per_month": 2000,
        "max_users": 50,
        "max_integrations": 10,
        "features": [
            "basic_context",
            "slack_delivery",
            "ai_summaries",
            "past_incidents",
            "runbook_linking",
            "analytics",
        ],
    },
    PlanTier.ENTERPRISE: {
        "max_incidents_per_month": -1,  # Unlimited
        "max_users": -1,
        "max_integrations": -1,
        "features": ["all"],
    },
}
