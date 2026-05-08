"""Tests for the agent state model and workflow nodes."""

import pytest
from sqlalchemy.orm import Session

from app.database import init_db, sync_engine
from app.agent.state import AgentState
from app.agent.graph import create_initial_state, run_workflow, resume_workflow_after_approval
from app.agent.planner import PlanStepType
from app.models.workflow_run import WorkflowRun
from app.models.approval import Approval


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


@pytest.fixture
def db() -> Session:
    with Session(sync_engine) as session:
        yield session
        from app.models.workflow_run import WorkflowRun
        from app.models.approval import Approval
        from app.models.audit_log import AuditLog
        session.query(AuditLog).delete()
        session.query(Approval).delete()
        session.query(WorkflowRun).delete()
        session.commit()


class TestAgentState:
    def test_initial_state(self):
        state = AgentState(
            workflow_id="wf-1",
            user_request="Find invoices",
        )
        assert state.workflow_id == "wf-1"
        assert state.status == "pending"
        assert state.search_results == []
        assert state.errors == []

    def test_add_error(self):
        state = AgentState(workflow_id="wf-1", user_request="test")
        state.add_error("search_email", "Connection failed")
        assert len(state.errors) == 1
        assert state.errors[0]["step"] == "search_email"

    def test_model_copy_update(self):
        state = AgentState(workflow_id="wf-1", user_request="test")
        updated = state.model_copy(update={"status": "in_progress"})
        assert updated.status == "in_progress"
        assert updated.workflow_id == "wf-1"


class TestWorkflowCreation:
    async def test_create_initial_state(self, db: Session):
        workflow_id, state = await create_initial_state(
            "Find all pending invoices", db
        )
        assert workflow_id
        assert state.user_request == "Find all pending invoices"
        assert state.status == "pending"

        run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()
        assert run is not None
        assert run.user_request == "Find all pending invoices"


class TestRunWorkflow:
    async def test_full_workflow_runs_to_completion(self, db: Session):
        workflow_id, state = await create_initial_state(
            "Find all pending invoices, draft reminder emails, and schedule follow-ups.",
            db,
        )

        # Run workflow with stop_at_approval=True - should pause at approval
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        assert state.status == "awaiting_approval"
        assert len(state.pending_approvals) > 0
        assert len(state.pending_invoices) > 0
        assert len(state.proposed_email_drafts) > 0

    async def test_workflow_stops_at_approval(self, db: Session):
        workflow_id, state = await create_initial_state(
            "Find invoices, draft reminder emails, and schedule follow-ups.",
            db,
        )

        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        assert state.status == "awaiting_approval"
        assert state.approval_status == "awaiting_approval"
        assert len(state.pending_approvals) >= 1

        # Verify approval records in DB
        approvals = (
            db.query(Approval)
            .filter(Approval.workflow_id == workflow_id)
            .all()
        )
        assert len(approvals) >= 1
        assert all(a.status == "pending" for a in approvals)

    async def test_workflow_without_calendar(self, db: Session):
        """Test a simpler request without calendar steps."""
        workflow_id, state = await create_initial_state(
            "Find invoices and draft reminders",
            db,
        )
        state = await run_workflow(
            workflow_id, state, db, stop_at_approval=True, max_steps=20
        )
        assert state.status in ("awaiting_approval", "completed")
        assert len(state.pending_invoices) >= 0

    async def test_resume_after_approval(self, db: Session):
        workflow_id, state = await create_initial_state(
            "Find all pending invoices, draft reminder emails, and schedule follow-ups.",
            db,
        )

        # Run to approval checkpoint
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        assert state.status == "awaiting_approval"
        drafts_before = len(state.proposed_email_drafts)

        # Resume after approval
        state = resume_workflow_after_approval(workflow_id, state, db, approved=True)

        assert state.status == "completed"
        assert len(state.approved_drafts) == drafts_before
        assert state.final_response != ""

    async def test_run_without_approval_stop(self, db: Session):
        """Run full workflow without stopping at approval (auto-approve mock)."""
        workflow_id, state = await create_initial_state(
            "Find all pending invoices, draft reminder emails.",
            db,
        )
        state = await run_workflow(workflow_id, state, db, stop_at_approval=False)
        assert state.status in ("completed", "awaiting_approval")

    async def test_workflow_audit_logs_created(self, db: Session):
        workflow_id, state = await create_initial_state(
            "Find all pending invoices, draft reminder emails, and schedule follow-ups.",
            db,
        )
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        from app.services.audit_service import AuditService
        svc = AuditService(db)
        logs = svc.get_logs_for_workflow(workflow_id)
        assert len(logs) > 0
        tool_names = {l.tool_name for l in logs}
        assert "planner" in tool_names
        assert "search_email" in tool_names
