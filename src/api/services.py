"""Tenant-scoped services API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth.middleware import AuthContext, get_auth_context
from ..onboarding import checklist_store, service_catalog_store
from ..onboarding.analytics import onboarding_analytics
from ..supabase_client import is_supabase_db_enabled

router = APIRouter(prefix="/api/services", tags=["services"])


class ServiceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source: str = Field(default="manual", max_length=32)
    external_id: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_services(auth: AuthContext = Depends(get_auth_context)):
    """List services for the current tenant."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    if is_supabase_db_enabled():
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        rows = await db.list_services(auth.tenant_id)
        return {
            "services": [
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "source": (row.get("metadata") or {}).get("source", "manual"),
                    "external_id": (row.get("metadata") or {}).get("external_id"),
                    "metadata": row.get("metadata") or {},
                    "created_at": row.get("created_at"),
                }
                for row in rows
            ]
        }

    rows = await service_catalog_store.list(auth.tenant_id)
    return {"services": rows}


@router.post("", status_code=201)
async def create_service(
    request: ServiceCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Create or update a service in the tenant catalog."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    normalized_name = request.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="service_name_required")

    if is_supabase_db_enabled():
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        payload = dict(request.metadata or {})
        payload["source"] = request.source
        payload["external_id"] = request.external_id
        row = await db.upsert_service(
            tenant_id=auth.tenant_id,
            name=normalized_name,
            metadata=payload,
        )
        service = {
            "id": row.get("id"),
            "name": row.get("name"),
            "source": request.source,
            "external_id": request.external_id,
            "metadata": row.get("metadata") or payload,
            "created_at": row.get("created_at"),
        }
    else:
        service = await service_catalog_store.upsert(
            tenant_id=auth.tenant_id,
            name=normalized_name,
            source=request.source,
            external_id=request.external_id,
            metadata=request.metadata,
        )

    await checklist_store.set_step(auth.tenant_id, "add_services", True)
    onboarding_analytics.track_event(
        auth.tenant_id,
        "step_completed",
        "add_services",
        {"service_name": normalized_name},
    )
    return service


@router.delete("/{service_name}", status_code=204)
async def delete_service(
    service_name: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Delete a service by name for the current tenant."""
    if not auth.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required"
        )

    if is_supabase_db_enabled():
        from ..db.supabase_db import get_db

        db = get_db(use_admin=True)
        deleted = await db.delete_service_by_name(
            tenant_id=auth.tenant_id, name=service_name
        )
    else:
        deleted = await service_catalog_store.delete(
            tenant_id=auth.tenant_id, name=service_name
        )

    if not deleted:
        raise HTTPException(status_code=404, detail="service_not_found")
