"""
Escalation Policies Module

Multi-level escalation management for incident response with:
- Time-based and condition-based escalation
- On-call schedule integration
- Team rotation support
- Multiple notification channels (page, email, Slack, phone)
- De-escalation rules
- Full history tracking
"""

from .engine import (
    ActionExecutor,
    ConditionEvaluator,
    PolicyEngine,
    get_policy_engine,
)
from .models import (  # Enums; Core models; State and history; On-call; Request/Response
    ActionType,
    ConditionOperator,
    CreatePolicyRequest,
    DeescalationRule,
    EscalationAction,
    EscalationCondition,
    EscalationHistoryEntry,
    EscalationHistoryFilter,
    EscalationLevel,
    EscalationPolicy,
    EscalationState,
    EscalationStatus,
    OnCallAssignment,
    OverrideEscalationRequest,
    Severity,
    TeamRotation,
    TimeWindow,
    TriggerEscalationRequest,
    UpdatePolicyRequest,
)
from .routes import router
from .scheduler import (
    EscalationScheduler,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
)
from .service import (
    EscalationService,
    get_escalation_service,
)

__all__ = [
    # Enums
    "ActionType",
    "Severity",
    "EscalationStatus",
    "ConditionOperator",
    # Core models
    "TimeWindow",
    "EscalationCondition",
    "EscalationAction",
    "EscalationLevel",
    "EscalationPolicy",
    "DeescalationRule",
    # State and history
    "EscalationState",
    "EscalationHistoryEntry",
    # On-call
    "OnCallAssignment",
    "TeamRotation",
    # Request/Response
    "CreatePolicyRequest",
    "UpdatePolicyRequest",
    "TriggerEscalationRequest",
    "OverrideEscalationRequest",
    "EscalationHistoryFilter",
    # Service
    "EscalationService",
    "get_escalation_service",
    # Engine
    "PolicyEngine",
    "ActionExecutor",
    "ConditionEvaluator",
    "get_policy_engine",
    # Scheduler
    "EscalationScheduler",
    "get_scheduler",
    "start_scheduler",
    "stop_scheduler",
    # Router
    "router",
]
