"""Audit event storage backends."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from typing import Protocol

import asyncpg

from .models import AuditEvent, AuditLogQuery


class AuditStoreProtocol(Protocol):
    """Protocol for audit store implementations."""

    async def store_event(self, event: AuditEvent) -> AuditEvent:
        """Store an audit event."""
        ...

    async def query_events(self, query: AuditLogQuery) -> list[AuditEvent]:
        """Query audit events."""
        ...

    async def count_events(self, query: AuditLogQuery) -> int:
        """Count audit events matching query."""
        ...

    async def cleanup_old_events(self) -> int:
        """Clean up events older than retention period."""
        ...


class AuditStore:
    """In-memory audit store for development and testing.

    For production, use PostgresAuditStore.
    """

    def __init__(
        self,
        max_events_memory: int = 10000,
        retention_days: int = 90,
    ):
        self.max_events = max_events_memory
        self.retention_days = retention_days
        self._events: list[AuditEvent] = []
        self._events_by_tenant: dict[str, list[AuditEvent]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the in-memory store (no-op for memory store)."""
        pass

    @staticmethod
    def _normalize_to_utc(dt: datetime) -> datetime:
        """Normalize a datetime to timezone-aware UTC.

        Naive datetimes are treated as UTC to preserve prior behavior.
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    async def store_event(self, event: AuditEvent) -> AuditEvent:
        """Store an audit event in memory."""
        async with self._lock:
            self._events.append(event)
            if event.tenant_id:
                self._events_by_tenant[event.tenant_id].append(event)

            # Enforce max events limit (remove oldest)
            while len(self._events) > self.max_events:
                oldest = self._events.pop(0)
                if (
                    oldest.tenant_id
                    and oldest in self._events_by_tenant[oldest.tenant_id]
                ):
                    self._events_by_tenant[oldest.tenant_id].remove(oldest)

        return event

    async def query_events(self, query: AuditLogQuery) -> list[AuditEvent]:
        """Query audit events with filtering and pagination."""
        async with self._lock:
            # Start with tenant-filtered events
            events = list(self._events_by_tenant.get(query.tenant_id, []))

        # Apply filters
        events = self._apply_filters(events, query)

        # Sort by timestamp descending (newest first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply pagination
        start = query.offset
        end = start + query.limit
        return events[start:end]

    async def count_events(self, query: AuditLogQuery) -> int:
        """Count events matching query."""
        async with self._lock:
            events = list(self._events_by_tenant.get(query.tenant_id, []))

        events = self._apply_filters(events, query)
        return len(events)

    async def get_event_by_id(self, event_id: str) -> AuditEvent | None:
        """Get a single event by ID."""
        async with self._lock:
            for event in self._events:
                if event.id == event_id:
                    return event
        return None

    async def cleanup_old_events(self) -> int:
        """Remove events older than retention period."""
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        deleted = 0

        async with self._lock:
            # Filter out old events
            old_events = [
                e for e in self._events if self._normalize_to_utc(e.timestamp) < cutoff
            ]
            deleted = len(old_events)

            self._events = [
                e for e in self._events if self._normalize_to_utc(e.timestamp) >= cutoff
            ]

            # Update tenant indices
            for tenant_id in self._events_by_tenant:
                self._events_by_tenant[tenant_id] = [
                    e
                    for e in self._events_by_tenant[tenant_id]
                    if self._normalize_to_utc(e.timestamp) >= cutoff
                ]

        return deleted

    def _apply_filters(
        self, events: list[AuditEvent], query: AuditLogQuery
    ) -> list[AuditEvent]:
        """Apply query filters to events list."""
        filtered = events

        # Date range filter
        start_date = (
            self._normalize_to_utc(query.start_date) if query.start_date else None
        )
        end_date = self._normalize_to_utc(query.end_date) if query.end_date else None

        if query.start_date:
            filtered = [
                e for e in filtered if self._normalize_to_utc(e.timestamp) >= start_date
            ]
        if query.end_date:
            filtered = [
                e for e in filtered if self._normalize_to_utc(e.timestamp) <= end_date
            ]

        # Event type filter
        if query.event_types:
            filtered = [e for e in filtered if e.event_type in query.event_types]

        # Category filter
        if query.categories:
            filtered = [e for e in filtered if e.category in query.categories]

        # User filter
        if query.user_id:
            filtered = [e for e in filtered if e.user_id == query.user_id]

        # Resource filter
        if query.resource_type:
            filtered = [e for e in filtered if e.resource_type == query.resource_type]
        if query.resource_id:
            filtered = [e for e in filtered if e.resource_id == query.resource_id]

        # Outcome filter
        if query.outcome:
            filtered = [e for e in filtered if e.outcome == query.outcome]

        # IP address filter
        if query.ip_address:
            filtered = [e for e in filtered if e.ip_address == query.ip_address]

        return filtered

    async def search_events(
        self,
        tenant_id: str,
        text: str,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Full-text search across event actions and metadata."""
        async with self._lock:
            events = self._events_by_tenant.get(tenant_id, [])

        text_lower = text.lower()
        matching = []

        for event in events:
            # Search in action
            if text_lower in event.action.lower():
                matching.append(event)
                continue

            # Search in metadata values
            for value in event.metadata.values():
                if isinstance(value, str) and text_lower in value.lower():
                    matching.append(event)
                    break

        # Sort by timestamp descending
        matching.sort(key=lambda e: e.timestamp, reverse=True)
        return matching[:limit]


class PostgresAuditStore:
    """PostgreSQL-based audit store for production use."""

    def __init__(
        self,
        database_url: str,
        retention_days: int = 90,
    ):
        self.database_url = database_url
        self.retention_days = retention_days
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Establish database connection pool."""
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

    async def initialize_schema(self) -> None:
        """Create audit_events table if it doesn't exist."""
        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id VARCHAR(32) PRIMARY KEY,
                    event_type VARCHAR(64) NOT NULL,
                    category VARCHAR(64) NOT NULL,
                    tenant_id VARCHAR(64),
                    user_id VARCHAR(64),
                    user_email VARCHAR(255),
                    action TEXT NOT NULL,
                    resource_type VARCHAR(64),
                    resource_id VARCHAR(255),
                    outcome VARCHAR(32) NOT NULL DEFAULT 'success',
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    request_id VARCHAR(64),
                    request_path TEXT,
                    request_method VARCHAR(10),
                    metadata JSONB DEFAULT '{}',
                    api_key_id VARCHAR(64),
                    session_id VARCHAR(64),
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_audit_tenant_timestamp
                    ON audit_events (tenant_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_user_timestamp
                    ON audit_events (user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_event_type
                    ON audit_events (event_type);
                CREATE INDEX IF NOT EXISTS idx_audit_category
                    ON audit_events (category);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                    ON audit_events (timestamp DESC);
            """
            )

    async def store_event(self, event: AuditEvent) -> AuditEvent:
        """Store an audit event in PostgreSQL."""
        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_events (
                    id, event_type, category, tenant_id, user_id, user_email,
                    action, resource_type, resource_id, outcome, ip_address,
                    user_agent, request_id, request_path, request_method,
                    metadata, api_key_id, session_id, timestamp
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                """,
                event.id,
                event.event_type.value,
                event.category.value,
                event.tenant_id,
                event.user_id,
                event.user_email,
                event.action,
                event.resource_type,
                event.resource_id,
                event.outcome.value,
                event.ip_address,
                event.user_agent,
                event.request_id,
                event.request_path,
                event.request_method,
                event.metadata,
                event.api_key_id,
                event.session_id,
                event.timestamp,
            )

        return event

    async def query_events(self, query: AuditLogQuery) -> list[AuditEvent]:
        """Query audit events from PostgreSQL."""
        if not self._pool:
            await self.connect()

        conditions = ["tenant_id = $1"]
        params: list = [query.tenant_id]
        param_num = 2

        if query.start_date:
            conditions.append(f"timestamp >= ${param_num}")
            params.append(query.start_date)
            param_num += 1

        if query.end_date:
            conditions.append(f"timestamp <= ${param_num}")
            params.append(query.end_date)
            param_num += 1

        if query.event_types:
            placeholders = ", ".join(
                f"${i}" for i in range(param_num, param_num + len(query.event_types))
            )
            conditions.append(f"event_type IN ({placeholders})")
            params.extend(et.value for et in query.event_types)
            param_num += len(query.event_types)

        if query.categories:
            placeholders = ", ".join(
                f"${i}" for i in range(param_num, param_num + len(query.categories))
            )
            conditions.append(f"category IN ({placeholders})")
            params.extend(c.value for c in query.categories)
            param_num += len(query.categories)

        if query.user_id:
            conditions.append(f"user_id = ${param_num}")
            params.append(query.user_id)
            param_num += 1

        if query.resource_type:
            conditions.append(f"resource_type = ${param_num}")
            params.append(query.resource_type)
            param_num += 1

        if query.resource_id:
            conditions.append(f"resource_id = ${param_num}")
            params.append(query.resource_id)
            param_num += 1

        if query.outcome:
            conditions.append(f"outcome = ${param_num}")
            params.append(query.outcome.value)
            param_num += 1

        if query.ip_address:
            conditions.append(f"ip_address = ${param_num}")
            params.append(query.ip_address)
            param_num += 1

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT * FROM audit_events
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_num} OFFSET ${param_num + 1}
        """  # nosec B608 - where_clause is built from validated enum values and parameterized parts
        params.extend([query.limit, query.offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [self._row_to_event(row) for row in rows]

    async def count_events(self, query: AuditLogQuery) -> int:
        """Count events matching query."""
        if not self._pool:
            await self.connect()

        conditions = ["tenant_id = $1"]
        params: list = [query.tenant_id]
        param_num = 2

        if query.start_date:
            conditions.append(f"timestamp >= ${param_num}")
            params.append(query.start_date)
            param_num += 1

        if query.end_date:
            conditions.append(f"timestamp <= ${param_num}")
            params.append(query.end_date)
            param_num += 1

        if query.event_types:
            placeholders = ", ".join(
                f"${i}" for i in range(param_num, param_num + len(query.event_types))
            )
            conditions.append(f"event_type IN ({placeholders})")
            params.extend(et.value for et in query.event_types)
            param_num += len(query.event_types)

        if query.categories:
            placeholders = ", ".join(
                f"${i}" for i in range(param_num, param_num + len(query.categories))
            )
            conditions.append(f"category IN ({placeholders})")
            params.extend(c.value for c in query.categories)
            param_num += len(query.categories)

        if query.user_id:
            conditions.append(f"user_id = ${param_num}")
            params.append(query.user_id)
            param_num += 1

        where_clause = " AND ".join(conditions)

        sql = f"SELECT COUNT(*) FROM audit_events WHERE {where_clause}"  # nosec B608 - where_clause is built from validated enum values and parameterized parts

        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, *params)

    async def cleanup_old_events(self) -> int:
        """Delete events older than retention period."""
        if not self._pool:
            await self.connect()

        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM audit_events WHERE timestamp < $1",
                cutoff,
            )

        # Extract count from "DELETE N"
        return int(result.split()[-1])

    async def search_events(
        self,
        tenant_id: str,
        text: str,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Full-text search across event actions and metadata."""
        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM audit_events
                WHERE tenant_id = $1
                  AND (action ILIKE $2 OR metadata::text ILIKE $2)
                ORDER BY timestamp DESC
                LIMIT $3
                """,
                tenant_id,
                f"%{text}%",
                limit,
            )

        return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row: asyncpg.Record) -> AuditEvent:
        """Convert database row to AuditEvent."""
        from .models import EventCategory, EventType, Outcome

        return AuditEvent(
            id=row["id"],
            event_type=EventType(row["event_type"]),
            category=EventCategory(row["category"]),
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            user_email=row["user_email"],
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            outcome=Outcome(row["outcome"]),
            ip_address=row["ip_address"],
            user_agent=row["user_agent"],
            request_id=row["request_id"],
            request_path=row["request_path"],
            request_method=row["request_method"],
            metadata=dict(row["metadata"]) if row["metadata"] else {},
            api_key_id=row["api_key_id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
        )


# Global instance for dependency injection
audit_store: AuditStore | PostgresAuditStore = AuditStore()


def get_audit_store() -> AuditStore | PostgresAuditStore:
    """Get the global audit store instance."""
    return audit_store


async def init_audit_store(
    database_url: str | None = None, retention_days: int = 90
) -> None:
    """Initialize the audit store with appropriate backend."""
    global audit_store

    if database_url and not database_url.startswith("sqlite"):
        audit_store = PostgresAuditStore(database_url, retention_days)
        await audit_store.connect()
        await audit_store.initialize_schema()
    else:
        audit_store = AuditStore(retention_days=retention_days)
