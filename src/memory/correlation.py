"""Cross-service failure correlation for incident memory."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from itertools import combinations

import structlog

from .config import IncidentMemoryConfig
from .models import ServiceCorrelation
from .store import IncidentMemoryStore

logger = structlog.get_logger()


class ServiceCorrelationEngine:
    """Build and query service co-failure correlations."""

    def __init__(self, store: IncidentMemoryStore, config: IncidentMemoryConfig):
        self.store = store
        self.config = config

    async def rebuild(self) -> int:
        """Rebuild correlation table from incident_memory history."""
        pool = await self.store._ensure_pool()

        since = datetime.now(UTC) - timedelta(
            days=self.config.correlation_lookback_days
        )
        rows = await pool.fetch(
            f"""  # nosec B608
            SELECT id, created_at, services_affected
            FROM {self.config.table_name}
            WHERE created_at >= $1
              AND array_length(services_affected, 1) > 0
            ORDER BY created_at ASC
            """,
            since,
        )

        service_counts: dict[str, int] = defaultdict(int)
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        pair_timestamps: dict[tuple[str, str], list[datetime]] = defaultdict(list)

        for row in rows:
            services_raw = row.get("services_affected")
            if not isinstance(services_raw, list):
                continue

            normalized = sorted(
                {str(item).strip() for item in services_raw if str(item).strip()}
            )
            if not normalized:
                continue

            for service in normalized:
                service_counts[service] += 1

            created_at = row["created_at"]
            if not isinstance(created_at, datetime):
                continue

            for service_a, service_b in combinations(normalized, 2):
                key = (service_a, service_b)
                pair_counts[key] += 1
                pair_timestamps[key].append(created_at)

        correlations: list[ServiceCorrelation] = []
        for (service_a, service_b), count in pair_counts.items():
            if count < self.config.correlation_min_cooccurrence:
                continue

            timestamps = sorted(pair_timestamps[(service_a, service_b)])
            avg_gap = _avg_gap_minutes(timestamps)
            denominator = max(
                1, min(service_counts[service_a], service_counts[service_b])
            )
            confidence = min(1.0, round(count / denominator, 4))

            correlations.append(
                ServiceCorrelation(
                    service_a=service_a,
                    service_b=service_b,
                    co_occurrence_count=count,
                    avg_time_gap_minutes=round(avg_gap, 3),
                    confidence=confidence,
                )
            )

        correlations.sort(
            key=lambda item: (item.confidence, item.co_occurrence_count),
            reverse=True,
        )
        correlations = correlations[: self.config.correlation_max_pairs]

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"TRUNCATE TABLE {self.config.correlations_table_name}"  # nosec B608
                )
                if correlations:
                    await conn.executemany(
                        f"""  # nosec B608
                        INSERT INTO {self.config.correlations_table_name} (
                            service_a,
                            service_b,
                            co_occurrence_count,
                            avg_time_gap_minutes,
                            confidence,
                            updated_at
                        ) VALUES ($1, $2, $3, $4, $5, NOW())
                        """,
                        [
                            (
                                item.service_a,
                                item.service_b,
                                item.co_occurrence_count,
                                item.avg_time_gap_minutes,
                                item.confidence,
                            )
                            for item in correlations
                        ],
                    )

        logger.info(
            "memory_service_correlations_rebuilt",
            total=len(correlations),
            lookback_days=self.config.correlation_lookback_days,
        )
        return len(correlations)

    async def get_for_service(
        self,
        service: str,
        limit: int = 20,
    ) -> list[ServiceCorrelation]:
        """Get correlation rows for one service."""
        pool = await self.store._ensure_pool()
        rows = await pool.fetch(
            f"""  # nosec B608
            SELECT
                service_a,
                service_b,
                co_occurrence_count,
                avg_time_gap_minutes,
                confidence
            FROM {self.config.correlations_table_name}
            WHERE service_a = $1 OR service_b = $1
            ORDER BY confidence DESC, co_occurrence_count DESC
            LIMIT $2
            """,
            service,
            limit,
        )

        return [
            ServiceCorrelation(
                service_a=str(row["service_a"]),
                service_b=str(row["service_b"]),
                co_occurrence_count=int(row["co_occurrence_count"]),
                avg_time_gap_minutes=float(row["avg_time_gap_minutes"]),
                confidence=float(row["confidence"]),
            )
            for row in rows
        ]


class ServiceCorrelationScheduler:
    """Periodic background rebuild for service correlations."""

    def __init__(
        self,
        engine: ServiceCorrelationEngine,
        interval_seconds: int,
    ):
        self.engine = engine
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "memory_service_correlation_scheduler_started",
            interval_seconds=self.interval_seconds,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("memory_service_correlation_scheduler_stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.engine.rebuild()
            except Exception as exc:
                logger.warning(
                    "memory_service_correlations_rebuild_failed",
                    error=str(exc),
                )
            await asyncio.sleep(self.interval_seconds)


def _avg_gap_minutes(timestamps: list[datetime]) -> float:
    if len(timestamps) <= 1:
        return 0.0
    gaps: list[float] = []
    for previous, current in zip(timestamps[:-1], timestamps[1:]):
        gap = max((current - previous).total_seconds() / 60.0, 0.0)
        gaps.append(gap)
    if not gaps:
        return 0.0
    return sum(gaps) / len(gaps)
