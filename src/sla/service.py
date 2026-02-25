"""SLA Calculation Service.

Handles SLA timer management, breach detection, and metrics calculation.
Supports business hours awareness and escalation notifications.
"""

import logging
from datetime import datetime, timedelta, UTC
from typing import Any
from zoneinfo import ZoneInfo

from .models import (
    BusinessHours,
    EscalationLevel,
    SLABreach,
    SLAIncidentStatus,
    SLAMetrics,
    SLANotification,
    SLAPolicy,
    SLASeverity,
    SLAStatus,
    SLATimer,
    SLAType,
)

logger = logging.getLogger(__name__)


class SLAService:
    """Service for SLA calculations and management.

    Provides methods for:
    - Starting and stopping SLA timers
    - Checking for breaches
    - Calculating elapsed time with business hours
    - Generating metrics and reports
    """

    def __init__(self, store: Any) -> None:
        """Initialize SLA service.

        Args:
            store: SLA data store instance (SLAStore)
        """
        self.store = store

    async def start_timer(
        self,
        incident_id: str,
        policy: SLAPolicy,
        severity: SLASeverity,
        sla_type: SLAType,
        started_at: datetime | None = None,
    ) -> SLATimer | None:
        """Start an SLA timer for an incident.

        Args:
            incident_id: Unique incident identifier
            policy: SLA policy to apply
            severity: Incident severity level
            sla_type: Response or resolution timer
            started_at: Optional start time (defaults to now)

        Returns:
            Created SLATimer or None if no target exists
        """
        target = policy.get_target(severity, sla_type)
        if not target:
            logger.warning(
                f"No SLA target for {severity}/{sla_type} in policy {policy.id}"
            )
            return None

        timer = SLATimer(
            incident_id=incident_id,
            policy_id=policy.id,
            severity=severity,
            sla_type=sla_type,
            started_at=started_at or datetime.now(UTC),
            target_minutes=target.target_minutes,
        )

        # Check if we should start paused (outside business hours)
        if policy.business_hours.enabled:
            if not self._is_business_hours(timer.started_at, policy.business_hours):
                timer.paused = True
                timer.paused_at = timer.started_at

        await self.store.save_timer(timer)
        logger.info(
            f"Started {sla_type} SLA timer for incident {incident_id}, "
            f"target: {target.target_minutes}min"
        )
        return timer

    async def stop_timer(
        self,
        incident_id: str,
        sla_type: SLAType,
        completed_at: datetime | None = None,
    ) -> SLATimer | None:
        """Stop an SLA timer (marks completion).

        Args:
            incident_id: Incident identifier
            sla_type: Which timer to stop
            completed_at: Completion time (defaults to now)

        Returns:
            Updated timer or None if not found
        """
        timer = await self.store.get_timer(incident_id, sla_type)
        if not timer:
            return None

        now = completed_at or datetime.now(UTC)

        # Update elapsed time
        timer = await self._update_elapsed(timer, now)
        timer.completed_at = now

        # Check final status
        if timer.elapsed_minutes >= timer.target_minutes:
            timer.status = SLAStatus.BREACHED
            if not timer.breached_at:
                timer.breached_at = now

        await self.store.save_timer(timer)
        logger.info(
            f"Stopped {sla_type} timer for {incident_id}, elapsed: {timer.elapsed_minutes:.1f}min"
        )
        return timer

    async def pause_timer(self, incident_id: str, sla_type: SLAType) -> SLATimer | None:
        """Pause an SLA timer (for business hours or manual pause).

        Args:
            incident_id: Incident identifier
            sla_type: Which timer to pause

        Returns:
            Updated timer or None if not found
        """
        timer = await self.store.get_timer(incident_id, sla_type)
        if not timer or timer.paused or timer.completed_at:
            return timer

        now = datetime.now(UTC)
        timer = await self._update_elapsed(timer, now)
        timer.paused = True
        timer.paused_at = now

        await self.store.save_timer(timer)
        return timer

    async def resume_timer(
        self, incident_id: str, sla_type: SLAType
    ) -> SLATimer | None:
        """Resume a paused SLA timer.

        Args:
            incident_id: Incident identifier
            sla_type: Which timer to resume

        Returns:
            Updated timer or None if not found
        """
        timer = await self.store.get_timer(incident_id, sla_type)
        if not timer or not timer.paused:
            return timer

        now = datetime.now(UTC)
        if timer.paused_at:
            paused_duration = (now - timer.paused_at).total_seconds() / 60
            timer.total_paused_minutes += paused_duration

        timer.paused = False
        timer.paused_at = None

        await self.store.save_timer(timer)
        return timer

    async def check_breach(
        self,
        incident_id: str,
        sla_type: SLAType,
        policy: SLAPolicy,
    ) -> SLABreach | None:
        """Check if an SLA timer has breached and create breach record.

        Args:
            incident_id: Incident identifier
            sla_type: Which timer to check
            policy: SLA policy for escalation settings

        Returns:
            SLABreach if breached, None otherwise
        """
        timer = await self.store.get_timer(incident_id, sla_type)
        if not timer or timer.completed_at:
            return None

        # Update elapsed time
        timer = await self._update_elapsed(timer, datetime.now(UTC))

        # Already breached?
        if timer.status == SLAStatus.BREACHED:
            existing = await self.store.get_breach(incident_id, sla_type)
            return existing

        target = policy.get_target(timer.severity, sla_type)
        if not target:
            return None

        # Check warning threshold
        if timer.elapsed_minutes >= target.warning_minutes:
            if timer.status != SLAStatus.AT_RISK:
                timer.status = SLAStatus.AT_RISK
                await self.store.save_timer(timer)
                logger.warning(
                    f"SLA at risk for {incident_id}/{sla_type}: "
                    f"{timer.percent_elapsed:.1f}% elapsed"
                )

        # Check breach
        if timer.elapsed_minutes >= timer.target_minutes:
            timer.status = SLAStatus.BREACHED
            timer.breached_at = datetime.now(UTC)
            await self.store.save_timer(timer)

            breach = await self._create_breach(timer, policy)
            logger.error(
                f"SLA BREACHED for {incident_id}/{sla_type}: "
                f"{timer.elapsed_minutes:.1f}min > {timer.target_minutes}min"
            )
            return breach

        return None

    async def get_incident_status(
        self, incident_id: str, policy: SLAPolicy
    ) -> SLAIncidentStatus:
        """Get complete SLA status for an incident.

        Args:
            incident_id: Incident identifier
            policy: SLA policy applied

        Returns:
            Complete SLA status including all timers and breaches
        """
        response_timer = await self.store.get_timer(incident_id, SLAType.RESPONSE)
        resolution_timer = await self.store.get_timer(incident_id, SLAType.RESOLUTION)
        breaches = await self.store.get_incident_breaches(incident_id)

        # Update elapsed times
        now = datetime.now(UTC)
        if response_timer and not response_timer.completed_at:
            response_timer = await self._update_elapsed(response_timer, now)
        if resolution_timer and not resolution_timer.completed_at:
            resolution_timer = await self._update_elapsed(resolution_timer, now)

        severity = (
            response_timer.severity
            if response_timer
            else (resolution_timer.severity if resolution_timer else SLASeverity.P3)
        )

        status = SLAIncidentStatus(
            incident_id=incident_id,
            severity=severity,
            policy_id=policy.id,
            policy_name=policy.name,
            response_timer=response_timer,
            response_breached=response_timer.is_breached if response_timer else False,
            response_completed=(
                response_timer.completed_at is not None if response_timer else False
            ),
            resolution_timer=resolution_timer,
            resolution_breached=(
                resolution_timer.is_breached if resolution_timer else False
            ),
            resolution_completed=(
                resolution_timer.completed_at is not None if resolution_timer else False
            ),
            breaches=breaches,
        )
        status.overall_status = status.worst_status
        return status

    async def calculate_remaining_time(
        self,
        incident_id: str,
        sla_type: SLAType,
        policy: SLAPolicy,
    ) -> dict[str, Any]:
        """Calculate remaining time until SLA breach.

        Accounts for business hours if configured.

        Args:
            incident_id: Incident identifier
            sla_type: Response or resolution
            policy: SLA policy for business hours

        Returns:
            Dict with remaining time info
        """
        timer = await self.store.get_timer(incident_id, sla_type)
        if not timer:
            return {"error": "Timer not found"}

        timer = await self._update_elapsed(timer, datetime.now(UTC))
        remaining = timer.remaining_minutes

        result = {
            "incident_id": incident_id,
            "sla_type": sla_type,
            "target_minutes": timer.target_minutes,
            "elapsed_minutes": round(timer.elapsed_minutes, 2),
            "remaining_minutes": round(remaining, 2),
            "percent_elapsed": round(timer.percent_elapsed, 2),
            "status": timer.status,
            "paused": timer.paused,
        }

        # Calculate ETA to breach in real time (with business hours)
        if remaining > 0 and policy.business_hours.enabled:
            eta = self._calculate_breach_eta(remaining, policy.business_hours)
            result["breach_eta"] = eta.isoformat()
        elif remaining > 0:
            result["breach_eta"] = (
                datetime.now(UTC) + timedelta(minutes=remaining)
            ).isoformat()

        return result

    async def calculate_metrics(
        self,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        team_id: str | None = None,
        service_id: str | None = None,
        policy_id: str | None = None,
    ) -> SLAMetrics:
        """Calculate SLA compliance metrics for a time period.

        Args:
            organization_id: Organization scope
            period_start: Start of reporting period
            period_end: End of reporting period
            team_id: Optional team filter
            service_id: Optional service filter
            policy_id: Optional policy filter

        Returns:
            Aggregated SLA metrics
        """
        timers = await self.store.get_timers_in_period(
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
            team_id=team_id,
            service_id=service_id,
            policy_id=policy_id,
        )

        metrics = SLAMetrics(
            organization_id=organization_id,
            team_id=team_id,
            service_id=service_id,
            policy_id=policy_id,
            period_start=period_start,
            period_end=period_end,
        )

        response_times: list[float] = []
        resolution_times: list[float] = []
        incidents: set[str] = set()
        by_severity: dict[str, int] = {}

        for timer in timers:
            incidents.add(timer.incident_id)
            sev = timer.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            if timer.sla_type == SLAType.RESPONSE:
                if timer.completed_at:
                    response_times.append(timer.elapsed_minutes)
                if timer.is_breached:
                    metrics.response_sla_breached += 1
                else:
                    metrics.response_sla_met += 1
            elif timer.sla_type == SLAType.RESOLUTION:
                if timer.completed_at:
                    resolution_times.append(timer.elapsed_minutes)
                if timer.is_breached:
                    metrics.resolution_sla_breached += 1
                else:
                    metrics.resolution_sla_met += 1

        metrics.total_incidents = len(incidents)
        metrics.incidents_by_severity = by_severity

        if response_times:
            metrics.avg_response_minutes = round(
                sum(response_times) / len(response_times), 2
            )
        if resolution_times:
            metrics.avg_resolution_minutes = round(
                sum(resolution_times) / len(resolution_times), 2
            )

        metrics.calculate_compliance()

        # Add daily trend data
        metrics.compliance_trend = await self._calculate_trend(
            organization_id, period_start, period_end, team_id, service_id
        )

        return metrics

    async def check_all_active_timers(
        self, policy_lookup: dict[str, SLAPolicy]
    ) -> list[SLABreach]:
        """Check all active timers for breaches.

        Called periodically by the scheduler.

        Args:
            policy_lookup: Dict of policy_id -> SLAPolicy

        Returns:
            List of new breaches detected
        """
        active_timers = await self.store.get_active_timers()
        breaches: list[SLABreach] = []

        for timer in active_timers:
            policy = policy_lookup.get(timer.policy_id)
            if not policy:
                continue

            # Handle business hours pausing
            if policy.business_hours.enabled:
                is_biz_hours = self._is_business_hours(
                    datetime.now(UTC), policy.business_hours
                )
                if is_biz_hours and timer.paused:
                    await self.resume_timer(timer.incident_id, timer.sla_type)
                elif not is_biz_hours and not timer.paused:
                    await self.pause_timer(timer.incident_id, timer.sla_type)
                    continue  # Skip breach check if paused

            # Check for breach
            breach = await self.check_breach(timer.incident_id, timer.sla_type, policy)
            if breach:
                breaches.append(breach)

        return breaches

    # --- Private Methods ---

    async def _update_elapsed(self, timer: SLATimer, now: datetime) -> SLATimer:
        """Update elapsed time on a timer.

        Accounts for paused time.
        """
        if timer.completed_at or timer.paused:
            return timer

        total_seconds = (now - timer.started_at).total_seconds()
        total_minutes = total_seconds / 60
        timer.elapsed_minutes = total_minutes - timer.total_paused_minutes

        # Update status
        if timer.elapsed_minutes >= timer.target_minutes:
            timer.status = SLAStatus.BREACHED
        elif timer.percent_elapsed >= 75:
            timer.status = SLAStatus.AT_RISK

        return timer

    async def _create_breach(self, timer: SLATimer, policy: SLAPolicy) -> SLABreach:
        """Create a breach record from a breached timer."""
        import uuid

        breach_amount = timer.elapsed_minutes - timer.target_minutes
        breach_percent = (timer.elapsed_minutes / timer.target_minutes) * 100

        escalation_level = EscalationLevel.BREACH
        if breach_percent >= 150:
            escalation_level = EscalationLevel.CRITICAL

        breach = SLABreach(
            id=str(uuid.uuid4()),
            incident_id=timer.incident_id,
            policy_id=timer.policy_id,
            severity=timer.severity,
            sla_type=timer.sla_type,
            target_minutes=timer.target_minutes,
            actual_minutes=timer.elapsed_minutes,
            breach_amount_minutes=round(breach_amount, 2),
            breach_percent=round(breach_percent, 2),
            escalation_level=escalation_level,
            escalated_to=policy.escalation_contacts,
            breached_at=timer.breached_at or datetime.now(UTC),
        )

        await self.store.save_breach(breach)
        return breach

    def _is_business_hours(self, dt: datetime, config: BusinessHours) -> bool:
        """Check if a datetime falls within business hours."""
        if not config.enabled:
            return True

        try:
            tz = ZoneInfo(config.timezone)
            local_dt = dt.astimezone(tz)
        except Exception:
            local_dt = dt

        # Check holiday
        date_str = local_dt.strftime("%Y-%m-%d")
        if date_str in config.holidays:
            return False

        # Check working day (weekday() returns 0=Monday)
        if local_dt.weekday() not in config.working_days:
            return False

        # Check time
        current_time = local_dt.time()
        return config.start_time <= current_time < config.end_time

    def _calculate_breach_eta(
        self, remaining_minutes: float, config: BusinessHours
    ) -> datetime:
        """Calculate when SLA will breach accounting for business hours."""
        if not config.enabled:
            return datetime.now(UTC) + timedelta(minutes=remaining_minutes)

        try:
            tz = ZoneInfo(config.timezone)
        except Exception:
            return datetime.now(UTC) + timedelta(minutes=remaining_minutes)

        current = datetime.now(tz)
        remaining = remaining_minutes

        while remaining > 0:
            if self._is_business_hours(current, config):
                # Count business minutes until end of day
                end_of_day = current.replace(
                    hour=config.end_time.hour,
                    minute=config.end_time.minute,
                    second=0,
                    microsecond=0,
                )
                minutes_today = (end_of_day - current).total_seconds() / 60

                if remaining <= minutes_today:
                    return current + timedelta(minutes=remaining)

                remaining -= minutes_today
                current = end_of_day

            # Move to next business day start
            current += timedelta(days=1)
            current = current.replace(
                hour=config.start_time.hour,
                minute=config.start_time.minute,
                second=0,
                microsecond=0,
            )

        return current

    async def _calculate_trend(
        self,
        organization_id: str,
        period_start: datetime,
        period_end: datetime,
        team_id: str | None = None,
        service_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Calculate daily compliance trend."""
        trend: list[dict[str, Any]] = []
        current = period_start.replace(hour=0, minute=0, second=0, microsecond=0)

        while current < period_end:
            next_day = current + timedelta(days=1)

            timers = await self.store.get_timers_in_period(
                organization_id=organization_id,
                period_start=current,
                period_end=next_day,
                team_id=team_id,
                service_id=service_id,
            )

            met = sum(1 for t in timers if not t.is_breached)
            total = len(timers)
            compliance = (met / total * 100) if total > 0 else 100.0

            trend.append(
                {
                    "date": current.strftime("%Y-%m-%d"),
                    "total": total,
                    "met": met,
                    "breached": total - met,
                    "compliance_percent": round(compliance, 2),
                }
            )

            current = next_day

        return trend


async def create_sla_notification(
    breach: SLABreach,
    channel: str = "email",
) -> SLANotification:
    """Create an SLA breach notification.

    Args:
        breach: The breach to notify about
        channel: Notification channel (email, slack, pagerduty)

    Returns:
        SLANotification ready to send
    """
    import uuid

    severity_emoji = {
        SLASeverity.P1: "🔴",
        SLASeverity.P2: "🟠",
        SLASeverity.P3: "🟡",
        SLASeverity.P4: "🟢",
    }

    subject = (
        f"{severity_emoji.get(breach.severity, '⚠️')} SLA Breach: "
        f"{breach.severity} {breach.sla_type} - Incident {breach.incident_id}"
    )

    body = f"""
SLA Breach Alert

Incident ID: {breach.incident_id}
Severity: {breach.severity}
SLA Type: {breach.sla_type}
Target: {breach.target_minutes} minutes
Actual: {breach.actual_minutes:.1f} minutes
Breach Amount: {breach.breach_amount_minutes:.1f} minutes ({breach.breach_percent:.1f}% over target)
Escalation Level: {breach.escalation_level}

Breached at: {breach.breached_at.isoformat()}

Please investigate immediately.
"""

    return SLANotification(
        id=str(uuid.uuid4()),
        incident_id=breach.incident_id,
        sla_type=breach.sla_type,
        severity=breach.severity,
        escalation_level=breach.escalation_level,
        recipients=breach.escalated_to,
        channel=channel,
        subject=subject,
        body=body.strip(),
    )
