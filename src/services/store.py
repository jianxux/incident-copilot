"""Persistent service catalog storage using PostgreSQL/Supabase."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import asyncpg
import structlog

from ..config import get_settings
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
    """Async PostgreSQL-backed store for services and dependencies."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool: asyncpg.Pool | None = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._enabled = database_url.startswith("postgresql")

    @property
    def enabled(self) -> bool:
        """Whether persistent Postgres storage is available in this runtime."""
        return self._enabled

    async def connect(self) -> None:
        """Connect to PostgreSQL (graceful — does not crash on failure)."""
        if not self._enabled or self._pool is not None:
            return

        try:
            self._pool = await asyncpg.create_pool(
                self.database_url.replace("+asyncpg", ""),
                min_size=1,
                max_size=10,
                timeout=10,
            )
        except (OSError, asyncpg.PostgresError, Exception) as exc:
            logger.warning("service_catalog_db_connect_failed", error=str(exc))
            self._enabled = False
            self._pool = None

    async def disconnect(self) -> None:
        """Close PostgreSQL pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def initialize(self) -> None:
        """Initialize schema required by service catalog (graceful)."""
        if not self._enabled:
            return

        async with self._lock:
            if self._initialized:
                return
            await self.connect()
            if not self._pool:
                return

            try:
                init_sql_path = Path(__file__).parent / "init.sql"
                sql = init_sql_path.read_text(encoding="utf-8")
                async with self._pool.acquire() as conn:
                    await conn.execute(sql)

                self._initialized = True
                logger.info("service_catalog_store_initialized")
            except Exception as exc:
                logger.warning("service_catalog_schema_init_failed", error=str(exc))
                self._enabled = False

    async def _ensure_ready(self) -> bool:
        """Ensure pool/schema is ready when Postgres is enabled."""
        if not self._enabled:
            return False
        if not self._initialized:
            await self.initialize()
        return self._pool is not None

    async def _resolve_tenant_id(self, tenant_slug: str = "default") -> str:
        """Resolve or create tenant UUID by slug for service catalog ops."""
        if not self._pool:
            raise RuntimeError("Service catalog store not connected")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id::text FROM public.tenants WHERE slug = $1 LIMIT 1",
                tenant_slug,
            )
            if row:
                return str(row["id"])

            created = await conn.fetchrow(
                """
                INSERT INTO public.tenants(name, slug, plan)
                VALUES($1, $2, 'free')
                RETURNING id::text
                """,
                f"{tenant_slug.title()} Tenant",
                tenant_slug,
            )
            if not created:
                raise RuntimeError("Failed to create default tenant")
            return str(created["id"])

    def _normalize_service_id(self, name: str) -> str:
        key = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
        return key or "service"

    def _row_to_service(self, row: asyncpg.Record) -> Service:
        return Service(
            id=row["service_key"] or str(row["id"]),
            name=row["name"],
            tenant_id=str(row["tenant_id"]),
            description=row["description"],
            team=row["team"],
            owner_email=row.get("owner_email"),
            criticality=row["criticality"],
            health=row.get("health") or "unknown",
            tags=row.get("tags") or [],
            critical_user_journey=bool(row.get("critical_user_journey") or False),
            repo_url=row.get("repo_url"),
            dashboard_url=row.get("dashboard_url"),
            runbook_url=row.get("runbook_url"),
            metadata=row.get("metadata") or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    async def _get_service_internal_id(
        self,
        conn: asyncpg.Connection,
        tenant_id: str,
        service_id: str,
    ) -> str | None:
        row = await conn.fetchrow(
            """
            SELECT id::text
            FROM public.services
            WHERE tenant_id = $1::uuid
              AND (service_key = $2 OR id::text = $2 OR name = $2)
            LIMIT 1
            """,
            tenant_id,
            service_id,
        )
        return str(row["id"]) if row else None

    async def create_service(
        self,
        request: ServiceCreate,
        tenant_slug: str = "default",
    ) -> Service:
        """Create a service and optional environment records."""
        if not await self._ensure_ready():
            service_id = request.id or self._normalize_service_id(request.name)
            return Service(
                id=service_id,
                name=request.name,
                description=request.description,
                team=request.team,
                owner_email=request.owner_email,
                criticality=request.criticality,
                health=request.health,
                tags=request.tags,
                critical_user_journey=request.critical_user_journey,
                repo_url=request.repo_url,
                dashboard_url=request.dashboard_url,
                runbook_url=request.runbook_url,
                metadata=request.metadata,
                environments=request.environments,
            )

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        service_key = request.id or self._normalize_service_id(request.name)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO public.services (
                    tenant_id, service_key, name, description, team, owner_email,
                    criticality, health, tags, critical_user_journey,
                    repo_url, dashboard_url, runbook_url, metadata
                )
                VALUES (
                    $1::uuid, $2, $3, $4, $5, $6,
                    $7, $8, $9::text[], $10,
                    $11, $12, $13, $14::jsonb
                )
                ON CONFLICT (tenant_id, service_key)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    team = EXCLUDED.team,
                    owner_email = EXCLUDED.owner_email,
                    criticality = EXCLUDED.criticality,
                    health = EXCLUDED.health,
                    tags = EXCLUDED.tags,
                    critical_user_journey = EXCLUDED.critical_user_journey,
                    repo_url = EXCLUDED.repo_url,
                    dashboard_url = EXCLUDED.dashboard_url,
                    runbook_url = EXCLUDED.runbook_url,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                tenant_id,
                service_key,
                request.name,
                request.description,
                request.team,
                request.owner_email,
                request.criticality.value,
                request.health.value,
                request.tags,
                request.critical_user_journey,
                request.repo_url,
                request.dashboard_url,
                request.runbook_url,
                json.dumps(request.metadata or {}),
            )

            if not row:
                raise RuntimeError("Failed to upsert service")

            service = self._row_to_service(row)
            environments = request.environments or []
            if environments:
                await self.replace_service_environments(
                    service.id,
                    environments,
                    tenant_slug=tenant_slug,
                    conn=conn,
                )
                service.environments = await self.list_service_environments(
                    service.id, tenant_slug=tenant_slug, conn=conn
                )
            return service

    async def get_service(
        self,
        service_id: str,
        tenant_slug: str = "default",
    ) -> Service | None:
        """Get a service by key, UUID, or name."""
        if not await self._ensure_ready():
            return None

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM public.services
                WHERE tenant_id = $1::uuid
                  AND (service_key = $2 OR id::text = $2 OR name = $2)
                LIMIT 1
                """,
                tenant_id,
                service_id,
            )
            if not row:
                return None
            svc = self._row_to_service(row)
            svc.environments = await self.list_service_environments(
                svc.id, tenant_slug=tenant_slug, conn=conn
            )
            return svc

    async def get_service_by_name(
        self,
        name: str,
        tenant_slug: str = "default",
    ) -> Service | None:
        """Get a service by name."""
        return await self.get_service(name, tenant_slug=tenant_slug)

    async def list_services(
        self,
        tenant_slug: str = "default",
        team: str | None = None,
        criticality: str | None = None,
        environment: str | None = None,
        region: str | None = None,
    ) -> list[Service]:
        """List services with optional filters."""
        if not await self._ensure_ready():
            return []

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        clauses = ["tenant_id = $1::uuid"]
        args: list[Any] = [tenant_id]

        if team:
            args.append(team)
            clauses.append(f"team = ${len(args)}")
        if criticality:
            args.append(criticality)
            clauses.append(f"criticality = ${len(args)}")

        sql = f"""
            SELECT *
            FROM public.services
            WHERE {' AND '.join(clauses)}
            ORDER BY name ASC
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            services = [self._row_to_service(r) for r in rows]

            for svc in services:
                envs = await self.list_service_environments(
                    svc.id, tenant_slug=tenant_slug, conn=conn
                )
                if environment and not any(e.environment == environment for e in envs):
                    continue
                if region and not any(e.region == region for e in envs):
                    continue
                svc.environments = envs

            filtered = [s for s in services if s.environments or not (environment or region)]
            if environment or region:
                return filtered
            return services

    async def update_service(
        self,
        service_id: str,
        request: ServiceUpdate,
        tenant_slug: str = "default",
    ) -> Service | None:
        """Update service fields and optionally replace environments."""
        existing = await self.get_service(service_id, tenant_slug=tenant_slug)
        if not existing:
            return None

        if not await self._ensure_ready():
            return existing

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        update_data = request.model_dump(exclude_unset=True)
        environments = update_data.pop("environments", None)

        if not update_data and environments is None:
            return existing

        assignments: list[str] = []
        args: list[Any] = [tenant_id, existing.id]

        field_mapping = {
            "name": "name",
            "description": "description",
            "team": "team",
            "owner_email": "owner_email",
            "criticality": "criticality",
            "health": "health",
            "tags": "tags",
            "critical_user_journey": "critical_user_journey",
            "repo_url": "repo_url",
            "dashboard_url": "dashboard_url",
            "runbook_url": "runbook_url",
            "metadata": "metadata",
        }

        for key, value in update_data.items():
            if key not in field_mapping:
                continue
            col = field_mapping[key]
            if hasattr(value, "value"):
                value = value.value
            if key == "metadata":
                value = json.dumps(value)
                assignments.append(f"{col} = ${len(args)+1}::jsonb")
            elif key == "tags":
                assignments.append(f"{col} = ${len(args)+1}::text[]")
            else:
                assignments.append(f"{col} = ${len(args)+1}")
            args.append(value)

        if assignments:
            assignments.append("updated_at = NOW()")

        async with self._pool.acquire() as conn:
            if assignments:
                await conn.execute(
                    f"""
                    UPDATE public.services
                    SET {', '.join(assignments)}
                    WHERE tenant_id = $1::uuid
                      AND (service_key = $2 OR id::text = $2 OR name = $2)
                    """,
                    *args,
                )

            if environments is not None:
                env_models = [ServiceEnvironment(**env) for env in environments]
                await self.replace_service_environments(
                    existing.id,
                    env_models,
                    tenant_slug=tenant_slug,
                    conn=conn,
                )

        return await self.get_service(existing.id, tenant_slug=tenant_slug)

    async def delete_service(self, service_id: str, tenant_slug: str = "default") -> bool:
        """Delete a service and cascading dependencies."""
        if not await self._ensure_ready():
            return False

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM public.services
                WHERE tenant_id = $1::uuid
                  AND (service_key = $2 OR id::text = $2 OR name = $2)
                """,
                tenant_id,
                service_id,
            )
        return result.endswith("1")

    async def list_service_environments(
        self,
        service_id: str,
        tenant_slug: str = "default",
        conn: asyncpg.Connection | None = None,
    ) -> list[ServiceEnvironment]:
        """List environments for a service."""
        if not await self._ensure_ready():
            return []

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        close_conn = False
        if conn is None:
            conn = await self._pool.acquire()
            close_conn = True

        try:
            internal_id = await self._get_service_internal_id(conn, tenant_id, service_id)
            if not internal_id:
                return []

            rows = await conn.fetch(
                """
                SELECT id::text AS id,
                       environment,
                       region,
                       cluster,
                       namespace,
                       version,
                       is_primary,
                       metadata,
                       last_seen_at,
                       created_at,
                       updated_at
                FROM public.service_environments
                WHERE service_id = $1::uuid
                ORDER BY environment, region, cluster
                """,
                internal_id,
            )
            return [
                ServiceEnvironment(
                    id=r["id"],
                    service_id=service_id,
                    environment=r["environment"],
                    region=r["region"],
                    cluster=r["cluster"],
                    namespace=r["namespace"],
                    version=r["version"],
                    is_primary=bool(r["is_primary"]),
                    metadata=r["metadata"] or {},
                    last_seen_at=r["last_seen_at"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]
        finally:
            if close_conn:
                assert self._pool is not None
                await self._pool.release(conn)

    async def replace_service_environments(
        self,
        service_id: str,
        environments: list[ServiceEnvironment],
        tenant_slug: str = "default",
        conn: asyncpg.Connection | None = None,
    ) -> None:
        """Replace all environments associated with a service."""
        if not await self._ensure_ready():
            return

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        close_conn = False
        if conn is None:
            conn = await self._pool.acquire()
            close_conn = True

        try:
            internal_id = await self._get_service_internal_id(conn, tenant_id, service_id)
            if not internal_id:
                return

            await conn.execute(
                "DELETE FROM public.service_environments WHERE service_id = $1::uuid",
                internal_id,
            )

            for env in environments:
                await conn.execute(
                    """
                    INSERT INTO public.service_environments (
                        service_id, environment, region, cluster, namespace,
                        version, is_primary, metadata, last_seen_at
                    )
                    VALUES (
                        $1::uuid, $2, $3, $4, $5,
                        $6, $7, $8::jsonb, COALESCE($9, NOW())
                    )
                    """,
                    internal_id,
                    env.environment,
                    env.region,
                    env.cluster,
                    env.namespace,
                    env.version,
                    env.is_primary,
                    json.dumps(env.metadata or {}),
                    env.last_seen_at,
                )
        finally:
            if close_conn:
                assert self._pool is not None
                await self._pool.release(conn)

    def _row_to_dependency(self, row: asyncpg.Record) -> ServiceDependency:
        return ServiceDependency(
            id=row["id"],
            source_service_id=row["source_service_id"],
            target_service_id=row["target_service_id"],
            tenant_id=row["tenant_id"],
            dependency_type=row["dependency_type"],
            is_critical=bool(row["is_critical"]),
            latency_p99_ms=row["latency_p99_ms"],
            error_rate=row["error_rate"],
            requests_per_min=row["requests_per_min"],
            health=row.get("health") or "unknown",
            discovered_from=row.get("discovered_from"),
            metadata=row.get("metadata") or {},
            discovered_at=row.get("discovered_at"),
            last_seen_at=row.get("last_seen_at"),
            created_at=row.get("created_at"),
        )

    async def create_dependency(
        self,
        source_service_id: str,
        request: ServiceDependencyCreate,
        tenant_slug: str = "default",
    ) -> ServiceDependency | None:
        """Create dependency edge from source to target service."""
        if not await self._ensure_ready():
            return None

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        async with self._pool.acquire() as conn:
            source_internal = await self._get_service_internal_id(
                conn, tenant_id, source_service_id
            )
            target_internal = await self._get_service_internal_id(
                conn, tenant_id, request.target_service_id
            )
            if not source_internal or not target_internal:
                return None

            row = await conn.fetchrow(
                """
                INSERT INTO public.service_dependencies (
                    tenant_id,
                    upstream_service_id,
                    downstream_service_id,
                    dependency_type,
                    is_critical,
                    metadata,
                    discovered_at,
                    last_seen_at
                )
                VALUES (
                    $1::uuid,
                    $2::uuid,
                    $3::uuid,
                    $4,
                    $5,
                    $6::jsonb,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (tenant_id, upstream_service_id, downstream_service_id)
                DO UPDATE SET
                    dependency_type = EXCLUDED.dependency_type,
                    is_critical = EXCLUDED.is_critical,
                    metadata = EXCLUDED.metadata,
                    last_seen_at = NOW()
                RETURNING
                    id::text,
                    tenant_id::text,
                    (SELECT COALESCE(service_key, name) FROM public.services WHERE id = upstream_service_id) AS source_service_id,
                    (SELECT COALESCE(service_key, name) FROM public.services WHERE id = downstream_service_id) AS target_service_id,
                    dependency_type,
                    is_critical,
                    latency_p99_ms,
                    error_rate,
                    requests_per_min,
                    health,
                    discovered_from,
                    metadata,
                    discovered_at,
                    last_seen_at,
                    created_at
                """,
                tenant_id,
                source_internal,
                target_internal,
                request.dependency_type.value,
                request.is_critical,
                json.dumps(request.metadata or {}),
            )
            return self._row_to_dependency(row) if row else None

    async def get_dependency(
        self,
        dependency_id: str,
        tenant_slug: str = "default",
    ) -> ServiceDependency | None:
        """Get dependency edge by ID."""
        if not await self._ensure_ready():
            return None

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    d.id::text,
                    d.tenant_id::text,
                    COALESCE(src.service_key, src.name) AS source_service_id,
                    COALESCE(dst.service_key, dst.name) AS target_service_id,
                    d.dependency_type,
                    d.is_critical,
                    d.latency_p99_ms,
                    d.error_rate,
                    d.requests_per_min,
                    d.health,
                    d.discovered_from,
                    d.metadata,
                    d.discovered_at,
                    d.last_seen_at,
                    d.created_at
                FROM public.service_dependencies d
                JOIN public.services src ON src.id = d.upstream_service_id
                JOIN public.services dst ON dst.id = d.downstream_service_id
                WHERE d.tenant_id = $1::uuid
                  AND d.id::text = $2
                LIMIT 1
                """,
                tenant_id,
                dependency_id,
            )
            return self._row_to_dependency(row) if row else None

    async def list_dependencies(
        self,
        tenant_slug: str = "default",
        source_service_id: str | None = None,
        target_service_id: str | None = None,
    ) -> list[ServiceDependency]:
        """List dependency edges with optional source/target filters."""
        if not await self._ensure_ready():
            return []

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        clauses = ["d.tenant_id = $1::uuid"]
        args: list[Any] = [tenant_id]

        if source_service_id:
            args.append(source_service_id)
            clauses.append(
                f"(src.service_key = ${len(args)} OR src.id::text = ${len(args)} OR src.name = ${len(args)})"
            )
        if target_service_id:
            args.append(target_service_id)
            clauses.append(
                f"(dst.service_key = ${len(args)} OR dst.id::text = ${len(args)} OR dst.name = ${len(args)})"
            )

        sql = f"""
            SELECT
                d.id::text,
                d.tenant_id::text,
                COALESCE(src.service_key, src.name) AS source_service_id,
                COALESCE(dst.service_key, dst.name) AS target_service_id,
                d.dependency_type,
                d.is_critical,
                d.latency_p99_ms,
                d.error_rate,
                d.requests_per_min,
                d.health,
                d.discovered_from,
                d.metadata,
                d.discovered_at,
                d.last_seen_at,
                d.created_at
            FROM public.service_dependencies d
            JOIN public.services src ON src.id = d.upstream_service_id
            JOIN public.services dst ON dst.id = d.downstream_service_id
            WHERE {' AND '.join(clauses)}
            ORDER BY src.name, dst.name
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [self._row_to_dependency(r) for r in rows]

    async def update_dependency(
        self,
        dependency_id: str,
        request: ServiceDependencyUpdate,
        tenant_slug: str = "default",
    ) -> ServiceDependency | None:
        """Update dependency edge fields and metrics."""
        if not await self._ensure_ready():
            return None

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)
        update_data = request.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_dependency(dependency_id, tenant_slug=tenant_slug)

        assignments: list[str] = []
        args: list[Any] = [tenant_id, dependency_id]

        for key, value in update_data.items():
            if hasattr(value, "value"):
                value = value.value
            if key == "metadata":
                assignments.append(f"metadata = ${len(args)+1}::jsonb")
                args.append(json.dumps(value))
            else:
                assignments.append(f"{key} = ${len(args)+1}")
                args.append(value)

        assignments.append("last_seen_at = NOW()")

        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE public.service_dependencies
                SET {', '.join(assignments)}
                WHERE tenant_id = $1::uuid
                  AND id::text = $2
                """,
                *args,
            )
        return await self.get_dependency(dependency_id, tenant_slug=tenant_slug)

    async def delete_dependency(
        self,
        dependency_id: str,
        tenant_slug: str = "default",
    ) -> bool:
        """Delete dependency edge."""
        if not await self._ensure_ready():
            return False

        assert self._pool is not None
        tenant_id = await self._resolve_tenant_id(tenant_slug)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM public.service_dependencies
                WHERE tenant_id = $1::uuid
                  AND id::text = $2
                """,
                tenant_id,
                dependency_id,
            )
        return result.endswith("1")


service_catalog_store: ServiceCatalogStore | None = None


def get_service_catalog_store() -> ServiceCatalogStore:
    """Get singleton service catalog store."""
    global service_catalog_store
    if service_catalog_store is None:
        settings = get_settings()
        service_catalog_store = ServiceCatalogStore(settings.database_url)
    return service_catalog_store


async def init_service_catalog_store() -> ServiceCatalogStore:
    """Initialize singleton service catalog store."""
    store = get_service_catalog_store()
    await store.initialize()
    return store


async def close_service_catalog_store() -> None:
    """Close singleton service catalog store."""
    global service_catalog_store
    if service_catalog_store is None:
        return
    await service_catalog_store.disconnect()
    service_catalog_store = None
