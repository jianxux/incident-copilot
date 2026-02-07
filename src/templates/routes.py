"""FastAPI routes for incident templates."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .models import (
    AppliedTemplate,
    IncidentTemplate,
    TemplateCategory,
    TemplateCreateRequest,
    TemplateExport,
    TemplateMatch,
    TemplateUpdateRequest,
)
from .service import TemplateService, get_template_service

router = APIRouter(prefix="/templates", tags=["templates"])


class SuggestRequest(BaseModel):
    """Request body for template suggestion."""

    title: str
    description: str | None = None
    service: str | None = None
    source: str | None = None
    tags: list[str] | None = None


class ApplyRequest(BaseModel):
    """Request body for applying a template."""

    template_id: str
    field_values: dict[str, Any] = Field(default_factory=dict)


class CustomizeRequest(BaseModel):
    """Request body for customizing a template."""

    template_id: str


class RecordResolutionRequest(BaseModel):
    """Request body for recording resolution metrics."""

    template_id: str
    resolution_minutes: float
    escalated: bool = False


class ImportRequest(BaseModel):
    """Request body for importing templates."""

    export_data: TemplateExport


@router.get("", response_model=list[IncidentTemplate])
async def list_templates(
    organization_id: str | None = Query(None),
    category: TemplateCategory | None = Query(None),
    include_inactive: bool = Query(False),
    service: TemplateService = Depends(get_template_service),
) -> list[IncidentTemplate]:
    """List all available templates."""
    templates = await service.get_all(organization_id, include_inactive)
    if category:
        templates = [t for t in templates if t.category == category]
    return templates


@router.get("/{template_id}", response_model=IncidentTemplate)
async def get_template(
    template_id: str,
    organization_id: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> IncidentTemplate:
    """Get a specific template by ID."""
    template = await service.get(template_id, organization_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("", response_model=IncidentTemplate, status_code=201)
async def create_template(
    request: TemplateCreateRequest,
    organization_id: str | None = Query(None),
    created_by: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> IncidentTemplate:
    """Create a new template."""
    return await service.create(request, organization_id, created_by)


@router.put("/{template_id}", response_model=IncidentTemplate)
async def update_template(
    template_id: str,
    request: TemplateUpdateRequest,
    organization_id: str | None = Query(None),
    updated_by: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> IncidentTemplate:
    """Update an existing template."""
    template = await service.update(template_id, request, organization_id, updated_by)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found or is built-in")
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    organization_id: str | None = Query(None),
    hard: bool = Query(False),
    service: TemplateService = Depends(get_template_service),
) -> None:
    """Delete a template (soft delete by default)."""
    if hard:
        success = await service.hard_delete(template_id, organization_id)
    else:
        success = await service.delete(template_id, organization_id)

    if not success:
        raise HTTPException(status_code=404, detail="Template not found or is built-in")


@router.post("/suggest", response_model=list[TemplateMatch])
async def suggest_templates(
    request: SuggestRequest,
    organization_id: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    service: TemplateService = Depends(get_template_service),
) -> list[TemplateMatch]:
    """Suggest templates based on alert content."""
    return await service.suggest(
        title=request.title,
        description=request.description,
        service=request.service,
        source=request.source,
        tags=request.tags,
        organization_id=organization_id,
        limit=limit,
    )


@router.post("/apply", response_model=AppliedTemplate)
async def apply_template(
    request: ApplyRequest,
    organization_id: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> AppliedTemplate:
    """Apply a template with field values."""
    result = await service.apply(
        template_id=request.template_id,
        field_values=request.field_values,
        organization_id=organization_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.post("/customize", response_model=IncidentTemplate)
async def customize_template(
    request: CustomizeRequest,
    organization_id: str = Query(...),
    created_by: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> IncidentTemplate:
    """Create an organization-specific copy of a template."""
    template = await service.customize(request.template_id, organization_id, created_by)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("/resolution", status_code=204)
async def record_resolution(
    request: RecordResolutionRequest,
    organization_id: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> None:
    """Record resolution metrics for analytics."""
    await service.record_resolution(
        template_id=request.template_id,
        resolution_minutes=request.resolution_minutes,
        escalated=request.escalated,
        organization_id=organization_id,
    )


@router.get("/analytics/summary")
async def get_analytics(
    organization_id: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> list[dict]:
    """Get analytics for all templates."""
    return await service.get_analytics(organization_id)


@router.post("/export", response_model=TemplateExport)
async def export_templates(
    template_ids: list[str] | None = Query(None),
    organization_id: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> TemplateExport:
    """Export templates to portable format."""
    return await service.export_templates(template_ids, organization_id)


@router.post("/import", response_model=list[IncidentTemplate])
async def import_templates(
    request: ImportRequest,
    organization_id: str = Query(...),
    created_by: str | None = Query(None),
    service: TemplateService = Depends(get_template_service),
) -> list[IncidentTemplate]:
    """Import templates from export format."""
    return await service.import_templates(request.export_data, organization_id, created_by)
