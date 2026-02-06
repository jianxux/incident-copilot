"""Condition evaluators for escalation rules.

Supports various condition types:
- Time-based (time since alert, time since ack)
- Severity-based
- Unacknowledged alerts
- No response from assignee
- Service tier conditions
- Custom expressions
"""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import structlog

from .models import (
    ConditionOperator,
    ConditionType,
    EscalationCondition,
    IncidentState,
    ServiceTier,
)

logger = structlog.get_logger()


class ConditionEvaluator(ABC):
    """Abstract base class for condition evaluators."""

    @abstractmethod
    def evaluate(
        self, condition: EscalationCondition, incident: IncidentState
    ) -> bool:
        """Evaluate the condition against an incident state.

        Args:
            condition: The condition to evaluate
            incident: The current incident state

        Returns:
            True if condition is met, False otherwise
        """
        pass

    def _compare(
        self, actual: Any, operator: ConditionOperator, expected: Any
    ) -> bool:
        """Compare actual value against expected using operator."""
        try:
            if operator == ConditionOperator.EQUALS:
                return actual == expected
            elif operator == ConditionOperator.NOT_EQUALS:
                return actual != expected
            elif operator == ConditionOperator.GREATER_THAN:
                return actual > expected
            elif operator == ConditionOperator.GREATER_THAN_OR_EQUALS:
                return actual >= expected
            elif operator == ConditionOperator.LESS_THAN:
                return actual < expected
            elif operator == ConditionOperator.LESS_THAN_OR_EQUALS:
                return actual <= expected
            elif operator == ConditionOperator.IN:
                if isinstance(expected, (list, tuple, set)):
                    return actual in expected
                return actual in str(expected).split(",")
            elif operator == ConditionOperator.NOT_IN:
                if isinstance(expected, (list, tuple, set)):
                    return actual not in expected
                return actual not in str(expected).split(",")
            elif operator == ConditionOperator.CONTAINS:
                return str(expected) in str(actual)
            elif operator == ConditionOperator.MATCHES:
                return bool(re.match(str(expected), str(actual)))
            else:
                logger.warning("unknown_operator", operator=operator)
                return False
        except (TypeError, ValueError) as e:
            logger.warning(
                "comparison_error",
                actual=actual,
                operator=operator,
                expected=expected,
                error=str(e),
            )
            return False


class TimeBasedCondition(ConditionEvaluator):
    """Evaluates time-based conditions (minutes since alert/ack)."""

    def evaluate(
        self, condition: EscalationCondition, incident: IncidentState
    ) -> bool:
        """Evaluate time-based condition.

        Supports:
        - TIME_SINCE_ALERT: Minutes since incident was triggered
        - TIME_SINCE_ACK: Minutes since incident was acknowledged
        """
        if condition.condition_type == ConditionType.TIME_SINCE_ALERT:
            actual_minutes = incident.minutes_since_triggered
        elif condition.condition_type == ConditionType.TIME_SINCE_ACK:
            actual_minutes = incident.minutes_since_acknowledged
            if actual_minutes is None:
                # Not acknowledged, so time_since_ack conditions don't apply
                return False
        else:
            return False

        expected_minutes = float(condition.value)

        result = self._compare(actual_minutes, condition.operator, expected_minutes)

        logger.debug(
            "time_condition_evaluated",
            condition_type=condition.condition_type,
            actual_minutes=actual_minutes,
            expected_minutes=expected_minutes,
            operator=condition.operator,
            result=result,
        )

        return result


class SeverityCondition(ConditionEvaluator):
    """Evaluates severity-based conditions."""

    # Severity ordering (lower index = higher severity)
    SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

    def evaluate(
        self, condition: EscalationCondition, incident: IncidentState
    ) -> bool:
        """Evaluate severity condition.

        Supports string comparison and severity level comparison.
        """
        if condition.condition_type != ConditionType.SEVERITY:
            return False

        actual_severity = incident.severity.lower()
        expected_severity = str(condition.value).lower()

        # For ordering comparisons, use severity index
        if condition.operator in (
            ConditionOperator.GREATER_THAN,
            ConditionOperator.GREATER_THAN_OR_EQUALS,
            ConditionOperator.LESS_THAN,
            ConditionOperator.LESS_THAN_OR_EQUALS,
        ):
            actual_idx = self._get_severity_index(actual_severity)
            expected_idx = self._get_severity_index(expected_severity)

            # Lower index = higher severity, so flip comparison
            # "greater than high" means "more severe than high" = critical
            result = self._compare(expected_idx, condition.operator, actual_idx)
        else:
            # Direct string comparison
            result = self._compare(actual_severity, condition.operator, expected_severity)

        logger.debug(
            "severity_condition_evaluated",
            actual_severity=actual_severity,
            expected_severity=expected_severity,
            operator=condition.operator,
            result=result,
        )

        return result

    def _get_severity_index(self, severity: str) -> int:
        """Get severity index (lower = more severe)."""
        try:
            return self.SEVERITY_ORDER.index(severity.lower())
        except ValueError:
            return len(self.SEVERITY_ORDER)  # Unknown severity is lowest


class UnacknowledgedCondition(ConditionEvaluator):
    """Evaluates whether an incident is unacknowledged."""

    def evaluate(
        self, condition: EscalationCondition, incident: IncidentState
    ) -> bool:
        """Evaluate unacknowledged condition.

        If value is True, condition is met when incident is NOT acknowledged.
        If value is False, condition is met when incident IS acknowledged.
        """
        if condition.condition_type != ConditionType.UNACKNOWLEDGED:
            return False

        # value=True means "is unacknowledged"
        expect_unacked = bool(condition.value)
        is_unacked = not incident.is_acknowledged

        result = expect_unacked == is_unacked

        logger.debug(
            "unacknowledged_condition_evaluated",
            is_acknowledged=incident.is_acknowledged,
            expect_unacked=expect_unacked,
            result=result,
        )

        return result


class NoResponseCondition(ConditionEvaluator):
    """Evaluates no-response conditions (no activity from assignee)."""

    def evaluate(
        self, condition: EscalationCondition, incident: IncidentState
    ) -> bool:
        """Evaluate no-response condition.

        Checks if there's been no activity for specified minutes.
        """
        if condition.condition_type != ConditionType.NO_RESPONSE:
            return False

        expected_minutes = float(condition.value)

        # Check last activity time
        if incident.last_activity_at is None:
            # No activity recorded, use triggered_at
            minutes_inactive = incident.minutes_since_triggered
        else:
            minutes_inactive = incident.minutes_since_last_activity or 0

        result = self._compare(minutes_inactive, condition.operator, expected_minutes)

        logger.debug(
            "no_response_condition_evaluated",
            minutes_inactive=minutes_inactive,
            expected_minutes=expected_minutes,
            operator=condition.operator,
            result=result,
        )

        return result


class ServiceTierCondition(ConditionEvaluator):
    """Evaluates service tier conditions."""

    # Tier ordering (lower index = higher tier)
    TIER_ORDER = [
        ServiceTier.CRITICAL,
        ServiceTier.HIGH,
        ServiceTier.MEDIUM,
        ServiceTier.LOW,
    ]

    def evaluate(
        self, condition: EscalationCondition, incident: IncidentState
    ) -> bool:
        """Evaluate service tier condition."""
        if condition.condition_type != ConditionType.SERVICE_TIER:
            return False

        if incident.service_tier is None:
            # No tier assigned, default to medium
            actual_tier = ServiceTier.MEDIUM
        else:
            actual_tier = incident.service_tier

        expected_tier = self._parse_tier(condition.value)
        if expected_tier is None:
            return False

        # For ordering comparisons, use tier index
        if condition.operator in (
            ConditionOperator.GREATER_THAN,
            ConditionOperator.GREATER_THAN_OR_EQUALS,
            ConditionOperator.LESS_THAN,
            ConditionOperator.LESS_THAN_OR_EQUALS,
        ):
            actual_idx = self._get_tier_index(actual_tier)
            expected_idx = self._get_tier_index(expected_tier)

            # Lower index = higher tier, so flip comparison
            result = self._compare(expected_idx, condition.operator, actual_idx)
        else:
            result = self._compare(actual_tier, condition.operator, expected_tier)

        logger.debug(
            "service_tier_condition_evaluated",
            actual_tier=actual_tier,
            expected_tier=expected_tier,
            operator=condition.operator,
            result=result,
        )

        return result

    def _parse_tier(self, value: Any) -> ServiceTier | None:
        """Parse tier from value."""
        if isinstance(value, ServiceTier):
            return value
        try:
            return ServiceTier(str(value).lower())
        except ValueError:
            logger.warning("invalid_service_tier", value=value)
            return None

    def _get_tier_index(self, tier: ServiceTier) -> int:
        """Get tier index (lower = higher priority tier)."""
        try:
            return self.TIER_ORDER.index(tier)
        except ValueError:
            return len(self.TIER_ORDER)


class CustomCondition(ConditionEvaluator):
    """Evaluates custom field-based conditions."""

    def evaluate(
        self, condition: EscalationCondition, incident: IncidentState
    ) -> bool:
        """Evaluate custom condition against incident fields or tags."""
        if condition.condition_type != ConditionType.CUSTOM:
            return False

        if not condition.field:
            logger.warning("custom_condition_missing_field")
            return False

        # Try to get value from incident attributes or tags
        actual_value = self._get_field_value(incident, condition.field)

        result = self._compare(actual_value, condition.operator, condition.value)

        logger.debug(
            "custom_condition_evaluated",
            field=condition.field,
            actual_value=actual_value,
            expected_value=condition.value,
            operator=condition.operator,
            result=result,
        )

        return result

    def _get_field_value(self, incident: IncidentState, field: str) -> Any:
        """Get value from incident by field path."""
        # Check direct attributes first
        if hasattr(incident, field):
            return getattr(incident, field)

        # Check tags
        if field.startswith("tags."):
            tag_key = field[5:]  # Remove "tags." prefix
            return incident.tags.get(tag_key)

        # Support nested field access with dots
        parts = field.split(".")
        value: Any = incident
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
            if value is None:
                return None

        return value


# Registry of condition evaluators
_EVALUATORS: dict[ConditionType, ConditionEvaluator] = {
    ConditionType.TIME_SINCE_ALERT: TimeBasedCondition(),
    ConditionType.TIME_SINCE_ACK: TimeBasedCondition(),
    ConditionType.SEVERITY: SeverityCondition(),
    ConditionType.UNACKNOWLEDGED: UnacknowledgedCondition(),
    ConditionType.NO_RESPONSE: NoResponseCondition(),
    ConditionType.SERVICE_TIER: ServiceTierCondition(),
    ConditionType.CUSTOM: CustomCondition(),
}


def get_condition_evaluator(condition_type: ConditionType) -> ConditionEvaluator | None:
    """Get the appropriate evaluator for a condition type."""
    return _EVALUATORS.get(condition_type)


def evaluate_condition(
    condition: EscalationCondition, incident: IncidentState
) -> bool:
    """Evaluate a single condition against an incident.

    Args:
        condition: The condition to evaluate
        incident: The current incident state

    Returns:
        True if condition is met, False otherwise
    """
    evaluator = get_condition_evaluator(condition.condition_type)
    if evaluator is None:
        logger.warning(
            "no_evaluator_for_condition_type",
            condition_type=condition.condition_type,
        )
        return False

    return evaluator.evaluate(condition, incident)


def evaluate_conditions(
    conditions: list[EscalationCondition],
    incident: IncidentState,
    require_all: bool = True,
) -> bool:
    """Evaluate multiple conditions against an incident.

    Args:
        conditions: List of conditions to evaluate
        incident: The current incident state
        require_all: If True, all conditions must be met (AND).
                    If False, any condition can be met (OR).

    Returns:
        True if conditions are satisfied, False otherwise
    """
    if not conditions:
        return True  # No conditions = always match

    results = [evaluate_condition(c, incident) for c in conditions]

    if require_all:
        return all(results)
    return any(results)
