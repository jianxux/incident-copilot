"""Advanced Incident Memory APIs (Phase 4)."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..config import get_settings
from ..memory.capture import IncidentCapture
from ..memory.config import IncidentMemoryConfig
from ..memory.correlation import ServiceCorrelationAnalyzer
from ..memory.health import MemoryHealthChecker
from ..memory.importer import IncidentMemoryImporter
from ..memory.runbook_generator import RunbookGenerator
from ..memory.store import IncidentMemoryStore

logger = structlog.get_logger()
router = APIRouter(prefix="/api/memory", tags=["memory-advanced"])


class GenerateRunbookRequest(BaseModel):
    service: str = Field(..., min_length=1)
    root_cause_category: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


@router.get("/correlations")
async def get_service_correlations(
    lookback_days: Annotated[int, Query(ge=1, le=365)] = 90,
    min_coincidents: Annotated[int, Query(ge=1, le=50)] = 2,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    """Find services that frequently fail together."""
    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)
    analyzer = ServiceCorrelationAnalyzer(
        database_url=config.database_url, config=config
    )

    try:
        correlations = await analyzer.analyze(
            lookback_days=lookback_days,
            min_coincidents=min_coincidents,
            limit=limit,
        )
        return {
            "lookback_days": lookback_days,
            "min_coincidents": min_coincidents,
            "count": len(correlations),
            "correlations": [item.model_dump() for item in correlations],
        }
    finally:
        await analyzer.disconnect()


@router.post("/runbooks/generate")
async def generate_runbook(request: GenerateRunbookRequest):
    """Generate a runbook from historical incidents for a service/root-cause pair."""
    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)
    generator = RunbookGenerator(settings=settings, config=config)

    try:
        runbook = await generator.generate(
            service=request.service,
            root_cause_category=request.root_cause_category,
            limit=request.limit,
        )
        return runbook.model_dump()
    finally:
        await generator.disconnect()


@router.get("/health")
async def get_memory_health(
    min_recall_hit_rate: Annotated[float, Query(ge=0.0, le=1.0)] = 0.35,
    stale_after_days: Annotated[int, Query(ge=1, le=365)] = 14,
):
    """Check incident memory health alerts and status."""
    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)
    checker = MemoryHealthChecker(settings=settings, config=config)

    try:
        report = await checker.check(
            min_recall_hit_rate=min_recall_hit_rate,
            stale_after_days=stale_after_days,
        )
        return report.model_dump()
    finally:
        await checker.disconnect()


@router.post("/import")
async def import_incidents(
    file: UploadFile = File(...),
    format_hint: Annotated[str | None, Query(pattern="^(csv|json)$")] = None,
):
    """Cold-start import incidents from CSV or JSON files."""
    filename = file.filename or "incidents"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Upload file is empty")

    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)
    store = IncidentMemoryStore(database_url=config.database_url, config=config)
    capture = IncidentCapture(settings=settings, store=store, config=config)
    importer = IncidentMemoryImporter(capture=capture)

    try:
        result = await importer.import_content(
            filename=filename,
            content=content,
            format_hint=format_hint,
        )
        return {
            "filename": filename,
            "imported_count": result.imported_count,
            "failed_count": result.failed_count,
            "failed_items": result.failed_items,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("incident_memory_import_failed", filename=filename, error=str(exc))
        raise HTTPException(status_code=500, detail="Incident import failed") from exc
    finally:
        await capture.close()
        await store.disconnect()
