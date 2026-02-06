"""Runbook auto-linking and execution module for Incident Copilot."""

from .automation import AutomationEngine, AutomationResult, AutomationType
from .executor import (
    AuditEntry,
    ExecutionStore,
    RunbookExecution,
    RunbookExecutor,
    RunbookStep,
    StepStatus,
    StepType,
    execution_store,
)
from .indexer import RunbookIndexer
from .linker import RunbookLinker
from .models import Runbook, RunbookMatch, RunbookSource, RunbookSourceType
from .progress import (
    ExecutionProgress,
    ExecutionSummary,
    HistoricalMetrics,
    ProgressTracker,
    StepProgress,
    progress_tracker,
)
from .routes import router as runbooks_execution_router
from .suggestions import (
    Suggestion,
    SuggestionEngine,
    SuggestionPriority,
    SuggestionsResponse,
    SuggestionType,
    suggestion_engine,
)

__all__ = [
    # Indexer & Linker
    "RunbookIndexer",
    "RunbookLinker",
    # Models
    "Runbook",
    "RunbookMatch",
    "RunbookSource",
    "RunbookSourceType",
    # Executor
    "RunbookExecutor",
    "RunbookExecution",
    "RunbookStep",
    "StepStatus",
    "StepType",
    "AuditEntry",
    "ExecutionStore",
    "execution_store",
    # Automation
    "AutomationEngine",
    "AutomationType",
    "AutomationResult",
    # Progress
    "ProgressTracker",
    "ExecutionProgress",
    "ExecutionSummary",
    "StepProgress",
    "HistoricalMetrics",
    "progress_tracker",
    # Suggestions
    "SuggestionEngine",
    "Suggestion",
    "SuggestionType",
    "SuggestionPriority",
    "SuggestionsResponse",
    "suggestion_engine",
    # Router
    "runbooks_execution_router",
]
