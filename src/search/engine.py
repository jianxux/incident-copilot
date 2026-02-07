"""Search engine with in-memory and optional Elasticsearch backends."""

import asyncio
import math
import re
import time
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Protocol

from .models import (
    FacetValue,
    IndexedDocument,
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


class SearchBackend(ABC):
    """Abstract search backend interface."""

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResult:
        """Execute a search query."""
        ...

    @abstractmethod
    async def index(self, doc: IndexedDocument) -> None:
        """Index a document."""
        ...

    @abstractmethod
    async def delete(self, doc_id: str) -> bool:
        """Delete a document by ID."""
        ...

    @abstractmethod
    async def suggest(self, prefix: str, limit: int = 10) -> list[SearchSuggestion]:
        """Get autocomplete suggestions."""
        ...

    @abstractmethod
    async def get_facets(self, filters: SearchFilter | None = None) -> SearchFacets:
        """Get facet counts."""
        ...


class InMemorySearchBackend(SearchBackend):
    """In-memory search backend for development and testing."""

    def __init__(self):
        self._documents: dict[str, IndexedDocument] = {}
        self._inverted_index: dict[str, set[str]] = defaultdict(set)
        self._title_index: dict[str, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into searchable terms."""
        text = text.lower()
        text = re.sub(r"[^\w\s-]", " ", text)
        tokens = text.split()
        return [t for t in tokens if len(t) >= 2]

    def _build_ngrams(self, text: str, n: int = 3) -> set[str]:
        """Build character n-grams for fuzzy matching."""
        text = text.lower()
        return {text[i : i + n] for i in range(len(text) - n + 1)}

    async def index(self, doc: IndexedDocument) -> None:
        """Index a document."""
        async with self._lock:
            # Remove old index entries if updating
            if doc.id in self._documents:
                await self._remove_from_index(doc.id)

            self._documents[doc.id] = doc

            # Index content
            searchable = doc.to_searchable_text()
            for token in self._tokenize(searchable):
                self._inverted_index[token].add(doc.id)

            # Index title separately for boosting
            for token in self._tokenize(doc.title):
                self._title_index[token].add(doc.id)

    async def _remove_from_index(self, doc_id: str) -> None:
        """Remove document from inverted index."""
        for token_docs in self._inverted_index.values():
            token_docs.discard(doc_id)
        for token_docs in self._title_index.values():
            token_docs.discard(doc_id)

    async def delete(self, doc_id: str) -> bool:
        """Delete a document."""
        async with self._lock:
            if doc_id not in self._documents:
                return False
            await self._remove_from_index(doc_id)
            del self._documents[doc_id]
            return True

    def _score_document(
        self, doc: IndexedDocument, query_tokens: list[str], now: datetime
    ) -> float:
        """Calculate relevance score for a document."""
        if not query_tokens:
            return 1.0

        score = 0.0
        doc_text = doc.to_searchable_text()
        title_lower = doc.title.lower()

        for token in query_tokens:
            # Exact match in title (highest boost)
            if token in title_lower:
                score += 10.0
            # Partial match in title
            elif any(token in word for word in title_lower.split()):
                score += 5.0
            # Match in content
            if token in doc_text:
                score += 2.0

        # Recency boost: docs from last 7 days get up to 2x boost
        if doc.created_at:
            age_days = (now - doc.created_at).days
            if age_days < 7:
                recency_boost = 1 + (7 - age_days) / 7
                score *= recency_boost

        # Severity boost for incidents
        if doc.doc_type == SearchableType.INCIDENT and doc.severity:
            severity_boosts = {"critical": 1.5, "high": 1.3, "medium": 1.1, "low": 1.0}
            score *= severity_boosts.get(doc.severity.lower(), 1.0)

        return score

    def _matches_filter(self, doc: IndexedDocument, filters: SearchFilter) -> bool:
        """Check if document matches all filters."""
        if filters.statuses and doc.status not in filters.statuses:
            return False
        if filters.severities and doc.severity not in filters.severities:
            return False
        if filters.services and doc.service not in filters.services:
            return False
        if filters.doc_types and doc.doc_type not in filters.doc_types:
            return False
        if filters.tags and not any(t in doc.tags for t in filters.tags):
            return False
        if filters.authors and doc.author_id not in filters.authors:
            return False
        if filters.date_from and doc.created_at and doc.created_at < filters.date_from:
            return False
        if filters.date_to and doc.created_at and doc.created_at > filters.date_to:
            return False
        return True

    def _highlight_text(
        self, text: str, query_tokens: list[str], max_len: int = 200
    ) -> str:
        """Create highlighted snippet from text."""
        if not query_tokens or not text:
            return text[:max_len] + "..." if len(text) > max_len else text

        text_lower = text.lower()
        best_pos = 0
        best_score = 0

        # Find best position to start snippet
        for i, token in enumerate(query_tokens):
            pos = text_lower.find(token)
            if pos != -1:
                score = len(query_tokens) - i
                if score > best_score:
                    best_score = score
                    best_pos = max(0, pos - 50)

        # Extract snippet
        snippet = text[best_pos : best_pos + max_len]
        if best_pos > 0:
            snippet = "..." + snippet
        if best_pos + max_len < len(text):
            snippet = snippet + "..."

        # Add highlights (simple markdown bold)
        for token in query_tokens:
            pattern = re.compile(re.escape(token), re.IGNORECASE)
            snippet = pattern.sub(f"**{token}**", snippet)

        return snippet

    async def search(self, query: SearchQuery) -> SearchResult:
        """Execute search query."""
        start_time = time.perf_counter()
        now = datetime.utcnow()

        query_tokens = self._tokenize(query.query)

        # Find candidate documents
        if query_tokens:
            candidate_ids: set[str] = set()
            for token in query_tokens:
                # Exact token match
                candidate_ids.update(self._inverted_index.get(token, set()))
                # Prefix match
                for indexed_token, doc_ids in self._inverted_index.items():
                    if indexed_token.startswith(token):
                        candidate_ids.update(doc_ids)
        else:
            candidate_ids = set(self._documents.keys())

        # Filter and score
        scored_docs: list[tuple[IndexedDocument, float]] = []
        facet_counts: dict[str, Counter] = {
            "statuses": Counter(),
            "severities": Counter(),
            "services": Counter(),
            "tags": Counter(),
            "doc_types": Counter(),
        }

        for doc_id in candidate_ids:
            doc = self._documents.get(doc_id)
            if not doc or not self._matches_filter(doc, query.filters):
                continue

            score = self._score_document(doc, query_tokens, now)
            scored_docs.append((doc, score))

            # Collect facets
            if doc.status:
                facet_counts["statuses"][doc.status] += 1
            if doc.severity:
                facet_counts["severities"][doc.severity] += 1
            if doc.service:
                facet_counts["services"][doc.service] += 1
            facet_counts["doc_types"][doc.doc_type.value] += 1
            for tag in doc.tags:
                facet_counts["tags"][tag] += 1

        # Sort results
        if query.sort_by == SortField.RELEVANCE:
            scored_docs.sort(
                key=lambda x: x[1], reverse=query.sort_order == SortOrder.DESC
            )
        elif query.sort_by == SortField.CREATED_AT:
            scored_docs.sort(
                key=lambda x: x[0].created_at or datetime.min,
                reverse=query.sort_order == SortOrder.DESC,
            )
        elif query.sort_by == SortField.UPDATED_AT:
            scored_docs.sort(
                key=lambda x: x[0].updated_at or datetime.min,
                reverse=query.sort_order == SortOrder.DESC,
            )
        elif query.sort_by == SortField.SEVERITY:
            severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            scored_docs.sort(
                key=lambda x: severity_order.get((x[0].severity or "").lower(), 0),
                reverse=query.sort_order == SortOrder.DESC,
            )
        elif query.sort_by == SortField.TITLE:
            scored_docs.sort(
                key=lambda x: x[0].title.lower(),
                reverse=query.sort_order == SortOrder.DESC,
            )

        # Paginate
        total_hits = len(scored_docs)
        total_pages = math.ceil(total_hits / query.page_size) if total_hits > 0 else 0
        start = query.offset
        end = start + query.page_size
        page_docs = scored_docs[start:end]

        # Build hits
        hits = []
        for doc, score in page_docs:
            highlights = {}
            snippet = ""
            if query.highlight and query_tokens:
                snippet = self._highlight_text(doc.content, query_tokens)
                highlights["title"] = [
                    self._highlight_text(doc.title, query_tokens, 100)
                ]
                highlights["content"] = [snippet]

            hits.append(
                SearchHit(
                    id=doc.id,
                    doc_type=doc.doc_type,
                    title=doc.title,
                    snippet=snippet or doc.content[:200],
                    score=score,
                    highlights=highlights,
                    metadata=doc.metadata,
                    created_at=doc.created_at,
                    updated_at=doc.updated_at,
                )
            )

        # Build facets
        def make_facet_values(
            counter: Counter, selected: list[str] | None
        ) -> list[FacetValue]:
            return [
                FacetValue(value=v, count=c, selected=v in (selected or []))
                for v, c in counter.most_common(20)
            ]

        facets = SearchFacets(
            statuses=make_facet_values(
                facet_counts["statuses"], query.filters.statuses
            ),
            severities=make_facet_values(
                facet_counts["severities"], query.filters.severities
            ),
            services=make_facet_values(
                facet_counts["services"], query.filters.services
            ),
            tags=make_facet_values(facet_counts["tags"], query.filters.tags),
            doc_types=make_facet_values(
                facet_counts["doc_types"],
                (
                    [t.value for t in query.filters.doc_types]
                    if query.filters.doc_types
                    else None
                ),
            ),
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return SearchResult(
            query=query.query,
            total_hits=total_hits,
            page=query.page,
            page_size=query.page_size,
            total_pages=total_pages,
            hits=hits,
            facets=facets,
            took_ms=elapsed_ms,
        )

    async def suggest(self, prefix: str, limit: int = 10) -> list[SearchSuggestion]:
        """Get autocomplete suggestions based on indexed titles."""
        if not prefix or len(prefix) < 2:
            return []

        prefix_lower = prefix.lower()
        suggestions: list[tuple[str, float, SearchableType | None]] = []

        for doc in self._documents.values():
            title_lower = doc.title.lower()
            if prefix_lower in title_lower:
                # Score based on position (earlier = better)
                pos = title_lower.find(prefix_lower)
                score = 1.0 / (1 + pos)
                suggestions.append((doc.title, score, doc.doc_type))

        # Sort by score and dedupe
        suggestions.sort(key=lambda x: x[1], reverse=True)
        seen: set[str] = set()
        results: list[SearchSuggestion] = []

        for title, score, doc_type in suggestions:
            if title not in seen:
                seen.add(title)
                highlight = re.sub(
                    re.escape(prefix), f"**{prefix}**", title, flags=re.IGNORECASE
                )
                results.append(
                    SearchSuggestion(
                        text=title,
                        doc_type=doc_type,
                        score=score,
                        highlight=highlight,
                    )
                )
                if len(results) >= limit:
                    break

        return results

    async def get_facets(self, filters: SearchFilter | None = None) -> SearchFacets:
        """Get facet counts, optionally filtered."""
        filters = filters or SearchFilter()
        facet_counts: dict[str, Counter] = {
            "statuses": Counter(),
            "severities": Counter(),
            "services": Counter(),
            "tags": Counter(),
            "doc_types": Counter(),
        }

        for doc in self._documents.values():
            if not self._matches_filter(doc, filters):
                continue
            if doc.status:
                facet_counts["statuses"][doc.status] += 1
            if doc.severity:
                facet_counts["severities"][doc.severity] += 1
            if doc.service:
                facet_counts["services"][doc.service] += 1
            facet_counts["doc_types"][doc.doc_type.value] += 1
            for tag in doc.tags:
                facet_counts["tags"][tag] += 1

        return SearchFacets(
            statuses=[
                FacetValue(value=v, count=c)
                for v, c in facet_counts["statuses"].most_common(20)
            ],
            severities=[
                FacetValue(value=v, count=c)
                for v, c in facet_counts["severities"].most_common(20)
            ],
            services=[
                FacetValue(value=v, count=c)
                for v, c in facet_counts["services"].most_common(20)
            ],
            tags=[
                FacetValue(value=v, count=c)
                for v, c in facet_counts["tags"].most_common(20)
            ],
            doc_types=[
                FacetValue(value=v, count=c)
                for v, c in facet_counts["doc_types"].most_common(20)
            ],
        )


class ElasticsearchBackend(SearchBackend):
    """Elasticsearch backend for production use."""

    def __init__(self, hosts: list[str], index_prefix: str = "incident-copilot"):
        self._hosts = hosts
        self._index_prefix = index_prefix
        self._client = None  # Lazy init

    async def _get_client(self):
        """Get or create Elasticsearch client."""
        if self._client is None:
            try:
                from elasticsearch import AsyncElasticsearch

                self._client = AsyncElasticsearch(hosts=self._hosts)
            except ImportError:
                raise RuntimeError(
                    "elasticsearch package not installed. "
                    "Install with: pip install elasticsearch[async]"
                )
        return self._client

    async def search(self, query: SearchQuery) -> SearchResult:
        """Execute search using Elasticsearch."""
        client = await self._get_client()

        # Build ES query
        must_clauses = []
        filter_clauses = []

        if query.query:
            must_clauses.append(
                {
                    "multi_match": {
                        "query": query.query,
                        "fields": ["title^3", "content", "tags^2", "service"],
                        "type": "best_fields",
                        "fuzziness": "AUTO",
                    }
                }
            )

        # Apply filters
        if query.filters.statuses:
            filter_clauses.append({"terms": {"status": query.filters.statuses}})
        if query.filters.severities:
            filter_clauses.append({"terms": {"severity": query.filters.severities}})
        if query.filters.services:
            filter_clauses.append({"terms": {"service": query.filters.services}})
        if query.filters.tags:
            filter_clauses.append({"terms": {"tags": query.filters.tags}})
        if query.filters.doc_types:
            filter_clauses.append(
                {"terms": {"doc_type": [t.value for t in query.filters.doc_types]}}
            )
        if query.filters.date_from or query.filters.date_to:
            range_filter = {"created_at": {}}
            if query.filters.date_from:
                range_filter["created_at"]["gte"] = query.filters.date_from.isoformat()
            if query.filters.date_to:
                range_filter["created_at"]["lte"] = query.filters.date_to.isoformat()
            filter_clauses.append({"range": range_filter})

        es_query = {
            "bool": {
                "must": must_clauses or [{"match_all": {}}],
                "filter": filter_clauses,
            }
        }

        # Build sort
        sort_mapping = {
            SortField.RELEVANCE: "_score",
            SortField.CREATED_AT: "created_at",
            SortField.UPDATED_AT: "updated_at",
            SortField.TITLE: "title.keyword",
        }
        sort_field = sort_mapping.get(query.sort_by, "_score")
        sort = [{sort_field: {"order": query.sort_order.value}}]

        # Recency boost via function_score
        body = {
            "query": {
                "function_score": {
                    "query": es_query,
                    "functions": [
                        {
                            "gauss": {
                                "created_at": {
                                    "origin": "now",
                                    "scale": "7d",
                                    "decay": 0.5,
                                }
                            }
                        }
                    ],
                    "boost_mode": "multiply",
                }
            },
            "sort": sort,
            "from": query.offset,
            "size": query.page_size,
            "aggs": {
                "statuses": {"terms": {"field": "status", "size": 20}},
                "severities": {"terms": {"field": "severity", "size": 20}},
                "services": {"terms": {"field": "service", "size": 20}},
                "tags": {"terms": {"field": "tags", "size": 20}},
                "doc_types": {"terms": {"field": "doc_type", "size": 10}},
            },
        }

        if query.highlight:
            body["highlight"] = {
                "fields": {
                    "title": {},
                    "content": {"fragment_size": 200, "number_of_fragments": 3},
                }
            }

        response = await client.search(index=f"{self._index_prefix}-*", body=body)

        # Parse response
        hits = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            highlights = hit.get("highlight", {})
            hits.append(
                SearchHit(
                    id=source["id"],
                    doc_type=SearchableType(source["doc_type"]),
                    title=source["title"],
                    snippet=highlights.get(
                        "content", [source.get("content", "")[:200]]
                    )[0],
                    score=hit["_score"] or 0.0,
                    highlights=highlights,
                    metadata=source.get("metadata", {}),
                    created_at=(
                        datetime.fromisoformat(source["created_at"])
                        if source.get("created_at")
                        else None
                    ),
                    updated_at=(
                        datetime.fromisoformat(source["updated_at"])
                        if source.get("updated_at")
                        else None
                    ),
                )
            )

        total_hits = response["hits"]["total"]["value"]
        total_pages = math.ceil(total_hits / query.page_size)

        # Parse aggregations
        aggs = response.get("aggregations", {})
        facets = SearchFacets(
            statuses=[
                FacetValue(value=b["key"], count=b["doc_count"])
                for b in aggs.get("statuses", {}).get("buckets", [])
            ],
            severities=[
                FacetValue(value=b["key"], count=b["doc_count"])
                for b in aggs.get("severities", {}).get("buckets", [])
            ],
            services=[
                FacetValue(value=b["key"], count=b["doc_count"])
                for b in aggs.get("services", {}).get("buckets", [])
            ],
            tags=[
                FacetValue(value=b["key"], count=b["doc_count"])
                for b in aggs.get("tags", {}).get("buckets", [])
            ],
            doc_types=[
                FacetValue(value=b["key"], count=b["doc_count"])
                for b in aggs.get("doc_types", {}).get("buckets", [])
            ],
        )

        return SearchResult(
            query=query.query,
            total_hits=total_hits,
            page=query.page,
            page_size=query.page_size,
            total_pages=total_pages,
            hits=hits,
            facets=facets,
            took_ms=response["took"],
        )

    async def index(self, doc: IndexedDocument) -> None:
        """Index a document in Elasticsearch."""
        client = await self._get_client()
        index_name = f"{self._index_prefix}-{doc.doc_type.value}"
        await client.index(
            index=index_name,
            id=doc.id,
            body=doc.model_dump(mode="json"),
            refresh=True,
        )

    async def delete(self, doc_id: str) -> bool:
        """Delete a document from Elasticsearch."""
        client = await self._get_client()
        try:
            await client.delete_by_query(
                index=f"{self._index_prefix}-*",
                body={"query": {"term": {"id": doc_id}}},
                refresh=True,
            )
            return True
        except Exception:
            return False

    async def suggest(self, prefix: str, limit: int = 10) -> list[SearchSuggestion]:
        """Get autocomplete suggestions from Elasticsearch."""
        client = await self._get_client()
        response = await client.search(
            index=f"{self._index_prefix}-*",
            body={
                "query": {
                    "multi_match": {
                        "query": prefix,
                        "fields": ["title^2", "title.autocomplete"],
                        "type": "phrase_prefix",
                    }
                },
                "size": limit,
                "_source": ["title", "doc_type"],
                "highlight": {"fields": {"title": {}}},
            },
        )

        suggestions = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            highlights = hit.get("highlight", {})
            suggestions.append(
                SearchSuggestion(
                    text=source["title"],
                    doc_type=(
                        SearchableType(source["doc_type"])
                        if source.get("doc_type")
                        else None
                    ),
                    score=hit["_score"] or 0.0,
                    highlight=highlights.get("title", [source["title"]])[0],
                )
            )
        return suggestions

    async def get_facets(self, filters: SearchFilter | None = None) -> SearchFacets:
        """Get facet counts from Elasticsearch."""
        query = SearchQuery(filters=filters or SearchFilter(), page_size=0)
        result = await self.search(query)
        return result.facets


class SearchEngine:
    """Main search engine facade."""

    def __init__(self, backend: SearchBackend | None = None):
        self._backend = backend or InMemorySearchBackend()
        self._query_log: list[tuple[datetime, str, int]] = (
            []
        )  # (time, query, result_count)

    @property
    def backend(self) -> SearchBackend:
        return self._backend

    async def search(self, query: SearchQuery) -> SearchResult:
        """Execute search and log for analytics."""
        result = await self._backend.search(query)
        self._query_log.append((datetime.utcnow(), query.query, result.total_hits))
        # Keep only last 10000 queries
        if len(self._query_log) > 10000:
            self._query_log = self._query_log[-10000:]
        return result

    async def index(self, doc: IndexedDocument) -> None:
        """Index a document."""
        await self._backend.index(doc)

    async def delete(self, doc_id: str) -> bool:
        """Delete a document."""
        return await self._backend.delete(doc_id)

    async def suggest(self, prefix: str, limit: int = 10) -> list[SearchSuggestion]:
        """Get search suggestions."""
        return await self._backend.suggest(prefix, limit)

    async def get_facets(self, filters: SearchFilter | None = None) -> SearchFacets:
        """Get facet counts."""
        return await self._backend.get_facets(filters)

    def get_analytics(self, hours: int = 24) -> dict:
        """Get search analytics for the specified time period."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        recent = [(t, q, c) for t, q, c in self._query_log if t >= cutoff]

        if not recent:
            return {
                "popular_queries": [],
                "zero_result_queries": [],
                "avg_results_per_query": 0.0,
                "total_searches": 0,
            }

        query_counts: Counter = Counter()
        zero_result_counts: Counter = Counter()
        total_results = 0

        for _, query, count in recent:
            if query:
                query_counts[query] += 1
                if count == 0:
                    zero_result_counts[query] += 1
            total_results += count

        return {
            "popular_queries": query_counts.most_common(20),
            "zero_result_queries": zero_result_counts.most_common(20),
            "avg_results_per_query": total_results / len(recent) if recent else 0.0,
            "total_searches": len(recent),
        }
