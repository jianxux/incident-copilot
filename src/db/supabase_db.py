"""Supabase database operations for Incident Copilot.

This module provides database operations using Supabase's client library,
which wraps PostgreSQL with a REST API and real-time subscriptions.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from ..supabase_client import (
    get_supabase_admin_client,
    get_supabase_client,
    is_supabase_db_enabled,
)

logger = structlog.get_logger()


class SupabaseDB:
    """Database operations via Supabase.

    Provides CRUD operations for all incident copilot entities using
    Supabase's PostgREST API.
    """

    def __init__(self, use_admin: bool = False):
        """Initialize the database client.

        Args:
            use_admin: Use service role key for elevated permissions
        """
        self.use_admin = use_admin
        self._client = None

    @property
    def client(self):
        """Get the Supabase client (lazy initialization)."""
        if self._client is None:
            if self.use_admin:
                self._client = get_supabase_admin_client()
            else:
                self._client = get_supabase_client()
        return self._client

    def _check_enabled(self):
        """Check if Supabase DB is enabled."""
        if not is_supabase_db_enabled():
            raise RuntimeError(
                "Supabase DB is not enabled. Set SUPABASE_DB_ENABLED=true"
            )

    # ==================== Tenants ====================

    async def create_tenant(
        self,
        name: str,
        slug: str,
        plan: str = "free",
        **kwargs,
    ) -> dict:
        """Create a new tenant."""
        self._check_enabled()

        tenant = {
            "id": str(uuid4()),
            "name": name,
            "slug": slug,
            "plan": plan,
            "created_at": datetime.utcnow().isoformat(),
            **kwargs,
        }

        result = self.client.table("tenants").insert(tenant).execute()
        return result.data[0] if result.data else tenant

    async def get_tenant(self, tenant_id: str) -> dict | None:
        """Get a tenant by ID."""
        self._check_enabled()

        result = (
            self.client.table("tenants")
            .select("*")
            .eq("id", tenant_id)
            .single()
            .execute()
        )
        return result.data

    async def get_tenant_by_slug(self, slug: str) -> dict | None:
        """Get a tenant by slug."""
        self._check_enabled()

        result = (
            self.client.table("tenants")
            .select("*")
            .eq("slug", slug)
            .single()
            .execute()
        )
        return result.data

    async def update_tenant(self, tenant_id: str, **kwargs) -> dict | None:
        """Update a tenant."""
        self._check_enabled()

        kwargs["updated_at"] = datetime.utcnow().isoformat()
        result = (
            self.client.table("tenants")
            .update(kwargs)
            .eq("id", tenant_id)
            .execute()
        )
        return result.data[0] if result.data else None

    # ==================== Users ====================

    async def create_user(
        self,
        email: str,
        tenant_id: str,
        name: str | None = None,
        role: str = "member",
        **kwargs,
    ) -> dict:
        """Create a new user."""
        self._check_enabled()

        user = {
            "id": str(uuid4()),
            "email": email,
            "tenant_id": tenant_id,
            "name": name,
            "role": role,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            **kwargs,
        }

        result = self.client.table("users").insert(user).execute()
        return result.data[0] if result.data else user

    async def get_user(self, user_id: str) -> dict | None:
        """Get a user by ID."""
        self._check_enabled()

        result = (
            self.client.table("users")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return result.data

    async def get_user_by_email(self, email: str) -> dict | None:
        """Get a user by email."""
        self._check_enabled()

        result = (
            self.client.table("users")
            .select("*")
            .eq("email", email)
            .single()
            .execute()
        )
        return result.data

    async def update_user(self, user_id: str, **kwargs) -> dict | None:
        """Update a user."""
        self._check_enabled()

        kwargs["updated_at"] = datetime.utcnow().isoformat()
        result = (
            self.client.table("users")
            .update(kwargs)
            .eq("id", user_id)
            .execute()
        )
        return result.data[0] if result.data else None

    async def list_users(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List users in a tenant."""
        self._check_enabled()

        result = (
            self.client.table("users")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or []

    # ==================== Incidents ====================

    async def create_incident(
        self,
        tenant_id: str,
        title: str,
        source: str,
        source_id: str,
        severity: str = "unknown",
        status: str = "triggered",
        **kwargs,
    ) -> dict:
        """Create a new incident."""
        self._check_enabled()

        incident = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "title": title,
            "source": source,
            "source_id": source_id,
            "severity": severity,
            "status": status,
            "created_at": datetime.utcnow().isoformat(),
            **kwargs,
        }

        result = self.client.table("incidents").insert(incident).execute()
        return result.data[0] if result.data else incident

    async def get_incident(self, incident_id: str) -> dict | None:
        """Get an incident by ID."""
        self._check_enabled()

        result = (
            self.client.table("incidents")
            .select("*")
            .eq("id", incident_id)
            .single()
            .execute()
        )
        return result.data

    async def update_incident(self, incident_id: str, **kwargs) -> dict | None:
        """Update an incident."""
        self._check_enabled()

        kwargs["updated_at"] = datetime.utcnow().isoformat()
        result = (
            self.client.table("incidents")
            .update(kwargs)
            .eq("id", incident_id)
            .execute()
        )
        return result.data[0] if result.data else None

    async def list_incidents(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List incidents for a tenant."""
        self._check_enabled()

        query = (
            self.client.table("incidents")
            .select("*")
            .eq("tenant_id", tenant_id)
        )

        if status:
            query = query.eq("status", status)

        result = (
            query
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or []

    async def search_incidents(
        self,
        tenant_id: str,
        query: str,
        limit: int = 20,
    ) -> list[dict]:
        """Search incidents by title/description."""
        self._check_enabled()

        # Use Supabase full-text search if configured, otherwise ILIKE
        result = (
            self.client.table("incidents")
            .select("*")
            .eq("tenant_id", tenant_id)
            .ilike("title", f"%{query}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    # ==================== Context Cards ====================

    async def create_context_card(
        self,
        incident_id: str,
        tenant_id: str,
        data: dict,
        **kwargs,
    ) -> dict:
        """Create a context card for an incident."""
        self._check_enabled()

        card = {
            "id": str(uuid4()),
            "incident_id": incident_id,
            "tenant_id": tenant_id,
            "data": data,
            "created_at": datetime.utcnow().isoformat(),
            **kwargs,
        }

        result = self.client.table("context_cards").insert(card).execute()
        return result.data[0] if result.data else card

    async def get_context_card(self, incident_id: str) -> dict | None:
        """Get the context card for an incident."""
        self._check_enabled()

        result = (
            self.client.table("context_cards")
            .select("*")
            .eq("incident_id", incident_id)
            .order("created_at", desc=True)
            .limit(1)
            .single()
            .execute()
        )
        return result.data

    # ==================== Runbooks ====================

    async def create_runbook(
        self,
        tenant_id: str,
        title: str,
        content: str,
        source: str = "manual",
        **kwargs,
    ) -> dict:
        """Create a runbook."""
        self._check_enabled()

        runbook = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "title": title,
            "content": content,
            "source": source,
            "created_at": datetime.utcnow().isoformat(),
            **kwargs,
        }

        result = self.client.table("runbooks").insert(runbook).execute()
        return result.data[0] if result.data else runbook

    async def get_runbook(self, runbook_id: str) -> dict | None:
        """Get a runbook by ID."""
        self._check_enabled()

        result = (
            self.client.table("runbooks")
            .select("*")
            .eq("id", runbook_id)
            .single()
            .execute()
        )
        return result.data

    async def list_runbooks(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List runbooks for a tenant."""
        self._check_enabled()

        result = (
            self.client.table("runbooks")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("title")
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or []

    # ==================== Audit Logs ====================

    async def create_audit_log(
        self,
        tenant_id: str,
        user_id: str | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> dict:
        """Create an audit log entry."""
        self._check_enabled()

        log = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
            "ip_address": ip_address,
            "created_at": datetime.utcnow().isoformat(),
        }

        result = self.client.table("audit_logs").insert(log).execute()
        return result.data[0] if result.data else log

    async def list_audit_logs(
        self,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
        user_id: str | None = None,
        action: str | None = None,
    ) -> list[dict]:
        """List audit logs for a tenant."""
        self._check_enabled()

        query = (
            self.client.table("audit_logs")
            .select("*")
            .eq("tenant_id", tenant_id)
        )

        if user_id:
            query = query.eq("user_id", user_id)
        if action:
            query = query.eq("action", action)

        result = (
            query
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or []


# Singleton instance
_db: SupabaseDB | None = None


def get_db(use_admin: bool = False) -> SupabaseDB:
    """Get the database instance.

    Args:
        use_admin: Use service role key for elevated permissions

    Returns:
        SupabaseDB instance
    """
    global _db

    if use_admin:
        # Admin client is not cached
        return SupabaseDB(use_admin=True)

    if _db is None:
        _db = SupabaseDB(use_admin=False)

    return _db
