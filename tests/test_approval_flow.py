"""Tests for approval service and approval-based workflow flow."""

import uuid
import pytest
from sqlalchemy.orm import Session

from app.database import init_db, sync_engine
from app.models.approval import Approval
from app.models.workflow_run import WorkflowRun
from app.services.approval_service import ApprovalService
from app.agent.state import AgentState
from app.agent.graph import (
    create_initial_state,
    run_workflow,
    resume_workflow_after_approval,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


@pytest.fixture
def db() -> Session:
    with Session(sync_engine) as session:
        yield session
        # Clean up all records created during this test
        session.query(Approval).delete()
        session.query(WorkflowRun).delete()
        session.commit()


class TestApprovalService:
    def test_create_approval(self, db: Session):
        svc = ApprovalService(db)
        approval = svc.create_approval(
            workflow_id="wf-1",
            approval_type="gmail_draft",
            proposed_action="Create draft to test@example.com",
            proposed_payload={"to": "test@example.com", "subject": "Test"},
        )
        assert approval.id
        assert approval.status == "pending"
        assert approval.workflow_id == "wf-1"

    def test_get_pending_for_workflow(self, db: Session):
        svc = ApprovalService(db)
        svc.create_approval("wf-1", "gmail_draft", "Draft 1")
        svc.create_approval("wf-1", "calendar_event", "Event 1")
        svc.create_approval("wf-2", "gmail_draft", "Other workflow")

        pending = svc.get_pending_for_workflow("wf-1")
        assert len(pending) == 2

    def test_decide_approval_approve(self, db: Session):
        svc = ApprovalService(db)
        approval = svc.create_approval("wf-1", "gmail_draft", "Test draft")
        result = svc.decide_approval(approval.id, "approved")
        assert result.status == "approved"
        assert result.decided_at is not None

    def test_decide_approval_reject(self, db: Session):
        svc = ApprovalService(db)
        approval = svc.create_approval("wf-1", "gmail_draft", "Test draft")
        result = svc.decide_approval(approval.id, "rejected")
        assert result.status == "rejected"

    def test_decide_already_decided_fails(self, db: Session):
        svc = ApprovalService(db)
        approval = svc.create_approval("wf-1", "gmail_draft", "Test draft")
        svc.decide_approval(approval.id, "approved")
        with pytest.raises(ValueError, match="already"):
            svc.decide_approval(approval.id, "rejected")

    def test_invalid_status_fails(self, db: Session):
        svc = ApprovalService(db)
        approval = svc.create_approval("wf-1", "gmail_draft", "Test")
        with pytest.raises(ValueError, match="approved.*rejected"):
            svc.decide_approval(approval.id, "invalid")

    def test_approve_all_for_workflow(self, db: Session):
        svc = ApprovalService(db)
        svc.create_approval("wf-1", "gmail_draft", "Draft 1")
        svc.create_approval("wf-1", "gmail_draft", "Draft 2")
        svc.create_approval("wf-1", "calendar_event", "Event 1")

        count = svc.approve_all_for_workflow("wf-1")
        assert count == 3

        pending = svc.get_pending_for_workflow("wf-1")
        assert len(pending) == 0


class TestApprovalFlow:
    """Integration tests for workflow approval flow."""

    async def test_full_approval_lifecycle(self, db: Session):
        """Test: start workflow -> reach approval -> approve -> resume -> complete."""
        workflow_id, state = await create_initial_state(
            "Find all pending invoices, draft reminder emails, and schedule follow-ups.",
            db,
        )

        # Run to approval checkpoint
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        assert state.status == "awaiting_approval"
        assert len(state.pending_approvals) > 0

        # Verify approval records exist in DB
        approvals = (
            db.query(Approval)
            .filter(Approval.workflow_id == workflow_id)
            .all()
        )
        assert len(approvals) > 0
        assert all(a.status == "pending" for a in approvals)

        # Mark all as approved and resume
        state = resume_workflow_after_approval(workflow_id, state, db, approved=True)

        assert state.status == "completed"
        assert state.final_response != ""
        assert "pending invoices" in state.final_response.lower()

    async def test_approval_rejection_flow(self, db: Session):
        """Test: start -> reach approval -> reject -> complete with no drafts."""
        workflow_id, state = await create_initial_state(
            "Find pending invoices and draft reminders.",
            db,
        )

        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)
        assert state.status == "awaiting_approval"

        state = resume_workflow_after_approval(workflow_id, state, db, approved=False)

        assert state.status == "completed"
        # Approved drafts should be empty since we rejected
        assert len(state.approved_drafts) == 0
