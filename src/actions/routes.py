"""API routes for suggested actions."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .approval import ApprovalWorkflow
from .engine import ActionEngine
from .executor import ActionExecutor
from .models import SuggestedAction

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])

# Module-level singletons (same pattern as other modules in the project)
_engine = ActionEngine()
_executor = ActionExecutor()
_workflow = ApprovalWorkflow()


class SuggestRequest(BaseModel):
    incident_id: str
    verdict: dict[str, Any]
    context: dict[str, Any] = {}


class ApproveRequest(BaseModel):
    approved_by: str
    reason: str | None = None


class RejectRequest(BaseModel):
    rejected_by: str
    reason: str | None = None


class ExecuteRequest(BaseModel):
    dry_run: bool = False


@router.post("/suggest", response_model=list[SuggestedAction])
async def suggest_actions(req: SuggestRequest) -> list[SuggestedAction]:
    """Generate suggested actions for an incident."""
    ctx = {**req.context, "incident_id": req.incident_id}
    actions = _engine.generate_actions(req.verdict, ctx)

    # Auto-submit high-risk actions for approval
    for action in actions:
        if action.requires_approval:
            _workflow.submit_for_approval(action)

    return actions


@router.post("/{action_id}/approve", response_model=SuggestedAction)
async def approve_action(action_id: str, req: ApproveRequest) -> SuggestedAction:
    """Approve a pending action."""
    try:
        return _workflow.approve(action_id, req.approved_by, req.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{action_id}/reject", response_model=SuggestedAction)
async def reject_action(action_id: str, req: RejectRequest) -> SuggestedAction:
    """Reject a pending action."""
    try:
        return _workflow.reject(action_id, req.rejected_by, req.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{action_id}/execute", response_model=SuggestedAction)
async def execute_action(action_id: str, req: ExecuteRequest) -> SuggestedAction:
    """Execute an action (optionally dry-run)."""
    action = _workflow.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    try:
        return _executor.execute(action, dry_run=req.dry_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pending", response_model=list[SuggestedAction])
async def get_pending() -> list[SuggestedAction]:
    """Get all actions pending approval."""
    return _workflow.get_pending()


@router.get("/history")
async def get_history() -> list[dict]:
    """Get action execution audit log."""
    return _executor.get_audit_log()


@router.get("/{action_id}", response_model=SuggestedAction)
async def get_action(action_id: str) -> SuggestedAction:
    """Get a specific action by ID."""
    action = _workflow.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    return action
