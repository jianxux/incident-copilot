"""API endpoints for plugin management."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from ..plugins import PluginRegistry, get_registry
from ..plugins.models import (
    Plugin,
    PluginCreateRequest,
    PluginEvent,
    PluginStatus,
    PluginTestRequest,
    PluginTestResult,
    PluginType,
    PluginUpdateRequest,
)
from ..plugins.registry import PluginExistsError, PluginNotFoundError
from ..plugins.transform import get_template, list_templates

logger = structlog.get_logger()
router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.post("", response_model=Plugin, status_code=status.HTTP_201_CREATED)
async def create_plugin(request: PluginCreateRequest) -> Plugin:
    try:
        return await get_registry().register(request)
    except PluginExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=list[Plugin])
async def list_plugins(
    type: PluginType | None = None,
    status_filter: PluginStatus | None = Query(None, alias="status"),
    event: PluginEvent | None = None,
) -> list[Plugin]:
    return get_registry().list(plugin_type=type, status=status_filter, event=event)


@router.get("/{plugin_id}", response_model=Plugin)
async def get_plugin(plugin_id: str) -> Plugin:
    try:
        return get_registry().get(plugin_id)
    except PluginNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{plugin_id}", response_model=Plugin)
async def update_plugin(plugin_id: str, request: PluginUpdateRequest) -> Plugin:
    try:
        return await get_registry().update(plugin_id, request)
    except PluginNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(plugin_id: str) -> None:
    try:
        await get_registry().unregister(plugin_id)
    except PluginNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{plugin_id}/test", response_model=PluginTestResult)
async def test_plugin(plugin_id: str, request: PluginTestRequest) -> PluginTestResult:
    try:
        sample = request.sample_data or {
            "incident_id": "INC-12345",
            "title": "Test incident",
            "severity": "high",
            "service_name": "test-service",
        }
        return await get_registry().test_plugin(plugin_id, sample, request.dry_run)
    except PluginNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{plugin_id}/enable", response_model=Plugin)
async def enable_plugin(plugin_id: str) -> Plugin:
    try:
        return await get_registry().update(
            plugin_id, PluginUpdateRequest(status=PluginStatus.ACTIVE)
        )
    except PluginNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{plugin_id}/disable", response_model=Plugin)
async def disable_plugin(plugin_id: str) -> Plugin:
    try:
        return await get_registry().update(
            plugin_id, PluginUpdateRequest(status=PluginStatus.DISABLED)
        )
    except PluginNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/templates/list", response_model=list[str])
async def list_payload_templates() -> list[str]:
    return list_templates()


@router.get("/templates/{name}", response_model=dict[str, Any])
async def get_payload_template(name: str) -> dict[str, Any]:
    template = get_template(name)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Template '{name}' not found"
        )
    return {"name": name, "template": template}
