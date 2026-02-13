"""Incident Memory stats endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

from ..config import get_settings
from ..memory import IncidentMemoryConfig, IncidentMemoryStore, get_feedback_store

logger = structlog.get_logger()
router = APIRouter(prefix="/api/memory", tags=["memory-stats"])


@router.get("/stats")
async def get_memory_stats():
    """Return coarse Incident Memory effectiveness metrics."""
    settings = get_settings()
    config = IncidentMemoryConfig.from_settings(settings)

    total_records = 0
    try:
        memory_store = IncidentMemoryStore(
            database_url=config.database_url,
            config=config,
        )
        total_records = await memory_store.count()
        await memory_store.disconnect()
    except Exception as exc:
        logger.warning("incident_memory_stats_store_unavailable", error=str(exc))

    feedback_store = get_feedback_store(config.feedback_database_path)
    breakdown = await feedback_store.feedback_breakdown()
    total_feedback = sum(breakdown.values())
    avg_similarity_score = 0.0
    if total_feedback > 0:
        avg_similarity_score = round(
            (
                (breakdown.get("helpful", 0) * 1.0)
                + (breakdown.get("partial", 0) * 0.5)
                + (breakdown.get("not_helpful", 0) * 0.0)
            )
            / total_feedback,
            4,
        )

    return {
        "total_records": total_records,
        "avg_similarity_scores": {
            "feedback_weighted_mean": avg_similarity_score,
        },
        "feedback_breakdown": breakdown,
        "recall_hit_rate": await feedback_store.recall_hit_rate(),
    }
