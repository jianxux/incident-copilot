"""
Runbook Executor - Execute runbook steps with manual checkoff and automated scripts.

Provides interactive runbook execution with:
- Manual step checkoff with notes
- Automated step execution (with approval gates)
- Progress tracking
- Execution audit logging
- Rollback procedure tracking
"""

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from .automation import AutomationEngine, AutomationResult, AutomationType
from .models import Runbook

logger = structlog.get_logger()


class StepStatus(str, Enum):
    """Status of a runbook step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    BLOCKED = "blocked"  # Waiting for approval
    ROLLED_BACK = "rolled_back"


class StepType(str, Enum):
    """Type of runbook step."""

    MANUAL = "manual"
    AUTOMATED = "automated"
    APPROVAL_GATE = "approval_gate"
    CHECKPOINT = "checkpoint"
    ROLLBACK = "rollback"


class RunbookStep(BaseModel):
    """A single step in a runbook execution."""

    step_id: str
    step_number: int
    title: str
    description: str | None = None
    step_type: StepType = StepType.MANUAL
    status: StepStatus = StepStatus.PENDING

    # Automation config (for automated steps)
    automation_type: AutomationType | None = None
    automation_config: dict[str, Any] = Field(default_factory=dict)

    # Execution details
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None

    # User input
    notes: str | None = None
    completed_by: str | None = None
    approved_by: str | None = None

    # Automation results
    automation_result: AutomationResult | None = None

    # Rollback
    has_rollback: bool = False
    rollback_step_id: str | None = None
    rollback_executed: bool = False

    # Dependencies
    depends_on: list[str] = Field(default_factory=list)
    required_approval: bool = False
    approval_roles: list[str] = Field(default_factory=list)

    # Estimated time
    estimated_duration_minutes: int | None = None


class AuditEntry(BaseModel):
    """Audit log entry for runbook execution."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: str
    step_id: str | None = None
    user_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RunbookExecution(BaseModel):
    """An active runbook execution instance."""

    execution_id: str
    runbook_id: str
    runbook_title: str
    incident_id: str | None = None

    # Steps
    steps: list[RunbookStep] = Field(default_factory=list)
    current_step_index: int = 0

    # Status tracking
    status: str = "active"  # active, paused, completed, aborted, rolled_back
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    last_activity_at: datetime = Field(default_factory=datetime.utcnow)

    # Progress
    total_steps: int = 0
    completed_steps: int = 0
    skipped_steps: int = 0
    failed_steps: int = 0

    # Users
    initiated_by: str | None = None
    participants: list[str] = Field(default_factory=list)

    # Audit trail
    audit_log: list[AuditEntry] = Field(default_factory=list)

    # Context
    context: dict[str, Any] = Field(default_factory=dict)

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps + self.skipped_steps) / self.total_steps * 100

    @property
    def estimated_time_remaining_minutes(self) -> int | None:
        """Estimate time remaining based on pending steps."""
        remaining = 0
        for step in self.steps[self.current_step_index :]:
            if step.status == StepStatus.PENDING:
                remaining += step.estimated_duration_minutes or 5
        return remaining if remaining > 0 else None

    @property
    def current_step(self) -> RunbookStep | None:
        """Get the current active step."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None


class ExecutionStore:
    """In-memory store for runbook executions."""

    def __init__(self):
        self._executions: dict[str, RunbookExecution] = {}
        self._by_incident: dict[str, list[str]] = {}

    async def save(self, execution: RunbookExecution) -> None:
        """Save an execution."""
        self._executions[execution.execution_id] = execution
        if execution.incident_id:
            if execution.incident_id not in self._by_incident:
                self._by_incident[execution.incident_id] = []
            if execution.execution_id not in self._by_incident[execution.incident_id]:
                self._by_incident[execution.incident_id].append(execution.execution_id)

    async def get(self, execution_id: str) -> RunbookExecution | None:
        """Get an execution by ID."""
        return self._executions.get(execution_id)

    async def get_by_incident(self, incident_id: str) -> list[RunbookExecution]:
        """Get all executions for an incident."""
        execution_ids = self._by_incident.get(incident_id, [])
        return [self._executions[eid] for eid in execution_ids if eid in self._executions]

    async def list_active(self) -> list[RunbookExecution]:
        """List all active executions."""
        return [e for e in self._executions.values() if e.status == "active"]

    async def delete(self, execution_id: str) -> bool:
        """Delete an execution."""
        if execution_id in self._executions:
            execution = self._executions.pop(execution_id)
            if execution.incident_id and execution.incident_id in self._by_incident:
                self._by_incident[execution.incident_id] = [
                    eid
                    for eid in self._by_incident[execution.incident_id]
                    if eid != execution_id
                ]
            return True
        return False

    async def clear(self) -> None:
        """Clear all executions (for testing)."""
        self._executions.clear()
        self._by_incident.clear()


# Global execution store
execution_store = ExecutionStore()


class RunbookExecutor:
    """
    Executes runbook steps with manual checkoff and automation support.

    Features:
    - Interactive step execution (checkboxes, notes)
    - Automated steps with approval gates
    - Progress tracking
    - Rollback procedure tracking
    - Comprehensive audit logging
    """

    def __init__(
        self,
        automation_engine: AutomationEngine | None = None,
        store: ExecutionStore | None = None,
    ):
        self.automation = automation_engine or AutomationEngine()
        self.store = store or execution_store

    async def start_execution(
        self,
        runbook: Runbook,
        incident_id: str | None = None,
        initiated_by: str | None = None,
        context: dict[str, Any] | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> RunbookExecution:
        """
        Start a new runbook execution.

        Args:
            runbook: The runbook to execute
            incident_id: Optional incident this execution is for
            initiated_by: User who started the execution
            context: Additional context data
            steps: Pre-defined steps (if not parsing from runbook content)

        Returns:
            The created RunbookExecution instance
        """
        execution_id = str(uuid.uuid4())

        # Parse steps from runbook or use provided steps
        parsed_steps = self._parse_runbook_steps(runbook, steps)

        execution = RunbookExecution(
            execution_id=execution_id,
            runbook_id=runbook.id,
            runbook_title=runbook.title,
            incident_id=incident_id,
            steps=parsed_steps,
            total_steps=len(parsed_steps),
            initiated_by=initiated_by,
            context=context or {},
        )

        # Add audit entry
        execution.audit_log.append(
            AuditEntry(
                action="execution_started",
                user_id=initiated_by,
                details={
                    "runbook_id": runbook.id,
                    "incident_id": incident_id,
                    "total_steps": len(parsed_steps),
                },
            )
        )

        await self.store.save(execution)

        logger.info(
            "runbook_execution_started",
            execution_id=execution_id,
            runbook_id=runbook.id,
            incident_id=incident_id,
            total_steps=len(parsed_steps),
        )

        return execution

    async def complete_step(
        self,
        execution_id: str,
        step_id: str,
        user_id: str | None = None,
        notes: str | None = None,
        skip: bool = False,
    ) -> RunbookExecution:
        """
        Complete (check off) a manual step.

        Args:
            execution_id: The execution instance ID
            step_id: The step to complete
            user_id: User completing the step
            notes: Optional notes about the completion
            skip: If True, skip the step instead of completing

        Returns:
            Updated RunbookExecution
        """
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        step = next((s for s in execution.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step {step_id} not found in execution")

        # Check if step can be completed
        if step.status not in (StepStatus.PENDING, StepStatus.IN_PROGRESS, StepStatus.BLOCKED):
            raise ValueError(f"Step {step_id} cannot be completed (status: {step.status})")

        # Check dependencies
        for dep_id in step.depends_on:
            dep_step = next((s for s in execution.steps if s.step_id == dep_id), None)
            if dep_step and dep_step.status not in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                raise ValueError(f"Step {step_id} depends on incomplete step {dep_id}")

        # Update step
        now = datetime.utcnow()
        step.completed_at = now
        step.completed_by = user_id
        step.notes = notes

        if step.started_at:
            step.duration_seconds = (now - step.started_at).total_seconds()

        if skip:
            step.status = StepStatus.SKIPPED
            execution.skipped_steps += 1
        else:
            step.status = StepStatus.COMPLETED
            execution.completed_steps += 1

        execution.last_activity_at = now

        # Add user to participants
        if user_id and user_id not in execution.participants:
            execution.participants.append(user_id)

        # Advance to next step
        self._advance_current_step(execution)

        # Add audit entry
        execution.audit_log.append(
            AuditEntry(
                action="step_skipped" if skip else "step_completed",
                step_id=step_id,
                user_id=user_id,
                details={"notes": notes},
            )
        )

        # Check if execution is complete
        self._check_execution_complete(execution)

        await self.store.save(execution)

        logger.info(
            "runbook_step_completed",
            execution_id=execution_id,
            step_id=step_id,
            status=step.status.value,
            user_id=user_id,
        )

        return execution

    async def start_step(
        self,
        execution_id: str,
        step_id: str,
        user_id: str | None = None,
    ) -> RunbookExecution:
        """
        Mark a step as in progress.

        Args:
            execution_id: The execution instance ID
            step_id: The step to start
            user_id: User starting the step

        Returns:
            Updated RunbookExecution
        """
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        step = next((s for s in execution.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step {step_id} not found")

        if step.status != StepStatus.PENDING:
            raise ValueError(f"Step {step_id} is not pending (status: {step.status})")

        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.utcnow()
        execution.last_activity_at = step.started_at

        if user_id and user_id not in execution.participants:
            execution.participants.append(user_id)

        execution.audit_log.append(
            AuditEntry(
                action="step_started",
                step_id=step_id,
                user_id=user_id,
            )
        )

        await self.store.save(execution)
        return execution

    async def execute_automated_step(
        self,
        execution_id: str,
        step_id: str,
        user_id: str | None = None,
        approved_by: str | None = None,
    ) -> RunbookExecution:
        """
        Execute an automated step.

        Args:
            execution_id: The execution instance ID
            step_id: The automated step to execute
            user_id: User triggering the execution
            approved_by: Approver for steps requiring approval

        Returns:
            Updated RunbookExecution with automation results
        """
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        step = next((s for s in execution.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step {step_id} not found")

        if step.step_type != StepType.AUTOMATED:
            raise ValueError(f"Step {step_id} is not an automated step")

        # Check if approval is required
        if step.required_approval and not approved_by:
            step.status = StepStatus.BLOCKED
            execution.audit_log.append(
                AuditEntry(
                    action="step_blocked_awaiting_approval",
                    step_id=step_id,
                    user_id=user_id,
                    details={"required_roles": step.approval_roles},
                )
            )
            await self.store.save(execution)
            raise ValueError(f"Step {step_id} requires approval")

        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.utcnow()
        step.approved_by = approved_by

        execution.audit_log.append(
            AuditEntry(
                action="automated_step_started",
                step_id=step_id,
                user_id=user_id,
                details={
                    "automation_type": step.automation_type.value if step.automation_type else None,
                    "approved_by": approved_by,
                },
            )
        )

        await self.store.save(execution)

        try:
            # Execute automation
            result = await self.automation.execute(
                automation_type=step.automation_type,
                config=step.automation_config,
                context=execution.context,
            )

            step.automation_result = result
            step.completed_at = datetime.utcnow()
            step.duration_seconds = (step.completed_at - step.started_at).total_seconds()

            if result.success:
                step.status = StepStatus.COMPLETED
                execution.completed_steps += 1
            else:
                step.status = StepStatus.FAILED
                execution.failed_steps += 1

            execution.audit_log.append(
                AuditEntry(
                    action="automated_step_completed",
                    step_id=step_id,
                    details={
                        "success": result.success,
                        "duration_seconds": step.duration_seconds,
                        "error": result.error,
                    },
                )
            )

        except Exception as e:
            step.status = StepStatus.FAILED
            step.completed_at = datetime.utcnow()
            execution.failed_steps += 1

            step.automation_result = AutomationResult(
                success=False,
                error=str(e),
            )

            execution.audit_log.append(
                AuditEntry(
                    action="automated_step_failed",
                    step_id=step_id,
                    details={"error": str(e)},
                )
            )

            logger.error(
                "automated_step_failed",
                execution_id=execution_id,
                step_id=step_id,
                error=str(e),
            )

        execution.last_activity_at = datetime.utcnow()
        self._advance_current_step(execution)
        self._check_execution_complete(execution)

        await self.store.save(execution)
        return execution

    async def approve_step(
        self,
        execution_id: str,
        step_id: str,
        approved_by: str,
        notes: str | None = None,
    ) -> RunbookExecution:
        """
        Approve a blocked step that requires approval.

        Args:
            execution_id: The execution instance ID
            step_id: The step to approve
            approved_by: User approving the step
            notes: Optional approval notes

        Returns:
            Updated RunbookExecution
        """
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        step = next((s for s in execution.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step {step_id} not found")

        step.approved_by = approved_by
        step.status = StepStatus.PENDING  # Reset to pending so it can be executed
        step.notes = f"Approved: {notes}" if notes else f"Approved by {approved_by}"

        execution.audit_log.append(
            AuditEntry(
                action="step_approved",
                step_id=step_id,
                user_id=approved_by,
                details={"notes": notes},
            )
        )

        await self.store.save(execution)

        logger.info(
            "runbook_step_approved",
            execution_id=execution_id,
            step_id=step_id,
            approved_by=approved_by,
        )

        return execution

    async def execute_rollback(
        self,
        execution_id: str,
        step_id: str,
        user_id: str | None = None,
    ) -> RunbookExecution:
        """
        Execute rollback for a step that has a rollback procedure.

        Args:
            execution_id: The execution instance ID
            step_id: The step to rollback
            user_id: User executing the rollback

        Returns:
            Updated RunbookExecution
        """
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        step = next((s for s in execution.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step {step_id} not found")

        if not step.has_rollback:
            raise ValueError(f"Step {step_id} does not have a rollback procedure")

        if step.rollback_step_id:
            # Execute the linked rollback step
            rollback_step = next(
                (s for s in execution.steps if s.step_id == step.rollback_step_id),
                None,
            )
            if rollback_step and rollback_step.step_type == StepType.AUTOMATED:
                await self.execute_automated_step(
                    execution_id, step.rollback_step_id, user_id
                )

        step.rollback_executed = True
        step.status = StepStatus.ROLLED_BACK

        execution.audit_log.append(
            AuditEntry(
                action="step_rolled_back",
                step_id=step_id,
                user_id=user_id,
            )
        )

        await self.store.save(execution)

        logger.info(
            "runbook_step_rolled_back",
            execution_id=execution_id,
            step_id=step_id,
            user_id=user_id,
        )

        return execution

    async def add_note(
        self,
        execution_id: str,
        step_id: str,
        note: str,
        user_id: str | None = None,
    ) -> RunbookExecution:
        """
        Add a note to a step without changing its status.

        Args:
            execution_id: The execution instance ID
            step_id: The step to add note to
            note: The note content
            user_id: User adding the note

        Returns:
            Updated RunbookExecution
        """
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        step = next((s for s in execution.steps if s.step_id == step_id), None)
        if not step:
            raise ValueError(f"Step {step_id} not found")

        # Append to existing notes
        if step.notes:
            step.notes = f"{step.notes}\n---\n{note}"
        else:
            step.notes = note

        execution.audit_log.append(
            AuditEntry(
                action="note_added",
                step_id=step_id,
                user_id=user_id,
                details={"note": note},
            )
        )

        await self.store.save(execution)
        return execution

    async def abort_execution(
        self,
        execution_id: str,
        user_id: str | None = None,
        reason: str | None = None,
    ) -> RunbookExecution:
        """
        Abort a runbook execution.

        Args:
            execution_id: The execution instance ID
            user_id: User aborting the execution
            reason: Reason for aborting

        Returns:
            Updated RunbookExecution
        """
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        execution.status = "aborted"
        execution.completed_at = datetime.utcnow()

        execution.audit_log.append(
            AuditEntry(
                action="execution_aborted",
                user_id=user_id,
                details={"reason": reason},
            )
        )

        await self.store.save(execution)

        logger.info(
            "runbook_execution_aborted",
            execution_id=execution_id,
            user_id=user_id,
            reason=reason,
        )

        return execution

    async def pause_execution(
        self,
        execution_id: str,
        user_id: str | None = None,
    ) -> RunbookExecution:
        """Pause a runbook execution."""
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        execution.status = "paused"

        execution.audit_log.append(
            AuditEntry(
                action="execution_paused",
                user_id=user_id,
            )
        )

        await self.store.save(execution)
        return execution

    async def resume_execution(
        self,
        execution_id: str,
        user_id: str | None = None,
    ) -> RunbookExecution:
        """Resume a paused runbook execution."""
        execution = await self.store.get(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != "paused":
            raise ValueError(f"Execution {execution_id} is not paused")

        execution.status = "active"

        execution.audit_log.append(
            AuditEntry(
                action="execution_resumed",
                user_id=user_id,
            )
        )

        await self.store.save(execution)
        return execution

    def _parse_runbook_steps(
        self,
        runbook: Runbook,
        steps: list[dict[str, Any]] | None,
    ) -> list[RunbookStep]:
        """Parse runbook content into executable steps."""
        if steps:
            # Use provided steps
            return [
                RunbookStep(
                    step_id=s.get("step_id", str(uuid.uuid4())),
                    step_number=i + 1,
                    title=s.get("title", f"Step {i + 1}"),
                    description=s.get("description"),
                    step_type=StepType(s.get("step_type", "manual")),
                    automation_type=AutomationType(s["automation_type"])
                    if s.get("automation_type")
                    else None,
                    automation_config=s.get("automation_config", {}),
                    has_rollback=s.get("has_rollback", False),
                    rollback_step_id=s.get("rollback_step_id"),
                    depends_on=s.get("depends_on", []),
                    required_approval=s.get("required_approval", False),
                    approval_roles=s.get("approval_roles", []),
                    estimated_duration_minutes=s.get("estimated_duration_minutes"),
                )
                for i, s in enumerate(steps)
            ]

        # Parse from runbook content (simple markdown list parsing)
        import re

        parsed = []
        lines = runbook.content.split("\n")
        step_num = 0

        for line in lines:
            # Match numbered list items or bullet points
            match = re.match(r"^\s*(?:\d+\.|[-*])\s+(.+)$", line)
            if match:
                step_num += 1
                title = match.group(1).strip()

                # Check for automation markers
                step_type = StepType.MANUAL
                automation_type = None

                if "[automated]" in title.lower():
                    step_type = StepType.AUTOMATED
                    title = re.sub(r"\[automated\]", "", title, flags=re.IGNORECASE).strip()

                if "[shell]" in title.lower():
                    step_type = StepType.AUTOMATED
                    automation_type = AutomationType.SHELL
                    title = re.sub(r"\[shell\]", "", title, flags=re.IGNORECASE).strip()

                if "[rollback]" in title.lower():
                    step_type = StepType.ROLLBACK
                    title = re.sub(r"\[rollback\]", "", title, flags=re.IGNORECASE).strip()

                parsed.append(
                    RunbookStep(
                        step_id=str(uuid.uuid4()),
                        step_number=step_num,
                        title=title,
                        step_type=step_type,
                        automation_type=automation_type,
                    )
                )

        return parsed

    def _advance_current_step(self, execution: RunbookExecution) -> None:
        """Advance to the next pending step."""
        for i, step in enumerate(execution.steps):
            if step.status == StepStatus.PENDING:
                execution.current_step_index = i
                return
        execution.current_step_index = len(execution.steps)

    def _check_execution_complete(self, execution: RunbookExecution) -> None:
        """Check if execution is complete."""
        pending = sum(
            1
            for s in execution.steps
            if s.status in (StepStatus.PENDING, StepStatus.IN_PROGRESS, StepStatus.BLOCKED)
        )

        if pending == 0:
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()
            execution.audit_log.append(
                AuditEntry(
                    action="execution_completed",
                    details={
                        "completed_steps": execution.completed_steps,
                        "skipped_steps": execution.skipped_steps,
                        "failed_steps": execution.failed_steps,
                    },
                )
            )

            logger.info(
                "runbook_execution_completed",
                execution_id=execution.execution_id,
                completed_steps=execution.completed_steps,
                skipped_steps=execution.skipped_steps,
                failed_steps=execution.failed_steps,
            )
