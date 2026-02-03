"""Alert Correlation Engine - Reduce alert fatigue through intelligent grouping."""

from .engine import CorrelationEngine
from .models import (
    AlertGroup,
    AlertGroupStatus,
    CorrelationRule,
    CorrelationStrategy,
    IncomingAlert,
)
from .rules import RuleManager
from .store import CorrelationStore

__all__ = [
    "CorrelationEngine",
    "CorrelationStore",
    "RuleManager",
    "CorrelationRule",
    "CorrelationStrategy",
    "AlertGroup",
    "AlertGroupStatus",
    "IncomingAlert",
]
