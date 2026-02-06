"""Update scheduler for periodic communication reminders.

Provides:
- Scheduled update reminders ("You haven't posted an update in 15 mins")
- Automatic reminder escalation
- Configurable reminder intervals per incident
"""

import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable

import structlog
from pydantic import BaseModel, Field

from .models import (
    CommunicationPlan,
    DeliveryChannel,
    ScheduledReminder,
    UpdatePriority,
)

logger = structlog.get_logger()


class UpdateReminder(BaseModel):
    """A reminder notification to post an update."""

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(12))
    incident_id: str
    plan_id: str | None = None

    # Reminder content
    message: str
    minutes_since_update: int

    # Delivery
    channels: list[DeliveryChannel] = Field(default_factory=list)
    recipient_ids: list[str] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None


class UpdateScheduler:
    """Scheduler for periodic update reminders during incidents.

    Monitors active incidents and sends reminders when updates are overdue.
    """

    def __init__(
        self,
        check_interval_seconds: int = 60,
    ) -> None:
        self._check_interval = check_interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None

        # Active communication plans being monitored
        self._plans: dict[str, CommunicationPlan] = {}

        # Reminder history
        self._reminders: list[UpdateReminder] = []

        # Callbacks
        self._reminder_callbacks: list[Callable[[UpdateReminder], Any]] = []

        # Stats
        self._stats = {
            "reminders_sent": 0,
            "checks_performed": 0,
            "last_check_at": None,
        }

    async def start(self) -> None:
        """Start the reminder scheduler."""
        if self._running:
            logger.warning("scheduler_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("update_scheduler_started", interval=self._check_interval)

    async def stop(self) -> None:
        """Stop the reminder scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("update_scheduler_stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self.check_and_send_reminders()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scheduler_error", error=str(e))
                await asyncio.sleep(self._check_interval)

    async def check_and_send_reminders(self) -> int:
        """Check all plans and send reminders as needed.

        Returns the number of reminders sent.
        """
        self._stats["checks_performed"] += 1
        self._stats["last_check_at"] = datetime.utcnow()

        reminders_sent = 0

        for plan_id, plan in list(self._plans.items()):
            if not plan.is_active or not plan.auto_reminder_enabled:
                continue

            if plan.needs_update_reminder:
                reminder = await self._create_reminder(plan)
                if reminder:
                    await self._send_reminder(reminder)
                    reminders_sent += 1

        return reminders_sent

    async def _create_reminder(self, plan: CommunicationPlan) -> UpdateReminder | None:
        """Create a reminder for a plan."""
        minutes = plan.minutes_since_last_update
        if minutes is None:
            # Calculate from creation time
            delta = datetime.utcnow() - plan.created_at
            minutes = int(delta.total_seconds() / 60)

        # Get notification channels and recipients from plan's reminders config
        channels = [DeliveryChannel.SLACK]
        recipient_ids: list[str] = []

        for reminder_config in plan.reminders:
            if reminder_config.is_active:
                channels = list(set(channels + list(reminder_config.notify_channels)))
                recipient_ids = list(
                    set(recipient_ids + reminder_config.notify_user_ids)
                )

        message = f"⏰ Reminder: You haven't posted an update for incident '{plan.incident_title}' in {int(minutes)} minutes."

        return UpdateReminder(
            incident_id=plan.incident_id,
            plan_id=plan.id,
            message=message,
            minutes_since_update=int(minutes),
            channels=channels,
            recipient_ids=recipient_ids,
        )

    async def _send_reminder(self, reminder: UpdateReminder) -> None:
        """Send a reminder notification."""
        self._reminders.append(reminder)
        self._stats["reminders_sent"] += 1

        logger.info(
            "update_reminder_sent",
            incident_id=reminder.incident_id,
            plan_id=reminder.plan_id,
            minutes=reminder.minutes_since_update,
        )

        # Notify callbacks
        for callback in self._reminder_callbacks:
            try:
                result = callback(reminder)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("reminder_callback_error", error=str(e))

    def on_reminder(self, callback: Callable[[UpdateReminder], Any]) -> None:
        """Register a callback for reminder events."""
        self._reminder_callbacks.append(callback)

    # ========================================================================
    # Plan Management
    # ========================================================================

    async def register_plan(self, plan: CommunicationPlan) -> None:
        """Register a communication plan for monitoring."""
        self._plans[plan.id] = plan
        logger.info(
            "plan_registered_for_reminders",
            plan_id=plan.id,
            incident_id=plan.incident_id,
            interval_minutes=plan.auto_reminder_interval_minutes,
        )

    async def unregister_plan(self, plan_id: str) -> None:
        """Unregister a plan from monitoring."""
        if plan_id in self._plans:
            del self._plans[plan_id]
            logger.info("plan_unregistered_from_reminders", plan_id=plan_id)

    async def update_plan(self, plan: CommunicationPlan) -> None:
        """Update a registered plan."""
        if plan.id in self._plans:
            self._plans[plan.id] = plan
            logger.debug("plan_updated_in_scheduler", plan_id=plan.id)

    async def record_update_sent(self, plan_id: str) -> None:
        """Record that an update was sent for a plan (resets reminder timer)."""
        if plan_id in self._plans:
            self._plans[plan_id].last_update_at = datetime.utcnow()
            self._plans[plan_id].total_updates_sent += 1
            logger.debug("update_recorded", plan_id=plan_id)

    async def get_plan(self, plan_id: str) -> CommunicationPlan | None:
        """Get a registered plan."""
        return self._plans.get(plan_id)

    async def list_active_plans(self) -> list[CommunicationPlan]:
        """List all active plans being monitored."""
        return [p for p in self._plans.values() if p.is_active]

    # ========================================================================
    # Scheduled Reminders Configuration
    # ========================================================================

    async def add_reminder_config(
        self,
        plan_id: str,
        interval_minutes: int = 15,
        message: str | None = None,
        notify_channels: list[DeliveryChannel] | None = None,
        notify_user_ids: list[str] | None = None,
    ) -> ScheduledReminder | None:
        """Add a reminder configuration to a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return None

        reminder = ScheduledReminder(
            incident_id=plan.incident_id,
            plan_id=plan_id,
            interval_minutes=interval_minutes,
            message=message or f"You haven't posted an update in {{minutes}} minutes",
            notify_channels=notify_channels or [DeliveryChannel.SLACK],
            notify_user_ids=notify_user_ids or [],
        )

        plan.reminders.append(reminder)
        self._plans[plan_id] = plan

        logger.info(
            "reminder_config_added",
            plan_id=plan_id,
            interval_minutes=interval_minutes,
        )

        return reminder

    async def remove_reminder_config(self, plan_id: str, reminder_id: str) -> bool:
        """Remove a reminder configuration from a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return False

        original_count = len(plan.reminders)
        plan.reminders = [r for r in plan.reminders if r.id != reminder_id]

        if len(plan.reminders) < original_count:
            self._plans[plan_id] = plan
            logger.info("reminder_config_removed", plan_id=plan_id, reminder_id=reminder_id)
            return True

        return False

    async def pause_reminders(self, plan_id: str) -> bool:
        """Pause reminders for a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return False

        plan.auto_reminder_enabled = False
        self._plans[plan_id] = plan
        logger.info("reminders_paused", plan_id=plan_id)
        return True

    async def resume_reminders(self, plan_id: str) -> bool:
        """Resume reminders for a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return False

        plan.auto_reminder_enabled = True
        # Reset the last update time to now to avoid immediate reminder
        plan.last_update_at = datetime.utcnow()
        self._plans[plan_id] = plan
        logger.info("reminders_resumed", plan_id=plan_id)
        return True

    async def set_reminder_interval(self, plan_id: str, interval_minutes: int) -> bool:
        """Update the reminder interval for a plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            return False

        plan.auto_reminder_interval_minutes = interval_minutes
        self._plans[plan_id] = plan
        logger.info(
            "reminder_interval_updated",
            plan_id=plan_id,
            interval_minutes=interval_minutes,
        )
        return True

    # ========================================================================
    # Reminder History
    # ========================================================================

    async def get_reminder_history(
        self,
        incident_id: str | None = None,
        plan_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[UpdateReminder], int]:
        """Get reminder history with optional filters."""
        reminders = self._reminders.copy()

        if incident_id:
            reminders = [r for r in reminders if r.incident_id == incident_id]

        if plan_id:
            reminders = [r for r in reminders if r.plan_id == plan_id]

        # Sort by creation time descending
        reminders.sort(key=lambda r: r.created_at, reverse=True)

        total = len(reminders)
        reminders = reminders[offset:offset + limit]

        return reminders, total

    async def acknowledge_reminder(
        self, reminder_id: str, user_id: str
    ) -> UpdateReminder | None:
        """Mark a reminder as acknowledged."""
        for reminder in self._reminders:
            if reminder.id == reminder_id:
                reminder.acknowledged_at = datetime.utcnow()
                reminder.acknowledged_by = user_id
                logger.info(
                    "reminder_acknowledged",
                    reminder_id=reminder_id,
                    user_id=user_id,
                )
                return reminder
        return None

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_stats(self) -> dict:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "check_interval_seconds": self._check_interval,
            "active_plans": len(self._plans),
            "total_reminders_sent": self._stats["reminders_sent"],
            "checks_performed": self._stats["checks_performed"],
            "last_check_at": self._stats["last_check_at"],
        }

    async def get_overdue_plans(self) -> list[CommunicationPlan]:
        """Get all plans that are overdue for an update."""
        overdue = []
        for plan in self._plans.values():
            if plan.is_active and plan.needs_update_reminder:
                overdue.append(plan)
        return overdue


# Singleton instance
_scheduler: UpdateScheduler | None = None


async def get_update_scheduler() -> UpdateScheduler:
    """Get the singleton update scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = UpdateScheduler()
    return _scheduler
