"""
Runbook execution progress tracking.

Provides:
- Real-time progress tracking
- Estimated time remaining calculations
- Progress notifications
- Historical execution metrics
"""

from datetime import datetime, timedelta
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .executor import (
    ExecutionStore,
    RunbookExecution,
    StepStatus,
    execution_store,
)

logger = structlog.get_logger()


class StepProgress(BaseModel):
    """Progress information for a single step."""

    step_id: str
    step_number: int
    title: str
    status: StepStatus
    is_current: bool = False
    duration_seconds: float | None = None
    estimated_duration_minutes: int | None = None
    notes: str | None = None
    completed_by: str | None = None
    has_rollback: bool = False
    rollback_executed: bool = False


class ExecutionProgress(BaseModel):
    """Overall progress of a runbook execution."""

    execution_id: str
    runbook_id: str
    runbook_title: str
    incident_id: str | None = None

    # Status
    status: str  # active, paused, completed, aborted, rolled_back
    started_at: datetime
    completed_at: datetime | None = None
    last_activity_at: datetime

    # Progress metrics
    total_steps: int
    completed_steps: int
    skipped_steps: int
    failed_steps: int
    pending_steps: int
    progress_percentage: float

    # Time estimates
    elapsed_seconds: float
    estimated_remaining_minutes: int | None = None
    estimated_completion_at: datetime | None = None

    # Current step info
    current_step: StepProgress | None = None

    # Step breakdown
    steps: list[StepProgress] = Field(default_factory=list)

    # Participants
    initiated_by: str | None = None
    participants: list[str] = Field(default_factory=list)


class ExecutionSummary(BaseModel):
    """Summary of an execution for listing."""

    execution_id: str
    runbook_title: str
    incident_id: str | None = None
    status: str
    progress_percentage: float
    started_at: datetime
    completed_at: datetime | None = None
    initiated_by: str | None = None
    total_steps: int
    completed_steps: int


class HistoricalMetrics(BaseModel):
    """Historical metrics for runbook executions."""

    runbook_id: str
    runbook_title: str
    total_executions: int
    successful_executions: int
    failed_executions: int
    aborted_executions: int
    average_duration_minutes: float | None = None
    median_duration_minutes: float | None = None
    min_duration_minutes: float | None = None
    max_duration_minutes: float | None = None
    average_steps_completed: float | None = None
    common_failure_points: list[str] = Field(default_factory=list)
    last_executed_at: datetime | None = None


class ProgressTracker:
    """
    Tracks progress of runbook executions.

    Provides real-time progress updates, time estimates,
    and historical metrics.
    """

    def __init__(self, store: ExecutionStore | None = None):
        self.store = store or execution_store
        self._historical: dict[str, list[RunbookExecution]] = {}

    async def get_progress(self, execution_id: str) -> ExecutionProgress | None:
        """
        Get detailed progress for an execution.

        Args:
            execution_id: The execution to get progress for

        Returns:
            ExecutionProgress with detailed step-by-step progress
        """
        execution = await self.store.get(execution_id)
        if not execution:
            return None

        return self._build_progress(execution)

    async def get_summary(self, execution_id: str) -> ExecutionSummary | None:
        """
        Get a summary of an execution for listing.

        Args:
            execution_id: The execution to summarize

        Returns:
            ExecutionSummary with key metrics
        """
        execution = await self.store.get(execution_id)
        if not execution:
            return None

        return ExecutionSummary(
            execution_id=execution.execution_id,
            runbook_title=execution.runbook_title,
            incident_id=execution.incident_id,
            status=execution.status,
            progress_percentage=execution.progress_percentage,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            initiated_by=execution.initiated_by,
            total_steps=execution.total_steps,
            completed_steps=execution.completed_steps,
        )

    async def list_active_executions(self) -> list[ExecutionSummary]:
        """List all active executions with summaries."""
        active = await self.store.list_active()
        return [
            ExecutionSummary(
                execution_id=e.execution_id,
                runbook_title=e.runbook_title,
                incident_id=e.incident_id,
                status=e.status,
                progress_percentage=e.progress_percentage,
                started_at=e.started_at,
                completed_at=e.completed_at,
                initiated_by=e.initiated_by,
                total_steps=e.total_steps,
                completed_steps=e.completed_steps,
            )
            for e in active
        ]

    async def get_incident_executions(self, incident_id: str) -> list[ExecutionSummary]:
        """Get all executions for an incident."""
        executions = await self.store.get_by_incident(incident_id)
        return [
            ExecutionSummary(
                execution_id=e.execution_id,
                runbook_title=e.runbook_title,
                incident_id=e.incident_id,
                status=e.status,
                progress_percentage=e.progress_percentage,
                started_at=e.started_at,
                completed_at=e.completed_at,
                initiated_by=e.initiated_by,
                total_steps=e.total_steps,
                completed_steps=e.completed_steps,
            )
            for e in executions
        ]

    async def get_historical_metrics(self, runbook_id: str) -> HistoricalMetrics | None:
        """
        Get historical metrics for a runbook.

        Analyzes past executions to provide metrics like
        average duration, success rate, and common failure points.
        """
        if runbook_id not in self._historical:
            return None

        executions = self._historical[runbook_id]
        if not executions:
            return None

        completed = [e for e in executions if e.status == "completed"]
        failed = [e for e in executions if e.status in ("aborted", "rolled_back")]

        # Calculate durations for completed executions
        durations = []
        for e in completed:
            if e.completed_at and e.started_at:
                duration = (e.completed_at - e.started_at).total_seconds() / 60
                durations.append(duration)

        # Find common failure points
        failure_points: dict[str, int] = {}
        for e in failed:
            for step in e.steps:
                if step.status == StepStatus.FAILED:
                    failure_points[step.title] = failure_points.get(step.title, 0) + 1

        common_failures = sorted(
            failure_points.keys(),
            key=lambda x: failure_points[x],
            reverse=True,
        )[:5]

        # Calculate averages
        avg_duration = sum(durations) / len(durations) if durations else None
        avg_steps = (
            sum(e.completed_steps for e in completed) / len(completed)
            if completed
            else None
        )

        sorted_durations = sorted(durations) if durations else []
        median_duration = (
            sorted_durations[len(sorted_durations) // 2]
            if sorted_durations
            else None
        )

        # Get last execution
        last_execution = max(executions, key=lambda e: e.started_at)

        return HistoricalMetrics(
            runbook_id=runbook_id,
            runbook_title=last_execution.runbook_title,
            total_executions=len(executions),
            successful_executions=len(completed),
            failed_executions=len(failed),
            aborted_executions=sum(1 for e in executions if e.status == "aborted"),
            average_duration_minutes=avg_duration,
            median_duration_minutes=median_duration,
            min_duration_minutes=min(durations) if durations else None,
            max_duration_minutes=max(durations) if durations else None,
            average_steps_completed=avg_steps,
            common_failure_points=common_failures,
            last_executed_at=last_execution.started_at,
        )

    async def record_completion(self, execution: RunbookExecution) -> None:
        """
        Record a completed execution for historical analysis.

        Called when an execution finishes (completed, aborted, etc.)
        """
        if execution.runbook_id not in self._historical:
            self._historical[execution.runbook_id] = []

        # Keep only last 100 executions per runbook
        if len(self._historical[execution.runbook_id]) >= 100:
            self._historical[execution.runbook_id] = self._historical[
                execution.runbook_id
            ][-99:]

        self._historical[execution.runbook_id].append(execution)

        logger.info(
            "execution_recorded_for_metrics",
            runbook_id=execution.runbook_id,
            execution_id=execution.execution_id,
            status=execution.status,
        )

    def _build_progress(self, execution: RunbookExecution) -> ExecutionProgress:
        """Build ExecutionProgress from execution state."""
        now = datetime.utcnow()
        elapsed = (now - execution.started_at).total_seconds()

        # Count pending steps
        pending = sum(
            1
            for s in execution.steps
            if s.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS, StepStatus.BLOCKED)
        )

        # Build step progress list
        steps = [
            StepProgress(
                step_id=s.step_id,
                step_number=s.step_number,
                title=s.title,
                status=s.status,
                is_current=(i == execution.current_step_index),
                duration_seconds=s.duration_seconds,
                estimated_duration_minutes=s.estimated_duration_minutes,
                notes=s.notes,
                completed_by=s.completed_by,
                has_rollback=s.has_rollback,
                rollback_executed=s.rollback_executed,
            )
            for i, s in enumerate(execution.steps)
        ]

        # Get current step
        current_step = None
        if execution.current_step:
            idx = execution.current_step_index
            current_step = steps[idx] if idx < len(steps) else None

        # Estimate remaining time
        estimated_remaining = execution.estimated_time_remaining_minutes
        estimated_completion = None
        if estimated_remaining:
            estimated_completion = now + timedelta(minutes=estimated_remaining)

        return ExecutionProgress(
            execution_id=execution.execution_id,
            runbook_id=execution.runbook_id,
            runbook_title=execution.runbook_title,
            incident_id=execution.incident_id,
            status=execution.status,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            last_activity_at=execution.last_activity_at,
            total_steps=execution.total_steps,
            completed_steps=execution.completed_steps,
            skipped_steps=execution.skipped_steps,
            failed_steps=execution.failed_steps,
            pending_steps=pending,
            progress_percentage=execution.progress_percentage,
            elapsed_seconds=elapsed,
            estimated_remaining_minutes=estimated_remaining,
            estimated_completion_at=estimated_completion,
            current_step=current_step,
            steps=steps,
            initiated_by=execution.initiated_by,
            participants=execution.participants,
        )

    async def calculate_eta(
        self,
        execution_id: str,
        use_historical: bool = True,
    ) -> dict[str, Any]:
        """
        Calculate estimated time of arrival (completion).

        Uses both current execution pace and historical data
        to provide accurate estimates.
        """
        execution = await self.store.get(execution_id)
        if not execution:
            return {"error": "Execution not found"}

        now = datetime.utcnow()
        elapsed = (now - execution.started_at).total_seconds()

        # Method 1: Based on remaining step estimates
        remaining_by_estimates = execution.estimated_time_remaining_minutes

        # Method 2: Based on current pace
        completed = execution.completed_steps + execution.skipped_steps
        remaining_steps = execution.total_steps - completed

        remaining_by_pace = None
        if completed > 0:
            avg_time_per_step = elapsed / completed / 60  # minutes
            remaining_by_pace = int(avg_time_per_step * remaining_steps)

        # Method 3: Based on historical data
        remaining_by_history = None
        if use_historical and execution.runbook_id in self._historical:
            metrics = await self.get_historical_metrics(execution.runbook_id)
            if metrics and metrics.average_duration_minutes:
                historical_remaining = max(
                    0, metrics.average_duration_minutes - (elapsed / 60)
                )
                remaining_by_history = int(historical_remaining)

        # Combine estimates (weighted average)
        estimates = []
        if remaining_by_estimates:
            estimates.append(remaining_by_estimates)
        if remaining_by_pace:
            estimates.append(remaining_by_pace)
        if remaining_by_history:
            estimates.append(remaining_by_history)

        combined_estimate = (
            int(sum(estimates) / len(estimates)) if estimates else None
        )

        eta = (
            now + timedelta(minutes=combined_estimate) if combined_estimate else None
        )

        return {
            "execution_id": execution_id,
            "progress_percentage": execution.progress_percentage,
            "elapsed_minutes": round(elapsed / 60, 1),
            "estimated_remaining_minutes": combined_estimate,
            "eta": eta.isoformat() if eta else None,
            "estimation_methods": {
                "by_step_estimates": remaining_by_estimates,
                "by_current_pace": remaining_by_pace,
                "by_historical_data": remaining_by_history,
            },
        }

    async def get_step_analytics(
        self,
        execution_id: str,
    ) -> dict[str, Any]:
        """
        Get detailed analytics for each step.

        Useful for identifying bottlenecks and slow steps.
        """
        execution = await self.store.get(execution_id)
        if not execution:
            return {"error": "Execution not found"}

        step_analytics = []
        for step in execution.steps:
            analytics = {
                "step_id": step.step_id,
                "step_number": step.step_number,
                "title": step.title,
                "status": step.status.value,
                "type": step.step_type.value,
                "duration_seconds": step.duration_seconds,
            }

            # Compare to estimate
            if step.estimated_duration_minutes and step.duration_seconds:
                expected_seconds = step.estimated_duration_minutes * 60
                variance = step.duration_seconds - expected_seconds
                analytics["variance_seconds"] = variance
                analytics["variance_percentage"] = round(
                    (variance / expected_seconds) * 100, 1
                )

            # Add automation details
            if step.automation_result:
                analytics["automation"] = {
                    "success": step.automation_result.success,
                    "duration_ms": step.automation_result.duration_ms,
                    "exit_code": step.automation_result.exit_code,
                    "error": step.automation_result.error,
                }

            step_analytics.append(analytics)

        # Calculate totals
        total_duration = sum(
            s.duration_seconds or 0 for s in execution.steps
        )
        automated_count = sum(
            1 for s in execution.steps if s.automation_result
        )

        return {
            "execution_id": execution_id,
            "total_duration_seconds": total_duration,
            "total_steps": len(execution.steps),
            "automated_steps": automated_count,
            "manual_steps": len(execution.steps) - automated_count,
            "steps": step_analytics,
        }


# Global progress tracker instance
progress_tracker = ProgressTracker()
