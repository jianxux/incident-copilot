"""
AI-powered next-step suggestions for runbook execution.

Provides intelligent suggestions based on:
- Current execution state
- Incident context
- Historical patterns
- Step dependencies
"""

import json
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from .executor import RunbookExecution, StepStatus, StepType
from .progress import HistoricalMetrics, progress_tracker

logger = structlog.get_logger()


class SuggestionType(str, Enum):
    """Types of suggestions."""

    NEXT_STEP = "next_step"
    SKIP_RECOMMENDATION = "skip_recommendation"
    ROLLBACK_WARNING = "rollback_warning"
    PARALLEL_EXECUTION = "parallel_execution"
    ESCALATION = "escalation"
    DIAGNOSTIC = "diagnostic"
    AUTOMATION_HINT = "automation_hint"
    CONTEXT_UPDATE = "context_update"


class SuggestionPriority(str, Enum):
    """Priority levels for suggestions."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Suggestion(BaseModel):
    """A single suggestion for the next action."""

    suggestion_id: str
    suggestion_type: SuggestionType
    priority: SuggestionPriority
    title: str
    description: str
    rationale: str | None = None
    action_label: str | None = None  # e.g., "Execute Step", "Skip", "Escalate"
    action_step_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SuggestionsResponse(BaseModel):
    """Response containing multiple suggestions."""

    execution_id: str
    suggestions: list[Suggestion]
    ai_analysis: str | None = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SuggestionEngine:
    """
    AI-powered suggestion engine for runbook execution.

    Analyzes the current execution state and provides
    intelligent recommendations for next steps.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def get_suggestions(
        self,
        execution: RunbookExecution,
        incident_context: dict[str, Any] | None = None,
        max_suggestions: int = 5,
    ) -> SuggestionsResponse:
        """
        Get AI-powered suggestions for the current execution state.

        Args:
            execution: The current runbook execution
            incident_context: Additional context about the incident
            max_suggestions: Maximum number of suggestions to return

        Returns:
            SuggestionsResponse with prioritized suggestions
        """
        suggestions: list[Suggestion] = []

        # Get rule-based suggestions first
        suggestions.extend(self._get_next_step_suggestions(execution))
        suggestions.extend(self._get_skip_recommendations(execution))
        suggestions.extend(self._get_parallel_execution_suggestions(execution))
        suggestions.extend(self._get_rollback_warnings(execution))
        suggestions.extend(self._get_escalation_suggestions(execution, incident_context))
        suggestions.extend(await self._get_historical_suggestions(execution))

        # Get AI analysis if API key is available
        ai_analysis = None
        if self.settings.anthropic_api_key:
            ai_suggestions, ai_analysis = await self._get_ai_suggestions(
                execution, incident_context
            )
            suggestions.extend(ai_suggestions)

        # Sort by priority and limit
        priority_order = {
            SuggestionPriority.CRITICAL: 0,
            SuggestionPriority.HIGH: 1,
            SuggestionPriority.MEDIUM: 2,
            SuggestionPriority.LOW: 3,
            SuggestionPriority.INFO: 4,
        }
        suggestions.sort(key=lambda s: priority_order[s.priority])
        suggestions = suggestions[:max_suggestions]

        return SuggestionsResponse(
            execution_id=execution.execution_id,
            suggestions=suggestions,
            ai_analysis=ai_analysis,
        )

    def _get_next_step_suggestions(
        self, execution: RunbookExecution
    ) -> list[Suggestion]:
        """Get suggestions for the next step to execute."""
        suggestions = []

        # Find steps that can be executed now
        for step in execution.steps:
            if step.status != StepStatus.PENDING:
                continue

            # Check if dependencies are satisfied
            deps_satisfied = all(
                next(
                    (s for s in execution.steps if s.step_id == dep_id), None
                ).status
                in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                if any(s.step_id == dep_id for s in execution.steps)
                else True
                for dep_id in step.depends_on
            )

            if not deps_satisfied:
                continue

            # Create suggestion
            if step.step_type == StepType.AUTOMATED:
                suggestions.append(
                    Suggestion(
                        suggestion_id=f"next-{step.step_id}",
                        suggestion_type=SuggestionType.NEXT_STEP,
                        priority=SuggestionPriority.HIGH,
                        title=f"Execute automated step: {step.title}",
                        description=f"Ready to execute automated step {step.step_number}",
                        action_label="Execute",
                        action_step_id=step.step_id,
                        metadata={
                            "step_type": "automated",
                            "requires_approval": step.required_approval,
                        },
                    )
                )
            else:
                suggestions.append(
                    Suggestion(
                        suggestion_id=f"next-{step.step_id}",
                        suggestion_type=SuggestionType.NEXT_STEP,
                        priority=SuggestionPriority.MEDIUM,
                        title=f"Complete step: {step.title}",
                        description=f"Step {step.step_number} is ready for execution",
                        action_label="Start",
                        action_step_id=step.step_id,
                        metadata={"step_type": "manual"},
                    )
                )

            # Only suggest the first ready step
            break

        return suggestions

    def _get_skip_recommendations(
        self, execution: RunbookExecution
    ) -> list[Suggestion]:
        """Get recommendations for steps that could be skipped."""
        suggestions = []

        # Check context for skip conditions
        context = execution.context

        for step in execution.steps:
            if step.status != StepStatus.PENDING:
                continue

            # Check if step has skip conditions in metadata
            skip_reason = None

            # Example: Skip database rollback if no DB changes were made
            if "database" in step.title.lower() and context.get("no_db_changes"):
                skip_reason = "No database changes were made in this incident"

            # Example: Skip notification step if already notified
            if "notify" in step.title.lower() and context.get("already_notified"):
                skip_reason = "Stakeholders have already been notified"

            if skip_reason:
                suggestions.append(
                    Suggestion(
                        suggestion_id=f"skip-{step.step_id}",
                        suggestion_type=SuggestionType.SKIP_RECOMMENDATION,
                        priority=SuggestionPriority.LOW,
                        title=f"Consider skipping: {step.title}",
                        description=skip_reason,
                        rationale="Based on incident context, this step may not be necessary",
                        action_label="Skip",
                        action_step_id=step.step_id,
                    )
                )

        return suggestions

    def _get_parallel_execution_suggestions(
        self, execution: RunbookExecution
    ) -> list[Suggestion]:
        """Identify steps that can be executed in parallel."""
        suggestions = []

        # Find all pending steps with satisfied dependencies
        ready_steps = []
        for step in execution.steps:
            if step.status != StepStatus.PENDING:
                continue

            deps_satisfied = all(
                any(
                    s.step_id == dep_id
                    and s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                    for s in execution.steps
                )
                for dep_id in step.depends_on
            ) or not step.depends_on

            if deps_satisfied:
                ready_steps.append(step)

        # If multiple steps are ready, suggest parallel execution
        if len(ready_steps) > 1:
            step_titles = [s.title for s in ready_steps[:3]]
            suggestions.append(
                Suggestion(
                    suggestion_id="parallel-exec",
                    suggestion_type=SuggestionType.PARALLEL_EXECUTION,
                    priority=SuggestionPriority.MEDIUM,
                    title="Multiple steps can be executed in parallel",
                    description=f"These steps have no dependencies on each other: {', '.join(step_titles)}",
                    rationale="Parallel execution can reduce total resolution time",
                    metadata={
                        "parallel_step_ids": [s.step_id for s in ready_steps],
                    },
                )
            )

        return suggestions

    def _get_rollback_warnings(self, execution: RunbookExecution) -> list[Suggestion]:
        """Check for rollback-related warnings."""
        suggestions = []

        # Check if any completed steps have failed and have rollback procedures
        failed_with_rollback = [
            step
            for step in execution.steps
            if step.status == StepStatus.FAILED
            and step.has_rollback
            and not step.rollback_executed
        ]

        for step in failed_with_rollback:
            suggestions.append(
                Suggestion(
                    suggestion_id=f"rollback-{step.step_id}",
                    suggestion_type=SuggestionType.ROLLBACK_WARNING,
                    priority=SuggestionPriority.HIGH,
                    title=f"Rollback available for failed step: {step.title}",
                    description="This step failed and has a rollback procedure that hasn't been executed",
                    rationale="Consider executing rollback before proceeding",
                    action_label="Execute Rollback",
                    action_step_id=step.step_id,
                )
            )

        return suggestions

    def _get_escalation_suggestions(
        self,
        execution: RunbookExecution,
        incident_context: dict[str, Any] | None,
    ) -> list[Suggestion]:
        """Get escalation suggestions based on execution state."""
        suggestions = []

        # Check for stuck execution
        elapsed = (datetime.utcnow() - execution.started_at).total_seconds() / 60

        # If execution has been running too long
        if elapsed > 60 and execution.progress_percentage < 50:
            suggestions.append(
                Suggestion(
                    suggestion_id="escalate-slow",
                    suggestion_type=SuggestionType.ESCALATION,
                    priority=SuggestionPriority.HIGH,
                    title="Consider escalating - Slow progress",
                    description=f"Execution has been running for {int(elapsed)} minutes with only {execution.progress_percentage:.0f}% progress",
                    rationale="Runbook execution is taking longer than expected",
                    action_label="Escalate",
                )
            )

        # Check for high severity incidents
        if incident_context and incident_context.get("severity") in ("critical", "high"):
            if execution.failed_steps > 0:
                suggestions.append(
                    Suggestion(
                        suggestion_id="escalate-severity",
                        suggestion_type=SuggestionType.ESCALATION,
                        priority=SuggestionPriority.CRITICAL,
                        title="Escalate - High severity incident with failures",
                        description=f"{execution.failed_steps} step(s) have failed on a high-severity incident",
                        rationale="Failed steps on critical incidents may require additional expertise",
                        action_label="Escalate Now",
                    )
                )

        return suggestions

    async def _get_historical_suggestions(
        self, execution: RunbookExecution
    ) -> list[Suggestion]:
        """Get suggestions based on historical execution data."""
        suggestions = []

        metrics = await progress_tracker.get_historical_metrics(execution.runbook_id)
        if not metrics:
            return suggestions

        # Warn about common failure points
        current_step = execution.current_step
        if current_step and current_step.title in metrics.common_failure_points:
            suggestions.append(
                Suggestion(
                    suggestion_id="history-warning",
                    suggestion_type=SuggestionType.DIAGNOSTIC,
                    priority=SuggestionPriority.MEDIUM,
                    title=f"Attention: '{current_step.title}' commonly fails",
                    description="This step has a high failure rate in previous executions",
                    rationale=f"Based on {metrics.total_executions} historical executions",
                    metadata={
                        "failure_rate": metrics.failed_executions / metrics.total_executions
                        if metrics.total_executions > 0
                        else 0,
                    },
                )
            )

        return suggestions

    async def _get_ai_suggestions(
        self,
        execution: RunbookExecution,
        incident_context: dict[str, Any] | None,
    ) -> tuple[list[Suggestion], str | None]:
        """Get AI-generated suggestions using Claude."""
        suggestions = []
        analysis = None

        if not self.settings.anthropic_api_key:
            return suggestions, analysis

        try:
            # Build context for AI
            step_summaries = []
            for step in execution.steps:
                summary = {
                    "number": step.step_number,
                    "title": step.title,
                    "status": step.status.value,
                    "type": step.step_type.value,
                }
                if step.notes:
                    summary["notes"] = step.notes[:200]
                if step.automation_result and step.automation_result.error:
                    summary["error"] = step.automation_result.error[:200]
                step_summaries.append(summary)

            prompt = f"""You are an incident response expert helping an engineer execute a runbook.

Current runbook: {execution.runbook_title}
Progress: {execution.progress_percentage:.0f}% ({execution.completed_steps}/{execution.total_steps} steps)
Status: {execution.status}

Steps:
{json.dumps(step_summaries, indent=2)}

Incident context:
{json.dumps(incident_context or {}, indent=2)}

Based on the current state, provide:
1. A brief analysis of the situation (2-3 sentences)
2. The single most important recommendation for the next action

Respond in JSON format:
{{"analysis": "...", "recommendation": {{"title": "...", "description": "...", "priority": "high|medium|low"}}}}
"""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.settings.ai_model,
                        "max_tokens": 500,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=30,
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result.get("content", [{}])[0].get("text", "{}")

                    # Parse AI response
                    try:
                        ai_response = json.loads(content)
                        analysis = ai_response.get("analysis")

                        if "recommendation" in ai_response:
                            rec = ai_response["recommendation"]
                            priority_map = {
                                "high": SuggestionPriority.HIGH,
                                "medium": SuggestionPriority.MEDIUM,
                                "low": SuggestionPriority.LOW,
                            }
                            suggestions.append(
                                Suggestion(
                                    suggestion_id="ai-recommendation",
                                    suggestion_type=SuggestionType.DIAGNOSTIC,
                                    priority=priority_map.get(
                                        rec.get("priority", "medium"),
                                        SuggestionPriority.MEDIUM,
                                    ),
                                    title=rec.get("title", "AI Recommendation"),
                                    description=rec.get("description", ""),
                                    rationale="AI-generated based on execution state",
                                    metadata={"source": "ai"},
                                )
                            )
                    except json.JSONDecodeError:
                        # If JSON parsing fails, use raw text as analysis
                        analysis = content

        except Exception as e:
            logger.error("ai_suggestion_error", error=str(e))

        return suggestions, analysis

    async def get_diagnostic_suggestions(
        self,
        execution: RunbookExecution,
        failed_step_id: str | None = None,
    ) -> list[Suggestion]:
        """
        Get diagnostic suggestions for troubleshooting.

        Useful when a step fails and the engineer needs guidance.
        """
        suggestions = []

        # Find the failed step
        failed_step = None
        if failed_step_id:
            failed_step = next(
                (s for s in execution.steps if s.step_id == failed_step_id), None
            )
        else:
            # Find the most recent failed step
            failed_step = next(
                (s for s in reversed(execution.steps) if s.status == StepStatus.FAILED),
                None,
            )

        if not failed_step:
            return suggestions

        # Analyze the error
        error_message = ""
        if failed_step.automation_result and failed_step.automation_result.error:
            error_message = failed_step.automation_result.error

        # Common error patterns and suggestions
        error_suggestions = {
            "connection refused": Suggestion(
                suggestion_id="diag-connection",
                suggestion_type=SuggestionType.DIAGNOSTIC,
                priority=SuggestionPriority.HIGH,
                title="Connection Issue Detected",
                description="The target service may be down or unreachable",
                rationale="Verify the service is running and network connectivity",
            ),
            "permission denied": Suggestion(
                suggestion_id="diag-permission",
                suggestion_type=SuggestionType.DIAGNOSTIC,
                priority=SuggestionPriority.HIGH,
                title="Permission Issue Detected",
                description="The operation lacks required permissions",
                rationale="Check IAM roles, service account permissions, or sudo access",
            ),
            "timeout": Suggestion(
                suggestion_id="diag-timeout",
                suggestion_type=SuggestionType.DIAGNOSTIC,
                priority=SuggestionPriority.MEDIUM,
                title="Timeout Occurred",
                description="The operation took too long to complete",
                rationale="Consider increasing timeout or checking for resource contention",
            ),
            "not found": Suggestion(
                suggestion_id="diag-notfound",
                suggestion_type=SuggestionType.DIAGNOSTIC,
                priority=SuggestionPriority.MEDIUM,
                title="Resource Not Found",
                description="The target resource doesn't exist",
                rationale="Verify resource names and namespaces",
            ),
        }

        error_lower = error_message.lower()
        for pattern, suggestion in error_suggestions.items():
            if pattern in error_lower:
                suggestions.append(suggestion)

        # Generic suggestion if no specific pattern matched
        if not suggestions:
            suggestions.append(
                Suggestion(
                    suggestion_id="diag-generic",
                    suggestion_type=SuggestionType.DIAGNOSTIC,
                    priority=SuggestionPriority.MEDIUM,
                    title=f"Step failed: {failed_step.title}",
                    description=f"Error: {error_message[:200] if error_message else 'Unknown error'}",
                    rationale="Review the error message and check logs for more details",
                )
            )

        return suggestions


# Global suggestion engine instance
suggestion_engine = SuggestionEngine()
