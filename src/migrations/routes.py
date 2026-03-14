"""API routes for migration management."""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .models import MigrationEntityType, MigrationJob, MigrationStatus
from .opsgenie.client import OpsgenieClient
from .opsgenie.importer import OpsgenieImporter
from .opsgenie.validator import OpsgenieValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/migrations", tags=["migrations"])

# In-memory job storage
_jobs: dict[str, MigrationJob] = {}
_importers: dict[str, OpsgenieImporter] = {}


class ValidateRequest(BaseModel):
    api_key: str


class StartMigrationRequest(BaseModel):
    api_key: str
    selected_entities: list[MigrationEntityType]


@router.post("/opsgenie/validate")
async def validate_opsgenie(req: ValidateRequest) -> dict[str, Any]:
    """Validate an Opsgenie API key and preview available entities."""
    client = OpsgenieClient(api_key=req.api_key)
    try:
        validator = OpsgenieValidator(client)
        return await validator.full_validate()
    finally:
        await client.close()


@router.post("/opsgenie/start")
async def start_migration(
    req: StartMigrationRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Start an Opsgenie migration job in the background."""
    client = OpsgenieClient(api_key=req.api_key)
    importer = OpsgenieImporter(client, api_key=req.api_key)
    job_id = importer.job.id

    _jobs[job_id] = importer.job
    _importers[job_id] = importer

    async def _run() -> None:
        try:
            await importer.run(req.selected_entities)
        except Exception as e:
            importer.job.status = MigrationStatus.FAILED
            importer.job.error = str(e)
            logger.exception("Migration %s failed", job_id)
        finally:
            await client.close()

    background_tasks.add_task(_run)
    return {"job_id": job_id}


@router.get("/{job_id}/status")
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Get migration job status."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump(mode="json")


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, str]:
    """Cancel a running migration job."""
    importer = _importers.get(job_id)
    if not importer:
        raise HTTPException(status_code=404, detail="Job not found")
    if importer.job.status != MigrationStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Job is not running")
    importer.cancel()
    return {"status": "cancelling"}


@router.get("/history")
async def migration_history() -> list[dict[str, Any]]:
    """List all migration jobs."""
    return [job.model_dump(mode="json") for job in _jobs.values()]
