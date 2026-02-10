"""On-call schedule integration for handoff summaries.

This module focuses on:
- retrieving shift timelines (PagerDuty primary, Opsgenie fallback)
- detecting shift boundaries (outgoing -> incoming)
- caching results to reduce API calls

It uses the existing provider implementations in :mod:`src.integrations.oncall`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from ..config import Settings
from ..integrations.oncall.models import OnCallShift
from ..integrations.oncall.service import OnCallService
from .models import ShiftInfo, ShiftPerson

logger = structlog.get_logger()


@dataclass
class _CacheEntry:
    fetched_at: datetime
    value: list[OnCallShift]


class OnCallScheduleClient:
    """Fetches on-call schedule timelines and detects handoffs."""

    def __init__(
        self,
        settings: Settings,
        cache_ttl_seconds: int = 300,
    ):
        self.settings = settings
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._service = OnCallService(
            pagerduty_key=settings.pagerduty_api_key or None,
            opsgenie_key=settings.opsgenie_api_key or None,
        )
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self._service.close()

    async def get_shifts(
        self,
        schedule_id: str,
        days: int = 2,
        force_refresh: bool = False,
    ) -> list[OnCallShift]:
        """Get schedule shifts over the next ``days`` days.

        Cached in-memory by schedule_id.
        """
        now = datetime.now(UTC)

        async with self._lock:
            if not force_refresh and schedule_id in self._cache:
                entry = self._cache[schedule_id]
                if now - entry.fetched_at <= self.cache_ttl:
                    return entry.value

        try:
            shifts = await self._service.get_upcoming_shifts(schedule_id, days=days)
            shifts = sorted(shifts, key=lambda s: s.start_time)
        except Exception as e:
            logger.warning(
                "oncall_get_shifts_failed",
                schedule_id=schedule_id,
                error=str(e),
            )
            return []

        async with self._lock:
            self._cache[schedule_id] = _CacheEntry(fetched_at=now, value=shifts)

        return shifts

    async def detect_shift_boundary(
        self,
        schedule_id: str,
        reference_time: datetime | None = None,
        window_hours: int = 24,
    ) -> ShiftInfo | None:
        """Detect the most recent shift handoff near ``reference_time``.

        Args:
            schedule_id: Internal schedule id (e.g., "pd_<id>" from oncall service).
            reference_time: Time to detect boundary around (defaults to now).
            window_hours: Look back/forward window to search for a boundary.

        Returns:
            ShiftInfo for the outgoing shift window and the adjacent incoming person.
        """
        ref = reference_time or datetime.now(UTC)
        # Fetch enough shifts to cover the window around ref. The provider interface
        # fetches forward-looking shifts; we request a couple of days and then search.
        shifts = await self.get_shifts(
            schedule_id, days=max(2, (window_hours // 24) + 2)
        )
        if not shifts:
            return None

        # Find boundary nearest but <= ref (prefer a handoff that just happened).
        best: tuple[float, int] | None = None  # (delta_seconds, boundary_index)
        for i in range(len(shifts) - 1):
            outgoing = shifts[i]
            incoming = shifts[i + 1]
            boundary = outgoing.end_time

            # Some schedules may have gaps/overlaps; allow small drift.
            if abs((incoming.start_time - boundary).total_seconds()) > 3600:
                continue

            delta = (ref - boundary).total_seconds()
            if delta < 0:
                continue
            if abs(delta) > window_hours * 3600:
                continue

            if best is None or delta < best[0]:
                best = (delta, i)

        if best is None:
            return None

        outgoing = shifts[best[1]]
        incoming = shifts[best[1] + 1]

        return ShiftInfo(
            schedule_id=schedule_id,
            schedule_name=None,
            outgoing=self._to_person(outgoing.user),
            incoming=self._to_person(incoming.user),
            shift_start=outgoing.start_time,
            shift_end=outgoing.end_time,
            handoff_time=outgoing.end_time,
            timezone=outgoing.timezone or "UTC",
            provider="pagerduty" if schedule_id.startswith("pd_") else "opsgenie",
            raw={
                "outgoing_shift_id": outgoing.id,
                "incoming_shift_id": incoming.id,
            },
        )

    def _to_person(self, user) -> ShiftPerson:
        return ShiftPerson(
            id=user.id,
            name=user.name,
            email=getattr(user, "email", None) or None,
            slack_user_id=getattr(user, "slack_user_id", None) or None,
        )
