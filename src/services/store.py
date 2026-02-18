"""Persistent service catalog storage using Supabase PostgREST."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from uuid import uuid4

import structlog

from ..supabase_client import get_supabase_admin_client, is_supabase_db_enabled
from .models import (
    Service,
    ServiceCreate,
    ServiceDependency,
    ServiceDependencyCreate,
    ServiceDependencyUpdate,
    ServiceEnvironment,
    ServiceUpdate,
)

logger = structlog.get_logger()


class ServiceCatalogStore:
    """Supabase-backed store for services and dependencies."""

    def __init__(self) -> None:
        self._enabled: bool | None = None  # lazy check

    @property
    def enabled(self) -> bool:
        if self._enabled is None:
            self._enabled = is_supabase_db_enabled()
        return self._enabled

    def _client(self):
        return get_supabase_admin_client()

    async def _run(self, fn):
        """Run a synchronous Supabase call in a thread."""
        try:
            return await asyncio.to_thread(fn)
        except Exception as exc:
            logger.warning("service_catalog_db_error", error=str(exc))
            return None

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def initialize(self) -> None:
        if not self.enabled:
            return
        # Verify tables exist by doing a lightweight query
        try:
            client = self._client()
            if not client:
                self._enabled = False
                return
            result = await asyncio.to_thread(
                lambda: client.table("services").select("id").limit(1).execute()
            )
            logger.info("service_catalog_store_initialized", rows=len(result.data))
        except Exception as exc:
            logger.warning("service_catalog_store_init_failed", error=str(exc))
            self._enabled = False

    async def _ensure_ready(self) -> bool:
        return self.enabled and self._client() is not None

    def _normalize_service_id(self, name: str) -> str:
        key = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
        return key or "service"

    async def _resolve_tenant_id(self, tenant_slug: str = "default") -> str | None:
        client = self._client()
        if not client:
            return None
        try:
            result = await asyncio.to_thread(
                lambda: client.table("tenants").select("id").eq("slug", tenant_slug).limit(1).execute()
            )
            if result.data:
                return str(result.data[0]["id"])
            # Create tenant
            result = await asyncio.to_thread(
                lambda: client.table("tenants").insert({
                    "name": f"{tenant_slug.title()} Tenant",
                    "slug": tenant_slug,
                    "plan": "free",
                }).execute()
            )
            if result.data:
                return str(result.data[0]["id"])
        except Exception as exc:
            logger.warning("tenant_resolve_failed", slug=tenant_slug, error=str(exc))
        return None

    def _row_to_service(self, row: dict) -> Service:
        return Service(
            id=row.get("service_key") or str(row.get("id", "")),
            name=row.get("name", ""),
            tenant_id=str(row.get("tenant_id", "")),
            description=row.get("description"),
            team=row.get("team"),
            owner_email=row.get("owner_email"),
            criticality=row.get("criticality", "unknown"),
            health=row.get("health", "unknown"),
            tags=row.get("tags") or [],
            critical_user_journey=bool(row.get("critical_user_journey", False)),
            repo_url=row.get("repo_url"),
            dashboard_url=row.get("dashboard_url"),
            runbook_url=row.get("runbook_url"),
            metadata=row.get("metadata") or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    def _row_to_dependency(self, row: dict) -> ServiceDependency:
        return ServiceDependency(
            id=str(row.get("id", "")),
            source_service_id=str(row.get("upstream_service_id", "")),
            target_service_id=str(row.get("downstream_service_id", "")),
            tenant_id=str(row.get("tenant_id", "")),
            dependency_type=row.get("dependency_type", "sync"),
            is_critical=bool(row.get("is_critical", False)),
            latency_p99_ms=row.get("latency_p99_ms"),
            error_rate=row.get("error_rate"),
            requests_per_min=row.get("requests_per_min"),
            health=row.get("health", "unknown"),
            discovered_from=row.get("discovered_from"),
            metadata=row.get("metadata") or {},
            discovered_at=row.get("discovered_at"),
            last_seen_at=row.get("last_seen_at"),
            created_at=row.get("created_at"),
        )

    # ── Services CRUD ──────────────────────────────────────────────

    async def create_service(
        self,
        request: ServiceCreate,
        tenant_slug: str = "default",
    ) -> Service:
        service_key = request.id or self._normalize_service_id(request.name)
        fallback = Service(
            id=service_key, name=request.name, description=request.description,
            team=request.team, owner_email=request.owner_email,
            criticality=request.criticality, health=request.health,
            tags=request.tags, critical_user_journey=request.critical_user_journey,
            repo_url=request.repo_url, dashboard_url=request.dashboard_url,
            runbook_url=request.runbook_url, metadata=request.metadata,
            environments=request.environments,
        )
        if not await self._ensure_ready():
            return fallback

        tenant_id = await self._resolve_tenant_id(tenant_slug)
        if not tenant_id:
            return fallback

        client = self._client()
        data = {
            "tenant_id": tenant_id,
            "service_key": service_key,
            "name": request.name,
            "description": request.description,
            "team": request.team,
            "owner_email": request.owner_email,
            "criticality": request.criticality.value if request.criticality else "medium",
            "health": request.health.value if request.health else "unknown",
            "tags": request.tags or [],
            "critical_user_journey": request.critical_user_journey,
            "repo_url": request.repo_url,
            "dashboard_url": request.dashboard_url,
            "runbook_url": request.runbook_url,
            "metadata": request.metadata or {},
        }

        result = await self._run(
            lambda: client.table("services").upsert(
                data, on_conflict="tenant_id,name"
            ).execute()
        )
        if result and result.data:
            return self._row_to_service(result.data[0])
        return fallback

    async def get_service(
        self,
        service_id: str,
        tenant_slug: str = "default",
    ) -> Service | None:
        if not await self._ensure_ready():
            return None
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        if not tenant_id:
            return None
        client = self._client()
        result = await self._run(
            lambda: client.table("services").select("*").eq(
                "tenant_id", tenant_id
            ).or_(
                f"service_key.eq.{service_id},name.eq.{service_id}"
            ).limit(1).execute()
        )
        if result and result.data:
            return self._row_to_service(result.data[0])
        return None

    async def get_service_by_name(
        self,
        name: str,
        tenant_slug: str = "default",
    ) -> Service | None:
        return await self.get_service(name, tenant_slug=tenant_slug)

    async def list_services(
        self,
        tenant_slug: str = "default",
        team: str | None = None,
        criticality: str | None = None,
        environment: str | None = None,
        region: str | None = None,
    ) -> list[Service]:
        if not await self._ensure_ready():
            return []
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        if not tenant_id:
            return []
        client = self._client()

        def _query():
            q = client.table("services").select("*").eq("tenant_id", tenant_id)
            if team:
                q = q.eq("team", team)
            if criticality:
                q = q.eq("criticality", criticality)
            return q.order("name").execute()

        result = await self._run(_query)
        if not result or not result.data:
            return []
        return [self._row_to_service(r) for r in result.data]

    async def update_service(
        self,
        service_id: str,
        request: ServiceUpdate,
        tenant_slug: str = "default",
    ) -> Service | None:
        existing = await self.get_service(service_id, tenant_slug=tenant_slug)
        if not existing:
            return None
        if not await self._ensure_ready():
            return existing

        tenant_id = await self._resolve_tenant_id(tenant_slug)
        if not tenant_id:
            return existing

        update_data = request.model_dump(exclude_unset=True)
        update_data.pop("environments", None)
        if not update_data:
            return existing

        # Convert enums to values
        for key in ("criticality", "health"):
            if key in update_data and hasattr(update_data[key], "value"):
                update_data[key] = update_data[key].value

        client = self._client()
        await self._run(
            lambda: client.table("services").update(update_data).eq(
                "tenant_id", tenant_id
            ).eq("service_key", existing.id).execute()
        )
        return await self.get_service(service_id, tenant_slug=tenant_slug)

    async def delete_service(self, service_id: str, tenant_slug: str = "default") -> bool:
        if not await self._ensure_ready():
            return False
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        if not tenant_id:
            return False
        client = self._client()
        result = await self._run(
            lambda: client.table("services").delete().eq(
                "tenant_id", tenant_id
            ).or_(
                f"service_key.eq.{service_id},name.eq.{service_id}"
            ).execute()
        )
        return bool(result and result.data)

    # ── Environments ───────────────────────────────────────────────

    async def list_service_environments(
        self,
        service_id: str,
        tenant_slug: str = "default",
        conn=None,
    ) -> list[ServiceEnvironment]:
        # Simplified — environments are a future enhancement
        return []

    async def replace_service_environments(
        self,
        service_id: str,
        environments: list[ServiceEnvironment],
        tenant_slug: str = "default",
        conn=None,
    ) -> None:
        pass

    # ── Dependencies CRUD ──────────────────────────────────────────

    async def create_dependency(
        self,
        source_service_id: str,
        request: ServiceDependencyCreate,
        tenant_slug: str = "default",
    ) -> ServiceDependency | None:
        if not await self._ensure_ready():
            return None
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        if not tenant_id:
            return None

        # Resolve service UUIDs
        source = await self.get_service(source_service_id, tenant_slug=tenant_slug)
        target = await self.get_service(request.target_service_id, tenant_slug=tenant_slug)
        if not source or not target:
            return None

        client = self._client()
        data = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "upstream_service_id": source.id,
            "downstream_service_id": target.id,
            "dependency_type": request.dependency_type.value,
            "is_critical": request.is_critical,
            "metadata": request.metadata or {},
        }
        result = await self._run(
            lambda: client.table("service_dependencies").insert(data).execute()
        )
        if result and result.data:
            return self._row_to_dependency(result.data[0])
        return None

    async def get_dependency(
        self,
        dependency_id: str,
        tenant_slug: str = "default",
    ) -> ServiceDependency | None:
        if not await self._ensure_ready():
            return None
        client = self._client()
        result = await self._run(
            lambda: client.table("service_dependencies").select("*").eq(
                "id", dependency_id
            ).limit(1).execute()
        )
        if result and result.data:
            return self._row_to_dependency(result.data[0])
        return None

    async def list_dependencies(
        self,
        tenant_slug: str = "default",
        source_service_id: str | None = None,
        target_service_id: str | None = None,
    ) -> list[ServiceDependency]:
        if not await self._ensure_ready():
            return []
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        if not tenant_id:
            return []
        client = self._client()

        def _query():
            q = client.table("service_dependencies").select("*").eq("tenant_id", tenant_id)
            if source_service_id:
                q = q.eq("upstream_service_id", source_service_id)
            if target_service_id:
                q = q.eq("downstream_service_id", target_service_id)
            return q.execute()

        result = await self._run(_query)
        if not result or not result.data:
            return []
        return [self._row_to_dependency(r) for r in result.data]

    async def update_dependency(
        self,
        dependency_id: str,
        request: ServiceDependencyUpdate,
        tenant_slug: str = "default",
    ) -> ServiceDependency | None:
        if not await self._ensure_ready():
            return None
        update_data = request.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_dependency(dependency_id, tenant_slug=tenant_slug)

        for key in ("dependency_type", "health"):
            if key in update_data and hasattr(update_data[key], "value"):
                update_data[key] = update_data[key].value

        client = self._client()
        await self._run(
            lambda: client.table("service_dependencies").update(
                update_data
            ).eq("id", dependency_id).execute()
        )
        return await self.get_dependency(dependency_id, tenant_slug=tenant_slug)

    async def delete_dependency(
        self,
        dependency_id: str,
        tenant_slug: str = "default",
    ) -> bool:
        if not await self._ensure_ready():
            return False
        client = self._client()
        result = await self._run(
            lambda: client.table("service_dependencies").delete().eq(
                "id", dependency_id
            ).execute()
        )
        return bool(result and result.data)


# ── Singleton ──────────────────────────────────────────────────────

service_catalog_store: ServiceCatalogStore | None = None


def get_service_catalog_store() -> ServiceCatalogStore:
    global service_catalog_store
    if service_catalog_store is None:
        service_catalog_store = ServiceCatalogStore()
    return service_catalog_store


async def init_service_catalog_store() -> ServiceCatalogStore:
    store = get_service_catalog_store()
    await store.initialize()
    return store


async def close_service_catalog_store() -> None:
    global service_catalog_store
    if service_catalog_store is not None:
        await service_catalog_store.disconnect()
        service_catalog_store = None
