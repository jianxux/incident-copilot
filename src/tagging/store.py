"""Storage for tags and incident-tag associations."""

import asyncio
import re
import uuid
from datetime import datetime, UTC

import structlog

from .models import (
    AutoTagRule,
    AutoTagRuleCreate,
    AutoTagRuleType,
    AutoTagRuleUpdate,
    IncidentTag,
    Tag,
    TagCreate,
    TagUpdate,
)

logger = structlog.get_logger()


class TagStore:
    """In-memory tag store for development and testing."""

    def __init__(self):
        self._tags: dict[str, Tag] = {}
        self._incident_tags: dict[str, list[IncidentTag]] = {}
        self._tag_incidents: dict[str, set[str]] = {}
        self._auto_rules: dict[str, AutoTagRule] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the store."""
        pass

    async def create_tag(
        self, request: TagCreate, created_by: str | None = None
    ) -> Tag:
        """Create a new tag."""
        async with self._lock:
            tag_id = f"tag-{uuid.uuid4().hex[:12]}"
            tag = Tag(
                id=tag_id,
                name=request.name,
                description=request.description,
                color=request.color,
                parent_id=request.parent_id,
                created_by=created_by,
            )
            self._tags[tag_id] = tag
            self._tag_incidents[tag_id] = set()
            logger.info("tag_created", tag_id=tag_id, name=request.name)
            return tag

    async def get_tag(self, tag_id: str) -> Tag | None:
        """Get a tag by ID."""
        return self._tags.get(tag_id)

    async def get_tag_by_name(self, name: str) -> Tag | None:
        """Get a tag by name."""
        for tag in self._tags.values():
            if tag.name.lower() == name.lower():
                return tag
        return None

    async def update_tag(self, tag_id: str, request: TagUpdate) -> Tag | None:
        """Update an existing tag."""
        async with self._lock:
            tag = self._tags.get(tag_id)
            if not tag:
                return None
            update_data = request.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if value is not None:
                    setattr(tag, field, value)
            tag.updated_at = datetime.now(UTC)
            return tag

    async def delete_tag(self, tag_id: str) -> bool:
        """Delete a tag and its associations."""
        async with self._lock:
            if tag_id not in self._tags:
                return False
            for incident_id in list(self._tag_incidents.get(tag_id, [])):
                if incident_id in self._incident_tags:
                    self._incident_tags[incident_id] = [
                        it
                        for it in self._incident_tags[incident_id]
                        if it.tag_id != tag_id
                    ]
            del self._tags[tag_id]
            self._tag_incidents.pop(tag_id, None)
            for tag in self._tags.values():
                if tag.parent_id == tag_id:
                    tag.parent_id = None
            return True

    async def list_tags(
        self,
        parent_id: str | None = None,
        include_children: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Tag], int]:
        """List tags with optional parent filter."""
        tags = list(self._tags.values())
        if parent_id is not None:
            tags = [t for t in tags if t.parent_id == parent_id]
        elif not include_children:
            tags = [t for t in tags if t.parent_id is None]
        for tag in tags:
            tag.incident_count = len(self._tag_incidents.get(tag.id, []))
        total = len(tags)
        tags = sorted(tags, key=lambda t: t.name.lower())
        return tags[offset : offset + limit], total

    async def get_children(self, parent_id: str) -> list[Tag]:
        """Get all child tags of a parent."""
        return [t for t in self._tags.values() if t.parent_id == parent_id]

    async def get_all_descendants(self, tag_id: str) -> list[str]:
        """Get all descendant tag IDs (recursive)."""
        descendants = []
        children = await self.get_children(tag_id)
        for child in children:
            descendants.append(child.id)
            descendants.extend(await self.get_all_descendants(child.id))
        return descendants

    async def add_tags_to_incident(
        self,
        incident_id: str,
        tag_ids: list[str],
        applied_by: str | None = None,
        auto_applied: bool = False,
        confidence: float | None = None,
    ) -> list[IncidentTag]:
        """Add tags to an incident."""
        async with self._lock:
            if incident_id not in self._incident_tags:
                self._incident_tags[incident_id] = []
            added = []
            existing_tag_ids = {it.tag_id for it in self._incident_tags[incident_id]}
            for tag_id in tag_ids:
                if tag_id not in self._tags or tag_id in existing_tag_ids:
                    continue
                incident_tag = IncidentTag(
                    incident_id=incident_id,
                    tag_id=tag_id,
                    applied_by=applied_by,
                    auto_applied=auto_applied,
                    confidence=confidence,
                )
                self._incident_tags[incident_id].append(incident_tag)
                self._tag_incidents[tag_id].add(incident_id)
                added.append(incident_tag)
            return added

    async def remove_tag_from_incident(self, incident_id: str, tag_id: str) -> bool:
        """Remove a tag from an incident."""
        async with self._lock:
            if incident_id not in self._incident_tags:
                return False
            original_len = len(self._incident_tags[incident_id])
            self._incident_tags[incident_id] = [
                it for it in self._incident_tags[incident_id] if it.tag_id != tag_id
            ]
            if len(self._incident_tags[incident_id]) < original_len:
                if tag_id in self._tag_incidents:
                    self._tag_incidents[tag_id].discard(incident_id)
                return True
            return False

    async def get_incident_tags(self, incident_id: str) -> list[Tag]:
        """Get all tags for an incident."""
        incident_tags = self._incident_tags.get(incident_id, [])
        return [
            self._tags[it.tag_id] for it in incident_tags if it.tag_id in self._tags
        ]

    async def get_incidents_by_tag(
        self,
        tag_id: str,
        include_children: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[str], int]:
        """Get all incident IDs with a specific tag."""
        tag_ids = {tag_id}
        if include_children:
            tag_ids.update(await self.get_all_descendants(tag_id))
        incident_ids = set()
        for tid in tag_ids:
            incident_ids.update(self._tag_incidents.get(tid, []))
        incident_list = sorted(incident_ids)
        return incident_list[offset : offset + limit], len(incident_list)

    async def search_incidents_by_tags(
        self,
        tag_ids: list[str],
        match_all: bool = False,
        include_children: bool = True,
    ) -> list[str]:
        """Search incidents by multiple tags."""
        if not tag_ids:
            return []
        expanded_tag_ids = set(tag_ids)
        if include_children:
            for tag_id in tag_ids:
                expanded_tag_ids.update(await self.get_all_descendants(tag_id))
        tag_incident_sets = [
            self._tag_incidents.get(tid, set()) for tid in expanded_tag_ids
        ]
        if match_all:
            result = (
                set.intersection(*tag_incident_sets) if tag_incident_sets else set()
            )
        else:
            result = set.union(*tag_incident_sets) if tag_incident_sets else set()
        return sorted(result)

    async def create_auto_rule(
        self,
        request: AutoTagRuleCreate,
        created_by: str | None = None,
    ) -> AutoTagRule:
        """Create an auto-tag rule."""
        async with self._lock:
            rule_id = f"rule-{uuid.uuid4().hex[:12]}"
            rule = AutoTagRule(
                id=rule_id,
                tag_id=request.tag_id,
                rule_type=request.rule_type,
                pattern=request.pattern,
                is_enabled=request.is_enabled,
                priority=request.priority,
                created_by=created_by,
            )
            self._auto_rules[rule_id] = rule
            return rule

    async def get_auto_rule(self, rule_id: str) -> AutoTagRule | None:
        """Get an auto-tag rule by ID."""
        return self._auto_rules.get(rule_id)

    async def update_auto_rule(
        self, rule_id: str, request: AutoTagRuleUpdate
    ) -> AutoTagRule | None:
        """Update an auto-tag rule."""
        async with self._lock:
            rule = self._auto_rules.get(rule_id)
            if not rule:
                return None
            update_data = request.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if value is not None:
                    setattr(rule, field, value)
            rule.updated_at = datetime.now(UTC)
            return rule

    async def delete_auto_rule(self, rule_id: str) -> bool:
        """Delete an auto-tag rule."""
        async with self._lock:
            if rule_id in self._auto_rules:
                del self._auto_rules[rule_id]
                return True
            return False

    async def list_auto_rules(
        self, tag_id: str | None = None, enabled_only: bool = False
    ) -> list[AutoTagRule]:
        """List auto-tag rules."""
        rules = list(self._auto_rules.values())
        if tag_id:
            rules = [r for r in rules if r.tag_id == tag_id]
        if enabled_only:
            rules = [r for r in rules if r.is_enabled]
        return sorted(rules, key=lambda r: (-r.priority, r.created_at))

    async def evaluate_auto_rules(
        self,
        incident_id: str,
        service_name: str,
        title: str,
        severity: str,
    ) -> list[tuple[str, float]]:
        """Evaluate all auto-tag rules for an incident."""
        rules = await self.list_auto_rules(enabled_only=True)
        matches: list[tuple[str, float]] = []
        matched_tags = set()
        for rule in rules:
            if rule.tag_id in matched_tags:
                continue
            confidence = 0.0
            if rule.rule_type == AutoTagRuleType.SERVICE_NAME:
                if service_name.lower() == rule.pattern.lower():
                    confidence = 1.0
            elif rule.rule_type == AutoTagRuleType.TITLE_KEYWORD:
                if rule.pattern.lower() in title.lower():
                    confidence = 0.9
            elif rule.rule_type == AutoTagRuleType.SEVERITY:
                if severity.lower() == rule.pattern.lower():
                    confidence = 1.0
            elif rule.rule_type == AutoTagRuleType.REGEX:
                try:
                    if re.search(rule.pattern, title, re.IGNORECASE):
                        confidence = 0.85
                except re.error:
                    pass
            if confidence > 0:
                matches.append((rule.tag_id, confidence))
                matched_tags.add(rule.tag_id)
        return matches

    async def clear(self) -> None:
        """Clear all data (for testing)."""
        async with self._lock:
            self._tags.clear()
            self._incident_tags.clear()
            self._tag_incidents.clear()
            self._auto_rules.clear()


class PostgresTagStore:
    """PostgreSQL-backed tag store for production use."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool = None

    async def connect(self) -> None:
        """Establish database connection pool."""
        import asyncpg

        self._pool = await asyncpg.create_pool(
            self.database_url.replace("+asyncpg", ""),
            min_size=2,
            max_size=10,
        )

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        if not self._pool:
            await self.connect()
        logger.info("postgres_tag_store_initialized")


# Global store instance (in-memory by default)
tag_store: TagStore | PostgresTagStore = TagStore()


def get_tag_store() -> TagStore | PostgresTagStore:
    """Get the global tag store instance."""
    return tag_store


async def init_tag_store(database_url: str | None = None) -> None:
    """Initialize the tag store with appropriate backend."""
    global tag_store
    if database_url and "postgresql" in database_url:
        tag_store = PostgresTagStore(database_url)
        await tag_store.connect()
        await tag_store.initialize()
    else:
        tag_store = TagStore()
        await tag_store.initialize()
