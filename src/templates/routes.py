"""FastAPI routes for incident template management."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .defaults import initialize_default_templates
from .matcher import template_matcher
from .models import (
    IncidentTemplate,
    RenderedChecklist,
    TemplateCategory,
    TemplateCreateRequest,
    TemplateMatch,
    TemplateStepStatus,
    TemplateUpdateRequest,
)
from .renderer import template_renderer
from .store import template_store

logger = structlog.get_logger()
router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateListResponse(BaseModel):
    """Response for listing templates."""

    templates: list[IncidentTemplate]
    total: int


class TemplateMatchResponse(BaseModel):
    """Response for template matching."""

    matches: list[TemplateMatch]
    total: int


class ChecklistCreateRequest(BaseModel):
    """Request to create a checklist from a template."""

    template_id: str
    incident_id: str
    context: dict | None = None


class ChecklistResponse(BaseModel):
    """Response containing a rendered checklist."""

    checklist: RenderedChecklist
    message: str


class StepUpdateRequest(BaseModel):
    """Request to update a step's status."""

    step_id: str
    status: TemplateStepStatus
    completed_by: str | None = None
    notes: str | None = None


class MarkdownExportResponse(BaseModel):
    """Response containing markdown export."""

    markdown: str
    checklist_id: str


class AutoSuggestRequest(BaseModel):
    """Request for auto-suggesting a template."""

    alert_title: str
    alert_description: str | None = None
    service_name: str | None = None
    severity: str | None = None
    tags: list[str] | None = None
    tenant_id: str | None = None


# --- Template CRUD Routes ---


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    category: Annotated[
        TemplateCategory | None,
        Query(description="Filter by category"),
    ] = None,
    tenant_id: Annotated[
        str | None,
        Query(description="Filter by tenant ID"),
    ] = None,
    include_builtin: Annotated[
        bool,
        Query(description="Include built-in templates"),
    ] = True,
    enabled_only: Annotated[
        bool,
        Query(description="Only return enabled templates"),
    ] = True,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Maximum number of results"),
    ] = 100,
) -> TemplateListResponse:
    """
    List incident templates with optional filters.

    Returns templates sorted by usage count (most used first).
    """
    templates = await template_store.list(
        category=category,
        tenant_id=tenant_id,
        include_builtin=include_builtin,
        enabled_only=enabled_only,
        limit=limit,
    )

    return TemplateListResponse(
        templates=templates,
        total=len(templates),
    )


@router.get("/categories")
async def list_categories() -> list[dict]:
    """
    List all available template categories.
    """
    return [
        {"value": cat.value, "name": cat.name}
        for cat in TemplateCategory
    ]


@router.post("", response_model=IncidentTemplate)
async def create_template(
    request: TemplateCreateRequest,
    created_by: str | None = None,
) -> IncidentTemplate:
    """
    Create a new incident template.

    Example request:
    ```json
    {
        "name": "Database Failover",
        "description": "Steps for handling database failover scenarios",
        "category": "database",
        "steps": [
            {
                "id": "step-1",
                "order": 1,
                "title": "Verify database connectivity",
                "description": "Check if the database is reachable",
                "time_estimate_minutes": 5,
                "is_critical": true
            }
        ],
        "keywords": ["database", "failover", "mysql"],
        "service_tags": ["db-primary", "mysql"],
        "severity_levels": ["critical", "high"]
    }
    ```
    """
    template = await template_store.create(request, created_by=created_by)
    
    logger.info(
        "template_created",
        template_id=template.id,
        name=template.name,
        category=template.category.value,
    )
    
    return template


@router.get("/{template_id}", response_model=IncidentTemplate)
async def get_template(template_id: str) -> IncidentTemplate:
    """
    Get a template by its ID.
    """
    template = await template_store.get(template_id)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} not found",
        )
    return template


@router.put("/{template_id}", response_model=IncidentTemplate)
async def update_template(
    template_id: str,
    updates: TemplateUpdateRequest,
) -> IncidentTemplate:
    """
    Update an existing template.

    Only provided fields will be updated.
    """
    template = await template_store.update(template_id, updates)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} not found",
        )
    
    logger.info(
        "template_updated",
        template_id=template_id,
        version=template.version,
    )
    
    return template


@router.delete("/{template_id}")
async def delete_template(template_id: str) -> dict:
    """
    Delete a template.

    Built-in templates cannot be deleted.
    """
    template = await template_store.get(template_id)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} not found",
        )
    
    if template.is_builtin:
        raise HTTPException(
            status_code=400,
            detail="Built-in templates cannot be deleted. Disable it instead.",
        )
    
    deleted = await template_store.delete(template_id)
    if not deleted:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete template",
        )
    
    return {"message": f"Template {template_id} deleted successfully"}


# --- Template Matching Routes ---


@router.post("/match", response_model=TemplateMatchResponse)
async def match_templates(
    query: Annotated[str, Query(description="Alert text to match against")],
    service_name: Annotated[
        str | None,
        Query(description="Service name for matching"),
    ] = None,
    severity: Annotated[
        str | None,
        Query(description="Incident severity"),
    ] = None,
    tags: Annotated[
        list[str] | None,
        Query(description="Alert tags"),
    ] = None,
    tenant_id: Annotated[
        str | None,
        Query(description="Tenant ID"),
    ] = None,
    min_score: Annotated[
        float,
        Query(ge=0.0, le=1.0, description="Minimum relevance score"),
    ] = 0.1,
    top_k: Annotated[
        int,
        Query(ge=1, le=20, description="Maximum results"),
    ] = 5,
) -> TemplateMatchResponse:
    """
    Find templates matching the given alert context.

    Returns templates sorted by relevance score.
    """
    matches = await template_matcher.find_matching_templates(
        query=query,
        service_name=service_name,
        severity=severity,
        tags=tags,
        tenant_id=tenant_id,
        min_score=min_score,
        top_k=top_k,
    )
    
    return TemplateMatchResponse(
        matches=matches,
        total=len(matches),
    )


@router.post("/auto-suggest", response_model=TemplateMatch | None)
async def auto_suggest_template(
    request: AutoSuggestRequest,
) -> TemplateMatch | None:
    """
    Automatically suggest the best matching template for an alert.

    Returns the top match if relevance score >= 0.3, otherwise null.
    """
    match = await template_matcher.auto_suggest(
        alert_title=request.alert_title,
        alert_description=request.alert_description,
        service_name=request.service_name,
        severity=request.severity,
        tags=request.tags,
        tenant_id=request.tenant_id,
    )
    
    return match


# --- Checklist Routes ---


@router.post("/checklists", response_model=ChecklistResponse)
async def create_checklist(request: ChecklistCreateRequest) -> ChecklistResponse:
    """
    Create a rendered checklist from a template for an incident.

    Example request:
    ```json
    {
        "template_id": "tmpl-abc123",
        "incident_id": "INC-12345",
        "context": {
            "service_name": "payments-api",
            "environment": "production"
        }
    }
    ```
    """
    template = await template_store.get(request.template_id)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template {request.template_id} not found",
        )
    
    checklist = await template_renderer.render(
        template=template,
        incident_id=request.incident_id,
        context=request.context,
    )
    
    # Save the checklist
    await template_store.save_checklist(checklist)
    
    return ChecklistResponse(
        checklist=checklist,
        message="Checklist created successfully",
    )


@router.get("/checklists/{checklist_id}", response_model=RenderedChecklist)
async def get_checklist(checklist_id: str) -> RenderedChecklist:
    """
    Get a checklist by its ID.
    """
    checklist = await template_store.get_checklist(checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    return checklist


@router.get("/checklists/incident/{incident_id}", response_model=list[RenderedChecklist])
async def get_checklists_for_incident(incident_id: str) -> list[RenderedChecklist]:
    """
    Get all checklists for a specific incident.
    """
    checklists = await template_store.get_checklists_for_incident(incident_id)
    return checklists


@router.patch("/checklists/{checklist_id}/steps", response_model=RenderedChecklist)
async def update_checklist_step(
    checklist_id: str,
    request: StepUpdateRequest,
) -> RenderedChecklist:
    """
    Update the status of a step in a checklist.

    Example request:
    ```json
    {
        "step_id": "step-1",
        "status": "completed",
        "completed_by": "john.doe@example.com",
        "notes": "Verified database is accessible"
    }
    ```
    """
    checklist = await template_store.get_checklist(checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    
    # Find and validate step exists
    step_exists = any(s.step_id == request.step_id for s in checklist.steps)
    if not step_exists:
        raise HTTPException(
            status_code=404,
            detail=f"Step {request.step_id} not found in checklist",
        )
    
    updated_checklist = await template_renderer.update_step_status(
        checklist=checklist,
        step_id=request.step_id,
        status=request.status,
        completed_by=request.completed_by,
        notes=request.notes,
    )
    
    # Save updated checklist
    await template_store.save_checklist(updated_checklist)
    
    return updated_checklist


@router.delete("/checklists/{checklist_id}")
async def delete_checklist(checklist_id: str) -> dict:
    """
    Delete a checklist.
    """
    deleted = await template_store.delete_checklist(checklist_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    
    return {"message": f"Checklist {checklist_id} deleted successfully"}


# --- Export Routes ---


@router.get("/checklists/{checklist_id}/export/markdown", response_model=MarkdownExportResponse)
async def export_checklist_markdown(
    checklist_id: str,
    include_header: bool = True,
) -> MarkdownExportResponse:
    """
    Export a checklist to Markdown format.
    """
    checklist = await template_store.get_checklist(checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    
    markdown = await template_renderer.render_to_markdown(
        checklist=checklist,
        include_header=include_header,
    )
    
    return MarkdownExportResponse(
        markdown=markdown,
        checklist_id=checklist_id,
    )


@router.get("/checklists/{checklist_id}/export/slack")
async def export_checklist_slack(checklist_id: str) -> list[dict]:
    """
    Export a checklist to Slack Block Kit format.
    """
    checklist = await template_store.get_checklist(checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    
    blocks = await template_renderer.render_to_slack_blocks(checklist)
    return blocks


@router.get("/checklists/{checklist_id}/export/html")
async def export_checklist_html(checklist_id: str) -> dict:
    """
    Export a checklist to HTML format.
    """
    checklist = await template_store.get_checklist(checklist_id)
    if not checklist:
        raise HTTPException(
            status_code=404,
            detail=f"Checklist {checklist_id} not found",
        )
    
    html = await template_renderer.render_to_html(checklist)
    return {"html": html, "checklist_id": checklist_id}


# --- Admin Routes ---


@router.post("/initialize-defaults")
async def initialize_defaults() -> dict:
    """
    Initialize the built-in default templates.

    This is idempotent - existing built-in templates will not be duplicated.
    """
    count = await initialize_default_templates()
    return {
        "message": f"Initialized {count} default templates",
        "count": count,
    }


@router.get("/builtin", response_model=TemplateListResponse)
async def list_builtin_templates() -> TemplateListResponse:
    """
    List all built-in templates.
    """
    templates = await template_store.get_builtin_templates()
    return TemplateListResponse(
        templates=templates,
        total=len(templates),
    )
