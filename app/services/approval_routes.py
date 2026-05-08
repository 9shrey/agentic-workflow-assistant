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


@router.post("/{approval_id}/approve")
async def approve_action(approval_id: str):
    """Approve a pending action (draft email or calendar event)."""
    db = next(_get_sync_db())
    try:
        svc = ApprovalService(db)
        approval = svc.decide_approval(approval_id, "approved")
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        # Check if all approvals for this workflow are decided
        workflow_id = approval.workflow_id
        remaining = (
            db.query(Approval)
            .filter(
                Approval.workflow_id == workflow_id,
                Approval.status == "pending",
            )
            .count()
        )

        result = {
            "approval_id": approval.id,
            "status": approval.status,
            "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
            "workflow_id": workflow_id,
        }

        # If all approvals decided, resume the workflow
        if remaining == 0:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
            if run and run.agent_state:
                state = AgentState.model_validate(run.agent_state)
                state = resume_workflow_after_approval(workflow_id, state, db, approved=True)
                result["workflow_status"] = state.status
                result["final_response"] = state.final_response
            else:
                result["workflow_resumed"] = False
        else:
            result["remaining_approvals"] = remaining

        return result
    finally:
        db.close()


@router.post("/{approval_id}/reject")
async def reject_action(approval_id: str):
    """Reject a pending action."""
    db = next(_get_sync_db())
    try:
        svc = ApprovalService(db)
        approval = svc.decide_approval(approval_id, "rejected")
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        # Check if all approvals for this workflow are decided
        workflow_id = approval.workflow_id
        remaining = (
            db.query(Approval)
            .filter(
                Approval.workflow_id == workflow_id,
                Approval.status == "pending",
            )
            .count()
        )

        result = {
            "approval_id": approval.id,
            "status": approval.status,
            "workflow_id": workflow_id,
        }

        if remaining == 0:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
            if run and run.agent_state:
                state = AgentState.model_validate(run.agent_state)
                state = resume_workflow_after_approval(workflow_id, state, db, approved=False)
                result["workflow_status"] = state.status
                result["final_response"] = state.final_response
            else:
                result["workflow_resumed"] = False
        else:
            result["remaining_approvals"] = remaining

        return result
    finally:
        db.close()
