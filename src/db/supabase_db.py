"""Supabase database operations for Incident Copilot.

This module provides database operations using Supabase's client library,
which wraps PostgreSQL with a REST API and real-time subscriptions.
"""

import asyncio
from datetime import UTC, datetime
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

        if self._client is None:
            raise RuntimeError(
                "Supabase client not configured for this mode "
                f"(use_admin={self.use_admin}). Check SUPABASE_URL/keys."
            )

        return self._client

    async def _to_thread(self, fn, *args, **kwargs):
        """Run a synchronous Supabase call in a thread.

        Supabase Python client is synchronous; the rest of the app is async.
        """
        return await asyncio.to_thread(fn, *args, **kwargs)

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
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        result = self.client.table("tenants").insert(tenant).execute()
        return result.data[0] if result.data else tenant

    async def get_tenant(self, tenant_id: str) -> dict | None:
        """Get a tenant by ID."""
        self._check_enabled()

        try:
            result = (
                self.client.table("tenants")
                .select("*")
                .eq("id", tenant_id)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    async def get_tenant_by_slug(self, slug: str) -> dict | None:
        """Get a tenant by slug."""
        self._check_enabled()

        try:
            result = (
                self.client.table("tenants").select("*").eq("slug", slug).single().execute()
            )
            return result.data
        except Exception:
            return None

    async def update_tenant(self, tenant_id: str, **kwargs) -> dict | None:
        """Update a tenant."""
        self._check_enabled()

        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        result = (
            self.client.table("tenants").update(kwargs).eq("id", tenant_id).execute()
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
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        result = self.client.table("users").insert(user).execute()
        return result.data[0] if result.data else user

    async def get_user(self, user_id: str) -> dict | None:
        """Get a user by ID."""
        self._check_enabled()

        try:
            result = (
                self.client.table("users").select("*").eq("id", user_id).single().execute()
            )
            return result.data
        except Exception:
            return None

    async def get_user_by_email(self, email: str) -> dict | None:
        """Get a user by email."""
        self._check_enabled()

        try:
            result = (
                self.client.table("users").select("*").eq("email", email).single().execute()
            )
            return result.data
        except Exception:
            # .single() throws when 0 rows found — return None so callers
            # can auto-create the user profile.
            return None

    async def update_user(self, user_id: str, **kwargs) -> dict | None:
        """Update a user."""
        self._check_enabled()

        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        result = self.client.table("users").update(kwargs).eq("id", user_id).execute()
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

    # ==================== Tenants (helpers) ====================

    async def ensure_tenant(
        self,
        *,
        slug: str = "default",
        name: str = "Default Tenant",
        plan: str = "free",
    ) -> dict:
        """Ensure a tenant exists (by slug) and return it.

        Intended for server-side/demo usage when there is no end-user auth context.
        """
        self._check_enabled()

        def _get():
            return (
                self.client.table("tenants")
                .select("*")
                .eq("slug", slug)
                .single()
                .execute()
            )

        try:
            res = await self._to_thread(_get)
            if res.data:
                return res.data
        except Exception:
            # Not found / .single() error in PostgREST -> create
            pass

        tenant = {
            "id": str(uuid4()),
            "name": name,
            "slug": slug,
            "plan": plan,
            "created_at": datetime.now(UTC).isoformat(),
        }

        def _insert():
            return self.client.table("tenants").insert(tenant).execute()

        res = await self._to_thread(_insert)
        return res.data[0] if res.data else tenant

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
            "created_at": datetime.now(UTC).isoformat(),
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

        kwargs["updated_at"] = datetime.now(UTC).isoformat()

        def _do():
            return (
                self.client.table("incidents")
                .update(kwargs)
                .eq("id", incident_id)
                .execute()
            )

        result = await self._to_thread(_do)
        return result.data[0] if result.data else None

    async def upsert_processing_incident(
        self,
        *,
        tenant_id: str,
        incident_id: str,
        title: str,
        service_name: str,
        severity: str,
        status: str,
        triggered_at: str | None = None,
        processed_at: str | None = None,
        error_message: str | None = None,
        source: str = "manual",
        source_url: str | None = None,
        source_id: str | None = None,
        metadata: dict | None = None,
        description: str | None = None,
    ) -> dict:
        """Upsert an incident row used by the web dashboard."""
        self._check_enabled()

        payload = {
            "id": incident_id,
            "tenant_id": tenant_id,
            "title": title,
            "description": description,
            "service": service_name,
            "severity": severity,
            "status": status,
            "triggered_at": triggered_at,
            "processed_at": processed_at,
            "error_message": error_message,
            "source": source,
            "source_url": source_url,
            "source_id": source_id or incident_id,
            "metadata": metadata or {},
            "created_at": triggered_at or datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        def _do():
            return (
                self.client.table("incidents")
                .upsert(payload, on_conflict="id")
                .execute()
            )

        res = await self._to_thread(_do)
        return res.data[0] if res.data else payload

    async def list_processing_incidents(
        self,
        *,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List incidents for the dashboard."""
        self._check_enabled()

        def _do():
            return (
                self.client.table("incidents")
                .select("*")
                .eq("tenant_id", tenant_id)
                .order("triggered_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )

        res = await self._to_thread(_do)
        return res.data or []

    async def get_processing_incident(
        self, *, tenant_id: str, incident_id: str
    ) -> dict | None:
        """Get an incident row (tenant scoped)."""
        self._check_enabled()

        def _do():
            return (
                self.client.table("incidents")
                .select("*")
                .eq("tenant_id", tenant_id)
                .eq("id", incident_id)
                .single()
                .execute()
            )

        try:
            res = await self._to_thread(_do)
            return res.data
        except Exception:
            return None

    async def list_incidents(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List incidents for a tenant."""
        self._check_enabled()

        query = self.client.table("incidents").select("*").eq("tenant_id", tenant_id)

        if status:
            query = query.eq("status", status)

        result = (
            query.order("created_at", desc=True)
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
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        def _do():
            return self.client.table("context_cards").insert(card).execute()

        result = await self._to_thread(_do)
        return result.data[0] if result.data else card

    async def get_context_card(self, incident_id: str) -> dict | None:
        """Get the context card for an incident."""
        self._check_enabled()

        def _do():
            return (
                self.client.table("context_cards")
                .select("*")
                .eq("incident_id", incident_id)
                .order("created_at", desc=True)
                .limit(1)
                .single()
                .execute()
            )

        result = await self._to_thread(_do)
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
            "created_at": datetime.now(UTC).isoformat(),
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

    # ==================== OAuth Integration Tokens ====================

    async def upsert_integration_token(
        self,
        tenant_id: str,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        token_expiry: str | None = None,
        scopes: list[str] | None = None,
    ) -> dict:
        """Create or update an integration OAuth token record."""
        self._check_enabled()

        now = datetime.now(UTC).isoformat()
        payload = {
            "tenant_id": tenant_id,
            "provider": provider,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiry": token_expiry,
            "scopes": scopes or [],
            "updated_at": now,
        }

        existing = await self.get_integration_token(tenant_id=tenant_id, provider=provider)
        if existing:
            payload["created_at"] = now
            result = (
                self.client.table("integration_tokens")
                .update(payload)
                .eq("tenant_id", tenant_id)
                .eq("provider", provider)
                .execute()
            )
            return result.data[0] if result.data else existing

        payload["id"] = str(uuid4())
        payload["created_at"] = now
        result = self.client.table("integration_tokens").insert(payload).execute()
        return result.data[0] if result.data else payload

    async def get_integration_token(self, tenant_id: str, provider: str) -> dict | None:
        """Fetch an integration token row for a tenant/provider."""
        self._check_enabled()

        try:
            result = (
                self.client.table("integration_tokens")
                .select("*")
                .eq("tenant_id", tenant_id)
                .eq("provider", provider)
                .single()
                .execute()
            )
            return result.data
        except Exception:
            return None

    async def delete_integration_token(self, tenant_id: str, provider: str) -> bool:
        """Delete an integration token row for a tenant/provider."""
        self._check_enabled()

        self.client.table("integration_tokens").delete().eq("tenant_id", tenant_id).eq(
            "provider", provider
        ).execute()
        return True

    async def list_expiring_integration_tokens(
        self,
        expires_before: str,
        limit: int = 200,
    ) -> list[dict]:
        """List tokens with refresh tokens that are expiring before the cutoff."""
        self._check_enabled()

        result = (
            self.client.table("integration_tokens")
            .select("*")
            .neq("refresh_token", "")
            .lte("token_expiry", expires_before)
            .order("token_expiry")
            .limit(limit)
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
            "created_at": datetime.now(UTC).isoformat(),
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

        query = self.client.table("audit_logs").select("*").eq("tenant_id", tenant_id)

        if user_id:
            query = query.eq("user_id", user_id)
        if action:
            query = query.eq("action", action)

        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or []

    # ==================== Incident Events ====================

    async def create_incident_event(
        self,
        incident_id: str,
        tenant_id: str,
        event_type: str,
        title: str,
        occurred_at: str | None = None,
        **kwargs,
    ) -> dict:
        """Create a timeline event for an incident."""
        self._check_enabled()

        event = {
            "id": str(uuid4()),
            "incident_id": incident_id,
            "tenant_id": tenant_id,
            "event_type": event_type,
            "title": title,
            "occurred_at": occurred_at or datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        result = self.client.table("incident_events").insert(event).execute()
        return result.data[0] if result.data else event

    async def list_incident_events(
        self,
        incident_id: str,
        limit: int = 200,
    ) -> list[dict]:
        """List timeline events for an incident."""
        self._check_enabled()

        result = (
            self.client.table("incident_events")
            .select("*")
            .eq("incident_id", incident_id)
            .order("occurred_at")
            .limit(limit)
            .execute()
        )
        return result.data or []

    # ==================== Postmortems ====================

    async def create_postmortem(
        self,
        incident_id: str,
        tenant_id: str,
        title: str,
        service_name: str,
        severity: str,
        executive_summary: str,
        **kwargs,
    ) -> dict:
        """Create a postmortem."""
        self._check_enabled()

        postmortem = {
            "id": str(uuid4()),
            "incident_id": incident_id,
            "tenant_id": tenant_id,
            "title": title,
            "service_name": service_name,
            "severity": severity,
            "executive_summary": executive_summary,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }

        result = self.client.table("postmortems").insert(postmortem).execute()
        return result.data[0] if result.data else postmortem

    async def get_postmortem(self, postmortem_id: str) -> dict | None:
        """Get a postmortem by ID."""
        self._check_enabled()
        result = (
            self.client.table("postmortems")
            .select("*")
            .eq("id", postmortem_id)
            .single()
            .execute()
        )
        return result.data

    async def get_postmortem_by_incident(self, incident_id: str) -> dict | None:
        """Get a postmortem by incident ID."""
        self._check_enabled()
        result = (
            self.client.table("postmortems")
            .select("*")
            .eq("incident_id", incident_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def update_postmortem(self, postmortem_id: str, **kwargs) -> dict | None:
        """Update a postmortem."""
        self._check_enabled()
        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        result = (
            self.client.table("postmortems")
            .update(kwargs)
            .eq("id", postmortem_id)
            .execute()
        )
        return result.data[0] if result.data else None

    async def list_postmortems(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List postmortems for a tenant."""
        self._check_enabled()
        query = self.client.table("postmortems").select("*").eq("tenant_id", tenant_id)
        if status:
            query = query.eq("status", status)
        result = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data or []

    # ==================== Tags ====================

    async def create_tag(
        self,
        tenant_id: str,
        name: str,
        **kwargs,
    ) -> dict:
        """Create a tag."""
        self._check_enabled()
        tag = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "name": name,
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = self.client.table("tags").insert(tag).execute()
        return result.data[0] if result.data else tag

    async def list_tags(self, tenant_id: str) -> list[dict]:
        """List tags for a tenant."""
        self._check_enabled()
        result = (
            self.client.table("tags")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("name")
            .execute()
        )
        return result.data or []

    async def add_incident_tag(
        self,
        incident_id: str,
        tag_id: str,
        **kwargs,
    ) -> dict:
        """Tag an incident."""
        self._check_enabled()
        record = {
            "incident_id": incident_id,
            "tag_id": tag_id,
            "applied_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = self.client.table("incident_tags").insert(record).execute()
        return result.data[0] if result.data else record

    async def get_incident_tags(self, incident_id: str) -> list[dict]:
        """Get tags for an incident."""
        self._check_enabled()
        result = (
            self.client.table("incident_tags")
            .select("*, tags(*)")
            .eq("incident_id", incident_id)
            .execute()
        )
        return result.data or []

    async def remove_incident_tag(self, incident_id: str, tag_id: str) -> bool:
        """Remove a tag from an incident."""
        self._check_enabled()
        self.client.table("incident_tags").delete().eq("incident_id", incident_id).eq(
            "tag_id", tag_id
        ).execute()
        return True

    # ==================== Services ====================

    async def create_service(
        self,
        tenant_id: str,
        name: str,
        **kwargs,
    ) -> dict:
        """Create a service."""
        self._check_enabled()
        service = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "name": name,
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = self.client.table("services").insert(service).execute()
        return result.data[0] if result.data else service

    async def get_service(self, service_id: str) -> dict | None:
        """Get a service by ID."""
        self._check_enabled()
        result = (
            self.client.table("services")
            .select("*")
            .eq("id", service_id)
            .single()
            .execute()
        )
        return result.data

    async def get_service_by_name(self, tenant_id: str, name: str) -> dict | None:
        """Get a service by name."""
        self._check_enabled()
        result = (
            self.client.table("services")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("name", name)
            .single()
            .execute()
        )
        return result.data

    async def list_services(self, tenant_id: str) -> list[dict]:
        """List services for a tenant."""
        self._check_enabled()
        result = (
            self.client.table("services")
            .select("*")
            .eq("tenant_id", tenant_id)
            .order("name")
            .execute()
        )
        return result.data or []

    async def update_service(self, service_id: str, **kwargs) -> dict | None:
        """Update a service."""
        self._check_enabled()
        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        result = (
            self.client.table("services").update(kwargs).eq("id", service_id).execute()
        )
        return result.data[0] if result.data else None

    # ==================== Service Dependencies ====================

    async def create_service_dependency(
        self,
        tenant_id: str,
        upstream_service_id: str,
        downstream_service_id: str,
        **kwargs,
    ) -> dict:
        """Create a service dependency."""
        self._check_enabled()
        dep = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "upstream_service_id": upstream_service_id,
            "downstream_service_id": downstream_service_id,
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = self.client.table("service_dependencies").insert(dep).execute()
        return result.data[0] if result.data else dep

    async def get_service_dependencies(self, service_id: str) -> dict:
        """Get upstream and downstream dependencies for a service."""
        self._check_enabled()
        upstream = (
            self.client.table("service_dependencies")
            .select("*, services!upstream_service_id(*)")
            .eq("downstream_service_id", service_id)
            .execute()
        )
        downstream = (
            self.client.table("service_dependencies")
            .select("*, services!downstream_service_id(*)")
            .eq("upstream_service_id", service_id)
            .execute()
        )
        return {
            "upstream": upstream.data or [],
            "downstream": downstream.data or [],
        }

    # ==================== On-Call Schedules ====================

    async def upsert_on_call_schedule(
        self,
        tenant_id: str,
        schedule_id: str,
        schedule_name: str,
        provider: str,
        **kwargs,
    ) -> dict:
        """Create or update an on-call schedule."""
        self._check_enabled()
        schedule = {
            "tenant_id": tenant_id,
            "schedule_id": schedule_id,
            "schedule_name": schedule_name,
            "provider": provider,
            "updated_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = (
            self.client.table("on_call_schedules")
            .upsert(schedule, on_conflict="tenant_id,provider,schedule_id")
            .execute()
        )
        return result.data[0] if result.data else schedule

    async def list_on_call_schedules(self, tenant_id: str) -> list[dict]:
        """List on-call schedules for a tenant."""
        self._check_enabled()
        result = (
            self.client.table("on_call_schedules")
            .select("*, on_call_persons(*)")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .execute()
        )
        return result.data or []

    # ==================== Cost Entries ====================

    async def create_cost_entry(
        self,
        tenant_id: str,
        incident_id: str,
        category: str,
        amount: float,
        **kwargs,
    ) -> dict:
        """Create a cost entry."""
        self._check_enabled()
        entry = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "incident_id": incident_id,
            "category": category,
            "amount": amount,
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = self.client.table("cost_entries").insert(entry).execute()
        return result.data[0] if result.data else entry

    async def get_cost_entries_for_incident(self, incident_id: str) -> list[dict]:
        """Get cost entries for an incident."""
        self._check_enabled()
        result = (
            self.client.table("cost_entries")
            .select("*")
            .eq("incident_id", incident_id)
            .order("created_at")
            .execute()
        )
        return result.data or []

    async def delete_cost_entry(self, entry_id: str) -> bool:
        """Delete a cost entry."""
        self._check_enabled()
        self.client.table("cost_entries").delete().eq("id", entry_id).execute()
        return True

    # ==================== Incident Comments ====================

    async def create_comment(
        self,
        incident_id: str,
        tenant_id: str,
        author_name: str,
        content: str,
        **kwargs,
    ) -> dict:
        """Create a comment on an incident."""
        self._check_enabled()
        comment = {
            "id": str(uuid4()),
            "incident_id": incident_id,
            "tenant_id": tenant_id,
            "author_name": author_name,
            "content": content,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = self.client.table("incident_comments").insert(comment).execute()
        return result.data[0] if result.data else comment

    async def list_comments(
        self,
        incident_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """List comments for an incident."""
        self._check_enabled()
        result = (
            self.client.table("incident_comments")
            .select("*")
            .eq("incident_id", incident_id)
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return result.data or []

    async def update_comment(self, comment_id: str, **kwargs) -> dict | None:
        """Update a comment."""
        self._check_enabled()
        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        kwargs["edited"] = True
        result = (
            self.client.table("incident_comments")
            .update(kwargs)
            .eq("id", comment_id)
            .execute()
        )
        return result.data[0] if result.data else None

    async def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment."""
        self._check_enabled()
        self.client.table("incident_comments").delete().eq("id", comment_id).execute()
        return True

    # ==================== Insights ====================

    async def create_insight(
        self,
        tenant_id: str,
        insight_type: str,
        title: str,
        **kwargs,
    ) -> dict:
        """Create an insight."""
        self._check_enabled()
        insight = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "insight_type": insight_type,
            "title": title,
            "created_at": datetime.now(UTC).isoformat(),
            **kwargs,
        }
        result = self.client.table("insights").insert(insight).execute()
        return result.data[0] if result.data else insight

    async def list_insights(
        self,
        tenant_id: str,
        insight_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List insights for a tenant."""
        self._check_enabled()
        query = self.client.table("insights").select("*").eq("tenant_id", tenant_id)
        if insight_type:
            query = query.eq("insight_type", insight_type)
        result = query.order("created_at", desc=True).limit(limit).execute()
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
