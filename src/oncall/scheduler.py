"""Background scheduler for automatic on-call handoff generation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from ..config import Settings
from .aggregator import OnCallActivityAggregator
from .delivery import HandoffDeliveryService
from .generator import HandoffSummaryGenerator
from .routes import _HANDOFF_CONFIGS, _store_summary
from .schedule import OnCallScheduleClient

logger = structlog.get_logger()


class OnCallHandoffScheduler:
    """Periodic scheduler that auto-generates handoffs at shift boundaries."""

    def __init__(
        self,
        settings: Settings,
        poll_interval_seconds: int = 300,
    ):
        self.settings = settings
        self.poll_interval_seconds = poll_interval_seconds

        self.schedule_client = OnCallScheduleClient(settings)
        self.aggregator = OnCallActivityAggregator(settings)
        self.generator = HandoffSummaryGenerator(settings)
        self.delivery = HandoffDeliveryService(settings)

        self._running = False
        self._task: asyncio.Task | None = None
        self._generated_boundaries: set[str] = set()

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            logger.warning("oncall_handoff_scheduler_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "oncall_handoff_scheduler_started",
            poll_interval_seconds=self.poll_interval_seconds,
        )

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                # TestClient lifespans may stop on a different loop than start.
                # In that case, awaiting the task raises "attached to a different loop".
                if self._task.get_loop() is asyncio.get_running_loop():
                    await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await self.schedule_client.close()
        logger.info("oncall_handoff_scheduler_stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.check_once()
            except Exception as exc:
                logger.warning("oncall_handoff_scheduler_loop_failed", error=str(exc))

            await asyncio.sleep(self.poll_interval_seconds)

    async def check_once(self) -> int:
        """Check all enabled configs once. Returns number of generated summaries."""
        now = datetime.now(UTC)
        generated = 0

        configs = [cfg for cfg in _HANDOFF_CONFIGS.values() if cfg.enabled]
        for cfg in configs:
            try:
                shift = await self.schedule_client.detect_shift_boundary(
                    schedule_id=cfg.schedule_id,
                    reference_time=now,
                    window_hours=24,
                )
                if not shift:
                    continue

                seconds_since_boundary = (now - shift.handoff_time).total_seconds()
                if seconds_since_boundary < 0:
                    continue
                if seconds_since_boundary > cfg.grace_minutes * 60:
                    continue

                boundary_key = f"{cfg.schedule_id}:{shift.handoff_time.astimezone(UTC).isoformat()}"
                if boundary_key in self._generated_boundaries:
                    continue

                aggregate = await self.aggregator.aggregate(shift)
                summary = await self.generator.generate(aggregate)
                _store_summary(summary)

                delivery_results = await self.delivery.deliver(summary, cfg)
                summary.delivered_to = delivery_results

                self._generated_boundaries.add(boundary_key)
                generated += 1

                logger.info(
                    "oncall_handoff_auto_generated",
                    schedule_id=cfg.schedule_id,
                    handoff_time=shift.handoff_time.isoformat(),
                    handoff_id=summary.id,
                    deliveries=len(delivery_results),
                )
            except Exception as exc:
                logger.warning(
                    "oncall_handoff_auto_generation_failed",
                    schedule_id=cfg.schedule_id,
                    error=str(exc),
                )

        return generated


_scheduler: OnCallHandoffScheduler | None = None


def get_oncall_handoff_scheduler(
    settings: Settings,
    poll_interval_seconds: int = 300,
) -> OnCallHandoffScheduler:
    """Get or create singleton scheduler instance.

    Note: unit/integration tests may create multiple event loops (via TestClient).
    If a scheduler task was created on a different loop, discard it and recreate.
    """
    global _scheduler

    if _scheduler is not None and _scheduler._task is not None:
        try:
            if _scheduler._task.get_loop() is not asyncio.get_running_loop():
                _scheduler = None
        except RuntimeError:
            # No running loop in this context; keep existing.
            pass

    if _scheduler is None:
        _scheduler = OnCallHandoffScheduler(
            settings=settings,
            poll_interval_seconds=poll_interval_seconds,
        )
    return _scheduler


async def start_oncall_handoff_scheduler(
    settings: Settings,
    poll_interval_seconds: int = 300,
) -> None:
    scheduler = get_oncall_handoff_scheduler(
        settings=settings,
        poll_interval_seconds=poll_interval_seconds,
    )
    await scheduler.start()


async def stop_oncall_handoff_scheduler() -> None:
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None
