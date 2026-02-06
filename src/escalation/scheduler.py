"""Background scheduler for automatic escalation rule evaluation.

Periodically checks active incidents and applies escalation rules.
"""

import asyncio
from datetime import datetime
from typing import Any, Callable

import structlog

from .engine import EscalationEngine
from .models import EscalationResult, IncidentState

logger = structlog.get_logger()


class EscalationScheduler:
    """Background scheduler for escalation rule evaluation.

    Runs a continuous loop checking active incidents against
    escalation policies and rules.
    """

    def __init__(
        self,
        engine: EscalationEngine,
        check_interval_seconds: int = 60,
        batch_size: int = 100,
    ):
        """Initialize the scheduler.

        Args:
            engine: The escalation engine to use
            check_interval_seconds: How often to check incidents (default 60s)
            batch_size: Maximum incidents to process per check
        """
        self.engine = engine
        self.check_interval = check_interval_seconds
        self.batch_size = batch_size
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_check: datetime | None = None
        self._checks_completed = 0
        self._escalations_triggered = 0
        self._errors = 0
        self._callbacks: list[Callable] = []

    async def start(self) -> None:
        """Start the background scheduler."""
        if self._running:
            logger.warning("escalation_scheduler_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "escalation_scheduler_started",
            check_interval=self.check_interval,
            batch_size=self.batch_size,
        )

    async def stop(self) -> None:
        """Stop the background scheduler."""
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

        logger.info(
            "escalation_scheduler_stopped",
            checks_completed=self._checks_completed,
            escalations_triggered=self._escalations_triggered,
        )

    def on_escalation(self, callback: Callable) -> None:
        """Register callback for escalation events.

        Callback signature: async def callback(incident: IncidentState, result: EscalationResult)
        """
        self._callbacks.append(callback)

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_incidents()
                self._checks_completed += 1
                self._last_check = datetime.utcnow()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._errors += 1
                logger.error(
                    "escalation_scheduler_error",
                    error=str(e),
                    checks_completed=self._checks_completed,
                )

            # Wait for next check interval
            if self._running:
                await asyncio.sleep(self.check_interval)

    async def _check_incidents(self) -> None:
        """Check all active incidents for escalation."""
        # Get active incidents from the engine's store
        incidents = await self.engine.store.list_active_incidents(
            limit=self.batch_size
        )

        if not incidents:
            logger.debug("escalation_scheduler_no_active_incidents")
            return

        logger.debug(
            "escalation_scheduler_checking_incidents",
            count=len(incidents),
        )

        # Evaluate each incident
        results: list[tuple[IncidentState, EscalationResult]] = []
        for incident in incidents:
            try:
                result = await self.engine.evaluate_incident(incident)
                if result.triggered:
                    results.append((incident, result))
                    self._escalations_triggered += 1
            except Exception as e:
                logger.warning(
                    "escalation_evaluation_failed",
                    incident_id=incident.incident_id,
                    error=str(e),
                )

        # Call registered callbacks
        for incident, result in results:
            for callback in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(incident, result)
                    else:
                        callback(incident, result)
                except Exception as e:
                    logger.error(
                        "escalation_callback_error",
                        error=str(e),
                    )

        if results:
            logger.info(
                "escalation_scheduler_check_complete",
                incidents_checked=len(incidents),
                escalations_triggered=len(results),
            )

    async def check_now(self) -> int:
        """Manually trigger an escalation check.

        Returns:
            Number of escalations triggered
        """
        triggered_before = self._escalations_triggered
        await self._check_incidents()
        return self._escalations_triggered - triggered_before

    def get_stats(self) -> dict[str, Any]:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "check_interval_seconds": self.check_interval,
            "batch_size": self.batch_size,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "checks_completed": self._checks_completed,
            "escalations_triggered": self._escalations_triggered,
            "errors": self._errors,
        }


class IncidentWatcher:
    """Watches for incident state changes and triggers immediate evaluation.

    Use this for real-time escalation triggering when incidents are
    created, acknowledged, or updated.
    """

    def __init__(self, engine: EscalationEngine):
        self.engine = engine
        self._callbacks: list[Callable] = []

    def on_escalation(self, callback: Callable) -> None:
        """Register callback for escalation events."""
        self._callbacks.append(callback)

    async def on_incident_created(self, incident: IncidentState) -> EscalationResult:
        """Handle new incident creation.

        Called when a new incident is created to check for immediate escalation.
        """
        logger.info(
            "incident_watcher_new_incident",
            incident_id=incident.incident_id,
            service=incident.service,
            severity=incident.severity,
        )

        result = await self.engine.evaluate_incident(incident)
        await self._emit_if_triggered(incident, result)
        return result

    async def on_incident_acknowledged(
        self, incident: IncidentState
    ) -> EscalationResult:
        """Handle incident acknowledgment.

        Updates the incident state and re-evaluates escalation.
        """
        logger.info(
            "incident_watcher_acknowledged",
            incident_id=incident.incident_id,
        )

        # Update state to acknowledged
        incident.acknowledged_at = datetime.utcnow()
        incident.last_activity_at = datetime.utcnow()

        result = await self.engine.evaluate_incident(incident)
        await self._emit_if_triggered(incident, result)
        return result

    async def on_incident_resolved(self, incident: IncidentState) -> None:
        """Handle incident resolution.

        Updates the incident state - no further escalation needed.
        """
        logger.info(
            "incident_watcher_resolved",
            incident_id=incident.incident_id,
        )

        incident.resolved_at = datetime.utcnow()
        incident.last_activity_at = datetime.utcnow()
        await self.engine.store.store_incident_state(incident)

    async def on_incident_updated(
        self, incident: IncidentState
    ) -> EscalationResult:
        """Handle incident update (activity recorded).

        Updates last activity time and re-evaluates.
        """
        incident.last_activity_at = datetime.utcnow()
        result = await self.engine.evaluate_incident(incident)
        await self._emit_if_triggered(incident, result)
        return result

    async def _emit_if_triggered(
        self, incident: IncidentState, result: EscalationResult
    ) -> None:
        """Emit callbacks if escalation was triggered."""
        if not result.triggered:
            return

        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(incident, result)
                else:
                    callback(incident, result)
            except Exception as e:
                logger.error("incident_watcher_callback_error", error=str(e))


class CompositeScheduler:
    """Combines periodic scheduling with real-time incident watching.

    Use this for production deployments where you want both:
    - Background periodic checks (catch any missed escalations)
    - Real-time evaluation on incident events
    """

    def __init__(
        self,
        engine: EscalationEngine,
        check_interval_seconds: int = 60,
        batch_size: int = 100,
    ):
        self.engine = engine
        self.scheduler = EscalationScheduler(
            engine,
            check_interval_seconds=check_interval_seconds,
            batch_size=batch_size,
        )
        self.watcher = IncidentWatcher(engine)
        self._callbacks: list[Callable] = []

    def on_escalation(self, callback: Callable) -> None:
        """Register callback for escalation events from both scheduler and watcher."""
        self._callbacks.append(callback)
        self.scheduler.on_escalation(callback)
        self.watcher.on_escalation(callback)

    async def start(self) -> None:
        """Start the background scheduler."""
        await self.scheduler.start()
        logger.info("composite_scheduler_started")

    async def stop(self) -> None:
        """Stop the background scheduler."""
        await self.scheduler.stop()
        logger.info("composite_scheduler_stopped")

    async def on_incident_created(self, incident: IncidentState) -> EscalationResult:
        """Handle new incident - immediate evaluation."""
        return await self.watcher.on_incident_created(incident)

    async def on_incident_acknowledged(
        self, incident: IncidentState
    ) -> EscalationResult:
        """Handle incident acknowledgment."""
        return await self.watcher.on_incident_acknowledged(incident)

    async def on_incident_resolved(self, incident: IncidentState) -> None:
        """Handle incident resolution."""
        await self.watcher.on_incident_resolved(incident)

    async def on_incident_updated(
        self, incident: IncidentState
    ) -> EscalationResult:
        """Handle incident update."""
        return await self.watcher.on_incident_updated(incident)

    def get_stats(self) -> dict[str, Any]:
        """Get combined statistics."""
        return {
            **self.scheduler.get_stats(),
            "type": "composite",
        }


# Default scheduler instance
_scheduler_instance: EscalationScheduler | None = None


async def get_escalation_scheduler(
    engine: EscalationEngine,
    check_interval_seconds: int = 60,
) -> EscalationScheduler:
    """Get or create the global escalation scheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = EscalationScheduler(
            engine,
            check_interval_seconds=check_interval_seconds,
        )
    return _scheduler_instance


async def shutdown_escalation_scheduler() -> None:
    """Shutdown the global escalation scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        await _scheduler_instance.stop()
        _scheduler_instance = None
