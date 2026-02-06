"""Comprehensive tests for Runbook Executor module."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.runbooks import (
    AutomationEngine,
    AutomationResult,
    AutomationType,
    ExecutionProgress,
    ExecutionStore,
    HistoricalMetrics,
    ProgressTracker,
    Runbook,
    RunbookExecution,
    RunbookExecutor,
    RunbookSourceType,
    RunbookStep,
    StepProgress,
    StepStatus,
    StepType,
    Suggestion,
    SuggestionEngine,
    SuggestionPriority,
    SuggestionType,
    execution_store,
    progress_tracker,
    suggestion_engine,
)
from src.runbooks.automation import (
    DANGEROUS_PATTERNS,
    SAFE_COMMANDS,
    HttpConfig,
    KubernetesConfig,
    ShellConfig,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def clean_store():
    """Clean the execution store before and after each test."""
    await execution_store.clear()
    yield execution_store
    await execution_store.clear()


@pytest.fixture
def sample_runbook():
    """Sample runbook for testing."""
    return Runbook(
        id="test-runbook-001",
        title="Database Recovery Runbook",
        url="https://docs.example.com/runbooks/db-recovery",
        source_type=RunbookSourceType.LOCAL,
        source_name="test",
        content="""
# Database Recovery Runbook

1. Check database status
2. Review recent deployments
3. [automated] Run health check script
4. Restart database service
5. Verify connectivity
6. [rollback] Restore from backup
        """,
        keywords=["database", "recovery", "outage"],
        services=["payments-api"],
    )


@pytest.fixture
def sample_steps():
    """Sample pre-defined steps for testing."""
    return [
        {
            "step_id": "step-1",
            "title": "Check database status",
            "description": "Verify current database state",
            "step_type": "manual",
            "estimated_duration_minutes": 5,
        },
        {
            "step_id": "step-2",
            "title": "Review recent deployments",
            "description": "Check for recent changes",
            "step_type": "manual",
            "depends_on": ["step-1"],
            "estimated_duration_minutes": 10,
        },
        {
            "step_id": "step-3",
            "title": "Run health check script",
            "step_type": "automated",
            "automation_type": "shell",
            "automation_config": {
                "command": "echo 'Health check passed'",
                "timeout_seconds": 30,
            },
            "depends_on": ["step-2"],
            "estimated_duration_minutes": 2,
        },
        {
            "step_id": "step-4",
            "title": "Restart database service",
            "step_type": "automated",
            "automation_type": "shell",
            "automation_config": {
                "command": "systemctl restart postgresql",
                "timeout_seconds": 60,
            },
            "required_approval": True,
            "approval_roles": ["sre", "dba"],
            "has_rollback": True,
            "rollback_step_id": "step-6",
            "estimated_duration_minutes": 5,
        },
        {
            "step_id": "step-5",
            "title": "Verify connectivity",
            "step_type": "manual",
            "depends_on": ["step-4"],
            "estimated_duration_minutes": 5,
        },
        {
            "step_id": "step-6",
            "title": "Restore from backup",
            "step_type": "rollback",
            "automation_type": "shell",
            "automation_config": {
                "command": "echo 'Restore initiated'",
            },
            "has_rollback": False,
        },
    ]


# === Executor Tests ===


class TestRunbookExecutor:
    """Tests for RunbookExecutor class."""

    @pytest.mark.asyncio
    async def test_start_execution(self, clean_store, sample_runbook, sample_steps):
        """Test starting a new runbook execution."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            incident_id="INC-12345",
            initiated_by="alice@example.com",
            context={"severity": "high"},
            steps=sample_steps,
        )

        assert execution.execution_id is not None
        assert execution.runbook_id == sample_runbook.id
        assert execution.incident_id == "INC-12345"
        assert execution.initiated_by == "alice@example.com"
        assert execution.status == "active"
        assert execution.total_steps == len(sample_steps)
        assert execution.completed_steps == 0
        assert len(execution.audit_log) == 1
        assert execution.audit_log[0].action == "execution_started"

    @pytest.mark.asyncio
    async def test_complete_manual_step(self, clean_store, sample_runbook, sample_steps):
        """Test completing a manual step."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Complete the first step
        updated = await executor.complete_step(
            execution_id=execution.execution_id,
            step_id="step-1",
            user_id="bob@example.com",
            notes="Database status: healthy",
        )

        assert updated.completed_steps == 1
        step = next(s for s in updated.steps if s.step_id == "step-1")
        assert step.status == StepStatus.COMPLETED
        assert step.completed_by == "bob@example.com"
        assert step.notes == "Database status: healthy"
        assert "bob@example.com" in updated.participants

    @pytest.mark.asyncio
    async def test_skip_step(self, clean_store, sample_runbook, sample_steps):
        """Test skipping a step."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Skip the first step
        updated = await executor.complete_step(
            execution_id=execution.execution_id,
            step_id="step-1",
            user_id="alice@example.com",
            notes="Skipping - not applicable",
            skip=True,
        )

        assert updated.skipped_steps == 1
        step = next(s for s in updated.steps if s.step_id == "step-1")
        assert step.status == StepStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_step_dependencies(self, clean_store, sample_runbook, sample_steps):
        """Test that steps with unmet dependencies cannot be completed."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Try to complete step-2 which depends on step-1
        with pytest.raises(ValueError, match="depends on incomplete step"):
            await executor.complete_step(
                execution_id=execution.execution_id,
                step_id="step-2",
            )

    @pytest.mark.asyncio
    async def test_execute_automated_step(self, clean_store, sample_runbook, sample_steps):
        """Test executing an automated step."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Complete dependencies first
        await executor.complete_step(execution.execution_id, "step-1")
        await executor.complete_step(execution.execution_id, "step-2")

        # Execute automated step
        updated = await executor.execute_automated_step(
            execution_id=execution.execution_id,
            step_id="step-3",
            user_id="alice@example.com",
        )

        step = next(s for s in updated.steps if s.step_id == "step-3")
        assert step.status == StepStatus.COMPLETED
        assert step.automation_result is not None
        assert step.automation_result.success is True

    @pytest.mark.asyncio
    async def test_automated_step_requires_approval(
        self, clean_store, sample_runbook, sample_steps
    ):
        """Test that dangerous automated steps require approval."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Complete dependencies
        await executor.complete_step(execution.execution_id, "step-1")
        await executor.complete_step(execution.execution_id, "step-2")
        await executor.execute_automated_step(execution.execution_id, "step-3")

        # Try to execute step-4 which requires approval
        with pytest.raises(ValueError, match="requires approval"):
            await executor.execute_automated_step(
                execution_id=execution.execution_id,
                step_id="step-4",
            )

    @pytest.mark.asyncio
    async def test_approve_and_execute_step(
        self, clean_store, sample_runbook, sample_steps
    ):
        """Test approving and executing a step that requires approval."""
        executor = RunbookExecutor(store=clean_store)

        # Use a mock automation engine that allows dangerous commands
        mock_automation = AutomationEngine(allow_dangerous=True, dry_run=True)
        executor.automation = mock_automation

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Complete dependencies
        await executor.complete_step(execution.execution_id, "step-1")
        await executor.complete_step(execution.execution_id, "step-2")
        await executor.execute_automated_step(execution.execution_id, "step-3")

        # Execute with approval
        updated = await executor.execute_automated_step(
            execution_id=execution.execution_id,
            step_id="step-4",
            approved_by="manager@example.com",
        )

        step = next(s for s in updated.steps if s.step_id == "step-4")
        assert step.approved_by == "manager@example.com"

    @pytest.mark.asyncio
    async def test_abort_execution(self, clean_store, sample_runbook, sample_steps):
        """Test aborting an execution."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        updated = await executor.abort_execution(
            execution_id=execution.execution_id,
            user_id="alice@example.com",
            reason="False alarm",
        )

        assert updated.status == "aborted"
        assert updated.completed_at is not None
        assert any(e.action == "execution_aborted" for e in updated.audit_log)

    @pytest.mark.asyncio
    async def test_pause_and_resume_execution(
        self, clean_store, sample_runbook, sample_steps
    ):
        """Test pausing and resuming an execution."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Pause
        paused = await executor.pause_execution(execution.execution_id)
        assert paused.status == "paused"

        # Resume
        resumed = await executor.resume_execution(execution.execution_id)
        assert resumed.status == "active"

    @pytest.mark.asyncio
    async def test_add_note(self, clean_store, sample_runbook, sample_steps):
        """Test adding notes to a step."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        await executor.add_note(
            execution_id=execution.execution_id,
            step_id="step-1",
            note="First observation",
            user_id="alice@example.com",
        )

        await executor.add_note(
            execution_id=execution.execution_id,
            step_id="step-1",
            note="Second observation",
        )

        updated = await clean_store.get(execution.execution_id)
        step = next(s for s in updated.steps if s.step_id == "step-1")
        assert "First observation" in step.notes
        assert "Second observation" in step.notes

    @pytest.mark.asyncio
    async def test_execution_auto_completes(
        self, clean_store, sample_runbook, sample_steps
    ):
        """Test that execution completes when all steps are done."""
        # Use simpler steps for this test
        simple_steps = [
            {"step_id": "s1", "title": "Step 1", "step_type": "manual"},
            {"step_id": "s2", "title": "Step 2", "step_type": "manual"},
        ]

        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=simple_steps,
        )

        await executor.complete_step(execution.execution_id, "s1")
        updated = await executor.complete_step(execution.execution_id, "s2")

        assert updated.status == "completed"
        assert updated.completed_at is not None
        assert updated.progress_percentage == 100.0

    @pytest.mark.asyncio
    async def test_rollback_execution(self, clean_store, sample_runbook, sample_steps):
        """Test executing a rollback procedure."""
        executor = RunbookExecutor(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Mark step-4 as failed (simulate)
        step = next(s for s in execution.steps if s.step_id == "step-4")
        step.status = StepStatus.FAILED
        await clean_store.save(execution)

        # Execute rollback
        updated = await executor.execute_rollback(
            execution_id=execution.execution_id,
            step_id="step-4",
            user_id="alice@example.com",
        )

        step = next(s for s in updated.steps if s.step_id == "step-4")
        assert step.rollback_executed is True
        assert step.status == StepStatus.ROLLED_BACK


# === Automation Engine Tests ===


class TestAutomationEngine:
    """Tests for AutomationEngine class."""

    @pytest.mark.asyncio
    async def test_execute_safe_shell_command(self):
        """Test executing a safe shell command."""
        engine = AutomationEngine()

        result = await engine.execute(
            automation_type=AutomationType.SHELL,
            config={"command": "echo 'Hello, World!'"},
            context={},
        )

        assert result.success is True
        assert "Hello, World!" in result.output
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_dangerous_command_detection(self):
        """Test that dangerous commands are detected."""
        engine = AutomationEngine(allow_dangerous=False)

        result = await engine.execute(
            automation_type=AutomationType.SHELL,
            config={"command": "rm -rf /tmp/test"},
            context={},
        )

        assert result.success is False
        assert result.requires_approval is True
        assert "requires approval" in result.error.lower()

    @pytest.mark.asyncio
    async def test_dry_run_mode(self):
        """Test dry run mode doesn't execute commands."""
        engine = AutomationEngine(dry_run=True)

        result = await engine.execute(
            automation_type=AutomationType.SHELL,
            config={"command": "echo 'test'"},
            context={},
        )

        assert result.success is True
        assert "[DRY RUN]" in result.output

    @pytest.mark.asyncio
    async def test_command_timeout(self):
        """Test command timeout handling."""
        engine = AutomationEngine()

        result = await engine.execute(
            automation_type=AutomationType.SHELL,
            config={
                "command": "sleep 10",
                "timeout_seconds": 1,
            },
            context={},
        )

        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_variable_substitution(self):
        """Test variable substitution in commands."""
        engine = AutomationEngine()

        result = await engine.execute(
            automation_type=AutomationType.SHELL,
            config={"command": "echo 'Service: ${service_name}'"},
            context={"service_name": "payments-api"},
        )

        assert result.success is True
        assert "payments-api" in result.output

    def test_command_safety_check(self):
        """Test the command safety check method."""
        engine = AutomationEngine()

        # Safe command
        safe_result = engine.check_command_safety("kubectl get pods")
        assert safe_result["is_safe"] is True

        # Dangerous command
        dangerous_result = engine.check_command_safety("rm -rf /")
        assert dangerous_result["is_safe"] is False
        assert dangerous_result["requires_approval"] is True

    @pytest.mark.asyncio
    async def test_http_request_execution(self):
        """Test HTTP request execution."""
        engine = AutomationEngine()

        # Mock the HTTP client
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"status": "ok"}'
            mock_response.json.return_value = {"status": "ok"}

            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            result = await engine.execute(
                automation_type=AutomationType.HTTP,
                config={
                    "url": "https://api.example.com/health",
                    "method": "GET",
                    "expected_status_codes": [200],
                },
                context={},
            )

            assert result.success is True
            assert result.status_code == 200


# === Progress Tracker Tests ===


class TestProgressTracker:
    """Tests for ProgressTracker class."""

    @pytest.mark.asyncio
    async def test_get_progress(self, clean_store, sample_runbook, sample_steps):
        """Test getting execution progress."""
        executor = RunbookExecutor(store=clean_store)
        tracker = ProgressTracker(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        await executor.complete_step(execution.execution_id, "step-1")

        progress = await tracker.get_progress(execution.execution_id)

        assert progress is not None
        assert progress.execution_id == execution.execution_id
        assert progress.completed_steps == 1
        assert progress.progress_percentage > 0
        assert len(progress.steps) == len(sample_steps)

    @pytest.mark.asyncio
    async def test_list_active_executions(self, clean_store, sample_runbook, sample_steps):
        """Test listing active executions."""
        executor = RunbookExecutor(store=clean_store)
        tracker = ProgressTracker(store=clean_store)

        # Create two executions
        await executor.start_execution(
            runbook=sample_runbook,
            incident_id="INC-001",
            steps=sample_steps,
        )
        await executor.start_execution(
            runbook=sample_runbook,
            incident_id="INC-002",
            steps=sample_steps,
        )

        active = await tracker.list_active_executions()

        assert len(active) == 2

    @pytest.mark.asyncio
    async def test_get_incident_executions(self, clean_store, sample_runbook, sample_steps):
        """Test getting executions by incident."""
        executor = RunbookExecutor(store=clean_store)
        tracker = ProgressTracker(store=clean_store)

        # Create executions for same incident
        await executor.start_execution(
            runbook=sample_runbook,
            incident_id="INC-001",
            steps=sample_steps,
        )
        await executor.start_execution(
            runbook=sample_runbook,
            incident_id="INC-001",
            steps=sample_steps[:2],
        )
        # Different incident
        await executor.start_execution(
            runbook=sample_runbook,
            incident_id="INC-002",
            steps=sample_steps,
        )

        executions = await tracker.get_incident_executions("INC-001")

        assert len(executions) == 2

    @pytest.mark.asyncio
    async def test_calculate_eta(self, clean_store, sample_runbook, sample_steps):
        """Test ETA calculation."""
        executor = RunbookExecutor(store=clean_store)
        tracker = ProgressTracker(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        await executor.complete_step(execution.execution_id, "step-1")

        eta = await tracker.calculate_eta(execution.execution_id)

        assert "execution_id" in eta
        assert "progress_percentage" in eta
        assert "estimated_remaining_minutes" in eta

    @pytest.mark.asyncio
    async def test_step_analytics(self, clean_store, sample_runbook, sample_steps):
        """Test step analytics."""
        executor = RunbookExecutor(store=clean_store)
        tracker = ProgressTracker(store=clean_store)

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Start and complete a step
        await executor.start_step(execution.execution_id, "step-1")
        await executor.complete_step(execution.execution_id, "step-1")

        analytics = await tracker.get_step_analytics(execution.execution_id)

        assert "total_steps" in analytics
        assert "steps" in analytics
        assert len(analytics["steps"]) == len(sample_steps)


# === Suggestion Engine Tests ===


class TestSuggestionEngine:
    """Tests for SuggestionEngine class."""

    @pytest.mark.asyncio
    async def test_get_next_step_suggestions(self, clean_store, sample_runbook, sample_steps):
        """Test getting next step suggestions."""
        executor = RunbookExecutor(store=clean_store)
        engine = SuggestionEngine()

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        response = await engine.get_suggestions(execution)

        assert len(response.suggestions) > 0
        # First suggestion should be about the next step
        next_step_suggestions = [
            s for s in response.suggestions if s.suggestion_type == SuggestionType.NEXT_STEP
        ]
        assert len(next_step_suggestions) > 0

    @pytest.mark.asyncio
    async def test_rollback_warning_suggestions(
        self, clean_store, sample_runbook, sample_steps
    ):
        """Test rollback warning suggestions for failed steps."""
        executor = RunbookExecutor(store=clean_store)
        engine = SuggestionEngine()

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Simulate a failed step with rollback
        step = next(s for s in execution.steps if s.step_id == "step-4")
        step.status = StepStatus.FAILED
        await clean_store.save(execution)

        response = await engine.get_suggestions(execution)

        rollback_suggestions = [
            s
            for s in response.suggestions
            if s.suggestion_type == SuggestionType.ROLLBACK_WARNING
        ]
        assert len(rollback_suggestions) > 0

    @pytest.mark.asyncio
    async def test_diagnostic_suggestions(self, clean_store, sample_runbook, sample_steps):
        """Test diagnostic suggestions for failed steps."""
        executor = RunbookExecutor(store=clean_store)
        engine = SuggestionEngine()

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
        )

        # Simulate a failed step with error
        step = next(s for s in execution.steps if s.step_id == "step-3")
        step.status = StepStatus.FAILED
        step.automation_result = AutomationResult(
            success=False,
            error="Connection refused: unable to connect to database",
        )
        await clean_store.save(execution)

        diagnostics = await engine.get_diagnostic_suggestions(execution, "step-3")

        assert len(diagnostics) > 0
        # Should detect connection issue
        connection_suggestions = [
            s for s in diagnostics if "connection" in s.title.lower()
        ]
        assert len(connection_suggestions) > 0

    @pytest.mark.asyncio
    async def test_escalation_suggestions(self, clean_store, sample_runbook, sample_steps):
        """Test escalation suggestions for critical incidents."""
        executor = RunbookExecutor(store=clean_store)
        engine = SuggestionEngine()

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=sample_steps,
            context={"severity": "critical"},
        )

        # Mark a step as failed
        step = next(s for s in execution.steps if s.step_id == "step-1")
        step.status = StepStatus.FAILED
        execution.failed_steps = 1
        await clean_store.save(execution)

        response = await engine.get_suggestions(
            execution, incident_context={"severity": "critical"}
        )

        escalation_suggestions = [
            s
            for s in response.suggestions
            if s.suggestion_type == SuggestionType.ESCALATION
        ]
        assert len(escalation_suggestions) > 0


# === API Route Tests ===


class TestRunbookExecutionRoutes:
    """Tests for runbook execution API routes."""

    def test_search_runbooks(self, client):
        """Test runbook search endpoint."""
        response = client.get("/api/runbooks?query=database+recovery")

        # May return empty list if no index, but should not error
        assert response.status_code == 200

    def test_get_runbook_stats(self, client):
        """Test runbook stats endpoint."""
        response = client.get("/api/runbooks/stats")

        assert response.status_code == 200
        data = response.json()
        assert "indexed" in data

    def test_list_executions_empty(self, client):
        """Test listing executions when empty."""
        response = client.get("/api/runbooks/executions")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_nonexistent_execution(self, client):
        """Test getting a non-existent execution."""
        response = client.get("/api/runbooks/executions/nonexistent-id")

        assert response.status_code == 404

    def test_command_safety_check(self, client):
        """Test command safety check endpoint."""
        # Safe command
        response = client.post(
            "/api/runbooks/automation/safety-check",
            json={"command": "echo hello"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_safe"] is True

        # Dangerous command
        response = client.post(
            "/api/runbooks/automation/safety-check",
            json={"command": "rm -rf /"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_safe"] is False

    def test_get_dangerous_patterns(self, client):
        """Test getting dangerous patterns endpoint."""
        response = client.get("/api/runbooks/automation/dangerous-patterns")

        assert response.status_code == 200
        data = response.json()
        assert "dangerous_patterns" in data
        assert "safe_commands" in data
        assert len(data["dangerous_patterns"]) > 0


# === Integration Tests ===


class TestRunbookExecutionIntegration:
    """Integration tests for the full runbook execution flow."""

    @pytest.mark.asyncio
    async def test_full_execution_flow(self, clean_store, sample_runbook):
        """Test a complete runbook execution from start to finish."""
        executor = RunbookExecutor(store=clean_store)
        tracker = ProgressTracker(store=clean_store)

        # Define simple steps
        steps = [
            {"step_id": "s1", "title": "First step", "step_type": "manual"},
            {"step_id": "s2", "title": "Second step", "step_type": "manual"},
            {"step_id": "s3", "title": "Third step", "step_type": "manual"},
        ]

        # Start execution
        execution = await executor.start_execution(
            runbook=sample_runbook,
            incident_id="INC-INTEGRATION",
            initiated_by="test@example.com",
            steps=steps,
        )

        # Verify initial state
        progress = await tracker.get_progress(execution.execution_id)
        assert progress.status == "active"
        assert progress.progress_percentage == 0

        # Complete steps one by one
        for i, step_id in enumerate(["s1", "s2", "s3"]):
            await executor.start_step(execution.execution_id, step_id)
            await executor.complete_step(
                execution_id=execution.execution_id,
                step_id=step_id,
                user_id="test@example.com",
                notes=f"Completed step {i + 1}",
            )

        # Verify completion
        final = await tracker.get_progress(execution.execution_id)
        assert final.status == "completed"
        assert final.progress_percentage == 100
        assert final.completed_steps == 3

    @pytest.mark.asyncio
    async def test_execution_with_mixed_steps(self, clean_store, sample_runbook):
        """Test execution with manual and automated steps."""
        executor = RunbookExecutor(store=clean_store)

        steps = [
            {"step_id": "manual-1", "title": "Manual check", "step_type": "manual"},
            {
                "step_id": "auto-1",
                "title": "Run script",
                "step_type": "automated",
                "automation_type": "shell",
                "automation_config": {"command": "echo 'automated'"},
            },
            {"step_id": "manual-2", "title": "Final verification", "step_type": "manual"},
        ]

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=steps,
        )

        # Complete manual step
        await executor.complete_step(execution.execution_id, "manual-1")

        # Execute automated step
        await executor.execute_automated_step(execution.execution_id, "auto-1")

        # Complete final step
        updated = await executor.complete_step(execution.execution_id, "manual-2")

        assert updated.status == "completed"
        assert updated.completed_steps == 3

        # Verify automated step has result
        auto_step = next(s for s in updated.steps if s.step_id == "auto-1")
        assert auto_step.automation_result is not None
        assert auto_step.automation_result.success is True

    @pytest.mark.asyncio
    async def test_audit_log_completeness(self, clean_store, sample_runbook):
        """Test that audit log captures all actions."""
        executor = RunbookExecutor(store=clean_store)

        steps = [
            {"step_id": "s1", "title": "Step 1", "step_type": "manual"},
            {"step_id": "s2", "title": "Step 2", "step_type": "manual"},
        ]

        execution = await executor.start_execution(
            runbook=sample_runbook,
            steps=steps,
            initiated_by="alice@example.com",
        )

        await executor.start_step(execution.execution_id, "s1", "alice@example.com")
        await executor.add_note(
            execution.execution_id, "s1", "Note 1", "alice@example.com"
        )
        await executor.complete_step(
            execution.execution_id, "s1", "alice@example.com", "Done"
        )
        await executor.pause_execution(execution.execution_id, "alice@example.com")
        await executor.resume_execution(execution.execution_id, "alice@example.com")
        await executor.complete_step(execution.execution_id, "s2", "bob@example.com")

        final = await clean_store.get(execution.execution_id)

        # Verify audit log entries
        actions = [entry.action for entry in final.audit_log]
        assert "execution_started" in actions
        assert "step_started" in actions
        assert "note_added" in actions
        assert "step_completed" in actions
        assert "execution_paused" in actions
        assert "execution_resumed" in actions
        assert "execution_completed" in actions
