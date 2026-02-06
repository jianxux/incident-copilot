"""Action handlers for escalation rules.

Supports various action types:
- Notify (email, Slack, webhook)
- Page (PagerDuty, Opsgenie)
- Update severity
- Auto-assign
- Escalate to manager
- Add responder
- Post to channel
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import structlog

from .models import (
    ActionType,
    EscalationAction,
    EscalationAuditEntry,
    IncidentState,
)

logger = structlog.get_logger()


class ActionResult:
    """Result of executing an action."""

    def __init__(
        self,
        success: bool,
        action: EscalationAction,
        message: str | None = None,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.success = success
        self.action = action
        self.message = message
        self.error = error
        self.details = details or {}
        self.executed_at = datetime.utcnow()

    def to_audit_entry(
        self, incident_id: str, policy_id: str | None = None
    ) -> EscalationAuditEntry:
        """Convert to audit entry."""
        return EscalationAuditEntry(
            incident_id=incident_id,
            policy_id=policy_id,
            event_type="action_executed" if self.success else "action_failed",
            action_type=self.action.action_type,
            target=self.action.target,
            details={
                "action_id": self.action.id,
                "params": self.action.params,
                "message": self.message,
                **self.details,
            },
            success=self.success,
            error_message=self.error,
        )


class ActionHandler(ABC):
    """Abstract base class for action handlers."""

    @abstractmethod
    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Execute the action.

        Args:
            action: The action to execute
            incident: The current incident state

        Returns:
            ActionResult with success/failure status
        """
        pass

    async def execute_with_retry(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Execute the action with retries on failure."""
        last_error: str | None = None

        for attempt in range(action.retry_count + 1):
            try:
                result = await self.execute(action, incident)
                if result.success:
                    return result
                last_error = result.error
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "action_execution_error",
                    action_type=action.action_type,
                    attempt=attempt + 1,
                    error=str(e),
                )

            if attempt < action.retry_count:
                await asyncio.sleep(action.retry_delay_seconds)

        return ActionResult(
            success=False,
            action=action,
            error=f"Failed after {action.retry_count + 1} attempts: {last_error}",
        )


class NotifyHandler(ActionHandler):
    """Handler for notification actions (email, Slack, etc.)."""

    def __init__(
        self,
        slack_client: Any | None = None,
        email_client: Any | None = None,
    ):
        self.slack_client = slack_client
        self.email_client = email_client

    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Send notification via specified channel."""
        channel = action.params.get("channel", "slack")
        message = self._build_message(action, incident)

        try:
            if channel == "slack":
                return await self._send_slack(action, incident, message)
            elif channel == "email":
                return await self._send_email(action, incident, message)
            elif channel == "webhook":
                return await self._send_webhook(action, incident, message)
            else:
                return ActionResult(
                    success=False,
                    action=action,
                    error=f"Unknown notification channel: {channel}",
                )
        except Exception as e:
            logger.error(
                "notification_failed",
                action_id=action.id,
                channel=channel,
                error=str(e),
            )
            return ActionResult(
                success=False,
                action=action,
                error=str(e),
            )

    def _build_message(
        self, action: EscalationAction, incident: IncidentState
    ) -> str:
        """Build notification message."""
        template = action.params.get(
            "message",
            "🚨 Escalation Alert: {title} ({severity}) - Service: {service}",
        )
        return template.format(
            title=incident.title,
            severity=incident.severity,
            service=incident.service,
            incident_id=incident.incident_id,
            minutes=int(incident.minutes_since_triggered),
            url=incident.url or "",
        )

    async def _send_slack(
        self, action: EscalationAction, incident: IncidentState, message: str
    ) -> ActionResult:
        """Send Slack notification."""
        target = action.target or action.params.get("slack_channel")
        if not target:
            return ActionResult(
                success=False,
                action=action,
                error="No Slack target specified",
            )

        if self.slack_client is None:
            # Simulate success for testing without actual Slack client
            logger.info(
                "slack_notification_simulated",
                target=target,
                message=message[:100],
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Notification sent to Slack: {target}",
                details={"simulated": True},
            )

        # Real Slack client integration would go here
        try:
            await self.slack_client.post_message(
                channel=target,
                text=message,
                blocks=self._build_slack_blocks(incident, message),
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Notification sent to Slack: {target}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Slack error: {str(e)}",
            )

    def _build_slack_blocks(
        self, incident: IncidentState, message: str
    ) -> list[dict]:
        """Build Slack Block Kit blocks for rich notification."""
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Service:*\n{incident.service}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{incident.severity}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{incident.status}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Duration:*\n{int(incident.minutes_since_triggered)} min",
                    },
                ],
            },
        ]
        if incident.url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Incident"},
                            "url": incident.url,
                        }
                    ],
                }
            )
        return blocks

    async def _send_email(
        self, action: EscalationAction, incident: IncidentState, message: str
    ) -> ActionResult:
        """Send email notification."""
        target = action.target or action.params.get("email")
        if not target:
            return ActionResult(
                success=False,
                action=action,
                error="No email target specified",
            )

        if self.email_client is None:
            logger.info(
                "email_notification_simulated",
                target=target,
                subject=f"Escalation: {incident.title}",
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Email sent to: {target}",
                details={"simulated": True},
            )

        # Real email client integration would go here
        try:
            await self.email_client.send(
                to=target,
                subject=f"[Escalation] {incident.title}",
                body=message,
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Email sent to: {target}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Email error: {str(e)}",
            )

    async def _send_webhook(
        self, action: EscalationAction, incident: IncidentState, message: str
    ) -> ActionResult:
        """Send webhook notification."""
        webhook_url = action.params.get("webhook_url")
        if not webhook_url:
            return ActionResult(
                success=False,
                action=action,
                error="No webhook URL specified",
            )

        import httpx

        payload = {
            "incident_id": incident.incident_id,
            "title": incident.title,
            "service": incident.service,
            "severity": incident.severity,
            "status": incident.status,
            "message": message,
            "triggered_at": incident.triggered_at.isoformat(),
            "url": incident.url,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()

            return ActionResult(
                success=True,
                action=action,
                message=f"Webhook sent to: {webhook_url}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Webhook error: {str(e)}",
            )


class PageHandler(ActionHandler):
    """Handler for paging actions (PagerDuty, Opsgenie)."""

    def __init__(
        self,
        pagerduty_client: Any | None = None,
        opsgenie_client: Any | None = None,
    ):
        self.pagerduty_client = pagerduty_client
        self.opsgenie_client = opsgenie_client

    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Page via PagerDuty or Opsgenie."""
        provider = action.params.get("provider", self._detect_provider(incident))
        target = action.target or action.target_id

        if not target:
            return ActionResult(
                success=False,
                action=action,
                error="No page target (user/schedule) specified",
            )

        try:
            if provider == "pagerduty":
                return await self._page_pagerduty(action, incident, target)
            elif provider == "opsgenie":
                return await self._page_opsgenie(action, incident, target)
            else:
                return ActionResult(
                    success=False,
                    action=action,
                    error=f"Unknown paging provider: {provider}",
                )
        except Exception as e:
            logger.error(
                "paging_failed",
                action_id=action.id,
                provider=provider,
                error=str(e),
            )
            return ActionResult(
                success=False,
                action=action,
                error=str(e),
            )

    def _detect_provider(self, incident: IncidentState) -> str:
        """Detect provider from incident source."""
        if incident.source == "pagerduty":
            return "pagerduty"
        elif incident.source == "opsgenie":
            return "opsgenie"
        # Default to pagerduty if available
        if self.pagerduty_client:
            return "pagerduty"
        if self.opsgenie_client:
            return "opsgenie"
        return "pagerduty"

    async def _page_pagerduty(
        self, action: EscalationAction, incident: IncidentState, target: str
    ) -> ActionResult:
        """Create PagerDuty incident or add responder."""
        if self.pagerduty_client is None:
            logger.info(
                "pagerduty_page_simulated",
                target=target,
                incident_id=incident.incident_id,
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"PagerDuty page sent to: {target}",
                details={"simulated": True},
            )

        # Real PagerDuty client integration
        try:
            # Add responder to existing incident
            await self.pagerduty_client.add_responder(
                incident_id=incident.incident_id,
                responder_id=target,
                message=action.params.get(
                    "message", f"Escalation: {incident.title}"
                ),
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"PagerDuty responder added: {target}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"PagerDuty error: {str(e)}",
            )

    async def _page_opsgenie(
        self, action: EscalationAction, incident: IncidentState, target: str
    ) -> ActionResult:
        """Create Opsgenie alert or add responder."""
        if self.opsgenie_client is None:
            logger.info(
                "opsgenie_page_simulated",
                target=target,
                incident_id=incident.incident_id,
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Opsgenie page sent to: {target}",
                details={"simulated": True},
            )

        # Real Opsgenie client integration
        try:
            await self.opsgenie_client.add_responder(
                alert_id=incident.incident_id,
                responder={"type": "user", "id": target},
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Opsgenie responder added: {target}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Opsgenie error: {str(e)}",
            )


class UpdateSeverityHandler(ActionHandler):
    """Handler for updating incident severity."""

    def __init__(
        self,
        pagerduty_client: Any | None = None,
        opsgenie_client: Any | None = None,
        state_store: Any | None = None,
    ):
        self.pagerduty_client = pagerduty_client
        self.opsgenie_client = opsgenie_client
        self.state_store = state_store

    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Update incident severity."""
        new_severity = action.params.get("severity") or action.target
        if not new_severity:
            return ActionResult(
                success=False,
                action=action,
                error="No new severity specified",
            )

        old_severity = incident.severity

        # Validate severity
        valid_severities = ["critical", "high", "medium", "low", "info"]
        if new_severity.lower() not in valid_severities:
            return ActionResult(
                success=False,
                action=action,
                error=f"Invalid severity: {new_severity}",
            )

        try:
            # Update in source system
            if incident.source == "pagerduty" and self.pagerduty_client:
                await self.pagerduty_client.update_incident(
                    incident_id=incident.incident_id,
                    urgency="high" if new_severity in ["critical", "high"] else "low",
                )
            elif incident.source == "opsgenie" and self.opsgenie_client:
                await self.opsgenie_client.update_alert_priority(
                    alert_id=incident.incident_id,
                    priority=self._severity_to_opsgenie_priority(new_severity),
                )

            # Update local state
            if self.state_store:
                await self.state_store.update_incident_severity(
                    incident.incident_id, new_severity
                )

            logger.info(
                "severity_updated",
                incident_id=incident.incident_id,
                old_severity=old_severity,
                new_severity=new_severity,
            )

            return ActionResult(
                success=True,
                action=action,
                message=f"Severity updated: {old_severity} -> {new_severity}",
                details={
                    "old_severity": old_severity,
                    "new_severity": new_severity,
                },
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Failed to update severity: {str(e)}",
            )

    def _severity_to_opsgenie_priority(self, severity: str) -> str:
        """Map severity to Opsgenie priority."""
        mapping = {
            "critical": "P1",
            "high": "P2",
            "medium": "P3",
            "low": "P4",
            "info": "P5",
        }
        return mapping.get(severity.lower(), "P3")


class AutoAssignHandler(ActionHandler):
    """Handler for auto-assigning incidents."""

    def __init__(
        self,
        pagerduty_client: Any | None = None,
        opsgenie_client: Any | None = None,
        team_resolver: Any | None = None,
    ):
        self.pagerduty_client = pagerduty_client
        self.opsgenie_client = opsgenie_client
        self.team_resolver = team_resolver

    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Auto-assign incident to user or team."""
        target = action.target or action.target_id
        assignment_type = action.params.get("type", "user")  # user, team, oncall

        if not target and assignment_type != "oncall":
            return ActionResult(
                success=False,
                action=action,
                error="No assignment target specified",
            )

        try:
            if assignment_type == "oncall":
                # Resolve on-call person for the service/team
                target = await self._resolve_oncall(incident, action)
                if not target:
                    return ActionResult(
                        success=False,
                        action=action,
                        error="Could not resolve on-call person",
                    )

            # Perform assignment
            if incident.source == "pagerduty" and self.pagerduty_client:
                await self.pagerduty_client.assign_incident(
                    incident_id=incident.incident_id,
                    assignee_id=target,
                )
            elif incident.source == "opsgenie" and self.opsgenie_client:
                await self.opsgenie_client.assign_alert(
                    alert_id=incident.incident_id,
                    owner=target,
                )

            logger.info(
                "incident_auto_assigned",
                incident_id=incident.incident_id,
                assignee=target,
                assignment_type=assignment_type,
            )

            return ActionResult(
                success=True,
                action=action,
                message=f"Incident assigned to: {target}",
                details={
                    "assignee": target,
                    "assignment_type": assignment_type,
                },
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Failed to assign: {str(e)}",
            )

    async def _resolve_oncall(
        self, incident: IncidentState, action: EscalationAction
    ) -> str | None:
        """Resolve the on-call person for the incident."""
        schedule_id = action.params.get("schedule_id")
        team_id = action.params.get("team_id") or incident.team_id

        if self.team_resolver:
            try:
                oncall = await self.team_resolver.get_oncall(
                    schedule_id=schedule_id,
                    team_id=team_id,
                    service=incident.service,
                )
                return oncall.id if oncall else None
            except Exception as e:
                logger.warning("oncall_resolution_failed", error=str(e))

        # Fallback to action target
        return action.target


class EscalateToManagerHandler(ActionHandler):
    """Handler for escalating to manager."""

    def __init__(
        self,
        org_resolver: Any | None = None,
        notify_handler: NotifyHandler | None = None,
        page_handler: PageHandler | None = None,
    ):
        self.org_resolver = org_resolver
        self.notify_handler = notify_handler or NotifyHandler()
        self.page_handler = page_handler or PageHandler()

    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Escalate incident to manager."""
        # Get manager from action params or resolve from org
        manager = action.target or action.params.get("manager_id")

        if not manager and self.org_resolver:
            # Try to resolve manager from assigned user(s)
            for assignee in incident.assigned_to:
                try:
                    manager = await self.org_resolver.get_manager(assignee)
                    if manager:
                        break
                except Exception:
                    pass

        if not manager:
            return ActionResult(
                success=False,
                action=action,
                error="Could not determine manager to escalate to",
            )

        # Determine escalation method
        escalation_method = action.params.get("method", "page")

        if escalation_method == "page":
            page_action = EscalationAction(
                action_type=ActionType.PAGE,
                target=manager,
                params=action.params,
            )
            result = await self.page_handler.execute(page_action, incident)
        else:
            notify_action = EscalationAction(
                action_type=ActionType.NOTIFY,
                target=manager,
                params={
                    "channel": escalation_method,
                    "message": f"🔺 Escalation: {incident.title} requires attention",
                    **action.params,
                },
            )
            result = await self.notify_handler.execute(notify_action, incident)

        if result.success:
            result.message = f"Escalated to manager: {manager}"
            result.details["manager"] = manager

        return result


class AddResponderHandler(ActionHandler):
    """Handler for adding additional responders."""

    def __init__(
        self,
        pagerduty_client: Any | None = None,
        opsgenie_client: Any | None = None,
    ):
        self.pagerduty_client = pagerduty_client
        self.opsgenie_client = opsgenie_client

    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Add additional responder to incident."""
        responder = action.target or action.target_id
        if not responder:
            return ActionResult(
                success=False,
                action=action,
                error="No responder specified",
            )

        try:
            if incident.source == "pagerduty" and self.pagerduty_client:
                await self.pagerduty_client.add_responder(
                    incident_id=incident.incident_id,
                    responder_id=responder,
                    message=action.params.get("message", "Additional help requested"),
                )
            elif incident.source == "opsgenie" and self.opsgenie_client:
                responder_type = action.params.get("responder_type", "user")
                await self.opsgenie_client.add_responder(
                    alert_id=incident.incident_id,
                    responder={"type": responder_type, "id": responder},
                )
            else:
                logger.info(
                    "add_responder_simulated",
                    incident_id=incident.incident_id,
                    responder=responder,
                )

            return ActionResult(
                success=True,
                action=action,
                message=f"Added responder: {responder}",
                details={"responder": responder},
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Failed to add responder: {str(e)}",
            )


class PostToChannelHandler(ActionHandler):
    """Handler for posting to Slack/Teams channels."""

    def __init__(self, slack_client: Any | None = None):
        self.slack_client = slack_client

    async def execute(
        self, action: EscalationAction, incident: IncidentState
    ) -> ActionResult:
        """Post update to channel."""
        channel = action.target or action.params.get("channel")
        if not channel:
            return ActionResult(
                success=False,
                action=action,
                error="No channel specified",
            )

        message = action.params.get("message", self._default_message(incident))

        if self.slack_client is None:
            logger.info(
                "channel_post_simulated",
                channel=channel,
                message=message[:100],
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Posted to channel: {channel}",
                details={"simulated": True},
            )

        try:
            await self.slack_client.post_message(
                channel=channel,
                text=message,
            )
            return ActionResult(
                success=True,
                action=action,
                message=f"Posted to channel: {channel}",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action=action,
                error=f"Failed to post: {str(e)}",
            )

    def _default_message(self, incident: IncidentState) -> str:
        return (
            f"🚨 *Escalation Update*\n"
            f"Incident: {incident.title}\n"
            f"Service: {incident.service}\n"
            f"Severity: {incident.severity}\n"
            f"Duration: {int(incident.minutes_since_triggered)} minutes"
        )


# Handler registry
_HANDLERS: dict[ActionType, type[ActionHandler]] = {
    ActionType.NOTIFY: NotifyHandler,
    ActionType.PAGE: PageHandler,
    ActionType.UPDATE_SEVERITY: UpdateSeverityHandler,
    ActionType.AUTO_ASSIGN: AutoAssignHandler,
    ActionType.ESCALATE_TO_MANAGER: EscalateToManagerHandler,
    ActionType.ADD_RESPONDER: AddResponderHandler,
    ActionType.POST_TO_CHANNEL: PostToChannelHandler,
}

# Handler instances (can be replaced with configured instances)
_handler_instances: dict[ActionType, ActionHandler] = {}


def get_action_handler(action_type: ActionType) -> ActionHandler | None:
    """Get the appropriate handler for an action type."""
    if action_type in _handler_instances:
        return _handler_instances[action_type]

    handler_class = _HANDLERS.get(action_type)
    if handler_class:
        handler = handler_class()
        _handler_instances[action_type] = handler
        return handler

    return None


def register_action_handler(
    action_type: ActionType, handler: ActionHandler
) -> None:
    """Register a custom action handler instance."""
    _handler_instances[action_type] = handler


async def execute_action(
    action: EscalationAction, incident: IncidentState
) -> ActionResult:
    """Execute a single action.

    Args:
        action: The action to execute
        incident: The current incident state

    Returns:
        ActionResult with success/failure status
    """
    handler = get_action_handler(action.action_type)
    if handler is None:
        logger.warning(
            "no_handler_for_action_type",
            action_type=action.action_type,
        )
        return ActionResult(
            success=False,
            action=action,
            error=f"No handler for action type: {action.action_type}",
        )

    return await handler.execute_with_retry(action, incident)


async def execute_actions(
    actions: list[EscalationAction], incident: IncidentState
) -> list[ActionResult]:
    """Execute multiple actions concurrently.

    Args:
        actions: List of actions to execute
        incident: The current incident state

    Returns:
        List of ActionResults
    """
    if not actions:
        return []

    results = await asyncio.gather(
        *[execute_action(action, incident) for action in actions],
        return_exceptions=True,
    )

    # Convert exceptions to ActionResults
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append(
                ActionResult(
                    success=False,
                    action=actions[i],
                    error=str(result),
                )
            )
        else:
            processed_results.append(result)

    return processed_results
