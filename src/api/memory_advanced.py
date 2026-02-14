"""Advanced Incident Memory APIs (Phase 4)."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..config import get_settings
from ..memory.capture import IncidentCapture
from ..memory.config import IncidentMemoryConfig
from ..memory.correlation import ServiceCorrelationEngine
from ..memory.health import MemoryHealthChecker
from ..memory.importer import IncidentMemoryImporter
from ..memory.runbooks import AutoRunbookGenerator
from ..memory.store import IncidentMemoryStore

logger = structlog.get_logger()
router = APIRouter(prefix="/api/memory", tags=["memory-advanced"])


class GenerateRunbookRequest(BaseModel):
    service: str = Field(..., min_length=1)
    root_cause_category: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


async def _build_store(config: IncidentMemoryConfig) -> IncidentMemoryStore:
    store = IncidentMemoryStore(database_url=config.database_url, config=config)
    await store.connect()
    return store


@router.get("/correlations")
async def get_service_correlations(
    lookback_days: Annotated[int, Query(ge=1, le=365)] = 90,
    min_coincidents: Annotated[int, Query(ge=1, le=50)] = 2,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    """Find services that frequently fail together."""
    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)
    store = await _build_store(config)

    try:
        engine = ServiceCorrelationEngine(store=store, config=config)
        # Rebuild correlation data from incident history
        await engine.rebuild()
        # Return all correlations via a generic query
        pool = await store._ensure_pool()
        rows = await pool.fetch(
            "SELECT * FROM service_correlations ORDER BY co_occurrence_count DESC LIMIT $1",
            limit,
        )
        correlations = [dict(r) for r in rows]
        return {
            "lookback_days": lookback_days,
            "min_coincidents": min_coincidents,
            "count": len(correlations),
            "correlations": correlations,
        }
    finally:
        await store.disconnect()


@router.post("/runbooks/generate")
async def generate_runbook(request: GenerateRunbookRequest):
    """Generate a runbook from historical incidents for a service/root-cause pair."""
    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)
    store = await _build_store(config)

    try:
        generator = AutoRunbookGenerator(settings=settings, store=store, config=config)
        count = await generator.rebuild()
        runbooks = await generator.list_runbooks(limit=request.limit)
        # Filter by requested service/root_cause if provided
        filtered = [
            r
            for r in runbooks
            if request.service in (r.service or "")
            and request.root_cause_category in (r.root_cause_category or "")
        ]
        return {
            "total_generated": count,
            "matching": len(filtered),
            "runbooks": [r.model_dump() for r in filtered],
        }
    finally:
        await store.disconnect()


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
        return report
    except Exception as exc:
        logger.error("memory_health_check_failed", error=str(exc))
        raise HTTPException(
            status_code=500, detail="Memory health check failed"
        ) from exc


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
    store = await _build_store(config)
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
