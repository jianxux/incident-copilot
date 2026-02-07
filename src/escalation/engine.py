"""
Policy Engine - Condition evaluation and action execution.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .models import (
    ActionType,
    EscalationAction,
    EscalationCondition,
    EscalationLevel,
    EscalationPolicy,
    EscalationState,
    OnCallAssignment,
    TimeWindow,
)
from .service import EscalationService

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes escalation actions."""

    def __init__(self):
        self._handlers: dict[
            ActionType, Callable[[EscalationAction, dict], Awaitable[bool]]
        ] = {
            ActionType.PAGE: self._send_page,
            ActionType.EMAIL: self._send_email,
            ActionType.SLACK: self._send_slack,
            ActionType.PHONE: self._make_phone_call,
            ActionType.SMS: self._send_sms,
            ActionType.WEBHOOK: self._call_webhook,
        }

    async def execute(
        self,
        action: EscalationAction,
        context: dict[str, Any],
        oncall: OnCallAssignment | None = None,
    ) -> bool:
        """Execute an escalation action with retry logic."""
        handler = self._handlers.get(action.action_type)
        if not handler:
            logger.error(f"No handler for action type: {action.action_type}")
            return False

        # Resolve target from on-call if needed
        target = self._resolve_target(action, oncall)
        context["_target"] = target
        context["_action"] = action

        for attempt in range(action.retry_count + 1):
            try:
                success = await handler(action, context)
                if success:
                    logger.info(
                        f"Action {action.action_type} executed successfully to {target}"
                    )
                    return True
            except Exception as e:
                logger.warning(
                    f"Action {action.action_type} failed (attempt {attempt + 1}): {e}"
                )

            if attempt < action.retry_count:
                await asyncio.sleep(action.retry_delay_seconds)

        logger.error(
            f"Action {action.action_type} failed after {action.retry_count + 1} attempts"
        )
        return False

    def _resolve_target(
        self, action: EscalationAction, oncall: OnCallAssignment | None
    ) -> str:
        """Resolve the action target, preferring on-call if available."""
        if not oncall:
            return action.target

        if action.action_type == ActionType.EMAIL:
            return oncall.user_email
        elif action.action_type in (ActionType.PHONE, ActionType.SMS):
            return oncall.user_phone or action.target
        elif action.action_type == ActionType.SLACK:
            return oncall.slack_id or action.target
        else:
            return action.target

    def _render_template(self, template: str | None, context: dict[str, Any]) -> str:
        """Render a message template with context variables."""
        if not template:
            return (
                f"Escalation alert for incident {context.get('incident_id', 'unknown')}"
            )

        # Simple template rendering with {variable} syntax
        result = template
        for key, value in context.items():
            if not key.startswith("_"):
                result = result.replace(f"{{{key}}}", str(value))
        return result

    async def _send_page(
        self, action: EscalationAction, context: dict[str, Any]
    ) -> bool:
        """Send a page (PagerDuty, Opsgenie, etc.)."""
        target = context["_target"]
        message = self._render_template(action.template, context)
        logger.info(f"[MOCK] Paging {target}: {message}")
        # TODO: Integrate with PagerDuty/Opsgenie API
        return True

    async def _send_email(
        self, action: EscalationAction, context: dict[str, Any]
    ) -> bool:
        """Send an email notification."""
        target = context["_target"]
        self._render_template(action.template, context)
        subject = f"[ESCALATION] Incident {context.get('incident_id', 'unknown')}"
        logger.info(f"[MOCK] Emailing {target}: {subject}")
        # TODO: Integrate with email service
        return True

    async def _send_slack(
        self, action: EscalationAction, context: dict[str, Any]
    ) -> bool:
        """Send a Slack notification."""
        target = context["_target"]
        message = self._render_template(action.template, context)
        logger.info(f"[MOCK] Slacking {target}: {message}")
        # TODO: Integrate with Slack API
        return True

    async def _make_phone_call(
        self, action: EscalationAction, context: dict[str, Any]
    ) -> bool:
        """Make a phone call (Twilio, etc.)."""
        target = context["_target"]
        message = self._render_template(action.template, context)
        logger.info(f"[MOCK] Calling {target}: {message}")
        # TODO: Integrate with Twilio API
        return True

    async def _send_sms(
        self, action: EscalationAction, context: dict[str, Any]
    ) -> bool:
        """Send an SMS message."""
        target = context["_target"]
        message = self._render_template(action.template, context)
        logger.info(f"[MOCK] SMS to {target}: {message}")
        # TODO: Integrate with SMS service
        return True

    async def _call_webhook(
        self, action: EscalationAction, context: dict[str, Any]
    ) -> bool:
        """Call a webhook URL."""
        target = context["_target"]
        logger.info(f"[MOCK] Webhook to {target}")
        # TODO: Make HTTP request to webhook
        return True


class ConditionEvaluator:
    """Evaluates escalation conditions."""

    def __init__(self):
        self._custom_evaluators: dict[str, Callable[[Any, Any], bool]] = {}

    def register_evaluator(self, field: str, evaluator: Callable[[Any, Any], bool]):
        """Register a custom evaluator for a field."""
        self._custom_evaluators[field] = evaluator

    def evaluate(self, condition: EscalationCondition, context: dict[str, Any]) -> bool:
        """Evaluate a single condition against context."""
        # Check time window first
        if condition.time_window:
            if not self._check_time_window(condition.time_window):
                return False

        # Check custom evaluator
        if condition.field in self._custom_evaluators:
            field_value = context.get(condition.field)
            return self._custom_evaluators[condition.field](
                field_value, condition.value
            )

        # Use the condition's built-in matching
        return condition.matches(context)

    def evaluate_all(
        self,
        conditions: list[EscalationCondition],
        context: dict[str, Any],
        match_all: bool = True,
    ) -> bool:
        """Evaluate multiple conditions."""
        if not conditions:
            return True

        results = [self.evaluate(c, context) for c in conditions]
        return all(results) if match_all else any(results)

    def _check_time_window(self, window: TimeWindow) -> bool:
        """Check if current time is within the time window."""
        try:
            tz = ZoneInfo(window.timezone)
        except Exception:
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)
        current_time = now.time()
        current_day = now.weekday()

        # Check day of week
        if current_day not in window.days_of_week:
            return False

        # Check time range (handles overnight windows)
        if window.start_time <= window.end_time:
            return window.start_time <= current_time <= window.end_time
        else:
            # Overnight window (e.g., 22:00 - 06:00)
            return current_time >= window.start_time or current_time <= window.end_time


class PolicyEngine:
    """Main policy engine for escalation management."""

    def __init__(self, service: EscalationService):
        self.service = service
        self.executor = ActionExecutor()
        self.evaluator = ConditionEvaluator()

    async def evaluate_incident(
        self, incident_id: str, context: dict[str, Any]
    ) -> EscalationPolicy | None:
        """Find and return the matching policy for an incident."""
        return await self.service.find_matching_policy(context)

    async def should_escalate(
        self, state: EscalationState, context: dict[str, Any]
    ) -> bool:
        """Determine if an incident should be escalated."""
        policy = await self.service.get_policy(state.policy_id)
        if not policy or not policy.enabled:
            return False

        # Check if paused
        if state.is_paused:
            if state.paused_until and state.paused_until <= datetime.utcnow():
                state.is_paused = False
            else:
                return False

        # Check if time for next escalation
        if state.next_escalation_at:
            if datetime.utcnow() < state.next_escalation_at:
                return False

        # Get next level and check its conditions
        next_level, _ = await self.service.get_next_level(state.incident_id)
        if not next_level:
            return False

        # Evaluate level-specific conditions
        if next_level.conditions:
            if not self.evaluator.evaluate_all(next_level.conditions, context):
                return False

        return True

    async def execute_escalation(
        self, state: EscalationState, context: dict[str, Any]
    ) -> bool:
        """Execute escalation to the next level."""
        policy = await self.service.get_policy(state.policy_id)
        if not policy:
            return False

        # Escalate to next level
        updated_state = await self.service.escalate(state.incident_id)
        if not updated_state:
            return False

        # Get the current level config
        level = self._get_level(policy, updated_state.current_level)
        if not level:
            return False

        # Get on-call if needed
        oncall = None
        if level.use_oncall and level.team_id:
            oncall = await self.service.get_oncall(level.team_id)

        # Execute all actions for this level
        context["level"] = level.level
        context["level_name"] = level.name
        context["policy_name"] = policy.name

        success_count = 0
        for action in level.actions:
            if await self.executor.execute(action, context.copy(), oncall):
                success_count += 1

        return success_count > 0

    async def process_incident(
        self, incident_id: str, context: dict[str, Any]
    ) -> EscalationState | None:
        """Process an incident through the escalation engine."""
        # Get or create escalation state
        state = await self.service.get_escalation_state(incident_id)

        if not state:
            # Find matching policy
            policy = await self.evaluate_incident(incident_id, context)
            if not policy:
                logger.info(f"No matching policy for incident {incident_id}")
                return None

            # Start escalation
            state = await self.service.start_escalation(incident_id, policy, context)
            logger.info(
                f"Started escalation for {incident_id} with policy {policy.name}"
            )

        # Check for de-escalation first
        await self.service.check_deescalation(incident_id, context)

        # Check if should escalate
        if await self.should_escalate(state, context):
            await self.execute_escalation(state, context)

        return await self.service.get_escalation_state(incident_id)

    async def process_pending(self) -> list[EscalationState]:
        """Process all pending escalations."""
        pending = await self.service.get_pending_escalations()
        processed = []

        for state in pending:
            try:
                # Build minimal context
                context = {
                    "incident_id": state.incident_id,
                    "current_level": state.current_level,
                }

                if await self.should_escalate(state, context):
                    await self.execute_escalation(state, context)
                    processed.append(state)
            except Exception as e:
                logger.error(
                    f"Error processing escalation for {state.incident_id}: {e}"
                )

        return processed

    def _get_level(
        self, policy: EscalationPolicy, level_num: int
    ) -> EscalationLevel | None:
        """Get a specific level from a policy."""
        for level in policy.levels:
            if level.level == level_num:
                return level
        return None


# Global engine instance
_engine: PolicyEngine | None = None


def get_policy_engine(service: EscalationService | None = None) -> PolicyEngine:
    """Get or create the global policy engine."""
    global _engine
    if _engine is None:
        from .service import get_escalation_service

        _engine = PolicyEngine(service or get_escalation_service())
    return _engine
