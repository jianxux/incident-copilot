"""Status Page Integration - FastAPI Routes."""

import uuid
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from .automation import StatusPageAutomation, get_statuspage_automation
from .models import (
    Component,
    ComponentStatus,
    ConfigCreateRequest,
    IncidentCreateRequest,
    IncidentStatus,
    MaintenanceWindow,
    StatusPageConfig,
    StatusPageIncident,
    StatusPageMetrics,
    StatusUpdate,
    SyncResult,
)
from .service import StatusPageService, get_statuspage_service

router = APIRouter(prefix="/statuspage", tags=["statuspage"])


def get_service() -> StatusPageService:
    return get_statuspage_service()


def get_automation() -> StatusPageAutomation:
    return get_statuspage_automation()


@router.post("/configs", response_model=StatusPageConfig)
async def create_config(
    request: ConfigCreateRequest, service: StatusPageService = Depends(get_service)
) -> StatusPageConfig:
    config = StatusPageConfig(
        id=str(uuid.uuid4()),
        name=request.name,
        provider=request.provider,
        credentials=request.credentials,
        auto_sync=request.auto_sync,
        component_mapping=request.component_mapping,
    )
    if not await service.add_config(config):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to validate credentials",
        )
    return config


@router.get("/configs", response_model=list[StatusPageConfig])
async def list_configs(
    service: StatusPageService = Depends(get_service),
) -> list[StatusPageConfig]:
    return service.list_configs()


@router.get("/configs/{config_id}", response_model=StatusPageConfig)
async def get_config(
    config_id: str, service: StatusPageService = Depends(get_service)
) -> StatusPageConfig:
    if not (config := service.get_config(config_id)):
        raise HTTPException(status_code=404, detail="Config not found")
    return config


@router.delete("/configs/{config_id}")
async def delete_config(
    config_id: str, service: StatusPageService = Depends(get_service)
) -> dict[str, str]:
    if not await service.remove_config(config_id):
        raise HTTPException(status_code=404, detail="Config not found")
    return {"status": "deleted", "config_id": config_id}


@router.get("/configs/{config_id}/components", response_model=list[Component])
async def list_components(
    config_id: str, service: StatusPageService = Depends(get_service)
) -> list[Component]:
    return await service.get_components(config_id)


@router.put("/configs/{config_id}/components/{component_id}")
async def update_component(
    config_id: str,
    component_id: str,
    status: ComponentStatus,
    service: StatusPageService = Depends(get_service),
) -> Component:
    if not (
        component := await service.update_component_status(
            config_id, component_id, status
        )
    ):
        raise HTTPException(status_code=404, detail="Component not found")
    return component


@router.post("/configs/{config_id}/components/sync")
async def sync_components(
    config_id: str, service: StatusPageService = Depends(get_service)
) -> SyncResult:
    result = await service.sync_components(config_id)
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.errors
        )
    return result


@router.post("/configs/{config_id}/incidents", response_model=StatusPageIncident)
async def create_incident(
    config_id: str,
    request: IncidentCreateRequest,
    service: StatusPageService = Depends(get_service),
) -> StatusPageIncident:
    incident = StatusPageIncident(
        name=request.name,
        message=request.message,
        status=request.status,
        impact=request.impact,
        component_ids=request.component_ids,
        component_status=request.component_status,
    )
    if not (created := await service.create_incident(config_id, incident)):
        raise HTTPException(status_code=404, detail="Config not found")
    return created


@router.get("/configs/{config_id}/incidents", response_model=list[StatusPageIncident])
async def list_incidents(
    config_id: str, service: StatusPageService = Depends(get_service)
) -> list[StatusPageIncident]:
    return await service.get_active_incidents(config_id)


@router.patch("/configs/{config_id}/incidents/{incident_id}")
async def update_incident(
    config_id: str,
    incident_id: str,
    status_val: IncidentStatus,
    message: str,
    service: StatusPageService = Depends(get_service),
) -> StatusPageIncident:
    update = StatusUpdate(incident_id=incident_id, status=status_val, message=message)
    if not (updated := await service.update_incident(config_id, incident_id, update)):
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated


@router.post("/configs/{config_id}/incidents/{incident_id}/resolve")
async def resolve_incident(
    config_id: str,
    incident_id: str,
    message: str = "Issue resolved.",
    service: StatusPageService = Depends(get_service),
) -> StatusPageIncident:
    if not (
        resolved := await service.resolve_incident(config_id, incident_id, message)
    ):
        raise HTTPException(status_code=404, detail="Incident not found")
    return resolved


@router.get("/configs/{config_id}/maintenances", response_model=list[MaintenanceWindow])
async def list_maintenances(
    config_id: str, service: StatusPageService = Depends(get_service)
) -> list[MaintenanceWindow]:
    return await service.get_scheduled_maintenances(config_id)


@router.post("/configs/{config_id}/maintenances", response_model=MaintenanceWindow)
async def create_maintenance(
    config_id: str,
    maintenance: MaintenanceWindow,
    service: StatusPageService = Depends(get_service),
) -> MaintenanceWindow:
    if not (created := await service.create_maintenance(config_id, maintenance)):
        raise HTTPException(status_code=404, detail="Config not found")
    return created


@router.get("/configs/{config_id}/metrics", response_model=StatusPageMetrics)
async def get_metrics(
    config_id: str, service: StatusPageService = Depends(get_service)
) -> StatusPageMetrics:
    return await service.get_metrics(config_id)


@router.post("/automation/incident")
async def auto_create_incident(
    incident_id: str,
    title: str,
    description: str,
    severity: str,
    affected_services: list[str] | None = None,
    automation: StatusPageAutomation = Depends(get_automation),
) -> dict[str, Any]:
    results = await automation.on_incident_created(
        incident_id, title, description, severity, affected_services or []
    )
    return {"created_on": list(results.keys()), "count": len(results)}


@router.post("/automation/incident/{incident_id}/status")
async def auto_update_status(
    incident_id: str,
    new_status: str,
    message: str | None = None,
    automation: StatusPageAutomation = Depends(get_automation),
) -> dict[str, Any]:
    results = await automation.on_incident_status_change(
        incident_id, new_status, message
    )
    return {"updated_on": list(results.keys()), "count": len(results)}


@router.post("/automation/incident/{incident_id}/resolve")
async def auto_resolve_incident(
    incident_id: str,
    message: str | None = None,
    automation: StatusPageAutomation = Depends(get_automation),
) -> dict[str, Any]:
    results = await automation.on_incident_resolved(incident_id, message)
    return {"resolved_on": list(results.keys()), "count": len(results)}


@router.post("/automation/service/{service_id}/status")
async def auto_update_service_status(
    service_id: str,
    status: str,
    automation: StatusPageAutomation = Depends(get_automation),
) -> dict[str, Any]:
    results = await automation.on_service_status_change(service_id, status)
    return {"updated_on": list(results.keys()), "count": len(results)}
