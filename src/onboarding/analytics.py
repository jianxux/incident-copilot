"""Onboarding analytics tracking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .checklist import CHECKLIST_STEPS

logger = structlog.get_logger()


class OnboardingEvent(BaseModel):
    """An onboarding analytics event."""

    tenant_id: str
    event_type: str
    step: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FunnelStep(BaseModel):
    """Funnel step conversion metrics."""

    step: str
    started: int
    completed: int
    conversion_rate: float
    drop_offs: int


class FunnelReport(BaseModel):
    """Funnel conversion report for onboarding."""

    start_date: datetime | None
    end_date: datetime | None
    total_tenants: int
    steps: list[FunnelStep]


class DropOffReport(BaseModel):
    """Tenant drop-off report for a funnel step."""

    step: str
    tenant_ids: list[str]
    count: int


class OnboardingAnalytics:
    """In-memory onboarding analytics tracking."""

    def __init__(self):
        self._events: list[OnboardingEvent] = []

    def track_event(
        self,
        tenant_id: str,
        event_type: str,
        step: str | None,
        metadata: dict[str, Any],
    ) -> OnboardingEvent:
        """Record an onboarding event."""
        event = OnboardingEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            step=step,
            metadata=metadata or {},
        )
        self._events.append(event)
        logger.info(
            "onboarding_event_recorded",
            tenant_id=tenant_id,
            event_type=event_type,
            step=step,
        )
        return event

    def _events_in_range(
        self, date_range: tuple[datetime | None, datetime | None]
    ) -> list[OnboardingEvent]:
        start, end = date_range
        events = []
        for event in self._events:
            if start and event.occurred_at < start:
                continue
            if end and event.occurred_at > end:
                continue
            events.append(event)
        return events

    def get_funnel(
        self, date_range: tuple[datetime | None, datetime | None]
    ) -> FunnelReport:
        """Return funnel conversion rates per step."""
        events = self._events_in_range(date_range)
        tenants = {event.tenant_id for event in events}
        steps_report: list[FunnelStep] = []

        for step in CHECKLIST_STEPS:
            started = {
                event.tenant_id
                for event in events
                if event.step == step and event.event_type == "step_started"
            }
            completed = {
                event.tenant_id
                for event in events
                if event.step == step and event.event_type == "step_completed"
            }
            if not started and completed:
                started = completed

            started_count = len(started)
            completed_count = len(completed)
            conversion = completed_count / started_count if started_count else 0.0
            drop_offs = max(started_count - completed_count, 0)

            steps_report.append(
                FunnelStep(
                    step=step,
                    started=started_count,
                    completed=completed_count,
                    conversion_rate=conversion,
                    drop_offs=drop_offs,
                )
            )

        return FunnelReport(
            start_date=date_range[0],
            end_date=date_range[1],
            total_tenants=len(tenants),
            steps=steps_report,
        )

    def get_time_to_first_context_card(self, tenant_id: str) -> timedelta | None:
        """Return time to first context card for a tenant."""
        events = [event for event in self._events if event.tenant_id == tenant_id]
        if not events:
            return None
        events.sort(key=lambda event: event.occurred_at)
        first_event = events[0]
        first_context = next(
            (event for event in events if event.event_type == "context_card_created"),
            None,
        )
        if not first_context:
            return None
        return first_context.occurred_at - first_event.occurred_at

    def get_drop_off_report(
        self, date_range: tuple[datetime | None, datetime | None]
    ) -> list[DropOffReport]:
        """Return tenants stuck at each funnel step."""
        events = self._events_in_range(date_range)
        tenants = {event.tenant_id for event in events}
        per_tenant_completed: dict[str, set[str]] = {t: set() for t in tenants}

        for event in events:
            if event.event_type == "step_completed" and event.step:
                per_tenant_completed[event.tenant_id].add(event.step)

        report: dict[str, list[str]] = {step: [] for step in CHECKLIST_STEPS}

        for tenant_id in tenants:
            completed_steps = per_tenant_completed.get(tenant_id, set())
            if len(completed_steps) == len(CHECKLIST_STEPS):
                continue

            highest_index = -1
            for step in completed_steps:
                try:
                    idx = CHECKLIST_STEPS.index(step)
                except ValueError:
                    continue
                highest_index = max(highest_index, idx)

            next_index = highest_index + 1
            if next_index < len(CHECKLIST_STEPS):
                report[CHECKLIST_STEPS[next_index]].append(tenant_id)

        return [
            DropOffReport(step=step, tenant_ids=tenant_ids, count=len(tenant_ids))
            for step, tenant_ids in report.items()
            if tenant_ids
        ]

    def get_average_time_to_value(self) -> timedelta | None:
        """Return average time to first context card across tenants."""
        tenants = {event.tenant_id for event in self._events}
        durations = []
        for tenant_id in tenants:
            duration = self.get_time_to_first_context_card(tenant_id)
            if duration is not None:
                durations.append(duration)
        if not durations:
            return None
        total_seconds = sum(d.total_seconds() for d in durations)
        return timedelta(seconds=total_seconds / len(durations))


onboarding_analytics = OnboardingAnalytics()
