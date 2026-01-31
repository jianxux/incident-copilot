"""Runbook API endpoints."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Query

from ..runbooks import RunbookLinker
from ..runbooks.models import RunbookMatch

logger = structlog.get_logger()
router = APIRouter(prefix="/api/runbooks", tags=["runbooks"])


@router.get("", response_model=list[RunbookMatch])
async def search_runbooks(
    query: Annotated[str, Query(description="Search query for runbooks")],
    service: Annotated[str | None, Query(description="Filter by service name")] = None,
    limit: Annotated[int, Query(ge=1, le=20, description="Maximum results")] = 5,
) -> list[RunbookMatch]:
    """
    Search for runbooks matching a query.

    Returns the most relevant runbooks sorted by relevance score.

    Example:
        GET /api/runbooks?query=high+cpu+usage&service=payments-api
    """
    linker = RunbookLinker()

    matches = linker.find_relevant_runbooks(
        query=query,
        service_name=service,
        top_k=limit,
        min_score=0.05,
    )

    logger.info(
        "runbook_search",
        query=query,
        service=service,
        results=len(matches),
    )

    return matches


@router.get("/stats")
async def runbook_stats():
    """Get runbook index statistics."""
    from ..runbooks.indexer import RunbookIndexer

    indexer = RunbookIndexer()
    index = indexer.load_index()

    if not index:
        return {
            "indexed": False,
            "message": "No runbook index found. Run 'python -m src.runbooks.indexer --reindex'",
        }

    # Group by source
    by_source = {}
    for rb in index.runbooks:
        key = f"{rb.source_type.value}:{rb.source_name}"
        by_source[key] = by_source.get(key, 0) + 1

    return {
        "indexed": True,
        "built_at": index.built_at.isoformat(),
        "total_runbooks": len(index.runbooks),
        "vocabulary_size": len(index.vocabulary),
        "sources": by_source,
    }
