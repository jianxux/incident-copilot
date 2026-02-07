"""Tests for search engine and indexing module."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.search.models import (
    FacetValue,
    IndexedDocument,
    SavedSearch,
    SavedSearchCreate,
    SearchableType,
    SearchFacets,
    SearchFilter,
    SearchHit,
    SearchQuery,
    SearchResult,
    SearchSuggestion,
    SortField,
    SortOrder,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_document() -> IndexedDocument:
    """Create a sample indexed document."""
    return IndexedDocument(
        id="inc-123",
        doc_type=SearchableType.INCIDENT,
        title="Database connection timeout in production",
        content="Users experiencing slow response times due to database connection pool exhaustion",
        status="resolved",
        severity="P1",
        service="payments-api",
        tags=["database", "performance", "production"],
        author_id="user-1",
    )


@pytest.fixture
def sample_search_query() -> SearchQuery:
    """Create a sample search query."""
    return SearchQuery(
        query="database timeout",
        filters=SearchFilter(
            severities=["P1", "P2"],
            services=["payments-api"],
        ),
        sort_by=SortField.RELEVANCE,
        page=1,
        page_size=20,
    )


class TestSearchFilter:
    """Tests for SearchFilter model."""

    def test_empty_filter(self):
        """Test empty filter detection."""
        f = SearchFilter()
        assert f.is_empty()

    def test_non_empty_filter(self):
        """Test non-empty filter detection."""
        f = SearchFilter(severities=["P1"])
        assert not f.is_empty()

    def test_multiple_filters(self):
        """Test filter with multiple constraints."""
        f = SearchFilter(
            statuses=["open", "in_progress"],
            severities=["P1", "P2"],
            services=["api", "web"],
            tags=["critical"],
            date_from=datetime.utcnow() - timedelta(days=7),
        )
        assert not f.is_empty()
        assert len(f.statuses) == 2
        assert len(f.severities) == 2


class TestSearchQuery:
    """Tests for SearchQuery model."""

    def test_offset_calculation(self):
        """Test pagination offset calculation."""
        query = SearchQuery(query="test", page=3, page_size=20)
        assert query.offset == 40

    def test_default_values(self):
        """Test default query values."""
        query = SearchQuery()
        assert query.query == ""
        assert query.sort_by == SortField.RELEVANCE
        assert query.sort_order == SortOrder.DESC
        assert query.page == 1
        assert query.page_size == 20
        assert query.highlight

    def test_page_size_limits(self):
        """Test page size validation."""
        with pytest.raises(ValueError):
            SearchQuery(query="test", page_size=200)  # Exceeds max

    def test_page_minimum(self):
        """Test minimum page validation."""
        with pytest.raises(ValueError):
            SearchQuery(query="test", page=0)


class TestIndexedDocument:
    """Tests for IndexedDocument model."""

    def test_document_creation(self, sample_document):
        """Test creating an indexed document."""
        assert sample_document.id == "inc-123"
        assert sample_document.doc_type == SearchableType.INCIDENT
        assert len(sample_document.tags) == 3

    def test_searchable_text(self, sample_document):
        """Test generating searchable text."""
        text = sample_document.to_searchable_text()
        assert "database" in text.lower()
        assert "timeout" in text.lower()
        assert "payments-api" in text.lower()
        assert "production" in text.lower()

    def test_document_types(self):
        """Test all document types can be created."""
        for doc_type in SearchableType:
            doc = IndexedDocument(
                id=f"doc-{doc_type.value}",
                doc_type=doc_type,
                title=f"Test {doc_type.value}",
                content="Test content",
            )
            assert doc.doc_type == doc_type


class TestSearchHit:
    """Tests for SearchHit model."""

    def test_hit_creation(self):
        """Test creating a search hit."""
        hit = SearchHit(
            id="inc-123",
            doc_type=SearchableType.INCIDENT,
            title="Database timeout",
            snippet="...connection <em>timeout</em> in production...",
            score=0.95,
            highlights={"title": ["<em>Database</em> timeout"]},
        )
        assert hit.score == 0.95
        assert "title" in hit.highlights


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_empty_result(self):
        """Test creating an empty result."""
        result = SearchResult.empty(query="test", page=1, page_size=20)
        assert result.total_hits == 0
        assert result.total_pages == 0
        assert len(result.hits) == 0

    def test_result_with_hits(self):
        """Test creating a result with hits."""
        hits = [
            SearchHit(
                id=f"doc-{i}",
                doc_type=SearchableType.INCIDENT,
                title=f"Incident {i}",
                score=1.0 - (i * 0.1),
            )
            for i in range(5)
        ]
        result = SearchResult(
            query="test",
            total_hits=100,
            page=1,
            page_size=20,
            total_pages=5,
            hits=hits,
            took_ms=15.5,
        )
        assert result.total_hits == 100
        assert len(result.hits) == 5
        assert result.took_ms == 15.5


class TestSearchFacets:
    """Tests for SearchFacets model."""

    def test_facets_creation(self):
        """Test creating search facets."""
        facets = SearchFacets(
            statuses=[
                FacetValue(value="open", count=10),
                FacetValue(value="resolved", count=50),
            ],
            severities=[
                FacetValue(value="P1", count=5, selected=True),
                FacetValue(value="P2", count=15),
            ],
        )
        assert len(facets.statuses) == 2
        assert facets.severities[0].selected


class TestSavedSearch:
    """Tests for SavedSearch model."""

    def test_saved_search_creation(self):
        """Test creating a saved search."""
        query = SearchQuery(
            query="production incidents",
            filters=SearchFilter(severities=["P1", "P2"]),
        )
        saved = SavedSearch(
            user_id="user-123",
            name="Critical Production Issues",
            query=query,
            is_default=True,
        )
        assert saved.user_id == "user-123"
        assert saved.is_default
        assert saved.run_count == 0

    def test_saved_search_create_request(self):
        """Test SavedSearchCreate request model."""
        request = SavedSearchCreate(
            name="My Search",
            description="Find all database incidents",
            query=SearchQuery(query="database"),
            notify_on_new=True,
        )
        assert request.name == "My Search"
        assert request.notify_on_new


class TestSearchSuggestion:
    """Tests for SearchSuggestion model."""

    def test_suggestion_creation(self):
        """Test creating a search suggestion."""
        suggestion = SearchSuggestion(
            text="database connection",
            doc_type=SearchableType.INCIDENT,
            score=0.9,
            highlight="<em>database</em> connection",
        )
        assert suggestion.text == "database connection"
        assert suggestion.score == 0.9


class TestSearchAPI:
    """Tests for Search API endpoints."""

    def test_search_incidents(self, client):
        """Test POST /api/search endpoint."""
        response = client.post(
            "/api/search",
            json={
                "query": "database timeout",
                "filters": {"severities": ["P1", "P2"]},
                "page": 1,
                "page_size": 20,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "hits" in data
        assert "total_hits" in data

    def test_search_empty_query(self, client):
        """Test search with empty query returns all results."""
        response = client.post("/api/search", json={"query": ""})
        assert response.status_code == 200

    def test_search_with_date_filter(self, client):
        """Test search with date range filter."""
        response = client.post(
            "/api/search",
            json={
                "query": "incident",
                "filters": {
                    "date_from": (datetime.utcnow() - timedelta(days=30)).isoformat(),
                    "date_to": datetime.utcnow().isoformat(),
                },
            },
        )
        assert response.status_code == 200

    def test_search_suggestions(self, client):
        """Test GET /api/search/suggest endpoint."""
        response = client.get("/api/search/suggest?q=data")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_save_search(self, client):
        """Test POST /api/search/saved endpoint."""
        response = client.post(
            "/api/search/saved",
            json={
                "name": "My Saved Search",
                "query": {"query": "test incidents"},
            },
        )
        assert response.status_code in (200, 201)

    def test_list_saved_searches(self, client):
        """Test GET /api/search/saved endpoint."""
        response = client.get("/api/search/saved")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_reindex(self, client):
        """Test POST /api/search/reindex endpoint."""
        response = client.post("/api/search/reindex")
        assert response.status_code in (200, 202)

    def test_search_analytics(self, client):
        """Test GET /api/search/analytics endpoint."""
        response = client.get("/api/search/analytics")
        assert response.status_code == 200
