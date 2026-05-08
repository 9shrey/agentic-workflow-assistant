"""Deterministic router for deciding which node to execute next."""

from app.agent.planner import PlanStepType
from app.agent.state import AgentState


def router(state: AgentState) -> str:
    """Determine the next node based on the current state and plan progress.

    This is a pure, deterministic function - no LLM needed.
    """
    if state.status == "completed":
        return "__end__"

    # If awaiting approval, route to approval handling
    if state.approval_status == "awaiting_approval":
        # Check if all approvals have been decided
        pending = [
            a for a in state.pending_approvals
            if a.get("status", "pending") == "pending"
        ]
        if not pending and state.pending_approvals:
            return "execute_approved_actions_node"
        return "approval_checkpoint_node"

    if not state.plan or state.current_step_index >= len(state.plan.steps):
        return "final_summary_node"

    current_step = state.plan.steps[state.current_step_index]
    step_type = current_step.step

    node_map = {
        PlanStepType.SEARCH_EMAIL_THREADS: "search_email_node",
        PlanStepType.SUMMARIZE_THREADS: "summarize_threads_node",
        PlanStepType.EXTRACT_PENDING_INVOICES: "extract_invoice_node",
        PlanStepType.DRAFT_REMINDER_EMAILS: "draft_email_node",
        PlanStepType.PROPOSE_CALENDAR_FOLLOWUPS: "propose_calendar_node",
        PlanStepType.REQUEST_APPROVAL: "approval_checkpoint_node",
        PlanStepType.CREATE_GMAIL_DRAFTS: "execute_approved_actions_node",
        PlanStepType.CREATE_CALENDAR_FOLLOWUPS: "execute_approved_actions_node",
        PlanStepType.FINAL_SUMMARY: "final_summary_node",
    }

    return node_map.get(step_type, "final_summary_node")
