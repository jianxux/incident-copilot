"""FastAPI routes for search functionality."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from .engine import SearchEngine, InMemorySearchBackend
from .indexer import IndexingService, WebhookIndexer
from .models import (
    SavedSearch,
    SavedSearchCreate,
    SavedSearchUpdate,
    SearchableType,
    SearchFacets,
    SearchFilter,
    SearchQuery,
    SearchResult,
    SearchSuggestion,
    SortField,
    SortOrder,
)

# Router setup
router = APIRouter(prefix="/search", tags=["search"])

# Dependency injection - these would be configured at app startup
_engine: SearchEngine | None = None
_indexer: IndexingService | None = None
_webhook_indexer: WebhookIndexer | None = None
_saved_searches: dict[str, dict[UUID, SavedSearch]] = {}  # user_id -> {id -> SavedSearch}


def get_engine() -> SearchEngine:
    """Get the search engine instance."""
    global _engine
    if _engine is None:
        _engine = SearchEngine(InMemorySearchBackend())
    return _engine


def get_indexer() -> IndexingService:
    """Get the indexing service instance."""
    global _indexer
    if _indexer is None:
        _indexer = IndexingService(get_engine())
    return _indexer


def get_webhook_indexer() -> WebhookIndexer:
    """Get the webhook indexer instance."""
    global _webhook_indexer
    if _webhook_indexer is None:
        _webhook_indexer = WebhookIndexer(get_indexer())
    return _webhook_indexer


def configure_search(engine: SearchEngine) -> None:
    """Configure the search engine (call at app startup)."""
    global _engine, _indexer, _webhook_indexer
    _engine = engine
    _indexer = IndexingService(engine)
    _webhook_indexer = WebhookIndexer(_indexer)


# Request/Response models
class SearchRequest(BaseModel):
    """Search request body."""

    query: str = ""
    filters: SearchFilter = Field(default_factory=SearchFilter)
    sort_by: SortField = SortField.RELEVANCE
    sort_order: SortOrder = SortOrder.DESC
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    highlight: bool = True


class QuickSearchParams(BaseModel):
    """Query parameters for quick search."""

    q: str = ""
    status: list[str] | None = None
    severity: list[str] | None = None
    service: list[str] | None = None
    tag: list[str] | None = None
    type: list[SearchableType] | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None
    sort: SortField = SortField.RELEVANCE
    order: SortOrder = SortOrder.DESC
    page: int = 1
    size: int = 20


class WebhookEvent(BaseModel):
    """Webhook event payload."""

    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class IndexRequest(BaseModel):
    """Request to index a document."""

    doc_type: SearchableType
    data: dict[str, Any]


class ReindexRequest(BaseModel):
    """Request to trigger reindexing."""

    doc_types: list[SearchableType] | None = None
    batch_size: int = Field(default=100, ge=1, le=1000)


class AnalyticsResponse(BaseModel):
    """Search analytics response."""

    popular_queries: list[tuple[str, int]]
    zero_result_queries: list[tuple[str, int]]
    avg_results_per_query: float
    total_searches: int
    period_hours: int


# Routes
@router.post("", response_model=SearchResult)
async def search(
    request: SearchRequest,
    engine: Annotated[SearchEngine, Depends(get_engine)],
) -> SearchResult:
    """
    Execute a full-text search with filters.

    Supports:
    - Full-text search across incidents, runbooks, and postmortems
    - Faceted filtering by status, severity, service, tags, date range
    - Relevance scoring with recency boost
    - Pagination and sorting
    """
    query = SearchQuery(
        query=request.query,
        filters=request.filters,
        sort_by=request.sort_by,
        sort_order=request.sort_order,
        page=request.page,
        page_size=request.page_size,
        highlight=request.highlight,
    )
    return await engine.search(query)


@router.get("", response_model=SearchResult)
async def quick_search(
    q: str = "",
    status: Annotated[list[str] | None, Query()] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    service: Annotated[list[str] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    doc_type: Annotated[list[SearchableType] | None, Query(alias="type")] = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    sort: SortField = SortField.RELEVANCE,
    order: SortOrder = SortOrder.DESC,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    engine: SearchEngine = Depends(get_engine),
) -> SearchResult:
    """
    Quick search with query parameters.

    Example: /search?q=database&severity=critical&service=api&page=1
    """
    filters = SearchFilter(
        statuses=status,
        severities=severity,
        services=service,
        tags=tag,
        doc_types=doc_type,
        date_from=from_date,
        date_to=to_date,
    )
    query = SearchQuery(
        query=q,
        filters=filters,
        sort_by=sort,
        sort_order=order,
        page=page,
        page_size=size,
    )
    return await engine.search(query)


@router.get("/suggest", response_model=list[SearchSuggestion])
async def get_suggestions(
    q: str = Query(..., min_length=2, description="Search prefix"),
    limit: int = Query(default=10, ge=1, le=50),
    engine: SearchEngine = Depends(get_engine),
) -> list[SearchSuggestion]:
    """
    Get autocomplete suggestions for search.

    Returns matching document titles based on the prefix.
    """
    return await engine.suggest(q, limit)


@router.get("/facets", response_model=SearchFacets)
async def get_facets(
    status: Annotated[list[str] | None, Query()] = None,
    severity: Annotated[list[str] | None, Query()] = None,
    service: Annotated[list[str] | None, Query()] = None,
    doc_type: Annotated[list[SearchableType] | None, Query(alias="type")] = None,
    engine: SearchEngine = Depends(get_engine),
) -> SearchFacets:
    """
    Get available facet values and counts.

    Useful for building filter UIs without executing a full search.
    """
    filters = SearchFilter(
        statuses=status,
        severities=severity,
        services=service,
        doc_types=doc_type,
    )
    return await engine.get_facets(filters if not filters.is_empty() else None)


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    hours: int = Query(default=24, ge=1, le=720, description="Time period in hours"),
    engine: SearchEngine = Depends(get_engine),
) -> AnalyticsResponse:
    """
    Get search analytics for monitoring and optimization.

    Returns popular queries, zero-result queries, and search statistics.
    """
    analytics = engine.get_analytics(hours)
    return AnalyticsResponse(
        popular_queries=analytics["popular_queries"],
        zero_result_queries=analytics["zero_result_queries"],
        avg_results_per_query=analytics["avg_results_per_query"],
        total_searches=analytics["total_searches"],
        period_hours=hours,
    )


# Saved Searches
@router.post("/saved", response_model=SavedSearch, status_code=status.HTTP_201_CREATED)
async def create_saved_search(
    request: SavedSearchCreate,
    user_id: str = Query(..., description="User ID"),
) -> SavedSearch:
    """Create a new saved search for a user."""
    saved = SavedSearch(
        user_id=user_id,
        name=request.name,
        description=request.description,
        query=request.query,
        is_default=request.is_default,
        notify_on_new=request.notify_on_new,
    )

    if user_id not in _saved_searches:
        _saved_searches[user_id] = {}

    # If this is default, unset other defaults
    if saved.is_default:
        for existing in _saved_searches[user_id].values():
            existing.is_default = False

    _saved_searches[user_id][saved.id] = saved
    return saved


@router.get("/saved", response_model=list[SavedSearch])
async def list_saved_searches(
    user_id: str = Query(..., description="User ID"),
) -> list[SavedSearch]:
    """List all saved searches for a user."""
    user_searches = _saved_searches.get(user_id, {})
    return sorted(user_searches.values(), key=lambda s: s.created_at, reverse=True)


@router.get("/saved/{search_id}", response_model=SavedSearch)
async def get_saved_search(
    search_id: UUID,
    user_id: str = Query(..., description="User ID"),
) -> SavedSearch:
    """Get a specific saved search."""
    user_searches = _saved_searches.get(user_id, {})
    if search_id not in user_searches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved search not found",
        )
    return user_searches[search_id]


@router.put("/saved/{search_id}", response_model=SavedSearch)
async def update_saved_search(
    search_id: UUID,
    request: SavedSearchUpdate,
    user_id: str = Query(..., description="User ID"),
) -> SavedSearch:
    """Update a saved search."""
    user_searches = _saved_searches.get(user_id, {})
    if search_id not in user_searches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved search not found",
        )

    saved = user_searches[search_id]
    update_data = request.model_dump(exclude_unset=True)

    # Handle default flag
    if update_data.get("is_default"):
        for existing in user_searches.values():
            existing.is_default = False

    for field, value in update_data.items():
        setattr(saved, field, value)

    saved.updated_at = datetime.utcnow()
    return saved


@router.delete("/saved/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_search(
    search_id: UUID,
    user_id: str = Query(..., description="User ID"),
) -> None:
    """Delete a saved search."""
    user_searches = _saved_searches.get(user_id, {})
    if search_id not in user_searches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved search not found",
        )
    del user_searches[search_id]


@router.post("/saved/{search_id}/run", response_model=SearchResult)
async def run_saved_search(
    search_id: UUID,
    user_id: str = Query(..., description="User ID"),
    page: int = Query(default=1, ge=1),
    engine: SearchEngine = Depends(get_engine),
) -> SearchResult:
    """Execute a saved search."""
    user_searches = _saved_searches.get(user_id, {})
    if search_id not in user_searches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved search not found",
        )

    saved = user_searches[search_id]
    query = saved.query.model_copy()
    query.page = page

    result = await engine.search(query)

    # Update run stats
    saved.last_run_at = datetime.utcnow()
    saved.run_count += 1

    return result


# Indexing endpoints
@router.post("/index", status_code=status.HTTP_201_CREATED)
async def index_document(
    request: IndexRequest,
    indexer: IndexingService = Depends(get_indexer),
) -> dict[str, str]:
    """Index a single document."""
    doc = await indexer.index_document(request.doc_type, request.data)
    return {"id": doc.id, "doc_type": doc.doc_type.value, "status": "indexed"}


@router.delete("/index/{doc_id}")
async def delete_from_index(
    doc_id: str,
    indexer: IndexingService = Depends(get_indexer),
) -> dict[str, Any]:
    """Delete a document from the index."""
    deleted = await indexer.delete_document(doc_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in index",
        )
    return {"id": doc_id, "status": "deleted"}


@router.post("/reindex")
async def trigger_reindex(
    request: ReindexRequest,
    indexer: IndexingService = Depends(get_indexer),
) -> dict[str, Any]:
    """Trigger reindexing of documents."""
    if request.doc_types:
        results = {}
        for doc_type in request.doc_types:
            results[doc_type.value] = await indexer.reindex_type(doc_type, request.batch_size)
        return {"status": "completed", "results": results}
    else:
        results = await indexer.reindex_all(request.batch_size)
        return {"status": "completed", "results": results}


@router.get("/index/stats")
async def get_index_stats(
    indexer: IndexingService = Depends(get_indexer),
) -> dict[str, Any]:
    """Get indexing statistics."""
    return indexer.get_stats()


# Webhook endpoint
@router.post("/webhook")
async def handle_webhook(
    event: WebhookEvent,
    webhook_indexer: WebhookIndexer = Depends(get_webhook_indexer),
) -> dict[str, Any]:
    """
    Handle webhook events to keep the index in sync.

    Supported events:
    - incident.created, incident.updated, incident.deleted
    - runbook.created, runbook.updated, runbook.deleted
    - postmortem.created, postmortem.updated, postmortem.deleted
    """
    handled = await webhook_indexer.handle_event(event.event_type, event.payload)
    if not handled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown event type: {event.event_type}. "
            f"Supported: {webhook_indexer.get_supported_events()}",
        )
    return {"status": "processed", "event_type": event.event_type}


# Health check
@router.get("/health")
async def health_check(
    engine: SearchEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Health check for the search service."""
    try:
        # Quick search to verify functionality
        await engine.search(SearchQuery(query="", page_size=1))
        return {
            "status": "healthy",
            "backend": type(engine.backend).__name__,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }
