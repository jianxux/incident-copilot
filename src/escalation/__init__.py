"""Escalation Rules Engine for incident management.

This module provides:
- EscalationRule, EscalationPolicy, EscalationAction models
- Condition evaluation (time-based, severity, unacknowledged, service tier)
- Action handlers (notify, page, update severity, auto-assign)
- Background scheduler for automatic escalations
- API routes for managing escalation policies
"""

from .actions import (
    ActionHandler,
    AutoAssignHandler,
    NotifyHandler,
    PageHandler,
    UpdateSeverityHandler,
    get_action_handler,
)
from .conditions import (
    ConditionEvaluator,
    NoResponseCondition,
    ServiceTierCondition,
    SeverityCondition,
    TimeBasedCondition,
    UnacknowledgedCondition,
)
from .engine import EscalationEngine, get_escalation_engine, shutdown_escalation_engine
from .models import (
    ActionType,
    ConditionOperator,
    ConditionType,
    EscalationAction,
    EscalationAuditEntry,
    EscalationCondition,
    EscalationPolicy,
    EscalationResult,
    EscalationRule,
    EscalationStep,
    IncidentState,
    MaintenanceWindow,
    ServiceTier,
)
from .scheduler import EscalationScheduler

__all__ = [
    # Models
    "ActionType",
    "ConditionOperator",
    "ConditionType",
    "EscalationAction",
    "EscalationAuditEntry",
    "EscalationCondition",
    "EscalationPolicy",
    "EscalationResult",
    "EscalationRule",
    "EscalationStep",
    "IncidentState",
    "MaintenanceWindow",
    "ServiceTier",
    # Conditions
    "ConditionEvaluator",
    "NoResponseCondition",
    "ServiceTierCondition",
    "SeverityCondition",
    "TimeBasedCondition",
    "UnacknowledgedCondition",
    # Actions
    "ActionHandler",
    "AutoAssignHandler",
    "NotifyHandler",
    "PageHandler",
    "UpdateSeverityHandler",
    "get_action_handler",
    # Engine
    "EscalationEngine",
    "get_escalation_engine",
    "shutdown_escalation_engine",
    # Scheduler
    "EscalationScheduler",
]
