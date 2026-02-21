"""Tag management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..tagging import AddTagsRequest, AutoTagRuleCreate, TagCreate, TagUpdate
from ..tagging.service import get_tagging_service

router = APIRouter(prefix="/api/tags", tags=["tags"])
incidents_router = APIRouter(tags=["incident-tags"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tag(request: TagCreate):
    service = get_tagging_service()
    try:
        return await service.create_tag(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
async def list_tags():
    service = get_tagging_service()
    result = await service.list_tags(include_children=True)
    return result.model_dump()


@router.get("/{tag_id}")
async def get_tag(tag_id: str):
    service = get_tagging_service()
    tag = await service.get_tag(tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@router.put("/{tag_id}")
async def update_tag(tag_id: str, request: TagUpdate):
    service = get_tagging_service()
    try:
        tag = await service.update_tag(tag_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@router.delete("/{tag_id}")
async def delete_tag(tag_id: str):
    service = get_tagging_service()
    try:
        deleted = await service.delete_tag(tag_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"deleted": True}


@router.post("/rules/auto", status_code=status.HTTP_201_CREATED)
async def create_auto_rule(request: AutoTagRuleCreate):
    service = get_tagging_service()
    try:
        return await service.create_auto_rule(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/rules/auto")
async def list_auto_rules():
    service = get_tagging_service()
    return await service.list_auto_rules()


@router.post("/suggest")
async def suggest_tags(
    title: str,
    service_name: str,
    severity: str,
    description: str | None = None,
):
    service = get_tagging_service()
    return await service.suggest_tags(
        title=title,
        service_name=service_name,
        severity=severity,
        description=description,
    )


@incidents_router.post("/{incident_id}/tags")
async def add_tags_to_incident(incident_id: str, request: AddTagsRequest):
    service = get_tagging_service()
    await service.add_tags_to_incident(incident_id, request)
    return (await service.get_incident_tags(incident_id)).tags


@incidents_router.get("/{incident_id}/tags")
async def get_incident_tags(incident_id: str):
    service = get_tagging_service()
    return (await service.get_incident_tags(incident_id)).tags


@incidents_router.delete("/{incident_id}/tags/{tag_id}")
async def remove_tag_from_incident(incident_id: str, tag_id: str):
    service = get_tagging_service()
    removed = await service.remove_tag_from_incident(incident_id, tag_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Tag association not found")
    return {"deleted": True}


@incidents_router.post("/{incident_id}/tags/auto")
async def auto_tag_incident(
    incident_id: str,
    service_name: str,
    title: str,
    severity: str,
):
    service = get_tagging_service()
    await service.auto_tag_incident(
        incident_id=incident_id,
        service_name=service_name,
        title=title,
        severity=severity,
    )
    return (await service.get_incident_tags(incident_id)).tags
