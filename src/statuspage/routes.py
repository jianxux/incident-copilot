"""API routes for status page management.

Provides REST API endpoints for managing status pages, components,
incidents, and automation settings.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import get_settings
from .automation import get_status_automation
from .client import get_statuspage_client
from .models import (
    ComponentImpact,
    ComponentMapping,
    ComponentStatus,
    IncidentImpact,
    IncidentStatus,
)
from .sync import get_status_sync
from .templates import TemplateCategory, get_templates

logger = structlog.get_logger()
router = APIRouter(prefix="/statuspage", tags=["statuspage"])


# ==================== Request/Response Models ====================


class ComponentStatusRequest(BaseModel):
    """Request to update component status."""

    status: ComponentStatus


class CreateIncidentRequest(BaseModel):
    """Request to create a status page incident."""

    name: str = Field(..., min_length=1, max_length=500)
    status: IncidentStatus = IncidentStatus.INVESTIGATING
    impact: IncidentImpact = IncidentImpact.NONE
    body: str | None = None
    component_ids: list[str] = Field(default_factory=list)
    deliver_notifications: bool = True


class UpdateIncidentRequest(BaseModel):
    """Request to update a status page incident."""

    status: IncidentStatus | None = None
    impact: IncidentImpact | None = None
    body: str | None = None
    component_statuses: dict[str, ComponentStatus] = Field(default_factory=dict)
    deliver_notifications: bool = True


class ResolveIncidentRequest(BaseModel):
    """Request to resolve a status page incident."""

    body: str | None = None
    deliver_notifications: bool = True


class PostUpdateRequest(BaseModel):
    """Request to post a custom update."""

    status: IncidentStatus
    body: str = Field(..., min_length=1)
    deliver_notifications: bool = True


class AddMappingRequest(BaseModel):
    """Request to add a component mapping."""

    internal_service: str
    component_id: str
    page_id: str | None = None
    severity_threshold: str = "high"
    auto_update: bool = True


class RenderTemplateRequest(BaseModel):
    """Request to render a template."""

    template_id: str
    variables: dict[str, str] = Field(default_factory=dict)


class SetOverrideRequest(BaseModel):
    """Request to set manual override."""

    enabled: bool = True


# ==================== Page Routes ====================


@router.get("/pages")
async def list_pages():
    """List all accessible status pages."""
    client = get_statuspage_client()

    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Statuspage integration not configured",
        )

    try:
        pages = await client.list_pages()
        return {
            "pages": [
                {
                    "id": p.id,
                    "name": p.name,
                    "subdomain": p.subdomain,
                    "url": p.url,
                }
                for p in pages
            ],
            "total": len(pages),
        }
    except Exception as e:
        logger.error("statuspage_list_pages_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{page_id}")
async def get_page(page_id: str):
    """Get details of a status page."""
    client = get_statuspage_client()

    try:
        page = await client.get_page(page_id)
        return {
            "id": page.id,
            "name": page.name,
            "subdomain": page.subdomain,
            "domain": page.domain,
            "url": page.url,
            "time_zone": page.time_zone,
        }
    except Exception as e:
        logger.error("statuspage_get_page_failed", page_id=page_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Component Routes ====================


@router.get("/components")
async def list_components(page_id: str | None = Query(None)):
    """List all components on a status page."""
    client = get_statuspage_client()

    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Statuspage integration not configured",
        )

    try:
        components = await client.list_components(page_id)
        return {
            "components": [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "description": c.description,
                    "group_id": c.group_id,
                    "position": c.position,
                }
                for c in components
            ],
            "total": len(components),
        }
    except Exception as e:
        logger.error("statuspage_list_components_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/components/{component_id}")
async def get_component(component_id: str, page_id: str | None = Query(None)):
    """Get details of a specific component."""
    client = get_statuspage_client()

    try:
        component = await client.get_component(component_id, page_id)
        return {
            "id": component.id,
            "name": component.name,
            "status": component.status,
            "description": component.description,
            "group_id": component.group_id,
            "position": component.position,
            "created_at": component.created_at.isoformat() if component.created_at else None,
            "updated_at": component.updated_at.isoformat() if component.updated_at else None,
        }
    except Exception as e:
        logger.error(
            "statuspage_get_component_failed",
            component_id=component_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/components/{component_id}/status")
async def update_component_status(
    component_id: str,
    request: ComponentStatusRequest,
    page_id: str | None = Query(None),
):
    """Update a component's status."""
    client = get_statuspage_client()

    try:
        component = await client.update_component_status(
            component_id, request.status, page_id
        )
        return {
            "id": component.id,
            "name": component.name,
            "status": component.status,
            "updated": True,
        }
    except Exception as e:
        logger.error(
            "statuspage_update_component_failed",
            component_id=component_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/components/{component_id}/uptime")
async def get_component_uptime(
    component_id: str,
    days: int = Query(30, ge=1, le=365),
    page_id: str | None = Query(None),
):
    """Get uptime metrics for a component."""
    client = get_statuspage_client()

    try:
        end_date = datetime.utcnow()
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta

        start_date = start_date - timedelta(days=days)

        metrics = await client.get_component_uptime(
            component_id, start_date, end_date, page_id
        )
        return {
            "component_id": metrics.component_id,
            "component_name": metrics.component_name,
            "uptime_percentage": metrics.uptime_percentage,
            "downtime_minutes": metrics.downtime_minutes,
            "total_incidents": metrics.total_incidents,
            "avg_resolution_minutes": metrics.avg_resolution_minutes,
            "period_start": metrics.period_start.isoformat(),
            "period_end": metrics.period_end.isoformat(),
        }
    except Exception as e:
        logger.error(
            "statuspage_get_uptime_failed",
            component_id=component_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Incident Routes ====================


@router.get("/incidents")
async def list_incidents(
    page_id: str | None = Query(None),
    status: IncidentStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List incidents on a status page."""
    client = get_statuspage_client()

    if not client.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Statuspage integration not configured",
        )

    try:
        incidents = await client.list_incidents(page_id, status, limit)
        return {
            "incidents": [
                {
                    "id": i.id,
                    "name": i.name,
                    "status": i.status,
                    "impact": i.impact,
                    "shortlink": i.shortlink,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                    "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
                    "component_count": len(i.component_ids),
                }
                for i in incidents
            ],
            "total": len(incidents),
        }
    except Exception as e:
        logger.error("statuspage_list_incidents_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents/unresolved")
async def list_unresolved_incidents(page_id: str | None = Query(None)):
    """List all unresolved incidents."""
    client = get_statuspage_client()

    try:
        incidents = await client.list_unresolved_incidents(page_id)
        return {
            "incidents": [
                {
                    "id": i.id,
                    "name": i.name,
                    "status": i.status,
                    "impact": i.impact,
                    "shortlink": i.shortlink,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                    "component_ids": i.component_ids,
                }
                for i in incidents
            ],
            "total": len(incidents),
        }
    except Exception as e:
        logger.error("statuspage_list_unresolved_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, page_id: str | None = Query(None)):
    """Get details of a specific incident."""
    client = get_statuspage_client()

    try:
        incident = await client.get_incident(incident_id, page_id)
        return {
            "id": incident.id,
            "name": incident.name,
            "status": incident.status,
            "impact": incident.impact,
            "shortlink": incident.shortlink,
            "created_at": incident.created_at.isoformat() if incident.created_at else None,
            "updated_at": incident.updated_at.isoformat() if incident.updated_at else None,
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "component_ids": incident.component_ids,
            "components": incident.components,
            "updates": [
                {
                    "id": u.id,
                    "status": u.status,
                    "body": u.body,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in incident.incident_updates
            ],
        }
    except Exception as e:
        logger.error(
            "statuspage_get_incident_failed",
            incident_id=incident_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/incidents", status_code=201)
async def create_incident(
    request: CreateIncidentRequest,
    page_id: str | None = Query(None),
):
    """Create a new status page incident."""
    client = get_statuspage_client()

    try:
        incident = await client.create_incident(
            name=request.name,
            status=request.status,
            impact=request.impact,
            body=request.body,
            component_ids=request.component_ids if request.component_ids else None,
            deliver_notifications=request.deliver_notifications,
            page_id=page_id,
        )
        return {
            "id": incident.id,
            "name": incident.name,
            "status": incident.status,
            "shortlink": incident.shortlink,
            "created": True,
        }
    except Exception as e:
        logger.error("statuspage_create_incident_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/incidents/{incident_id}")
async def update_incident(
    incident_id: str,
    request: UpdateIncidentRequest,
    page_id: str | None = Query(None),
):
    """Update an existing incident."""
    client = get_statuspage_client()

    try:
        component_statuses = (
            {k: v for k, v in request.component_statuses.items()}
            if request.component_statuses
            else None
        )

        incident = await client.update_incident(
            incident_id=incident_id,
            status=request.status,
            impact=request.impact,
            body=request.body,
            component_statuses=component_statuses,
            deliver_notifications=request.deliver_notifications,
            page_id=page_id,
        )
        return {
            "id": incident.id,
            "name": incident.name,
            "status": incident.status,
            "updated": True,
        }
    except Exception as e:
        logger.error(
            "statuspage_update_incident_failed",
            incident_id=incident_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    request: ResolveIncidentRequest,
    page_id: str | None = Query(None),
):
    """Resolve an incident."""
    client = get_statuspage_client()

    try:
        incident = await client.resolve_incident(
            incident_id=incident_id,
            body=request.body,
            deliver_notifications=request.deliver_notifications,
            page_id=page_id,
        )
        return {
            "id": incident.id,
            "name": incident.name,
            "status": incident.status,
            "resolved": True,
        }
    except Exception as e:
        logger.error(
            "statuspage_resolve_incident_failed",
            incident_id=incident_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/incidents/{incident_id}")
async def delete_incident(incident_id: str, page_id: str | None = Query(None)):
    """Delete an incident."""
    client = get_statuspage_client()

    try:
        await client.delete_incident(incident_id, page_id)
        return {"deleted": True, "incident_id": incident_id}
    except Exception as e:
        logger.error(
            "statuspage_delete_incident_failed",
            incident_id=incident_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Sync & Mapping Routes ====================


@router.get("/mappings")
async def list_mappings():
    """List all component mappings."""
    sync = get_status_sync()
    return {
        "mappings": [
            {
                "internal_service": m.internal_service,
                "component_id": m.component_id,
                "page_id": m.page_id,
                "severity_threshold": m.severity_threshold,
                "auto_update": m.auto_update,
            }
            for m in sync.component_mappings
        ],
        "total": len(sync.component_mappings),
    }


@router.post("/mappings", status_code=201)
async def add_mapping(request: AddMappingRequest):
    """Add a component mapping."""
    sync = get_status_sync()
    client = get_statuspage_client()

    mapping = ComponentMapping(
        internal_service=request.internal_service,
        component_id=request.component_id,
        page_id=request.page_id or client.default_page_id,
        severity_threshold=request.severity_threshold,
        auto_update=request.auto_update,
    )

    sync.add_mapping(mapping)

    return {
        "internal_service": mapping.internal_service,
        "component_id": mapping.component_id,
        "created": True,
    }


@router.delete("/mappings/{internal_service}")
async def remove_mapping(internal_service: str):
    """Remove a component mapping."""
    sync = get_status_sync()

    original_count = len(sync.component_mappings)
    sync.component_mappings = [
        m
        for m in sync.component_mappings
        if m.internal_service.lower() != internal_service.lower()
    ]

    if len(sync.component_mappings) == original_count:
        raise HTTPException(status_code=404, detail="Mapping not found")

    return {"deleted": True, "internal_service": internal_service}


@router.get("/sync/{internal_incident_id}")
async def get_synced_incident(internal_incident_id: str):
    """Get the status incident synced to an internal incident."""
    sync = get_status_sync()

    status_incident = await sync.get_synced_status_incident(internal_incident_id)
    if not status_incident:
        raise HTTPException(status_code=404, detail="No synced incident found")

    return {
        "internal_incident_id": internal_incident_id,
        "status_incident_id": status_incident.id,
        "name": status_incident.name,
        "status": status_incident.status,
        "shortlink": status_incident.shortlink,
    }


# ==================== Template Routes ====================


@router.get("/templates")
async def list_templates(category: TemplateCategory | None = Query(None)):
    """List available templates."""
    templates = get_templates()

    if category:
        template_list = templates.get_templates_by_category(category)
    else:
        template_list = templates.list_all_templates()

    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "description": t.description,
                "variables": t.variables,
                "is_default": t.is_default,
            }
            for t in template_list
        ],
        "total": len(template_list),
    }


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get a specific template."""
    templates = get_templates()
    template = templates.get_template(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "category": template.category,
        "description": template.description,
        "template": template.template,
        "variables": template.variables,
        "is_default": template.is_default,
    }


@router.post("/templates/render")
async def render_template(request: RenderTemplateRequest):
    """Render a template with provided variables."""
    templates = get_templates()

    try:
        rendered = templates.render_template(request.template_id, request.variables)
        return {"rendered": rendered, "template_id": request.template_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== Automation Routes ====================


@router.post("/automation/override/{internal_incident_id}")
async def set_manual_override(internal_incident_id: str, request: SetOverrideRequest):
    """Enable or disable manual override for an incident."""
    automation = get_status_automation()

    if request.enabled:
        automation.set_manual_override(internal_incident_id)
    else:
        automation.clear_manual_override(internal_incident_id)

    return {
        "internal_incident_id": internal_incident_id,
        "manual_override": request.enabled,
    }


@router.get("/automation/override/{internal_incident_id}")
async def get_manual_override(internal_incident_id: str):
    """Check if manual override is enabled for an incident."""
    automation = get_status_automation()
    has_override = automation.has_manual_override(internal_incident_id)

    return {
        "internal_incident_id": internal_incident_id,
        "manual_override": has_override,
    }


@router.post("/automation/custom-update/{internal_incident_id}")
async def post_custom_update(
    internal_incident_id: str,
    request: PostUpdateRequest,
    page_id: str | None = Query(None),
):
    """Post a custom update to a synced status incident."""
    automation = get_status_automation()

    result = await automation.post_custom_update(
        internal_incident_id,
        request.status,
        request.body,
        page_id,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Update failed")

    return {
        "internal_incident_id": internal_incident_id,
        "status_incident_id": result.status_incident_id,
        "status": request.status,
        "updated": True,
    }


@router.post("/automation/process-pending")
async def process_pending_incidents(background_tasks: BackgroundTasks):
    """Process pending status incidents."""
    automation = get_status_automation()
    background_tasks.add_task(automation.process_pending_incidents)
    return {"status": "processing_scheduled"}


@router.get("/automation/config")
async def get_automation_config():
    """Get current automation configuration."""
    automation = get_status_automation()
    config = automation.config

    return {
        "enabled": config.enabled,
        "auto_create_for_severities": config.auto_create_for_severities,
        "auto_update_enabled": config.auto_update_enabled,
        "auto_resolve_enabled": config.auto_resolve_enabled,
        "notification_delay_seconds": config.notification_delay_seconds,
        "require_acknowledgement": config.require_acknowledgement,
        "group_related_incidents": config.group_related_incidents,
        "grouping_window_minutes": config.grouping_window_minutes,
    }
