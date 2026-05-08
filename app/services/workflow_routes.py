"""FastAPI routes for workflow management."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import sync_engine
from app.agent.state import AgentState
from app.agent.graph import create_initial_state, run_workflow, resume_workflow_after_approval
from app.models.workflow_run import WorkflowRun
from app.models.approval import Approval
from app.models.audit_log import AuditLog
from app.schemas.requests import WorkflowStartRequest, WorkflowStatusResponse, ApprovalResponse
from app.services.audit_service import AuditService
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _get_sync_db() -> Session:
    """Get a synchronous DB session for workflow execution."""
    from sqlalchemy.orm import Session as SyncSession
    db = SyncSession(sync_engine)
    try:
        yield db
    finally:
        db.close()


@router.post("/start", response_model=WorkflowStatusResponse)
async def start_workflow(request: WorkflowStartRequest):
    """Start a new workflow from a user request."""
    db = next(_get_sync_db())
    try:
        workflow_id, state = await create_initial_state(request.user_request, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
        if not run:
            raise HTTPException(status_code=500, detail="Workflow not found after creation")

        return WorkflowStatusResponse(
            workflow_id=run.id,
            user_request=run.user_request,
            status=run.status,
            plan=run.plan,
            final_response=run.final_response,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
    finally:
        db.close()


@router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow(workflow_id: str):
    """Get the current status of a workflow."""
    db = next(_get_sync_db())
    try:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return WorkflowStatusResponse(
            workflow_id=run.id,
            user_request=run.user_request,
            status=run.status,
            plan=run.plan,
            final_response=run.final_response,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
    finally:
        db.close()


@router.get("/{workflow_id}/pending-approvals")
async def get_pending_approvals(workflow_id: str):
    """Get all pending approvals for a workflow."""
    db = next(_get_sync_db())
    try:
        approvals = (
            db.query(Approval)
            .filter(Approval.workflow_id == workflow_id, Approval.status == "pending")
            .all()
        )
        return [
            {
                "id": a.id,
                "workflow_id": a.workflow_id,
                "approval_type": a.approval_type,
                "proposed_action": a.proposed_action,
                "proposed_payload": a.proposed_payload,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in approvals
        ]
    finally:
        db.close()


@router.get("/{workflow_id}/audit-logs")
async def get_audit_logs(workflow_id: str):
    """Get all audit logs for a workflow."""
    db = next(_get_sync_db())
    try:
        svc = AuditService(db)
        logs = svc.get_logs_for_workflow(workflow_id)
        return [
            {
                "id": l.id,
                "workflow_id": l.workflow_id,
                "tool_name": l.tool_name,
                "input_payload": l.input_payload,
                "output_payload": l.output_payload,
                "status": l.status,
                "error_message": l.error_message,
                "started_at": l.started_at.isoformat() if l.started_at else None,
                "completed_at": l.completed_at.isoformat() if l.completed_at else None,
                "duration_ms": l.duration_ms,
            }
            for l in logs
        ]
    finally:
        db.close()
