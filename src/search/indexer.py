"""Indexing service for incidents, runbooks, and postmortems."""

import asyncio
from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from .engine import SearchEngine
from .models import IndexedDocument, SearchableType


class DocumentSource(Protocol):
    """Protocol for document sources that can be indexed."""

    async def get_all(self) -> list[dict[str, Any]]:
        """Get all documents for full reindex."""
        ...

    async def get_by_id(self, doc_id: str) -> dict[str, Any] | None:
        """Get a single document by ID."""
        ...


class IncidentAdapter:
    """Adapter to convert incidents to indexable documents."""

    @staticmethod
    def to_indexed_doc(incident: dict[str, Any]) -> IndexedDocument:
        """Convert incident dict to IndexedDocument."""
        # Build searchable content from incident fields
        content_parts = []
        if incident.get("description"):
            content_parts.append(incident["description"])
        if incident.get("summary"):
            content_parts.append(incident["summary"])
        if incident.get("timeline"):
            for entry in incident["timeline"]:
                if isinstance(entry, dict):
                    content_parts.append(entry.get("description", ""))
                else:
                    content_parts.append(str(entry))
        if incident.get("impact"):
            content_parts.append(incident["impact"])

        return IndexedDocument(
            id=str(incident.get("id", "")),
            doc_type=SearchableType.INCIDENT,
            title=incident.get("title", "Untitled Incident"),
            content=" ".join(content_parts),
            status=incident.get("status"),
            severity=incident.get("severity"),
            service=incident.get("service") or incident.get("affected_service"),
            tags=incident.get("tags", []),
            author_id=incident.get("created_by") or incident.get("reporter_id"),
            metadata={
                "incident_id": incident.get("incident_id"),
                "slack_channel": incident.get("slack_channel"),
                "pagerduty_id": incident.get("pagerduty_id"),
                "jira_ticket": incident.get("jira_ticket"),
            },
            created_at=_parse_datetime(incident.get("created_at")),
            updated_at=_parse_datetime(incident.get("updated_at")),
        )


class RunbookAdapter:
    """Adapter to convert runbooks to indexable documents."""

    @staticmethod
    def to_indexed_doc(runbook: dict[str, Any]) -> IndexedDocument:
        """Convert runbook dict to IndexedDocument."""
        content_parts = []
        if runbook.get("description"):
            content_parts.append(runbook["description"])
        if runbook.get("steps"):
            for step in runbook["steps"]:
                if isinstance(step, dict):
                    content_parts.append(step.get("instruction", ""))
                    content_parts.append(step.get("command", ""))
                else:
                    content_parts.append(str(step))
        if runbook.get("prerequisites"):
            content_parts.extend(runbook["prerequisites"])
        if runbook.get("notes"):
            content_parts.append(runbook["notes"])

        return IndexedDocument(
            id=str(runbook.get("id", "")),
            doc_type=SearchableType.RUNBOOK,
            title=runbook.get("title") or runbook.get("name", "Untitled Runbook"),
            content=" ".join(content_parts),
            status=runbook.get("status", "active"),
            severity=runbook.get("severity_applicable"),
            service=runbook.get("service") or runbook.get("target_service"),
            tags=runbook.get("tags", []),
            author_id=runbook.get("author_id") or runbook.get("created_by"),
            metadata={
                "version": runbook.get("version"),
                "last_used": runbook.get("last_used"),
                "success_rate": runbook.get("success_rate"),
                "avg_execution_time": runbook.get("avg_execution_time"),
            },
            created_at=_parse_datetime(runbook.get("created_at")),
            updated_at=_parse_datetime(runbook.get("updated_at")),
        )


class PostmortemAdapter:
    """Adapter to convert postmortems to indexable documents."""

    @staticmethod
    def to_indexed_doc(postmortem: dict[str, Any]) -> IndexedDocument:
        """Convert postmortem dict to IndexedDocument."""
        content_parts = []
        if postmortem.get("summary"):
            content_parts.append(postmortem["summary"])
        if postmortem.get("root_cause"):
            content_parts.append(f"Root Cause: {postmortem['root_cause']}")
        if postmortem.get("timeline"):
            content_parts.append(postmortem["timeline"])
        if postmortem.get("lessons_learned"):
            for lesson in postmortem["lessons_learned"]:
                content_parts.append(str(lesson))
        if postmortem.get("action_items"):
            for item in postmortem["action_items"]:
                if isinstance(item, dict):
                    content_parts.append(item.get("description", ""))
                else:
                    content_parts.append(str(item))
        if postmortem.get("contributing_factors"):
            content_parts.extend(postmortem["contributing_factors"])

        return IndexedDocument(
            id=str(postmortem.get("id", "")),
            doc_type=SearchableType.POSTMORTEM,
            title=postmortem.get("title", "Untitled Postmortem"),
            content=" ".join(content_parts),
            status=postmortem.get("status", "published"),
            severity=postmortem.get("incident_severity"),
            service=postmortem.get("service") or postmortem.get("affected_service"),
            tags=postmortem.get("tags", []),
            author_id=postmortem.get("author_id") or postmortem.get("lead_author"),
            metadata={
                "incident_id": postmortem.get("incident_id"),
                "detection_time": postmortem.get("detection_time"),
                "resolution_time": postmortem.get("resolution_time"),
                "ttd_minutes": postmortem.get("ttd_minutes"),
                "ttr_minutes": postmortem.get("ttr_minutes"),
            },
            created_at=_parse_datetime(postmortem.get("created_at")),
            updated_at=_parse_datetime(postmortem.get("updated_at")),
        )


def _parse_datetime(value: Any) -> datetime:
    """Parse datetime from various formats."""
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try common formats
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return datetime.now(UTC)


class IndexingService:
    """Service for indexing documents from various sources."""

    def __init__(self, engine: SearchEngine):
        self._engine = engine
        self._adapters: dict[SearchableType, type] = {
            SearchableType.INCIDENT: IncidentAdapter,
            SearchableType.RUNBOOK: RunbookAdapter,
            SearchableType.POSTMORTEM: PostmortemAdapter,
        }
        self._sources: dict[SearchableType, DocumentSource] = {}
        self._indexing_lock = asyncio.Lock()
        self._last_index_time: dict[SearchableType, datetime] = {}
        self._index_stats: dict[str, int] = {
            "total_indexed": 0,
            "total_deleted": 0,
            "total_errors": 0,
        }

    def register_source(self, doc_type: SearchableType, source: DocumentSource) -> None:
        """Register a document source for a type."""
        self._sources[doc_type] = source

    async def index_document(
        self,
        doc_type: SearchableType,
        data: dict[str, Any],
    ) -> IndexedDocument:
        """Index a single document."""
        adapter = self._adapters[doc_type]
        indexed_doc = adapter.to_indexed_doc(data)
        await self._engine.index(indexed_doc)
        self._index_stats["total_indexed"] += 1
        return indexed_doc

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document from the index."""
        result = await self._engine.delete(doc_id)
        if result:
            self._index_stats["total_deleted"] += 1
        return result

    async def reindex_type(
        self,
        doc_type: SearchableType,
        batch_size: int = 100,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, int]:
        """Reindex all documents of a specific type."""
        if doc_type not in self._sources:
            raise ValueError(f"No source registered for {doc_type}")

        source = self._sources[doc_type]
        adapter = self._adapters[doc_type]

        async with self._indexing_lock:
            all_docs = await source.get_all()
            total = len(all_docs)
            indexed = 0
            errors = 0

            for i in range(0, total, batch_size):
                batch = all_docs[i : i + batch_size]
                for doc_data in batch:
                    try:
                        indexed_doc = adapter.to_indexed_doc(doc_data)
                        await self._engine.index(indexed_doc)
                        indexed += 1
                    except Exception:
                        errors += 1
                        self._index_stats["total_errors"] += 1

                if progress_callback:
                    progress_callback(indexed, total)

            self._last_index_time[doc_type] = datetime.now(UTC)
            self._index_stats["total_indexed"] += indexed

            return {
                "total": total,
                "indexed": indexed,
                "errors": errors,
                "doc_type": doc_type.value,
            }

    async def reindex_all(
        self,
        batch_size: int = 100,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Reindex all registered document types."""
        results = {}
        for doc_type in self._sources:
            results[doc_type.value] = await self.reindex_type(
                doc_type, batch_size, progress_callback
            )
        return results

    async def index_incident(self, incident: dict[str, Any]) -> IndexedDocument:
        """Convenience method to index an incident."""
        return await self.index_document(SearchableType.INCIDENT, incident)

    async def index_runbook(self, runbook: dict[str, Any]) -> IndexedDocument:
        """Convenience method to index a runbook."""
        return await self.index_document(SearchableType.RUNBOOK, runbook)

    async def index_postmortem(self, postmortem: dict[str, Any]) -> IndexedDocument:
        """Convenience method to index a postmortem."""
        return await self.index_document(SearchableType.POSTMORTEM, postmortem)

    def get_stats(self) -> dict[str, Any]:
        """Get indexing statistics."""
        return {
            **self._index_stats,
            "last_index_times": {
                k.value: v.isoformat() for k, v in self._last_index_time.items()
            },
            "registered_sources": [t.value for t in self._sources],
        }


class InMemoryDocumentSource:
    """Simple in-memory document source for testing."""

    def __init__(self):
        self._documents: dict[str, dict[str, Any]] = {}

    def add(self, doc: dict[str, Any]) -> None:
        """Add a document."""
        doc_id = str(doc.get("id", len(self._documents)))
        self._documents[doc_id] = doc

    def remove(self, doc_id: str) -> bool:
        """Remove a document."""
        if doc_id in self._documents:
            del self._documents[doc_id]
            return True
        return False

    async def get_all(self) -> list[dict[str, Any]]:
        """Get all documents."""
        return list(self._documents.values())

    async def get_by_id(self, doc_id: str) -> dict[str, Any] | None:
        """Get document by ID."""
        return self._documents.get(doc_id)


class WebhookIndexer:
    """Handles webhook events to keep index in sync."""

    def __init__(self, indexing_service: IndexingService):
        self._service = indexing_service
        self._event_handlers: dict[str, callable] = {
            "incident.created": self._handle_incident_created,
            "incident.updated": self._handle_incident_updated,
            "incident.deleted": self._handle_incident_deleted,
            "runbook.created": self._handle_runbook_created,
            "runbook.updated": self._handle_runbook_updated,
            "runbook.deleted": self._handle_runbook_deleted,
            "postmortem.created": self._handle_postmortem_created,
            "postmortem.updated": self._handle_postmortem_updated,
            "postmortem.deleted": self._handle_postmortem_deleted,
        }

    async def handle_event(self, event_type: str, payload: dict[str, Any]) -> bool:
        """Handle a webhook event."""
        handler = self._event_handlers.get(event_type)
        if handler:
            await handler(payload)
            return True
        return False

    async def _handle_incident_created(self, payload: dict) -> None:
        await self._service.index_incident(payload)

    async def _handle_incident_updated(self, payload: dict) -> None:
        await self._service.index_incident(payload)

    async def _handle_incident_deleted(self, payload: dict) -> None:
        await self._service.delete_document(str(payload.get("id")))

    async def _handle_runbook_created(self, payload: dict) -> None:
        await self._service.index_runbook(payload)

    async def _handle_runbook_updated(self, payload: dict) -> None:
        await self._service.index_runbook(payload)

    async def _handle_runbook_deleted(self, payload: dict) -> None:
        await self._service.delete_document(str(payload.get("id")))

    async def _handle_postmortem_created(self, payload: dict) -> None:
        await self._service.index_postmortem(payload)

    async def _handle_postmortem_updated(self, payload: dict) -> None:
        await self._service.index_postmortem(payload)

    async def _handle_postmortem_deleted(self, payload: dict) -> None:
        await self._service.delete_document(str(payload.get("id")))

    def get_supported_events(self) -> list[str]:
        """Get list of supported event types."""
        return list(self._event_handlers.keys())
