"""Authentication service for user and session management."""

import hashlib
from datetime import datetime, UTC

import structlog

from ..db.supabase_db import get_db
from ..supabase_client import is_supabase_db_enabled
from .models import PLAN_LIMITS, APIKey, PlanTier, Session, Tenant, User, UserRole

logger = structlog.get_logger()


class AuthService:
    """Service for authentication and tenant management."""

    def __init__(self):
        # In-memory stores (replace with database in production)
        self._tenants: dict[str, Tenant] = {}
        self._users: dict[str, User] = {}
        self._sessions: dict[str, Session] = {}
        self._api_keys: dict[str, APIKey] = {}

        # Indexes for lookups
        self._user_by_email: dict[str, str] = {}  # email -> user_id
        self._tenant_by_slug: dict[str, str] = {}  # slug -> tenant_id
        self._session_by_token: dict[str, str] = {}  # access_token -> session_id
        self._api_key_by_hash: dict[str, str] = {}  # key_hash -> api_key_id

    def _cache_tenant(self, tenant: Tenant) -> Tenant:
        """Update in-memory tenant cache."""
        self._tenants[tenant.id] = tenant
        self._tenant_by_slug[tenant.slug] = tenant.id
        return tenant

    def _tenant_from_row(self, row: dict) -> Tenant:
        """Convert Supabase tenant row to Tenant model."""
        payload = dict(row)
        payload["integrations"] = payload.get("integrations") or {}
        if payload.get("plan"):
            payload["plan"] = PlanTier(payload["plan"])
        tenant = Tenant.model_validate(payload)
        return self._cache_tenant(tenant)

    def _tenant_to_row(self, tenant: Tenant) -> dict:
        """Convert Tenant model to Supabase row payload."""
        return tenant.model_dump(mode="json")

    # --- Tenant Management ---

    async def create_tenant(
        self,
        name: str,
        slug: str,
        plan: PlanTier = PlanTier.FREE,
    ) -> Tenant:
        """Create a new tenant."""
        if is_supabase_db_enabled():
            db = get_db()
            existing = await db.get_tenant_by_slug(slug)
            if existing:
                raise ValueError(f"Tenant with slug '{slug}' already exists")

            limits = PLAN_LIMITS[plan]
            tenant = Tenant(
                name=name,
                slug=slug,
                plan=plan,
                max_incidents_per_month=limits["max_incidents_per_month"],
                max_users=limits["max_users"],
                max_integrations=limits["max_integrations"],
            )
            row = self._tenant_to_row(tenant)
            created = await db.create_tenant(
                name=tenant.name,
                slug=tenant.slug,
                plan=tenant.plan.value,
                **{k: v for k, v in row.items() if k not in {"name", "slug", "plan"}},
            )
            tenant = self._tenant_from_row(created or row)
            logger.info("tenant_created", tenant_id=tenant.id, name=name, plan=plan)
            return tenant

        if slug in self._tenant_by_slug:
            raise ValueError(f"Tenant with slug '{slug}' already exists")

        limits = PLAN_LIMITS[plan]
        tenant = Tenant(
            name=name,
            slug=slug,
            plan=plan,
            max_incidents_per_month=limits["max_incidents_per_month"],
            max_users=limits["max_users"],
            max_integrations=limits["max_integrations"],
        )

        self._cache_tenant(tenant)

        logger.info("tenant_created", tenant_id=tenant.id, name=name, plan=plan)
        return tenant

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by ID."""
        cached = self._tenants.get(tenant_id)
        if cached:
            return cached

        if is_supabase_db_enabled():
            row = await get_db().get_tenant(tenant_id)
            if row:
                return self._tenant_from_row(row)
            return None

        return None

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        """Get a tenant by slug."""
        tenant_id = self._tenant_by_slug.get(slug)
        if tenant_id:
            return self._tenants.get(tenant_id)

        if is_supabase_db_enabled():
            row = await get_db().get_tenant_by_slug(slug)
            if row:
                return self._tenant_from_row(row)
        return None

    async def update_tenant_plan(self, tenant_id: str, plan: PlanTier) -> Tenant:
        """Update a tenant's plan."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        limits = PLAN_LIMITS[plan]
        tenant.plan = plan
        tenant.max_incidents_per_month = limits["max_incidents_per_month"]
        tenant.max_users = limits["max_users"]
        tenant.max_integrations = limits["max_integrations"]
        tenant.updated_at = datetime.now(UTC)

        if is_supabase_db_enabled():
            row = await get_db().update_tenant(
                tenant_id,
                plan=tenant.plan.value,
                max_incidents_per_month=tenant.max_incidents_per_month,
                max_users=tenant.max_users,
                max_integrations=tenant.max_integrations,
            )
            if not row:
                raise ValueError(f"Tenant {tenant_id} not found")
            tenant = self._tenant_from_row(row)
        else:
            self._cache_tenant(tenant)

        logger.info("tenant_plan_updated", tenant_id=tenant_id, new_plan=plan)
        return tenant

    async def update_tenant_integrations(
        self,
        tenant_id: str,
        integrations: dict,
    ) -> Tenant:
        """Update tenant's integration configurations."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        merged_integrations = {**tenant.integrations, **integrations}
        tenant.integrations = merged_integrations
        tenant.updated_at = datetime.now(UTC)

        if is_supabase_db_enabled():
            row = await get_db().update_tenant(
                tenant_id, integrations=merged_integrations
            )
            if not row:
                raise ValueError(f"Tenant {tenant_id} not found")
            tenant = self._tenant_from_row(row)
        else:
            self._cache_tenant(tenant)

        logger.info(
            "tenant_integrations_updated",
            tenant_id=tenant_id,
            integrations=list(integrations.keys()),
        )
        return tenant

    async def increment_tenant_usage(self, tenant_id: str) -> bool:
        """Increment incident count for a tenant. Returns False if limit reached."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return False

        if not tenant.can_create_incident():
            logger.warning(
                "tenant_usage_limit_reached",
                tenant_id=tenant_id,
                current=tenant.incidents_this_month,
                limit=tenant.max_incidents_per_month,
            )
            return False

        tenant.incidents_this_month += 1
        tenant.updated_at = datetime.now(UTC)
        return True

    # --- User Management ---

    async def create_user(
        self,
        email: str,
        name: str,
        tenant_id: str,
        role: UserRole = UserRole.MEMBER,
        oauth_provider: str | None = None,
        oauth_id: str | None = None,
        password: str | None = None,
    ) -> User:
        """Create a new user."""
        if email in self._user_by_email:
            raise ValueError(f"User with email '{email}' already exists")

        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        # Check user limit
        tenant_users = [u for u in self._users.values() if u.tenant_id == tenant_id]
        if tenant.max_users > 0 and len(tenant_users) >= tenant.max_users:
            raise ValueError(
                f"Tenant has reached maximum user limit ({tenant.max_users})"
            )

        password_hash = None
        if password:
            password_hash = hashlib.sha256(password.encode()).hexdigest()

        user = User(
            email=email,
            name=name,
            tenant_id=tenant_id,
            role=role,
            oauth_provider=oauth_provider,
            oauth_id=oauth_id,
            password_hash=password_hash,
            email_verified=bool(oauth_provider),  # OAuth users are pre-verified
        )

        self._users[user.id] = user
        self._user_by_email[email] = user.id

        logger.info("user_created", user_id=user.id, email=email, tenant_id=tenant_id)
        return user

    async def get_user(self, user_id: str) -> User | None:
        """Get a user by ID."""
        return self._users.get(user_id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email."""
        user_id = self._user_by_email.get(email)
        if user_id:
            return self._users.get(user_id)
        return None

    async def get_or_create_oauth_user(
        self,
        email: str,
        name: str,
        oauth_provider: str,
        oauth_id: str,
        avatar_url: str | None = None,
    ) -> tuple[User, Tenant, bool]:
        """Get or create a user from OAuth login. Returns (user, tenant, is_new)."""
        existing = await self.get_user_by_email(email)

        if existing:
            # Update OAuth info if needed
            existing.oauth_provider = oauth_provider
            existing.oauth_id = oauth_id
            if avatar_url:
                existing.avatar_url = avatar_url
            existing.last_login = datetime.now(UTC)

            tenant = await self.get_tenant(existing.tenant_id)
            return existing, tenant, False

        # Create new tenant and user
        slug = email.split("@")[0].lower().replace(".", "-")
        # Make slug unique
        base_slug = slug
        counter = 1
        while slug in self._tenant_by_slug:
            slug = f"{base_slug}-{counter}"
            counter += 1

        tenant = await self.create_tenant(
            name=f"{name}'s Team",
            slug=slug,
        )

        user = await self.create_user(
            email=email,
            name=name,
            tenant_id=tenant.id,
            role=UserRole.OWNER,
            oauth_provider=oauth_provider,
            oauth_id=oauth_id,
        )
        user.avatar_url = avatar_url
        user.last_login = datetime.now(UTC)

        return user, tenant, True

    async def verify_password(self, email: str, password: str) -> User | None:
        """Verify password and return user if valid."""
        user = await self.get_user_by_email(email)
        if not user or not user.password_hash:
            return None

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash != user.password_hash:
            return None

        user.last_login = datetime.now(UTC)
        return user

    # --- Session Management ---

    async def create_session(
        self,
        user_id: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> Session:
        """Create a new session for a user."""
        user = await self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        session = Session(
            user_id=user_id,
            tenant_id=user.tenant_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        self._sessions[session.id] = session
        self._session_by_token[session.access_token] = session.id

        logger.info("session_created", session_id=session.id, user_id=user_id)
        return session

    async def get_session_by_token(self, access_token: str) -> Session | None:
        """Get a session by access token."""
        session_id = self._session_by_token.get(access_token)
        if session_id:
            session = self._sessions.get(session_id)
            if session and not session.is_expired():
                return session
        return None

    async def refresh_session(self, refresh_token: str) -> Session | None:
        """Refresh a session using refresh token."""
        for session in self._sessions.values():
            if session.refresh_token == refresh_token:
                if session.is_refresh_expired():
                    return None

                # Remove old token mapping
                self._session_by_token.pop(session.access_token, None)

                # Refresh
                session.refresh()
                self._session_by_token[session.access_token] = session.id

                logger.info("session_refreshed", session_id=session.id)
                return session
        return None

    async def invalidate_session(self, session_id: str) -> None:
        """Invalidate a session."""
        session = self._sessions.get(session_id)
        if session:
            self._session_by_token.pop(session.access_token, None)
            del self._sessions[session_id]
            logger.info("session_invalidated", session_id=session_id)

    # --- API Key Management ---

    async def create_api_key(
        self,
        tenant_id: str,
        created_by: str,
        name: str,
        scopes: list[str] = None,
    ) -> tuple[APIKey, str]:
        """Create a new API key. Returns (api_key, raw_key)."""
        api_key, raw_key = APIKey.generate(
            tenant_id=tenant_id,
            created_by=created_by,
            name=name,
            scopes=scopes,
        )

        self._api_keys[api_key.id] = api_key
        self._api_key_by_hash[api_key.key_hash] = api_key.id

        logger.info(
            "api_key_created",
            api_key_id=api_key.id,
            tenant_id=tenant_id,
            name=name,
        )
        return api_key, raw_key

    async def verify_api_key(self, raw_key: str) -> tuple[APIKey, Tenant] | None:
        """Verify an API key and return the key and tenant if valid."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        api_key_id = self._api_key_by_hash.get(key_hash)

        if not api_key_id:
            return None

        api_key = self._api_keys.get(api_key_id)
        if not api_key or not api_key.is_active:
            return None

        if api_key.expires_at and datetime.now(UTC) > api_key.expires_at:
            return None

        tenant = await self.get_tenant(api_key.tenant_id)
        if not tenant:
            return None

        api_key.last_used = datetime.now(UTC)
        return api_key, tenant

    async def revoke_api_key(self, api_key_id: str) -> None:
        """Revoke an API key."""
        api_key = self._api_keys.get(api_key_id)
        if api_key:
            api_key.is_active = False
            logger.info("api_key_revoked", api_key_id=api_key_id)


# Global auth service instance
auth_service = AuthService()
