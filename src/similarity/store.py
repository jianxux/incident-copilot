"""Store and retrieve incidents with embeddings using SQLite."""

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import numpy as np
import structlog

from ..models import ContextCard, PastIncident

logger = structlog.get_logger()

# Default database path
DEFAULT_DB_PATH = Path("data/incidents.db")


class IncidentStore:
    """
    Store incidents with their embeddings in SQLite.

    Uses SQLite for metadata storage and stores embeddings as JSON blobs.
    For MVP, this is simple and works well for thousands of incidents.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    service TEXT NOT NULL,
                    description TEXT,
                    root_cause TEXT,
                    resolution TEXT,
                    occurred_at TEXT NOT NULL,
                    resolved_at TEXT,
                    embedding TEXT,
                    context_card TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_incidents_service
                ON incidents(service)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_incidents_occurred
                ON incidents(occurred_at)
            """)
            conn.commit()

        logger.info("incident_store_initialized", db_path=str(self.db_path))

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def store_incident(
        self,
        incident_id: str,
        title: str,
        service: str,
        occurred_at: datetime,
        embedding: list[float],
        description: str | None = None,
        root_cause: str | None = None,
        resolution: str | None = None,
        resolved_at: datetime | None = None,
        context_card: ContextCard | None = None,
    ) -> None:
        """
        Store an incident with its embedding.

        Args:
            incident_id: Unique incident identifier
            title: Incident title
            service: Service name
            occurred_at: When the incident occurred
            embedding: Vector embedding of the incident
            description: Optional description
            root_cause: Optional root cause (can be added later)
            resolution: Optional resolution notes
            resolved_at: When the incident was resolved
            context_card: Optional full context card
        """
        embedding_json = json.dumps(embedding)
        context_card_json = context_card.model_dump_json() if context_card else None

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO incidents
                (incident_id, title, service, description, root_cause, resolution,
                 occurred_at, resolved_at, embedding, context_card)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    title,
                    service,
                    description,
                    root_cause,
                    resolution,
                    occurred_at.isoformat(),
                    resolved_at.isoformat() if resolved_at else None,
                    embedding_json,
                    context_card_json,
                ),
            )
            conn.commit()

        logger.info(
            "incident_stored",
            incident_id=incident_id,
            service=service,
        )

    def update_resolution(
        self,
        incident_id: str,
        resolution: str,
        root_cause: str | None = None,
        resolved_at: datetime | None = None,
    ) -> bool:
        """
        Update resolution info for an incident.

        Returns True if incident was found and updated.
        """
        resolved_at = resolved_at or datetime.utcnow()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE incidents
                SET resolution = ?, root_cause = ?, resolved_at = ?
                WHERE incident_id = ?
                """,
                (resolution, root_cause, resolved_at.isoformat(), incident_id),
            )
            conn.commit()

            if cursor.rowcount > 0:
                logger.info("incident_resolution_updated", incident_id=incident_id)
                return True
            return False

    def get_incident(self, incident_id: str) -> PastIncident | None:
        """Get a single incident by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()

            if row:
                return self._row_to_past_incident(row)
            return None

    def get_all_with_embeddings(self) -> list[tuple[PastIncident, np.ndarray]]:
        """
        Get all incidents with their embeddings.

        Returns list of (incident, embedding) tuples.
        """
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM incidents WHERE embedding IS NOT NULL").fetchall()

        results = []
        for row in rows:
            incident = self._row_to_past_incident(row)
            embedding = np.array(json.loads(row["embedding"]))
            results.append((incident, embedding))

        return results

    def get_recent_incidents(
        self,
        limit: int = 100,
        service: str | None = None,
    ) -> list[PastIncident]:
        """Get recent incidents, optionally filtered by service."""
        with self._get_connection() as conn:
            if service:
                rows = conn.execute(
                    """
                    SELECT * FROM incidents
                    WHERE service = ?
                    ORDER BY occurred_at DESC
                    LIMIT ?
                    """,
                    (service, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM incidents
                    ORDER BY occurred_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [self._row_to_past_incident(row) for row in rows]

    def count_incidents(self) -> int:
        """Get total number of stored incidents."""
        with self._get_connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()
            return result[0] if result else 0

    def _row_to_past_incident(self, row: sqlite3.Row) -> PastIncident:
        """Convert a database row to a PastIncident model."""
        return PastIncident(
            incident_id=row["incident_id"],
            title=row["title"],
            service=row["service"],
            description=row["description"],
            root_cause=row["root_cause"],
            resolution=row["resolution"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None
            ),
        )

    def delete_incident(self, incident_id: str) -> bool:
        """Delete an incident. Returns True if deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM incidents WHERE incident_id = ?",
                (incident_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
