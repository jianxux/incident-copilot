"""Search models for incident-copilot."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SearchableType(str, Enum):
    """Types of searchable documents."""

    INCIDENT = "incident"
    RUNBOOK = "runbook"
    POSTMORTEM = "postmortem"


class SortField(str, Enum):
    """Fields available for sorting."""

    RELEVANCE = "relevance"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    SEVERITY = "severity"
    TITLE = "title"


class SortOrder(str, Enum):
    """Sort order options."""

    ASC = "asc"
    DESC = "desc"


class SearchFilter(BaseModel):
    """Faceted filter for search queries."""

    statuses: list[str] | None = Field(
        default=None, description="Filter by status values"
    )
    severities: list[str] | None = Field(
        default=None, description="Filter by severity levels"
    )
    services: list[str] | None = Field(
        default=None, description="Filter by service names"
    )
    tags: list[str] | None = Field(default=None, description="Filter by tags")
    doc_types: list[SearchableType] | None = Field(
        default=None, description="Filter by document type"
    )
    date_from: datetime | None = Field(default=None, description="Filter from date")
    date_to: datetime | None = Field(default=None, description="Filter to date")
    authors: list[str] | None = Field(default=None, description="Filter by author IDs")

    def is_empty(self) -> bool:
        """Check if filter has any constraints."""
        return all(getattr(self, f) is None for f in self.model_fields)


class SearchQuery(BaseModel):
    """Search query with filters and pagination."""

    query: str = Field(default="", description="Full-text search query")
    filters: SearchFilter = Field(default_factory=SearchFilter)
    sort_by: SortField = Field(default=SortField.RELEVANCE)
    sort_order: SortOrder = Field(default=SortOrder.DESC)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    highlight: bool = Field(default=True, description="Include highlighted snippets")

    @property
    def offset(self) -> int:
        """Calculate offset for pagination."""
        return (self.page - 1) * self.page_size


class SearchHit(BaseModel):
    """A single search result hit."""

    id: str
    doc_type: SearchableType
    title: str
    snippet: str = Field(default="", description="Text snippet with highlights")
    score: float = Field(default=0.0, description="Relevance score")
    highlights: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FacetValue(BaseModel):
    """A facet value with count."""

    value: str
    count: int
    selected: bool = False


class SearchFacets(BaseModel):
    """Aggregated facet counts from search results."""

    statuses: list[FacetValue] = Field(default_factory=list)
    severities: list[FacetValue] = Field(default_factory=list)
    services: list[FacetValue] = Field(default_factory=list)
    tags: list[FacetValue] = Field(default_factory=list)
    doc_types: list[FacetValue] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Complete search result with hits, facets, and pagination info."""

    query: str
    total_hits: int
    page: int
    page_size: int
    total_pages: int
    hits: list[SearchHit]
    facets: SearchFacets = Field(default_factory=SearchFacets)
    took_ms: float = Field(default=0.0, description="Search execution time in ms")

    @classmethod
    def empty(
        cls, query: str = "", page: int = 1, page_size: int = 20
    ) -> "SearchResult":
        """Create an empty result."""
        return cls(
            query=query,
            total_hits=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            hits=[],
        )


class SavedSearch(BaseModel):
    """A saved search query for a user."""

    id: UUID = Field(default_factory=uuid4)
    user_id: str
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="")
    query: SearchQuery
    is_default: bool = Field(default=False, description="Show on dashboard")
    notify_on_new: bool = Field(default=False, description="Notify when new results")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_run_at: datetime | None = None
    run_count: int = Field(default=0)


class SavedSearchCreate(BaseModel):
    """Request to create a saved search."""

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="")
    query: SearchQuery
    is_default: bool = False
    notify_on_new: bool = False


class SavedSearchUpdate(BaseModel):
    """Request to update a saved search."""

    name: str | None = None
    description: str | None = None
    query: SearchQuery | None = None
    is_default: bool | None = None
    notify_on_new: bool | None = None


class SearchSuggestion(BaseModel):
    """Autocomplete suggestion."""

    text: str
    doc_type: SearchableType | None = None
    score: float = 0.0
    highlight: str = ""


class SearchAnalytics(BaseModel):
    """Search analytics data."""

    popular_queries: list[tuple[str, int]] = Field(default_factory=list)
    zero_result_queries: list[tuple[str, int]] = Field(default_factory=list)
    avg_results_per_query: float = 0.0
    total_searches: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None


class IndexedDocument(BaseModel):
    """Document stored in the search index."""

    id: str
    doc_type: SearchableType
    title: str
    content: str
    status: str | None = None
    severity: str | None = None
    service: str | None = None
    tags: list[str] = Field(default_factory=list)
    author_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_searchable_text(self) -> str:
        """Combine all searchable fields into one text."""
        parts = [self.title, self.content]
        if self.service:
            parts.append(self.service)
        parts.extend(self.tags)
        return " ".join(parts).lower()
