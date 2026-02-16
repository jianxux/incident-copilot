"""End-to-end latency tracking for incident context assembly.

Tracks T₀ (alert fired) → T₁ (card delivered) as the North Star metric.
Provides structured timing breakdowns for each phase of context assembly.
"""

import time
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class Phase(StrEnum):
    """Phases of context assembly pipeline."""

    WEBHOOK_RECEIVED = "webhook_received"  # Alert lands on our API
    CONTEXT_FETCH_START = "context_fetch_start"  # Fan-out begins
    SCM_FETCH = "scm_fetch"  # GitHub/GitLab
    LOG_FETCH = "log_fetch"  # Datadog/CloudWatch/Loki
    ONCALL_FETCH = "oncall_fetch"  # PagerDuty/Opsgenie roster
    TOPOLOGY_FETCH = "topology_fetch"  # Service dependencies
    AI_SUMMARIZE = "ai_summarize"  # Log summarization
    AI_VERDICT = "ai_verdict"  # Verdict generation
    RUNBOOK_LINK = "runbook_link"  # Runbook matching
    CARD_ASSEMBLED = "card_assembled"  # ContextCard built
    CARD_DELIVERED = "card_delivered"  # Sent to Slack/Teams


class PhaseTimings(BaseModel):
    """Timing for a single phase."""

    phase: Phase
    started_at: float  # monotonic time
    ended_at: float | None = None
    duration_ms: int | None = None
    success: bool = True
    error: str | None = None


class LatencyReport(BaseModel):
    """Complete latency report for one incident processing run."""

    incident_id: str
    service_name: str

    # The North Star: total time from webhook to delivery
    total_ms: int | None = None

    # Individual phase timings
    phases: dict[str, PhaseTimings] = Field(default_factory=dict)

    # Alert metadata
    alert_fired_at: datetime | None = None  # T₀ — when PagerDuty/Opsgenie fired
    webhook_received_at: datetime | None = None  # When we received it
    card_delivered_at: datetime | None = None  # T₁ — when Slack/Teams got it

    # Derived: alert-to-delivery (includes network latency from alert provider)
    alert_to_delivery_ms: int | None = None

    # Budget tracking
    budget_ms: int = 10000  # 10 second target
    within_budget: bool | None = None

    def finalize(self) -> "LatencyReport":
        """Calculate derived fields after all phases complete."""
        # Total from webhook to delivery
        webhook_phase = self.phases.get(Phase.WEBHOOK_RECEIVED)
        delivery_phase = self.phases.get(Phase.CARD_DELIVERED)

        if webhook_phase and delivery_phase and delivery_phase.ended_at:
            self.total_ms = int(
                (delivery_phase.ended_at - webhook_phase.started_at) * 1000
            )
            self.within_budget = self.total_ms <= self.budget_ms

        # Alert-to-delivery (includes external latency)
        if self.alert_fired_at and self.card_delivered_at:
            delta = (self.card_delivered_at - self.alert_fired_at).total_seconds()
            self.alert_to_delivery_ms = int(delta * 1000)

        return self

    def summary(self) -> dict:
        """Human-readable summary for logging and display."""
        phase_summary = {}
        for name, timing in self.phases.items():
            phase_summary[name] = {
                "ms": timing.duration_ms,
                "ok": timing.success,
            }
            if timing.error:
                phase_summary[name]["error"] = timing.error

        return {
            "incident_id": self.incident_id,
            "service": self.service_name,
            "total_ms": self.total_ms,
            "alert_to_delivery_ms": self.alert_to_delivery_ms,
            "within_budget": self.within_budget,
            "budget_ms": self.budget_ms,
            "phases": phase_summary,
        }


class LatencyTracker:
    """Tracks end-to-end latency for a single incident processing run.

    Usage:
        tracker = LatencyTracker("INC-123", "payments-api")
        tracker.set_alert_fired_at(incident.triggered_at)

        tracker.start(Phase.WEBHOOK_RECEIVED)
        tracker.end(Phase.WEBHOOK_RECEIVED)

        tracker.start(Phase.CONTEXT_FETCH_START)
        async with tracker.track(Phase.SCM_FETCH):
            ctx = await github.get_context(service)
        async with tracker.track(Phase.LOG_FETCH):
            logs = await datadog.get_context(service)

        tracker.start(Phase.CARD_DELIVERED)
        await slack.send(card)
        tracker.end(Phase.CARD_DELIVERED)

        report = tracker.report()
        # report.total_ms → 4200
        # report.within_budget → True
    """

    def __init__(self, incident_id: str, service_name: str, budget_ms: int = 10000):
        self.incident_id = incident_id
        self.service_name = service_name
        self.budget_ms = budget_ms
        self._phases: dict[str, PhaseTimings] = {}
        self._alert_fired_at: datetime | None = None
        self._card_delivered_at: datetime | None = None

    def set_alert_fired_at(self, fired_at: datetime) -> None:
        """Set T₀ — when the alert originally fired (from PagerDuty/Opsgenie)."""
        self._alert_fired_at = fired_at

    def start(self, phase: Phase) -> None:
        """Mark the start of a phase."""
        self._phases[phase.value] = PhaseTimings(
            phase=phase,
            started_at=time.monotonic(),
        )

    def end(self, phase: Phase, success: bool = True, error: str | None = None) -> None:
        """Mark the end of a phase."""
        timing = self._phases.get(phase.value)
        if timing:
            timing.ended_at = time.monotonic()
            timing.duration_ms = int((timing.ended_at - timing.started_at) * 1000)
            timing.success = success
            timing.error = error

            if phase == Phase.CARD_DELIVERED:
                self._card_delivered_at = datetime.now(UTC)

            logger.debug(
                "phase_completed",
                phase=phase.value,
                duration_ms=timing.duration_ms,
                success=success,
            )

    @contextmanager
    def track(self, phase: Phase):
        """Context manager to track a phase.

        Usage:
            with tracker.track(Phase.SCM_FETCH):
                result = await fetch_github()
        """
        self.start(phase)
        try:
            yield
            self.end(phase, success=True)
        except Exception as e:
            self.end(phase, success=False, error=str(e))
            raise

    def report(self) -> LatencyReport:
        """Generate the final latency report."""
        report = LatencyReport(
            incident_id=self.incident_id,
            service_name=self.service_name,
            phases=self._phases,
            alert_fired_at=self._alert_fired_at,
            card_delivered_at=self._card_delivered_at,
            budget_ms=self.budget_ms,
        )

        if self._alert_fired_at:
            report.alert_fired_at = self._alert_fired_at

        return report.finalize()

    def log_report(self) -> LatencyReport:
        """Generate report and log it."""
        report = self.report()
        summary = report.summary()

        if report.within_budget:
            logger.info("latency_report", **summary)
        else:
            logger.warning("latency_over_budget", **summary)

        return report
