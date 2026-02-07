"""
Escalation Scheduler - Background tasks for scheduled escalation checks.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from .engine import PolicyEngine, get_policy_engine
from .models import EscalationState, TeamRotation
from .service import EscalationService, get_escalation_service

logger = logging.getLogger(__name__)


class EscalationScheduler:
    """Scheduler for background escalation tasks."""

    def __init__(
        self,
        service: EscalationService | None = None,
        engine: PolicyEngine | None = None,
        check_interval_seconds: int = 30,
        rotation_check_interval_seconds: int = 300,
    ):
        self.service = service or get_escalation_service()
        self.engine = engine or get_policy_engine(self.service)
        self.check_interval = check_interval_seconds
        self.rotation_check_interval = rotation_check_interval_seconds

        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._callbacks: list[Callable[[EscalationState], Awaitable[None]]] = []
        self._last_rotation_check: datetime | None = None

    def register_callback(self, callback: Callable[[EscalationState], Awaitable[None]]):
        """Register a callback to be called when escalation occurs."""
        self._callbacks.append(callback)

    async def start(self):
        """Start the scheduler background tasks."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        logger.info("Starting escalation scheduler")

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._escalation_loop()),
            asyncio.create_task(self._rotation_loop()),
            asyncio.create_task(self._cleanup_loop()),
        ]

    async def stop(self):
        """Stop the scheduler gracefully."""
        if not self._running:
            return

        logger.info("Stopping escalation scheduler")
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks = []

    async def _escalation_loop(self):
        """Main loop for checking and processing escalations."""
        while self._running:
            try:
                await self._check_escalations()
            except Exception as e:
                logger.error(f"Error in escalation loop: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_escalations(self):
        """Check and process pending escalations."""
        pending = await self.service.get_pending_escalations()

        if pending:
            logger.debug(f"Found {len(pending)} pending escalations")

        for state in pending:
            try:
                # Build context from state
                context = {
                    "incident_id": state.incident_id,
                    "current_level": state.current_level,
                    "started_at": state.started_at.isoformat(),
                    "repeat_count": state.repeat_count,
                }

                # Check if should escalate
                if await self.engine.should_escalate(state, context):
                    logger.info(f"Escalating incident {state.incident_id}")
                    await self.engine.execute_escalation(state, context)

                    # Notify callbacks
                    for callback in self._callbacks:
                        try:
                            await callback(state)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")

            except Exception as e:
                logger.error(f"Error processing {state.incident_id}: {e}")

    async def _rotation_loop(self):
        """Loop for checking and applying team rotations."""
        while self._running:
            try:
                await self._check_rotations()
            except Exception as e:
                logger.error(f"Error in rotation loop: {e}")

            await asyncio.sleep(self.rotation_check_interval)

    async def _check_rotations(self):
        """Check and apply team rotations."""
        now = datetime.utcnow()

        for team_id, rotation in self.service._rotations.items():
            if self._should_rotate(rotation, now):
                logger.info(f"Rotating on-call for team {team_id}")
                await self.service.rotate_oncall(team_id)

    def _should_rotate(self, rotation: TeamRotation, now: datetime) -> bool:
        """Determine if a rotation should occur."""
        if not rotation.members:
            return False

        if not rotation.last_rotation:
            return True

        if rotation.rotation_type == "daily":
            threshold = timedelta(days=1)
        elif rotation.rotation_type == "weekly":
            threshold = timedelta(weeks=1)
        elif rotation.rotation_type == "hourly":
            threshold = timedelta(hours=1)
        else:
            threshold = timedelta(weeks=1)

        return (now - rotation.last_rotation) >= threshold

    async def _cleanup_loop(self):
        """Loop for cleaning up old escalation states."""
        cleanup_interval = 3600  # 1 hour
        max_age_hours = 168  # 7 days

        while self._running:
            await asyncio.sleep(cleanup_interval)

            try:
                await self._cleanup_old_states(max_age_hours)
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_old_states(self, max_age_hours: int):
        """Remove old resolved escalation states."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        removed = 0

        to_remove = []
        for incident_id, state in self.service._states.items():
            if state.status.value in ("resolved", "skipped", "overridden"):
                if state.started_at < cutoff:
                    to_remove.append(incident_id)

        for incident_id in to_remove:
            del self.service._states[incident_id]
            removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} old escalation states")

    async def trigger_immediate(self, incident_id: str, context: dict | None = None):
        """Trigger immediate escalation check for a specific incident."""
        state = await self.service.get_escalation_state(incident_id)
        if not state:
            logger.warning(f"No escalation state for {incident_id}")
            return

        ctx = context or {
            "incident_id": incident_id,
            "current_level": state.current_level,
        }

        if await self.engine.should_escalate(state, ctx):
            await self.engine.execute_escalation(state, ctx)
            for callback in self._callbacks:
                try:
                    await callback(state)
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    async def get_status(self) -> dict:
        """Get scheduler status information."""
        pending = await self.service.get_pending_escalations()

        return {
            "running": self._running,
            "check_interval_seconds": self.check_interval,
            "rotation_check_interval_seconds": self.rotation_check_interval,
            "active_tasks": len([t for t in self._tasks if not t.done()]),
            "pending_escalations": len(pending),
            "registered_callbacks": len(self._callbacks),
            "last_rotation_check": (
                self._last_rotation_check.isoformat()
                if self._last_rotation_check
                else None
            ),
        }


# Global scheduler instance
_scheduler: EscalationScheduler | None = None


def get_scheduler(
    service: EscalationService | None = None,
    engine: PolicyEngine | None = None,
) -> EscalationScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = EscalationScheduler(service, engine)
    return _scheduler


async def start_scheduler():
    """Start the global scheduler."""
    scheduler = get_scheduler()
    await scheduler.start()


async def stop_scheduler():
    """Stop the global scheduler."""
    if _scheduler:
        await _scheduler.stop()
