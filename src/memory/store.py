"""PostgreSQL-backed incident memory store using pgvector."""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
import structlog

from .config import IncidentMemoryConfig
from .models import IncidentRecallResult, IncidentRecord

if TYPE_CHECKING:
    from .recall import RecallQuery

logger = structlog.get_logger()


class IncidentMemoryStore:
    """Store and recall incident memory records from PostgreSQL."""

    def __init__(
        self,
        database_url: str,
        config: IncidentMemoryConfig | None = None,
        pool: asyncpg.Pool | None = None,
    ):
        self.database_url = database_url
        self.config = config or IncidentMemoryConfig(database_url=database_url)
        self._pool = pool

    async def connect(self) -> None:
        """Open asyncpg connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url.replace("+asyncpg", ""),
                min_size=1,
                max_size=10,
            )

    async def disconnect(self) -> None:
        """Close asyncpg pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def store(self, record: IncidentRecord) -> IncidentRecord:
        """Insert or update an incident memory record."""
        pool = await self._ensure_pool()

        await pool.execute(
            f"""
            INSERT INTO {self.config.table_name} (
                id, title, created_at, resolved_at, duration_minutes, severity,
                services_affected, root_cause_category, root_cause_summary,
                error_signatures, metric_anomalies, deploy_involved, deploy_sha,
                resolution_steps, resolution_summary, time_to_diagnose_minutes,
                time_to_fix_minutes, was_rollback, runbook_used,
                what_helped, what_was_missing, tags, embedding, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9,
                $10, $11, $12, $13,
                $14, $15, $16,
                $17, $18, $19,
                $20, $21, $22, $23::vector, NOW()
            )
            ON CONFLICT (id)
            DO UPDATE SET
                title = EXCLUDED.title,
                created_at = EXCLUDED.created_at,
                resolved_at = EXCLUDED.resolved_at,
                duration_minutes = EXCLUDED.duration_minutes,
                severity = EXCLUDED.severity,
                services_affected = EXCLUDED.services_affected,
                root_cause_category = EXCLUDED.root_cause_category,
                root_cause_summary = EXCLUDED.root_cause_summary,
                error_signatures = EXCLUDED.error_signatures,
                metric_anomalies = EXCLUDED.metric_anomalies,
                deploy_involved = EXCLUDED.deploy_involved,
                deploy_sha = EXCLUDED.deploy_sha,
                resolution_steps = EXCLUDED.resolution_steps,
                resolution_summary = EXCLUDED.resolution_summary,
                time_to_diagnose_minutes = EXCLUDED.time_to_diagnose_minutes,
                time_to_fix_minutes = EXCLUDED.time_to_fix_minutes,
                was_rollback = EXCLUDED.was_rollback,
                runbook_used = EXCLUDED.runbook_used,
                what_helped = EXCLUDED.what_helped,
                what_was_missing = EXCLUDED.what_was_missing,
                tags = EXCLUDED.tags,
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
            """,  # nosec B608 - table_name from config, not user input
            record.id,
            record.title,
            record.created_at,
            record.resolved_at,
            record.duration_minutes,
            record.severity,
            record.services_affected,
            record.root_cause_category,
            record.root_cause_summary,
            record.error_signatures,
            record.metric_anomalies,
            record.deploy_involved,
            record.deploy_sha,
            record.resolution_steps,
            record.resolution_summary,
            record.time_to_diagnose_minutes,
            record.time_to_fix_minutes,
            record.was_rollback,
            record.runbook_used,
            record.what_helped,
            record.what_was_missing,
            record.tags,
            self._to_vector_literal(record.embedding),
        )
        return record

    async def recall(self, query: RecallQuery) -> list[IncidentRecallResult]:
        """Recall similar incidents using vector + structured filters."""
        pool = await self._ensure_pool()

        start_time = query.start_time
        end_time = query.end_time
        if query.lookback_days is not None and start_time is None:
            import datetime as dt

            start_time = dt.datetime.now(dt.UTC) - dt.timedelta(days=query.lookback_days)

        rows = await pool.fetch(
            f"""
            WITH base AS (
                SELECT
                    *,
                    (1 - (embedding <=> $1::vector))::float8 AS vector_similarity,
                    exp(
                        -ln(2)
                        * GREATEST(EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400.0, 0)
                        / NULLIF($2::float8, 0)
                    )::float8 AS temporal_decay
                FROM {self.config.table_name}
                WHERE embedding IS NOT NULL
                  AND ($3::text[] IS NULL OR services_affected && $3::text[])
                  AND ($4::text IS NULL OR severity = $4::text)
                  AND ($5::timestamptz IS NULL OR created_at >= $5)
                  AND ($6::timestamptz IS NULL OR created_at <= $6)
                ORDER BY embedding <=> $1::vector
                LIMIT $7
            )
            SELECT
                *,
                (
                    vector_similarity * temporal_decay
                    + CASE
                        WHEN $3::text[] IS NOT NULL AND services_affected && $3::text[]
                        THEN $8::float8 ELSE 0::float8 END
                    + CASE
                        WHEN $4::text IS NOT NULL AND severity = $4::text
                        THEN $9::float8 ELSE 0::float8 END
                ) AS score
            FROM base
            WHERE vector_similarity >= $10::float8
            ORDER BY score DESC
            LIMIT $11
            """,  # nosec B608 - table_name from config, not user input
            self._to_vector_literal(query.embedding),
            float(self.config.recall_temporal_half_life_days),
            query.services if query.services else None,
            query.severity,
            start_time,
            end_time,
            int(query.candidate_limit or self.config.recall_candidate_limit),
            float(self.config.recall_service_boost),
            float(self.config.recall_severity_boost),
            float(query.min_similarity or self.config.recall_min_similarity),
            int(query.limit or self.config.recall_default_limit),
        )

        results: list[IncidentRecallResult] = []
        for row in rows:
            results.append(
                IncidentRecallResult(
                    record=self._row_to_record(row),
                    score=float(row["score"]),
                    vector_similarity=float(row["vector_similarity"]),
                    temporal_decay=float(row["temporal_decay"]),
                )
            )
        return results

    async def get(self, record_id: str) -> IncidentRecord | None:
        """Get a record by id."""
        pool = await self._ensure_pool()
        row = await pool.fetchrow(
            f"SELECT * FROM {self.config.table_name} WHERE id = $1",  # nosec B608
            record_id,
        )
        if row is None:
            return None
        return self._row_to_record(row)

    async def delete(self, record_id: str) -> bool:
        """Delete a record by id."""
        pool = await self._ensure_pool()
        result = await pool.execute(
            f"DELETE FROM {self.config.table_name} WHERE id = $1",  # nosec B608
            record_id,
        )
        return result.endswith("1")

    async def count(self) -> int:
        """Count all records."""
        pool = await self._ensure_pool()
        return int(
            await pool.fetchval(
                f"SELECT COUNT(*) FROM {self.config.table_name}"  # nosec B608
            )
        )

    async def list_recent(self, limit: int = 10) -> list[IncidentRecord]:
        """List most recent records by created_at."""
        pool = await self._ensure_pool()
        rows = await pool.fetch(
            f"SELECT * FROM {self.config.table_name} ORDER BY created_at DESC LIMIT $1",  # nosec B608
            limit,
        )
        return [self._row_to_record(row) for row in rows]

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            await self.connect()
        assert self._pool is not None
        return self._pool

    @staticmethod
    def _to_vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(f"{value:.10f}" for value in embedding) + "]"

    @staticmethod
    def _row_to_record(row: asyncpg.Record) -> IncidentRecord:
        def to_list(value: object | None) -> list[str]:
            if value is None:
                return []
            if isinstance(value, list):
                return [str(item) for item in value]
            return []

        embedding_value = row.get("embedding")
        if isinstance(embedding_value, str):
            cleaned = embedding_value.strip("[]")
            embedding = [float(part) for part in cleaned.split(",") if part.strip()]
        elif isinstance(embedding_value, list):
            embedding = [float(v) for v in embedding_value]
        else:
            embedding = []

        return IncidentRecord(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            resolved_at=row.get("resolved_at"),
            duration_minutes=row.get("duration_minutes"),
            severity=row.get("severity"),
            services_affected=to_list(row.get("services_affected")),
            root_cause_category=row.get("root_cause_category"),
            root_cause_summary=row.get("root_cause_summary"),
            error_signatures=to_list(row.get("error_signatures")),
            metric_anomalies=to_list(row.get("metric_anomalies")),
            deploy_involved=bool(row.get("deploy_involved", False)),
            deploy_sha=row.get("deploy_sha"),
            resolution_steps=to_list(row.get("resolution_steps")),
            resolution_summary=row.get("resolution_summary"),
            time_to_diagnose_minutes=row.get("time_to_diagnose_minutes"),
            time_to_fix_minutes=row.get("time_to_fix_minutes"),
            was_rollback=row.get("was_rollback"),
            runbook_used=row.get("runbook_used"),
            what_helped=row.get("what_helped"),
            what_was_missing=row.get("what_was_missing"),
            tags=to_list(row.get("tags")),
            embedding=embedding,
        )
