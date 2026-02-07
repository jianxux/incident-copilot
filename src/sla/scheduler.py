"""SLA Breach Scheduler.

Background task to periodically check for SLA breaches and send notifications.
Supports configurable check intervals and escalation handling.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Coroutine

from .models import (
    EscalationLevel,
    SLABreach,
    SLANotification,
    SLAPolicy,
    SLASeverity,
)
from .service import SLAService, create_sla_notification

logger = logging.getLogger(__name__)


# Type alias for notification sender
NotificationSender = Callable[[SLANotification], Coroutine[Any, Any, bool]]


class SLAScheduler:
    """Background scheduler for SLA breach checking.
    
    Runs periodic checks on all active SLA timers, detects breaches,
    and sends notifications/escalations.
    
    Example usage:
        scheduler = SLAScheduler(sla_service, check_interval_seconds=60)
        scheduler.set_notification_sender(my_notification_handler)
        await scheduler.start()
        
        # Later...
        await scheduler.stop()
    """

    def __init__(
        self,
        service: SLAService,
        check_interval_seconds: int = 60,
        warning_interval_seconds: int = 300,
    ) -> None:
        """Initialize the SLA scheduler.
        
        Args:
            service: SLA service instance
            check_interval_seconds: How often to check for breaches (default: 60s)
            warning_interval_seconds: Minimum time between warning notifications
        """
        self.service = service
        self.check_interval = check_interval_seconds
        self.warning_interval = warning_interval_seconds
        
        self._running = False
        self._task: asyncio.Task | None = None
        self._notification_sender: NotificationSender | None = None
        self._policy_cache: dict[str, SLAPolicy] = {}
        self._policy_cache_ttl = 300  # 5 minutes
        self._policy_cache_time: datetime | None = None
        
        # Track sent warnings to avoid spam
        self._warning_sent: dict[str, datetime] = {}

    def set_notification_sender(self, sender: NotificationSender) -> None:
        """Set the notification sender callback.
        
        Args:
            sender: Async function that sends notifications.
                    Should return True if sent successfully.
        """
        self._notification_sender = sender

    async def start(self) -> None:
        """Start the background scheduler.
        
        Begins periodic SLA breach checking. Safe to call multiple times.
        """
        if self._running:
            logger.warning("SLA scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"SLA scheduler started (check interval: {self.check_interval}s)"
        )

    async def stop(self) -> None:
        """Stop the background scheduler.
        
        Gracefully stops the check loop and waits for completion.
        """
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
        
        logger.info("SLA scheduler stopped")

    async def run_once(self) -> list[SLABreach]:
        """Run a single breach check cycle.
        
        Useful for testing or manual triggering.
        
        Returns:
            List of new breaches detected
        """
        return await self._check_breaches()

    @property
    def is_running(self) -> bool:
        """Check if the scheduler is currently running."""
        return self._running

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                breaches = await self._check_breaches()
                
                if breaches:
                    logger.info(f"Detected {len(breaches)} new SLA breaches")
                    await self._handle_breaches(breaches)
                
                # Also check for warnings
                await self._check_warnings()
                
            except Exception as e:
                logger.error(f"Error in SLA scheduler loop: {e}", exc_info=True)
            
            # Sleep until next check
            await asyncio.sleep(self.check_interval)

    async def _check_breaches(self) -> list[SLABreach]:
        """Check all active timers for breaches."""
        # Refresh policy cache if stale
        await self._refresh_policy_cache()
        
        # Check all active timers
        breaches = await self.service.check_all_active_timers(self._policy_cache)
        
        return breaches

    async def _check_warnings(self) -> None:
        """Check for SLA at-risk warnings and send notifications."""
        active_timers = await self.service.store.get_active_timers()
        now = datetime.utcnow()

        for timer in active_timers:
            # Skip if not at risk or already breached
            from .models import SLAStatus
            if timer.status != SLAStatus.AT_RISK:
                continue

            # Check if we already sent a warning recently
            warn_key = f"{timer.incident_id}:{timer.sla_type}"
            last_warn = self._warning_sent.get(warn_key)
            
            if last_warn:
                seconds_since = (now - last_warn).total_seconds()
                if seconds_since < self.warning_interval:
                    continue

            # Get policy for escalation contacts
            policy = self._policy_cache.get(timer.policy_id)
            if not policy or not policy.escalation_enabled:
                continue

            # Create and send warning notification
            warning = await self._create_warning_notification(timer, policy)
            if warning and self._notification_sender:
                try:
                    sent = await self._notification_sender(warning)
                    if sent:
                        self._warning_sent[warn_key] = now
                        logger.info(
                            f"Sent SLA warning for {timer.incident_id}/{timer.sla_type}"
                        )
                except Exception as e:
                    logger.error(f"Failed to send warning notification: {e}")

    async def _handle_breaches(self, breaches: list[SLABreach]) -> None:
        """Handle detected breaches by sending notifications."""
        for breach in breaches:
            policy = self._policy_cache.get(breach.policy_id)
            
            if not policy or not policy.escalation_enabled:
                continue

            # Create notification for each configured channel
            for channel in ["email", "slack"]:
                try:
                    notification = await create_sla_notification(breach, channel)
                    
                    if self._notification_sender:
                        sent = await self._notification_sender(notification)
                        if sent:
                            # Update breach with notification sent time
                            breach.escalation_sent_at = datetime.utcnow()
                            await self.service.store.save_breach(breach)
                            logger.info(
                                f"Sent {channel} notification for breach {breach.id}"
                            )
                except Exception as e:
                    logger.error(
                        f"Failed to send {channel} notification for {breach.id}: {e}"
                    )

    async def _refresh_policy_cache(self) -> None:
        """Refresh the policy cache if stale."""
        now = datetime.utcnow()
        
        if self._policy_cache_time:
            age = (now - self._policy_cache_time).total_seconds()
            if age < self._policy_cache_ttl:
                return

        # Get all active timers and fetch their policies
        active_timers = await self.service.store.get_active_timers()
        policy_ids = set(t.policy_id for t in active_timers)
        
        new_cache: dict[str, SLAPolicy] = {}
        for policy_id in policy_ids:
            policy = await self.service.store.get_policy(policy_id)
            if policy:
                new_cache[policy_id] = policy

        self._policy_cache = new_cache
        self._policy_cache_time = now
        logger.debug(f"Refreshed policy cache with {len(new_cache)} policies")

    async def _create_warning_notification(
        self,
        timer: Any,
        policy: SLAPolicy,
    ) -> SLANotification | None:
        """Create a warning notification for an at-risk SLA."""
        import uuid

        severity_emoji = {
            SLASeverity.P1: "🔴",
            SLASeverity.P2: "🟠",
            SLASeverity.P3: "🟡",
            SLASeverity.P4: "🟢",
        }

        subject = (
            f"⚠️ SLA At Risk: {timer.severity} {timer.sla_type} - "
            f"Incident {timer.incident_id}"
        )

        remaining = timer.remaining_minutes
        body = f"""
SLA Warning - Action Required

Incident ID: {timer.incident_id}
Severity: {timer.severity}
SLA Type: {timer.sla_type}
Target: {timer.target_minutes} minutes
Elapsed: {timer.elapsed_minutes:.1f} minutes ({timer.percent_elapsed:.1f}%)
Remaining: {remaining:.1f} minutes

{severity_emoji.get(timer.severity, '⚠️')} This SLA is at risk of breach!

Please take action to resolve within the remaining time.
"""

        return SLANotification(
            id=str(uuid.uuid4()),
            incident_id=timer.incident_id,
            sla_type=timer.sla_type,
            severity=timer.severity,
            escalation_level=EscalationLevel.WARNING,
            recipients=policy.escalation_contacts,
            channel="email",
            subject=subject,
            body=body.strip(),
        )


class SLASchedulerManager:
    """Manager for SLA scheduler lifecycle.
    
    Integrates with FastAPI application lifecycle events.
    
    Example:
        manager = SLASchedulerManager(sla_service)
        
        @app.on_event("startup")
        async def startup():
            await manager.startup()
        
        @app.on_event("shutdown")
        async def shutdown():
            await manager.shutdown()
    """

    def __init__(
        self,
        service: SLAService,
        check_interval_seconds: int = 60,
        enabled: bool = True,
    ) -> None:
        """Initialize the scheduler manager.
        
        Args:
            service: SLA service instance
            check_interval_seconds: Breach check interval
            enabled: Whether to enable the scheduler on startup
        """
        self.scheduler = SLAScheduler(
            service, check_interval_seconds=check_interval_seconds
        )
        self._enabled = enabled

    def set_notification_sender(self, sender: NotificationSender) -> None:
        """Set the notification sender callback."""
        self.scheduler.set_notification_sender(sender)

    async def startup(self) -> None:
        """Start the scheduler (call from app startup event)."""
        if self._enabled:
            await self.scheduler.start()
            logger.info("SLA scheduler manager: scheduler started")
        else:
            logger.info("SLA scheduler manager: scheduler disabled")

    async def shutdown(self) -> None:
        """Stop the scheduler (call from app shutdown event)."""
        await self.scheduler.stop()
        logger.info("SLA scheduler manager: scheduler stopped")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.is_running


# Example notification sender implementations

async def email_notification_sender(notification: SLANotification) -> bool:
    """Example email notification sender.
    
    Replace with your actual email sending implementation.
    """
    logger.info(
        f"[EMAIL] To: {notification.recipients}, "
        f"Subject: {notification.subject}"
    )
    # TODO: Implement actual email sending
    # Example with aiosmtplib:
    # await send_email(
    #     to=notification.recipients,
    #     subject=notification.subject,
    #     body=notification.body,
    # )
    return True


async def slack_notification_sender(notification: SLANotification) -> bool:
    """Example Slack notification sender.
    
    Replace with your actual Slack integration.
    """
    logger.info(
        f"[SLACK] Channels: {notification.recipients}, "
        f"Message: {notification.subject}"
    )
    # TODO: Implement actual Slack sending
    # Example with slack_sdk:
    # client = AsyncWebClient(token=os.environ["SLACK_BOT_TOKEN"])
    # for channel in notification.recipients:
    #     await client.chat_postMessage(
    #         channel=channel,
    #         text=notification.subject,
    #         blocks=[...],
    #     )
    return True


async def multi_channel_sender(notification: SLANotification) -> bool:
    """Send notifications to multiple channels based on type."""
    if notification.channel == "email":
        return await email_notification_sender(notification)
    elif notification.channel == "slack":
        return await slack_notification_sender(notification)
    else:
        logger.warning(f"Unknown notification channel: {notification.channel}")
        return False


# Convenience function to create and configure scheduler

def create_sla_scheduler(
    service: SLAService,
    check_interval: int = 60,
    notification_sender: NotificationSender | None = None,
) -> SLAScheduler:
    """Create and configure an SLA scheduler.
    
    Args:
        service: SLA service instance
        check_interval: Seconds between breach checks
        notification_sender: Optional notification callback
        
    Returns:
        Configured SLAScheduler instance
    """
    scheduler = SLAScheduler(service, check_interval_seconds=check_interval)
    
    if notification_sender:
        scheduler.set_notification_sender(notification_sender)
    else:
        scheduler.set_notification_sender(multi_channel_sender)
    
    return scheduler
