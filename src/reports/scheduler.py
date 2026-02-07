"""Report scheduler with cron expression support."""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

import structlog

from .models import ReportConfig, ReportSchedule, ReportStatus
from .store import report_store

logger = structlog.get_logger()


class CronExpression:
    """
    Parser and evaluator for cron expressions.

    Supports standard 5-field cron format:
    minute hour day_of_month month day_of_week

    Examples:
    - "0 9 * * 1" = Every Monday at 9am
    - "0 0 1 * *" = First day of every month at midnight
    - "*/15 * * * *" = Every 15 minutes
    - "0 9-17 * * 1-5" = Every hour 9am-5pm on weekdays
    """

    FIELD_RANGES = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day_of_month": (1, 31),
        "month": (1, 12),
        "day_of_week": (0, 6),  # 0 = Sunday
    }

    DAY_NAMES = {
        "sun": 0,
        "mon": 1,
        "tue": 2,
        "wed": 3,
        "thu": 4,
        "fri": 5,
        "sat": 6,
    }

    MONTH_NAMES = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    def __init__(self, expression: str):
        self.expression = expression.strip()
        self.fields = self._parse(self.expression)

    def _parse(self, expression: str) -> dict[str, set[int]]:
        """Parse cron expression into field value sets."""
        parts = expression.lower().split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression: expected 5 fields, got {len(parts)}"
            )

        field_names = ["minute", "hour", "day_of_month", "month", "day_of_week"]
        fields = {}

        for i, (name, value) in enumerate(zip(field_names, parts)):
            min_val, max_val = self.FIELD_RANGES[name]

            # Handle day/month names
            if name == "day_of_week":
                for day_name, day_num in self.DAY_NAMES.items():
                    value = value.replace(day_name, str(day_num))
            elif name == "month":
                for month_name, month_num in self.MONTH_NAMES.items():
                    value = value.replace(month_name, str(month_num))

            fields[name] = self._parse_field(value, min_val, max_val)

        return fields

    def _parse_field(self, value: str, min_val: int, max_val: int) -> set[int]:
        """Parse a single cron field into a set of valid values."""
        result = set()

        for part in value.split(","):
            # Handle step values (e.g., */5, 1-10/2)
            step = 1
            if "/" in part:
                part, step_str = part.split("/")
                step = int(step_str)

            # Handle wildcard
            if part == "*":
                result.update(range(min_val, max_val + 1, step))
            # Handle range (e.g., 1-5)
            elif "-" in part:
                start, end = map(int, part.split("-"))
                start = max(start, min_val)
                end = min(end, max_val)
                result.update(range(start, end + 1, step))
            # Handle single value
            else:
                val = int(part)
                if min_val <= val <= max_val:
                    result.add(val)

        return result

    def matches(self, dt: datetime) -> bool:
        """Check if a datetime matches this cron expression."""
        return (
            dt.minute in self.fields["minute"]
            and dt.hour in self.fields["hour"]
            and dt.day in self.fields["day_of_month"]
            and dt.month in self.fields["month"]
            and dt.weekday() in self._convert_weekday(self.fields["day_of_week"])
        )

    def _convert_weekday(self, cron_days: set[int]) -> set[int]:
        """Convert cron weekday (0=Sun) to Python weekday (0=Mon)."""
        python_days = set()
        for day in cron_days:
            if day == 0:  # Sunday
                python_days.add(6)
            else:
                python_days.add(day - 1)
        return python_days

    def next_run(self, after: datetime | None = None) -> datetime:
        """Calculate the next run time after a given datetime."""
        if after is None:
            after = datetime.utcnow()

        # Start from the next minute
        current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Search for next matching time (limit to 1 year to prevent infinite loop)
        max_iterations = 60 * 24 * 366  # ~1 year of minutes
        for _ in range(max_iterations):
            if self.matches(current):
                return current
            current += timedelta(minutes=1)

        raise ValueError(
            f"Could not find next run time for expression: {self.expression}"
        )

    @staticmethod
    def validate(expression: str) -> tuple[bool, str | None]:
        """Validate a cron expression."""
        try:
            CronExpression(expression)
            return True, None
        except ValueError as e:
            return False, str(e)


class ReportScheduler:
    """
    Scheduler service for managing scheduled reports.

    Handles cron scheduling, timezone conversion, and report triggering.
    """

    def __init__(self, run_callback: Callable | None = None):
        """
        Initialize the scheduler.

        Args:
            run_callback: Async callback to invoke when a report should run.
                         Signature: async def callback(config: ReportConfig) -> None
        """
        self.store = report_store
        self.run_callback = run_callback
        self._running = False
        self._task: asyncio.Task | None = None
        self._check_interval = 60  # Check every minute

    async def start(self) -> None:
        """Start the scheduler background task."""
        if self._running:
            logger.warning("scheduler_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("scheduler_started")

    async def stop(self) -> None:
        """Stop the scheduler background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("scheduler_stopped")

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_schedules()
            except Exception as e:
                logger.error("scheduler_check_error", error=str(e))

            await asyncio.sleep(self._check_interval)

    async def _check_schedules(self) -> None:
        """Check all active schedules and trigger due reports."""
        now = datetime.utcnow()
        active_configs = await self.store.get_active_configs()

        for config in active_configs:
            try:
                if await self._should_run(config, now):
                    await self._trigger_report(config, now)
            except Exception as e:
                logger.error(
                    "schedule_check_failed",
                    config_id=config.id,
                    error=str(e),
                )

    async def _should_run(self, config: ReportConfig, now: datetime) -> bool:
        """Check if a report should run now."""
        schedule = config.schedule

        # Convert now to the schedule's timezone
        tz = ZoneInfo(schedule.timezone)
        now_tz = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)

        # Check if next_run_at is set and due
        if schedule.next_run_at:
            next_run_tz = schedule.next_run_at.replace(
                tzinfo=ZoneInfo("UTC")
            ).astimezone(tz)
            if now_tz >= next_run_tz:
                # Check for holiday skip
                if schedule.skip_holidays and self._is_holiday(
                    now_tz, schedule.holiday_calendar
                ):
                    logger.info(
                        "skipping_holiday",
                        config_id=config.id,
                        date=now_tz.date().isoformat(),
                    )
                    # Update next run time
                    await self._update_next_run(config)
                    return False
                return True

        return False

    def _is_holiday(self, dt: datetime, calendar: str | None) -> bool:
        """
        Check if a date is a holiday.

        This is a simple implementation - in production, you'd use
        a library like 'holidays' or an external API.
        """
        if not calendar:
            return False

        # Simplified US holiday check
        if calendar.upper() == "US":
            us_holidays = [
                (1, 1),  # New Year's Day
                (7, 4),  # Independence Day
                (12, 25),  # Christmas
            ]
            return (dt.month, dt.day) in us_holidays

        return False

    async def _trigger_report(self, config: ReportConfig, now: datetime) -> None:
        """Trigger a report run."""
        logger.info(
            "triggering_scheduled_report",
            config_id=config.id,
            name=config.name,
        )

        # Update last run time
        await self.store.update_schedule(config.id, last_run_at=now)

        # Calculate and set next run time
        await self._update_next_run(config)

        # Invoke the callback if set
        if self.run_callback:
            try:
                await self.run_callback(config)
            except Exception as e:
                logger.error(
                    "report_trigger_failed",
                    config_id=config.id,
                    error=str(e),
                )

    async def _update_next_run(self, config: ReportConfig) -> None:
        """Calculate and update the next run time for a config."""
        try:
            cron = CronExpression(config.schedule.cron_expression)
            tz = ZoneInfo(config.schedule.timezone)

            # Calculate next run in the schedule's timezone
            now_tz = datetime.now(tz)
            next_run_tz = cron.next_run(now_tz)

            # Convert back to UTC for storage
            next_run_utc = next_run_tz.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            await self.store.update_schedule(config.id, next_run_at=next_run_utc)

            logger.debug(
                "updated_next_run",
                config_id=config.id,
                next_run=next_run_utc.isoformat(),
            )
        except Exception as e:
            logger.error(
                "update_next_run_failed",
                config_id=config.id,
                error=str(e),
            )

    async def schedule_report(self, config: ReportConfig) -> ReportConfig:
        """
        Add or update a report schedule.

        Calculates the initial next_run_at time.
        """
        # Calculate initial next run time
        try:
            cron = CronExpression(config.schedule.cron_expression)
            tz = ZoneInfo(config.schedule.timezone)
            now_tz = datetime.now(tz)
            next_run_tz = cron.next_run(now_tz)
            next_run_utc = next_run_tz.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            config.schedule.next_run_at = next_run_utc
        except Exception as e:
            logger.error(
                "schedule_calculation_failed",
                config_id=config.id,
                error=str(e),
            )

        # Save to store
        await self.store.save_config(config)

        logger.info(
            "report_scheduled",
            config_id=config.id,
            name=config.name,
            cron=config.schedule.cron_expression,
            next_run=(
                config.schedule.next_run_at.isoformat()
                if config.schedule.next_run_at
                else None
            ),
        )

        return config

    async def unschedule_report(self, config_id: str) -> bool:
        """Remove a report from the schedule."""
        result = await self.store.delete_config(config_id)
        if result:
            logger.info("report_unscheduled", config_id=config_id)
        return result

    async def pause_report(self, config_id: str) -> ReportConfig | None:
        """Pause a scheduled report."""
        config = await self.store.update_config_status(config_id, ReportStatus.PAUSED)
        if config:
            logger.info("report_paused", config_id=config_id)
        return config

    async def resume_report(self, config_id: str) -> ReportConfig | None:
        """Resume a paused report."""
        config = await self.store.get_config(config_id)
        if not config:
            return None

        # Recalculate next run time
        config.status = ReportStatus.ACTIVE
        await self._update_next_run(config)
        await self.store.save_config(config)

        logger.info("report_resumed", config_id=config_id)
        return config

    async def get_upcoming_runs(
        self,
        hours: int = 24,
        limit: int = 10,
    ) -> list[tuple[ReportConfig, datetime]]:
        """Get upcoming scheduled report runs."""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)

        active_configs = await self.store.get_active_configs()
        upcoming = []

        for config in active_configs:
            if config.schedule.next_run_at and config.schedule.next_run_at <= cutoff:
                upcoming.append((config, config.schedule.next_run_at))

        # Sort by next run time
        upcoming.sort(key=lambda x: x[1])
        return upcoming[:limit]

    async def get_schedule_status(self) -> dict:
        """Get overall scheduler status."""
        stats = await self.store.get_stats()
        upcoming = await self.get_upcoming_runs(hours=24)

        return {
            "running": self._running,
            "check_interval_seconds": self._check_interval,
            "active_schedules": stats["active_configs"],
            "total_schedules": stats["configs_count"],
            "upcoming_runs_24h": len(upcoming),
            "next_run": upcoming[0][1].isoformat() if upcoming else None,
        }


# Common cron presets for convenience
CRON_PRESETS = {
    "every_minute": "* * * * *",
    "every_hour": "0 * * * *",
    "daily_9am": "0 9 * * *",
    "daily_midnight": "0 0 * * *",
    "weekly_monday_9am": "0 9 * * 1",
    "weekly_friday_5pm": "0 17 * * 5",
    "monthly_first_9am": "0 9 1 * *",
    "monthly_last_friday": "0 9 * * 5",  # Note: true "last Friday" needs special handling
    "weekdays_9am": "0 9 * * 1-5",
    "weekends_noon": "0 12 * * 0,6",
}


def get_cron_preset(name: str) -> str | None:
    """Get a cron expression from a preset name."""
    return CRON_PRESETS.get(name.lower())


def describe_cron(expression: str) -> str:
    """
    Generate a human-readable description of a cron expression.

    This is a simplified implementation - for production, consider
    using a library like 'cron-descriptor'.
    """
    try:
        parts = expression.split()
        if len(parts) != 5:
            return f"Invalid expression: {expression}"

        minute, hour, dom, month, dow = parts

        # Handle common patterns
        if expression == "* * * * *":
            return "Every minute"
        if expression == "0 * * * *":
            return "Every hour"
        if expression == "0 0 * * *":
            return "Every day at midnight"
        if minute == "0" and dom == "*" and month == "*":
            if dow == "*":
                return f"Every day at {hour}:00"
            elif dow == "1-5":
                return f"Every weekday at {hour}:00"
            elif dow == "0,6":
                return f"Every weekend at {hour}:00"

        # Generic description
        time_part = f"{hour}:{minute.zfill(2)}" if minute != "*" and hour != "*" else ""
        return f"Cron: {expression}" + (f" ({time_part})" if time_part else "")

    except Exception:
        return f"Cron: {expression}"
