"""LangGraph workflow graph assembly and execution orchestration."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.agent.state import AgentState
from app.agent.nodes import (
    planner_node,
    search_email_node,
    summarize_threads_node,
    extract_invoice_node,
    draft_email_node,
    propose_calendar_node,
    approval_checkpoint_node,
    execute_approved_actions_node,
    final_summary_node,
)
from app.agent.router import router
from app.models.workflow_run import WorkflowRun
from app.models.approval import Approval
from app.services.audit_service import AuditService

NODE_FUNCTIONS = {
    "planner_node": planner_node,
    "search_email_node": search_email_node,
    "summarize_threads_node": summarize_threads_node,
    "extract_invoice_node": extract_invoice_node,
    "draft_email_node": draft_email_node,
    "propose_calendar_node": propose_calendar_node,
    "approval_checkpoint_node": approval_checkpoint_node,
    "execute_approved_actions_node": execute_approved_actions_node,
    "final_summary_node": final_summary_node,
}

ORDERED_NODES = [
    "planner_node",
    "search_email_node",
    "summarize_threads_node",
    "extract_invoice_node",
    "draft_email_node",
    "propose_calendar_node",
    "approval_checkpoint_node",
    "execute_approved_actions_node",
    "final_summary_node",
]


async def run_workflow(
    workflow_id: str,
    state: AgentState,
    db: Session,
    max_steps: int = 20,
    stop_at_approval: bool = True,
) -> AgentState:
    """Execute the workflow as a sequential state machine.

    Args:
        workflow_id: The ID of the workflow run.
        state: The initial or current agent state.
        db: Database session.
        max_steps: Maximum number of node executions to prevent infinite loops.
        stop_at_approval: If True, pause execution at approval checkpoints.

    Returns:
        The final agent state after execution or after hitting an approval pause.
    """
    # Step 1: Run the planner to generate the plan
    if not state.plan:
        planner_updates = planner_node(state, db)
        state = state.model_copy(update=planner_updates)
        state = state.model_copy(update={"current_step_index": 0})
        _persist_state(state, db)

    step_count = 0

    while step_count < max_steps:
        step_count += 1
        next_node = router(state)

        if next_node == "__end__":
            break

        if next_node == "approval_checkpoint_node" and stop_at_approval:
            node_fn = NODE_FUNCTIONS.get(next_node)
            if node_fn:
                updates = node_fn(state, db)
                state = state.model_copy(update=updates)

            _persist_state(state, db)
            _create_approval_records(state, db)
            return state  # Return immediately - workflow is awaiting approval

        node_fn = NODE_FUNCTIONS.get(next_node)
        if not node_fn:
            break

        try:
            updates = node_fn(state, db)
            state = state.model_copy(update=updates)
        except Exception as e:
            state.add_error(next_node, str(e))

        # Advance to next step in plan AFTER execution
        if state.plan and state.current_step_index < len(state.plan.steps):
            state = state.model_copy(
                update={"current_step_index": state.current_step_index + 1}
            )
        _persist_state(state, db)

    # Generate final summary if not already at a terminal state
    if state.status not in ("completed", "awaiting_approval"):
        final_updates = final_summary_node(state, db)
        state = state.model_copy(update=final_updates)

    _persist_state(state, db)
    return state


def _persist_state(state: AgentState, db: Session) -> None:
    """Save the current agent state to the workflow run record."""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == state.workflow_id).first()
    if run:
        run.status = state.status
        run.plan = state.plan.model_dump(mode="json") if state.plan else None
        run.agent_state = state.model_dump(mode="json")
        run.final_response = state.final_response or None
        run.updated_at = datetime.now(timezone.utc)
        db.commit()


def _create_approval_records(state: AgentState, db: Session) -> None:
    """Create Approval records in the database from pending_approvals."""
    for approval_data in state.pending_approvals:
        existing = (
            db.query(Approval)
            .filter(
                Approval.workflow_id == state.workflow_id,
                Approval.approval_type == approval_data["approval_type"],
                Approval.proposed_action == approval_data["proposed_action"],
            )
            .first()
        )
        if not existing:
            approval = Approval(
                id=str(uuid.uuid4()),
                workflow_id=state.workflow_id,
                approval_type=approval_data["approval_type"],
                proposed_action=approval_data["proposed_action"],
                proposed_payload=approval_data.get("proposed_payload"),
                status="pending",
            )
            db.add(approval)
    db.commit()


def resume_workflow_after_approval(
    workflow_id: str, state: AgentState, db: Session, approved: bool = True
) -> AgentState:
    """Resume a paused workflow after approval/rejection.

    This is called from the approval endpoint handler.
    """
    # Mark pending approvals as approved/rejected
    for approval_data in state.pending_approvals:
        approval_data["status"] = "approved" if approved else "rejected"

    state = state.model_copy(
        update={
            "approval_status": "resolved",
            "status": "in_progress",
        }
    )

    # Execute approved actions
    if approved:
        exec_updates = execute_approved_actions_node(state, db)
        state = state.model_copy(update=exec_updates)

    # Generate final summary
    final_updates = final_summary_node(state, db)
    state = state.model_copy(update=final_updates)

    _persist_state(state, db)
    return state


async def create_initial_state(user_request: str, db: Session) -> tuple[str, AgentState]:
    """Create a new workflow run and initial agent state."""
    workflow_id = str(uuid.uuid4())

    state = AgentState(
        workflow_id=workflow_id,
        user_request=user_request,
        status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    run = WorkflowRun(
        id=workflow_id,
        user_request=user_request,
        status="pending",
        agent_state=state.model_dump(),
    )
    db.add(run)
    db.commit()

    return workflow_id, state
