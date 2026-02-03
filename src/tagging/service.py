"""Tag management service for incident copilot."""

import structlog

from ..config import Settings, get_settings
from .models import (
    AddTagsRequest,
    AutoTagRule,
    AutoTagRuleCreate,
    AutoTagRuleUpdate,
    IncidentTag,
    IncidentTagsResponse,
    Tag,
    TagCreate,
    TagHierarchy,
    TagListResponse,
    TagSearchFilters,
    TagStats,
    TagSuggestion,
    TagUpdate,
)
from .store import PostgresTagStore, TagStore, get_tag_store
from .suggestions import TagSuggester, get_tag_suggester

logger = structlog.get_logger()


class TaggingService:
    """High-level service for managing incident tags."""

    def __init__(
        self,
        store: TagStore | PostgresTagStore | None = None,
        suggester: TagSuggester | None = None,
        settings: Settings | None = None,
    ):
        self.store = store or get_tag_store()
        self.settings = settings or get_settings()
        self.suggester = suggester or get_tag_suggester(self.settings)

    async def create_tag(
        self, request: TagCreate, created_by: str | None = None
    ) -> Tag:
        """Create a new tag."""
        if request.parent_id:
            parent = await self.store.get_tag(request.parent_id)
            if not parent:
                raise ValueError(f"Parent tag '{request.parent_id}' not found")
        existing = await self.store.get_tag_by_name(request.name)
        if existing:
            raise ValueError(f"Tag with name '{request.name}' already exists")
        return await self.store.create_tag(request, created_by)

    async def get_tag(self, tag_id: str) -> Tag | None:
        """Get a tag by ID."""
        return await self.store.get_tag(tag_id)

    async def get_tag_by_name(self, name: str) -> Tag | None:
        """Get a tag by name."""
        return await self.store.get_tag_by_name(name)

    async def update_tag(self, tag_id: str, request: TagUpdate) -> Tag | None:
        """Update an existing tag."""
        tag = await self.store.get_tag(tag_id)
        if not tag:
            return None
        if request.parent_id:
            if request.parent_id == tag_id:
                raise ValueError("Tag cannot be its own parent")
            descendants = await self.store.get_all_descendants(tag_id)
            if request.parent_id in descendants:
                raise ValueError("Cannot create circular tag hierarchy")
            parent = await self.store.get_tag(request.parent_id)
            if not parent:
                raise ValueError(f"Parent tag '{request.parent_id}' not found")
        if request.name and request.name != tag.name:
            existing = await self.store.get_tag_by_name(request.name)
            if existing and existing.id != tag_id:
                raise ValueError(f"Tag with name '{request.name}' already exists")
        return await self.store.update_tag(tag_id, request)

    async def delete_tag(self, tag_id: str) -> bool:
        """Delete a tag."""
        tag = await self.store.get_tag(tag_id)
        if not tag:
            return False
        if tag.is_system:
            raise ValueError("Cannot delete system-managed tags")
        return await self.store.delete_tag(tag_id)

    async def list_tags(
        self,
        parent_id: str | None = None,
        include_children: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> TagListResponse:
        """List tags with optional filtering."""
        tags, total = await self.store.list_tags(
            parent_id=parent_id,
            include_children=include_children,
            limit=limit,
            offset=offset,
        )
        return TagListResponse(tags=tags, total=total)

    async def get_tag_hierarchy(self, root_id: str | None = None) -> list[TagHierarchy]:
        """Get tags in a hierarchical structure."""
        if root_id:
            tag = await self.store.get_tag(root_id)
            if not tag:
                return []
            children = await self._build_hierarchy(root_id)
            return [TagHierarchy(tag=tag, children=children)]
        root_tags, _ = await self.store.list_tags(
            parent_id=None, include_children=False
        )
        return [
            TagHierarchy(tag=tag, children=await self._build_hierarchy(tag.id))
            for tag in root_tags
        ]

    async def _build_hierarchy(self, parent_id: str) -> list[TagHierarchy]:
        """Recursively build tag hierarchy."""
        children = await self.store.get_children(parent_id)
        return [
            TagHierarchy(tag=child, children=await self._build_hierarchy(child.id))
            for child in children
        ]

    async def add_tags_to_incident(
        self,
        incident_id: str,
        request: AddTagsRequest,
        applied_by: str | None = None,
    ) -> list[IncidentTag]:
        """Add tags to an incident."""
        return await self.store.add_tags_to_incident(
            incident_id=incident_id,
            tag_ids=request.tag_ids,
            applied_by=applied_by,
        )

    async def remove_tag_from_incident(self, incident_id: str, tag_id: str) -> bool:
        """Remove a tag from an incident."""
        return await self.store.remove_tag_from_incident(incident_id, tag_id)

    async def get_incident_tags(self, incident_id: str) -> IncidentTagsResponse:
        """Get all tags for an incident."""
        tags = await self.store.get_incident_tags(incident_id)
        return IncidentTagsResponse(incident_id=incident_id, tags=tags)

    async def get_incidents_by_tag(
        self,
        tag_id: str,
        include_children: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[Tag | None, list[str], int]:
        """Get all incidents with a specific tag."""
        tag = await self.store.get_tag(tag_id)
        if not tag:
            return None, [], 0
        incident_ids, total = await self.store.get_incidents_by_tag(
            tag_id=tag_id,
            include_children=include_children,
            limit=limit,
            offset=offset,
        )
        return tag, incident_ids, total

    async def search_incidents_by_tags(self, filters: TagSearchFilters) -> list[str]:
        """Search incidents by tag filters."""
        if not filters.tag_ids:
            return []
        return await self.store.search_incidents_by_tags(
            tag_ids=filters.tag_ids,
            match_all=filters.match_all,
            include_children=filters.include_children,
        )

    async def create_auto_rule(
        self,
        request: AutoTagRuleCreate,
        created_by: str | None = None,
    ) -> AutoTagRule:
        """Create an auto-tagging rule."""
        tag = await self.store.get_tag(request.tag_id)
        if not tag:
            raise ValueError(f"Tag '{request.tag_id}' not found")
        return await self.store.create_auto_rule(request, created_by)

    async def get_auto_rule(self, rule_id: str) -> AutoTagRule | None:
        """Get an auto-tagging rule by ID."""
        return await self.store.get_auto_rule(rule_id)

    async def update_auto_rule(
        self, rule_id: str, request: AutoTagRuleUpdate
    ) -> AutoTagRule | None:
        """Update an auto-tagging rule."""
        return await self.store.update_auto_rule(rule_id, request)

    async def delete_auto_rule(self, rule_id: str) -> bool:
        """Delete an auto-tagging rule."""
        return await self.store.delete_auto_rule(rule_id)

    async def list_auto_rules(
        self, tag_id: str | None = None, enabled_only: bool = False
    ) -> list[AutoTagRule]:
        """List auto-tagging rules."""
        return await self.store.list_auto_rules(tag_id, enabled_only)

    async def auto_tag_incident(
        self,
        incident_id: str,
        service_name: str,
        title: str,
        severity: str,
    ) -> list[IncidentTag]:
        """Automatically apply tags to an incident based on rules."""
        matches = await self.store.evaluate_auto_rules(
            incident_id=incident_id,
            service_name=service_name,
            title=title,
            severity=severity,
        )
        if not matches:
            return []
        applied = []
        for tag_id, confidence in matches:
            result = await self.store.add_tags_to_incident(
                incident_id=incident_id,
                tag_ids=[tag_id],
                auto_applied=True,
                confidence=confidence,
            )
            applied.extend(result)
        return applied

    async def suggest_tags(
        self,
        title: str,
        service_name: str,
        severity: str,
        description: str | None = None,
        max_suggestions: int = 5,
    ) -> list[TagSuggestion]:
        """Get AI-powered tag suggestions for an incident."""
        tags, _ = await self.store.list_tags(include_children=True, limit=1000)
        if not tags:
            return []
        return await self.suggester.suggest_tags(
            title=title,
            service_name=service_name,
            severity=severity,
            description=description,
            available_tags=tags,
            max_suggestions=max_suggestions,
        )

    async def apply_suggested_tags(
        self,
        incident_id: str,
        suggestions: list[TagSuggestion],
        min_confidence: float = 0.8,
        applied_by: str | None = None,
    ) -> list[IncidentTag]:
        """Apply AI-suggested tags above a confidence threshold."""
        tag_ids = [s.tag_id for s in suggestions if s.confidence >= min_confidence]
        if not tag_ids:
            return []
        return await self.store.add_tags_to_incident(
            incident_id=incident_id,
            tag_ids=tag_ids,
            applied_by=applied_by or "ai",
            auto_applied=True,
            confidence=max(s.confidence for s in suggestions if s.tag_id in tag_ids),
        )

    async def get_tag_stats(self, tag_id: str) -> TagStats | None:
        """Get usage statistics for a tag."""
        tag = await self.store.get_tag(tag_id)
        if not tag:
            return None
        _, total = await self.store.get_incidents_by_tag(
            tag_id=tag_id, include_children=True
        )
        return TagStats(tag_id=tag_id, tag_name=tag.name, incident_count=total)

    async def get_popular_tags(self, limit: int = 10) -> list[TagStats]:
        """Get most frequently used tags."""
        tags, _ = await self.store.list_tags(include_children=True, limit=1000)
        stats = []
        for tag in tags:
            _, total = await self.store.get_incidents_by_tag(
                tag_id=tag.id, include_children=False
            )
            stats.append(
                TagStats(tag_id=tag.id, tag_name=tag.name, incident_count=total)
            )
        stats.sort(key=lambda s: s.incident_count, reverse=True)
        return stats[:limit]


_service: TaggingService | None = None


def get_tagging_service() -> TaggingService:
    """Get or create the global tagging service."""
    global _service
    if _service is None:
        _service = TaggingService()
    return _service


def reset_tagging_service() -> None:
    """Reset the global tagging service (for testing)."""
    global _service
    _service = None
