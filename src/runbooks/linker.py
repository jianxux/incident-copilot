"""
Runbook linker - matches incidents to relevant runbooks.

Uses TF-IDF-style scoring to find the most relevant runbooks
for a given incident based on alert text, service name, and tags.
"""

import math
import re
from collections import Counter

import structlog

from .indexer import RunbookIndexer
from .models import Runbook, RunbookMatch

logger = structlog.get_logger()


class RunbookLinker:
    """Links incidents to relevant runbooks using text similarity."""

    def __init__(self, indexer: RunbookIndexer | None = None):
        self.indexer = indexer or RunbookIndexer()
        self._index = None
        self._idf_cache: dict[str, float] = {}

    def _ensure_index_loaded(self) -> bool:
        """Ensure the runbook index is loaded."""
        if self._index is None:
            self._index = self.indexer.load_index()
            if self._index:
                self._compute_idf()
        return self._index is not None

    def _compute_idf(self) -> None:
        """Compute IDF (inverse document frequency) for all terms."""
        if not self._index:
            return

        n_docs = len(self._index.runbooks) + 1  # +1 to avoid division by zero

        for term, doc_freq in self._index.vocabulary.items():
            # IDF = log(N / df)
            self._idf_cache[term] = math.log(n_docs / (doc_freq + 1))

    def find_relevant_runbooks(
        self,
        query: str,
        service_name: str | None = None,
        tags: list[str] | None = None,
        top_k: int = 3,
        min_score: float = 0.1,
    ) -> list[RunbookMatch]:
        """
        Find runbooks relevant to an incident.

        Args:
            query: The alert text/title to match against.
            service_name: Optional service name for boosting matches.
            tags: Optional tags to boost matches.
            top_k: Maximum number of results to return.
            min_score: Minimum relevance score threshold.

        Returns:
            List of RunbookMatch objects, sorted by relevance.
        """
        if not self._ensure_index_loaded():
            logger.warning("runbook_index_not_available")
            return []

        # Tokenize query
        query_terms = self._tokenize(query)
        if service_name:
            query_terms.extend(self._tokenize(service_name))
        if tags:
            for tag in tags:
                query_terms.extend(self._tokenize(tag))

        if not query_terms:
            return []

        # Compute query term frequencies
        query_tf = Counter(query_terms)

        # Score each runbook
        scored_runbooks: list[tuple[float, Runbook, list[str]]] = []

        for runbook in self._index.runbooks:
            score, matched_terms = self._score_runbook(runbook, query_tf, service_name)
            if score >= min_score:
                scored_runbooks.append((score, runbook, matched_terms))

        # Sort by score descending
        scored_runbooks.sort(key=lambda x: x[0], reverse=True)

        # Convert to RunbookMatch objects
        matches = []
        for score, runbook, matched_terms in scored_runbooks[:top_k]:
            match = RunbookMatch(
                runbook_id=runbook.id,
                title=runbook.title,
                url=runbook.url,
                source_type=runbook.source_type,
                source_name=runbook.source_name,
                relevance_score=min(score, 1.0),  # Cap at 1.0
                matched_terms=matched_terms[:10],
                description=runbook.description,
            )
            matches.append(match)

        logger.info(
            "runbook_linking_complete",
            query_terms=len(query_terms),
            candidates=len(self._index.runbooks),
            matches=len(matches),
        )

        return matches

    def _score_runbook(
        self,
        runbook: Runbook,
        query_tf: Counter,
        service_name: str | None,
    ) -> tuple[float, list[str]]:
        """
        Score a runbook against a query using TF-IDF.

        Returns:
            Tuple of (score, matched_terms)
        """
        # Build runbook term frequencies from keywords
        doc_terms = set(runbook.keywords)
        doc_terms.update(self._tokenize(runbook.title))

        # Also add tags and services as high-value terms
        doc_terms.update(t.lower() for t in runbook.tags)
        doc_terms.update(s.lower() for s in runbook.services)

        # Calculate TF-IDF cosine similarity
        score = 0.0
        matched_terms = []

        for term, tf in query_tf.items():
            if term in doc_terms:
                # TF-IDF weight
                idf = self._idf_cache.get(term, 1.0)
                score += tf * idf
                matched_terms.append(term)

        # Normalize by query length
        if query_tf:
            score /= len(query_tf)

        # Boost if service matches
        if service_name:
            service_lower = service_name.lower()
            if service_lower in [s.lower() for s in runbook.services]:
                score *= 2.0  # Strong boost for service match
                matched_terms.append(f"service:{service_name}")
            elif service_lower in runbook.title.lower():
                score *= 1.5  # Moderate boost for title match
            elif service_lower in runbook.content.lower():
                score *= 1.2  # Light boost for content mention

        # Boost for tag matches
        if runbook.tags:
            for tag in runbook.tags:
                if tag.lower() in query_tf:
                    score *= 1.3

        return score, matched_terms

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into terms."""
        # Common stopwords
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "they",
            "them",
            "their",
            "we",
            "you",
            "your",
        }

        # Tokenize
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", text.lower())
        return [w for w in words if w not in stopwords]

    def search(self, query: str, top_k: int = 5) -> list[RunbookMatch]:
        """
        Simple search endpoint for API.

        Args:
            query: Search query string.
            top_k: Maximum results to return.

        Returns:
            List of matching runbooks.
        """
        return self.find_relevant_runbooks(query, top_k=top_k, min_score=0.05)


# Convenience function for direct usage
def link_runbooks_to_incident(
    alert_text: str,
    service_name: str | None = None,
    tags: list[str] | None = None,
    top_k: int = 3,
) -> list[RunbookMatch]:
    """
    Find relevant runbooks for an incident.

    This is a convenience function that creates a linker and searches.

    Args:
        alert_text: The incident alert text/title.
        service_name: The affected service name.
        tags: Any tags associated with the incident.
        top_k: Maximum number of runbooks to return.

    Returns:
        List of RunbookMatch objects sorted by relevance.

    Example:
        >>> matches = link_runbooks_to_incident(
        ...     alert_text="High CPU usage on payments-api",
        ...     service_name="payments-api",
        ... )
        >>> for m in matches:
        ...     print(f"{m.title} ({m.relevance_score:.2f}): {m.url}")
    """
    linker = RunbookLinker()
    return linker.find_relevant_runbooks(
        query=alert_text,
        service_name=service_name,
        tags=tags,
        top_k=top_k,
    )
