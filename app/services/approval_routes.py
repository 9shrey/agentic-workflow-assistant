"""FastAPI routes for approval management."""

from fastapi import APIRouter, HTTPException

from app.database import sync_engine
from app.models.workflow_run import WorkflowRun
from app.models.approval import Approval
from app.agent.state import AgentState
from app.agent.graph import resume_workflow_after_approval
from app.services.approval_service import ApprovalService
from sqlalchemy.orm import Session

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _get_sync_db() -> Session:
    db = Session(sync_engine)
    try:
        yield db
    finally:
        db.close()


def _resume_if_fully_decided(workflow_id: str, db: Session, result: dict) -> dict:
    """Resume the workflow once every approval for it has been decided.

    The decisions are read back **per row** from the approvals table and handed
    to the graph as an ``approval_id -> status`` map. Passing a single boolean
    here would apply one reviewer's answer to every outstanding item, so
    rejecting four actions and approving the fifth would execute all five.
    """
    remaining = (
        db.query(Approval)
        .filter(Approval.workflow_id == workflow_id, Approval.status == "pending")
        .count()
    )
    if remaining:
        result["remaining_approvals"] = remaining
        return result

    run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
    if not (run and run.agent_state):
        result["workflow_resumed"] = False
        return result

    decisions = {
        a.id: a.status
        for a in db.query(Approval).filter(Approval.workflow_id == workflow_id).all()
    }

    state = AgentState.model_validate(run.agent_state)
    state = resume_workflow_after_approval(workflow_id, state, db, decisions=decisions)
    result["workflow_status"] = state.status
    result["final_response"] = state.final_response
    result["executed_actions"] = len(state.approved_drafts) + len(state.approved_events)
    return result


def _decide(approval_id: str, decision: str) -> dict:
    db = next(_get_sync_db())
    try:
        svc = ApprovalService(db)
        approval = svc.decide_approval(approval_id, decision)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        result = {
            "approval_id": approval.id,
            "status": approval.status,
            "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
            "workflow_id": approval.workflow_id,
        }
        return _resume_if_fully_decided(approval.workflow_id, db, result)
    finally:
        db.close()


@router.post("/{approval_id}/approve")
async def approve_action(approval_id: str):
    """Approve a single pending action (draft email or calendar event)."""
    return _decide(approval_id, "approved")


@router.post("/{approval_id}/reject")
async def reject_action(approval_id: str):
    """Reject a single pending action."""
    return _decide(approval_id, "rejected")
