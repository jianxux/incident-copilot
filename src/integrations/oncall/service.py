"""On-Call Service - Core business logic for schedule management."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
import uuid

from .models import (
    OnCallSchedule,
    OnCallShift,
    OnCallUser,
    OnCallOverride,
    Rotation,
    ProviderType,
    OverrideStatus,
    HandoffNotification,
    OnCallHistoryEntry,
    ScheduleSyncResult,
)
from .providers.pagerduty import PagerDutyProvider
from .providers.opsgenie import OpsgenieProvider


class OnCallService:
    """Service for managing on-call schedules, lookups, and overrides."""

    def __init__(self, pagerduty_key: Optional[str] = None, opsgenie_key: Optional[str] = None):
        self._pagerduty = PagerDutyProvider(pagerduty_key) if pagerduty_key else None
        self._opsgenie = OpsgenieProvider(opsgenie_key) if opsgenie_key else None

        # In-memory stores (replace with database in production)
        self._schedules: dict[str, OnCallSchedule] = {}
        self._overrides: dict[str, OnCallOverride] = {}
        self._shifts_cache: dict[str, list[OnCallShift]] = {}
        self._history: list[OnCallHistoryEntry] = []
        self._notifications: list[HandoffNotification] = []

    async def close(self) -> None:
        """Close provider connections."""
        if self._pagerduty:
            await self._pagerduty.close()
        if self._opsgenie:
            await self._opsgenie.close()

    # === Schedule Management ===

    async def sync_all_schedules(self) -> list[ScheduleSyncResult]:
        """Sync schedules from all configured providers."""
        results = []

        if self._pagerduty:
            try:
                schedules = await self._pagerduty.get_schedules()
                for sched in schedules:
                    self._schedules[sched.id] = sched
                    result = await self._pagerduty.sync_schedule(sched.provider_schedule_id)
                    results.append(result)
            except Exception as e:
                results.append(
                    ScheduleSyncResult(
                        schedule_id="pagerduty",
                        provider=ProviderType.PAGERDUTY,
                        success=False,
                        errors=[str(e)],
                    )
                )

        if self._opsgenie:
            try:
                schedules = await self._opsgenie.get_schedules()
                for sched in schedules:
                    self._schedules[sched.id] = sched
                    result = await self._opsgenie.sync_schedule(sched.provider_schedule_id)
                    results.append(result)
            except Exception as e:
                results.append(
                    ScheduleSyncResult(
                        schedule_id="opsgenie",
                        provider=ProviderType.OPSGENIE,
                        success=False,
                        errors=[str(e)],
                    )
                )

        return results

    async def get_schedule(self, schedule_id: str) -> Optional[OnCallSchedule]:
        """Get a schedule by ID."""
        return self._schedules.get(schedule_id)

    async def list_schedules(self, team_id: Optional[str] = None) -> list[OnCallSchedule]:
        """List all schedules, optionally filtered by team."""
        schedules = list(self._schedules.values())
        if team_id:
            schedules = [s for s in schedules if s.team_id == team_id]
        return schedules

    async def create_manual_schedule(self, schedule: OnCallSchedule) -> OnCallSchedule:
        """Create a manually-managed schedule."""
        schedule.provider = ProviderType.MANUAL
        schedule.id = f"manual_{uuid.uuid4().hex[:8]}"
        self._schedules[schedule.id] = schedule
        return schedule

    # === Who Is On-Call ===

    async def who_is_oncall(
        self, schedule_id: str, at_time: Optional[datetime] = None
    ) -> Optional[OnCallUser]:
        """
        Get the on-call user for a schedule at a specific time.
        Checks overrides first, then falls back to scheduled rotation.
        """
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            return None

        check_time = at_time or datetime.utcnow()

        # Check for active overrides first
        for override in self._overrides.values():
            if (
                override.schedule_id == schedule_id
                and override.status == OverrideStatus.ACTIVE
                and override.start_time <= check_time <= override.end_time
            ):
                return override.override_user

        # Try to get from provider
        if schedule.provider == ProviderType.PAGERDUTY and self._pagerduty:
            users = await self._pagerduty.get_oncall_now(schedule.provider_schedule_id)
            if users:
                return users[0]
        elif schedule.provider == ProviderType.OPSGENIE and self._opsgenie:
            users = await self._opsgenie.get_oncall_now(schedule.provider_schedule_id)
            if users:
                return users[0]

        # Fall back to rotation calculation
        return schedule.get_current_oncall()

    async def who_is_oncall_with_fallbacks(
        self, schedule_ids: list[str], at_time: Optional[datetime] = None
    ) -> list[OnCallUser]:
        """
        Get on-call users from multiple schedules with fallback chain.
        Returns users in priority order (primary, then fallbacks).
        """
        users = []
        for schedule_id in schedule_ids:
            user = await self.who_is_oncall(schedule_id, at_time)
            if user:
                users.append(user)
        return users

    async def get_all_oncall_now(self) -> dict[str, OnCallUser]:
        """Get currently on-call users for all schedules."""
        result = {}
        for schedule_id in self._schedules:
            user = await self.who_is_oncall(schedule_id)
            if user:
                result[schedule_id] = user
        return result

    # === Shifts ===

    async def get_upcoming_shifts(self, schedule_id: str, days: int = 7) -> list[OnCallShift]:
        """Get upcoming shifts for a schedule."""
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            return []

        now = datetime.utcnow()
        until = now + timedelta(days=days)

        if schedule.provider == ProviderType.PAGERDUTY and self._pagerduty:
            return await self._pagerduty.get_schedule_shifts(
                schedule.provider_schedule_id, now, until
            )
        elif schedule.provider == ProviderType.OPSGENIE and self._opsgenie:
            return await self._opsgenie.get_schedule_timeline(
                schedule.provider_schedule_id, now, until
            )

        # Generate shifts from rotation for manual schedules
        return self._generate_shifts_from_rotation(schedule, now, until)

    def _generate_shifts_from_rotation(
        self, schedule: OnCallSchedule, since: datetime, until: datetime
    ) -> list[OnCallShift]:
        """Generate shift entries from rotation configuration."""
        shifts = []

        for rotation in schedule.rotations:
            if not rotation.participants:
                continue

            current = since
            position = rotation.current_position()

            while current < until:
                user = rotation.participants[position % len(rotation.participants)]

                # Determine shift end based on rotation type
                if rotation.type == RotationType.DAILY:
                    end = current + timedelta(days=1)
                elif rotation.type == RotationType.WEEKLY:
                    end = current + timedelta(weeks=1)
                elif rotation.type == RotationType.BIWEEKLY:
                    end = current + timedelta(weeks=2)
                else:
                    end = current + timedelta(days=1)

                shifts.append(
                    OnCallShift(
                        id=f"{schedule.id}_shift_{current.isoformat()}",
                        user=user,
                        schedule_id=schedule.id,
                        start_time=current,
                        end_time=min(end, until),
                        timezone=schedule.timezone,
                    )
                )

                current = end
                position += 1

        return shifts

    # === Overrides ===

    async def create_override(
        self,
        schedule_id: str,
        override_user: OnCallUser,
        start_time: datetime,
        end_time: datetime,
        reason: Optional[str] = None,
        created_by: str = "system",
    ) -> OnCallOverride:
        """Create a temporary schedule override (handoff)."""
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        # Get current on-call as original user
        original_user = await self.who_is_oncall(schedule_id)
        if not original_user:
            raise ValueError("No current on-call user found")

        override = OnCallOverride(
            id=f"override_{uuid.uuid4().hex[:8]}",
            schedule_id=schedule_id,
            original_user=original_user,
            override_user=override_user,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            created_by=created_by,
            status=OverrideStatus.PENDING,
        )

        # Push to provider if available
        if schedule.provider == ProviderType.PAGERDUTY and self._pagerduty:
            override = await self._pagerduty.create_override(
                schedule.provider_schedule_id, override
            )
        elif schedule.provider == ProviderType.OPSGENIE and self._opsgenie:
            override = await self._opsgenie.create_override(schedule.provider_schedule_id, override)
        else:
            override.activate()

        self._overrides[override.id] = override
        return override

    async def cancel_override(self, override_id: str) -> bool:
        """Cancel an active override."""
        override = self._overrides.get(override_id)
        if not override:
            return False

        override.cancel()
        return True

    async def list_overrides(
        self, schedule_id: Optional[str] = None, active_only: bool = False
    ) -> list[OnCallOverride]:
        """List overrides, optionally filtered."""
        overrides = list(self._overrides.values())

        if schedule_id:
            overrides = [o for o in overrides if o.schedule_id == schedule_id]

        if active_only:
            overrides = [o for o in overrides if o.is_active]

        return overrides

    # === Handoff Notifications ===

    async def create_handoff_notification(
        self,
        schedule_id: str,
        outgoing: OnCallUser,
        incoming: OnCallUser,
        handoff_time: datetime,
        message: Optional[str] = None,
    ) -> HandoffNotification:
        """Create a handoff notification."""
        notification = HandoffNotification(
            id=f"handoff_{uuid.uuid4().hex[:8]}",
            schedule_id=schedule_id,
            outgoing_user=outgoing,
            incoming_user=incoming,
            handoff_time=handoff_time,
            message=message,
        )
        self._notifications.append(notification)
        return notification

    async def get_pending_handoffs(self, lookahead_hours: int = 2) -> list[HandoffNotification]:
        """Get handoffs happening in the next N hours that haven't been sent."""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=lookahead_hours)

        return [
            n for n in self._notifications if n.sent_at is None and now <= n.handoff_time <= cutoff
        ]

    async def mark_handoff_sent(self, notification_id: str) -> bool:
        """Mark a handoff notification as sent."""
        for n in self._notifications:
            if n.id == notification_id:
                n.sent_at = datetime.utcnow()
                return True
        return False

    # === History ===

    async def record_history(
        self,
        schedule_id: str,
        user: OnCallUser,
        start_time: datetime,
        end_time: datetime,
        was_override: bool = False,
        incidents_handled: int = 0,
    ) -> OnCallHistoryEntry:
        """Record on-call history entry."""
        entry = OnCallHistoryEntry(
            id=f"history_{uuid.uuid4().hex[:8]}",
            schedule_id=schedule_id,
            user=user,
            start_time=start_time,
            end_time=end_time,
            was_override=was_override,
            incidents_handled=incidents_handled,
        )
        self._history.append(entry)
        return entry

    async def get_history(
        self,
        schedule_id: Optional[str] = None,
        user_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[OnCallHistoryEntry]:
        """Query on-call history."""
        entries = self._history

        if schedule_id:
            entries = [e for e in entries if e.schedule_id == schedule_id]
        if user_id:
            entries = [e for e in entries if e.user.id == user_id]
        if since:
            entries = [e for e in entries if e.end_time >= since]
        if until:
            entries = [e for e in entries if e.start_time <= until]

        return sorted(entries, key=lambda e: e.start_time, reverse=True)[:limit]

    # === Rotation Visualization ===

    async def get_rotation_visualization(self, schedule_id: str, days: int = 14) -> dict:
        """Get rotation data for visualization."""
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            return {}

        shifts = await self.get_upcoming_shifts(schedule_id, days)

        # Group shifts by user for visualization
        user_shifts: dict[str, list[dict]] = {}
        for shift in shifts:
            if shift.user.id not in user_shifts:
                user_shifts[shift.user.id] = []
            user_shifts[shift.user.id].append({
                "start": shift.start_time.isoformat(),
                "end": shift.end_time.isoformat(),
                "is_override": shift.is_override,
            })

        return {
            "schedule_id": schedule_id,
            "schedule_name": schedule.name,
            "timezone": schedule.timezone,
            "range_days": days,
            "participants": [
                {"user_id": uid, "shifts": shifts_data} for uid, shifts_data in user_shifts.items()
            ],
            "rotations": [
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.type.value,
                    "handoff_time": r.handoff_time,
                    "participant_count": len(r.participants),
                }
                for r in schedule.rotations
            ],
        }
