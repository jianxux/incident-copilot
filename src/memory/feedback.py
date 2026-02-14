"""Feedback storage and scoring adjustments for incident memory recall."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

FeedbackType = Literal["helpful", "not_helpful", "partial"]


class ResolutionFeedback(BaseModel):
    """Operator feedback about recalled incident usefulness."""

    incident_id: str = Field(..., min_length=1)
    recalled_incident_id: str = Field(..., min_length=1)
    feedback: FeedbackType
    notes: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FeedbackStore:
    """SQLite-backed store for resolution feedback events."""

    def __init__(self, database_path: str = "data/incident_memory_feedback.db"):
        self.database_path = Path(database_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incident_memory_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT NOT NULL,
                    recalled_incident_id TEXT NOT NULL,
                    feedback TEXT NOT NULL CHECK(feedback IN ('helpful', 'not_helpful', 'partial')),
                    notes TEXT,
                    timestamp TEXT NOT NULL
                )
                """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feedback_incident_id
                ON incident_memory_feedback (incident_id)
                """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_feedback_pair
                ON incident_memory_feedback (incident_id, recalled_incident_id)
                """)
            conn.commit()
        finally:
            conn.close()

    async def submit(self, item: ResolutionFeedback) -> ResolutionFeedback:
        """Persist one feedback record."""
        await asyncio.to_thread(self._submit_sync, item)
        logger.info(
            "incident_memory_feedback_submitted",
            incident_id=item.incident_id,
            recalled_incident_id=item.recalled_incident_id,
            feedback=item.feedback,
        )
        return item

    def _submit_sync(self, item: ResolutionFeedback) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO incident_memory_feedback (
                    incident_id,
                    recalled_incident_id,
                    feedback,
                    notes,
                    timestamp
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item.incident_id,
                    item.recalled_incident_id,
                    item.feedback,
                    item.notes,
                    item.timestamp.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def list_for_incident(self, incident_id: str) -> list[ResolutionFeedback]:
        """List all feedback for an incident."""
        return await asyncio.to_thread(self._list_for_incident_sync, incident_id)

    def _list_for_incident_sync(self, incident_id: str) -> list[ResolutionFeedback]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT incident_id, recalled_incident_id, feedback, notes, timestamp
                FROM incident_memory_feedback
                WHERE incident_id = ?
                ORDER BY timestamp DESC
                """,
                (incident_id,),
            ).fetchall()
            return [self._row_to_feedback(row) for row in rows]
        finally:
            conn.close()

    async def feedback_breakdown(self) -> dict[str, int]:
        """Count feedback events by type."""
        return await asyncio.to_thread(self._feedback_breakdown_sync)

    def _feedback_breakdown_sync(self) -> dict[str, int]:
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT feedback, COUNT(*) AS count
                FROM incident_memory_feedback
                GROUP BY feedback
                """).fetchall()
            breakdown = {"helpful": 0, "not_helpful": 0, "partial": 0}
            for row in rows:
                breakdown[str(row["feedback"])] = int(row["count"])
            return breakdown
        finally:
            conn.close()

    async def similarity_weight_adjustment(
        self, incident_id: str, recalled_incident_id: str
    ) -> float:
        """Return bounded score adjustment for an incident-pair feedback history."""
        return await asyncio.to_thread(
            self._similarity_weight_adjustment_sync,
            incident_id,
            recalled_incident_id,
        )

    def _similarity_weight_adjustment_sync(
        self, incident_id: str, recalled_incident_id: str
    ) -> float:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT feedback
                FROM incident_memory_feedback
                WHERE incident_id = ? AND recalled_incident_id = ?
                """,
                (incident_id, recalled_incident_id),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return 0.0

        weights = {"helpful": 1.0, "partial": 0.3, "not_helpful": -1.0}
        aggregate = sum(weights.get(str(row["feedback"]), 0.0) for row in rows)
        average = aggregate / len(rows)
        return max(-0.25, min(0.25, round(average * 0.20, 4)))

    async def recall_hit_rate(self) -> float:
        """Compute incident-level recall hit rate from feedback outcomes."""
        return await asyncio.to_thread(self._recall_hit_rate_sync)

    def _recall_hit_rate_sync(self) -> float:
        conn = self._connect()
        try:
            rows = conn.execute("""
                SELECT incident_id, feedback
                FROM incident_memory_feedback
                """).fetchall()
        finally:
            conn.close()

        if not rows:
            return 0.0

        per_incident: dict[str, list[str]] = {}
        for row in rows:
            incident_id = str(row["incident_id"])
            per_incident.setdefault(incident_id, []).append(str(row["feedback"]))

        hits = 0
        for feedbacks in per_incident.values():
            if any(item in {"helpful", "partial"} for item in feedbacks):
                hits += 1

        return round(hits / len(per_incident), 4)

    @staticmethod
    def _row_to_feedback(row: sqlite3.Row) -> ResolutionFeedback:
        return ResolutionFeedback(
            incident_id=str(row["incident_id"]),
            recalled_incident_id=str(row["recalled_incident_id"]),
            feedback=str(row["feedback"]),  # type: ignore[arg-type]
            notes=str(row["notes"]) if row["notes"] is not None else None,
            timestamp=datetime.fromisoformat(str(row["timestamp"])),
        )


_feedback_store: FeedbackStore | None = None


def get_feedback_store(
    database_path: str = "data/incident_memory_feedback.db",
) -> FeedbackStore:
    """Get singleton feedback store."""
    global _feedback_store
    if _feedback_store is None:
        _feedback_store = FeedbackStore(database_path=database_path)
    return _feedback_store
