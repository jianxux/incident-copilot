"""Incident memory health checks and alerts."""

from __future__ import annotations

from datetime import datetime, timedelta

import asyncpg
import structlog
from pydantic import BaseModel, Field

from ..config import Settings
from .config import IncidentMemoryConfig

logger = structlog.get_logger()


class MemoryHealthAlert(BaseModel):
    """A single memory health alert."""

    code: str
    severity: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class MemoryHealthReport(BaseModel):
    """Incident memory health summary and alerts."""

    status: str
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    total_records: int
    recall_hit_rate: float | None = None
    stale_days: int | None = None
    alerts: list[MemoryHealthAlert] = Field(default_factory=list)


class MemoryHealthChecker:
    """Evaluate memory quality and coverage health."""

    def __init__(
        self,
        settings: Settings,
        config: IncidentMemoryConfig | None = None,
        pool: asyncpg.Pool | None = None,
    ):
        self.settings = settings
        self.config = config or IncidentMemoryConfig.from_settings(settings)
        self.database_url = self.config.database_url
        self._pool = pool

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url.replace("+asyncpg", ""),
                min_size=1,
                max_size=10,
            )

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def check(
        self,
        min_recall_hit_rate: float = 0.35,
        stale_after_days: int = 14,
    ) -> MemoryHealthReport:
        pool = await self._ensure_pool()
        alerts: list[MemoryHealthAlert] = []

        total_records = int(
            await pool.fetchval(
                f"SELECT COUNT(*) FROM {self.config.table_name}"  # nosec B608
            )
            or 0
        )

        latest_created_at = await pool.fetchval(
            f"SELECT MAX(created_at) FROM {self.config.table_name}"  # nosec B608
        )

        stale_days: int | None = None
        if latest_created_at is not None:
            stale_days = max(
                (datetime.utcnow() - latest_created_at.replace(tzinfo=None)).days, 0
            )

        recall_hit_rate = await self._recall_hit_rate(pool)

        if total_records == 0:
            alerts.append(
                MemoryHealthAlert(
                    code="NO_MEMORY_RECORDS",
                    severity="critical",
                    message="Incident memory has no captured incidents.",
                )
            )

        if stale_days is not None and stale_days >= stale_after_days:
            alerts.append(
                MemoryHealthAlert(
                    code="STALE_MEMORY",
                    severity="warning",
                    message="Incident memory has not been updated recently.",
                    details={
                        "stale_days": stale_days,
                        "threshold_days": stale_after_days,
                    },
                )
            )

        if recall_hit_rate is not None and recall_hit_rate < min_recall_hit_rate:
            alerts.append(
                MemoryHealthAlert(
                    code="LOW_RECALL_HIT_RATE",
                    severity="warning",
                    message="Recall hit rate is below the configured threshold.",
                    details={
                        "recall_hit_rate": recall_hit_rate,
                        "threshold": min_recall_hit_rate,
                    },
                )
            )

        missing_services = await self._missing_services(pool)
        if missing_services:
            alerts.append(
                MemoryHealthAlert(
                    code="SERVICES_WITHOUT_MEMORY",
                    severity="info",
                    message="Some configured services have no incident memory yet.",
                    details={
                        "services": missing_services,
                        "count": len(missing_services),
                    },
                )
            )

        status = "healthy"
        if any(alert.severity == "critical" for alert in alerts):
            status = "critical"
        elif any(alert.severity == "warning" for alert in alerts):
            status = "warning"

        report = MemoryHealthReport(
            status=status,
            total_records=total_records,
            recall_hit_rate=recall_hit_rate,
            stale_days=stale_days,
            alerts=alerts,
        )

        logger.info(
            "incident_memory_health_checked",
            status=report.status,
            total_records=total_records,
            alerts=len(alerts),
        )
        return report

    async def _recall_hit_rate(self, pool: asyncpg.Pool) -> float | None:
        window_start = datetime.utcnow() - timedelta(days=30)
        try:
            total_feedback = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM incident_memory_feedback
                WHERE created_at >= $1
                """,
                window_start,
            )
        except Exception as exc:
            logger.warning("incident_memory_feedback_table_unavailable", error=str(exc))
            return None

        if total_feedback is None or int(total_feedback) == 0:
            return None

        helpful = await pool.fetchval(
            """
            SELECT COUNT(*)
            FROM incident_memory_feedback
            WHERE created_at >= $1
              AND feedback IN ('helpful', 'partial')
            """,
            window_start,
        )
        return round(float(helpful or 0) / float(total_feedback), 4)

    async def _missing_services(self, pool: asyncpg.Pool) -> list[str]:
        configured = set(self.settings.service_repo_map.keys()) | set(
            self.settings.oncall_schedule_map.keys()
        )
        if not configured:
            return []

        rows = await pool.fetch(
            f"""  # nosec B608
            SELECT DISTINCT UNNEST(services_affected) AS service
            FROM {self.config.table_name}
            WHERE array_length(services_affected, 1) > 0
            """
        )
        observed = {str(row["service"]) for row in rows}
        return sorted(list(configured - observed))

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            await self.connect()
        assert self._pool is not None
        return self._pool
