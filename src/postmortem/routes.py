"""FastAPI routes for postmortem management."""

from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..config import get_settings
from ..models import ContextCard, Severity
from .generator import PostmortemGenerator
from .models import (
    Postmortem,
    PostmortemFormat,
    PostmortemGenerateRequest,
    PostmortemStatus,
    PostmortemUpdateRequest,
)
from .store import postmortem_store
from .templates import render_postmortem

logger = structlog.get_logger()
router = APIRouter(prefix="/api/postmortems", tags=["postmortems"])


class GenerateResponse(BaseModel):
    """Response for postmortem generation."""

    postmortem: Postmortem
    message: str


class ExportRequest(BaseModel):
    """Request to export a postmortem."""

    format: PostmortemFormat = PostmortemFormat.MARKDOWN


class ExportResponse(BaseModel):
    """Response containing exported postmortem."""

    format: PostmortemFormat
    content: str
    postmortem_id: str


class PostmortemListResponse(BaseModel):
    """Response for listing postmortems."""

    postmortems: list[Postmortem]
    total: int


@router.post("/generate", response_model=GenerateResponse)
async def generate_postmortem(request: PostmortemGenerateRequest) -> GenerateResponse:
    """
    Generate a new postmortem from incident context.

    This endpoint uses AI to analyze incident data and generate a comprehensive
    postmortem including timeline, root cause analysis, impact assessment,
    and action items.

    Example request:
    ```json
    {
        "incident_id": "INC-12345",
        "format": "markdown",
        "include_ai_analysis": true,
        "custom_context": "Additional context about the incident"
    }
    ```
    """
    settings = get_settings()
    generator = PostmortemGenerator(settings)

    # Check if postmortem already exists for this incident
    existing = await postmortem_store.get_by_incident(request.incident_id)
    if existing:
        logger.info(
            "postmortem_already_exists",
            incident_id=request.incident_id,
            postmortem_id=existing.id,
        )
        return GenerateResponse(
            postmortem=existing,
            message=f"Postmortem already exists for incident {request.incident_id}",
        )

    # For now, create a minimal context card
    # In production, this would be fetched from the orchestrator
    # or provided in the request body
    context_card = ContextCard(
        incident_id=request.incident_id,
        title=f"Incident {request.incident_id}",
        severity=Severity.MEDIUM,
        service_name="unknown-service",
        triggered_at=__import__("datetime").datetime.utcnow(),
    )

    try:
        postmortem = await generator.generate(
            incident_id=request.incident_id,
            context_card=context_card,
            include_ai_analysis=request.include_ai_analysis,
        )

        # Save to store
        await postmortem_store.save(postmortem)

        logger.info(
            "postmortem_generated",
            incident_id=request.incident_id,
            postmortem_id=postmortem.id,
            ai_generated=postmortem.ai_generated,
        )

        return GenerateResponse(
            postmortem=postmortem,
            message="Postmortem generated successfully",
        )

    except Exception as e:
        logger.error(
            "postmortem_generation_failed",
            incident_id=request.incident_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate postmortem: {str(e)}",
        )


@router.post("/generate-from-context", response_model=GenerateResponse)
async def generate_postmortem_from_context(
    context_card: ContextCard,
    include_ai_analysis: bool = True,
) -> GenerateResponse:
    """
    Generate a postmortem from a provided context card.

    This endpoint allows generating a postmortem with full context data,
    useful when the context has already been assembled by the orchestrator.
    """
    settings = get_settings()
    generator = PostmortemGenerator(settings)

    # Check if postmortem already exists
    existing = await postmortem_store.get_by_incident(context_card.incident_id)
    if existing:
        return GenerateResponse(
            postmortem=existing,
            message=f"Postmortem already exists for incident {context_card.incident_id}",
        )

    try:
        postmortem = await generator.generate(
            incident_id=context_card.incident_id,
            context_card=context_card,
            include_ai_analysis=include_ai_analysis,
        )

        await postmortem_store.save(postmortem)

        return GenerateResponse(
            postmortem=postmortem,
            message="Postmortem generated successfully from context",
        )

    except Exception as e:
        logger.error(
            "postmortem_generation_failed",
            incident_id=context_card.incident_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate postmortem: {str(e)}",
        )


@router.get("/{postmortem_id}", response_model=Postmortem)
async def get_postmortem(postmortem_id: str) -> Postmortem:
    """
    Get a postmortem by its ID.

    Returns the full postmortem document including all sections.
    """
    postmortem = await postmortem_store.get(postmortem_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"Postmortem {postmortem_id} not found",
        )
    return postmortem


@router.get("/by-incident/{incident_id}", response_model=Postmortem)
async def get_postmortem_by_incident(incident_id: str) -> Postmortem:
    """
    Get a postmortem by incident ID.

    Returns the postmortem associated with the given incident.
    """
    postmortem = await postmortem_store.get_by_incident(incident_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"No postmortem found for incident {incident_id}",
        )
    return postmortem


@router.put("/{postmortem_id}", response_model=Postmortem)
async def update_postmortem(
    postmortem_id: str,
    updates: PostmortemUpdateRequest,
) -> Postmortem:
    """
    Update an existing postmortem.

    Allows updating specific fields of a postmortem document.
    Only provided fields will be updated.
    """
    # First get the postmortem to find its incident_id
    postmortem = await postmortem_store.get(postmortem_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"Postmortem {postmortem_id} not found",
        )

    # Update using incident_id (as that's how store.update works)
    updated = await postmortem_store.update(postmortem.incident_id, updates)
    if not updated:
        raise HTTPException(
            status_code=500,
            detail="Failed to update postmortem",
        )

    logger.info(
        "postmortem_updated",
        postmortem_id=postmortem_id,
        version=updated.version,
    )

    return updated


@router.delete("/{postmortem_id}")
async def delete_postmortem(postmortem_id: str) -> dict:
    """
    Delete a postmortem.

    Permanently removes the postmortem document.
    """
    # First get the postmortem to find its incident_id
    postmortem = await postmortem_store.get(postmortem_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"Postmortem {postmortem_id} not found",
        )

    deleted = await postmortem_store.delete(postmortem.incident_id)
    if not deleted:
        raise HTTPException(
            status_code=500,
            detail="Failed to delete postmortem",
        )

    logger.info("postmortem_deleted", postmortem_id=postmortem_id)

    return {"message": f"Postmortem {postmortem_id} deleted successfully"}


@router.get("", response_model=PostmortemListResponse)
async def list_postmortems(
    status: Annotated[
        PostmortemStatus | None,
        Query(description="Filter by postmortem status"),
    ] = None,
    service: Annotated[
        str | None,
        Query(description="Filter by service name"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of results"),
    ] = 50,
) -> PostmortemListResponse:
    """
    List postmortems with optional filters.

    Returns postmortems sorted by creation date (most recent first).
    """
    postmortems = await postmortem_store.list(
        status=status,
        service_name=service,
        limit=limit,
    )

    return PostmortemListResponse(
        postmortems=postmortems,
        total=len(postmortems),
    )


@router.post("/{postmortem_id}/export", response_model=ExportResponse)
async def export_postmortem(
    postmortem_id: str,
    request: ExportRequest,
) -> ExportResponse:
    """
    Export a postmortem in a specified format.

    Supported formats:
    - markdown: Clean Markdown document
    - confluence: Confluence wiki markup
    - slack: Slack Block Kit JSON
    - json: Structured JSON

    Example request:
    ```json
    {
        "format": "markdown"
    }
    ```
    """
    postmortem = await postmortem_store.get(postmortem_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"Postmortem {postmortem_id} not found",
        )

    try:
        content = render_postmortem(postmortem, request.format)

        logger.info(
            "postmortem_exported",
            postmortem_id=postmortem_id,
            format=request.format.value,
        )

        return ExportResponse(
            format=request.format,
            content=content,
            postmortem_id=postmortem_id,
        )

    except Exception as e:
        logger.error(
            "postmortem_export_failed",
            postmortem_id=postmortem_id,
            format=request.format.value,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export postmortem: {str(e)}",
        )


@router.get("/{postmortem_id}/export/{format}")
async def export_postmortem_raw(
    postmortem_id: str,
    format: PostmortemFormat,
) -> PlainTextResponse:
    """
    Export a postmortem and return the raw content.

    This endpoint returns the exported content directly without JSON wrapping,
    useful for downloading or direct integration.
    """
    postmortem = await postmortem_store.get(postmortem_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"Postmortem {postmortem_id} not found",
        )

    try:
        content = render_postmortem(postmortem, format)

        # Set appropriate content type
        content_types = {
            PostmortemFormat.MARKDOWN: "text/markdown",
            PostmortemFormat.CONFLUENCE: "text/plain",
            PostmortemFormat.SLACK: "application/json",
            PostmortemFormat.JSON: "application/json",
        }

        return PlainTextResponse(
            content=content,
            media_type=content_types.get(format, "text/plain"),
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export postmortem: {str(e)}",
        )


@router.post("/{postmortem_id}/refresh")
async def refresh_postmortem(
    postmortem_id: str,
    sections: Annotated[
        list[str] | None,
        Query(description="Sections to refresh: timeline, root_cause, impact, action_items"),
    ] = None,
) -> Postmortem:
    """
    Refresh a postmortem with updated context.

    Re-runs AI analysis on specified sections using the latest available data.
    If no sections specified, refreshes all AI-generated content.
    """
    postmortem = await postmortem_store.get(postmortem_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"Postmortem {postmortem_id} not found",
        )

    settings = get_settings()
    generator = PostmortemGenerator(settings)

    # Create a minimal context card for refresh
    # In production, this would fetch fresh data
    context_card = ContextCard(
        incident_id=postmortem.incident_id,
        title=postmortem.title.replace("Postmortem: ", ""),
        severity=Severity(postmortem.severity),
        service_name=postmortem.service_name,
        triggered_at=postmortem.incident_started_at or __import__("datetime").datetime.utcnow(),
        alert_url=postmortem.alert_url,
        dashboard_url=postmortem.dashboard_url,
    )

    try:
        updated = await generator.update_incrementally(
            postmortem=postmortem,
            context_card=context_card,
            sections=sections,
        )

        await postmortem_store.save(updated)

        logger.info(
            "postmortem_refreshed",
            postmortem_id=postmortem_id,
            sections=sections or "all",
        )

        return updated

    except Exception as e:
        logger.error(
            "postmortem_refresh_failed",
            postmortem_id=postmortem_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refresh postmortem: {str(e)}",
        )


@router.post("/{postmortem_id}/status")
async def update_postmortem_status(
    postmortem_id: str,
    status: PostmortemStatus,
    approved_by: str | None = None,
) -> Postmortem:
    """
    Update the status of a postmortem.

    Status flow: draft -> in_review -> approved -> published
    """
    postmortem = await postmortem_store.get(postmortem_id)
    if not postmortem:
        raise HTTPException(
            status_code=404,
            detail=f"Postmortem {postmortem_id} not found",
        )

    # Validate status transitions
    valid_transitions = {
        PostmortemStatus.DRAFT: [PostmortemStatus.IN_REVIEW],
        PostmortemStatus.IN_REVIEW: [PostmortemStatus.DRAFT, PostmortemStatus.APPROVED],
        PostmortemStatus.APPROVED: [
            PostmortemStatus.IN_REVIEW,
            PostmortemStatus.PUBLISHED,
        ],
        PostmortemStatus.PUBLISHED: [PostmortemStatus.APPROVED],
    }

    if status not in valid_transitions.get(postmortem.status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition from {postmortem.status.value} to {status.value}",
        )

    updates = PostmortemUpdateRequest(status=status)
    if status == PostmortemStatus.APPROVED and approved_by:
        # Store approved_by separately
        postmortem.approved_by = approved_by

    updated = await postmortem_store.update(postmortem.incident_id, updates)
    if not updated:
        raise HTTPException(
            status_code=500,
            detail="Failed to update status",
        )

    if approved_by:
        updated.approved_by = approved_by
        await postmortem_store.save(updated)

    logger.info(
        "postmortem_status_updated",
        postmortem_id=postmortem_id,
        old_status=postmortem.status.value,
        new_status=status.value,
    )

    return updated
