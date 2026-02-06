"""FastAPI routes for runbook execution."""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .automation import AutomationType, automation_engine
from .executor import (
    RunbookExecution,
    RunbookExecutor,
    RunbookStep,
    StepType,
    execution_store,
)
from .indexer import RunbookIndexer
from .linker import RunbookLinker
from .models import Runbook, RunbookMatch
from .progress import (
    ExecutionProgress,
    ExecutionSummary,
    HistoricalMetrics,
    progress_tracker,
)
from .suggestions import Suggestion, SuggestionsResponse, suggestion_engine

logger = structlog.get_logger()
router = APIRouter(prefix="/api/runbooks", tags=["runbooks"])


# === Request/Response Models ===


class StartExecutionRequest(BaseModel):
    """Request to start a new runbook execution."""

    runbook_id: str
    incident_id: str | None = None
    initiated_by: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] | None = None  # Optional pre-defined steps


class StartExecutionResponse(BaseModel):
    """Response after starting execution."""

    execution_id: str
    runbook_id: str
    runbook_title: str
    total_steps: int
    status: str
    message: str


class CompleteStepRequest(BaseModel):
    """Request to complete a step."""

    user_id: str | None = None
    notes: str | None = None
    skip: bool = False


class ApproveStepRequest(BaseModel):
    """Request to approve a blocked step."""

    approved_by: str
    notes: str | None = None


class ExecuteAutomatedStepRequest(BaseModel):
    """Request to execute an automated step."""

    user_id: str | None = None
    approved_by: str | None = None


class AddNoteRequest(BaseModel):
    """Request to add a note to a step."""

    note: str
    user_id: str | None = None


class AbortExecutionRequest(BaseModel):
    """Request to abort an execution."""

    user_id: str | None = None
    reason: str | None = None


class CommandSafetyCheckRequest(BaseModel):
    """Request to check command safety."""

    command: str


class StepDefinition(BaseModel):
    """Definition of a runbook step for creation."""

    title: str
    description: str | None = None
    step_type: StepType = StepType.MANUAL
    automation_type: AutomationType | None = None
    automation_config: dict[str, Any] = Field(default_factory=dict)
    has_rollback: bool = False
    rollback_step_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    required_approval: bool = False
    approval_roles: list[str] = Field(default_factory=list)
    estimated_duration_minutes: int | None = None


# === Existing Search Endpoints ===


@router.get("", response_model=list[RunbookMatch])
async def search_runbooks(
    query: Annotated[str, Query(description="Search query for runbooks")],
    service: Annotated[str | None, Query(description="Filter by service name")] = None,
    limit: Annotated[int, Query(ge=1, le=20, description="Maximum results")] = 5,
) -> list[RunbookMatch]:
    """
    Search for runbooks matching a query.

    Returns the most relevant runbooks sorted by relevance score.

    Example:
        GET /api/runbooks?query=high+cpu+usage&service=payments-api
    """
    linker = RunbookLinker()

    matches = linker.find_relevant_runbooks(
        query=query,
        service_name=service,
        top_k=limit,
        min_score=0.05,
    )

    logger.info(
        "runbook_search",
        query=query,
        service=service,
        results=len(matches),
    )

    return matches


@router.get("/stats")
async def runbook_stats():
    """Get runbook index statistics."""
    indexer = RunbookIndexer()
    index = indexer.load_index()

    if not index:
        return {
            "indexed": False,
            "message": "No runbook index found. Run 'python -m src.runbooks.indexer --reindex'",
        }

    # Group by source
    by_source = {}
    for rb in index.runbooks:
        key = f"{rb.source_type.value}:{rb.source_name}"
        by_source[key] = by_source.get(key, 0) + 1

    return {
        "indexed": True,
        "built_at": index.built_at.isoformat(),
        "total_runbooks": len(index.runbooks),
        "vocabulary_size": len(index.vocabulary),
        "sources": by_source,
    }


# === Execution Endpoints ===


@router.post("/executions", response_model=StartExecutionResponse)
async def start_execution(request: StartExecutionRequest) -> StartExecutionResponse:
    """
    Start a new runbook execution.

    Creates an execution instance for the specified runbook,
    ready for step-by-step completion.

    Example:
    ```json
    {
        "runbook_id": "github-abc123",
        "incident_id": "INC-12345",
        "initiated_by": "alice@company.com"
    }
    ```
    """
    # Load the runbook
    indexer = RunbookIndexer()
    index = indexer.load_index()

    if not index:
        raise HTTPException(
            status_code=503,
            detail="Runbook index not available. Run reindex first.",
        )

    runbook = next((rb for rb in index.runbooks if rb.id == request.runbook_id), None)
    if not runbook:
        raise HTTPException(
            status_code=404,
            detail=f"Runbook {request.runbook_id} not found",
        )

    executor = RunbookExecutor()

    try:
        execution = await executor.start_execution(
            runbook=runbook,
            incident_id=request.incident_id,
            initiated_by=request.initiated_by,
            context=request.context,
            steps=request.steps,
        )

        logger.info(
            "execution_started_via_api",
            execution_id=execution.execution_id,
            runbook_id=request.runbook_id,
            incident_id=request.incident_id,
        )

        return StartExecutionResponse(
            execution_id=execution.execution_id,
            runbook_id=execution.runbook_id,
            runbook_title=execution.runbook_title,
            total_steps=execution.total_steps,
            status=execution.status,
            message="Execution started successfully",
        )

    except Exception as e:
        logger.error("execution_start_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/executions", response_model=list[ExecutionSummary])
async def list_executions(
    status: Annotated[str | None, Query(description="Filter by status")] = None,
    incident_id: Annotated[str | None, Query(description="Filter by incident")] = None,
) -> list[ExecutionSummary]:
    """
    List runbook executions.

    Returns summaries of executions, optionally filtered by status or incident.
    """
    if incident_id:
        return await progress_tracker.get_incident_executions(incident_id)

    if status == "active":
        return await progress_tracker.list_active_executions()

    # Return all active executions by default
    return await progress_tracker.list_active_executions()


@router.get("/executions/{execution_id}", response_model=ExecutionProgress)
async def get_execution(execution_id: str) -> ExecutionProgress:
    """
    Get detailed execution progress.

    Returns full progress information including all steps and their status.
    """
    progress = await progress_tracker.get_progress(execution_id)

    if not progress:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found",
        )

    return progress


@router.get("/executions/{execution_id}/steps", response_model=list[RunbookStep])
async def get_execution_steps(execution_id: str) -> list[RunbookStep]:
    """Get all steps for an execution."""
    execution = await execution_store.get(execution_id)

    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found",
        )

    return execution.steps


@router.post("/executions/{execution_id}/steps/{step_id}/complete")
async def complete_step(
    execution_id: str,
    step_id: str,
    request: CompleteStepRequest,
) -> ExecutionProgress:
    """
    Complete (check off) a manual step.

    Mark a step as completed and optionally add notes.
    Set `skip: true` to skip the step instead.
    """
    executor = RunbookExecutor()

    try:
        execution = await executor.complete_step(
            execution_id=execution_id,
            step_id=step_id,
            user_id=request.user_id,
            notes=request.notes,
            skip=request.skip,
        )

        return await progress_tracker.get_progress(execution_id)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/steps/{step_id}/start")
async def start_step(
    execution_id: str,
    step_id: str,
    user_id: Annotated[str | None, Query(description="User starting the step")] = None,
) -> ExecutionProgress:
    """Mark a step as in progress."""
    executor = RunbookExecutor()

    try:
        await executor.start_step(execution_id, step_id, user_id)
        return await progress_tracker.get_progress(execution_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/steps/{step_id}/execute")
async def execute_automated_step(
    execution_id: str,
    step_id: str,
    request: ExecuteAutomatedStepRequest,
) -> ExecutionProgress:
    """
    Execute an automated step.

    Runs the automation configured for the step.
    For steps requiring approval, provide `approved_by`.
    """
    executor = RunbookExecutor()

    try:
        await executor.execute_automated_step(
            execution_id=execution_id,
            step_id=step_id,
            user_id=request.user_id,
            approved_by=request.approved_by,
        )

        return await progress_tracker.get_progress(execution_id)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/steps/{step_id}/approve")
async def approve_step(
    execution_id: str,
    step_id: str,
    request: ApproveStepRequest,
) -> ExecutionProgress:
    """
    Approve a blocked step.

    Unblocks a step that was waiting for approval.
    """
    executor = RunbookExecutor()

    try:
        await executor.approve_step(
            execution_id=execution_id,
            step_id=step_id,
            approved_by=request.approved_by,
            notes=request.notes,
        )

        return await progress_tracker.get_progress(execution_id)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/steps/{step_id}/rollback")
async def rollback_step(
    execution_id: str,
    step_id: str,
    user_id: Annotated[str | None, Query(description="User executing rollback")] = None,
) -> ExecutionProgress:
    """Execute rollback for a step that has a rollback procedure."""
    executor = RunbookExecutor()

    try:
        await executor.execute_rollback(execution_id, step_id, user_id)
        return await progress_tracker.get_progress(execution_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/steps/{step_id}/note")
async def add_step_note(
    execution_id: str,
    step_id: str,
    request: AddNoteRequest,
) -> ExecutionProgress:
    """Add a note to a step without changing its status."""
    executor = RunbookExecutor()

    try:
        await executor.add_note(
            execution_id=execution_id,
            step_id=step_id,
            note=request.note,
            user_id=request.user_id,
        )

        return await progress_tracker.get_progress(execution_id)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/abort")
async def abort_execution(
    execution_id: str,
    request: AbortExecutionRequest,
) -> ExecutionProgress:
    """Abort a runbook execution."""
    executor = RunbookExecutor()

    try:
        await executor.abort_execution(
            execution_id=execution_id,
            user_id=request.user_id,
            reason=request.reason,
        )

        return await progress_tracker.get_progress(execution_id)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/pause")
async def pause_execution(
    execution_id: str,
    user_id: Annotated[str | None, Query()] = None,
) -> ExecutionProgress:
    """Pause a runbook execution."""
    executor = RunbookExecutor()

    try:
        await executor.pause_execution(execution_id, user_id)
        return await progress_tracker.get_progress(execution_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/resume")
async def resume_execution(
    execution_id: str,
    user_id: Annotated[str | None, Query()] = None,
) -> ExecutionProgress:
    """Resume a paused runbook execution."""
    executor = RunbookExecutor()

    try:
        await executor.resume_execution(execution_id, user_id)
        return await progress_tracker.get_progress(execution_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === Progress & Analytics Endpoints ===


@router.get("/executions/{execution_id}/eta")
async def get_execution_eta(execution_id: str) -> dict:
    """
    Get estimated time of completion.

    Uses multiple estimation methods for accuracy.
    """
    result = await progress_tracker.calculate_eta(execution_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/executions/{execution_id}/analytics")
async def get_execution_analytics(execution_id: str) -> dict:
    """
    Get detailed analytics for the execution.

    Includes per-step timing and variance analysis.
    """
    result = await progress_tracker.get_step_analytics(execution_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/executions/{execution_id}/audit-log")
async def get_execution_audit_log(execution_id: str) -> list[dict]:
    """Get the audit log for an execution."""
    execution = await execution_store.get(execution_id)

    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found",
        )

    return [entry.model_dump() for entry in execution.audit_log]


@router.get("/metrics/{runbook_id}", response_model=HistoricalMetrics | None)
async def get_runbook_metrics(runbook_id: str) -> HistoricalMetrics | None:
    """
    Get historical metrics for a runbook.

    Returns aggregated data from past executions.
    """
    return await progress_tracker.get_historical_metrics(runbook_id)


# === Suggestions Endpoints ===


@router.get("/executions/{execution_id}/suggestions", response_model=SuggestionsResponse)
async def get_suggestions(
    execution_id: str,
    max_suggestions: Annotated[int, Query(ge=1, le=10)] = 5,
) -> SuggestionsResponse:
    """
    Get AI-powered suggestions for the current execution state.

    Returns prioritized recommendations for next actions.
    """
    execution = await execution_store.get(execution_id)

    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found",
        )

    return await suggestion_engine.get_suggestions(
        execution=execution,
        incident_context=execution.context,
        max_suggestions=max_suggestions,
    )


@router.get(
    "/executions/{execution_id}/steps/{step_id}/diagnostics",
    response_model=list[Suggestion],
)
async def get_step_diagnostics(
    execution_id: str,
    step_id: str,
) -> list[Suggestion]:
    """
    Get diagnostic suggestions for a failed step.

    Analyzes the error and provides troubleshooting guidance.
    """
    execution = await execution_store.get(execution_id)

    if not execution:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found",
        )

    return await suggestion_engine.get_diagnostic_suggestions(execution, step_id)


# === Automation Safety Endpoints ===


@router.post("/automation/safety-check")
async def check_command_safety(request: CommandSafetyCheckRequest) -> dict:
    """
    Check if a command is safe to execute.

    Analyzes the command for dangerous patterns.
    """
    return automation_engine.check_command_safety(request.command)


@router.get("/automation/dangerous-patterns")
async def get_dangerous_patterns() -> dict:
    """Get the list of dangerous command patterns."""
    from .automation import DANGEROUS_PATTERNS, SAFE_COMMANDS

    return {
        "dangerous_patterns": DANGEROUS_PATTERNS,
        "safe_commands": SAFE_COMMANDS,
    }
