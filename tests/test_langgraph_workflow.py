"""Tests for the LangGraph StateGraph assembly, interrupt, and approval gating."""

import pytest
from langgraph.graph import END
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.database import init_db, sync_engine
from app.agent.graph import (
    ORDERED_NODES,
    apply_approval_decisions,
    build_workflow_graph,
    create_initial_state,
    resume_workflow_after_approval,
    run_workflow,
)
from app.agent.nodes import execute_approved_actions_node
from app.agent.router import router
from app.agent.state import AgentState
from app.models.approval import Approval
from app.models.audit_log import AuditLog
from app.models.workflow_run import WorkflowRun

FULL_REQUEST = (
    "Find all pending invoices, draft reminder emails, and schedule follow-ups."
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


@pytest.fixture
def db() -> Session:
    with Session(sync_engine) as session:
        yield session
        session.query(AuditLog).delete()
        session.query(Approval).delete()
        session.query(WorkflowRun).delete()
        session.commit()


class TestGraphAssembly:
    """The workflow must be an actual compiled LangGraph graph, not a loop."""

    def test_graph_compiles_to_a_langgraph_state_graph(self, db: Session):
        graph = build_workflow_graph(db)
        assert isinstance(graph, CompiledStateGraph)

    def test_every_node_is_registered_on_the_graph(self, db: Session):
        nodes = set(build_workflow_graph(db).get_graph().nodes.keys())
        for node_name in ORDERED_NODES:
            assert node_name in nodes, f"{node_name} missing from the graph"

    def test_graph_has_a_checkpointer(self, db: Session):
        assert build_workflow_graph(db).checkpointer is not None

    def test_router_end_value_is_the_langgraph_sentinel(self):
        """The router doubles as the conditional-edge function, so its
        terminal value has to be LangGraph's own END sentinel."""
        state = AgentState(workflow_id="wf-1", user_request="x", status="completed")
        assert router(state) == END


class TestInterrupt:
    """The approval checkpoint must be a real interrupt(), not an early return."""

    async def test_graph_pauses_at_the_approval_node(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        assert state.status == "awaiting_approval"

        snapshot = build_workflow_graph(db).get_state(
            {"configurable": {"thread_id": workflow_id}}
        )
        # A paused graph reports the node it is suspended on.
        assert snapshot.next == ("approval_checkpoint_node",)
        assert snapshot.interrupts

    async def test_interrupt_payload_describes_the_pending_actions(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        await run_workflow(workflow_id, state, db, stop_at_approval=True)

        snapshot = build_workflow_graph(db).get_state(
            {"configurable": {"thread_id": workflow_id}}
        )
        payload = snapshot.interrupts[0].value
        assert payload["workflow_id"] == workflow_id
        assert len(payload["pending_approvals"]) > 0

    async def test_resume_clears_the_pause_and_completes(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)
        state = resume_workflow_after_approval(workflow_id, state, db, approved=True)

        assert state.status == "completed"
        snapshot = build_workflow_graph(db).get_state(
            {"configurable": {"thread_id": workflow_id}}
        )
        assert snapshot.next == ()

    async def test_stop_at_approval_false_runs_straight_through(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=False)
        assert state.status == "completed"


class TestPerItemApproval:
    """Regression tests for the approval-granularity bug.

    Resume used to take a single `approved` boolean and stamp it onto every
    pending approval, so rejecting four actions and approving the fifth
    executed all five.
    """

    async def test_approving_one_item_executes_only_that_item(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        drafts = [
            a for a in state.pending_approvals if a["approval_type"] == "gmail_draft"
        ]
        assert len(drafts) > 1, "need multiple drafts for this to be meaningful"

        decisions = {a["approval_id"]: "rejected" for a in state.pending_approvals}
        decisions[drafts[0]["approval_id"]] = "approved"

        state = resume_workflow_after_approval(
            workflow_id, state, db, decisions=decisions
        )

        assert state.status == "completed"
        assert len(state.approved_drafts) == 1
        assert len(state.approved_events) == 0

    async def test_rejecting_everything_executes_nothing(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        decisions = {a["approval_id"]: "rejected" for a in state.pending_approvals}
        state = resume_workflow_after_approval(
            workflow_id, state, db, decisions=decisions
        )

        assert state.approved_drafts == []
        assert state.approved_events == []

    async def test_every_approval_carries_its_database_id(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)

        row_ids = {
            a.id
            for a in db.query(Approval).filter(Approval.workflow_id == workflow_id).all()
        }
        assert row_ids
        for approval in state.pending_approvals:
            assert approval["approval_id"] in row_ids


class TestApprovalDecisionSemantics:
    def test_missing_decision_defaults_to_rejected(self):
        """An approval gate that defaults to 'allow' is not a gate."""
        approvals = [{"approval_id": "a1", "approval_type": "gmail_draft"}]
        assert apply_approval_decisions(approvals, {})[0]["status"] == "rejected"

    def test_unknown_decision_value_is_rejected(self):
        approvals = [{"approval_id": "a1", "approval_type": "gmail_draft"}]
        resolved = apply_approval_decisions(approvals, {"a1": "maybe"})
        assert resolved[0]["status"] == "rejected"

    def test_none_decision_is_rejected(self):
        approvals = [{"approval_id": "a1", "approval_type": "gmail_draft"}]
        assert apply_approval_decisions(approvals, None)[0]["status"] == "rejected"

    def test_bool_applies_to_every_item(self):
        approvals = [{"approval_id": "a1"}, {"approval_id": "a2"}]
        assert [a["status"] for a in apply_approval_decisions(approvals, True)] == [
            "approved",
            "approved",
        ]

    def test_decisions_do_not_mutate_the_input(self):
        approvals = [{"approval_id": "a1"}]
        apply_approval_decisions(approvals, True)
        assert "status" not in approvals[0]


class TestExecuteNodeIdempotency:
    """The plan routes through the execute node once per action type, so
    running it twice must not double up the executed actions."""

    async def test_second_execution_is_a_no_op(self, db: Session):
        workflow_id, state = await create_initial_state(FULL_REQUEST, db)
        state = await run_workflow(workflow_id, state, db, stop_at_approval=True)
        state = resume_workflow_after_approval(workflow_id, state, db, approved=True)

        first_count = len(state.approved_drafts)
        assert first_count > 0

        again = execute_approved_actions_node(state, db)
        assert again == {}
        assert len(state.approved_drafts) == first_count
