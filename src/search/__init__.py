"""
Advanced Search Module for Incident Copilot.

Provides full-text search across incidents, runbooks, and postmortems with:
- Faceted filtering (status, severity, service, tags, date range)
- Relevance scoring with recency boost
- Saved search queries per user
- Search suggestions/autocomplete
- Search analytics (popular queries, zero-result queries)
- Support for in-memory and Elasticsearch backends

Usage:
    from search import SearchEngine, IndexingService, router

    # Create engine with in-memory backend (default)
    engine = SearchEngine()

    # Or with Elasticsearch
    from search.engine import ElasticsearchBackend
    es_backend = ElasticsearchBackend(hosts=["http://localhost:9200"])
    engine = SearchEngine(es_backend)

    # Create indexer
    indexer = IndexingService(engine)

    # Index documents
    await indexer.index_incident({
        "id": "inc-123",
        "title": "Database connection timeout",
        "description": "Users experiencing slow queries...",
        "severity": "high",
        "status": "resolved",
        "service": "api",
        "tags": ["database", "performance"],
    })

    # Search
    from search.models import SearchQuery, SearchFilter
    query = SearchQuery(
        query="database timeout",
        filters=SearchFilter(severities=["high", "critical"]),
    )
    results = await engine.search(query)

    # Add routes to FastAPI app
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
"""

from .models import (
    FacetValue,
    IndexedDocument,
    SavedSearch,
    SavedSearchCreate,
    SavedSearchUpdate,
    SearchableType,
    SearchAnalytics,
    SearchFacets,
    SearchFilter,
    SearchHit,
    SearchQuery,
    SearchResult,
    SearchSuggestion,
    SortField,
    SortOrder,
)
from .engine import (
    ElasticsearchBackend,
    InMemorySearchBackend,
    SearchBackend,
    SearchEngine,
)
from .indexer import (
    IncidentAdapter,
    IndexingService,
    InMemoryDocumentSource,
    PostmortemAdapter,
    RunbookAdapter,
    WebhookIndexer,
)
from .routes import configure_search, router

__all__ = [
    # Models
    "FacetValue",
    "IndexedDocument",
    "SavedSearch",
    "SavedSearchCreate",
    "SavedSearchUpdate",
    "SearchableType",
    "SearchAnalytics",
    "SearchFacets",
    "SearchFilter",
    "SearchHit",
    "SearchQuery",
    "SearchResult",
    "SearchSuggestion",
    "SortField",
    "SortOrder",
    # Engine
    "ElasticsearchBackend",
    "InMemorySearchBackend",
    "SearchBackend",
    "SearchEngine",
    # Indexer
    "IncidentAdapter",
    "IndexingService",
    "InMemoryDocumentSource",
    "PostmortemAdapter",
    "RunbookAdapter",
    "WebhookIndexer",
    # Routes
    "configure_search",
    "router",
]

__version__ = "1.0.0"
